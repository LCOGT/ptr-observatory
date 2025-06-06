'''
focuser.py focuser.py  focuser.py  focuser.py  focuser.py  focuser.py

'''

'''
   Example : at 0.6 µm, at the F/D 6 focus of an instrument, the focusing tolerance which leads to a focusing \
   precision better than l/8 is 8*62*0.0006*(1/8) = 0.02 mm, ie ± 20 microns.

    F/d Tolerance
        ± mm

    2   0.0025 mm!  Note the units

    3   0.005

    4   0.010

    5   0.015

    6   0.020

    8   0.040

    10  0.060

    12  0.090

    15  0.130

    20  0.240

    30  0.540
'''
import datetime
import json
import shelve
import time

import numpy as np
import requests
import serial
import win32com.client
import traceback
import threading
import copy
from global_yard import g_dev
from ptr_utility import plog
from dateutil import parser
import os

# We only use Observatory in type hints, so use a forward reference to prevent circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from obs import Observatory

# Unused except for WMD
def probeRead(com_port):
    with serial.Serial(com_port, timeout=0.3) as com:
        com.write(b"R1\n")
        probePosition = (
            float(com.read(7).decode()) * 994.96 - 137
        )  # Corrects Probe to Stage. Up and down, lash = 5000 enc.
        plog(round(probePosition, 1))


