import win32com.client
from global_yard import g_dev
import time
import serial
import requests
import json
from pprint import pprint


class FilterWheel:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev['fil']= self
        self.config = config['filter_wheel']

        self.dual_filter = self.config['filter_wheel1']['dual_wheel']
        self.ip = str(self.config['filter_wheel1']['ip_string'])
        self.filter_data = self.config['filter_wheel1']['settings']['filter_data'][1:]  #  Stips off column heading entry
        self.filter_screen_sort = self.config['filter_wheel1']['settings']['filter_screen_sort']
        self.filter_reference = int(self.config['filter_wheel1']['settings']['filter_reference'])
   
        #  THIS CODE DOES NOT implement a filter via the Maxim application which is passed in
        #  as a valid instance of class camera.
        self.filter_message = '-'
        print('Please NOTE: Filter wheel may block for many seconds while first connecting & homing.')
        if driver == 'LCO.dual':
            '''
            home the wheel and get responses, hat indicates it is connected.
            set current_0 and _1 to [0, 0]
            position to default of w/L filter.
            
            '''

            r0 = requests.get(self.ip + '/filterwheel/0/position')
            r1 = requests.get(self.ip + '/filterwheel/1/position')
            if str(r0) == str(r1) == '<Response [200]>':
                print ("LCO Wheel present and connected.")

            r0 = json.loads(r0.text)
            r1 = json.loads(r1.text)
            self.r0 = r0
            self.r1 = r1
            r0['filterwheel']['position'] = 0
            r1['filterwheel']['position'] = 7
            r0_pr = requests.put(self.ip + '/filterwheel/0/position', json=r0)
            r1_pr = requests.put(self.ip + '/filterwheel/1/position', json=r1)
            if str(r0_pr) == str(r1_pr) == '<Response [200]>':
                print ("Set up default filter configuration.")
            self.maxim = False
            self.ascom = False
            self.dual = True
            self.custom = True
            self.filter_selected = self.filter_data[self.filter_reference][0]   #This is the default expected after a
            self.filter_number = self.filter_reference
            self.filter_offset = self.filter_data[self.filter_reference][2]
        elif type(driver) is list and self.dual_filter:
            '''THIS IS A FAST KLUDGE TO GET MRC@ WORKING, NEED TO VERIFY THE FILTER ORDERING'''
            
            self.filter_back = win32com.client.Dispatch(driver[0])  #  Closest to Camera
            self.filter_front = win32com.client.Dispatch(driver[1])  #  Closest to Telescope
            self.filter_back.Connected = True
            self.filter_front.Connected = True

            self.filter_front.Position = 0
            self.filter_back.Position  = 0
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
            print(self.filter_selected, self.filter_offset)   #self.filter_front.Names, self.filter_back.Names, 
        elif driver == 'ASCOM.FLI.FilterWheel' and self.dual_filter:  #   == list:
            self.maxim = False
            self.dual = True

            #win32com.client.pythoncom.CoInitialize()
            #breakpoint()
            fw0 = win32com.client.Dispatch(driver)  #  Closest to Camera
            fw1 = win32com.client.Dispatch(driver)  #  Closest to Telescope
            print(fw0, fw1)
 
            actions0 = fw0.SupportedActions
            actions1 = fw1.SupportedActions
            for action in actions0:
                print("action0:   "+ action)
            for action in actions1:
                print("action1:   " + action)
            device_names0 = fw0.Action('GetDeviceNames', '')
            print ('action0:    ' + device_names0)
            devices0 = device_names0.split(';')
            device_names1 = fw1.Action('GetDeviceNames', '')
            print ('action1:    ' + device_names1)
            devices1 = device_names1.split(';')
            fw0.Action("SetDeviceName", devices0[0])
            fw1.Action('SetDeviceName', devices1[1])
            fw0.Connected = True
            fw1.Connected = True
            print("Conn 1,2:  ", fw0.Connected, fw1.Connected)
            print('Pos  1,2:  ', fw0.Position, fw1.Position)
            #breakpoint()
            
            
            
            self.filter_back = fw1 #win32com.client.Dispatch(driver)  #  Closest to Camera
            self.filter_front = fw0 #win32com.client.Dispatch(driver)  #  Closest to Telescope
            self.filter_back.Connected = True
            self.filter_front.Connected = True
