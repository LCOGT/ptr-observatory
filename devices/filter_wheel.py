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
import ptr_config
from global_yard import g_dev
from ptr_utility import plog

class FilterWheel:
    """A filter wheel instrument."""

    def __init__(self, driver, name: str, config: dict):
        self.name = name
        g_dev["fil"] = self
        self.config = config["filter_wheel"]
        self.previous_filter_name='none'

        self.driver = driver

        if driver is not None:
            self.null_filterwheel = False
            self.dual_filter = self.config["filter_wheel1"]["dual_wheel"]
            self.ip = str(self.config["filter_wheel1"]["ip_string"])
            self.filter_data = self.config["filter_wheel1"]["settings"]["filter_data"]
            # self.filter_screen_sort = self.config["filter_wheel1"]["settings"][
            #     "filter_screen_sort"
            # ]
            self.wait_time_after_filter_change=self.config["filter_wheel1"]["filter_settle_time"]

            self.filter_message = "-"
            plog("Please NOTE: Filter wheel may block for many seconds while first connecting \
                 & homing.")

            self.filter_change_requested=False
            self.filterwheel_update_period=0.2
            self.filterwheel_update_timer=time.time() - 2* self.filterwheel_update_period
            self.filterwheel_updates=0
            #self.focuser_update_thread_queue = queue.Queue(maxsize=0)
            self.filterwheel_update_thread=threading.Thread(target=self.filterwheel_update_thread)
            self.filterwheel_update_thread.start()

            if driver == "LCO.dual":
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
                self.dual = True
                self.custom = True

            elif isinstance(driver, list) and self.dual_filter:
                # TODO: Fix this, THIS IS A FAST KLUDGE TO GET MRC WORKING, NEED TO VERIFY THE FILTER ORDERING
                self.filter_back = win32com.client.Dispatch(driver[0])  # Closest to Camera
                self.filter_front = win32com.client.Dispatch(driver[1])  # Closest to Tel
                self.filter_back.Connected = True
                self.filter_front.Connected = True

                self.filter_front.Position = 0
                self.filter_back.Position = 0
                self.dual = True
                self.custom = False

                while self.filter_front.Position == -1:
                    time.sleep(0.1)
                self.filter_front.Position = self.filter_data[self.filter_reference][1][1]

                while self.filter_back.Position == -1:
                    time.sleep(0.1)
                self.filter_back.Position = self.filter_data[self.filter_reference][1][0]

                plog(self.filter_selected, self.filter_offset)
            elif driver == "ASCOM.FLI.FilterWheel" and self.dual_filter:
                self.maxim = False
                self.dual = True

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

                self.dual = True
                self.custom = False
                self.filter_selected = self.filter_data[self.filter_reference][0]
                self.filter_number = self.filter_reference
                self.filter_offset = self.filter_data[self.filter_reference][2]


                while self.filter_front.Position == -1:
                    time.sleep(0.1)
                self.filter_front.Position = self.filter_data[self.filter_reference][1][1]

                while self.filter_back.Position == -1:
                    time.sleep(0.1)
                self.filter_back.Position = self.filter_data[self.filter_reference][1][0]

                plog(self.filter_selected, self.filter_offset)

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
                self.dual = True
                self.custom = False

            elif "com" in driver.lower():
                self.custom = True
                try:
                    ser = serial.Serial(str(driver), timeout=12)
                    filter_pos = str(ser.read().decode())
                    plog("QHY filter is Home", filter_pos)
                    self.filter_number = 0
                    self.filter_name = "lpr"
                except:
                    plog("QHY Filter not connected.")

            # This controls the filter wheel through TheSkyX
            elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
                self.maxim = False
                self.dual = False
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
                self.dual = False
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
            #print ('ping')
            time.sleep(sleep_period)

    # Note this is a thread!
    def filterwheel_update_thread(self):


        #one_at_a_time = 0

        #Hooking up connection to win32 com focuser
        #win32com.client.pythoncom.CoInitialize()
    #     fl = win32com.client.Dispatch(
    #         win32com.client.pythoncom.CoGetInterfaceAndReleaseStream(g_dev['foc'].focuser_id, win32com.client.pythoncom.IID_IDispatch)
    # )
        #breakpoint()
        #breakpoint()
        if not self.driver == "LCO.dual":
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



        # try:
        #     self.pier_side = g_dev[
        #         "mnt"
        #     ].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
        #     self.can_report_pierside = True
        # except:
        #     self.can_report_pierside = False

        # This stopping mechanism allows for threads to close cleanly.
        while True:
            try:
                # update every so often, but update rapidly if slewing.
                if (self.filterwheel_update_timer < time.time() - self.filterwheel_update_period) or (self.currently_slewing):

                    if self.filter_change_requested:
                        self.filter_change_requested=False
                        if self.dual and self.custom:
                            r0 = self.r0
                            r1 = self.r1
                            r0["filterwheel"]["position"] = self.filter_selections[0]
                            r1["filterwheel"]["position"] = self.filter_selections[1]
                            r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0, timeout=5)
                            r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1, timeout=5)
                            if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                                pass
                            
                            print ("MTF temp filterwheel report: r0_pr " + str(r0_pr) + " r1_pr " + str(r1_pr))
                            
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
                                if r0_t == 808 or r1_t == 808:
                                    continue
                                else:
                                    pass
                                    break
                            print ("MTF temp filterwheel report: r0_t " + str(r0_t) + " r1_t " + str(r1_t))
                            

                        elif self.dual and not self.maxim:
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
                            self.filter_offset = float(self.filter_data[self.filt_pointer][2])
                        elif self.maxim and self.dual:
                            try:
                                self.filterwheel_update_wincom.Filter = self.filter_selections[0]
                                if self.dual_filter:
                                    self.filterwheel_update_wincom.GuiderFilter = self.filter_selections[1]

                            except:
                                #plog("Filter RPC error, Maxim not responding. Reset Maxim needed.")
                                plog(traceback.format_exc())
                                breakpoint()
                        elif self.theskyx:

                            self.filterwheel_update_wincom.FilterIndexZeroBased = self.filter_data[self.filt_pointer][1][0]

                        else:
                            try:
                                while self.filter_front.Position == -1:
                                    time.sleep(0.1)
                                self.filter_front.Position = self.filter_selections[0]
                            except:
                                plog ("Failed to change filter")
                                pass

                            self.filter_offset = float(self.filter_data[self.filt_pointer][2])

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

    def get_status(self):
        """Returns filter name, number, offset, and wheel movement status."""

        try:
            f_move = False
            status = {
                "filter_name": self.filter_selected,
                "filter_number": self.filter_number,
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

        filter_identified = 0

        for match in range(
            len(self.filter_data)
        ):

            if filter_name in str(self.filter_data[match][0]).lower():
                self.filt_pointer = match
                filter_identified = 1
                break

        try:
            filter_throughput = float(self.filter_data[self.filt_pointer][3])
        except:
            plog("Could not find an appropriate throughput for " +str(filter_name))
            filter_throughput = np.nan

        return filter_throughput



    def set_name_command(self, req: dict, opt: dict):
        """Sets the filter position by filter name."""

        try:
            filter_name = str(req["filter"]).lower()
        except:
            filter_name = str(req["filter_name"]).lower()
        filter_identified = 0
        
        

        for match in range(
            len(self.filter_data)
        ):

            if filter_name in str(self.filter_data[match][0]).lower():
                self.filt_pointer = match
                filter_identified = 1
                break

        # If filter was not identified, find a substitute filter
        if filter_identified == 0:
            
            filter_name = str(self.substitute_filter(filter_name)).lower()
            if filter_name == "none":
                return "none"
            for match in range(
                len(self.filter_data)
            ):
                if filter_name in str(self.filter_data[match][0]).lower():
                    self.filt_pointer = match
                    filter_identified = 1
                    break

        

        if self.previous_filter_name==filter_name:

            return self.previous_filter_name, self.previous_filter_match, self.filter_offset

        
        
        try:
            plog("Filter name is:  ", self.filter_data[match][0])
            g_dev["obs"].send_to_user("Filter set to:  " + str(self.filter_data[match][0]))
        except:
            pass  # This is usually when it is just booting up and obs doesn't exist yet
            
        try:
            self.filter_number = self.filt_pointer
            self.filter_selected = str(filter_name).lower()
            self.filter_selections = self.filter_data[self.filt_pointer][1]
            #self.filter_offset = float(self.filter_data[self.filt_pointer][2])
            self.filter_offset = 0
        except:
            plog("Failed to change filter. Returning.")
            #breakpoint()
            return None, None, None


        self.filter_change_requested=True
        self.wait_for_filterwheel_update()

# <<<<<<< Updated upstream
# =======
#             except:
#                 pass
#             self.filter_offset = float(self.filter_data[filt_pointer][2])
#         elif self.maxim and self.dual:
#             try:
#                 breakpoint()
#                 self.filter.Filter = filter_selections[0]
#                 if self.dual_filter:
#                     self.filter.GuiderFilter = filter_selections[1]
# >>>>>>> Stashed changes


        if self.wait_time_after_filter_change != 0:
            plog ("Waiting " + str(self.wait_time_after_filter_change) + " seconds for filter wheel.")
            time.sleep(self.wait_time_after_filter_change)

        # make sure focusser is adjusted every filter change
        g_dev['foc'].adjust_focus()
        self.previous_filter_name=filter_name
        self.previous_filter_match=match

        return filter_name, match, self.filter_offset

    def home_command(self, opt: dict):
        """Sets the filter to the home position."""


        self.set_name_command({"filter": self.config["filter_wheel1"]["settings"]['default_filter']}, {})


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
        for ctr in range(len(self.config["filter_wheel1"]["settings"]['filter_data'])):
            filter_names.append(self.config["filter_wheel1"]["settings"]['filter_data'][ctr][0])

        available_filters = list(map(lambda x: x.lower(), filter_names))


        # if asking for a pointing filter, but it is an osc, we actually need a lum filter
        try:
            if g_dev['cam'].is_osc and requested_filter=='pointing':
                requested_filter='w'
        except:
            pass

        #  NB NB NB note any filter string when lower cased needs to be unique. j - Johnson,
        #  c = Cousins, p or ' implies Sloane, S is for stromgren.  Some of the mappings
        #  below may not be optimal. WER

        # List of tuples containing ([requested filter groups], [priority order]).
        # If this list continues to grow, consider putting it in a separate file.
        # This is going to get messy when we add Stromgrens, so I suggest
        # Su, Sv, Sy, Sr, Hb and Hbc    -- WER
        # next we need to purge for out sites and set them up with the correct defaults.
        #other filters in the offing:  Duo, Quad, LPR and NEB.
        filter_groups = [
            (["U", "JU", "BU", "up"], ["up", "U", "BU","JU"]),  # U broadband
            (["Blue", "B", "JB", "BB", "PB"], ["JB", "BB","PB"]),  # B broadband
            (["Green", "JV", "BV", "PG"], ["JV", "BV","PG", "V"]),  # G broadband
            (["Red", "R", "BR", "r", "PR", "Rc", "rp"], ["rp", "Rc", "BR", "PR"]),  # R broadband
            (["i", "Ic", "ip", "BI"], ["ip", "Ic", "BI"]),  # infrared broadband
            (["z", "zs", "zp"], ["zp", "zs", "z"]),  # NB z broadband  z and zs are different.  Y?  WER
            (["gp", "g"], ["gp"]),  # generic sdss-g
            (["HA", "H", 'Ha'], ["HA"]),  # generic H
            (["O3", "O"], ["O3"]),  # generic O
            (["S2", "S"], ["S2"]),  # generic S
            (["CR", "C"], ["CR"]),  # generic C
            (["N2", "N"], ["N2"]),  # generic N
            (["dark"], ["S2", "O3", "HA", "up", "U", "JU"]),  # generic C
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
                plog(
                    f"Found substitute {str(sub)} filter matching requested {str(requested_filter)}"
                )
                return str(sub).lower()
        # NB I suggest we pick the default (w) filter instead of skipping. WER

        plog("No substitute filter found, skipping exposure.")
        return "none", None, None


# if __name__ == "__main__":
#     filt = FilterWheel(
#         ["ASCOM.FLI.FilterWheel", "ASCOM.FLI.FilterWheel1"],
#         "Dual filter wheel",
#         config.site_config,
#     )