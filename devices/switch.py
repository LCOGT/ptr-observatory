
import win32com.client

class Switch:

    def __init__(self, driver: str):
        self.switch = win32com.client.Dispatch(driver)
        self.switch.Connected = True

        print(f"switch connected.")
        print(self.switch.Description)

    def get_status(self):
        status = {"type":"switch"}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        
        if action == "on":
            self.on_command(req, opt)
        elif action == "off":
            self.off_command(req, opt)
        elif action == "pulse":
            self.pulse_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ##############################
    #       Switch Commands      #
    ##############################

    def on_command(self, req: dict, opt: dict):
        ''' set the switch to `on` '''
        print(f"switch cmd: on")
        pass
    def off_command(self, req: dict, opt: dict):
        ''' set the switch to `off` '''
        print(f"switch cmd: off")
        pass
    def pulse_command(self, req: dict, opt:dict):
        ''' set the switch to `pulse` '''
        pritn(f"switch cmd: pulse")
        pass