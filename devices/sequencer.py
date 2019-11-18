
import win32com.client
import time
from global_yard import g_dev 

class Sequencer:

    def __init__(self, driver: str, name: str):
        self.name = name
        g_dev['seq'] = self
        self.connected = True
        self.description = "Sequencer for the eastpier mounting and OTAs"

        print(f"sequencer connected.")
        print(self.description)

    def get_status(self):
        '''
        The position is expressed as an angle from 0 up to but not including 
        360 degrees, counter-clockwise against the sky. This is the standard 
        definition of Position Angle. However, the rotator does not need to 
        (and in general will not) report the true Equatorial Position Angle, 
        as the attached imager may not be precisely aligned with the rotator's 
        indexing. It is up to the client to determine any offset between 
        mechanical rotator position angle and the true Equatorial Position 
        Angle of the imager, and compensate for any difference.
        '''
        status = {
            "active_script": 'none',
            "sequencer_busy":  'false'
        }
        return status


    

    
    def parse_command(self, command):
        print('Sequencer input:  ', command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        script = command['required_params']['script']
        if action == "run" and script == 'focus_auto':
            req = {'time': 0.2,  'alias': 'gf01', 'image_type': 'toss', 'filter': 2}
            opt = {'size': 100, 'count': 1}
            g_dev['cam'].expose_command(req, opt)   #Do not inhibit gather status for an autofocus.
        elif action == "run" and script == 'genScreenFlatMasters':
            self.screen_flat_script(req, opt)
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print('Sequencer command:  ', command, ' not recognized.')


    ###############################
    #       Sequencer Commands and Scripts
    ###############################

    def move_relative_command(self, req: dict, opt: dict):
        ''' set the focus position by moving relative to current position '''
        print(f"rotator cmd: move_relative")
        position = float(req['position'])
        self.rotator.Move(position)

    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"rotator cmd: move_absolute")
        position = float(req['position'])
        self.rotator.MoveAbsolute(position)

    def stop_command(self, req: dict, opt: dict):
        ''' stop rotator movement immediately '''
        print(f"rotator cmd: stop")
        self.rotator.Halt()

    def home_command(self, req: dict, opt: dict):
        ''' set the rotator to the home position'''
        print(f"rotator cmd: home")
        pass
    
    def screen_flat_script(self, req, opt):
        
        '''
        We will assume the filters have loaded those filters needed in screen flats, highest throughput to lowest.
        We will assume count contains the number of repeated flats needed.
        We will assume u filter is only dealt with via skyflats since its exposures are excessive with the screen.
        
        Park the mounting.
        Close the Enclosure.
        Turn off any lights.
        Use 'w' filter for now.  More generally a wide bandwidth.
            take the count
        
        '''
        gain_screen_values = [42, 39, 36, 33, 30, 27, 23, 20, 17, 14, 11, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
        bias_count = 15
        flat_count = int(req['numFrames'])
        gain_calc = req['gainCalc']
        shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        g_dev['scr'].screen_dark()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': 'gf01', 'image_type': 'Bias'}
        opt = {'size': 100, 'count': bias_count, 'filter': g_dev['fil'].filter_data[2][0]}
        breakpoint()
        g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        
        for gain in gain_screen_values :
            g_dev['scr'].set_screen_bright(gain, is_percent=False)
            g_dev['scr'].screen_light_on()
            g_dev['fil'].set_number_command(2)
            print('Test Screen; filter, bright:  ', 2, gain)
            exp_time = 1.7
            req = {'time': exp_time,  'alias': 'gf01', 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': 2, 'filter': g_dev['fil'].filter_data[2][0]}
            g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
                
        g_dev['scr'].screen_dark()
        #take a 10 s dark screen air flat to sense ambient
#        req = {'time': 10,  'alias': 'gf01', 'image_type': 'screen flat'}
#        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
#        g_dev['cam'].expose_command(req, opt, gather_status = False)
        print('Screen Gain sequence completed.')
        
    def screen_flat_script1(self, req, opt):
        
        '''
        We will assume the filters have loaded those filters needed in screen flats, highest throughput to lowest.
        We will assume count contains the number of repeated flats needed.
        We will assume u filter is only dealt with via skyflats since its exposures are excessive with the screen.
        
        Park the mounting.
        Close the Enclosure.
        Turn off any lights.
        For filter in list
            set the filter
            get its gain @ 0.2 second exposure
            set the screen
            take the count
        
        '''
        dark_count = 1
        flat_count = int(req['numFrames'])
        gain_calc = req['gainCalc']
        shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        g_dev['scr'].screen_dark()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': 'gf01', 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        
        for filt in g_dev['fil'].filter_screen_sort:
            filter_number = int(filt)
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            exposure = 0.2
            sensitivity = float(g_dev['fil'].filter_data[filter_number][4])
            sensitivity = sensitivity*exposure
            screen_bright = int((3000/sensitivity)*100/160)
            g_dev['scr'].set_screen_bright(screen_bright)
            g_dev['scr'].screen_light_on()
            g_dev['fil'].set_number_command(filter_number)
            print('Test Screen; filter, bright:  ', filter_number, screen_bright)
            exp_time = 3
            if filter_number == 9 or filter_number == 21:
                exp_time *= 8
            req = {'time': exp_time,  'alias': 'gf01', 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
                
        g_dev['scr'].screen_dark()
        #take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': 'gf01', 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False)
        print('Screen Flat sequence completed.')
 
    def sky_flat_script(self, req, opt):
        
        '''
     
             
        
        
        '''
        
    def auto_focus_script(self, req, opt):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. ti requires 8 points plus
        a verify.
        
        Quick focus consists of three points plus a verify.
        
        Fine focus consists of five points plus a verify.
        
        Optionally individual images can be multiples of one to average out seeing.

#NBNBNB This is holdover AF code to be removed.
#        if required_params['image_type'] == 'toss':           
#            count =  4    #Must be set to cause the right number of images to be taken
#            self.af_mode = True
#            self.af_step = -1
#            area = "1x-jpg"
#            new_filter = 'w'
#            exposure_time = max(exposure_time, 3.0)
#            print('AUTOFOCUS CYCLE\n')
#        else:
#            self.af_mode = False
#            self.af_step = -1 
        
        
#NB Again, ALL AF code.                        
#                        throw = 600
#                        if True:   #Was a Maxim test 
#                            if not self.af_mode:
#                                next_focus = g_dev['foc'].focuser.Position #self.current_offset + g_dev['foc'].reference
#                            else:
#                                #This is an AF cycle so need to set up.  This version  does not PRE_FOCUS from reference.
#                                if  self.af_step == -1:
#                                    self.f_positions = []
#                                    self.f_spot_dia = []
#                                    #Take first image with no focus adjustment
#                                    next_focus = g_dev['foc'].focuser.Position   #self.current_offset + g_dev['foc'].reference
#                                    self.af_start_position = next_focus
#                                    self.af_step = 0
#                                elif self.af_step == 0:
#                                    #Since cooling requires an increased focus setting move out:
#                                    next_focus = self.af_start_position + throw   #self.current_offset + g_dev['foc'].reference + throw  #+0.6mm
#                                    self.af_step = 1
#                                elif self.af_step == 1:
#                                    #This step needs to overcome backlash
#                                    next_focus = self.af_start_position - (throw + 600)   #-1.2mm
#                                    if next_focus != g_dev['foc'].focuser.Position:
#                                        #Here we overtravel them come back
#                                        g_dev['foc'].focuser.Move(next_focus)
#                                        while  g_dev['foc'].focuser.IsMoving:
#                                            time.sleep(0.5)
#                                            print('<')
#                                    #Now we advance by inward extra throw amount
#                                    next_focus = self.af_start_position - throw   #-0.6MM
#                                    self.af_step = 2                            
#                                elif self.af_step == 2:
#                                    #this should use the self.new_focus solution
#                                    next_focus = self.next_focus #self.filter_offset[selection] + ptr_config.get_focal_ref(self.name)
#                                    #next_focus -= self.filter_offset   #Filter-offsets need to be thought through better
#                                    #ptr_config.set_focal_ref(self.name, next_focus)
#                                    #Here we would update the shelved reference focus
#                                    self.af_step = 3
#                                elif self.af_step == 3:
#                                    #Here we should advance and verify new focus
#                                    #next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name) 
#                                    self.f_positions = []
#                                    self.f_spot_dia = []
#                                    self.af_mode = False    #This terminates the AF steps, if count > 4 will just read other images
#                                    self.af_step = -1
#                                    next_focus = self.next_focus
#                            next_focus = g_dev['foc'].focuser.Position     #THIS IS CLEASRLY INCORRECT
#                            if next_focus != g_dev['foc'].focuser.Position:
#                                print('****Focus adjusting to:  ', next_focus)
#                                g_dev['foc'].focuser.Move(next_focus)
        self=None
        spot = None
        #second part
        if self.af_mode:
            #THIS NEEDS DEFENSE AGAINST NaN returns from sep
            
            if 0 <= self.af_step < 3:
                #to simulate
    #                                if self.af_step == 0:
    #                                    spot = 5                                 
    #                                if self.af_step == 1: spot = 4
    #                                if self.af_step == 2: spot = 6
    #                                if self.af_step == 3: spot = 5.01                                
                self.f_positions.append(g_dev['foc'].focuser.Position)
                self.f_spot_dia.append(spot)
                print("Auto-focus:  ", self.f_spot_dia, self.f_positions)
            if self.af_step == 2:
                if self.f_spot_dia[2] <= self.f_spot_dia[0] <= self.f_spot_dia[1]:
                    print ('Increasing spot size, move in.')
                    self.next_focus = self.f_positions[2] - 250   #microns
                elif self.f_spot_dia[2] >= self.f_spot_dia[0] >= self.f_spot_dia[1]:
                    print ('Decreasing spot size, move out')
                    self.next_focus = self.f_positions[1] + 250   #microns
                else:
                    tup = self.fit_quadratic(self.f_positions, self.f_spot_dia)
                    aaa = tup[0]
                    bbb = tup[1]
                    ccc = tup[2]
                    print ('a, b, c:  ', aaa , bbb, ccc, self.f_positions, self.f_spot_dia)
                    #find the minimum
                    try:
                        x = -bbb/(2*aaa)
                        print('a, b, c, x, spot:  ', aaa ,bbb , ccc, x, aaa*x**2 + bbb*x + ccc)
                    except:
                        print('Auto Focus did not produce a Solution.')
                        x = self.af_start_position  #  Return to prior to startng g_dev['foc'].reference
                    self.next_focus = x
                self.af_step = 3
            if self.af_step == 3:
                print("Check before seeking to final.")
                print('AF result:  ', spot, g_dev['foc'].focuser.Position)
                self.f_spot_dia = []
                self.f_positions = []

        NB   Focus centering. If the solve is outside the supplied range of the focus x-values, then
        we are way out of focus.  In that case we know which way and can revert to a V-curve solution.  That
        should put the second focus test very close to correct.  Note the temp compensation is on order of -168 to -200
        microns per c.  So we need a V-Curve envelope to improve this setup.  And we need a better temp coefficient.
    '''                         
        
            
    #return  focus, temp, float(spot)
    
    