#            flifil1 or flifil3?
#            HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\ASCOM\FilterWheel Drivers\ASCOM.FLI.FilterWheel1
            print("filters are connected:  ", self.filter_front.Connected, self.filter_back.Connected)
            print("filter positions:  ", self.filter_front.Position, self.filter_back.Position)
            # self.filter_front.Position = 0
            # self.filter_back.Position  = 0
            # print("filter positions should be 0, 0:  ", self.filter_front.Position, self.filter_back.Position)
            # self.filter_front.Position = 4
            # self.filter_back.Position  = 2
            # print("filter positions should be 4, 2:  ", self.filter_front.Position, self.filter_back.Position) 
            # self.filter_front.Position = 2
            # self.filter_back.Position  = 4
            # print("filter positions should be 2, 4:  ", self.filter_front.Position, self.filter_back.Position)
            # breakpoint()
            #abooove back upplugged
            #now frront unplugged.
            #4 is diffuser, ok. #0 is air, #2 is w with blue tape wedge.
            
            #Now plug both in after both out.
            #Restart code.
            
            #back is in 2, see tape. Position reports 0.  Command to 3
            
            #THE FRONT WHEEL RESPONDS EVEN THOUGH I DID NOT CONNECT TO IT!self.
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
            print(self.filter_selected, self.filter_offset)   #self.filter_front.Names, self.filter_back.Names, 
        elif driver.lower() in ["maxim.ccdcamera", 'maxim', 'maximdl', 'maximdlpro']:
            '''
            20220508 Changed since FLI Dual code is failing. This presumes Maxim is filter wheel controller
            and it may be the Aux-camera contrller as well.
            '''
            #print('Maxim controlled filter (ONLY) is initializing.')

            win32com.client.pythoncom.CoInitialize()
            self.filter = win32com.client.Dispatch(driver)
            #Monkey patch in Maxim specific methods.
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            #self._setpoint = self._maxim_setpoint
            #self._temperature = self._maxim_temperature
            #self._expose = self._maxim_expose
            #self._stop_expose = self._maxim_stop_expose
            self.description = 'Maxim is Filter Controller.'
            print('Maxim is connected:  ', self._connect(True)) 
            #self._setpoint(float(-100))
            #self.app = win32com.client.Dispatch("Maxim.Application")
            #self.app.TelescopeConnected = True
            #print("Maxim Telescope Connected: ", self.app.TelescopeConnected)
            print('Filter control is via Maxim filter interface.')
            print("Initial filters reported is:  ", self.filter.Filter, self.filter.GuiderFilter)
            self.maxim = True
            self.ascom = False
            self.dual = True
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
                
                ###ser.write(b'1') get you to Duo
                # 0 is lpr
                # 2 is air
                # 3 in dark
                
                
                
            
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
            
    '''
     FLI.filter_wheel.py 
     
     Object-oriented interface for handling FLI (Finger Lakes Instrumentation)
     USB filter wheels
     
     author:       Craig Wm. Versek, Yankee Environmental Systems 
     author_email: cwv@yesinc.com
    """
    
    __author__ = 'Craig Wm. Versek'
    __date__ = '2012-08-16'
    
    import sys, time
    
    from ctypes import byref, c_char, c_char_p, c_long, c_ubyte, c_double
    
    from lib import FLILibrary, FLIError, FLIWarning, flidomain_t, flidev_t,\
                    fliframe_t, FLIDOMAIN_USB, FLIDEVICE_FILTERWHEEL
    
    from device import USBDevice
    ###############################################################################
    DEBUG = False
    
    ###############################################################################
    class USBFilterWheel(USBDevice):
        #load the DLL
        _libfli = FLILibrary.getDll(debug=DEBUG)
        _domain = flidomain_t(FLIDOMAIN_USB | FLIDEVICE_FILTERWHEEL)
        
        def __init__(self, dev_name, model):
            USBDevice.__init__(self, dev_name = dev_name, model = model)
    
        def set_filter_pos(self, pos):      
            self._libfli.FLISetFilterPos(self._dev, c_long(pos))
    
        def get_filter_pos(self):
            pos = c_long()      
            self._libfli.FLIGetFilterPos(self._dev, byref(pos))
            return pos.value
    
        def get_filter_count(self):
            count = c_long()      
            self._libfli.FLIGetFilterCount(self._dev, byref(count))
            return count.value
        
       
            
    ###############################################################################
    #  TEST CODE
    ###############################################################################
    if __name__ == "__main__":
        fws = USBFilterWheel.find_devices()
        fw0 = fws[0]
    '''


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
            # if self.dual and (self.filter_front.Position == -1 or self.filter_back.Position == -1):
            #     f_move = True
            #     print("At least one, of possibly two, filter wheels is moving.")
            # elif not self.dual and self.filter.Position == -1:
            #     f_move = True
            #     print('Maxim Filter is moving.')
            # else:
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
        is_connected = self._maxim_connected()
        if not is_connected:
            print("Found filter disconnected, reconnecting!")
            self.maxim_connect(True)
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
        filter_selections = self.filter_data[int(filter_number)][1]   #used to have an eval in front!
        #print('Selections:  ', filter_selections)
        self.filter_number = filter_number
        self.filter_selected = self.filter_data[filter_number][0]

        if self.dual and self.custom:

            r0 = self.r0
            r1 = self.r1
            r0['filterwheel']['position'] = filter_selections[0]
            r1['filterwheel']['position'] = filter_selections[1]
            r0_pr = requests.put(self.ip + '/filterwheel/0/position', json=r0)
            r1_pr = requests.put(self.ip + '/filterwheel/1/position', json=r1)
            if str(r0_pr) == str(r1_pr) == '<Response [200]>':
                print ("Set up filter configuration;  ", filter_selections)
            
            
        elif self.dual and not self.custom:  #Dual FLI

        
        
            #NB the order of the filter_selected [1] may be incorrect
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = self.filter_selected[1]
                time.sleep(0.2)
            except:
                pass#breakpoint()
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = self.filter_selected[0]
                time.sleep(0.2)
            except:
                pass#breakpoint()
            self.filter_offset = float(self.filter_data[filter_number][2])
        elif self.maxim:
            g_dev['cam'].camera.Filter = filter_selections[0]
            time.sleep(0.1)
            g_dev['cam'].camera.GuiderFilter = filter_selections[1]

    def set_position_command(self, req: dict, opt: dict):
        ''' set the filter position by  param string filter position index '''
        'NBNBNB This routine may not be correct'
        #print("filter cmd: set_position")

        filter_selections = self.filter_data[int(req['filter_num'])][1]
        #print('Selections:  ', filter_selections)
        breakpoint()
        if self.dual and self.custom:
            r0 = self.r0
            r1 = self.r1
            r0['filterwheel']['position'] = filter_selections[0]
            r1['filterwheel']['position'] = filter_selections[1]
            r0_pr = requests.put(self.ip + '/filterwheel/0/position', json=r0)
            r1_pr = requests.put(self.ip + '/filterwheel/1/position', json=r1)
            if str(r0_pr) == str(r1_pr) == '<Response [200]>':
                print ("Set up filter configuration;  ", filter_selections)
            
            
        elif self.dual and not self.custom:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[1]
                time.sleep(0.2)
            except:
                pass#breakpoint()
            try:
                while self.filter_back.Position == -1:
                    time.sleep(0.4)
                self.filter_back.Position = filter_selections[0]
                time.sleep(0.2)
            except:
                pass#breakpoint()
            self.filter_offset = float(self.filter_data[filter_selections][2])
        elif self.maxim:
            g_dev['cam'].camera.Filter = filter_selections[0]
            time.sleep(0.2)
            g_dev['cam'].camera.GuiderFilter = filter_selections[1]

    def set_name_command(self, req: dict, opt: dict):
        ''' set the filter position by filter name '''
        #print("filter cmd: set_name", req, opt)

        try:
            filter_name = req['filter']
        except:
            try:
                filter_name = req['filter']
            except:
                print("filter dictionary is seriously messed up.")

        # if filter_name =="W":     #  NB This is a temp patch
        #     filter_name = 'w'
        # if filter_name in ["Exo", "EXO", 'exo']:
        #     filter_name = 'exo'
        # if filter_name =="Rc":
        #     filter_name = 'R'
        # if filter_name =="r":
        #     filter_name = 'rp'
        # if filter_name =="g":
        #     filter_name = 'gp'
        # if filter_name =="i":
        #     filter_name = 'ip'
        # if filter_name =="u":
        #     filter_name = 'up'
        for match in range(int(self.config['filter_wheel1']['settings']['filter_count'])):  #NB Filter count MUST be correct in Config.
            if filter_name in self.filter_data[match][0]:

                filt_pointer = match
                break
        print('Filter name is:  ', self.filter_data[match][0])
        g_dev['obs'].send_to_user('Filter set to:  ' + str(self.filter_data[match][0]))
        #print('Filter pointer:  ', filt_pointer)
        self.filter_number = filt_pointer
        self.filter_selected = filter_name
        filter_selections = self.filter_data[filt_pointer][1]
        #print('Selections:  ', filter_selections)
        self.filter_offset = float(self.filter_data[filt_pointer][2])

        if self.dual and self.custom:
            r0 = self.r0
            r1 = self.r1
            r0['filterwheel']['position'] = filter_selections[0]
            r1['filterwheel']['position'] = filter_selections[1]
            r0_pr = requests.put(self.ip + '/filterwheel/0/position', json=r0)
            r1_pr = requests.put(self.ip + '/filterwheel/1/position', json=r1)
            if str(r0_pr) == str(r1_pr) == '<Response [200]>':
                print ("Set up filter configuration;  ", filter_selections)
                print('Status:  ', r0_pr.text, r1_pr.text)
            while True:
                r0_t = int(requests.get(self.ip + '/filterwheel/0/position').text.split('"position":')[1].split('}')[0])
                r1_t = int(requests.get(self.ip + '/filterwheel/1/position').text.split('"position":')[1].split('}')[0])
                print(r0_t,r1_t)
                if r0_t == 808 or r1_t == 808:
                    time.sleep(1)
                    continue
                else:
                    print('Filters:  ',r0_t,r1_t)

                    break
 
        elif self.dual and not self.maxim:
             try:
                 while self.filter_front.Position == -1:
                     time.sleep(0.4)
                 self.filter_front.Position = filter_selections[1]
                 time.sleep(0.2)
             except:
                 pass#breakpoint()
             try:
                 while self.filter_back.Position == -1:
                     time.sleep(0.4)
                 self.filter_back.Position = filter_selections[0]
                 time.sleep(0.2)
             except:
                 pass#breakpoint()
             self.filter_offset = float(self.filter_data[filt_pointer][2])
        elif self.maxim and self.dual:
            
# =============================================================================
#             flifil0 is closest to telescope,???
#             flifil1 is closest to camera.???
# =============================================================================
            #g_dev['cam'].camera.Filter = filter_selections[0]   #  Pure Maxim mrc
            self.filter.Filter = filter_selections[0]
            time.sleep(0.1)
            if self.dual_filter:
                self.filter.GuiderFilter = filter_selections[1]
                time.sleep(0.1)
            #g_dev['cam'].camera.GuiderFilter = filter_selections[1]
        else:
            try:
                while self.filter_front.Position == -1:
                    time.sleep(0.4)
                self.filter_front.Position = filter_selections[0]
            except:
                pass#breakpoint()

            self.filter_offset = float(self.filter_data[filt_pointer][2])

    def home_command(self, req: dict, opt: dict):
        ''' set the filter to the home position '''  #NB this is setting to default not Home.
        print("filter cmd: home", req, opt)
        #breakpoint()
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