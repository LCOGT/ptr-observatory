import datetime
import json
import shelve
import time

import numpy as np
import requests
import serial
import win32com.client

from global_yard import g_dev


# Unused except for WMD
def probeRead(com_port):
    with serial.Serial(com_port, timeout=0.3) as com:
        com.write(b"R1\n")
        probePosition = (
            float(com.read(7).decode()) * 994.96 - 137
        )  # Corrects Probe to Stage. Up and down, lash = 5000 enc.
        print(round(probePosition, 1))


class Focuser:
    def __init__(self, driver: str, name: str, config: dict):
        self.site = config["site"]
        self.name = name
        self.site_path = config["client_path"]
        self.camera_name = config["camera"]["camera_1_1"]["name"]
        g_dev["foc"] = self
        self.config = config["focuser"]["focuser1"]
        self.throw = int(config["focuser"]["focuser1"]["throw"])
        win32com.client.pythoncom.CoInitialize()
        self.focuser = win32com.client.Dispatch(driver)
        time.sleep(4)

        self.focuser.Connected = True
        self.micron_to_steps = float(
            config["focuser"]["focuser1"]["unit_conversion"]
        )  #  Note this can be a bogus value
        self.steps_to_micron = 1 / self.micron_to_steps
        self.focuser_message = "-"
        print(
            "Focuser connected, at:  ",
            round(self.focuser.Position * self.steps_to_micron, 1),
        )
        self.reference = None
        self.last_known_focus = None
        self.last_temperature = None
        self.last_source = None
        self.time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
            days=1
        )  # Initialise last focus as yesterday
        self.images_since_last_focus = (
            10000  # Set images since last focus as sillyvalue
        )
        self.last_focus_fwhm = None
        self.focus_tracker = [np.nan] * 10
        self.focus_needed = False # A variable that if the code detects that the focus has worsened it can trigger an autofocus
        try:
            self.get_af_log()
        except:
            self.set_focal_ref_reset_log(config["focuser"]["focuser1"]["reference"])

        try:
            self.z_compression = config["focuser"]["focuser1"]["z_compression"]
        except:
            self.z_compression = 0.0

        try:  #  NB NB NB This mess neads cleaning up.
            try:
                # TODO no site-specific code!
                if not self.site in ["sro"]:
                    self.last_temperature = self.focuser.Temperature
                    self.reference = self.calculate_compensation(
                        self.focuser.Temperature
                    )  # need to change to config supplied
                else:
                    self.last_temperature = g_dev["ocn"].temperature
                    self.reference = self.calculate_compensation(
                        g_dev["ocn"].temperature
                    )

                print(
                    "Focus position set from temp compensated value:  ",
                    self.reference,
                    ".  Temp used:  ",
                    self.last_temperature,
                )
                self.last_known_focus = self.reference
                self.last_source = "Focuser__init__  Calculate Comp references Config"
            except:
                self.reference = float(
                    self.get_focal_ref()
                )  # need to change to config supplied
                self.last_known_focus = self.reference
                print("Focus reference updated from Night Shelf:  ", self.reference)
                # Is this of any real value except to persist self.last_known...?
        except:
            self.reference = int(self.config["reference"])
            self.last_known_focus = self.reference
            print(
                "Focus reference derived from supplied config file for 10C:  ",
                self.reference,
            )
            # The config reference should be a table of value
        self.focuser.Move(int(float(self.reference) * self.micron_to_steps))


    def calculate_compensation(self, temp_primary):

        if -20 <= temp_primary <= 45:
            trial = round(
                float(
                    self.config["coef_0"] + float(self.config["coef_c"]) * temp_primary
                ),
                1,
            )
            trial = max(trial, 500)  # These values are for an Optec Gemini.
            trial = min(trial, 12150)
            # NB NB Numbers should all come from site config.
            return int(trial)
        print("Primary out of range -20C to 45C, using reference focus.")
        return float(self.config["reference"])

    def get_status(self):
        try:
            status = {
                "focus_position": round(
                    self.focuser.Position * self.steps_to_micron, 1
                ),  # THIS occasionally glitches, usually no temp probe on Gemini
                "focus_temperature": self.focuser.Temperature,
                "focus_moving": self.focuser.IsMoving,
                "comp": self.config["coef_c"],
                "filter_offset": g_dev["fil"].filter_offset,
            }

        except:
            try:
                temp = g_dev["ocn"].current_ambient
            except:
                temp = 10.0  # NB NB NB this needs to be a proper monthly config file default.
            status = {
                "focus_position": round(
                    self.focuser.Position * self.steps_to_micron, 1
                ),
                "focus_temperature": temp,
                "focus_moving": self.focuser.IsMoving,
                "comp": self.config["coef_c"],
                "filter_offset": "n.a",  # g_dev['fil'].filter_offset  # NB A patch
            }
        return status

    def get_quick_status(self, quick):
        quick.append(time.time())
        quick.append(self.focuser.Position * self.steps_to_micron)
        try:
            quick.append(self.focuser.Temperature)
        except:
            quick.append(10.0)
        quick.append(self.focuser.IsMoving)
        return quick

    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0]) / 2, 3))
        average.append(round((pre[1] + post[1]) / 2, 3))
        average.append(round((pre[2] + post[2]) / 2, 3))
        if pre[3] or post[3]:
            average.append(True)
        else:
            average.append(False)
        return average

    def update_job_status(self, cmd_id, status, seconds_remaining=-1):
        """Updates the status of a job.

        Args:
            cmd_id (string): the ulid that identifies the job to update.
            status (string): the new status (eg. "STARTED").
            seconds_remaining (int): time estimate until job is updated as "COMPLETE".
                Note: value of -1 used when no estimate is provided.
        """

        url = "https://jobs.photonranch.org/jobs/updatejobstatus"
        body = {
            "site": self.site,
            "ulid": cmd_id,
            "secondsUntilComplete": seconds_remaining,
            "newStatus": status,
        }
        response = requests.request("POST", url, data=json.dumps(body))
        if response:
            print(response.status_code)
        return response

    def parse_command(self, command):
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]

        if action == "move_relative":
            # Mark a job as "STARTED" just before starting it.
            # Include a time estmiate if possible. This is sent to the UI.
            self.update_job_status(command["ulid"], "STARTED", 5)

            # Do the command. Additional job updates can be sent in this function too.
            self.move_relative_command(req, opt)

            # Mark the job "COMPLETE" when finished.
            self.update_job_status(command["ulid"], "COMPLETE")

        elif action == "move_absolute":
            self.update_job_status(command["ulid"], "STARTED", 5)
            self.move_absolute_command(req, opt)
            self.update_job_status(command["ulid"], "COMPLETE")
        elif action == "go_to_reference":
            self.update_job_status(command["ulid"], "STARTED", 5)
            reference = self.get_focal_ref()
            self.focuser.Move(reference * self.micron_to_steps)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print(">")
            self.update_job_status(command["ulid"], "COMPLETE")
        elif action == "go_to_compensated":
            reference = self.calculate_compensation(self.focuser.Temperature)
            self.focuser.Move(reference * self.micron_to_steps)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print(">")
        elif action == "save_as_reference":
            self.set_focal_ref(
                self.focuser.Position * self.steps_to_micron
            )  # Need to get the alias properly
            # NB NB NB This needs to remove filter offset and save the temperature to be of any value.
        else:
            print(f"Command <{action}> not recognized:", command)

    ###############################
    #       Focuser Commands      #
    ###############################

    def get_position(self, counts=False):
        if not counts:
            return int(self.focuser.Position * self.steps_to_micron)

    def adjust_focus(self):
        """Adjusts the focus relative to the last formal focus procedure.

        This uses te most recent focus procedure that used last_temperature
        to focus. Functionally dependent of temp, coef_c, and filter thickness."""

        # NB NB NB this routine may build up a rounding error so consider making it more
        # absolute.  However if the user adjusted the focus then appling just a delta to their setpoint
        # makes more sense than a full recalcutatin of ax + b...

        # NB NB NB this routine may build up a rounding error so consider making it more
        # absolute.  However if the user adjusted the focus then appling just a delta to their setpoint
        # makes more sense than a full recalcutatin of ax + b...

        try:
            if self.site != "sro":
                temp_delta = self.focuser.Temperature - self.last_temperature
            else:
                try:
                    temp_delta = (
                        g_dev["ocn"].status["temperature_C"] - self.last_temperature
                    )
                except:
                    temp_delta = 0.0

            adjust = 0.0
            if abs(temp_delta) > 0.1 and self.last_temperature is not None:
                adjust = round(temp_delta * float(self.config["coef_c"]), 1)
            adjust += g_dev["fil"].filter_offset

            try:
                self.last_temperature = g_dev["ocn"].status[
                    "temperature_C"
                ]  # Save this for next adjustment
            except:
                pass
            req = {"position": str(self.last_known_focus + adjust)}
            opt = {}
            self.move_absolute_command(req, opt)
        except:
            print("Focus-adjust: no changes made.")

    def guarded_move(self, to_focus):
        try:
            self.focuser.Move(int(to_focus))
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.3)
                print(">f")
        except:
            print("AF Guarded move failed.")

    def move_relative_command(self, req: dict, opt: dict):
        """Sets the focus position by moving relative to current position."""
        # The string must start with a + or a - sign, otherwise treated as zero and no action.

        position_string = req["position"]
        position = int(self.focuser.Position * self.steps_to_micron)
        if position_string[0] != "-":
            relative = int(position_string)
            position += relative
            self.focuser.Move(int(position * self.micron_to_steps))
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print(">f++")
        elif position_string[0] == "-":
            relative = int(position_string[1:])
            position -= relative
            self.focuser.Move(int(position * self.micron_to_steps))
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print(">f rel")
        else:
            print("Supplied relative move is lacking a sign; ignoring.")

    def move_absolute_command(self, req: dict, opt: dict):
        """Sets the focus position by moving to an absolute position."""

        position = int(float(req["position"]))
        current_position = self.focuser.Position * self.steps_to_micron
        if current_position > position:
            tag = ">f abs"
        else:
            tag = "<f abs"
        self.focuser.Move(int(position * self.micron_to_steps))
        print(tag)
        time.sleep(0.3)
        while self.focuser.IsMoving:
            time.sleep(0.3)
            print(tag)

        # Here we could spin until the move is completed, simplifying other devices.
        # Since normally these are short moves,
        # that may make the most sense to keep things seperated.
        # A new seek *may* cause a mount move, a filter, rotator, and focus change.
        # How do we launch all of these in parallel, then
        # send status until each completes, then move on to exposing?

    def stop_command(self, req: dict, opt: dict):
        """stop focuser movement"""
        print(f"focuser cmd: stop")

    def home_command(self, req: dict, opt: dict):
        """set the focuser to the home position"""
        print(f"focuser cmd: home")

    def auto_command(self, req: dict, opt: dict):
        """autofocus"""
        print(f"focuser cmd: auto")

    def set_focal_ref(self, ref):
        cam_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + self.camera_name)
        cam_shelf["focus_ref"] = ref
        cam_shelf.close()
        return

    def set_focal_ref_reset_log(self, ref):
        cam_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + self.camera_name)
        cam_shelf["focus_ref"] = ref
        cam_shelf["af_log"] = []
        cam_shelf.close()
        return

    def af_log(self, ref, fwhm, solved):
        """Logs autofocus data to the night shelf."""

        # Note once focus comp is in place this data
        # needs to be combined with great care.
        cam_shelf = shelve.open(
            self.site_path + "ptr_night_shelf/" + self.camera_name, writeback=True
        )
        try:
            f_temp = (
                self.focuser.Temperature
            )  # NB refering a quantity possibly from WEMA if no focus temp available.
        except:  # Note above in temp comp, sro has no temp probe on gemini
            f_temp = g_dev["ocn"].status["temperature_C"]

        cam_shelf["af_log"].append(
            (f_temp, ref, fwhm, solved, datetime.datetime.now().isoformat())
        )
        cam_shelf.close()
        return

    def get_af_log(self):
        """Retrieves the autofocus log."""

        try:
            cam_shelf = shelve.open(
                self.site_path + "ptr_night_shelf/" + self.camera_name, writeback=True
            )
            for item in cam_shelf["af_log"]:
                print(str(item))
        except:
            print("There is no focus log on the night shelf.")

    def get_focal_ref(self):
        cam_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + self.camera_name)
        focus_ref = cam_shelf["focus_ref"]
        # NB Should we also return and use the ref temp?
        cam_shelf.close()
        return focus_ref


if __name__ == "__main__":
    pass