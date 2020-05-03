
import win32com.client
import time
from random import shuffle
from global_yard import g_dev
from processing.calibration import fit_quadratic

'''
Autofocus NOTE 20200122

As a general rule the focus is stable(temp).  So when code (re)starts, compute and go to that point(filter).

Nautical or astronomical dark, and time of last focus > 2 hours or delta-temp > ?1C, then schedule an
autofocus.  Presumably system is near the bottom of the focus parabola, but it may not be.

Pick a ~7mag focus star at an Alt of about 60 degrees, generally in the South.  Later on we can start
chosing and logging a range of altitudes so we can develop(temp, alt).

Take cental image, move in 1x and expose, move out 2x then in 1x and expose, solve the equation and
then finish with a check exposure.

Now there are cases if for some reason telescope is not near the focus:  first the minimum is at one end
of a linear series.  From that series and the image diameters we can imply where the focus is, subject to
seeing induced errors.  If either case occurs, go to the projected point and try again.

A second case is the focus is WAY off, and or pointing.  Make appropriate adjustments and try again.

The third case is we have a minimum.  Inspection of the FWHM may imply seeing is poor.  In that case
double the exposure and possibly do a 5-point fit rather than a 3-point.

Note at the last exposure it is reasonable to do a minor recalibrate of the pointing.

Once we have fully automatic observing it might make sense to do a more full range test of the focus mechanism
and or visit more altitudes and temeperatures.



1) Implement mag 7 star selection including getting that star at center of rotation.

2) Implement using Sep to reliably find that star.

3) change use of site config file.

4) use common settings for sep


'''

def bin_to_string(use_bin):
    if use_bin == 1:
        return '1,1'
    if use_bin == 2:
        return '2,2'
    if use_bin == 3:
        return '3,3'
    if use_bin == 4:
        return '4,4'
    if use_bin == 5:
        return'5,5'
    return '1,1'

