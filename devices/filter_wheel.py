import win32com.client
from global_yard import g_dev
import time


class FilterWheel:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev['fil']= self
        self.config = config
        #print("FW:  ", config)
        self.filter_data = self.config['filter_wheel']['filter_wheel1']['settings']['filter_data'][1:]
        self.filter_screen_sort = self.config['filter_wheel']['filter_wheel1']['settings']['filter_screen_sort']
        self.filter_reference = int(self.config['filter_wheel']['filter_wheel1']['settings']['filter_reference'])
        #THIS CODE DOES NOT implemnt a filter via the Maxim application which is passed in
        #as a valid instance of class camera.
        self.filter_message = '-'
        print('Please NOTE: Filter wheel may block for many seconds while first connecting & homing.')
        if type(driver) == list:
            self.maxim = False
            self.dual = True
            win32com.client.pythoncom.CoInitialize()
            self.filter_front = win32com.client.Dispatch(driver[0])
            self.filter_front.Connected = True
            win32com.client.pythoncom.CoInitialize()
            self.filter_back = win32com.client.Dispatch(driver[1])
            self.filter_back.Connected = True
#            flifil1 or flifil3?
#            HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\ASCOM\FilterWheel Drivers\ASCOM.FLI.FilterWheel1
            print("filters are connected")
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
        elif driver.lower() in ['maxim', 'maximdl', 'maximdlpro']:
            self.maxim = True
            self.dual = False
            self.filter_selected = self.filter_data[self.filter_reference][0]   #This is the defaultexpected after a
                                                                                #Home or power-up cycle.
            self.filter_number = int(self.filter_reference)
            self.filter_offset = eval(self.filter_data[self.filter_reference][2])
            #We assume camera object has been created before the filter object.
            #Note filter may be commanded directly by AWS or provided in an expose
            #command as an optional parameter.
        else:
            '''
            We default here to setting up a single wheel ASCOM driver.
            
            We need to distinguish here between an independent ASCOM filter wheel
            and a filter that is supported by maxim.  That is specified if a Maxim
            based driver is supplied. IF so it is NOT actually Dispatched, instead
            we assume access is via the Maxim camera application.  So basically we
            fake having an independnet filter wheel.  IF the filter supplied is
            an ASCOM.filter then we set this device up normally.  Eg., SAF is an
            example of this version of the setup.

            '''
            self.maxim = False
            self.dual = False
            win32com.client.pythoncom.CoInitialize()
            breakpoint()
            self.filter_front = win32com.client.Dispatch(driver)
            self.filter_front.Connected = True
            #self.filter_front = win32com.client.Dispatch(driver)
            #self.filter_front.Connected = True
            print("Entered a filter area with no code in it.")



    def get_status(self):
        try:
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
        except:
            f_move = 'false'
            status = {
                'filter_name': str('none'),
                'filter_number': str(0),
                'filter_offset': str(0.0),
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
        if self.dual:
            #NB the order of the filter_selected [1] may be incorrect
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = self.filter_selected[1]
                time.sleep(0.2)
            except:
                breakpoint()
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = self.filter_selected[0]
                time.sleep(0.2)
            except:
                breakpoint()
            self.filter_offset = int(self.filter_data[filt_pointer][2])
        elif self.maxim:
            g_dev['cam'].camera.Filter = filter_selections[0]
            time.sleep(0.1)
            g_dev['cam'].camera.GuiderFilter = filter_selections[1]

    def set_position_command(self, req: dict, opt: dict):
        ''' set the filter position by  param string filter position index '''
        'NBNBNB This routine may not be correct'
        print(f"filter cmd: set_position")
        filter_selections = eval(self.filter_data[int(req['filter_num'])][1])
        print('Selections:  ', filter_selections)
        if self.dual:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[1]
                time.sleep(0.2)
            except:
                breakpoint()
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = filter_selections[0]
                time.sleep(0.2)
            except:
                breakpoint()
            self.filter_offset = int(self.filter_data[filt_pointer][2])
        elif self.maxim:
            g_dev['cam'].camera.Filter = filter_selections[0]
            time.sleep(0.2)
            g_dev['cam'].camera.GuiderFilter = filter_selections[1]

    def set_name_command(self, req: dict, opt: dict):
        ''' set the filter position by filter name '''
        print(f"filter cmd: set_name", req, opt)
        filter_name = req['filter']
        if filter_name =="W":
            filter_name = 'w'
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
        if self.dual:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[1]
                time.sleep(0.2)
            except:
                breakpoint()
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = filter_selections[0]
                time.sleep(0.2)
            except:
                breakpoint()
            self.filter_offset = int(self.filter_data[filt_pointer][2])
        elif self.maxim:
            g_dev['cam'].camera.Filter = filter_selections[0]
            time.sleep(0.2)
            g_dev['cam'].camera.GuiderFilter = filter_selections[1]
        else:
             return  (filter_selections, int(self.filter_data[filt_pointer][2]))

    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position '''  #NB this is setting to defaault not Home.
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