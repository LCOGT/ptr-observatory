import win32com.client
from global_yard import g_dev
import time
import serial


class FilterWheel:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev['fil']= self
        self.config = config['filter_wheel']
        print("FW:  ", self.config)
        self.filter_data = self.config['filter_wheel1']['settings']['filter_data'][1:]  #  Stips off column heading entry
        self.filter_screen_sort = self.config['filter_wheel1']['settings']['filter_screen_sort']
        self.filter_reference = int(self.config['filter_wheel1']['settings']['filter_reference'])
        #  THIS CODE DOES NOT implement a filter via the Maxim application which is passed in
        #  as a valid instance of class camera.
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
            self.custom = False
            self.filter_selected = self.filter_data[self.filter_reference][0]
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
            #First setup:
            time.sleep(1)
            while self.filter_front.Position == -1:
                time.sleep(0.2)
            self.filter_front.Position = self.filter_data[self.filter_reference][1][1]
            time.sleep(1)
            while self.filter_back.Position == -1:
                time.sleep(0.2)
            self.filter_back.Position = self.filter_data[self.filter_reference][1][0]
            time.sleep(1)
            print(self.filter_front.Names, self.filter_back.Names, self.filter_selected, self.filter_offset)
        elif driver.lower() in ["maxim.ccdcamera", 'maxim', 'maximdl', 'maximdlpro']:
            print('Maxim controlled filter (ONLY) is initializing.')
            win32com.client.pythoncom.CoInitialize()
            breakpoint()
            self.filter = win32com.client.Dispatch(driver)
            #Monkey patch in Maxim specific methods.
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            self._setpoint = self._maxim_setpoint
            #self._temperature = self._maxim_temperature
            #self._expose = self._maxim_expose
            #self._stop_expose = self._maxim_stop_expose
            self.description = 'Maxim as Filter Controller is connecting.'
            print('Maxim is connected:  ', self._connect(True))
            self._setpoint(float(100))
            #self.app = win32com.client.Dispatch("Maxim.Application")
            #self.app.TelescopeConnected = True
            #print("Maxim Telescope Connected: ", self.app.TelescopeConnected)
            print('Control is Maxim filter interface.')
            self.maxim = True
            self.ascom = False
            self.dual = False
            self.custom = False
            self.filter_selected = self.filter_data[self.filter_reference][0]   #This is the default expected after a
                                                                                #Home or power-up cycle.
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
            #We assume camera object has been created before the filter object.
            #Note filter may be commanded directly by AWS or provided in an expose
            #command as an optional parameter.
        elif driver.lower() == 'com22':
            self.custom = True
            try:
                ser = serial.Serial("COM22", timeout=12)
                filter_pos = str(ser.read().decode())
                print("QHY filter is Home", filter_pos )
                self.filter_number = 0
                self.filter_name = 'lpr'
            except:
                print("QHY Filter not connected.")
                
                
                
            
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
            self.custom = False
            win32com.client.pythoncom.CoInitialize()
            self.filter_front = win32com.client.Dispatch(driver)
            self.filter_front.Connected = True
            print("Currently QHY RS232 FW")

    #The patches.   Note these are essentially a getter-setter/property constructs.
    #  NB we are here talking to Maxim acting only as a filter controller.
    def _maxim_connected(self):
        return self.filter.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.filter.LinkEnabled = p_connect
        return self.filter.LinkEnabled

    # def _maxim_temperature(self):
    #     return self.camera.Temperature

    def _maxim_setpoint(self, p_temp):
        self.filter.TemperatureSetpoint = float(p_temp)
        self.filter.CoolerOn = True
        return self.filter.TemperatureSetpoint

    # def _maxim_expose(self, exposure_time, imtypeb):
    #     self.camera.Expose(exposure_time, imtypeb)

    # def _maxim_stop_expose(self):
    #     self.camera.AbortExposure()



    def get_status(self):
        # if self.custom is True:
        #     status = {
        #         'filter_name': str(self.filter_name),
        #         'filter_number': str(self.filter_number),
        #         'filter_offset': str(0),
        #         'wheel_is_moving': 'false'
        #         }
        #     return status
            
        try:
            if self.dual and (self.filter_front.Position == -1 or self.filter_back.Position == -1):
                f_move = True
                print("At least one, of possibly two, filter wheels is moving.")
            elif not self.dual and self.filter.Position == -1:
                f_move = True
                print('Maxim Filter is moving.')
            else:
                f_move = False
            status = {
                'filter_name': self.filter_selected,
                'filter_number': self.filter_number,
                'filter_offset': self.filter_offset,
                'wheel_is_moving': f_move
                }
            return status
        except:
            f_move = False
            status = {
                'filter_name': None,
                'filter_number': 0,
                'filter_offset': 0.0,
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
            print("Command <{action}> not recognized.")


    ###############################
    #        Filter Commands      #
    ###############################

    def set_number_command(self, filter_number):
        ''' set the filter position by numeric filter position index '''
        #print("filter cmd: set_number")
        filter_selections = eval(self.filter_data[int(filter_number)][1])
        #print('Selections:  ', filter_selections)
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
        #print("filter cmd: set_position")
        breakpoint()
        filter_selections = self.filter_data[int(req['filter_num'])][1]
        #print('Selections:  ', filter_selections)
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
        #print("filter cmd: set_name", req, opt)
        try:
            filter_name = req['filter_name']
        except:
            try:
                filter_name = req['filter']
            except:
                print("filter dictionary is screwed up big time.")

        if filter_name =="W":     #  NB This is a temp patch
            filter_name = 'w'
        if filter_name =="r":
            filter_name = 'rp'
        if filter_name =="g":
            filter_name = 'gp'
        if filter_name =="i":
            filter_name = 'ip'
        if filter_name =="u":
            filter_name = 'up'
        for match in range(int(self.config['filter_wheel1']['settings']['filter_count'])):
            if filter_name == self.filter_data[match][0]:
                filt_pointer = match
                break
        print('Filter name is:  ', self.filter_data[match][0])
        print('Filter pointer:  ', filt_pointer)
        self.filter_number = filt_pointer
        self.filter_selected = filter_name
        filter_selections = self.filter_data[filt_pointer][1]   # eliminated eval with config format to Python values.
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
            
            #g_dev['cam'].camera.Filter = filter_selections[0]   #  Pure Maxim WMD
            self.filter.Filter = filter_selections[0]
            time.sleep(0.2)
            #g_dev['cam'].camera.GuiderFilter = filter_selections[1]
        else:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[0]
            except:
                breakpoint()
            self.filter_offset = float(self.filter_data[filt_pointer][2])

    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position '''  #NB this is setting to default not Home.
        print("filter cmd: home", req, opt)
        breakpoint()
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