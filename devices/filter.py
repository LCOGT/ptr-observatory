import win32com.client
from global_yard import g_dev 

class Filter:

    def __init__(self, driver: str, name: str, camera=None):
        self.name = name
        g_dev['fil']= self
        #breakpoint()
        if driver[0:5] != 'Maxim':
            self.filter = win32com.client.Dispatch(driver)
            self.filter.Connected = True
    
            print(f"filter connected.")
            print(self.filter.Description)
        else:
            #THIS CODE implements a filter via the Maxim application which is passed in 
            #as a valid instance of class camera.
            print('Fabricate Maxim supported Dual filter here.')
            

    def get_status(self):
        status = {"type":"filter"}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "set_position":
            self.set_position_command(req, opt)
        elif action == "set_name":
            self.set_name_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ###############################
    #        Filter Commands      #
    ###############################

    def set_position_command(self, req: dict, opt: dict):
        ''' set the filter position by numeric filter position index '''
        print(f"filter cmd: set_position")
        pass

    def set_name_command(self, req: dict, opt: dict):
        ''' set the filter position by filter name '''
        print(f"filter cmd: set_name")
        pass

    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position '''
        print(f"filter cmd: home")
        pass