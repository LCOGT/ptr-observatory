import win32com.client
from global_yard import g_dev 
import time


class FilterWheel:

    def __init__(self, driver: str, name: str, config):
        self.name = name
        g_dev['fil']= self
        self.config = config
        self.filter_data = self.config['filter_wheel']['filter_wheel1']['settings']['filter_data'][1:]
        self.filter_screen_sort = self.config['filter_wheel']['filter_wheel1']['settings']['filter_screen_sort']
        self.filter_reference = int(self.config['filter_wheel']['filter_wheel1']['settings']['filter_reference'])
        #THIS CODE implements a filter via the Maxim application which is passed in 
        #as a valid instance of class camera.

        print('Please NOTE: Filter wheel may block for many seconds while first connecting & homing.')
        if type(driver) == list:

            self.filter_front = win32com.client.Dispatch(driver[0])
            self.filter_front.Connected = True
            self.filter_back = win32com.client.Dispatch(driver[1])
            self.filter_back.Connected = True
            self.dual = True
            self.filter_selected = self.filter_data[self.filter_reference][0]
            self.filter_number = int(self.filter_reference)
            self.filter_offset = eval(self.filter_data[self.filter_reference][2])
            #First setup:
            time.sleep(1)
            while self.filter_front.Position == -1:
                time.sleep(0.2)
            self.filter_front.Position = eval(self.filter_data[self.filter_reference][1])[1]
            time.sleep(1)
            while self.filter_back.Position == -1:
                time.sleep(0.2)
            self.filter_back.Position = eval(self.filter_data[self.filter_reference][1])[0]
            time.sleep(1)
            print(self.filter_front.Names, self.filter_back.Names, self.filter_selected, self.filter_offset)
        else:
            self.dual = False
            self.filter_front = win32com.client.Dispatch(driver)
            self.filter_front.Connected = True
            self.dual = False

    def get_status(self):
        if self.filter_front.Position == -1 or self.filter_back.Position == -1:
            f_move = 'true'
        else:
            f_move = 'false'
        status = {
            'filter_name': str(self.filter_selected),
            'filter_number': str(self.filter_number),
            'filter_offset': str(self.filter_offset),
            'wheel_is_moving': f_move
            }
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

    def set_number_command(self, filter_number):
        ''' set the filter position by numeric filter position index '''
        print(f"filter cmd: set_number")
        filter_selections = eval(self.filter_data[int(filter_number)][1])
        print('Selections:  ', filter_selections)
        self.filter_number = filter_number
        self.filter_selected = self.filter_data[filter_number][0]
        while self.filter_front.Position == -1:
            time.sleep(0.2)
        self.filter_front.Position = filter_selections[1]
        while self.filter_back.Position == -1:
            time.sleep(0.2)
        self.filter_back.Position = filter_selections[0] 
        
    def set_position_command(self, req: dict, opt: dict):
        ''' set the filter position by  param string filter position index '''
        'NBNBNB This routine may not be correct'
        print(f"filter cmd: set_position")
        filter_selections = eval(self.filter_data[int(req['filter_num'])][1])
        print('Selections:  ', filter_selections)
        while self.filter_front.Position == -1:
            time.sleep(0.2)
        self.filter_front.Position = filter_selections[1]
        while self.filter_back.Position == -1:
            time.sleep(0.2)
        self.filter_back.Position =filter_selections[0]       

    def set_name_command(self, req: dict, opt: dict):
        ''' set the filter position by filter name '''
        print(f"filter cmd: set_name", req, opt)
        filter_name = req['filter_name']
        for match in range(int(self.config['filter_wheel']['filter_wheel1']['settings']['filter_count'])):
            if filter_name == self.filter_data[match][0]:
                filt_pointer = match 
#                break
#            else:
#                print('Filter name appears to be incorrect. Check for proper case.')
        print(filt_pointer)
        self.filter_number = filt_pointer
        self.filter_selected = filter_name
        filter_selections = eval(self.filter_data[filt_pointer][1])
        print('Selections:  ', filter_selections)
        while self.filter_front.Position == -1:
            time.sleep(0.2)
        self.filter_front.Position = filter_selections[1]
        while self.filter_back.Position == -1:
            time.sleep(0.2)
        self.filter_back.Position = filter_selections[0]
        self.filter_offset = int(self.filter_data[filt_pointer][2])

    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position '''
        print(f"filter cmd: home", req, opt)
        while self.filter_back.Position == -1:
            time.sleep(0.1)
        self.filter_back.Position = 2
        while self.filter_back.Position == -1:
            time.sleep(0.1)
        self.filter_selected = 'w'
        self.filter_reference = 2
        self.filter_offset = int(self.filter_data[2][2])
      

if __name__ == '__main__':
    import config
    filt = FilterWheel(['ASCOM.FLI.FilterWheel', 'ASCOM.FLI.FilterWheel1'], "Dual filter wheel", config.site_config)