
import win32com.client

class Focuser:

    def __init__(self, driver: str):
        self.focuser = win32com.client.Dispatch(driver)
        self.focuser.Connected = True

        print(f"focuser connected.")
        print(self.focuser.Description)

    def get_status(self):
        status = {"type":"focuser"}
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
        print(f"filter cmd: move_relative")
        pass
    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"filter cmd: move_absolute")
        pass
    def stop_command(self, req: dict, opt: dict):
        ''' stop filter movement '''
        print(f"filter cmd: stop")
        pass
    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position'''
        print(f"filter cmd: home")
        pass
    def auto_command(self, req: dict, opt: dict):
        ''' autofocus '''
        print(f"filter cmd: auto")
        pass