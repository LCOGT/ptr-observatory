
import win32com.client
import time
from global_yard import g_dev
from processing.calibration import fit_quadratic

class Sequencer:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        self.config = config
        g_dev['seq'] = self
        self.connected = True
        self.description = "Sequencer for the eastpier mounting and OTAs"
        self.sequencer_hold = False
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
#            req = {'time': 0.2,  'alias': 'gf01', 'image_type': 'toss', 'filter': 2}
#            opt = {'size': 100, 'count': 1}
#            g_dev['cam'].expose_command(req, opt)   #Do not inhibit gather status for an autofocus.
            self.focus_auto_script(req, opt)
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

    def screen_flat_script_oldest(self, req, opt):

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
        bias_count = 7
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

    def screen_flat_script_old(self, req, opt):

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
        alias = self.config.site_config['camera']['camera1']['name']
        dark_count = 3
        flat_count = 3#int(req['numFrames'])
        gain_calc = req['gainCalc']
        shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        g_dev['scr'].screen_dark()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to sense ambient
        req = {'time': 1,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        for filt in g_dev['fil'].filter_screen_sort:
            filter_number = int(filt)
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            exposure = 1
            sensitivity = float(g_dev['fil'].filter_data[filter_number][4])
            sensitivity = sensitivity*exposure
            screen_bright = int((3000/sensitivity)*100/160)
            g_dev['scr'].set_screen_bright(screen_bright, is_percent=False)
            g_dev['scr'].screen_light_on()
            g_dev['fil'].set_number_command(filter_number)
            print('Test Screen; filter, bright:  ', filter_number, screen_bright)
            exp_time = 5
            if filter_number == 9 or filter_number == 21:
                exp_time *= 8
            req = {'time': exp_time,  'alias': alias, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        g_dev['scr'].screen_dark()
        #take a 10 s dark screen air flat to sense ambient
        req = {'time': 1,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False)
        print('Screen Flat sequence completed.')

    def screen_flat_script(self, req, opt):

        alias = str(self.config.site_config['camera']['camera1']['name'])
        dark_count = 1
        flat_count = 2#int(req['numFrames'])
        #gain_calc = req['gainCalc']
        #shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        for filt in g_dev['fil'].filter_screen_sort:
            filter_number = int(filt)
            #g_dev['fil'].set_number_command(filter_number)  #THis faults
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            exposure = 1
            exp_time, screen_setting = g_dev['fil'].filter_data[filter_number][4]
            g_dev['scr'].set_screen_bright(float(screen_setting))
            g_dev['obs'].update_status()
            g_dev['scr'].screen_light_on()
            g_dev['obs'].update_status()
            print('Test Screen; filter, bright:  ', filter_number, float(screen_setting))
            req = {'time': float(exp_time),  'alias': alias, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        print('Screen Flat sequence completed.')


    def sky_flat_script(self, req, opt):
        '''
        Unimplemented.
        '''

    def focus_auto_script(self, req, opt):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. ti requires 8 points plus
        a verify.
        Quick focus consists of three points plus a verify.
        Fine focus consists of five points plus a verify.
        Optionally individual images can be multiples of one to average out seeing.
        NBNBNB This code needs to go to known stars to be moe relaible and permit subframes
        '''

        print('AF entered with:  ', req, opt)
        self.sequencer_hold = True  #Blocks command checks.
        req = {'time': 3,  'alias': 'gf03', 'image_type': 'light', 'filter': 2}
        opt = {'size': 71, 'count': 1}
        #Take first image where we are
        brealpoint()
        foc_pos1 = g_dev['foc'].focuser* g_dev['foc'].steps_to_micron
        print('Autofocus Starting at:  ', foc_pos1, '\n\n')
        throw = 300
        result = g_dev['cam'].expose_command(req, opt)
        if result[0] is not None and len(result) == 2:
            spot1, foc_pos1 = result
        else:
            spot1 = 3.0
            foc_pos1 = 7700
        g_dev['foc'].focuser.Move(foc_pos1 - throw)
        result = g_dev['cam'].expose_command(req, opt)
        if result[0] is not None and len(result) == 2:
            spot2, foc_pos2 = result
        else:
            spot2 = 3.6
            foc_pos2 = 7400
        g_dev['foc'].focuser.Move(foc_pos1 + 2*throw)   #It is important to overshoot to overcome any backlash
        g_dev['foc'].focuser.Move(foc_pos1 + throw)
        result = g_dev['cam'].expose_command(req, opt)
        if result[0] is not None and len(result) == 2:
            spot3, foc_pos3 = result
        else:
            spot3 = 3.7
            foc_pos3 = 8000
        x = [foc_pos1, foc_pos2, foc_pos3]
        y = [spot1, spot2, spot3]
        #Digits are to help out pdb commands!
        a1, b1, c1, d1 = fit_quadratic(x, y)
        new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
        print ('Solved focus:  ', round(d1, 2), new_spot)
        g_dev['foc'].focuser.Move(int(d1))
        result = g_dev['cam'].expose_command(req, opt, halt=True)
        if result[0] is not None and len(result) == 2:
            spot4, foc_pos4 = result
        print('Actual focus:  ', foc_pos4, round(spot4, 2))
        self.sequencer_hold = False   #Allow comand checks.