class Focuser:
    def __init__(self, driver: str, name: str, site_config: dict, observatory: 'Observatory'):
        g_dev["foc"] = self
        self.obs = observatory
        self.obsid = site_config["obs_id"]
        self.name = name
        self.obsid_path = self.obs.obsid_path

        # For now, assume the main camera is the one we are focusing
        self.camera_name = site_config['device_roles']['main_cam']

        self.config = site_config["focuser"][name]

        self.relative_focuser = site_config["focuser"][name]['relative_focuser']
        self.driver = driver

        # Configure the role, if it exists
        # Current design allows for only one role per device
        # We can add more roles by changing self.role to a list and adjusting any references
        self.role = None
        for role, device in site_config['device_roles'].items():
            if device == name:
                self.role = role
                break

        # Set the dummy flag which toggles simulator mode
        self.dummy = (driver == 'dummy')

        # Even in simulator mode, this variable needs to be set
        self.theskyx = (driver == "CCDSoft2XAdaptor.ccdsoft5Camera") or (driver == "TheSky64.ccdsoftCamera")


        if self.dummy:
            self.focuser = 'dummy'
        else:
            win32com.client.pythoncom.CoInitialize()
            self.focuser = win32com.client.Dispatch(driver)
            try:
                self.focuser.Connected = True
            except:
                try:
                    self.focuser.focConnect()
                except:
                    if self.focuser.Link == True:
                        plog ("focuser doesn't have ASCOM Connected keyword, but reports a positive link")
                    else:
                        try:
                            self.focuser.Link = True
                            plog ("focuser doesn't have ASCOM Connected keyword, attempted to send a positive Link")
                        except:
                            plog ("focuser doesn't have ASCOM Connected keyword, also crashed on focuser.Link")


        self.micron_to_steps = float(
            self.config["unit_conversion"]
        )  #  Note this can be a bogus value
        self.steps_to_micron = 1 / self.micron_to_steps

        # Just to need to wait a little bit for PWI3 to boot up, otherwise it sends temperatures that are absolute zero (-273)
        if driver == 'ASCOM.PWI3.Focuser':
            time.sleep(4)

        if not self.dummy and not self.relative_focuser:
            if not self.theskyx:
                self.current_focus_position=self.focuser.Position * self.steps_to_micron
            else:
                try:
                    self.current_focus_position=self.focuser.focPosition() * self.steps_to_micron
                except:
                    self.current_focus_position=self.focuser.focPosition * self.steps_to_micron

        else:
            self.current_focus_position=2000

        self.focuser_update_period=15   #WER changed from 3 20231214
        self.focuser_updates=0
        self.focuser_settle_time= 0 #initialise
        self.guarded_move_requested=False
        self.guarded_move_to_focus=20000

        self.focuser_update_timer=time.time() - 2* self.focuser_update_period
        self.focuser_update_thread=threading.Thread(target=self.focuser_update_thread)
        self.focuser_update_thread.daemon=True
        self.focuser_update_thread.start()
        self.focuser_message = "-"
        if not self.dummy and not self.relative_focuser :
            if self.theskyx:
                try:
                    plog(
                        "Focuser connected, at:  ",
                        round(self.focuser.focPosition() * self.steps_to_micron, 1),
                    )
                except:
                    plog(
                        "Focuser connected, at:  ",
                        round(self.focuser.focPosition * self.steps_to_micron, 1),
                    )
            else:
                plog(
                    "Focuser connected, at:  ",
                    round(self.focuser.Position * self.steps_to_micron, 1),
                )
        else:
            plog ("Focusser connected.")
        self.reference = None
        self.last_known_focus = None
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
        self.focus_temp_slope = None
        self.focus_temp_intercept = None
        self.best_previous_focus_point = None

        # If sufficient previous focus estimates have not been achieved
        # (10 usually) then the focus routines will try hard to find
        # the true focus rather than assume it is somewhere in the ballpark
        # already or "commissioned".
        self.focus_commissioned=False

        self.focuser_is_moving=False

        if not self.dummy:
            if self.theskyx:
                self.current_focus_temperature=self.focuser.focTemperature
            else:
                self.current_focus_temperature=self.focuser.Temperature
        else:
            self.current_focus_temperature=10.0

        self.previous_focus_temperature = copy.deepcopy(self.current_focus_temperature)
        if not self.relative_focuser:
            self.set_initial_best_guess_for_focus()

        try:
            self.last_filter_offset = g_dev["fil"].filter_offset
        except:
            plog ('setting last filter offset to 0')
            self.last_filter_offset= 0

        self.focuser_settle_time=self.config['focuser_movement_settle_time']


        # Load up the throw list unless we don't have one.
        if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'throw' + self.name + str(g_dev['obs'].name) + '.dat'):
            plog ("loading throw from throw shelf")
            # throw_shelf = shelve.open(
            #     g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'throw' + self.name + str(g_dev['obs'].name))
            # try:
            #     self.throw_list = throw_shelf['throw_list']
            #     self.throw = np.nanmedian(self.throw_list)
            #     plog('current throw: ' + str(self.throw))
            # except:
            #     self.throw_list=None
            #     self.throw = None
            shelf_path = os.path.join(
                g_dev['obs'].obsid_path,
                'ptr_night_shelf',
                f"throw{self.name}{g_dev['obs'].name}"
            )

            with shelve.open(shelf_path) as throw_shelf:
                try:
                    self.throw_list = throw_shelf['throw_list']
                    self.throw = min(np.nanmedian(self.throw_list),400)
                    plog(f"current throw: {self.throw}")
                except KeyError:
                    # no 'throw_list' key in shelf
                    self.throw_list = None
                    self.throw = None
        else:
            plog ("loading throw from config")
            self.throw = int(site_config["focuser"][name]["throw"])
            self.throw_list=[self.throw]

        plog ("used throw: " + str(self.throw))


        self.minimum_allowed_focus=self.config['minimum']
        self.maximum_allowed_focus=self.config['maximum']


    def report_optimal_throw(self,curve_step_length):

        # throw_shelf = shelve.open(
        #     g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'throw' + self.name + str(g_dev['obs'].name))

        # throw_list = throw_shelf['throw_list']
        # throw_list.append(
        #     float(abs(curve_step_length))
        # )

        # #update the throw itself
        # self.throw = np.nanmedian(throw_list)

        # too_long = True
        # while too_long:
        #     if len(throw_list) > 100:
        #         throw_list.pop(0)
        #     else:
        #         too_long = False
        # throw_shelf[
        #     "throw_list"
        # ] = throw_list
        # throw_shelf.close()
        shelf_path = os.path.join(
            g_dev['obs'].obsid_path,
            'ptr_night_shelf',
            f"throw{self.name}{g_dev['obs'].name}"
        )

        with shelve.open(shelf_path) as throw_shelf:
            # Load existing list or start fresh
            throw_list = throw_shelf.get('throw_list', [])

            # Append the new throw measurement
            throw_list.append(float(abs(curve_step_length)))

            # Update the running median
            self.throw = min(np.nanmedian(throw_list),1000)

            # Trim to the most recent 100 entries
            if len(throw_list) > 100:
                throw_list = throw_list[-100:]

            # Write the trimmed list back to the shelf
            throw_shelf['throw_list'] = throw_list

    # Note this is a thread!
    def focuser_update_thread(self):

        if not self.dummy:
            win32com.client.pythoncom.CoInitialize()
            self.focuser_update_wincom = win32com.client.Dispatch(self.driver)
            try:
                self.focuser_update_wincom.Connected = True
            except:
                try:
                    self.focuser_update_wincom.focConnect()
                except:
                    if self.focuser_update_wincom.Link == True:
                        plog ("focuser doesn't have ASCOM Connected keyword, but reports a positive link")
                    else:
                        try:
                            self.focuser_update_wincom.Link = True
                            plog ("focuser doesn't have ASCOM Connected keyword, attempted to send a positive Link")
                        except:
                            plog ("focuser doesn't have ASCOM Connected keyword, also crashed on focuser.Link")




        # This stopping mechanism allows for threads to close cleanly.
        while True:
            self.focuser_is_moving=False
            if self.guarded_move_requested:

                try:
                    while g_dev['cam'].shutter_open:
                        time.sleep(0.5)
                except:
                    print ("Exposure focuser wait failed. ")

                self.focuser_is_moving=True


                self.minimum_allowed_focus=self.config['minimum']
                self.maximum_allowed_focus=self.config['maximum']

                #breakpoint()

                requestedPosition=int(self.guarded_move_to_focus)
                if requestedPosition < self.minimum_allowed_focus* self.micron_to_steps or requestedPosition > self.maximum_allowed_focus * self.micron_to_steps :
                    plog ("Requested focuser position outside limits set in config!")
                    plog (requestedPosition)
                else:


                    try:
                        if not self.dummy:

                            if self.theskyx:

                                #requestedPosition=int(self.guarded_move_to_focus * self.micron_to_steps)
                                requestedPosition=int(self.guarded_move_to_focus)
                                try:
                                    difference_in_position=self.focuser_update_wincom.focPosition() - requestedPosition
                                    absdifference_in_position=abs(self.focuser_update_wincom.focPosition() - requestedPosition)
                                except:
                                    difference_in_position=self.focuser_update_wincom.focPosition - requestedPosition
                                    absdifference_in_position=abs(self.focuser_update_wincom.focPosition - requestedPosition)

                                #breakpoint()
                                print (difference_in_position)
                                print (absdifference_in_position)
                                if difference_in_position < 0 :
                                    self.focuser_update_wincom.focMoveOut(absdifference_in_position)
                                else:
                                    self.focuser_update_wincom.focMoveIn(absdifference_in_position)
                                # try:
                                #     print (self.focuser_update_wincom.focPosition())
                                # except:
                                #     #print ("failed")
                                #     print (self.focuser_update_wincom.focPosition)

                                time.sleep(self.config['focuser_movement_settle_time'])
                                try:
                                    self.current_focus_position=int(self.focuser_update_wincom.focPosition())# * self.steps_to_micron)
                                except:
                                    self.current_focus_position=int(self.focuser_update_wincom.focPosition)# * self.steps_to_micron)

                            else:
                                if not self.relative_focuser:
                                    self.focuser_update_wincom.Move(int(self.guarded_move_to_focus))
                                    time.sleep(0.1)
                                    movement_report=0

                                    while self.focuser_update_wincom.IsMoving:
                                        if movement_report==0:
                                            plog("Focuser is moving.....")
                                            movement_report=1
                                        self.current_focus_position=int(self.focuser_update_wincom.Position) * self.steps_to_micron

                                        time.sleep(0.3)

                                    time.sleep(self.config['focuser_movement_settle_time'])

                                    self.current_focus_position=int(self.focuser_update_wincom.Position) * self.steps_to_micron
                                else:
                                    plog ("at a focus move point here")

                        else:
                            # Currently just a fummy focuser report
                            self.current_focus_position=2000

                    except:
                        plog("AF Guarded move failed.")
                        plog (traceback.format_exc())

                time.sleep(self.focuser_settle_time)

                try:
                    plog("Focus Movement Complete")
                except:
                    pass

                self.focuser_is_moving=False
                self.guarded_move_requested=False


            elif self.focuser_update_timer < time.time() - self.focuser_update_period:


                if not self.dummy:
                    try:
                        if self.theskyx:
                            self.current_focus_temperature=self.focuser_update_wincom.focTemperature
                        else:
                            try:
                                self.current_focus_temperature=self.focuser_update_wincom.Temperature
                            except:
                                self.current_focus_temperature = None
                                plog("Focus temp set to None as couldn't read temperature. Thats ok.")
                    except:
                        plog ("glitch in getting focus temperature")
                        plog (traceback.format_exc())
                    if not self.relative_focuser:
                        if not self.theskyx:
                            self.current_focus_position=int(self.focuser_update_wincom.Position * self.steps_to_micron)

                        else:
                            try:
                                self.current_focus_position=int(self.focuser_update_wincom.focPosition() * self.steps_to_micron)
                            except:
                                self.current_focus_position=int(self.focuser_update_wincom.focPosition * self.steps_to_micron)

                else:
                    # NOTHING DOING FOR DUMMY FOCUSSING AT THIS STAGE
                    pass

                self.focuser_update_timer = time.time()
            else:
                time.sleep(1)

            self.focuser_updates=self.focuser_updates+1


    def calculate_compensation(self, temp_primary):

        if (-20 <= temp_primary <= 45) and (self.focus_temp_slope != None):
            trial = round(
                float(
                    (self.focus_temp_slope * temp_primary) + self.focus_temp_intercept
                ),
                1,
            )

            return int(trial)
        elif self.best_previous_focus_point != None:
            return int(self.best_previous_focus_point)
        else:
            return int(self.config["reference"])

    def get_status(self):

        try:
            reported_focus_temp_slope = round(self.focus_temp_slope, 2)
        except:
            reported_focus_temp_slope = None

        try:

            if self.theskyx:
                status = {
                "focus_position": round(
                    self.current_focus_position, 1
                ),
                "focus_temperature": self.current_focus_temperature,
                "comp": reported_focus_temp_slope,
                "filter_offset": 0,
            }

            elif g_dev['fil'].null_filterwheel == False:
                status = {
                    "focus_position": round(
                        self.current_focus_position, 1
                    ),
                    "focus_temperature": self.current_focus_temperature,
                    #"focus_moving": self.focuser.IsMoving,
                    "comp": reported_focus_temp_slope,
                    #"filter_offset": g_dev["fil"].filter_offset,
                    "filter_offset": 0,
                }
            else:
                status = {
                    "focus_position": round(
                        self.current_focus_position, 1
                    ),
                    "focus_temperature": self.current_focus_temperature,
                    #"focus_moving": self.focuser.IsMoving,
                    "comp": reported_focus_temp_slope,
                    "filter_offset": 0.0,
                }
        except Exception as e:
            plog ("focuser status breakdown: ", e)
            plog ("usually the focusser program has crashed. This breakpoint is to help catch and code in a fix - MTF")
            plog ("possibly just institute a full reboot")
            plog (traceback.format_exc())

        return status

    def get_quick_status(self, quick):

        quick.append(time.time())
        quick.append(self.current_focus_position)
        try:
            quick.append(self.current_focus_temperature)
        except:
            quick.append(10.0)
        quick.append(False)
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
            "site": self.obsid,
            "ulid": cmd_id,
            "secondsUntilComplete": seconds_remaining,
            "newStatus": status,
        }
        response = requests.request("POST", url, data=json.dumps(body), timeout=5)
        if response:
            plog(response.status_code)
        return response

    def parse_command(self, command):
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]

        if action == "move_relative":
            # Do the command. Additional job updates can be sent in this function too.
            self.move_relative_command(req, opt)

        elif action == "move_absolute":
            self.move_absolute_command(req, opt)
        elif action == "go_to_reference":
            reference = self.get_focal_ref()

            self.guarded_move(int(float(reference)* self.micron_to_steps))

        elif action == "save_as_reference":

            self.set_focal_ref(
                self.current_focus_position
            )
        else:
            plog(f"Command <{action}> not recognized:", command)

    ###############################
    #       Focuser Commands      #
    ###############################

    def get_position_status(self, counts=False):
        return int(self.current_focus_position)

    def get_position_actual(self, counts=False):
        self.wait_for_focuser_update()
        return int(self.current_focus_position)

    def set_initial_best_guess_for_focus(self):

        self.focus_commissioned=False

        try:
            # try:
            self.best_previous_focus_point, last_successful_focus_time, self.focus_temp_slope, self.focus_temp_intercept, number_of_previous_focusses=self.get_af_log()
            # except:
            #     plog (traceback.format_exc())
            #     breakpoint()

            plog("Number of previous focusses: " + str(number_of_previous_focusses))

            #breakpoint()

            if last_successful_focus_time != None:

                self.time_of_last_focus=parser.parse(last_successful_focus_time)

                # if throw empty or exposure empty or list shorter than x, commissioned is yet not true.
                if number_of_previous_focusses > 10:
                    self.focus_commissioned=True
                # print(number_of_previous_focusses)

                # breakpoint()

            else:
                self.focus_commissioned=False

            if self.best_previous_focus_point==None:
                self.focus_commissioned=False
                self.best_previous_focus_point=self.config["reference"]

            if self.focus_temp_slope==None:
                self.focus_commissioned=False

        except:
            self.set_focal_ref_reset_log(self.config["reference"])

        try:
            self.z_compression = self.config["z_compression"]
        except:
            self.z_compression = 0.0

        if self.config['start_at_config_reference']:
            self.reference = int(self.config["reference"])
            self.last_known_focus = self.reference
            plog(
                "Focus reference derived from supplied config file for 10C:  ",
                self.reference,
            )
        elif self.config['correct_focus_for_temperature']:

            self.reference = self.calculate_compensation(
                self.current_focus_temperature
            )


            plog(
                "Focus position set from temp compensated value:  ",
                self.reference,
                ".  Temp used:  ",
                self.current_focus_temperature,
            )

            self.last_known_focus = self.reference
            self.last_source = "Focuser__init__  Calculate Comp references Config"
        else:
            try:
                self.reference = float(self.best_previous_focus_point)
            except:
                self.reference = int(self.config["reference"])
            self.last_known_focus = self.reference
            plog("Focus reference updated from best recent focus from Night Shelf:  ", self.reference)

        self.guarded_move(int(float(self.reference) * self.micron_to_steps))
        #breakpoint()

    def adjust_focus(self, force_change=False):
        """Adjusts the focus relative to the last formal focus procedure.

        This uses te most recent focus procedure that used self.current_focus_temperature
        to focus. Functionally dependent of temp, coef_c, and filter thickness."""


        # No point adjusting focus during flats. Flats don't need to be particularly in focus.
        if g_dev['seq'].flats_being_collected:
            return

        if not force_change  : # If the filter is changed, then a force change is necessary.
            try:
                if g_dev['seq'].focussing or self.focuser_is_moving or g_dev['seq'].measuring_focus_offsets:
                    return
                if g_dev['mnt'].rapid_park_indicator:
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    plog ("Not adjusting focus as observatory is not open and enabled to observe.")
                    return
            except:
                # On initialisation there is no g_dev
                # so this just skips early checks.
                pass
        else:
            # if we have to force a change but the focuser is currently moving
            # realistically we need to wait for it to stop.
            if self.focuser_is_moving:
                reporty=0
                while self.focuser_is_moving:
                    if reporty==0:
                        plog ("Waiting for focuser to finish moving before adjusting focus")
                        reporty=1
                    time.sleep(0.05)

        if self.theskyx:
            temp_delta = self.current_focus_temperature - self.previous_focus_temperature
        else:
            try:
                temp_delta = self.current_focus_temperature - self.previous_focus_temperature
            except:
                temp_delta = 0
                plog (traceback.format_exc())
                plog ("something fishy in the focus temperature")


        if not self.relative_focuser :
            try:

                adjust = 0.0


                # adjust for temperature if we have the correct information.
                if abs(temp_delta) > 0.1 and self.current_focus_temperature is not None and self.focus_temp_slope is not None and self.focus_temp_intercept is not None:
                    adjust = round(temp_delta * float(self.focus_temp_slope), 1)

                # adjust for filter offset
                # it is try/excepted because some telescopes don't have filters
                try:
                    adjust -= (g_dev["fil"].filter_offset)
                except:
                    pass

                if force_change:
                    self.get_position_actual()

                current_focus_micron=self.current_focus_position#*self.steps_to_micron

                if abs((self.last_known_focus + adjust) - current_focus_micron) > 50:

                    self.focuser_is_moving=True
                    plog ("Adjusting focus to: " + str(self.last_known_focus + adjust))

                    self.guarded_move((self.last_known_focus + adjust)*self.micron_to_steps)

            except:
                plog("Focus-adjust: no changes made.")
                plog (traceback.format_exc())


    def wait_for_focuser_update(self):
        sleep_period= self.focuser_update_period / 4
        current_updates=copy.deepcopy(self.focuser_updates)
        while current_updates==self.focuser_updates:
            time.sleep(sleep_period)

    def guarded_move(self, to_focus):



        focuser_was_moving=False
        reported=False
        while self.focuser_is_moving:
            focuser_was_moving=True
            if not reported:
                plog ("guarded_move focuser moving")
                reported=True
            time.sleep(0.2)

        if focuser_was_moving:
            self.wait_for_focuser_update()

        if (self.current_focus_position*self.micron_to_steps) > to_focus-35 and \
            (self.current_focus_position*self.micron_to_steps) < to_focus+35:
            plog ("Not moving focus, focus already close to requested position")
        else:

            self.guarded_move_requested=True
            self.focuser_is_moving=True
            self.guarded_move_to_focus=to_focus
            self.wait_for_focuser_update()

    def move_relative_command(self, req: dict, opt: dict):
        """Sets the focus position by moving relative to current position."""
        # The string must start with a + or a - sign, otherwise treated as zero and no action.

        self.focuser_is_moving=True
        position_string = req["position"]

        difference_in_position=int(position_string) * self.micron_to_steps

        self.guarded_move(self.current_focus_position + difference_in_position)


        self.last_known_focus = req["position"]


    def move_absolute_command(self, req: dict, opt: dict):
        """Sets the focus position by moving to an absolute position."""
        #
        self.focuser_is_moving=True
        position = int(float(req["position"])) * self.micron_to_steps
        self.guarded_move(position )
        self.last_known_focus = req["position"]
        #plog("Forces last known focus to be new position Line 551 in focuser WER 20400917")

    def stop_command(self, req: dict, opt: dict):
        """stop focuser movement"""
        plog("focuser cmd: stop")

    def home_command(self, req: dict, opt: dict):
        """set the focuser to the home position"""
        plog("focuser cmd: home")

    def auto_command(self, req: dict, opt: dict):
        """autofocus"""
        plog("focuser cmd: auto")

    def set_focal_ref(self, ref):
        # cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))
        # cam_shelf["focus_ref"] = ref
        # cam_shelf.close()
        shelf_path = os.path.join(
            self.obsid_path,
            "ptr_night_shelf",
            f"focuslog_{self.camera_name}{g_dev['obs'].name}"
        )

        with shelve.open(shelf_path) as cam_shelf:
            cam_shelf["focus_ref"] = ref
        return

    def set_focal_ref_reset_log(self, ref):
        try:
            cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))
        except:
            plog ("Focus log file corrupt, creating new ones")
            import os
            os.remove(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + g_dev['obs'].name +".dat")
            os.remove(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + g_dev['obs'].name +".bak")
            os.remove(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + g_dev['obs'].name +".dir")
            cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))

        cam_shelf["focus_ref"] = ref
        cam_shelf["af_log"] = []
        cam_shelf.close()
        return

    def af_log(self, ref, fwhm, solved):
        """Logs autofocus data to the night shelf."""


        try:
            f_temp=self.current_focus_temperature
        except:

            f_temp = None

        # Note once focus comp is in place this data
        # needs to be combined with great care.
        # cam_shelf = shelve.open(
        #     self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name), writeback=True
        # )

        # if not f_temp == None and (-30 < f_temp < 40):
        #     if "af_log" in cam_shelf:
        #         cam_shelf["af_log"].append(
        #             (f_temp, ref, round(fwhm, 2), round(solved, 2), datetime.datetime.utcnow().isoformat())
        #         )
        #     else : # create af log if it doesn't exist
        #         cam_shelf["af_log"]=[(f_temp, ref, round(fwhm, 2), round(solved, 2), datetime.datetime.utcnow().isoformat())]
        # else:
        #     f_temp=15.0
        #     plog ("getting f_temp failed, using 15 degrees C")
        #     plog (traceback.format_exc())

        # cam_shelf.close()


        shelf_path = os.path.join(
            self.obsid_path,
            "ptr_night_shelf",
            f"focuslog_{self.camera_name}{g_dev['obs'].name}"
        )

        with shelve.open(shelf_path, writeback=True) as cam_shelf:
            # Check temperature validity
            if f_temp is not None and -30 < f_temp < 40:
                entry = (
                    f_temp,
                    ref,
                    round(fwhm, 2),
                    round(solved, 2),
                    datetime.datetime.utcnow().isoformat()
                )
                # Append or create
                if "af_log" in cam_shelf:
                    cam_shelf["af_log"].append(entry)
                else:
                    cam_shelf["af_log"] = [entry]
                # immediately flush the updated cache to disk
                cam_shelf.sync()
            else:
                f_temp = 15.0
                plog("getting f_temp failed, using 15 °C")
                plog(traceback.format_exc())

        return

    def get_af_log(self):
        """Retrieves the autofocus log."""

        try:

            max_arcsecond=self.config['maximum_good_focus_in_arcsecond']
            previous_focus=[]

            with shelve.open(
                self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name), writeback=True
            ) as cam_shelf:
                temp_focus_log=cam_shelf["af_log"]

            # Load last focuses and order from most recent to oldest
            for item in temp_focus_log:
                previous_focus.append(item)

            # Print focus log and sort in order of date
            for item in previous_focus:
                plog(str(item))

            previous_focus.reverse()

            # Cacluate the temperature coefficient and zero point
            tempvalues=[]
            for item in previous_focus:
                if item[2] < max_arcsecond and item[2] != 0 and item[1] !=False and -10 < item[0] < 40 :
                    tempvalues.append([item[0],item[1]])
            if len(tempvalues) > 10:
                tempvalues=np.array(tempvalues)
                # Calculate least squares fit
                x = tempvalues[:,0]
                A = np.vstack([x, np.ones(len(x))]).T
                focus_temp_slope, focus_temp_intercept = np.linalg.lstsq(A, tempvalues[:,1], rcond=None)[0]
            else:
                focus_temp_slope = None
                focus_temp_intercept = None

            # Figure out best last focus position
            for item in previous_focus:
                if item[2] < max_arcsecond and item[2] != 0 and item[1] !=False and -10 < item[0] < 40 :
                    plog ("Best previous focus is at: " +str(item))
                    return item[1], item[4], focus_temp_slope, focus_temp_intercept, len(previous_focus)

            try:
                print (len(previous_focus))
            except:
                plog (traceback.format_exc())

            return None, None, focus_temp_slope, focus_temp_intercept, len(previous_focus)

        except:
            plog("There is no focus log on the night shelf.")

    def get_focal_ref(self):
        # cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))
        # focus_ref = cam_shelf["focus_ref"]
        # # NB Should we also return and use the ref temp?
        # cam_shelf.close()
        # return focus_ref

        shelf_path = os.path.join(
            self.obsid_path,
            "ptr_night_shelf",
            f"focuslog_{self.camera_name}{g_dev['obs'].name}"
        )

        with shelve.open(shelf_path, writeback=False) as cam_shelf:
            focus_ref = cam_shelf["focus_ref"]

        return focus_ref


if __name__ == "__main__":
    pass