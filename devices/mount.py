import win32com.client

class Mount:

    def __init__(self, driver: str):
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True

        print(f"Mount connected.")
        print(self.mount.Description)

    def get_status(self):
        status = {"type":"mount"}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "go": 
            self.go_command(req, opt) 
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home": 
            self.home_command(req, opt)
        elif action == "flat_panel":
            self.flat_panel_command(req, opt)
        elif action == "tracking":
            self.tracking_command(req, opt)
        elif action == "park":
            self.park_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")

    ###############################
    #        Mount Commands       #
    ###############################

    def go_command(self, req, opt):
        ''' slew to the given coordinates '''
        print("mount cmd: slewing mount")
        pass

    def stop_command(self, req, opt):
        print("mount cmd: stopping mount")
        pass

    def home_command(self, req, opt):
        ''' slew to the home position '''
        print("mount cmd: homing mount")
        pass

    def flat_panel_command(self, req, opt):
        ''' slew to the flat panel if it exists '''
        print("mount cmd: slewing to flat panel")
        pass

    def tracking_command(self, req, opt):
        ''' set the tracking rates, or turn tracking off '''
        print("mount cmd: tracking changed")
        pass

    def park_command(self, req, opt):
        ''' park the telescope mount '''
        print("mount cmd: parking mount")
        pass
