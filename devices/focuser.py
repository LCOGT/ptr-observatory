
import win32com.client

class Focuser:

    def __init__(self, driver: str, name: str):
        self.name = name
        self.focuser = win32com.client.Dispatch(driver)
        self.focuser.Connected = True

        print(f"focuser connected.")
        print(self.focuser.Description)

    def get_status(self):
        f = self.focuser
        status = {
            "Absolute": str(f.Absolute),
            "Connected": str(f.Connected),
            "IsMoving": str(f.IsMoving),
            "MaxIncrement": str(f.MaxIncrement),
            "MaxStep": str(f.MaxStep),
            "Position": str(f.Position),
            "StepSize": str(f.StepSize),
            "TempComp": str(f.TempComp),
            "Temperature": str(f.Temperature),
        }
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "move_relative":
            self.move_relative_command(req, opt)
        elif action == "move_absolute":
            self.move_absolute_command(req, opt)
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        elif action == "auto":
            self.auto_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ###############################
    #       Focuser Commands      #
    ###############################

    def move_relative_command(self, req: dict, opt: dict):
        ''' set the focus position by moving relative to current position '''
        print(f"focuser cmd: move_relative")
        pass
    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"focuser cmd: move_absolute")
        pass
    def stop_command(self, req: dict, opt: dict):
        ''' stop focuser movement '''
        print(f"focuser cmd: stop")
        self.focuser.Halt()

    def home_command(self, req: dict, opt: dict):
        ''' set the focuser to the home position'''
        print(f"focuser cmd: home")
        pass
    def auto_command(self, req: dict, opt: dict):
        ''' autofocus '''
        print(f"focuser cmd: auto")
        pass