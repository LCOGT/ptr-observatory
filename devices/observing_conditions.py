
import win32com.client

class ObservingConditions:

    def __init__(self, driver: str, name: str):
        self.name = name
        self.observing_conditions = win32com.client.Dispatch(driver)
        self.observing_conditions.Connected = True

        print(f"observing_conditions connected.")
        print(self.observing_conditions.Description)

    def get_status(self):
        status = {"type":"observing_conditions"}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        
        if action is not None:
            self.move_relative_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ####################################
    #   Observing Conditions Commands  #
    ####################################

    def empty_command(self, req: dict, opt: dict):
        ''' does nothing '''
        print(f"obseving conditions cmd: empty command")
        pass