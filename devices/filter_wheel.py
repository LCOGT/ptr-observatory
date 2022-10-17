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

import config
from global_yard import g_dev


class FilterWheel:
    """A filter wheel instrument."""

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev["fil"] = self
        self.config = config["filter_wheel"]

        self.dual_filter = self.config["filter_wheel1"]["dual_wheel"]
        self.ip = str(self.config["filter_wheel1"]["ip_string"])
        self.filter_data = self.config["filter_wheel1"]["settings"]["filter_data"][
            1:
        ]  # Strips off column heading entry
        self.filter_screen_sort = self.config["filter_wheel1"]["settings"][
            "filter_screen_sort"
        ]
        self.filter_reference = int(
            self.config["filter_wheel1"]["settings"]["filter_reference"]
        )

        # NOTE: THIS CODE DOES NOT implement a filter via the Maxim application
        # which is passed in as a valid instance of class camera.
        self.filter_message = "-"
        print(
            "Please NOTE: Filter wheel may block for many seconds while first connecting & homing."
        )
        if driver == "LCO.dual":
            # home the wheel and get responses, which indicates it is connected.
            # set current_0 and _1 to [0, 0] position to default of w/L filter.

            r0 = requests.get(self.ip + "/filterwheel/0/position")
            r1 = requests.get(self.ip + "/filterwheel/1/position")
            if str(r0) == str(r1) == "<Response [200]>":
                print("LCO Wheel present and connected.")

            r0 = json.loads(r0.text)
            r1 = json.loads(r1.text)
            self.r0 = r0
            self.r1 = r1
            r0["filterwheel"]["position"] = 0
            r1["filterwheel"]["position"] = 7
            r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0)
            r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1)
            if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                print("Set up default filter configuration.")
            self.maxim = False
            self.ascom = False
            self.dual = True
            self.custom = True
            self.filter_selected = self.filter_data[self.filter_reference][0]
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
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
            self.filter_selected = self.filter_data[self.filter_reference][0]
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
            # First setup:
            time.sleep(1)
            while self.filter_front.Position == -1:
                time.sleep(0.2)
            self.filter_front.Position = self.filter_data[self.filter_reference][1][1]
            time.sleep(1)
            while self.filter_back.Position == -1:
                time.sleep(0.2)
            self.filter_back.Position = self.filter_data[self.filter_reference][1][0]
            time.sleep(1)
            print(self.filter_selected, self.filter_offset)
        elif driver == "ASCOM.FLI.FilterWheel" and self.dual_filter:
            self.maxim = False
            self.dual = True

            fw0 = win32com.client.Dispatch(driver)  # Closest to Camera
            fw1 = win32com.client.Dispatch(driver)  # Closest to Telescope
            print(fw0, fw1)

            actions0 = fw0.SupportedActions
            actions1 = fw1.SupportedActions
            for action in actions0:
                print("action0:   " + action)
            for action in actions1:
                print("action1:   " + action)
            device_names0 = fw0.Action("GetDeviceNames", "")
            print("action0:    " + device_names0)
            devices0 = device_names0.split(";")
            device_names1 = fw1.Action("GetDeviceNames", "")
            print("action1:    " + device_names1)
            devices1 = device_names1.split(";")
            fw0.Action("SetDeviceName", devices0[0])
            fw1.Action("SetDeviceName", devices1[1])
            fw0.Connected = True
            fw1.Connected = True
            print("Conn 1,2:  ", fw0.Connected, fw1.Connected)
            print("Pos  1,2:  ", fw0.Position, fw1.Position)

            self.filter_back = fw1  # Closest to Camera
            self.filter_front = fw0  # Closest to Telescope
            self.filter_back.Connected = True
            self.filter_front.Connected = True
            print(
                "filters are connected:  ",
                self.filter_front.Connected,
                self.filter_back.Connected,
            )
            print(
                "filter positions:  ",
                self.filter_front.Position,
                self.filter_back.Position,
            )

            self.dual = True
            self.custom = False
            self.filter_selected = self.filter_data[self.filter_reference][0]
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]

            # First setup:
            time.sleep(1)
            while self.filter_front.Position == -1:
                time.sleep(0.2)
            self.filter_front.Position = self.filter_data[self.filter_reference][1][1]
            time.sleep(1)
            while self.filter_back.Position == -1:
                time.sleep(0.2)
            self.filter_back.Position = self.filter_data[self.filter_reference][1][0]
            time.sleep(1)
            print(self.filter_selected, self.filter_offset)

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
            print("Maxim is connected:  ", self._connect(True))
            print("Filter control is via Maxim filter interface.")
            print(
                "Initial filters reported are:  ",
                self.filter.Filter,
                self.filter.GuiderFilter,
            )
            self.maxim = True
            self.ascom = False
            self.dual = True
            self.custom = False
            # This is the default expected after a home or power-up cycle.
            self.filter_selected = self.filter_data[self.filter_reference][0]

            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
            # We assume camera object has been created before the filter object.
            # Note filter may be commanded directly by AWS or provided in an expose
            # command as an optional parameter.
        elif "com" in driver.lower():
            self.custom = True
            try:
                ser = serial.Serial(str(driver), timeout=12)
                filter_pos = str(ser.read().decode())
                print("QHY filter is Home", filter_pos)
                self.filter_number = 0
                self.filter_name = "lpr"
            except:
                print("QHY Filter not connected.")

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
            print("Currently QHY RS232 FW")

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
                "filter_name": None,
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
                print("Found filter disconnected, reconnecting!")
                self.maxim_connect(True)
        if action == "set_position":
            self.set_position_command(req, opt)
        elif action == "set_name":
            self.set_name_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print("Command <{action}> not recognized.")

    ###############################
    #        Filter Commands      #
    ###############################

    def set_number_command(self, filter_number):
        """Sets the filter position by numeric filter position index."""

        filter_selections = self.filter_data[int(filter_number)][1]
        self.filter_number = filter_number
        self.filter_selected = self.filter_data[filter_number][0]

        if self.dual and self.custom:
            r0 = self.r0
            r1 = self.r1
            r0["filterwheel"]["position"] = filter_selections[0]
            r1["filterwheel"]["position"] = filter_selections[1]
            r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0)
            r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1)
            if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                print("Set up filter configuration;  ", filter_selections)

        elif self.dual and not self.custom:  # Dual FLI
            # NB the order of the filter_selected [1] may be incorrect
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = self.filter_selected[1]
                time.sleep(0.2)
            except:
                pass
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = self.filter_selected[0]
                time.sleep(0.2)
            except:
                pass
            self.filter_offset = float(self.filter_data[filter_number][2])
        elif self.maxim:
            g_dev["cam"].camera.Filter = filter_selections[0]
            time.sleep(0.1)
            g_dev["cam"].camera.GuiderFilter = filter_selections[1]

    def set_position_command(self, req: dict, opt: dict):
        """Sets the filter position by param string filter position index."""

        # NBNBNB This routine may not be correct. TODO: verify this works.
        filter_selections = self.filter_data[int(req["filter_num"])][1]

        if self.dual and self.custom:
            r0 = self.r0
            r1 = self.r1
            r0["filterwheel"]["position"] = filter_selections[0]
            r1["filterwheel"]["position"] = filter_selections[1]
            r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0)
            r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1)
            if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                print("Set up filter configuration;  ", filter_selections)

        elif self.dual and not self.custom:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[1]
                time.sleep(0.2)
            except:
                pass
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = filter_selections[0]
                time.sleep(0.2)
            except:
                pass
            self.filter_offset = float(self.filter_data[filter_selections][2])
        elif self.maxim:
            g_dev["cam"].camera.Filter = filter_selections[0]
            time.sleep(0.2)
            g_dev["cam"].camera.GuiderFilter = filter_selections[1]

    def set_name_command(self, req: dict, opt: dict):
        """Sets the filter position by filter name."""

        try:
            filter_name = req["filter_name"]
        except:
            try:
                filter_name = req["filter"]
            except:
                print(
                    "Unable to set filter position using filter name,\
                    double-check the filter name dictionary."
                )

        filter_identified = 0
        for match in range(
            int(self.config["filter_wheel1"]["settings"]["filter_count"])
        ):  # NB Filter count MUST be correct in Config.
            if filter_name in self.filter_data[match][0]:
                filt_pointer = match
                filter_identified = 1
                break

        # If filter was not identified, find a substitute filter
        if filter_identified == 0:
            print(
                f"Requested filter: {str(filter_name)} does not exist on this filter wheel."
            )
            filter_name = self.substitute_filter(filter_name)
            if filter_name == "none":
                return "none"
            for match in range(
                int(self.config["filter_wheel1"]["settings"]["filter_count"])
            ):  # NB Filter count MUST be correct in Config.
                if filter_name in self.filter_data[match][0]:

                    filt_pointer = match
                    filter_identified = 1
                    break

        print("Filter name is:  ", self.filter_data[match][0])
        g_dev["obs"].send_to_user("Filter set to:  " + str(self.filter_data[match][0]))
        self.filter_number = filt_pointer
        self.filter_selected = filter_name
        filter_selections = self.filter_data[filt_pointer][1]
        self.filter_offset = float(self.filter_data[filt_pointer][2])

        if self.dual and self.custom:
            r0 = self.r0
            r1 = self.r1
            r0["filterwheel"]["position"] = filter_selections[0]
            r1["filterwheel"]["position"] = filter_selections[1]
            r0_pr = requests.put(self.ip + "/filterwheel/0/position", json=r0)
            r1_pr = requests.put(self.ip + "/filterwheel/1/position", json=r1)
            if str(r0_pr) == str(r1_pr) == "<Response [200]>":
                print("Set up filter configuration;  ", filter_selections)
                print("Status:  ", r0_pr.text, r1_pr.text)
            while True:
                r0_t = int(
                    requests.get(self.ip + "/filterwheel/0/position")
                    .text.split('"position":')[1]
                    .split("}")[0]
                )
                r1_t = int(
                    requests.get(self.ip + "/filterwheel/1/position")
                    .text.split('"position":')[1]
                    .split("}")[0]
                )
                print(r0_t, r1_t)
                if r0_t == 808 or r1_t == 808:
                    time.sleep(1)
                    continue
                else:
                    print("Filters:  ", r0_t, r1_t)
                    break

        elif self.dual and not self.maxim:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[1]
                time.sleep(0.2)
            except:
                pass
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = filter_selections[0]
                time.sleep(0.2)
            except:
                pass
            self.filter_offset = float(self.filter_data[filt_pointer][2])
        elif self.maxim and self.dual:
            self.filter.Filter = filter_selections[0]
            time.sleep(0.1)
            if self.dual_filter:
                self.filter.GuiderFilter = filter_selections[1]
                time.sleep(0.1)
        else:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[0]
            except:
                pass

            self.filter_offset = float(self.filter_data[filt_pointer][2])

        return filter_name

    def home_command(self, opt: dict, opt: dict):
        """Sets the filter to the home position."""

        # NB TODO this is setting to default not Home.
        while self.filter_back.Position == -1:
            time.sleep(0.1)
        self.filter_back.Position = 2
        while self.filter_back.Position == -1:
            time.sleep(0.1)
        self.filter_selected = "w"
        self.filter_reference = 2
        self.filter_offset = int(self.filter_data[2][2])

    def substitute_filter(self, requested_filter: str):
        """Returns an alternative filter if requested filter not at site.

        Substitute filters with more than one option are sorted in a priority
        order and returns the highest priority sub first.
        Skips the requested exposure if no substitute filter can be found.
        """

        print(f"Finding substitute for {requested_filter}...")
        filter_names = self.config["filter_wheel1"]["settings"]["filter_list"]
        available_filters = list(map(lambda x: x.lower(), filter_names))
        print(
            f"Available Filters: {str(available_filters)} \
                \nRequested Filter: {str(requested_filter)}"
        )

        # List of tuples containing ([requested filter groups], [priority order]).
        # If this list continues to grow, consider putting it in a separate file.
        filter_groups = [
            (["U", "JU", "up"], ["up", "U", "JU"]),  # U broadband
            (["Blue", "B", "JB", "PB"], ["JB", "PB"]),  # B broadband
            (["Green", "JV", "PG"], ["JV", "PG"]),  # G broadband
            (["Red", "R", "r", "PR", "Rc", "rp"], ["rp", "Rc", "PR"]),  # R broadband
            (["i", "Ic", "ip"], ["ip", "Ic"]),  # infrared broadband
            (["z", "zs", "zp"], ["zp", "zs", "z"]),  # z broadband
            (["gp", "g"], ["gp"]),  # generic sdss-g
            (["HA", "H"], ["HA"]),  # generic H
            (["O3", "O"], ["O3"]),  # generic O
            (["S2", "S"], ["S2"]),  # generic S
            (["CR", "C"], ["CR"]),  # generic C
            (
                ["EXO"],
                ["EXO", "ip", "Ic", "rp", "Rc", "PR", "w", "Lum", "clear"],
            ),  # exoplanet
            (
                ["w", "W", "L", "Lum", "PL", "clear", "focus"],
                ["w", "Lum", "PL", "clear"],
            ),  # white clear
        ]

        priority_order = []
        for group in filter_groups:
            if requested_filter.lower() in list(map(lambda x: x.lower(), group[0])):
                priority_order = group[1]

        for sub in priority_order:
            if sub.lower() in available_filters:
                print(
                    f"Found substitute {str(sub)} matching requested {str(requested_filter)}"
                )
                return sub

        print("No substitute filter found, skipping exposure.")
        return "none"


if __name__ == "__main__":
    filt = FilterWheel(
        ["ASCOM.FLI.FilterWheel", "ASCOM.FLI.FilterWheel1"],
        "Dual filter wheel",
        config.site_config,
    )