class Sequencer:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        self.config = config
        g_dev['seq'] = self
        self.connected = True
        self.description = "Sequencer for script execution."
        self.sequencer_hold = False
        self.sequencer_message = '-'
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
        elif action == "run" and script in ['32TargetPointingRun', 'pointing_run', 'makeModel']:
            self.equatorial_pointing_run(req, opt)
        elif action == "run" and script in ("genBiasDarkMaster", "genBiasDarkMasters"):
            self.bias_dark_script(req, opt)
        elif action == "run" and script == "takeLRGBstack":
            self.take_lrgb_stack(req, opt)
        elif action == "run" and script == "takeO3HaS2N2Stack":
            self.take_lrgb_stack(req, opt)
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
        to process and update the bias-dark master images, which are sent to
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

        Parse parameters,
        if sommething to do, put up sequencer_guard, estimated duration, factoring in
        event windows -- if in a window and count = 0, keep going until end of window.
        More biases and darks never hurt anyone.
        Connect Camera
        set temperature target and wait for it (this could be first exposure of the day!)
        Flush camera 2X
        interleave the binnings with biases and darks so everthing is reasonably balanced.

        Loop until count goes to zero

        Note this can be called by the Auto Sequencer OR invoked by a user.
        """

        bias_list = []
        num_bias = max(9, req['numOfBias'])
        if req['bin1']:
            bias_list.append([1, max(9, num_bias)])
        if req['bin2']:
            bias_list.append([2, max(7, num_bias)])
        if req['bin3']:
            bias_list.append([3, max(5, num_bias//2)])
        if req['bin4']:
            bias_list.append([4, max(5, num_bias//3)])
        if req.get('bin5', False):
            bias_list.append([5, max(5, num_bias//4)])
        print('Bias_list:  ', bias_list)
        total_num_biases = 0
        for item in bias_list:
            total_num_biases += item[1]
        print("Total # of bias frames, all binnings =  ", total_num_biases )
        dark_list = []
        num_dark = max(5, req['numOfDark'])
        dark_time = float(req['darkTime'])
        if req['bin1']:
            dark_list.append([1, max(5, num_dark)])
        if req['bin2']:
            dark_list.append([2, max(3, num_dark)])
        if req['bin3']:
            dark_list.append([3, max(3, num_dark//2)])
        if req['bin4']:
            dark_list.append([4, max(3, num_dark//3)])
        if req.get('bin5', False):
            dark_list.append([5, max(3, num_dark//4)])
        print('Dark_list:  ', dark_list)
        total_num_dark = 0
        for item in dark_list:
            total_num_dark += item[1]
        print("Total # of dark frames, all binnings =  ", total_num_dark )
        long_dark_list = []
        num_long_dark = max(3, req['numOfDark2'])
        long_dark_time = float(req['dark2Time'])
        if req['bin1']:
            long_dark_list.append([1, max(3, num_long_dark)])
        if req['bin2']:
            long_dark_list.append([2, max(3, num_long_dark)])
        if req['bin3']:
            long_dark_list.append([3, max(3, num_long_dark//2)])
        if req['bin4']:
            long_dark_list.append([4, max(3, num_long_dark//3)])
        if req.get('bin5', False):
            long_dark_list.append([5, max(3, num_long_dark//4)])
        print('Long_dark_list:  ',  long_dark_list)
        total_num_long_dark = 0
        for item in long_dark_list:
            total_num_long_dark += item[1]
        print("Total # of long_dark frames, all binnings =  ", total_num_long_dark)
        bias_time = 12.  #NB Pick up from camera config
        total_time = bias_time*(total_num_biases + total_num_dark + total_num_long_dark)
        #  NB Note higher bin readout not compensated for.
        total_time += total_num_dark*float(req['darkTime']) + total_num_long_dark*float(req['dark2Time'])
        print('Approx duration of Bias Dark seguence:  ', total_time//60 + 1, ' min.')
        bias_ratio = int(total_num_biases//(total_num_dark + total_num_long_dark + 0.1) + 1)
        if bias_ratio < 1:
            bias_ratio = 1
        #Flush twice
        while len(bias_list) + len(dark_list) + len(long_dark_list) > 0:
            if len(bias_list) > 0:
                for bias in range(bias_ratio):
                    if len(bias_list) == 0:
                        pass
                    shuffle(bias_list)
                    use_bin = bias_list[0][0]   #  Pick up bin value
                    if bias_list[0][1] > 1:
                        bias_list[0][1] -= 1
                    if bias_list[0][1] <= 1:
                        bias_list.pop(0)
                    print("Expose Bias using:  ", use_bin, bias_list)
                    bin_str = bin_to_string(use_bin)
                    req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                    opt = {'size': 100, 'count': 1, 'bin': bin_str, \
                           'filter': g_dev['fil'].filter_data[0][0]}
                    breakpoint()
                    g_dev['cam'].expose_command(req, opt, gather_status=False, no_AWS=True, \
                                                do_sep=False, quick=False)
                    if len(bias_list) < 1:
                        print("Bias List exhausted.", bias_list)
                        break
            if len(dark_list) > 0:
                for dark in range(1):
                    shuffle(dark_list)
                    use_bin = dark_list[0][0]   #  Pick up bin value
                    if dark_list[0][1] > 1:
                        dark_list[0][1] -= 1
                    if dark_list[0][1] <= 1:
                        dark_list.pop(0)
                    print("Expose dark using:  ", use_bin, dark_list)
                    bin_str = bin_to_string(use_bin)
                    req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'size': 100, 'count': 1, 'bin': bin_str, \
                           'filter': g_dev['fil'].filter_data[0][0]}
                    g_dev['cam'].expose_command(req, opt, gather_status=False, no_AWS=True, \
                                                do_sep=False, quick=False)
                    if len(dark_list) < 1:
                        print("Dark List exhausted.",dark_list)
            if len(long_dark_list) > 0:
                for long_dark in range(1):
                    shuffle(long_dark_list)
                    use_bin = long_dark_list[0][0]   #  Pick up bin value
                    if long_dark_list[0][1] > 1:
                        long_dark_list[0][1] -= 1
                    if long_dark_list[0][1] <= 1:
                        long_dark_list.pop(0)
                    print("Expose long_dark using:  ", use_bin, long_dark_list)
                    bin_str = bin_to_string(use_bin)
                    req = {'time': long_dark_time,  'script': 'True', 'image_type': 'dark'}
                    opt = {'size': 100, 'count': 1, 'bin': bin_str, \
                           'filter': g_dev['fil'].filter_data[0][0]}
                    g_dev['cam'].expose_command(req, opt, gather_status=False, no_AWS=True, \
                                                do_sep=False, quick=False)
                    if len(long_dark_list) < 1:
                        print("Long_dark exhausted.", long_dark_list)
        print("fini")



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
        exp_time = 1
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
            bright, fwhm = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            g_dev['obs'].update_status()
            print("Bright:  ", bright)
            if bright > 35000:    #NB should gate with end of skyflat window as well.
                time.sleep(5)  #  (30)
                continue
            g_dev['mnt'].slewToSkyFlatAsync()
            g_dev['obs'].update_status()
            req = {'time': float(exp_time),  'alias': name, 'image_type': 'sky flat'}
            opt = {'size': 100, 'count': flat_count , 'filter': g_dev['fil'].filter_data[current_filter][0]}
            bright2, fwhm = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            time.sleep(2)
            if bright2 > 35000:
                time.sleep(5)
                continue
            print("filter pop:  ", current_filter, bright, bright2)
            pop_list.pop(0)
            g_dev['obs'].update_status()
            continue
        g_dev['mnt'].park_command({}, {})
        print('\nSky flat complete.\n')


    def screen_flat_script(self, req, opt):
        breakpoint()
        if req['numFrames'] > 1:
            flat_count = req['numFrames']
        else:
            flat_count = 7    #   A dedugging compromise

        #  NB here we ned to check cam at reasonable temp, or dwell until it is.

        alias = str(self.config['camera']['camera1']['name'])
        dark_count = 3
        exp_time = 5
        #gain_calc = req['gainCalc']
        #shut_comp =  req['shutterCompensation']
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        #  NB:  g_dev['enc'].close
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': 10,  'alias': alias, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[12][0]}  #  air has highest throughput
        # Skip for now;  bright, fwhm = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
        g_dev['scr'].screen_light_on()
        for filt in g_dev['fil'].filter_screen_sort:
            filter_number = int(filt)
            #g_dev['fil'].set_number_command(filter_number)  #THis faults
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(int(screen_setting))
            #  NB if changed we should wait 15 seconds. time.sleep(15)
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].update_status()
            print('Test Screen; filter, bright:  ', filter_number, screen_setting)

            req = {'time': float(exp_time),  'alias': alias, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            bright, fwhm = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            # if no exposure, wait 10 sec
            print("Screen flat:  ", bright, g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()
            #breakpoint()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].park_command({}, {})
        print('Sky Flat sequence completed, Telescope is parked.')

    def focus_auto_script(self, req, opt):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
        a verify.
        Quick focus consists of three points plus a verify.
        Fine focus consists of five points plus a verify.
        Optionally individual images can be multiples of one to average out seeing.
        NBNBNB This code needs to go to known stars to be moe relaible and permit subframes
        '''
        breakpoint()
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
        breakpoint()
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






