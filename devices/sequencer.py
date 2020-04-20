
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
        self.description = "Sequencer for script execution."
        self.sequencer_hold = False
        print(f"sequencer connected.")
        print(self.description)

    def get_status(self):
        status = {
            "active_script": 'none',
            "sequencer_busy":  'false'
        }
        return status





    def parse_command(self, command):
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
        elif action == "run" and script == 'genSkyFlatMasters':
            self.sky_flat_script(req, opt)
        elif action == "run" and script in ['32TargetPointingRun', 'pointing_run']:
            self.equatorial_pointing_run(req, opt)
        elif action.lower() in ["stop", "cancel"]:
            self.stop_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print('Sequencer command:  ', command, ' not recognized.')


    ###############################
    #       Sequencer Commands and Scripts
    ###############################
    def monitor(self):

        pass


    def bias_dark_script(self, req, opt):
        """
        This script may be auto-triggered as the bias_dark window opens,
        and this script runs for about an hour.  No images are sent to AWS.
        Images go to the calibs folder in a day-directory.  After the script
        ends build_masters.py executes in a different process and attempts
        to process and update the biad-dark master images, which are sent to
        AWS.

        Ultimately it can be running and random incoming requests for the
        camera will be honored between Bias dark images as a way to expidite
        debugging. This is not advised for normal operations.  Scheme though
        is sneak in BD images between commands to camera.  So this requires
        we have a camera_busy guard in place.  IF this works well, notice
        this means we could have a larger window to take longer darks.

        Defaults:  Darks: 9 frames  500 seconds 1:1, 360 2:2  240 3:3  120:4:4
                   Biases for each dark, 5 before, 4 after
                   Once a week: 600 seconds, 5 each to build hot pixel map

        """

        pass


    def sky_flat_script(self, req, opt):
        """

        If entered, put up a guard.
        if open conditions are acceptable then take a dark image of a dark screen, just for
        reference.
        Open the dome,
        GoTo flat spot, expose, rotating through 3 filters pick least sensitive
        discard overexposures, keep rotating.  once one of the three yeilds a good
        exposure, repeat four more times, then drop that filter from list, add a new one
        and proceed to loop.  This should allow us to generate the sensitivity list in
        the right order and not fill the system up will overexposed files.  Ultimatley
        we wait for the correct sky condition once we have the calibrations so as to not
        wear out the shutter.
        Non photometric shutters need longer exposure times.
        Note with alt-az mount we could get very near the zenith zone.
        Note we want Moon at least 30 degrees away

        """

        name = str(self.config['camera']['camera1']['name'])
        dark_count = 1
        flat_count = 1
        exp_time = 5
        #int(req['numFrames'])
        #gain_calc = req['gainCalc']
        #shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].unpark_command({}, {})
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #  We should probe to be sure dome is open, otherwise this is a test when closed and
        #  we can speed it up
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to sense ambient
        req = {'time': 10,  'alias': name, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        #g_dev['cam'].expose_command(req, opt, gather_status = False, no_AWS=True)
        g_dev['mnt'].slewToSkyFlatAsync()
        pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort']
        while len(pop_list) > 0:
            current_filter = int(pop_list[0])
            g_dev['fil'].set_number_command(current_filter)
            g_dev['mnt'].slewToSkyFlatAsync()
            req = {'time': float(exp_time),  'alias': name, 'image_type': 'sky flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[current_filter][0]}
            bright, fwhm = g_dev['cam'].expose_command(req, opt, gather_status = True, no_AWS=True)
            g_dev['obs'].update_status()
            if bright > 55000:    #NB should gate with end of skyflat window as well.
                time.sleep(30)
                continue
            g_dev['mnt'].slewToSkyFlatAsync()
            g_dev['obs'].update_status()
            req = {'time': float(exp_time),  'alias': name, 'image_type': 'sky flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[current_filter][0]}
            bright2, fwhm = g_dev['cam'].expose_command(req, opt, gather_status = True, no_AWS=True)
            time.sleep(2)
            if bright2 > 55000:
                continue
            print("filter pop:  ", current_filter, bright, bright2)
            pop_list.pop(0)
            g_dev['obs'].update_status()
            continue
        g_dev['mnt'].park_command({}, {})
        print('\nSky flat complete.\n')


    def screen_flat_script(self, req, opt):


        #  NB NB NB This code is broken.  Go back a few revs
        alias = str(self.config['camera']['camera1']['name'])
        dark_count = 1
        flat_count = 5#int(req['numFrames'])
        exp_time = 5
        #gain_calc = req['gainCalc']
        #shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': 10,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[0][0]}
        g_dev['cam'].expose_command(req, opt, gather_status =True, no_AWS=True)
        # Open Dome
        for filt in g_dev['fil'].filter_screen_sort:
            filter_number = int(filt)
            #g_dev['fil'].set_number_command(filter_number)  #THis faults
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])

            g_dev['obs'].update_status()
            print('Test Screen; filter, bright:  ', filter_number, float(screen_setting))

            req = {'time': float(exp_time),  'alias': alias, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            g_dev['cam'].expose_command(req, opt, gather_status = True, no_AWS=True)
            # if no exposure, wait 10 sec
        g_dev['obs'].update_status()

        print('Sky Flat sequence completed, Tracking is off.')

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

    def equatorial_pointing_run(self, reg, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.

        '''
        ha_deg_steps = (-72.5, -62.5, -52.5, -42.5, -32.5, -22.5, -12.5, -2.5, 7.5,
                        17.5, 27.5, 37.5, 47.5, 57.5, 67.5, 72.5, 62.5, 52.5, 42.5,
                        32.5, 22.5, 12.5, 2.5, -7.5, -17.5, -27.5, -37.5, -47.5,
                        -57.5, -67.5)
        print("Starting equatorial sweep.")
        g_dev['mnt'].unpark_command()
        cam_name = str(self.config['camera']['camera1']['name'])
        for ha_degree_value in ha_deg_steps:
            target_ra =  g_dev['mnt'].mount.SiderealTime - ha_degree_value/15.
            while target_ra < 0:
                target_ra += 24.
            while target_ra >=24:
                target_ra -= 24.
            req = {'ra':  target_ra,
                   'dec':  0.0}
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].enclosure.Slewing:
                g_dev['obs'].update_status()
                time.sleep(0.5)
            time.sleep(3)
            g_dev['obs'].update_status()
            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 10,  'alias': cam_name, 'image_type': 'Light Frame'}
            opt = {'size': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator pointing run.'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            print('Result:  ', result)
        g_dev['mnt'].stop_command()
        print("Equatorial sweep completed. Happy reducing.")
        pass






