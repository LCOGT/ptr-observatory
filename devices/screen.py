import win32com.client

from global_yard import g_dev


class Screen(object):
    def __init__(self, driver: str, name: str, config):
        g_dev["scr"] = self
        self.config = config["screen"]["screen1"]
        self.device_name = name
        win32com.client.pythoncom.CoInitialize()
        self.description = self.config["desc"]
        if driver is not None:
            self.screen = win32com.client.Dispatch(driver)
            self.screen.Connected = True
            self.screen.CalibratorOff()
            self.screen_dark()
        else:
            self.screen = None
        print("Screens may take a few seconds to process commands.")
        self.scrn = str("Alnitak")   #Should come from config.
        self.status = "Off"
        self.screen_message = "-"
        self.dark_setting = "Screen is Off"
        self.bright_setting = 0.0
        self.minimum = 5
        self.saturate = 255  # NB should pick up from config


    def set_screen_bright(self, pBright, is_percent=False):
        if pBright <= 0:
            self.screen_dark()
        if is_percent:
            pBright = min(abs(pBright), 100)
            scrn_setting = int(pBright * self.saturate / 100.0)
        else:
            pBright = min(abs(pBright), self.saturate)
            scrn_setting = int(pBright)
        self.bright_setting = pBright
        print("Brightness set to:  ", scrn_setting)

    def screen_light_on(self):
        self.screen.CalibratorOn(self.bright_setting)
        self.dark_setting = "Screen is On"

    def screen_dark(self):
        self.screen.CalibratorOff()
        self.dark_setting = "Screen is Off"
        self.bright_setting = 0

    def screen_light_off(self):
        self.screen.CalibratorOff()
        self.dark_setting = "Screen is Off"
        self.bright_setting = 0

    def get_status(self):
        status = {
            "bright_setting": round(self.bright_setting, 1),
            "dark_setting": self.dark_setting,
        }
        return status

    def parse_command(self, command):
        req = command["required_params"]
        action = command["action"]
        if action == "turn_off":
            self.screen_dark()
        elif action == "turn_on":
            bright = int(req["brightness"])
            self.set_screen_bright(bright)
            self.screen_light_on()
        else:
            print("Defective Screen Command", command)


if __name__ == "__main__":
    sc = Screen("COM22", "screen1")
