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
import queue
import copy
from global_yard import g_dev
from ptr_utility import plog
from dateutil import parser

# Unused except for WMD
def probeRead(com_port):
    with serial.Serial(com_port, timeout=0.3) as com:
        com.write(b"R1\n")
        probePosition = (
            float(com.read(7).decode()) * 994.96 - 137
        )  # Corrects Probe to Stage. Up and down, lash = 5000 enc.
        plog(round(probePosition, 1))


class Focuser:
    def __init__(self, driver: str, name: str, config: dict):
        self.obsid = config["obs_id"]
        self.name = name
        self.obsid_path = g_dev['obs'].obsid_path
        self.camera_name = config["camera"]["camera_1_1"]["name"]

        g_dev["foc"] = self
        self.config = config["focuser"]["focuser1"]
        self.throw = int(config["focuser"]["focuser1"]["throw"])

        win32com.client.pythoncom.CoInitialize()

        self.focuser = win32com.client.Dispatch(driver)
        #self.focuser_id = win32com.client.pythoncom.CoMarshalInterThreadInterfaceInStream(win32com.client.pythoncom.IID_IDispatch, self.focuser)

        self.driver = driver

        if driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
            self.theskyx=True
        else:
            self.theskyx=False

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
            config["focuser"]["focuser1"]["unit_conversion"]
        )  #  Note this can be a bogus value
        self.steps_to_micron = 1 / self.micron_to_steps


        # Just to need to wait a little bit for PWI3 to boot up, otherwise it sends temperatures that are absolute zero (-273)
        if driver == 'ASCOM.PWI3.Focuser':
            time.sleep(4)

        if not self.theskyx:
            self.current_focus_position=self.focuser.Position * self.steps_to_micron
        else:
            self.current_focus_position=self.focuser.focPosition() * self.steps_to_micron



        self.focuser_update_period=15   #WER changed from 3 20231214
        self.focuser_updates=0
        self.focuser_settle_time= 0 #initialise
        self.guarded_move_requested=False
        self.guarded_move_to_focus=20000

        self.focuser_update_timer=time.time() - 2* self.focuser_update_period
        #self.focuser_update_thread_queue = queue.Queue(maxsize=0)
        self.focuser_update_thread=threading.Thread(target=self.focuser_update_thread)
        self.focuser_update_thread.start()



        self.focuser_message = "-"

        if self.theskyx:
            plog(
                "Focuser connected, at:  ",
                round(self.focuser.focPosition() * self.steps_to_micron, 1),
            )
        else:
            plog(
                "Focuser connected, at:  ",
                round(self.focuser.Position * self.steps_to_micron, 1),
            )
        self.reference = None
        self.last_known_focus = None
        #self.last_temperature = None
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
        
        self.focuser_is_moving=False


        #self.update_focuser_temperature()

        #breakpoint()

        if self.theskyx:
            self.current_focus_temperature=self.focuser.focTemperature
        else:
            self.current_focus_temperature=self.focuser.Temperature

        self.previous_focus_temperature = copy.deepcopy(self.current_focus_temperature)

        self.set_initial_best_guess_for_focus()
        try:
            self.last_filter_offset = g_dev["fil"].filter_offset
        except:
            plog ('setting last filter offset to 0')
            self.last_filter_offset= 0

        self.focuser_settle_time=self.config['focuser_movement_settle_time']








    # Note this is a thread!
    def focuser_update_thread(self):


        #one_at_a_time = 0

        #Hooking up connection to win32 com focuser
        #win32com.client.pythoncom.CoInitialize()
    #     fl = win32com.client.Dispatch(
    #         win32com.client.pythoncom.CoGetInterfaceAndReleaseStream(g_dev['foc'].focuser_id, win32com.client.pythoncom.IID_IDispatch)
    # )

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
                        #print ("Focuser waiting for Exposure to finish.")
                        time.sleep(0.5)
                except:
                    print ("Exposure focuser wait failed. ")

                self.focuser_is_moving=True

                try:
                     if self.theskyx:
                        requestedPosition=int(self.guarded_move_to_focus * self.micron_to_steps)
                        difference_in_position=self.focuser_update_wincom.focPosition() - requestedPosition
                        absdifference_in_position=abs(self.focuser_update_wincom.focPosition() - requestedPosition)
                        print (difference_in_position)
                        print (absdifference_in_position)
                        if difference_in_position < 0 :
                            self.focuser_update_wincom.focMoveOut(absdifference_in_position)
                        else:
                            self.focuser_update_wincom.focMoveIn(absdifference_in_position)
                        print (self.focuser_update_wincom.focPosition())

                        #self.last_known_focus=
                        time.sleep(self.config['focuser_movement_settle_time'])
                        self.current_focus_position=int(self.focuser_update_wincom.focPosition() * self.steps_to_micron)

                        #self.current_focus_position=self.get_position()

                     else:
                        #print ("prefoc: " + str(self.current_focus_position) * self.micron_to_steps))
                        #breakpoint()
                        self.focuser_update_wincom.Move(int(self.guarded_move_to_focus))# * self.steps_to_micron)
                        time.sleep(0.1)
                        movement_report=0

                        while self.focuser_update_wincom.IsMoving:
                            if movement_report==0:
                                plog("Focuser is moving.....")
                                movement_report=1
                            self.current_focus_position=int(self.focuser_update_wincom.Position) * self.steps_to_micron
                            #g_dev['obs'].request_update_status()#, dont_wait=True)

                            time.sleep(0.3)

                        time.sleep(self.config['focuser_movement_settle_time'])

                        self.current_focus_position=int(self.focuser_update_wincom.Position) * self.steps_to_micron
                        #self.current_focus_position=self.get_position()
                        #print ("postfoc "+ str(self.current_focus_position))# * self.micron_to_steps))

                            #plog(">f")
                except:
                    plog("AF Guarded move failed.")
                    plog (traceback.format_exc())

                time.sleep(self.focuser_settle_time)

                try:
                    g_dev["obs"].send_to_user("Focus Movement Complete")

                    plog("Focus Movement Complete")
                except:
                    # first time booting up this won't work.
                    pass



                self.focuser_is_moving=False
                self.guarded_move_requested=False


            elif self.focuser_update_timer < time.time() - self.focuser_update_period:

                try:
                    if self.theskyx:
                        self.current_focus_temperature=self.focuser_update_wincom.focTemperature
                    else:
                        #MRC2temp probe has failed. Will sort tomorrow WER 20231213 Early Eve

                        try:
                            self.current_focus_temperature=self.focuser_update_wincom.Temperature
                        except:
                            self.current_focus_temperature = None  # NB 20231216 WER Temporary patch for MRC2
                            plog("Focus temp set to None as couldn't read temperature. Thats ok.")
                except:
                    plog ("glitch in getting focus temperature")
                    plog (traceback.format_exc())
                    # plog ("glitch in getting focus temperature")
                    # plog (traceback.format_exc())

                if not self.theskyx:
                    self.current_focus_position=int(self.focuser_update_wincom.Position * self.steps_to_micron)


                else:
                    self.current_focus_position=int(self.focuser_update_wincom.focPosition() * self.steps_to_micron)

                #print ("thread focus: " + str(self.current_focus_position))
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

    # def update_focuser_temperature(self):
    #     if self.theskyx:
    #         self.current_focus_temperature=self.focuser.focTemperature
    #     else:
    #         self.current_focus_temperature=self.focuser.Temperature

    def get_status(self):

        try:
            reported_focus_temp_slope = round(self.focus_temp_slope, 2)
        except:
            reported_focus_temp_slope = None

        try:

            if self.theskyx:
                #try:
                status = {
                "focus_position": round(
                    self.current_focus_position, 1
                ),
                "focus_temperature": self.current_focus_temperature,
                "comp": reported_focus_temp_slope,
                "filter_offset": g_dev["fil"].filter_offset,
            }
                # except Exception as e:
                #     try:
                #         if 'COleException: The RPC server is unavailable.' in str(e):
                #             plog ("TheSkyX focuser glitch.... recovering......")
                #             time.sleep(10)
                #             self.focuser = win32com.client.Dispatch('CCDSoft2XAdaptor.ccdsoft5Camera')
                #             time.sleep(10)
                #             self.focuser.focConnect()
                #             time.sleep(10)
                #             status = {
                #             "focus_position": round(
                #                 self.focuser.focPosition() * self.steps_to_micron, 1
                #             ),  # THIS occasionally glitches, usually no temp probe on Gemini
                #             "focus_temperature": self.current_focus_temperature,
                #             "comp": reported_focus_temp_slope,
                #             "filter_offset": g_dev["fil"].filter_offset,
                #         }
                #     except Exception as e:
                #         plog ("focuser status breakdown: ", e)
                #         plog ("usually the focusser program has crashed. This breakpoint is to help catch and code in a fix - MTF")
                #         plog ("possibly just institute a full reboot")
                #         plog (traceback.format_exc())
                #         # breakpoint()


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
            # breakpoint()
        return status

    def get_quick_status(self, quick):

        #if self.theskyx:
        quick.append(time.time())
        #self.current_focus_position=self.focuser.focPosition() * self.steps_to_micron
        quick.append(self.current_focus_position)
        try:
            quick.append(self.current_focus_temperature)
        except:
            quick.append(10.0)
        quick.append(False)
        # else:


        #     quick.append(time.time())
        #     self.current_focus_position=self.focuser.Position * self.steps_to_micron
        #     quick.append(self.current_focus_position)
        #     try:
        #         quick.append(self.focuser.Temperature)
        #     except:
        #         quick.append(10.0)
        #     quick.append(self.focuser.IsMoving)
        return quick

    def get_average_status(self, pre, post):
        #print ("MTF tempcheck - report to focuser average status")
        #print (str(pre))
        #print (str(post))
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
            # Mark a job as "STARTED" just before starting it.
            # Include a time estmiate if possible. This is sent to the UI.
            #self.update_job_status(command["ulid"], "STARTED", 5)

            # Do the command. Additional job updates can be sent in this function too.
            self.move_relative_command(req, opt)

            # Mark the job "COMPLETE" when finished.
            #self.update_job_status(command["ulid"], "COMPLETE")

        elif action == "move_absolute":
            #self.update_job_status(command["ulid"], "STARTED", 5)
            self.move_absolute_command(req, opt)
            #self.update_job_status(command["ulid"], "COMPLETE")
        elif action == "go_to_reference":
            #self.update_job_status(command["ulid"], "STARTED", 5)
            reference = self.get_focal_ref()

            self.guarded_move(int(float(reference)* self.micron_to_steps))

            # self.focuser.Move(reference * self.micron_to_steps)
            # time.sleep(0.1)
            # while self.focuser.IsMoving:
            #     time.sleep(0.5)
            #     plog(">")
            # self.update_job_status(command["ulid"], "COMPLETE")
        # elif action == "go_to_compensated":
        #     reference = self.calculate_compensation(self.focuser.Temperature)
        #     self.focuser.Move(reference * self.micron_to_steps)
        #     time.sleep(0.1)
        #     while self.focuser.IsMoving:
        #         time.sleep(0.5)
        #         plog(">")
        elif action == "save_as_reference":

            #self.current_focus_position
            self.set_focal_ref(
                self.current_focus_position# * self.steps_to_micron
            )
        else:
            plog(f"Command <{action}> not recognized:", command)

    ###############################
    #       Focuser Commands      #
    ###############################

    def get_position_status(self, counts=False):
        # if not counts:
        #     if not self.theskyx:
        #         #self.current_focus_position=self.focuser.Position * self.steps_to_micron

        return int(self.current_focus_position)
            # else:
            #     #self.current_focus_position=self.focuser.focPosition() * self.steps_to_micron

            #     return int(self.current_focus_position)

    def get_position_actual(self, counts=False):
        self.wait_for_focuser_update()
        return int(self.current_focus_position)



    def set_initial_best_guess_for_focus(self):

        try:
            self.best_previous_focus_point, last_successful_focus_time, self.focus_temp_slope, self.focus_temp_intercept=self.get_af_log()

            if last_successful_focus_time != None:
                self.time_of_last_focus=parser.parse(last_successful_focus_time)

            if self.best_previous_focus_point==None:
                self.best_previous_focus_point=self.config["reference"]

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
            # Get temperature
            #try:
                # if self.theskyx:
                #     self.last_temperature = self.focuser.focTemperature

                # else:
                #     self.last_temperature = self.focuser.Temperature
                # self.reference = self.calculate_compensation(
                #     self.last_temperature
                # )  # need to change to config supplied
            #except:
            # try:
            #     self.last_temperature = g_dev["ocn"].temperature
            #     self.reference = self.calculate_compensation(
            #         g_dev["ocn"].temperature
            #     )
            # except:
            #plog ("could not get temperature from ocn in focuser.py")
            #self.last_temperature=self.current_focus_temperature
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

        # #breakpoint()
        # if self.theskyx:
        #     # requestedPosition=int(float(self.reference) * self.micron_to_steps)
        #     # difference_in_position=self.focuser.focPosition() - requestedPosition
        #     # absdifference_in_position=abs(self.focuser.focPosition() - requestedPosition)
        #     # print (difference_in_position)
        #     # print (absdifference_in_position)
        #     # if difference_in_position < 0 :
        #     #     self.focuser.focMoveOut(absdifference_in_position)
        #     # else:
        #     #     self.focuser.focMoveIn(absdifference_in_position)
        #     # print (self.focuser.focPosition())
        #     # self.current_focus_position=self.get_position()#self.focuser.focPosition()# * self.micron_to_steps
        #     self.guarded_move(int(float(self.reference) * self.micron_to_steps))
        # else:
        #     self.guarded_move(int(float(self.reference) * self.micron_to_steps))
        #     #self.focuser.Move(int(float(self.reference) * self.micron_to_steps))
        #     #self.current_focus_position=self.focuser.Position * self.micron_to_steps
        #     self.current_focus_position=self.get_position()
        #     #breakpoint()

    def adjust_focus(self, force_change=False):
        """Adjusts the focus relative to the last formal focus procedure.

        This uses te most recent focus procedure that used self.current_focus_temperature
        to focus. Functionally dependent of temp, coef_c, and filter thickness."""

        # Hack to stop focus during commissioning
        #return
        
        if g_dev['seq'].flats_being_collected:
            plog ("adjusting focus disabled during focussing")
            return

        if not force_change  : # If the filter is changed, then a force change is necessary.
            try:
                if g_dev['seq'].focussing or self.focuser_is_moving or g_dev['seq'].measuring_focus_offsets:
                    return
                if g_dev['mnt'].rapid_park_indicator:
                    #plog ("Not adjusting focus as telescope is parked")
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
                while g_dev['foc'].focuser_is_moving:
                    if reporty==0:
                        plog ("Waiting for focuser to finish moving before adjusting focus")
                        reporty=1
                    time.sleep(0.05)


        # try:
        if self.theskyx:
            temp_delta = self.current_focus_temperature - self.previous_focus_temperature
        else:
            temp_delta = self.current_focus_temperature - self.previous_focus_temperature
        #print (self.current_focus_temperature)
        #print (self.previous_focus_temperature)
        #print ("Current temp_delta between solved focus and current time: " + str(temp_delta))
        # except:
        #     print ("")
        #     temp_delta = 0.0


        try:
            adjust = 0.0

            #print ("current focus position " + str(self.current_focus_position))
            # adjust for temperature if we have the correct information.
            if abs(temp_delta) > 0.1 and self.current_focus_temperature is not None and self.focus_temp_slope is not None and self.focus_temp_intercept is not None:

                adjust = round(temp_delta * float(self.focus_temp_slope), 1)
                #print ("focus adjust value due to temperature: " + str(adjust))

            # adjust for filter offset
            # it is try/excepted because some telescopes don't have filters
            try:
                adjust -= (g_dev["fil"].filter_offset)
                #print ("focus adjust value due to filter_offset: " + str(g_dev["fil"].filter_offset))
                #print ("New focus position would be: " + str(self.last_known_focus + adjust))
            except:
                pass


            #if self.theskyx:
                # self.current_focus_position=self.get_position()

            self.get_position_actual()

            # else:
            #     self.current_focus_position=self.get_position()

            current_focus_micron=self.current_focus_position#*self.steps_to_micron

            #breakpoint()
            if abs((self.last_known_focus + adjust) - current_focus_micron) > 50:
                #plog ('adjusting focus by ' + str(adjust))
                #self.last_filter_offset = g_dev["fil"].filter_offset
                #plog ("Current focus: " +str(current_focus_micron))
                #plog ("Focus different by: " + str((self.last_known_focus + adjust) - current_focus_micron) +'. Sending adjust command.')
                #plog ("Filter offset: " + str(g_dev["fil"].filter_offset))
                #plog ("Temperature difference: " + str(temp_delta))
                # if self.current_focus_temperature is not None:
                #     try:
                #         plog ("Temperature focus difference: " + str(round(temp_delta * float(self.focus_temp_slope), 1)))
                #     except:
                #         pass
                #req = {"position": self.last_known_focus + adjust}
                #opt = {}
                self.focuser_is_moving=True
                plog ("Adjusting focus to: " + str(self.last_known_focus + adjust))
                #self.move_absolute_command(req, opt)
                #breakpoint()
                self.guarded_move((self.last_known_focus + adjust)*self.micron_to_steps)

                #plog ("Position now: " + str(self.current_focus_position))
                # try:
                #     if self.theskyx:
                #         self.last_temperature = self.focuser.focTemperature
                #     else:
                #         self.last_temperature = self.focuser.Temperature
                # except:
                #     self.last_temperature = None

        except:
            plog("Focus-adjust: no changes made.")
            plog (traceback.format_exc())


    def wait_for_focuser_update(self):
        sleep_period= self.focuser_update_period / 4
        current_updates=copy.deepcopy(self.focuser_updates)
        while current_updates==self.focuser_updates:
            #print ('ping')
            time.sleep(sleep_period)

    def guarded_move(self, to_focus):

        
        while self.focuser_is_moving:
            plog ("guarded_move focuser wait")
            time.sleep(0.2)

        # Check that the guarded_move is even necessary
        # If it is roughly in the right space, the guarded_move
        # Just adds overhead for no benefit
        
        print ("MTF")
        print (self.current_focus_position)
        print (to_focus)
               
        
        if self.current_focus_position > to_focus-35 and self.current_focus_position < to_focus+35:
            plog ("Not moving focus, focus already close to requested position")
        else:

            self.guarded_move_requested=True
            self.focuser_is_moving=True
            self.guarded_move_to_focus=to_focus
            self.wait_for_focuser_update()


        # try:
        #      if self.theskyx:
        #         requestedPosition=int(to_focus * self.micron_to_steps)
        #         difference_in_position=self.focuser.focPosition() - requestedPosition
        #         absdifference_in_position=abs(self.focuser.focPosition() - requestedPosition)
        #         print (difference_in_position)
        #         print (absdifference_in_position)
        #         if difference_in_position < 0 :
        #             self.focuser.focMoveOut(absdifference_in_position)
        #         else:
        #             self.focuser.focMoveIn(absdifference_in_position)
        #         print (self.focuser.focPosition())
        #         self.current_focus_position=self.get_position()

        #      else:

        #         self.focuser.Move(int(to_focus))
        #         time.sleep(0.1)
        #         movement_report=0

        #         while self.focuser.IsMoving:
        #             if movement_report==0:
        #                 plog("Focuser is moving.....")
        #                 movement_report=1
        #             time.sleep(0.3)
        #         self.current_focus_position=self.get_position()


        #             #plog(">f")
        # except:
        #     plog("AF Guarded move failed.")
        #     plog (traceback.format_exc())



    # def is_moving(self):
    #     if self.theskyx:
    #         return False
    #     else:
    #         return self.focuser.IsMoving


    def move_relative_command(self, req: dict, opt: dict):
        """Sets the focus position by moving relative to current position."""
        # The string must start with a + or a - sign, otherwise treated as zero and no action.

        self.focuser_is_moving=True
        position_string = req["position"]

        difference_in_position=int(position_string) * self.micron_to_steps

        self.guarded_move(self.current_focus_position + difference_in_position)


    #     if self.theskyx:
    #         position = self.focuser.focPosition() * self.steps_to_micron
    #     else:
    #         position = self.focuser.Position * self.steps_to_micron


    #     if self.theskyx:
    #         difference_in_position=int(position_string)
    #         absdifference_in_position=abs(int(position_string))
    #         if difference_in_position < 0 :
    #             self.focuser.focMoveOut(absdifference_in_position)
    #         else:
    #             self.focuser.focMoveIn(absdifference_in_position)
    #         print (self.focuser.focPosition())
    #         self.current_focus_position=self.get_position()

    #     else:

    #         movement_report=0
    #         if position_string[0] != "-":
    #             relative = int(position_string)
    #             position += relative
    #             self.focuser.Move(int(position * self.micron_to_steps))
    #             time.sleep(0.1)
    #             while self.focuser.IsMoving:
    #                 if movement_report==0:
    #                     plog("Focuser is moving ++ .....")
    #                     movement_report=1
    #                 time.sleep(0.2)
    #         elif position_string[0] == "-":
    #             relative = int(position_string[1:])
    #             position -= relative
    #             self.focuser.Move(int(position * self.micron_to_steps))
    #             time.sleep(0.1)
    #             while self.focuser.IsMoving:
    #                 if movement_report==0:
    #                     plog("Focuser is moving >f rel.....")
    #                     movement_report=1
    #                 time.sleep(0.2)
    #         else:
    #             plog("Supplied relative move is lacking a sign; ignoring.")
    #         self.current_focus_position=self.get_position()

    #     #self.last_known_focus=self.current_focus_position


    def move_absolute_command(self, req: dict, opt: dict):
        """Sets the focus position by moving to an absolute position."""

        self.focuser_is_moving=True
        position = int(float(req["position"])) * self.micron_to_steps
        self.guarded_move(position)

    # def move_absolute_command(self, req: dict, opt: dict):
    #     """Sets the focus position by moving to an absolute position."""

    #     self.focuser_is_moving=True
    #     position = int(float(req["position"]))



    #     if self.theskyx:
    #         current_position = self.focuser.focPosition() * self.steps_to_micron
    #     else:
    #         current_position = self.focuser.Position * self.steps_to_micron



    #     if self.theskyx:
    #         requestedPosition=int(float(position) * self.micron_to_steps)
    #         difference_in_position=self.focuser.focPosition() - requestedPosition
    #         absdifference_in_position=abs(self.focuser.focPosition() - requestedPosition)
    #         print (difference_in_position)
    #         print (absdifference_in_position)
    #         if difference_in_position < 0 :
    #             self.focuser.focMoveOut(absdifference_in_position)
    #         else:
    #             self.focuser.focMoveIn(absdifference_in_position)
    #         print (self.focuser.focPosition())
    #         self.current_focus_position=self.get_position()

    #     else:
    #         self.focuser.Move(int(position * self.micron_to_steps))
    #         time.sleep(0.3)
    #         while self.focuser.IsMoving:
    #             time.sleep(0.3)
    #         self.current_focus_position=self.get_position()

    #     #self.last_known_focus=self.current_focus_position


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
        cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))
        cam_shelf["focus_ref"] = ref
        cam_shelf.close()
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

        # Note once focus comp is in place this data
        # needs to be combined with great care.
        cam_shelf = shelve.open(
            self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name), writeback=True
        )
        try:
            f_temp=self.current_focus_temperature
            # if self.theskyx:
            #     f_temp= self.focuser.focTemperature
            # else:
            #     f_temp = (
            #         self.focuser.Temperature
            #     )  # NB refering a quantity possibly from WEMA if no focus temp available.
        except:

            f_temp = None

        if not f_temp == None and (-30 < f_temp < 40):
            if "af_log" in cam_shelf:
                cam_shelf["af_log"].append(
                    (f_temp, ref, round(fwhm, 2), round(solved, 2), datetime.datetime.utcnow().isoformat())
                )
            else : # create af log if it doesn't exist
                cam_shelf["af_log"]=[(f_temp, ref, round(fwhm, 2), round(solved, 2), datetime.datetime.utcnow().isoformat())]
        else:
            f_temp=15.0
            plog ("getting f_temp failed, using 15 degrees C")
            plog (traceback.format_exc())

        cam_shelf.close()
        return

    def get_af_log(self):
        """Retrieves the autofocus log."""

        try:
            cam_shelf = shelve.open(
                self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name), writeback=True
            )

            max_arcsecond=self.config['maximum_good_focus_in_arcsecond']

            # Load last focuses and order from most recent to oldest
            previous_focus=[]
            for item in cam_shelf["af_log"]:
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
                    return item[1], item[4], focus_temp_slope, focus_temp_intercept

            return None, None, focus_temp_slope, focus_temp_intercept

        except:
            plog("There is no focus log on the night shelf.")

    def get_focal_ref(self):
        cam_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/focuslog_" + self.camera_name + str(g_dev['obs'].name))
        focus_ref = cam_shelf["focus_ref"]
        # NB Should we also return and use the ref temp?
        cam_shelf.close()
        return focus_ref


if __name__ == "__main__":
    pass