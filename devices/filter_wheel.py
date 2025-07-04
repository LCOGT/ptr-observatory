"""
The FilterWheel class represents and controls a filter wheel instrument
at an observatory site, which houses a site's filter set.

Given a non-homogenous distribution of filters across the network, a site
must be able to handle requests for filters it may not have. Most sites
have at least a minimum set of generic filters. The FilterWheel will attempt
to determine a substitute filter first, and skip the request if no subs can
be found.
"""
import json
import time

import requests
import serial
import win32com.client
import numpy as np
import threading
import copy
import traceback
from global_yard import g_dev
from ptr_utility import plog
import support_info.FLIsdk.fli_dual_wheel
# We only use Observatory in type hints, so use a forward reference to prevent circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from obs import Observatory

class FilterWheel:
    """A filter wheel instrument."""

    def __init__(self, driver, name: str, site_config: dict, observatory: 'Observatory'):
        self.name = name
        g_dev["fil"] = self
        self.config = site_config["filter_wheel"][name]
        self.settings = self.config['settings']
        self.obs = observatory

        # Configure the role, if it exists
        # Current design allows for only one role per device
        # We can add more roles by changing self.role to a list and adjusting any references
        self.role = None
        for role, device in site_config['device_roles'].items():
            if device == name:
                self.role = role
                break

        # Set the dummy flag
        if driver == 'dummy':
            self.dummy=True
        else:
            self.dummy=False

        self.driver = driver
        # Load filter offset shelf if avaiable
        self.filter_offsets={}

        # Initialise variables for the current filter position
        # These reflect the current state of the system, so be careful that
        # the initial values aren't confused for real state
        self.current_filter_name = 'none'
        self.current_filter_number = -1

        if driver is not None:
            self.null_filterwheel = False
            self.dual_filter = self.config["dual_wheel"]
            self.ip = str(self.config["ip_string"])
            self.filter_data = self.settings["filter_data"]
            # self.filter_screen_sort = self.settings["filter_screen_sort"]
            self.wait_time_after_filter_change=self.config["filter_settle_time"]

            self.filter_message = "-"
            plog("Please NOTE: Filter wheel may block for many seconds while first connecting \
                 & homing.")

            self.filter_change_requested=False
            self.filter_changing=False
            self.filterwheel_update_period=0.2
            self.filterwheel_update_timer=time.time() - 2* self.filterwheel_update_period
            self.filterwheel_updates=0
            #self.focuser_update_thread_queue = queue.Queue(maxsize=0)
            self.filterwheel_update_thread=threading.Thread(target=self.filterwheel_update_thread)
            self.filterwheel_update_thread.daemon = True
            self.filterwheel_update_thread.start()



            if driver =='dummy':
                self.maxim = False
                self.theskyx = False
                self.ascom = False
                self.dual_lco = False
                self.dual_fli=False
                self.custom = False
                self.dummy=True
            elif driver == "ASCOM.EFW2.FilterWheel":
                #breakpoint()
                win32com.client.pythoncom.CoInitialize()
                self.filter = win32com.client.Dispatch(driver)
                self.ascom = True
                self.maxim = False
                self.theskyx = False
                self.dual_lco = False
                self.dual_fli=False
                self.custom = False
                self.dummy=False
                self.filter.Connected = True

            elif driver == "FLI.dual":

                #breakpoint()
                # Import dual wheel instruction set

                self.fli_wheelids=support_info.FLIsdk.fli_dual_wheel.initialize_wheels()
                print ("Initialised FLI wheels: " + str(self.fli_wheelids))


                print ("FLI_dual")
                self.ascom = False
                self.maxim = False
                self.theskyx = False
                self.dual_lco = False
                self.dual_fli=True
                self.custom = False
                self.dummy=False

            elif driver == "LCO.dual":  #This is the LCO designed dual Filter wheel on ARO1
                # home the wheel and get responses, which indicates it is connected.
                # set current_0 and _1 to [0, 0] position to default of w/L filter.
                r0 = requests.get(self.ip + "/filterwheel/0/position", timeout=5)
                r1 = requests.get(self.ip + "/filterwheel/1/position", timeout=5)
                if str(r0) == str(r1) == "<Response [200]>":
                    plog("LCO Dual Layer Filter Wheel connected.")

                r0 = json.loads(r0.text)
                r1 = json.loads(r1.text)
                self.r0 = r0
                self.r1 = r1
                r0["filterwheel"]["position"] = 0
                r1["filterwheel"]["position"] = 7
                r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0, timeout=5)
                r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1, timeout=5)
                if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                    plog("Set up default filter configuration.")
                self.maxim = False
                self.theskyx = False
                self.ascom = False
                self.dual_lco = True
                self.dual_fli=False
                self.custom = True

            elif isinstance(driver, list) and self.dual_filter:
                # TODO: Fix this, THIS IS A FAST KLUDGE TO GET MRC WORKING, NEED TO VERIFY THE FILTER ORDERING
                self.filter_back = win32com.client.Dispatch(driver[0])  # Closest to Camera
                self.filter_front = win32com.client.Dispatch(driver[1])  # Closest to Tel
                self.filter_back.Connected = True
                self.filter_front.Connected = True

                self.filter_front.Position = 0
                self.filter_back.Position = 0
                self.dual_lco = False
                self.custom = False

                default_filter_number = self._get_default_filter_number()

                while self.filter_front.Position == -1:
                    time.sleep(0.1)
                self.filter_front.Position = self.filter_data[default_filter_number][1][1]

                while self.filter_back.Position == -1:
                    time.sleep(0.1)
                self.filter_back.Position = self.filter_data[default_filter_number][1][0]

                plog(self.current_filter_name, self.filter_offset)
            elif driver == "ASCOM.FLI.FilterWheel" and self.dual_filter:
                self.maxim = False
                self.dual_lco = False
                self.dual_fli=False
                #breakpoint()  #We should not get here. WER 20250512
                fw0 = win32com.client.Dispatch(driver)  # Closest to Camera
                fw1 = win32com.client.Dispatch(driver)  # Closest to Telescope
                plog(fw0, fw1)

                actions0 = fw0.SupportedActions
                actions1 = fw1.SupportedActions
                for action in actions0:
                    plog("action0:   " + action)
                for action in actions1:
                    plog("action1:   " + action)
                device_names0 = fw0.Action("GetDeviceNames", "")
                plog("action0:    " + device_names0)
                devices0 = device_names0.split(";")
                device_names1 = fw1.Action("GetDeviceNames", "")
                plog("action1:    " + device_names1)
                devices1 = device_names1.split(";")
                fw0.Action("SetDeviceName", devices0[0])
                fw1.Action("SetDeviceName", devices1[1])
                fw0.Connected = True
                fw1.Connected = True
                plog("Conn 1,2:  ", fw0.Connected, fw1.Connected)
                plog("Pos  1,2:  ", fw0.Position, fw1.Position)

                self.filter_back = fw1  # Closest to Camera
                self.filter_front = fw0  # Closest to Telescope
                self.filter_back.Connected = True
                self.filter_front.Connected = True
                plog(
                    "filters are connected:  ",
                    self.filter_front.Connected,
                    self.filter_back.Connected,
                )
                plog(
                    "filter positions:  ",
                    self.filter_front.Position,
                    self.filter_back.Position,
                )

                self.custom = False

                # The code below should move the filter wheel to the default filter
                default_filter_number = self._get_default_filter_number()
                self.current_filter_name = self.filter_data[default_filter_number][0]
                self.current_filter_number = default_filter_number
                # The line below appears to be incorrect, since it will fetch the filter alias
                self.filter_offset = self.filter_data[default_filter_number][2]


                while self.filter_front.Position == -1:
                    time.sleep(0.1)
                self.filter_front.Position = self.filter_data[default_filter_number][1][1]

                while self.filter_back.Position == -1:
                    time.sleep(0.1)
                self.filter_back.Position = self.filter_data[default_filter_number][1][0]

                plog(self.current_filter_name, self.filter_offset)

            elif driver.lower() in ["maxim.ccdcamera", "maxim", "maximdl", "maximdlpro"]:
                # NOTE: Changed since FLI Dual code is failing.
                # This presumes Maxim is filter wheel controller and
                # it may be the Aux-camera controller as well.
                win32com.client.pythoncom.CoInitialize()
                self.filter = win32com.client.Dispatch(driver)

                # Monkey patch in Maxim specific methods.
                self._connected = self._maxim_connected
                self._connect = self._maxim_connect
                self.description = "Maxim is Filter Controller."
                plog("Maxim is connected:  ", self._connect(True))
                plog("Filter control is via Maxim filter interface.")
                plog(
                    "Initial filters reported are:  ",
                    self.filter.Filter,
                    self.filter.GuiderFilter,
                )
                self.maxim = True
                self.ascom = False
                self.dual_lco = False
                self.dual_fli=False
                self.custom = False


            elif "com" in driver.lower():
                self.custom = True
                try:
                    ser = serial.Serial(str(driver), timeout=12)
                    filter_pos = str(ser.read().decode())
                    plog("QHY filter is Home", filter_pos)
                    self.current_filter_number = 0
                except:
                    plog("QHY Filter not connected.")

            # This controls the filter wheel through TheSkyX
            elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
                self.maxim = False
                self.dual_lco = False
                self.dual_fli=False
                self.custom = False
                self.theskyx = True
                win32com.client.pythoncom.CoInitialize()
                self.filter = win32com.client.Dispatch(driver)
                self.filter.Connect()
                #com_object = win32com.client.Dispatch(driver)

            else:
                # We default here to setting up a single wheel ASCOM driver.
                # We need to distinguish here between an independent ASCOM filter wheel
                # and a filter that is supported by Maxim. That is specified if a Maxim
                # based driver is supplied. IF so it is NOT actually Dispatched, instead
                # we assume access is via the Maxim camera application. So basically we
                # fake having an independnet filter wheel. IF the filter supplied is
                # an ASCOM.filter then we set this device up normally. Eg., SAF is an
                # example of this version of the setup.
                self.maxim = False
                self.dual_lco = False
                self.dual_fli=False
                self.custom = False
                win32com.client.pythoncom.CoInitialize()
                self.filter_front = win32com.client.Dispatch(driver)
                self.filter_front.Connected = True
                plog("Currently QHY RS232 FW")
        else:
            self.null_filterwheel = True

        if self.null_filterwheel == False:
            self.home_command(None)




    def wait_for_filterwheel_update(self):
        sleep_period= self.filterwheel_update_period / 4
        current_updates=copy.deepcopy(self.filterwheel_updates)
        while current_updates==self.filterwheel_updates:
            time.sleep(sleep_period)

    # Note this is a thread!
    def filterwheel_update_thread(self):

        if not self.driver == "FLI.dual" and not self.driver == "LCO.dual" and not self.dummy:
            win32com.client.pythoncom.CoInitialize()

            self.filterwheel_update_wincom = win32com.client.Dispatch(self.driver)
            try:
                self.filterwheel_update_wincom.Connected = True
            except:
                # perhaps the AP mount doesn't like this.
                pass

            # If theskyx, then it needs a different connect command
            if self.driver== "CCDSoft2XAdaptor.ccdsoft5Camera":
                self.filterwheel_update_wincom.Connect()

            if self.driver.lower() in ["maxim.ccdcamera", "maxim", "maximdl", "maximdlpro"]:
                #breakpoint()
                time.sleep(1)
                try:
                    self.filterwheel_update_wincom.LinkEnabled = True
                except:
                    plog(traceback.format_exc())


        # This stopping mechanism allows for threads to close cleanly.
        while True:
            try:
                # update when a filter change is requested or every so often.
                if self.filter_change_requested or (self.filterwheel_update_timer < time.time() - self.filterwheel_update_period):


                    if self.filter_change_requested:
                        self.filter_change_requested=False
                        self.filter_changing=True


                        if self.dual_fli:

                            filter_dict={}
                            filter_dict[self.config["fli_wheel_zero_id"]]=self.filter_selections[0]
                            filter_dict[self.config["fli_wheel_one_id"]]=self.filter_selections[1]

                            print ("changing filters to " +str(filter_dict))
                            support_info.FLIsdk.fli_dual_wheel.set_positions(filter_dict)
                            print ("filters changed")
                            #breakpoint()

                        elif self.dual_filter and self.custom:
                            r0 = self.r0
                            r1 = self.r1
                            r0["filterwheel"]["position"] = self.filter_selections[0]
                            r1["filterwheel"]["position"] = self.filter_selections[1]
                            # Values to aim at
                            value_0 = r0["filterwheel"]["position"]
                            value_1 = r1["filterwheel"]["position"]
                            while True:
                                r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0, timeout=5)
                                r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1, timeout=5)
                                if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                                    break
                                else:
                                    time.sleep(0.2)

                            while True:
                                r0_t = int(
                                    requests.get(self.ip + "/filterwheel/0/position", timeout=5)
                                    .text.split('"position":')[1]
                                    .split("}")[0]
                                )
                                r1_t = int(
                                    requests.get(self.ip + "/filterwheel/1/position", timeout=5)
                                    .text.split('"position":')[1]
                                    .split("}")[0]
                                )

                                if (value_0 == r0_t) and (value_1 == r1_t):
                                    break
                                else:
                                    time.sleep(0.5)

                        elif self.dual_filter and not self.maxim:
                            try:
                                while self.filter_front.Position == -1:
                                    time.sleep(0.1)
                                self.filter_front.Position = self.filter_selections[1]

                            except:
                                pass
                            try:
                                while self.filter_back.Position == -1:
                                    time.sleep(0.1)
                                self.filter_back.Position = self.filter_selections[0]

                            except:
                                pass
                            self.filter_offset = float(self.filter_data[self.current_filter_number][2])

                        elif self.maxim and self.dual_filter:
                            try:
                                #time.sleep(2)   #WER experiment
                                self.filterwheel_update_wincom.Filter = self.filter_selections[0]
                                #time.sleep(2)   #WER experiment

                                # if self.dual_filter:
                                    #time.sleep(2)   #WER experiment
                                self.filterwheel_update_wincom.GuiderFilter = self.filter_selections[1]
                                    #time.sleep(2)   #WER experiment
                                #plog("Filter Wheel delay Experiment Lines 381, 386   WER 20250512:  ", self.filter_selections[0],"  ", self.filter_selections[1])

                            except:
                                plog(traceback.format_exc())

                        elif self.theskyx:

                            self.filterwheel_update_wincom.FilterIndexZeroBased = self.filter_data[self.current_filter_number][1][0]

                        elif self.dummy:

                            plog ("Yup. Dummy changed the filter")

                        elif self.ascom:
                            print (self.filter.Position)
                            self.filter.Position = self.filter_data[self.current_filter_number][1][0]
                            print (self.filter.Position)
                            while self.filter.Position == -1:
                                #print ("Watiing for filter wheel")
                                time.sleep(0.1)
                            print (self.filter.Position)
                            #breakpoint()

                        else:
                            try:
                                while self.filter_front.Position == -1:
                                    time.sleep(0.1)
                                self.filter_front.Position = self.filter_selections[0]
                            except:
                                plog ("Failed to change filter")
                                pass

                            self.filter_offset = float(self.filter_data[self.current_filter_number][2])

                        if self.wait_time_after_filter_change != 0:
                            #plog ("Waiting " + str(self.wait_time_after_filter_change) + " seconds for filter wheel.")
                            time.sleep(self.wait_time_after_filter_change)

                        self.filter_changing=False

                    self.filterwheel_updates=self.filterwheel_updates+1

                else:
                    time.sleep(0.05)
            except Exception as e:
                plog ("some type of glitch in the mount thread: " + str(e))
                plog(traceback.format_exc())


    # The patches. Note these are essentially a getter-setter/property constructs.
    # NB we are here talking to Maxim acting only as a filter controller.
    def _maxim_connected(self):
        return self.filter.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.filter.LinkEnabled = p_connect
        return self.filter.LinkEnabled

    def _maxim_setpoint(self, p_temp):
        self.filter.TemperatureSetpoint = float(p_temp)
        self.filter.CoolerOn = True
        return self.filter.TemperatureSetpoint

    def _get_default_filter_number(self):
        """
        Get the index of the default filter in filter_data.

        Returns:
            Integer index of the filter in self.filter_data if found,
            -1 if the filter is not found
        """
        default_name = str(self.settings.get("default_filter", None)).lower()
        if default_name == None:
            plog("WARNING: Default filter not set. Using fallback of filter 0.")
            return 0
        default_number = self._get_filter_number(default_name)
        if default_number == -1: #
            plog('WARNING: Default filter did not match any existing filters. Using fallback of filter 0.')
            return 0
        return default_number

    def _get_filter_number(self, filter_name: str) -> int:
        """
        Check if a filter exists by name and return its index in filter_data.

        Args:
            filter_name: Name of the filter to search for

        Returns:
            Integer index of the filter in self.filter_data if found,
            -1 if the filter is not found
        """
        # Convert input to lowercase for case-insensitive matching
        filter_name = str(filter_name).lower()

        # Loop through all filters and check for a matching name
        for index, fil in enumerate(self.filter_data):
            if filter_name == fil[0].lower(): # case-insensitive matching
                return index

        # If we get here, the filter wasn't found
        return -1

    def get_status(self):
        """Returns filter name, number, offset, and wheel movement status."""

        try:
            f_move = False
            status = {
                "filter_name": self.current_filter_name,
                "filter_number": self.current_filter_number,
                "filter_offset": self.filter_offset,
                "wheel_is_moving": f_move,
            }
            return status
        except:
            f_move = False
            status = {
                "filter_name": "No filter",
                "filter_number": 0,
                "filter_offset": 0.0,
                "wheel_is_moving": f_move,
            }
            return status

    def parse_command(self, command):
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]
        if self.maxim:  # NB Annoying but Maxim sometimes disconnects.
            is_connected = self._maxim_connected()
            if not is_connected:
                plog("Found filter disconnected, reconnecting!")
                self.maxim_connect(True)
        if action == "set_position":
             self.set_position_command(req, opt)
        elif action == "set_name":
            self.set_name_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            plog("Command <{action}> not recognized.")

    ###############################
    #        Filter Commands      #
    ###############################


    def return_filter_throughput(self, req: dict, opt: dict):
        """Returns the filter throughput given a filter name."""

        try:
            filter_name = str(req["filter"]).lower()
        except:
            filter_name = str(req["filter_name"]).lower()

        for match in range(
            len(self.filter_data)
        ):

            if filter_name in str(self.filter_data[match][0]).lower():
                self.current_filter_number = match
                break

        try:
            filter_throughput = float(self.filter_data[self.current_filter_number][3])
        except:
            plog("Could not find an appropriate throughput for " +str(filter_name))
            filter_throughput = np.nan

        return filter_throughput



    def set_name_command(self, req: dict, opt: dict):
        """Sets the filter position by filter name."""

        self.filter_changing = True
        #using_substitute_filter = False  This variable is never used

        try:
            filter_name = str(req["filter"]).lower()
        except:
            filter_name = str(req["filter_name"]).lower()

        if filter_name =='focus':
            try:
                filter_name=str(self.config['settings']['focus_filter']).lower()
            except:
                plog ("tried to set focus filter but it isn't set in the config so trying for a substitute.")

        #breakpoint()

        # Try finding a filter with the requested name
        filter_number = self._get_filter_number(filter_name)
        # If that fails, try finding a substitute filter
        if filter_number == -1:
            plog(f"Filter {filter_name} not found, attempting to find a substitute.")
            #using_substitute_filter = True
            requested_name = filter_name
            filter_name = self.substitute_filter(filter_name)
            try:
                # Get the index for the substitute filter
                filter_number = self._get_filter_number(filter_name)
                if filter_number == -1:
                    plog('Substitute filter is not available. This suggest a problem with the substitute_filter function.')
                    raise Exception("Substitute filter not available.")
                plog(f'Using substitute filter {filter_name} in place of {requested_name}.')
            # No substitute found
            except:
                plog("No substitute filter found, skipping exposure.")
                return "none", "none", "none"

        # Do nothing if the filter is already set
        if self.current_filter_name == filter_name:
            self.filter_changing = False
            return self.current_filter_name, self.current_filter_number, self.filter_offset

        # Report the new filter name to the user
        try:
            original_filter_name = self.filter_data[filter_number][0] # preserve capitalization
            plog(f"Filter name is:  {original_filter_name}")
            g_dev["obs"].send_to_user(f"Filter set to:  {original_filter_name}")
        except:
            pass  # This is usually when it is just booting up and obs doesn't exist yet

        # Define the filter we are about to set
        try:
            self.current_filter_name = filter_name
            self.current_filter_number = filter_number
            self.filter_selections = self.filter_data[self.current_filter_number][1]
            self.filter_offset = self.filter_offsets.get(filter_name, 0)
        except:
            plog("Failed to change filter. Returning.")
            self.current_filter_name = 'none'
            self.filter_changing=False
            return None, None, None

        # Send in the filter change request
        self.filter_change_requested = True
        # Then force the focus adjustment to the right offset position for the filter
        try:
            if not g_dev['seq'].focussing:
                g_dev['foc'].adjust_focus(force_change=True)
        except:
            plog ("not adjusting focus for filter change on bootup")

        return filter_name, filter_number, self.filter_offset

    def home_command(self, opt: dict):
        """Sets the filter to the home position."""
        self.set_name_command({"filter": str(self.settings['default_filter']).lower()}, {})


    def get_starting_throughput_value(self, requested_filter: str):
        """Returns an approximate throughput value for a
        filter when a throughput has yet to be calculated during flats
        """

        requested_filter=requested_filter.lower()

        filter_default_throughputs = {}

        filter_default_throughputs['air'] = 2800.0
        filter_default_throughputs['bb'] = 750.0
        filter_default_throughputs['bi'] = 53.0
        filter_default_throughputs['br'] = 443.0
        filter_default_throughputs['bv'] = 623.0
        filter_default_throughputs['bu'] = 40.0

        filter_default_throughputs['clear'] = 2100.0
        filter_default_throughputs['cr'] = 8.0
        filter_default_throughputs['dif'] = 1000.0 #<< Much closer to 2000 WER
        filter_default_throughputs['exo'] = 1570.0
        filter_default_throughputs['gp'] = 1420.0

        filter_default_throughputs['ha'] = 8.0
        filter_default_throughputs['ip'] = 230.0

        filter_default_throughputs['jb'] = 750.0
        filter_default_throughputs['ji'] = 53.0
        filter_default_throughputs['jr'] = 443.0
        filter_default_throughputs['jv'] = 623.0
        filter_default_throughputs['ju'] = 40.0
        filter_default_throughputs['lum'] = 2100.0

        filter_default_throughputs['n2'] = 5.0
        filter_default_throughputs['nir'] = 81.0
        filter_default_throughputs['o3'] = 40.0
        filter_default_throughputs['pb'] = 1040.0
        filter_default_throughputs['pg'] = 575.0
        filter_default_throughputs['pl'] = 2090.0
        filter_default_throughputs['pr'] = 360.0

        filter_default_throughputs['rp'] = 460.0

        filter_default_throughputs['s2'] = 5.0
        filter_default_throughputs['up'] = 40.0
        filter_default_throughputs['v'] = 623.0
        filter_default_throughputs['w'] = 2100.0
        filter_default_throughputs['zp'] = 62
        filter_default_throughputs['z'] = 11.0  #  z and zp are the same so far.  Maybe we should
                                                #standardize on adding p <rime> on the Sloane's
        filter_default_throughputs['zs'] = 8.6
                                                # 'y' will eventually be in this list. Neyle has one., but it is defective and low throughput.

        try:
            plog ("found default filter throughput value: " + str(filter_default_throughputs[requested_filter] ))
            return filter_default_throughputs[requested_filter]
        except:
            plog ("did not find a default filter value for that filter, taking a swing with a standard 150.0 throughput value")
            return 150.0

    def substitute_filter(self, requested_filter: str):
        """Returns an alternative filter if requested filter not at site.

        Substitute filters with more than one option are sorted in a priority
        order and returns the highest priority sub first.
        Skips the requested exposure if no substitute filter can be found.
        """

        # Seriously dumb way to do this..... but quick!
        # Construct available filter list
        filter_names=[]
        for ctr in range(len(self.settings['filter_data'])):
            filter_names.append(self.settings['filter_data'][ctr][0])

        available_filters = list(map(lambda x: x.lower(), filter_names))


        # if asking for a pointing filter, but it is an osc, we actually need a lum filter
        try:
            # OSC cameras gain no benefit from ip filter
            if g_dev['cam'].is_osc and requested_filter=='pointing':
                requested_filter='w'

            # If the field of view is too small, then it becomes
            # disadvantageous to use a non-white filter
            if requested_filter=='pointing':
                max_length_pixels=max(g_dev['cam'].imagesize_x,g_dev['cam'].imagesize_y)
                max_length_arcminutes=(max_length_pixels * g_dev['cam'].pixscale)/60
                if max_length_arcminutes < 45:
                    requested_filter='w'

        except:
            pass

        # List of tuples containing ([requested filter groups], [priority order]).
        # If this list continues to grow, consider putting it in a separate file.
        # This is going to get messy when we add Stromgrens, so I suggest
        # Su, Sv, Sy, Sr, Hb and Hbc    -- WER
        # next we need to purge for our sites and set them up with the correct defaults.
        #other filters in the offing:  Duo, Quad, LPR and NEB.
        filter_groups = [
            (["U", "JU", "BU", "up"], ["up", "U", "BU","JU"]),  # U broadband
            (["Blue", "B", "JB", "BB", "PB"], ["BB", "PB","JB", "B"]),  # B broadband
            (["Green", "JV", "BV", "PG","V"], ["BV", "JV","PG", "V"]),  # G broadband
            (["Red", "R", "BR", "r", "PR", "Rc", "rp"], ["rp", "BR", "PR", "Rc", "ip", "R"]),  # R broadband
            (["i", "Ic", "ip", "BI"], ["ip", "Ic", "BI"]),  # infrared broadband
            (["z", "zs", "zp"], ["zp", "zs", "z"]),  # NB z broadband  z and zs are different.  Y?  WER
            (["gp", "g"], ["gp"]),  # generic sdss-g
            (["HA", "H", 'Ha', 'H2'], ["HA"]),  # generic H
            (["O3", "O"], ["O3"]),  # generic O
            (["S2", "S"], ["S2"]),  # generic S
            (["CR", "C"], ["CR"]),  # generic C
            (["N2", "N"], ["N2"]),  # generic N
            (["dark", "dk"], ["dark", "dk"]),  # generic dark
            #NB NB WE need to be sure a double filter = dark is not being changed to just S2...
            (["dark", 'drk','dk'], ['dk', "S2", "HA", "up", "U", "JU", 'BU']),  # generic C
            (
                ["Air, air, AIR"],
                ['air', 'clear', "w",'lum', "Lum", "PL",  'silica'],
            ),  # Nothing in the way!
            (
                ["EXO",  "Exo", "exo"],
                ["EXO", "ip", "Ic", "rp", "Rc", "PR", "w", "Lum", "clear"],
            ),  # exoplanet
            (
                ["w", "W", "L", "lum", "Lum", "LUM", "PL", "clear", "focus", 'silica'],
                ["w", 'lum', "Lum", "PL", "clear", 'silica'],
            ),  # white clear
            (
                ["pointing"],
                [ "ip", "Ic", "BI","JV", "BV" ,"V", "JB", "BB", "gp", "PG", "PB", "EXO", "w", "lum", "Lum", "PL", "clear", 'silica'],
            ),  # filters ordered in least affected by nebula for quality pointing estimates.
        ]

        priority_order = []
        for group in filter_groups:
            if requested_filter.lower() in list(map(lambda x: x.lower(), group[0])):
                priority_order = group[1]

        for sub in priority_order:
            if sub.lower() in available_filters:
                if not requested_filter == 'focus':
                    plog(
                        f"Found substitute {str(sub)} filter matching requested {str(requested_filter)}"
                    )
                return str(sub).lower()
        # NB I suggest we pick the default (w) filter instead of skipping. WER

        return None