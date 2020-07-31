
import win32com.client
import time
from random import shuffle
from global_yard import g_dev
import ephem
import build_tycho as tycho
from pprint import pprint

'''
Autofocus NOTE 20200122

As a general rule the focus is stable(temp).  So when code (re)starts, compute and go to that point(filter).

Nautical or astronomical dark, and time of last focus > 2 hours or delta-temp > ?1C, then schedule an
autofocus.  Presumably system is near the bottom of the focus parabola, but it may not be.

Pick a ~7mag focus star at an Alt of about 60 degrees, generally in the South.  Later on we can start
chosing and logging a range of altitudes so we can develop adj_focus(temp, alt, flip_side).

Take central image, move in 1x and expose, move out 2x then in 1x and expose, solve the equation and
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
#  NBNB This is a copy of this routine found in camera.py.  Bad form.
def create_simple_sequence(exp_time=0, img_type=0, speed=0, suffix='', repeat=1, \
                    readout_mode="RAW Mono", filter_name='W', enabled=1, \
                    binning=1, binmode=0, column=1):
    exp_time = round(abs(float(exp_time)), 3)
    if img_type > 3:
        img_type = 0
    repeat = abs(int(repeat))
    if repeat < 1:
        repeat = 1
    binning = abs(int(binning))
    if binning > 4:
        binning = 4
    if filter_name == "":
        filter_name = 'W'
    proto_file = open('D:/archive/archive/sq01/seq/ptr_saf.pro')
    proto = proto_file.readlines()
    proto_file.close()
    print(proto, '\n\n')

    if column == 1:
        proto[62] = proto[62][:9]  + str(exp_time) + proto[62][12:]
        proto[63] = proto[63][:9]  + str(img_type) + proto[63][10:]
        proto[58] = proto[58][:12] + str(suffix)   + proto[58][12:]
        proto[56] = proto[56][:10] + str(speed)    + proto[56][11:]
        proto[37] = proto[37][:11] + str(repeat)   + proto[37][12:]
        proto[33] = proto[33][:17] + readout_mode  + proto[33][20:]
        proto[15] = proto[15][:12] + filter_name   + proto[15][13:]
        proto[11] = proto[11][:12] + str(enabled)  + proto[11][13:]
        proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
    seq_file = open('D:/archive/archive/sq01/seq/ptr_saf.seq', 'w')
    for item in range(len(proto)):
        seq_file.write(proto[item])
    seq_file.close()
    print(proto)

def fit_quadratic(x, y):
    #From Meeus, works fine.
    #Abscissa arguments do not need to be ordered for this to work.
    #NB Single alpha variable names confict with debugger commands.
    if len(x) == len(y):
        p = 0
        q = 0
        r = 0
        s = 0
        t = 0
        u = 0
        v = 0
        for i in range(len(x)):
            p += x[i]
            q += x[i]**2
            r += x[i]**3
            s += x[i]**4
            t += y[i]
            u += x[i]*y[i]
            v += x[i]**2*y[i]
        n = len(x)
        d = n*q*s +2*p*q*r - q*q*q - p*p*s - n*r*r
        a = (n*q*v + p*r*t + p*q*u - q*q*t - p*p*v - n*r*u)/d
        b = (n*s*u + p*q*v + q*r*t - q*q*u - p*s*t - n*r*v)/d
        c = (q*s*t + q*r*u + p*r*v - q*q*v - p*s*u - r*r*t)/d
        print('Quad;  ', a, b, c)
        try:
            return (a, b, c, -b/(2*a))
        except:
            return (a, b, c)
    else:
        return None

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

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.config = config
        g_dev['seq'] = self
        self.connected = True
        self.description = "Sequencer for script execution."
        self.sequencer_hold = False
        self.sequencer_message = '-'
        print(f"sequencer connected.")
        print(self.description)
        self.guard = False

    def get_status(self):
        status = {
            "active_script": 'none',
            "sequencer_busy":  'false'
        }
        if not self.sequencer_hold:   #  NB THis should be wrapped in a timeout.
            self.manager()      #  There be dragons here!  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status





    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        g_dev['cam'].user_id = command['user_id']
        g_dev['cam'].user_name = command['user_name']
        action = command['action']
        script = command['required_params']['script']

        if action == "run" and script == 'focusAuto':
#            req = {'time': 0.2,  'alias': 'gf01', 'image_type': 'toss', 'filter': 2}
#            opt = {'size': 100, 'count': 1}
#            g_dev['cam'].expose_command(req, opt)   #Do not inhibit gather status for an autofocus.
            self.focus_auto_script(req, opt)
        elif action == "run" and script == 'genScreenFlatMasters':
            self.screen_flat_script(req, opt)
        elif action == "run" and script == 'genSkyFlatMasters':
            self.sky_flat_script(req, opt)
        elif action == "run" and script in ['32TargetPointingRun', 'pointingRun', 'makeModel']:
            self.sky_grid_pointing_run(req, opt)
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
    def manager(self):
        '''
        This is where scripts are automagically started.  Be careful what you put in here if it is
        going to open the dome or move the telescope at unexpected times.

        Scripts must not block too long or they must provide for periodic calls to check status.
        '''
        # NB Need a better way to get all the events.
        #obs_win_begin, sunZ88Op, sunZ88Cl, ephemNow = self.astro_events.getSunEvents()
        ephem_now = ephem.now()
        events = g_dev['events']

        self.current_script = "No current script"
        self.sequencer_hold = False
         #events['Eve Bias Dark']
        #if True:
        if (events['Eve Bias Dark'] <= ephem_now <= events['End Eve Bias Dark']) and False:
            req = {'numOfBias': 31, 'bin3': True, 'numOfDark2': 3, 'bin4': False, 'bin1': True, \
                   'darkTime': 360, 'hotMap': True, 'bin2': True, 'numOfDark': 3, 'dark2Time': 600, \
                   'coldMap': True, 'script': 'genBiasDarkMaster', 'bin5': False}
            opt = {}
            self.bias_dark_script(req, opt)
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        # elif (events[] <= ephem_now <= events[]):
        #     pass
        elif  (events['Eve Sky Flats'] < ephem_now < events['End Eve Sky Flats'])  \
                and g_dev['enc'].mode == 'Automatic' \
                and g_dev['ocn'].wx_is_ok \
                and not g_dev['ocn'].wx_hold \
                and not self.guard:      #  and g_dev['ocn'].wait_time <= 0 \
            self.guard = True
            self.current_script = "Eve Sky Flat script"
            self.sky_flat_script({}, {})   #Null command dictionaries
            self.guard = False
        else:
            self.current_script = "No current script"
            self.guard = False
            #print("No active script is scheduled.")
        pass


    def bias_dark_script(self, req=None, opt=None):
        """

        20200618   THis has been drastically simplied for now to deal with only QHY600M.

        This script may be auto-triggered as the bias_dark window opens, or
        by a qualified user.
        This auto script runs for about an hour.  No auto-triggered images are sent to AWS.
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
        if something to do, put up sequencer_guard, estimated duration, factoring in
        event windows -- if in a window and count = 0, keep going until end of window.
        More biases and darks never hurt anyone.
        Connect Camera
        set temperature target and wait for it (this could be first exposure of the day!)
        Flush camera 2X
        interleave the binnings with biases and darks so everthing is reasonably balanced.

        Loop until count goes to zero

        Note this can be called by the Auto Sequencer OR invoked by a user with different counts
        """
        if req is None:     #  NB This again should be a config item. 274 takes about 1 hour with SBIG 6303
            req = {'numOfBias': 127, 'bin3': False, 'numOfDark2': 0, 'bin4': False, 'bin1': True, \
                    'darkTime': '360', 'hotMap': True, 'bin2': false, 'numOfDark': 31, 'dark2Time': '720', \
                    'coldMap': True, 'script': 'genBiasDarkMaster'}
            opt = {}
        self.sequencer_hold = True
        bias_list = []
        num_bias = max(15, req['numOfBias'])
        breakpoint()
        if req['bin4']:
            bias_list.append([4, max(5, int(num_bias*19/255))])   #THis whole scheme is wrong. 20200525 WER
        if req['bin3']:
            bias_list.append([3, max(5, int(num_bias*35/255))])
        if req['bin2']:
            bias_list.append([2, max(9, int(num_bias*74/255))])
        if req['bin1']:
            bias_list.append([1, max(9, num_bias)])
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
            dark_list.append([2, max(5, num_dark)])
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
        num_long_dark = max(0, req['numOfDark2'])
        long_dark_time = float(req['dark2Time'])
        if req['bin1']:
            long_dark_list.append([1, max(0, num_long_dark)])
        if req['bin2']:
            long_dark_list.append([2, max(3, num_long_dark)])
        if req['bin3']:
            long_dark_list.append([3, max(3, num_long_dark//2)])   #  NB  need to create a make_odd function
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
                    result = g_dev['cam'].expose_command(req, opt, gather_status=False, no_AWS=True, \
                                                do_sep=False, quick=False)
                    print(result)

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
        print("Bias dark acquisition is finished.")
        self.sequencer_hold = False
        return



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
        self.guard = True
        print('Eve Sky Flat sequence Starting, Enclosure PRESUMED Open. Telescope will un-park.')
        camera_name = str(self.config['camera']['camera1']['name'])
        flat_count = 5
        exp_time = .1
        #  NB Sometime, try 2:2 binning and interpolate a 1:1 flat.  This might run a lot faster.
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].unpark_command({}, {})
        if g_dev['enc'].is_dome:
            g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #  We should probe to be sure dome is open, otherwise this is a test when closed and
        #  we can speed it up
        #Here we may need to switch off any
        #  Pick up list of filters is sky flat order of lowest to highest transparency.
        pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort']
        print('filters by low to high transmission:  ', pop_list)
        obs_win_begin, sunset, sunrise, ephemNow = self.astro_events.getSunEvents()
        while len(pop_list) > 0 and (ephemNow < g_dev['events']['End Eve Sky Flats']):

            current_filter = int(pop_list[0])
            acquired_count = 0
            #g_dev['fil'].set_number_command(current_filter)
            #g_dev['mnt'].slewToSkyFlatAsync()
            bright = 65000
            while acquired_count < flat_count:
                if g_dev['enc'].is_dome:
                    g_dev['mnt'].slewToSkyFlatAsync()
                req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}
                opt = {'size': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[current_filter][0]}
                print("using:  ", g_dev['fil'].filter_data[current_filter][0])
                result = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True, do_sep = False)
                bright = result['patch']    #  Patch should be circular and 20% of Chip area. ToDo project
                print("Bright:  ", bright)  #  Others are 'NE', 'NW', 'SE', 'SW'.
                if bright > 35000 and (ephemNow < g_dev['events']['End Eve Sky Flats']
                                  or True):    #NB should gate with end of skyflat window as well.
                    for i in range(1):
                        time.sleep(5)  #  #0 seconds of wait time.  Maybe shorten for wide bands?
                        g_dev['obs'].update_status()
                else:
                    acquired_count += 1
                    if acquired_count == flat_count:
                        pop_list.pop(0)
                continue
        g_dev['mnt'].park_command({}, {})  #  NB this is provisional, Ok when simulating
        print('\nSky flat complete.\n')
        self.guard = False


    def screen_flat_script(self, req, opt):
        if req['numFrames'] > 1:
            flat_count = req['numFrames']
        else:
            flat_count = 7    #   A dedugging compromise

        #  NB here we need to check cam at reasonable temp, or dwell until it is.

        camera_name = str(self.config['camera']['camera1']['name'])
        dark_count = 3
        exp_time = 5
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        #  NB:  g_dev['enc'].close
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': 10,  'alias': camera_name, 'image_type': 'screen flat'}
        opt = {'size': 100, 'count': dark_count, 'filter': g_dev['fil'].filter_data[12][0]}  #  air has highest throughput
        # Skip for now;  bright, fwhm = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
        # g_dev['scr'].screen_light_on()

        for filt in g_dev['fil'].filter_screen_sort:
            #enter with screen dark
            filter_number = int(filt)
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(int(screen_setting))
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].update_status()

            print('Dark Screen; filter, bright:  ', filter_number, 0.0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': 2, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            result = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            bright = result['patch']
            print("Dark Screen flat, starting:  ", bright, g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()

            print('Lighted Screen; filter, bright:  ', filter_number, screen_setting)
            g_dev['scr'].screen_light_on()
            time.sleep(10)
            g_dev['obs'].update_status()
            time.sleep(10)
            g_dev['obs'].update_status()
            time.sleep(10)
            g_dev['obs'].update_status()
            req = {'time': float(exp_time)/10.,  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': 2, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            result = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            bright = result['patch']
            # if no exposure, wait 10 sec
            print("Lighted Screen flat:  ", bright, g_dev['fil'].filter_data[filter_number][0], '\n\n')

            g_dev['obs'].update_status()
            g_dev['scr'].screen_dark()
            time.sleep(10)
            print('Dark Screen; filter, bright:  ', filter_number, 0.0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'size': 100, 'count': 2, 'filter': g_dev['fil'].filter_data[filter_number][0]}
            result = g_dev['cam'].expose_command(req, opt, gather_status=True, no_AWS=True)
            bright = result['patch']# if no exposure, wait 10 sec
            print("Dark Screen flat, ending:  ", bright, g_dev['fil'].filter_data[filter_number][0], '\n\n')


            #breakpoint()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].park_command({}, {})
        print('Eve Sky Flat sequence completed, Telescope is parked.')
        self.guard = False

    def focus_auto_script(self, req, opt):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
        a verify.
        Quick focus consists of three points plus a verify.
        Fine focus consists of five points plus a verify.
        Optionally individual images can be multiples of one to average out seeing.
        NBNBNB This code needs to go to known stars to be moe relaible and permit subframes

        Result format:
                        result['mean_focus'] = avg_foc[1]
                        result['mean_rotation'] = avg_rot[1]
                        result['FWHM'] = spot   What is returned is a close proxy to real fitted FWHM.
                        result['half_FD'] = None
                        result['patch'] = cal_result
                        result['temperature'] = avg_foc[2]  This is probably tube not reported by Gemini.
        '''
        self.guard = True
        print('AF entered with:  ', req, opt)
        #self.sequencer_hold = True  #Blocks command checks.
        start_ra = g_dev['mnt'].RightAscension
        start_dec = g_dev['mnt'].Declination
        if req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters

            #  Go to closest Mag 7.5 Tycho * with no flip
            focus_star = tycho.dist_sort_targets(g_dev['tel'].current_icrs_ra, g_dev['tel'].current_icrs_dec, \
                                    g_dev['tel'].current_sidereal)
            print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            g_dev['mnt'].go_coord(focus_star[1][1], focus_star[1][0])
            req = {'time': 5,  'alias':  str(self.config['camera']['camera1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'size': 100, 'count': 1, 'filter': 'W'}
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': 10,  'alias':  str(self.config['camera']['camera1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'size': 100, 'count': 1, 'filter': 'W'}
        foc_pos0 = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron

        print('Autofocus Starting at:  ', foc_pos0, '\n\n')
        throw = 100  # NB again, from config.  Units are microns
        result = g_dev['cam'].expose_command(req, opt)
        spot1 = result['FWHM']
        foc_pos1 = result['mean_focus']
        print('Autofocus Moving In.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 - throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        result = g_dev['cam'].expose_command(req, opt)
        spot2 = result['FWHM']
        foc_pos2 = result['mean_focus']
        print('Autofocus Overtaveling Out.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)   #It is important to overshoot to overcome any backlash
        print('Autofocus Moving back in half-way.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        result = g_dev['cam'].expose_command(req, opt)
        spot3 = result['FWHM']
        foc_pos3 = result['mean_focus']
        x = [foc_pos1, foc_pos2, foc_pos3]
        y = [spot1, spot2, spot3]
        print('X, Y:  ', x, y)
        #Digits are to help out pdb commands!
        a1, b1, c1, d1 = fit_quadratic(x, y)
        new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
        if x.min() <= d1 <= x.max:
            print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
            g_dev['foc'].focuser.Move(int(d1)*g_dev['foc'].micron_to_steps)
            result = g_dev['cam'].expose_command(req, opt, halt=True)
            spot4 = result['FWHM']
            foc_pos4 = result['mean_focus']
            print('\n\n\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n\n\n')
        else:
            print('Autofocus did not converge. Moving back to starting focus:  ', focus_start)
            g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
        g_dev['mnt'].SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        #  NB here we could re-solve with the overlay spot just to verify solution is sane.
        self.sequencer_hold = False   #Allow comand checks.
        self.guard = False
        return

    def focus_fine_script(self, req, opt):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
        a verify.
        Auto focus consists of three points plus a verify.
        Fine focus consists of five points plus a verify.
        Optionally individual images can be multiples of one to average out seeing.
        NBNBNB This code needs to go to known stars to be moe relaible and permit subframes
        '''
        print('AF entered with:  ', req, opt)
        self.guard = True
        #self.sequencer_hold = True  #Blocks command checks.
        start_ra = g_dev['mnt'].RightAscension
        start_dec = g_dev['mnt'].Declination
        if req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters
            #  Go to closest Mag 7.5 Tycho * with no flip
            focus_star = tycho.dist_sort_targets(g_dev['tel'].current_icrs_ra, g_dev['tel'].current_icrs_dec, \
                                    g_dev['tel'].current_sidereal)
            print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            g_dev['mnt'].go_coord(focus_star[1][1], focus_star[1][0])
            req = {'time': 5,  'alias':  str(self.config['camera']['camera1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'size': 100, 'count': 1, 'filter': 'W'}
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': 10,  'alias':  str(self.config['camera']['camera1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'size': 100, 'count': 1, 'filter': 'W'}
        foc_pos0 = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        print('Autofocus Starting at:  ', foc_pos0, '\n\n')
        throw = 75  # NB again, from config.  Units are microns
        result = g_dev['cam'].expose_command(req, opt)
        spot1 = result['FWHM']
        foc_pos1 = result['mean_focus']
        g_dev['foc'].focuser.Move((foc_pos0 - throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        result = g_dev['cam'].expose_command(req, opt)
        spot2 = result['FWHM']
        foc_pos2 = result['mean_focus']
        g_dev['foc'].focuser.Move((foc_pos0 - 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        result = g_dev['cam'].expose_command(req, opt)
        spot3 = result['FWHM']
        foc_pos3 = result['mean_focus']
        g_dev['foc'].focuser.Move((foc_pos0 + 5*throw)*g_dev['foc'].micron_to_steps)   #It is important to overshoot to overcome any backlash
        g_dev['foc'].focuser.Move((foc_pos0 - 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        result = g_dev['cam'].expose_command(req, opt)
        spot4 = result['FWHM']
        foc_pos4 = result['mean_focus']
        g_dev['foc'].focuser.Move((foc_pos0 - throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        result = g_dev['cam'].expose_command(req, opt)
        spot5 = result['FWHM']
        foc_pos5 = result['mean_focus']
        x = [foc_pos1, foc_pos2, foc_pos3, foc_pos4, foc_pos5]
        y = [spot1, spot2, spot3, spot4, spot5]
        print('X, Y:  ', x, y)
        #Digits are to help out pdb commands!
        a1, b1, c1, d1 = fit_quadratic(x, y)
        new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
        if x.min() <= d1 <= x.max:
            print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
            g_dev['foc'].focuser.Move(int(d1)*g_dev['foc'].micron_to_steps)
            result = g_dev['cam'].expose_command(req, opt, halt=True)
            spot4 = result['FWHM']
            foc_pos4 = result['mean_focus']
            print('\n\n\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n\n\n')
        else:
            print('Autofocus did not converge. Moving back to starting focus:  ', foc_pos0)
            g_dev['foc'].focuser.Move((foc_pos0)*g_dev['foc'].micron_to_steps)
        g_dev['mnt'].SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        #  NB here we coudld re-solve with the overlay spot just to verify solution is sane.
        self.sequencer_hold = False   #Allow comand checks.
        self.guard = False


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
IF sweep
        '''
        self.guard = True
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
            target_dec = 0
                #  Go to closest Mag 7.5 Tycho * with no flip
            focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
                               g_dev['mnt'].mount.SiderealTime)
            if focus_star is None:
                print("No near star, skipping.")   #This should not happen.
                continue
            print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            req = {'ra':  focus_star[1][1],
                   'dec': focus_star[1][0]     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].enclosure.Slewing:
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(3)
            g_dev['obs'].update_status()
            # req = {'time': 10,  'alias': cam_name, 'image_type': 'Light Frame'}
            # opt = {'size': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator pointing run.'}
            # result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated'
            print('Result:  ', result)
        g_dev['mnt'].stop_command()
        print("Equatorial sweep completed. Happy reducing.")
        self.guard = False
        return
 
    def sky_grid_pointing_run(self, reg, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
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
IF sweep
        '''
        self.guard = True
        print("Starting sky sweep.")
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera1']['name'])
        breakpoint()
        sid = g_dev['mnt'].mount.SiderealTime
        grid_stars = tycho.az_sort_targets(sid, 35, sid)
        #last_az = 0.01
        for grid_star in grid_stars:
            breakpoint()
            if grid_star is None:
                print("No near star, skipping.")   #This should not happen.
                continue
            print("Going to near grid star " + str(grid_star[0]) + "  degrees away.")
            req = {'ra':  grid_star[1][1],
                   'dec': grid_star[1][0]     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].enclosure.Slewing:
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(3)
            g_dev['obs'].update_status()
            # req = {'time': 10,  'alias': cam_name, 'image_type': 'Light Frame'}
            # opt = {'size': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator pointing run.'}
            # result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated'
            print('Result:  ', result)
        g_dev['mnt'].stop_command()
        print("Equatorial sweep completed. Happy reducing.")
        self.guard = False
        return       
        
        # #Grid 
        
        # for dec in np.arange(-30,85,9.583):
        #     for ha in np.arange(-6, 6, 9.583/15):
        # pass






