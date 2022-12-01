import time
import datetime
from datetime import timedelta
import copy
from global_yard import g_dev
import ephem
import build_tycho as tycho
import shelve
import redis
import math
import shutil
import numpy as np
import os
from glob import glob
import traceback
from ptr_utility import plog
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


def fit_quadratic(x, y):
    #From Meeus, works fine.
    #Abscissa arguments do not need to be ordered for this to work.
    #NB Single alpha variable names confict with debugger commands, so bad practce.
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
        plog('Quad;  ', a, b, c)
        try:
            return (a, b, c, -b/(2*a))
        except:
            return (a, b, c)
    else:
        plog("Unbalanced coordinate pairs suppied to fit_quadratic()")
        return None

def bin_to_string(use_bin):
    if use_bin == 1:
        return '1, 1'
    if use_bin == 2:
        return '2, 2'
    if use_bin == 3:
        return '3, 3'
    if use_bin == 4:
        return '4, 4'
    if use_bin == 5:
        return'5, 5'
    else:
        return '1, 1'

def ra_fix(ra):
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra +=24
    return ra

def ra_dec_fix_hd(ra, dec):
    if dec > 90:
        dec = 180 - dec
        ra -= 12
    if dec < -90:
        dec = -180 - dec
        ra += 12
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra += 24
    return ra, dec

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
        plog("sequencer connected.")
        #plog(self.description)
        redis_ip = config['redis_ip']

        if redis_ip is not None:
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
        else:
            self.redis_wx_enabled = False
        self.sky_guard = False
        self.af_guard = False
        self.block_guard = False
        self.time_of_next_slew = time.time()
        #NB NB These should be set up from config once a day at Noon/Startup time
        self.bias_dark_latch = True   #NB NB NB Should these initially be defined this way?
        self.sky_flat_latch = True
        self.morn_sky_flat_latch = True
        self.morn_bias_dark_latch = True   #NB NB NB Should these initially be defined this way?
        self.night_focus_ready=True

        self.reset_completes()  # NB NB Note this is reset each time sequencer is restarted.

        try:
            self.is_in_completes(None)
        except:
            self.reset_completes()


    def get_status(self):
        status = {
            "active_script": None,
            "sequencer_busy":  False
        }
        #20211026   I think this is causing problems.   WER
        # if not self.sequencer_hold:   #  NB THis should be wrapped in a timeout.
        #     if g_dev['obs'].status_count > 3:   #Gove syste time to settle.
        #         self.manager()      #  There be dragons here!  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status


    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        g_dev['cam'].user_id = command['user_id']
        g_dev['cam'].user_name = command['user_name']
        action = command['action']
        script = command['required_params']['script']
        if action == "run" and script == 'focusAuto':
            self.auto_focus_script(req, opt)
        elif action == "autofocus": # this action is the front button on Camera, so FORCES an autofocus
            g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                days=1
            )  # Initialise last focus as yesterday
            self.auto_focus_script(req, opt)
        elif action == "run" and script == 'focusFine':
            self.coarse_focus_script(req, opt)
        elif action == "run" and script == 'genScreenFlatMasters':
            self.screen_flat_script(req, opt)
        elif action == "run" and script == 'genSkyFlatMasters':
            self.sky_flat_script(req, opt)
        elif action == "run" and script in ['32TargetPointingRun', 'pointingRun', 'makeModel']:
            if req['gridType'] == 'sweep':
               self.equatorial_pointing_run(req, opt)
            elif req['gridType'] == 'cross':
                self.cross_pointing_run(req, opt)
            else:
                self.sky_grid_pointing_run(req, opt)
        elif action == "run" and script in ("genBiasDarkMaster", "genBiasDarkMasters"):
            self.bias_dark_script(req, opt, morn=True)
        elif action == "run" and script == 'takeLRGBStack':
            self.take_lrgb_stack(req, opt)
        elif action == "run" and script == "takeO3HaS2N2Stack":
            self.take_lrgb_stack(req, opt)
        elif action.lower() in ["stop", "cancel"]:
            self.stop_command(req, opt)
        elif action == "home":
            #breakpoint()
            self.home_command(req, opt)
        elif action == 'run' and script == 'findFieldCenter':
            g_dev['mnt'].go_command(req, opt, calibrate=True, auto_center=True)
        elif action == 'run' and script == 'calibrateAtFieldCenter':
            g_dev['mnt'].go_command(req, opt, calibrate=True, auto_center=False)
        else:
            plog('Sequencer command:  ', command, ' not recognized.')

    def enc_to_skyflat_and_open(self ,enc_status, ocn_status, no_sky=False):
        #ocn_status = eval(self.redis_server.get('ocn_status'))
           #NB 120 is enough time to telescope to get pointed to East
        self.time_of_next_slew = time.time() -1  #Set up so next block executes if unparked.
        if g_dev['mnt'].mount.AtParK:
            g_dev['mnt'].unpark_command({}, {}) # Get there early
            time.sleep(3)
            self.time_of_next_slew = time.time() + 120   #NB 120 is enough time to telescope to get pointed to East
            if not no_sky:
                g_dev['mnt'].slewToSkyFlatAsync()
                #This should run once. Next time this phase is entered in > 120 seconds we
            #flat_spot, flat_alt = g_dev['evnt'].flat_spot_now()


        if time.time() >= self.time_of_next_slew:
            #We slew to anti-solar Az and reissue this command every 120 seconds
            flat_spot, flat_alt = g_dev['evnt'].flat_spot_now()
            try:
                if not no_sky:
                    g_dev['mnt'].slewToSkyFlatAsync()
                    time.sleep(10)
                plog("Open and slew Dome to azimuth opposite the Sun:  ", round(flat_spot, 1))

                if enc_status['shutter_status'] in ['Closed', 'closed'] and g_dev['enc'].mode == 'Automatic' \
                    and ocn_status['hold_duration'] <= 0.1:   #NB
                    #breakpoint()
                    g_dev['enc'].open_command({}, {})
                    plog("Opening dome, will set Synchronize in 10 seconds.")
                    time.sleep(10)
                g_dev['enc'].sync_mount_command({}, {})
                #Prior to skyflats no dome following.
                self.dome_homed = False
                self.time_of_next_slew = time.time() + 60  # seconds between slews.
            except:
                pass#
        return

    def park_and_close(self, enc_status):
        try:
            if not g_dev['mnt'].mount.AtParK:   ###Test comment here
                g_dev['mnt'].park_command({}, {}) # Get there early
        except:
            plog("Park not executed during Park and Close" )
        try:
            if enc_status['shutter_status'] in ['open', ] and g_dev['enc'].mode == 'Automatic':
                g_dev['enc'].close_command( {}, {})
        except:
            plog('Dome close not executed during Park and Close.')



    ###############################
    #       Sequencer Commands and Scripts
    ###############################
    def manager(self):
        '''
        This is called by the update loop.   Call from local status probe was removed
        #on 20211026 WER

        This is where scripts are automagically started.  Be careful what you put in here if it is
        going to open the dome or move the telescope at unexpected times.

        Scripts must not block too long or they must provide for periodic calls to check status.
        '''

        # NB Need a better way to get all the events.
        if g_dev['obs'].status_count < 3:
            return
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        #just to be safe:  Should fix Line 344 Exception.
        g_dev['ocn'].status = g_dev['ocn'].get_status()
        g_dev['enc'].status = g_dev['enc'].get_status()
        ocn_status = g_dev['ocn'].status
        enc_status = g_dev['enc'].status
        events = g_dev['events']

        g_dev['enc'].mode = 'Automatic'     #  THis is a very common debug point.

        if self.bias_dark_latch and ((events['Eve Bias Dark'] <= ephem_now < events['End Eve Bias Dark']) and \
             self.config['auto_eve_bias_dark'] and g_dev['enc'].mode in ['Automatic', 'Autonomous', 'Manual'] ):
            self.bias_dark_latch = False
            req = {'bin1': False, 'bin2': True, 'bin3': False, 'bin4': False, 'numOfBias': 45, \
                   'numOfDark': 15, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 360, \
                   'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }
            opt = {}
            #No action needed on  the enclosure at this level
            self.park_and_close(enc_status)
            #NB The above put dome closed and telescope at Park, Which is where it should have been upon entry.
            self.bias_dark_script(req, opt, morn=False)
            self.bias_dark_latch = False

        elif ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Eve Sky Flats']) and \
               g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold:

            self.enc_to_skyflat_and_open(enc_status, ocn_status)
            self.night_focus_ready=True

        elif ((g_dev['events']['Clock & Auto Focus']  <= ephem_now < g_dev['events']['Observing Begins']) and \
               g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold:

            if self.night_focus_ready==True:
                g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')

                # Move to reasonable spot
                g_dev['mnt'].mount.Tracking = True

                g_dev['mnt'].move_to_altaz(90, 70)
                g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                    days=1
                )  # Initialise last focus as yesterday

                # Autofocus
                req2 = {'target': 'near_tycho_star', 'area': 150}
                opt = {}
                self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)

                # Pointing
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
                opt = {'area': 150, 'count': 1, 'bin': 'default', 'filter': 'focus'}
                result = g_dev['cam'].expose_command(req, opt, no_AWS=False, solve_it=True)
            self.night_focus_ready=False

        elif self.sky_flat_latch and ((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
               and g_dev['enc'].mode in [ 'Automatic', 'Autonomous'] and not g_dev['ocn'].wx_hold and \
               self.config['auto_eve_sky_flat']):

            self.enc_to_skyflat_and_open(enc_status, ocn_status)   #Just in case a Wx hold stopped opening
            self.current_script = "Eve Sky Flat script starting"
            #plog('Skipping Eve Sky Flats')
            self.sky_flat_script({}, {}, morn=False)   #Null command dictionaries
            self.sky_flat_latch = False
            g_dev['mnt'].mount.Tracking = True

# =============================================================================
#         NB NB Note below often faults, should be in a try except instead of this
#         complex nested if construct.  Enc_status can be None if Wema is not  operating.
#         Perhaps we should default set enc_status['enclosure_mode'] = 'Shutdown' as a default?
# =============================================================================
        elif (events['Observing Begins'] <= ephem_now \
                                   < events['Observing Ends']) and not g_dev['ocn'].wx_hold \
                                   and  g_dev['obs'].blocks is not None and g_dev['obs'].projects \
                                   is not None:
            try:
                
                if enc_status['enclosure_mode'] in ['Autonomous!', 'Automatic']:
                    blocks = g_dev['obs'].blocks
                    projects = g_dev['obs'].projects
                    debug = False
        
                    if self.config['site_roof_control'] != 'no' and  enc_status['shutter_status'] in ['Closed', 'closed'] \
                        and float(ocn_status['hold_duration']) <= 0.1:
                        #breakpoint()
                        g_dev['enc'].open_command({}, {})
                        plog("Opening dome, will set Synchronize in 10 seconds.")
                        time.sleep(10)
                    g_dev['enc'].sync_mount_command({}, {})
        
                    if debug:
                        plog("# of Blocks, projects:  ", len(g_dev['obs'].blocks),  len(g_dev['obs'].projects))
        
                    #Note here we could evaluate projects to see which meet observability constraints and place them
                    #In an observables list, then we could pick one to start.  IF there is no pre-sheduled observing block
                    #it would just run.  Voila an Opportunistic scheduler.  An observing block may be empty or point to
                    #a project and if the project is runnable any way, it runs or is marked completed.
                    # NB without deepcopy decrementing counts in blocks will be local to the machine an subject
                    # to over_write as the respons from AWS updates. This is particularly important for owner
                    # and background blocks.
        
                    #First, sort blocks to be in ascending order, just to promote clarity. Remove expired projects.
                    for block in blocks:  #  This merges project spec into the blocks.
                        for project in projects:
        
                            try:
                                if block['project_id'] == project['project_name'] + '#' + project['created_at']:
                                    block['project'] = project
                            except:
                                block['project'] = None  #nb nb nb 20220920   this faults with 'string indices must be integers". WER
        
                                #plog('Scheduled so removing:  ', project['project_name'])
                                #projects.remove(project)
        
                    #The residual in projects can be treated as background.
                    #plog('Background:  ', len(projects), '\n\n', projects)
        
        
                    #house = []
                    for project in projects:
                        if block['project_id']  != 'none':
                            try:
        
                                if block['project_id'] == project['project_name'] + '#' + project['created_at']:
                                    block['project'] = project
                            except:
                                block['project'] = None
                        else:
                            pass
                        #plog("Reservation asserting at this time.   ", )
                    '''
                    evaluate supplied projects for observable and mark as same. Discard
                    unobservable projects.  Projects may be "site" projects or 'ptr' (network wide:
                    All, Owner, PTR-network, North, South.)
                        The westernmost project is offered to run unless there is a runnable scheduled block.
                        for any given time, are the constraints met? Airmass < x, Moon Phaze < y, moon dist > z,
                        flip rules
        
                    '''
                    # breakpoint()
                    # #Figure out which are observable.  Currently only supports one target/proj
                    # NB Observing events without a project are "observable."
                    # observable = []
                    # for projects in projects:
                    #     ra = projects['project_targets']['ra']
                    #     dec = projects['project_targets']['dec']
                    #     sid = g_dev['mnt'].mount.SiderealTime
                    #     ha = tycho.reduceHA(sid - ra)
                    #     az, alt = transform_haDec_to_azAlt(ha, dec)
                    #     # Do not start a block within 15 min of end time???
                    #plog("Initial length:  ", len(blocks))

                    for block in blocks:
                        now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                        if not self.block_guard \
                            and (block['start'] <= now_date_timeZ < block['end']) \
                            and not self.is_in_completes(block['event_id']):
                            if block['project_id'] in ['none', 'real_time_slot', 'real_time_block']:
                                self.block_guard = False   # Changed from True WER on 20221011@2:24 UTC
                                return   # Do not try to execute an empty block.
                            self.block_guard = True
        
                            if block['project'] == None:
                                print (block)
                                print ("Skipping a block that contains an empty project")
                                return
        
        
                            completed_block = self.execute_block(block)  #In this we need to ultimately watch for weather holds.
                            self.append_completes(completed_block['event_id'])
                            #block['project_id'] in ['none', 'real_time_slot', 'real_time_block']
                            '''
                            When a scheduled block is completed it is not re-entered or the block needs to
                            be restored.  IN the execute block we need to make a deepcopy of the input block
                            so it does not get modified.
                            '''
                    #plog('block list exhausted')
                    #return  Commented out 20220409 WER
        
        
                        # plog("Here we would enter an observing block:  ",
                        #       block)
                        # breakpoint()
                    #OK here we go to a generalized block execution routine that runs
                    #until exhaustion of the observing window.
                    # else:
                    #     pass
                    #plog("Block tested for observatility")
        
                # #System hangs on this state
                # elif ((g_dev['events']['Observing Ends']  < ephem_now < g_dev['events']['End Morn Sky Flats']) and \
                #        g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold and self.config['auto_morn_sky_flat']:
                #     self.enc_to_skyflat_and_open(enc_status, ocn_status)
            except:
                 plog("Hang up in sequencer.")
        elif self.morn_sky_flat_latch and ((events['Morn Sky Flats'] <= ephem_now < events['End Morn Sky Flats'])  \
               and g_dev['enc'].mode == 'Automatic' and not g_dev['ocn'].wx_hold and \
               self.config['auto_morn_sky_flat']):
            self.enc_to_skyflat_and_open(enc_status, ocn_status)   #Just in case a Wx hold stopped opening
            self.current_script = "Morn Sky Flat script starting"
            #self.morn_sky_flat_latch = False
            #plog('Skipping Eve Sky Flats')
            self.sky_flat_script({}, {}, morn=True)   #Null command dictionaries
            self.morn_sky_flat_latch = False
            #self.park_and_close(enc_status)
        elif self.morn_bias_dark_latch and (events['Morn Bias Dark'] <= ephem_now < events['End Morn Bias Dark']) and \
                  self.config['auto_morn_bias_dark']: # and g_dev['enc'].mode == 'Automatic' ):
            #breakpoint()
            self.morn_bias_dark_latch = False
            req = {'bin1': False, 'bin2': True, 'bin3': False, 'bin4': False, 'numOfBias': 45, \
                    'numOfDark': 15, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 360, \
                    'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }
            opt = {}
            #No action needed on  the enclosure at this level
            self.park_and_close(enc_status)
            #NB The above put dome closed and telescope at Park, Which is where it should have been upon entry.
            self.bias_dark_script(req, opt, morn=True)

            self.park_and_close(enc_status)
            self.morn_bias_dark_latch = True
        else:
            self.current_script = "No current script, or site not in Automatic."
            try:
                pass
                #self.park_and_close(enc_status)
            except:
                plog("Park and close failed at end of sequencer loop.")
        return
    def take_lrgb_stack(self, req_None, opt=None):
        return
    def take_wugriz_stack(self, req_None, opt=None):
        return
    def take_UBRI_stack(self, req_None, opt=None):
        return
    def take_RGB_stack(self, req_None, opt=None):
        return
    def create_OSC_raw_image(self, req_None, opt=None):
        return
#    self.redis_server.set('sim_hold', True, ex=120)

    def clock_the_system(self, other_side=False):
        '''

        This routine carefully starts up the telescope and verifies the telescope is
        properly reporting correct coordiates and the dome is correctly positioning.
        Once a star field is returned, the system solves and synchs the telescope and
        dome if necessary.  Next a detailed autofocus is performed on a Tycho star of
        known mag and position.  The final reading from the autofocus is used for one
        last clocking.

        other_side = True causes the telescope to then flip and repeat the process.
        From differences in the solutions, flip_shift offsets can be calculated.

        If this routine does not solve, the night is potentially lost so an alert
        messagge should be sent to the owner and telops, the enclosure closed and
        left in manual, the telescope parked and instruments are put to bed.

        This routing is designed to begin when the altitude of the Sun is -9 degrees.
        The target azimuth will change so the Moon is always 15 or more degrees away.

        If called in the Morning and the routing fails, the system is still put to
        bed but a less urgent message is sent to the owner and telops.

        Returns
        -------
        None.

        '''

        '''
        if dome is closed: simulate
        if not simulate, check sun is down
                         check dome is open

        go to 90 az 60 alt then near tycho star
        Image and look for stars (or load simulated frames)

        If stars not present:
            slew dome right-left increasing to find stars
        if +/- 90 az change in dome does not work then
        things are very wrong -- close down and email list.

        if stars present, then autofocus with wide tolerance
        if after 5 tries no luck -- close down and email list.

        if good autofocus then last frame is the check frame.

        Try to astrometrically solve it.  if it solves, synch the
        telescope.  Wait for dome to get in position and

        Take second image, solve and synch again.

        If tel motion > 1 amin, do one last time.

        Look at dome Az -- is dome following the telescope?
        Report if necessary

        return control.

        '''

    def execute_block(self, block_specification):
        #ocn_status = eval(self.redis_server.get('ocn_status'))
        #enc_status = eval(self.redis_server.get('enc_status'))
        plog('|n|n Staring a new project!  \n')
        plog(block_specification, ' \n\n\n')

        self.block_guard = True
        # NB we assume the dome is open and already slaving.
        block = copy.deepcopy(block_specification)
        ocn_status = g_dev['ocn'].status
        enc_status = g_dev['enc'].status
        # #unpark, open dome etc.
        # #if not end of block
        # if not enc_status in ['open', 'Open', 'opening', 'Opening']:
        #     self.enc_to_skyflat_and_open(enc_status, ocn_status, no_sky=True)   #Just in case a Wx hold stopped opening
        # else:
        #g_dev['enc'].sync_mount_command({}, {})
        g_dev['mnt'].unpark_command({}, {})
        g_dev['mnt'].Tracking = True   # unpark_command({}, {})
        g_dev['cam'].user_name = 'tobor'
        g_dev['cam'].user_id = 'tobor'
        #NB  Servo the Dome??
        timer = time.time() - 1  #This should force an immediate autofocus.
        req2 = {'target': 'near_tycho_star', 'area': 150}
        opt = {}
        t = 0
        '''
        # to do is Targets*Mosaic*(sum of filters * count)

        Assume for now we only have one target and no mosaic factor.
        The the first thing to do is figure out how many exposures
        in the series.  If enhance AF is true they need to be injected
        at some point, but it does not decrement. This is still left to do
        '''


        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            try:
                #breakpoint()
                dest_ra = float(target['ra']) - \
                    float(block_specification['project']['project_constraints']['ra_offset'])/15.

                dest_dec = float(target['dec']) - float(block_specification['project']['project_constraints']['dec_offset'])
                dest_ra, dest_dec = ra_dec_fix_hd(dest_ra, dest_dec)
                dest_name =target['name']

                g_dev['cam'].user_name = block_specification['creator']
                g_dev['cam'].user_id = block_specification['creator_id']
                #breakpoint()
                if ('longstack' in block_specification['project']) == False:
                    longstackswitch='no'
                    longstackname='no'
                elif block_specification['project']['longstack'] == True:
                    longstackswitch='yes'
                    longstackname=block_specification['project']['created_at'].replace('-','').replace(':','')
                else:
                    longstackswitch='no'
                    longstackname='no'
                if ('smartstack' in block_specification['project']) == False:
                    smartstackswitch='no'
                elif block_specification['project']['smartstack'] == True:
                    smartstackswitch='yes'
                else:
                    smartstackswitch='no'

            except Exception as e:                
                print ("Could not execute project due to poorly formatted or corrupt project")
                print (e)
                g_dev['obs'].send_to_user("Could not execute project due to poorly formatted or corrupt project", p_level='INFO')
                continue

            if enc_status['shutter_status'] in ['Closed', 'closed'] and ocn_status['hold_duration'] <= 0.1:   #NB  # \  NB NB 20220901 WER fix this!

                #breakpoint()
                g_dev['enc'].open_command({}, {})
                plog("Opening dome, will set Synchronize in 10 seconds.")
                time.sleep(10)
            g_dev['enc'].sync_mount_command({}, {})

            '''
            We be starting a block:
            Open dome if alt Sun < 5 degrees
            Unpark telescope
            Slave the Dome
            Go to Az of the target and take a 15 second W  Square
            exposure -- better go to a tycho star near
            the aimpoint at Alt ~30-35  Take an exposure, try to solve
            an possibly synch.  But be above any horizon
            effects.

            THen autofocus, then finally go to the object
            whihc could be below Alt of 30.
            all of aboe for first of night then at start of a block
            do the square target check, then AF, then block, depending
            on AF more Frequently setting.

            Consider a target check and even synch after a flip.


            '''
            try:
                g_dev['mnt'].get_mount_coordinates()
            except:
                pass
            g_dev['mnt'].go_coord(dest_ra, dest_dec)

            plog("CAUTION:  rotator may block")
            pa = float(block_specification['project']['project_constraints']['position_angle'])
            if abs(pa) > 0.01:
                try:

                    g_dev['rot'].rotator.MoveAbsolute(pa)   #Skip rotator move if nominally 0
                except:
                    pass


            #Compute how many to do.
            left_to_do = 0
            ended = False
            #  NB NB NB Any mosaic larger than +SQ should be specified in degrees and be square
            #  NB NB NB NB this is the source of a big error$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$!!!! WER 20220814
            for exposure in block['project']['exposures']:
                multiplex = 0
                if exposure['area'] in ['300', '300%', 300, '220', '220%', 220, '150', '150%', 150, '250', '250%', 250]:
                    if block_specification['project']['project_constraints']['add_center_to_mosaic']:
                        multiplex = 5
                    else:
                        multiplex = 4
                if exposure['area'] in ['600', '600%', 600, '450', '450%', 450]:
                    multiplex = 16
                if exposure['area'] in ['500', '500%', 500]:
                    if block_specification['project']['project_constraints']['add_center_to_mosaic']:
                        multiplex = 7
                    else:
                        multiplex = 6
                if exposure['area'] in ['+SQ', '133%']:
                    multiplex = 2
                if multiplex > 1:
                    left_to_do += int(exposure['count'])*multiplex
                    exposure['count'] = int(exposure['count'])*multiplex  #Do not multiply the count string value as a dict entry!
                    plog('# of mosaic panes:  ', multiplex)
                else:
                    left_to_do += int(exposure['count'])
                    plog('Singleton image')

            plog("Left to do initial value:  ", left_to_do)
            req = {'target': 'near_tycho_star'}
            #initial_focus = True

            while left_to_do > 0 and not ended:


                if g_dev["foc"].last_focus_fwhm == None or g_dev["foc"].focus_needed == True:

                    g_dev['obs'].send_to_user("Running an initial autofocus run.")


                    self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)

                    just_focused = True
                    #initial_focus = False    #  Make above on-time event per block
                    g_dev["foc"].focus_needed = False
                    #timer = time.time() + af_delay  # 45 minutes

                # A flag to make sure the first image after a slew in an exposure set is solved, but then onto the normal solve timer
                reset_solve = True


                #cycle through exposures decrementing counts    MAY want to double check left-to do but do nut remultiply by 4
                for exposure in block['project']['exposures']:

                    #initial_focus = False
                    just_focused = True
                    #timer = time.time() + af_delay  #40 minutes to refocus

                    print ("Observing " + str(block['project']['project_targets'][0]['name']))

                    plog("Executing: ", exposure, left_to_do)
                    color = exposure['filter']
                    exp_time =  float(exposure['exposure'])




                    if exposure['bin'] == '"optimal"':
                        tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['default_bin'][0])
                        binning = tempBinString + ' ' + tempBinString
                    elif exposure['bin'] == '"maximum"' :
                        tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['maximum_bin'][0])
                        binning = tempBinString + ' ' + tempBinString
                    elif exposure['bin'] in[0, '0', '0,0', '0, 0', '0 0']:
                        tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['default_bin'][0])
                        binning = tempBinString + ' ' + tempBinString
                    elif exposure['bin'] in [2, '2,2', '2, 2', '2 2']:
                        binning = '2 2'
                    elif exposure['bin'] in [3, '3,3', '3, 3', '3 3']:
                        binning = '3 3'
                    elif exposure['bin'] in [4, '4,4', '4, 4', '4 4']:
                        binning = '4 4'
                    else:
                        tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['default_bin'][0])
                        binning = tempBinString + ' ' + tempBinString
                    count = int(exposure['count'])
                    #  We should add a frame repeat count
                    imtype = exposure['imtype']

                    if count <= 0:
                         continue
                    #At this point we have 1 to 9 exposures to make in this filter.  Note different areas can be defined.
                    if exposure['area'] in ['300', '300%', 300, '220', '220%', 220, '150', '150%', 150, ]:  # 4 or 5 expsoures.
                        if block_specification['project']['project_constraints']['add_center_to_mosaic']:
                            offset = [(0.0, 0.0), (-1.5, 1.), (1.5, 1.), (1.5, -1.), (-1.5, -1.)] #Aimpoint + Four mosaic quadrants 36 x 24mm chip
                            pane = 0
                        else:
                            offset = [(-1, 1.), (1, 1.), (1, -1.), (-1, -1.)] #Four mosaic quadrants 36 x 24mm chip
                            pane = 1
                        #Exact details of the expansions need to be calculated for accurate naming. 20201215 WER
                        if exposure['area'] in ['300', '300%', 300]:
                            pitch = 0.3125
                        if exposure['area'] in ['220', '220%', 220]:
                            pitch = 0.25
                        if exposure['area'] in ['150', '150%', 150]:
                            pitch = 0.1875

                    elif exposure['area'] in ['600', '600%', '4x4d', '4x4']:
                        offset = [(0,0), (-1, 0), (-1, 0.9), (-1, 1.8), (0, 1.8), (1, 1.8), (2, 0.9), (1, 0.9), (0, 0.9), \
                                  (2, 0), (1, 0), (1, -0.9), (0, -0.9), (-1, -0.9), (-1, -1.8), (0, -1.8), (1, -1.8)]
                                 #((2, -1,8), (2, -0.9), (2, 1.8))  #  Dead areas for star fill-in.
                        pitch = -1  #A signal to do something special.  ##'600', '600%', 600,
                    elif exposure['area'] in ['2x2', '500%']:
                        offset= [(0,0), (-0.5, 0), (-0.5, .35), (0.5, 0.35), (0.5, 0), (-0.5, -0.35), (0.5, -0.35), ]
                        pitch = 1
                    elif exposure['area'] in ['450', '450%', 450]:
                        pitch = 0.250
                        pane = 0
                    # elif exposure['area'] in ['500', '500%',]:  # 6 or 7 exposures.  SQUARE
                    #     step = 1.466667
                    #     if block_specification['project']['project_constraints']['add_center_to_mosaic']:
                    #         offset = [(0., 0.), (-1, 0.), (-1, step), (1, step), (1, 0), \
                    #                   (1, -step), (-1, -step)] #Aimpoint + six mosaic quadrants 36 x 24mm chip
                    #         pane = 0
                    #     else:
                    #         offset = [(-1, 0.), (-1, step),  (1, step), (1, 0), \
                    #                   (1, -step), (-1, -step)] #Six mosaic quadrants 36 x 24mm chip
                    #         pane = 1
                    #     pitch = .375
                    elif exposure['area'] in ['+SQ', '133%']:  # 2 exposures.  SQUARE
                        #step = 1
                        offset = [(0, -1), (0, 1)] #Two mosaic steps 36 x 24mm chip  Square
                        pane = 1
                        pitch = 0.25#*2   #Try this out for small overlap and tall field. 20220218 04:12 WER
                    else:
                        offset = [(0., 0.)] #Zero(no) mosaic offset
                        pitch = 0.
                        pane = 0

                    for displacement in offset:

                        x_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['x_field_deg']
                        y_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['y_field_deg']
                        if pitch == -1:
                            #Note positive offset means a negative displacement in RA for spiral to wrap CCW.
                            #Note offsets are absolute degrees.
                            d_ra = -displacement[0]/15.
                            d_dec = displacement[1]
                        else:
                            d_ra = displacement[0]*(pitch)*(x_field_deg/15.)  # 0.764243 deg = 0.0509496 Hours  These and pixscale should be computed in config.
                            d_dec = displacement[1]*( pitch)*(y_field_deg)  # = 0.5102414999999999   #Deg
                        new_ra = dest_ra + d_ra
                        new_dec= dest_dec + d_dec
                        new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)

                        #if offset != [(0., 0.)]: # only move if you need to move to another position in the mosaic.
                        plog('Seeking to:  ', new_ra, new_dec)
                        g_dev['mnt'].go_coord(new_ra, new_dec, reset_solve=reset_solve)  # This needs full angle checks
                            #time.sleep(5) # Give scope time to settle.
                        reset_solve=False # make sure slews after the first slew do not reset the PW Solve timer.
                        #if not just_focused:
                        #    g_dev['foc'].adjust_focus()
                        just_focused = False
                        if imtype in ['light'] and count > 0:
                            req = {'time': exp_time,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': imtype, 'smartstack' : smartstackswitch, 'longstackswitch' : longstackswitch, 'longstackname' : longstackname, 'block_end' : block['end']}   #  NB Should pick up filter and constants from config
                            opt = {'area': 150, 'count': 1, 'bin': binning, 'filter': color, \
                                   'hint': block['project_id'] + "##" + dest_name, 'object_name': block['project']['project_targets'][0]['name'], 'pane': pane}
                            plog('Seq Blk sent to camera:  ', req, opt)
                            obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

                            now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                            if now_date_timeZ >= block['end'] :
                                break
                            result = g_dev['cam'].expose_command(req, opt, no_AWS=False, solve_it=False)
                            try:
                                if result['stopped'] is True:
                                    g_dev['obs'].send_to_user("Project Stopped because Exposure cancelled")
                                    return block_specification
                            except:
                                pass
                            t +=1
                            count -= 1
                            exposure['count'] = count
                            left_to_do -= 1
                            plog("Left to do:  ", left_to_do)
                        pane += 1

                    now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'

                    events = g_dev['events']

                    ended = left_to_do <= 0 or now_date_timeZ >= block['end'] \
                            or ephem.now() >= events['Observing Ends']
                    #                                                    ]\
                    #         or g_dev['airmass'] > float( block_specification['project']['project_constraints']['max_airmass']) \
                    #         or abs(g_dev['ha']) > float(block_specification['project']['project_constraints']['max_ha'])
                    #         # Or mount has flipped, too low, too bright, entering zenith..

        plog("Project block has finished!")   #NB Should we consider turning off mount tracking?
        if block_specification['project']['project_constraints']['close_on_block_completion']:
            #g_dev['mnt'].park_command({}, {})
            # NB NBNeed to write a more robust and generalized clean up.
            try:
                pass#g_dev['enc'].enclosure.Slaved = False   NB with wema no longer exists
            except:
                pass
            #self.redis_server.set('unsync_enc', True, ex=1200)
            #g_dev['enc'].close_command({}, {})
            g_dev['mnt'].park_command({}, {})

            plog("Auto PARK (not Close) attempted at end of block.")
        self.block_guard = False
        return block_specification #used to flush the queue as it completes.


    def bias_dark_script(self, req=None, opt=None, morn=False):
        """

        20200618   This has been drastically simplied for now to deal with only QHY600M.

        May still have a bug where it latches up only outputting 2x2 frames.

        """
        print (morn)
        self.sequencer_hold = True
        self.current_script = 'Bias Dark'
        if morn:
            ending = g_dev['events']['End Morn Bias Dark']
        else:
            ending = g_dev['events']['End Eve Bias Dark']
        while ephem.now() < ending :   #Do not overrun the window end

            g_dev['mnt'].park_command({}, {}) # Get there early

            plog("Expose Biases: by configured binning;  normal and long darks.")

            dark_time = self.config['camera']['camera_1_1']['settings']['ref_dark']
            long_dark_time = self.config['camera']['camera_1_1']['settings']['long_dark']


            for bias in range(9):   #9*(9 +1) per cycle.
                if ephem.now() + 210/86400 > ending:
                    break
                if "1 1" in self.config['camera']['camera_1_1']['settings']['bin_enable']:
                    req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                    opt = {'area': "Full", 'count': 9, 'bin':'1 1', \
                            'filter': 'dark'}
                    plog("Expose b_1")
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                    do_sep=False, quick=False)
                    g_dev['obs'].update_status()
                    dark_time = 360
                    if ephem.now() + (dark_time + 30)/86400 > ending:
                        break
                    plog("Expose ref_dark using exposure:  ", dark_time )
                    req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count':1, 'bin': '1 1', \
                            'filter': 'dark'}
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                        do_sep=False, quick=False)

                    g_dev['obs'].update_status()
                    if long_dark_time is not None and long_dark_time > dark_time:

                        if ephem.now() + (long_dark_time + 30)/86400 > ending:
                            break
                        plog("Expose long dark using exposure:  ", long_dark_time)
                        req = {'time':long_dark_time ,  'script': 'True', 'image_type': 'dark'}
                        opt = {'area': "Full", 'count':1, 'bin': '1 1', \
                                'filter': 'dark'}
                        result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                            do_sep=False, quick=False)

                        g_dev['obs'].update_status()
                if "2 2" in self.config['camera']['camera_1_1']['settings']['bin_enable']:
                    req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                    opt = {'area': "Full", 'count': 9, 'bin':'2 2', \
                            'filter': 'dark'}
                    plog("Expose b_1")
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                    do_sep=False, quick=False)
                    g_dev['obs'].update_status()
                    dark_time = 360
                    if ephem.now() + (dark_time + 30)/86400 > ending:
                        break
                    plog("Expose ref_dark using exposure:  ", dark_time )
                    req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count':1, 'bin': '2 2', \
                            'filter': 'dark'}
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                        do_sep=False, quick=False)

                    g_dev['obs'].update_status()
                    if long_dark_time is not None and long_dark_time > dark_time:

                        if ephem.now() + (long_dark_time + 30)/86400 > ending:
                            break
                        plog("Expose long dark using exposure:  ", long_dark_time)
                        req = {'time':long_dark_time ,  'script': 'True', 'image_type': 'dark'}
                        opt = {'area': "Full", 'count':1, 'bin': '2 2', \
                                'filter': 'dark'}
                        result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                            do_sep=False, quick=False)

                        g_dev['obs'].update_status()

                g_dev['obs'].update_status()
                if ephem.now() + 30/86400 >= ending:
                    break

            plog(" Bias/Dark acquisition is finished normally.")

        self.sequencer_hold = False
        g_dev['mnt'].park_command({}, {}) # Get there early
        plog("Bias/Dark Phase has passed.")


        time.sleep(300) # Wait for telescope to park
        if morn:
            # UNDERTAKING END OF NIGHT ROUTINES

            # Setting runnight for mop up scripts
            yesterday = datetime.datetime.now() - timedelta(1)
            runNight=datetime.datetime.strftime(yesterday, '%Y%m%d')

            # Check the archive directory and upload any big fits that haven't been uploaded
            # wait until the queue is empty before mopping up

            # Go through and add any remaining fz files to the aws queue .... hopefully that is enough? If not, I will make it keep going until it is sure.
            #while True:
            dir_path=self.config['client_path'] + 'archive/'
            cameras=glob(dir_path + "*/")
            print (cameras)
            for camera in cameras:
                bigfzs=glob(camera + "/" + runNight + "/raw/*.fz")

                for fzneglect in bigfzs:
                    print ("Reattempting upload of " + str(os.path.basename(fzneglect)))
                    #breakpoint()
                    #image = (im_path, name)
                    #g_dev["obs"].aws_queue.put((priority, image), block=False)

                    g_dev['cam'].enqueue_for_AWS(26000000, camera + runNight + "/raw/", str(os.path.basename(fzneglect)))
                    #g_dev['obs'].send_to_aws()

            #time.sleep(300)
            #if (g_dev['obs'].aws_queue.empty()):
            #break

            # Sending token to AWS to inform it that all files have been uploaded
            print ("sending end of night token to AWS")
            #g_dev['cam'].enqueue_for_AWS(jpeg_data_size, paths['im_path'], paths['jpeg_name10'])

            isExist = os.path.exists(g_dev['cam'].site_path + 'tokens')
            if not isExist:
                os.makedirs(g_dev['cam'].site_path + 'tokens')
            runNightToken= g_dev['cam'].site_path + 'tokens/' + self.config['site'] + runNight + '.token'
            with open(runNightToken, 'w') as f:
                f.write('Night Completed')
            image = (g_dev['cam'].site_path + 'tokens/', self.config['site'] + runNight + '.token')
            g_dev['obs'].aws_queue.put((30000000000, image), block=False)
            g_dev['obs'].send_to_user("End of Night Token sent to AWS.", p_level='INFO')

            # while True:
            #     if (not g_dev['obs'].aws_queue.empty()):
            #         g_dev['obs'].send_to_AWS()
            #         print ("Emptying AWS queue at the end of the night")
            #         time.sleep(1)
            #     else:
            #         break

            # Culling the archive
            #FORTNIGHT=60*60*24*7*2
            if self.config['archive_age'] > 0 :
                print (self.config['client_path'] + 'archive/')
                dir_path=self.config['client_path'] + 'archive/'
                #cameras=[d for d in os.listdir(dir_path) if os.path.isdir(d)]
                cameras=glob(dir_path + "*/")
                print (cameras)
                for camera in cameras:  # Go through each camera directory
                    print ("*****************************************")
                    print ("Camera: " + str(camera))
                    timenow_cull=time.time()
                    directories=glob(camera + "*/")
                    deleteDirectories=[]
                    deleteTimes=[]
                    for q in range(len(directories)):
                        if ((timenow_cull)-os.path.getmtime(directories[q])) > (self.config['archive_age'] * 24* 60 * 60) :
                            deleteDirectories.append(directories[q])
                            deleteTimes.append(((timenow_cull)-os.path.getmtime(directories[q])) /60/60/24/7)
                    print ("These are the directories earmarked for  ")
                    print ("Eternal destruction. And how old they are")
                    print ("in weeks\n")
                    g_dev['obs'].send_to_user("Culling " + str(len(deleteDirectories)) +" from the local archive.", p_level='INFO')
                    for entry in range(len(deleteDirectories)):
                        print (deleteDirectories[entry] + ' ' + str(deleteTimes[entry]) + ' weeks old.')
                        shutil.rmtree(deleteDirectories[entry])

            # Clear out smartstacks directory
            print ("removing and reconstituting smartstacks directory")
            try:
                shutil.rmtree(g_dev["cam"].site_path + "smartstacks")
            except:
                print ("problems with removing the smartstacks directory... usually a file is open elsewhere")
            time.sleep(20)
            if not os.path.exists(g_dev["cam"].site_path + "smartstacks"):
                os.makedirs(g_dev["cam"].site_path + "smartstacks")




            # Reopening config and resetting all the things.
            self.astro_events.compute_day_directory()
            self.astro_events.display_events(endofnightoverride='yes')
            g_dev['obs'].astro_events = self.astro_events


            # sending this up to AWS
            '''
            Send the config to aws.
            '''
            uri = f"{self.name}/config/"
            self.config['events'] = g_dev['events']
            response = g_dev['obs'].api.authenticated_request("PUT", uri, self.config)
            if response:
                plog("Config uploaded successfully.")

            # If you are using TheSkyX, then update the autosave path
            if self.config['camera']['camera_1_1']['driver'] == "CCDSoft2XAdaptor.ccdsoft5Camera":
                g_dev['cam'].camera.AutoSavePath = self.config['archive_path'] +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d')
                try:
                    os.mkdir(self.config['archive_path'] +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d'))
                except:
                    print ("Couldn't make autosave directory")

            # Resetting complete projects
            print ("Nightly reset of complete projects")
            self.reset_completes()
            g_dev['obs'].blocks = None
            g_dev['obs'].projects = None
            g_dev['obs'].events_new = None
            g_dev['obs'].reset_last_reference()
            if self.config['mount']['mount1']['permissive_mount_reset'] == 'yes':
               g_dev['mnt'].reset_mount_reference()
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000

            # Resetting sequencer stuff
            self.connected = True
            self.description = "Sequencer for script execution."
            self.sequencer_hold = False
            self.sequencer_message = '-'
            plog("sequencer reconnected.")
            plog(self.description)
            self.sky_guard = False
            self.af_guard = False
            self.block_guard = False
            self.time_of_next_slew = time.time()
            self.bias_dark_latch = True
            self.sky_flat_latch = True
            self.morn_sky_flat_latch = True
            self.morn_bias_dark_latch = True
            self.reset_completes()


            # Reset focus tracker
            g_dev["foc"].focus_needed = True
            g_dev["foc"].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                days=1
            )  # Initialise last focus as yesterday
            g_dev["foc"].images_since_last_focus = (
                10000  # Set images since last focus as sillyvalue
            )
            g_dev["foc"].last_focus_fwhm = None
            g_dev["foc"].focus_tracker = [np.nan] * 10

            # Trying to figure out why sequencer isn't restarting.
            events = g_dev['events']
            obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

            # Reopening config and resetting all the things.
            self.astro_events.compute_day_directory()
            self.astro_events.display_events()
            g_dev['obs'].astro_events = self.astro_events

            # Allow early night focus
            self.night_focus_ready==True


        return



    def sky_flat_script(self, req, opt, morn=False):
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

        20220821  New try at this code
        Set up parameters for the site, camera, etc.
        set up 'end-time'.  Calling into this happens elesewhere at the prescribed start time
        Pick forward or reverse filter list depemnding on Eve or Morn flats. -- "the pop-list"
        flat count = 3
        scale = 1, used to drive exposure to ~32500ADU That is the target_flat value
        prior scale = 1  When changing filters apply this scale so we do not wast time.  This
        is intended to fix the problem the gain estimates are wrong.
        while len(pop_list) > 0  and ephem.now() < ending:
            Get the filter, its 'gain'
            go the the solar flat spot  (Tel should be there earlier)
            possibly here if not on flat spot or roof not open:
                time.sleep(10)
                continue the loop

                (Note if SRO roof opens late we are likely behinf the 8-ball and we waste time
                 on the Narrow Band filters.)
            calculate exposure (for S2 filter if Night, PL filter if morning.)
            if evening and exposure > 180 sec sky is too dark for that filter so:
                pop that filter
                flat count = 3
                continue the loop
            if morning and exposure < 1 sec then sky too bright for that filter so:
                pop tht tilter
                flat count = 3
                continue the loop

            Here I think we need another loop that gets the number of flats or pops
            the filter and then continues the above loop.
            Tries = 6   #basically prevent a spin on one filter from eating up the window.
            While flatcount > 0 and tries > 0 and ephem.now() < ending:
                Expose the filter for the computed time.
                Now lets fix the  convoluted code.
                The central patch should ideally be ~= target flat, so
                scale = target_flat/patch, avoiding the obvious divide by zero.  A problem
                here is if Patch is >> 65,000 we only scale exposure by about half. So it makes
                some sense to cut it down more so we converge faster.  (Scaling up seems to work
                on the first pass.)

                if patch is say 30000 <= patch <= 35000, accept the exposure as a valid flat:
                    flatcount -= 1
                    tried =- 1
                    scale = prior_scale*target_flat/patch    #prior _scale is 1.0
                elif outside that range
                    tried =- 1
                    scale = prior_scale*target_flat/patch as adjusted by the above paragraph.

                        Next step is a bit subtle.  if the loop is going to fail because with the flat_count
                        or tries are exceeded we need to set up prior_scale.  The theory is if the session worked
                        perfect we end with an effective scale on 1.  But the sky fades very fast so to do this
                        right we need somthing more like an average-scale.  However for now, keep it simple.
                        So the assumption is is the scale for the s2 filter to expose correctly is 0.9 then
                        the S2 signal is "bright".  So we put that factor into prior scale so when we move to HA
                        the system will bias the first HA exposure assuming it will be bright for that band as well.

                        What I have seen so far is there is variation night to night is the sky transmission in the
                        red bands. Add that to the fast chages is skybrighness after SRO opens and ... challenging.

                        Note in old code I try recomputing the "gain".  Ideally a better way to do this would be to
                        create a persisten gain list of say the last 7 successful nights per filter of course and then
                        seed the above more accurately.

                        Now once we get rid of CCD cameras this becomes a bit easier since min exposure can be 0.0001 sec.
                        But readout time then starts to dominate.  All fine you say but if we have a full wheel of filters
                        then haveing only 35 or so minutes is still limiting.

                        I am going to push this to Git right now so MFitz can comment. Then i will get back to the pseudo code.

        """

        self.sky_guard = True   #20220409 I think this is obsolete or unused.
        plog('Sky Flat sequence Starting, Enclosure PRESUMED Open. Telescope should be on sky flat spot.')

        g_dev['obs'].send_to_user('Sky Flat sequence Starting, Enclosure PRESUMED Open. Telescope should be on sky flat spot.', p_level='INFO')
        evening = not morn
        camera_name = str(self.config['camera']['camera_1_1']['name'])
        flat_count = 5
        min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_exposure'])
        bin_spec = '1,1'
        try:
            bin_spec = self.config['camera']['camera_1_1']['settings']['flat_bin_spec']
        except:
            pass
        exp_time = min_exposure # added 20220207 WER  0.2 sec for SRO


        #  Pick up list of filters is sky flat order of lowest to highest transparency.
        pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort'].copy()

        if morn:
            pop_list.reverse()
            plog('filters by high to low transmission:  ', pop_list)
            ending = g_dev['events']['End Morn Sky Flats']
        else:
            plog('filters by low to high transmission:  ', pop_list)
            ending = g_dev['events']['End Eve Sky Flats']
        #length = len(pop_list)
        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        exp_time = 0
        scale = 1.0
        prior_scale = 1   #THIS will be inhereted upon completion of the prior filter
        collecting_area = self.config['telescope']['telescope1']['collecting_area']/31808.   # SAF at F4.9 is the reference
        #   and (g_dev['events']['Eve Sky Flats'] <

        while len(pop_list) > 0  and ephem.now() < ending:

            current_filter = int(pop_list[0])
            acquired_count = 0
            g_dev['fil'].set_number_command(current_filter)  #  20220825  NB NB NB Change this to using a list of filter names.
            g_dev['mnt'].slewToSkyFlatAsync()
            target_flat = 30000

            # if not g_dev['enc'].status['shutter_status'] in ['Open', 'open']:
            #     g_dev['obs'].send_to_user("Wait for roof to be open to take skyflats. 60 sec delay loop.", p_level='INFO')
            #     time.sleep(60)
            #     g_dev['obs'].update_status()
            #     continue
            while (acquired_count < flat_count):# and g_dev['enc'].status['shutter_status'] in ['Open', 'open']: # NB NB NB and roof is OPEN! and (ephem_now +3/1440) < g_dev['events']['End Eve Sky Flats' ]:
                #if g_dev['enc'].is_dome:   #Does not apply
                g_dev['mnt'].slewToSkyFlatAsync()  #FRequently do this to dither.
                g_dev['obs'].update_status()

                try:
                    try:
                        sky_lux = eval(self.redis_server.get('ocn_status'))['calc_HSI_lux']     #Why Eval, whould have float?
                    except:
                        #plog("Redis not running. lux set to 1000.")
                        sky_lux = float(g_dev['ocn'].status['calc_HSI_lux'])

                    exp_time = prior_scale*scale*target_flat/(collecting_area*sky_lux*float(g_dev['fil'].filter_data[current_filter][3]))  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                    plog('Ex:  ', exp_time, scale, prior_scale, sky_lux, float(g_dev['fil'].filter_data[current_filter][3]))

                    if evening and exp_time > 120:
                        #exp_time = 60    #Live with this limit.  Basically started too late
                        plog('Break because proposed evening exposure > 180 seconds:  ', exp_time)
                        g_dev['obs'].send_to_user('Try next filter because proposed  flat exposure > 180 seconds.', p_level='INFO')
                        pop_list.pop(0)
                        break
                    if morn and exp_time < min_exposure:
                        #exp_time = 60    #Live with this limit.  Basically started too late
                        plog('Break because proposed evening exposure > 180 seconds:  ', exp_time)
                        g_dev['obs'].send_to_user('Try next filter because proposed  flat exposure < min_exposure.', p_level='INFO')
                        pop_list.pop(0)
                        break
                    if evening and exp_time < min_exposure:   #NB it is too bright, should consider a delay here.
                    #**************THIS SHOUD BE A WHILE LOOP! WAITING FOR THE SKY TO GET DARK AND EXP TIME TO BE LONGER********************
                        plog("Too bright, wating 180 seconds.")
                        g_dev['obs'].send_to_user('Delay 180 seconds to let it get darker.', p_level='INFO')
                        time.sleep(180)
                    if morn and exp_time > 120 :   #NB it is too bright, should consider a delay here.
                     #**************THIS SHOUD BE A WHILE LOOP! WAITING FOR THE SKY TO GET DARK AND EXP TIME TO BE LONGER********************
                        plog("Too dim, wating 180 seconds.")
                        g_dev['obs'].send_to_user('Delay 180 seconds to let it get lighterer.', p_level='INFO')
                        time.sleep(180)
                        #*****************NB Recompute exposure or otherwise wait
                        exp_time = min_exposure
                    exp_time = round(exp_time, 5)
                   # prior_scale = prior_scale*scale  #Only update prior scale when changing filters
                    plog("Sky flat estimated exposure time, scale are:  ", exp_time, scale)
                except:
                    exp_time = 0.3
                req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}
                opt = { 'count': 1, 'bin':  bin_spec, 'area': 150, 'filter': g_dev['fil'].filter_data[current_filter][0]}   #nb nb nb BIN CHNAGED FROM 2,2 ON 20220618 wer
                plog("using:  ", g_dev['fil'].filter_data[current_filter][0])
                if ephem.now() >= ending:
                    return
                try:

                    fred = g_dev['cam'].expose_command(req, opt, no_AWS=True, do_sep = False)

                    bright = fred['patch']    #  Patch should be circular and 20% of Chip area. ToDo project
                    plog('Returned:  ', bright)
                except Exception as e:
                    plog('Failed to get a flat image: ', e)
                    plog(traceback.format_exc())
                    plog("*****NO result returned*****  Will need to restart Camera")  #NB NB  NB this is drastic action needed.
                    g_dev['obs'].update_status()
                    continue
                g_dev['obs'].update_status()
                try:

                    scale *= target_flat /bright           #Note we are scaling the scale
                    plog("New scale is:  ", scale)
                    if scale > 5000:
                        scale = 5000
                    if scale < 0.01:
                        scale = 0.01
                except:
                    scale = 1.0

                if 'sky_lux' not in locals():
                    sky_lux=1000
                plog ("sky lux: " + str(sky_lux))


                plog('\n\n', "Patch/Bright:  ", bright, g_dev['fil'].filter_data[current_filter][0], \
                      'New Gain value: ', round(bright/(sky_lux*collecting_area*exp_time), 3), '\n\n')

                obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
                #  THE following code looks like a debug patch gone rogue.

                if bright > 35000 and (ephem.now() < ending):    #NB should gate with end of skyflat window as well.
                    for i in range(1):
                        time.sleep(2)  #  #0 seconds of wait time.  Maybe shorten for wide bands?
                        g_dev['obs'].update_status()
                else:
                    acquired_count += 1
                    if acquired_count == flat_count:
                        pop_list.pop(0)
                        plog("SCALE USED *************************:  ", scale)
                        prior_scale = scale     #Here is where we pre-scale the next filter. TEMPORARILLY TAKE THIS OUT
                        scale = 1

                obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
                g_dev['obs'].update_status()
                continue
        if morn is False:
            g_dev['mnt'].tracking = False   #  park_command({}, {})  #  NB this is provisional, Ok when simulating
            self.eve_sky_flat_latch = False
        elif morn:
            try:
                g_dev['mnt'].park_command({}, {})
            except:
                plog("Mount did not park at end of morning skyflats.")
            self.morn_sky_flat_latch = False
        plog('\nSky flat complete, or too early. Telescope Tracking is off.\n')
        self.sky_guard = False


    def screen_flat_script(self, req, opt):
        if req['numFrames'] > 1:
            flat_count = req['numFrames']
        else:
            flat_count = 1    #   A dedugging compromise

        #  NB here we need to check cam at reasonable temp, or dwell until it is.

        camera_name = str(self.config['camera']['camera_1_1']['name'])
        dark_count = 1
        exp_time = 15
        if flat_count < 1: flat_count = 1
        g_dev['mnt'].park_command({}, {})
        #  NB:  g_dev['enc'].close
        g_dev['obs'].update_status()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        time.sleep(5)
        g_dev['obs'].update_status()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': exp_time,  'alias': camera_name, 'image_type': 'screen flat'}
        opt = {'area': 100, 'count': dark_count, 'filter': 'dark', 'hint': 'screen dark'}  #  air has highest throughput

        result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        plog('First dark 30-sec patch, filter = "air":  ', result['patch'])
        # g_dev['scr'].screen_light_on()

        for filt in g_dev['fil'].filter_screen_sort:
            #enter with screen dark
            filter_number = int(filt)
            plog(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].update_status()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen pre-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
            plog("Dark Screen flat, starting:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()
            plog('Lighted Screen; filter, bright:  ', filter_number, screen_setting)
            g_dev['scr'].set_screen_bright(int(screen_setting))
            g_dev['scr'].screen_light_on()
            time.sleep(10)
            # g_dev['obs'].update_status()
            # time.sleep(10)
            # g_dev['obs'].update_status()
            # time.sleep(10)
            g_dev['obs'].update_status()
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen filter light'}
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
            # if no exposure, wait 10 sec
            plog("Lighted Screen flat:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            g_dev['obs'].update_status()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen post-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
            plog("Dark Screen flat, ending:  ",result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')


            #breakpoint()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].Tracking = False   #park_command({}, {})
        plog('Sky Flat sequence completed, Telescope tracking is off.')
        self.guard = False



    def auto_focus_script(self, req, opt, throw=600):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
        a verify.
        Auto focus consists of three points plus a verify.
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

        # First check how long it has been since the last focus
        print ("Time of last focus")
        print (g_dev['foc'].time_of_last_focus)
        print ("Time since last focus")
        print (datetime.datetime.now() - g_dev['foc'].time_of_last_focus)


        print ("Threshold time between auto focus routines (hours)")
        print (self.config['periodic_focus_time'])

        if ((datetime.datetime.now() - g_dev['foc'].time_of_last_focus)) > datetime.timedelta(hours=self.config['periodic_focus_time']):
            print ("Sufficient time has passed since last focus to do auto_focus")
            g_dev['foc'].time_of_last_focus = datetime.datetime.now()
        else:
            print ("too soon since last autofacus")
            return

        # Reset focus tracker
        g_dev['foc'].focus_tracker = [np.nan] * 10

        throw = g_dev['foc'].throw
        self.sequencer_hold = False   #Allow comand checks.
        self.guard = False
        self.af_guard = True

        req2 = copy.deepcopy(req)
        opt2 = copy.deepcopy(opt)

        sim = False  # g_dev['enc'].status['shutter_status'] in ['Closed', 'Closing', 'closed', 'closing']

        # try:
        #     self.redis_server.set('enc_cmd', 'sync_enc', ex=1200)
        #     self.redis_server.set('enc_cmd', 'open', ex=1200)
        # except:
        #     pass
        #plog('AF entered with:  ', req, opt, '\n .. and sim =  ', sim)
        #self.sequencer_hold = True  #Blocks command checks.
        #Here we jump in too  fast and need for mount to settle

        

# ============================================================================= Save AFTER mount has settled down.
# =============================================================================
# =============================================================================
        #  NB NB NB PLEASE NOTE WE ARE GETTING THE START POSITIONS WE EXPECT TO RETURN TO FROM THE MOUNT AND FOCUSER
        #  SO this may reult in drift if the return does not go to the mecahnical Ra and DEC.
        start_ra = g_dev['mnt'].mount.RightAscension   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
        start_dec = g_dev['mnt'].mount.Declination
        focus_start = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        #breakpoint()
# =============================================================================
# =============================================================================
# =============================================================================
        plog("Saved  *mounting* ra, dec, focus:  ", start_ra, start_dec, focus_start)

        if req2['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters

            #  Go to closest Mag 7.5 Tycho * with no flip

            focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
                                    g_dev['mnt'].current_sidereal)
            try:
                plog("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
                g_dev['mnt'].go_coord(focus_star[0][1][1], focus_star[0][1][0])
            except:
                print ("Issues pointing to a tycho star. Focussing at the current pointing.")
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
            opt = {'area': 150, 'count': 1, 'bin': 'default', 'filter': 'focus'}
        else:
            pass   #Just take an image where currently pointed.
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
            opt = {'area': 150, 'count': 1, 'bin': 'default', 'filter': 'focus'}
        foc_pos0 = focus_start
        result = {}
        #plog("temporary patch in Sim values")
        
        
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = ""
            
            #breakpoint()
            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            while g_dev['foc'].focuser.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'f>'
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                plog(st)
                st = ""
                time.sleep(0.2)
                g_dev['obs'].update_status()
            
            st = ""
            if g_dev['rot']!=None:                
                while g_dev['rot'].rotator.IsMoving:                    
                    if g_dev['rot'].rotator.IsMoving: st += 'r>'                    
                    #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                    plog(st)
                    st = ""
                    time.sleep(0.2)
                    g_dev['obs'].update_status()
                
        except:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            breakpoint()
        
        
        
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')


        g_dev['foc'].guarded_move((foc_pos0 - 0* throw)*g_dev['foc'].micron_to_steps)   # NB added 20220209 Nasty bug, varies with prior state

        #throw = throw  # NB again, from config.  Units are microns  Passed as default paramter
        retry = 0
        while retry < 3:
            if not sim:

                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.

            else:

                result['FWHM'] = 3
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron

            try:
                spot1 = result['FWHM']
                foc_pos1 = result['mean_focus']
            except:
                spot1 = False
                foc_pos1 = False
                print ("spot1 failed in autofocus script")

            print (spot1)

            if math.isnan(spot1) or spot1 ==False:
                retry += 1
                plog("Retry of central focus star)")
                continue
            else:
                break
        plog('Autofocus Moving In.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
        else:
            result['FWHM'] = 4
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot2 = result['FWHM']
            foc_pos2 = result['mean_focus']
        except:
            spot2 = False
            foc_pos2 = False
            print ("spot2 failed on autofocus moving in")

        plog('Autofocus Overtaveling Out.\n\n')
        g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
       #time.sleep(10)#It is important to overshoot to overcome any backlash  WE need to be sure Exposure waits.
        plog('Autofocus Moving back in half-way.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!

        #time.sleep(10)#opt['fwhm_sim'] = 5
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
        else:
            result['FWHM'] = 4.5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot3 = result['FWHM']
            foc_pos3 = result['mean_focus']
        except:
            spot3 = False
            foc_pos3 = False
            print ("spot3 failed on autofocus moving in")
        x = [foc_pos2, foc_pos1, foc_pos3]
        y = [spot2, spot1, spot3]
        plog('X, Y:  ', x, y, 'Desire center to be smallest.')

        if spot1 is None or spot2 is None or spot3 is None or spot1 == False or spot2 == False or spot3 == False:  #New additon to stop crash when no spots
            plog("No stars detected. Returning to original focus setting and pointing.")

            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)  #NB NB 20221002 THis unit fix shoudl be in the routine. WER
            self.sequencer_hold = False   #Allow comand checks.
            self.af_guard = False
            g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)  #MAKE sure same style coordinates.
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            return
        if spot1 < spot2 and spot1 < spot3:
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

            except:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
                time.sleep(5)
                self.sequencer_hold = False   #Allow comand checks.
                self.af_guard = False
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                self.sequencer_hold = False
                self.guard = False
                self.af_guard = False
                return
            if min(x) <= d1 <= max(x):
                print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                pos = int(d1*g_dev['foc'].micron_to_steps)



                g_dev['foc'].guarded_move(pos)
                time.sleep(5)
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    print ("spot4 failed ")
                plog('\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to:  ", start_ra, start_dec)
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
            if sim:

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
            #  NB here we could re-solve with the overlay spot just to verify solution is sane.

            #  NB NB We may want to consider sending the result image patch to AWS
            # NB NB NB I think we may have spot numbers wrong by 1 count and coarse focs not set up correctly.
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            return
        elif spot2  <= spot1 < spot3:      #Add to the inside
            pass
            plog('Autofocus Moving In 2nd time.\n\n')
            g_dev['foc'].guarded_move((foc_pos0 - 2.5*throw)*g_dev['foc'].micron_to_steps)
            if not sim:
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
            else:
                result['FWHM'] = 6
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot4 = result['FWHM']
                foc_pos4 = result['mean_focus']
            except:
                spot4 = False
                foc_pos4 = False
                print ("spot4 failed on autofocus moving in 2nd time.")
            x = [foc_pos4, foc_pos2, foc_pos1, foc_pos3]
            y = [spot4, spot2, spot1, spot3]
            plog('X, Y:  ', x, y, 'Desire center to be smallest.')
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

            except:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
                time.sleep(5)
                self.sequencer_hold = False   #Allow comand checks.
                self.af_guard = False
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                self.sequencer_hold = False
                self.guard = False
                self.af_guard = False
                return
            if min(x) <= d1 <= max(x):
                print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                pos = int(d1*g_dev['foc'].micron_to_steps)



                g_dev['foc'].guarded_move(pos)
                time.sleep(5)
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    print ("spot4 failed ")
                plog('\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to:  ", start_ra, start_dec)
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
            if sim:

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
            #  NB here we could re-solve with the overlay spot just to verify solution is sane.

            #  NB NB We may want to consider sending the result image patch to AWS
            # NB NB NB I think we may have spot numbers wrong by 1 count and coarse focs not set up correctly.
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            return

        elif spot2 > spot1 >= spot3:       #Add to the outside
            pass
            plog('Autofocus Moving back in half-way.\n\n')

            g_dev['foc'].guarded_move((foc_pos0 + 2.5*throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!
            if not sim:
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
            else:
                result['FWHM'] = 5.5
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot4 = result['FWHM']
                foc_pos4 = result['mean_focus']
            except:
                spot4 = False
                foc_pos4 = False
                print ("spot4 failed on autofocus moving out 2nd time.")
            x = [foc_pos2, foc_pos1, foc_pos3, foc_pos4]
            y = [spot2, spot1, spot3, spot4]
            plog('X, Y:  ', x, y, 'Desire center to be smallest.')
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

            except:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
                time.sleep(5)
                self.sequencer_hold = False   #Allow comand checks.
                self.af_guard = False
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                self.sequencer_hold = False
                self.guard = False
                self.af_guard = False
                return
            if min(x) <= d1 <= max(x):
                print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                pos = int(d1*g_dev['foc'].micron_to_steps)



                g_dev['foc'].guarded_move(pos)
                time.sleep(5)
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    print ("spot4 failed ")
                plog('\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to:  ", start_ra, start_dec)
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
            if sim:

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
            #  NB here we could re-solve with the overlay spot just to verify solution is sane.

            #  NB NB We may want to consider sending the result image patch to AWS
            # NB NB NB I think we may have spot numbers wrong by 1 count and coarse focs not set up correctly.
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False

            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            return
        elif spot2 <= spot1 or spot3 <= spot1:
            if spot2 <= spot3:
                min_focus = foc_pos2
            elif spot3 <= spot2:
                min_focus = foc_pos3
            else:
                min_focus = foc_pos0

            ##  HERE we could add a fourth or fifth try.  The parabola cannot really invert, nor should we ever be at a wild point after the first focus is
            ##  set up.
            plog("It appears camera is too far out; try again with coarse_focus_script.")
            self.coarse_focus_script(req2, opt2, throw=throw + 75, begin_at=min_focus)
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            return
        else:
            plog('Spots are really wrong so moving back to starting focus:  ', focus_start)
            g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
        plog("Returning to:  ", start_ra, start_dec)
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        if sim:

            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
        #  NB here we could re-solve with the overlay spot just to verify solution is sane.
        self.sequencer_hold = False   #Allow comand checks.
        self.af_guard = False
        #  NB NB We may want to consider sending the result image patch to AWS
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = False

        return


    def coarse_focus_script(self, req, opt, throw=700, begin_at=None):
        '''
        V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
        It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
        a verify.
        Auto focus consists of three points plus a verify.
        Fine focus consists of five points plus a verify.
        Optionally individual images can be multiples of one to average out seeing.
        NBNBNB This code needs to go to known stars to be moe relaible and permit subframes
        '''
        plog('AF entered with:  ', req, opt)
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = True
        # Reset focus tracker
        g_dev['foc'].focus_tracker = [np.nan] * 10
        sim = False #g_dev['enc'].status['shutter_status'] in ['Closed', 'closed', 'Closing', 'closing']
        plog('AF entered with:  ', req, opt, '\n .. and sim =  ', sim)
        #self.sequencer_hold = True  #Blocks command checks.
        start_ra = g_dev['mnt'].mount.RightAscension
        start_dec = g_dev['mnt'].mount.Declination
        if begin_at is None:  #  ADDED 20120821 WER
            foc_start = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        else:
            foc_start = begin_at  #In this case we start at a place close to a 3 point minimum.
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        plog("Saved ra, dec, focus:  ", start_ra, start_dec, foc_start)
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = ""
            while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'f>'
                if g_dev['rot'].rotator.IsMoving: st += 'r>'
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                plog(st)
                st = ""
                time.sleep(0.2)
                g_dev['obs'].update_status()
        except:
            plog("Motion check faulted.")
        if req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters
            #  Go to closest Mag 7.5 Tycho * with no flip
            focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
                                    g_dev['mnt'].current_sidereal)
            plog("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
            g_dev['mnt'].go_coord(focus_star[0][1][1], focus_star[0][1][0])
            req = {'time': 12.5,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': 15,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        foc_pos0 = foc_start
        result = {}
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 0*throw)*g_dev['foc'].micron_to_steps)  #Added 20220209! A bit late
        #throw = 100  # NB again, from config.  Units are microns
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)
        else:
            result['FWHM'] = 4
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot1 = result['FWHM']
            foc_pos1 = result['mean_focus']
        except:
            spot1 = False
            foc_pos1 = False
            print ("spot1 failed on coarse focus script")
        # if not sim:
        #     result = g_dev['cam'].expose_command(req, opt, no_AWS=True) ## , script = 'auto_focus_script_0')  #  This is where we start.
        # else:
        #     result['FWHM'] = 3
        #     result['mean_focus'] = foc_pos0
        # spot1 = result['FWHM']
        # foc_pos1 = result['mean_focus']


        plog('Autofocus Moving In -1x, second time.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)
        else:
            result['FWHM'] = 5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot2 = result['FWHM']
            foc_pos2 = result['mean_focus']
        except:
            spot2 = False
            foc_pos2 = False
            print ("spot2 failed on coarse focus script")
        plog('Autofocus Moving In -2x, second time.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)
        else:
            result['FWHM'] = 6
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot3 = result['FWHM']
            foc_pos3 = result['mean_focus']
        except:
            spot3 = False
            foc_pos3 = False
            print ("spot3 failed on coarse focus script")
        #Need to check we are not going out too far!
        plog('Autofocus Moving out +3X.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + 3*throw)*g_dev['foc'].micron_to_steps)
        plog('Autofocus back in for backlash to +2X\n\n')#It is important to overshoot to overcome any backlash
        g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)
        else:
            result['FWHM'] = 6.5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot4 = result['FWHM']
            foc_pos4 = result['mean_focus']
        except:
            spot4 = False
            foc_pos4 = False
            print ("spot4 failed on coarse focus script")
        plog('Autofocus back in for backlash to +1X\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=False)
        else:
            result['FWHM'] = 5.75
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot5 = result['FWHM']
            foc_pos5 = result['mean_focus']
        except:
            spot5 = False
            foc_pos5 = False
            print ("spot5 failed on coarse focus script")
        x = [foc_pos3, foc_pos2, foc_pos1, foc_pos5, foc_pos4]  # NB NB 20220218 This assigment is bogus!!!!
        y = [spot3, spot2, spot1, spot5, spot4]
        plog('X, Y:  ', x, y)
        try:
            #Digits are to help out pdb commands!
            a1, b1, c1, d1 = fit_quadratic(x, y)
            new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
        except:
            plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', foc_start)

            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            return
        if min(x) <= d1 <= max(x):
            print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
            #Saves a base for relative focus adjusts.
            pos = int(d1*g_dev['foc'].micron_to_steps)

            g_dev['foc'].guarded_move(pos)
            g_dev['foc'].last_known_focus = d1
            try:
                g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
            except:
                g_dev['foc'].last_temperature = 10.0    #NB NB This should be a site monthly default.
            g_dev['foc'].last_source = "coarse_focus_script"
            if not sim:

                result = g_dev['cam'].expose_command(req, opt, solve_it=False)
            else:
                result['FWHM'] = new_spot
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot6 = result['FWHM']
                foc_pos4 = result['mean_focus']
                plog('\n\n\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot6, 2), '\n\n\n')
            except:
                plog('Known bug, Verifcation did not work. Returing to target using solved focus.')
        else:
            plog('Coarse_focus did not converge. Moving back to starting focus:  ', foc_pos0)

            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        plog("Returning to:  ", start_ra, start_dec)
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        if sim:
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = False
        return result

    def append_completes(self, block_id):
        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + camera)
        plog("block_id:  ", block_id)
        lcl_list = seq_shelf['completed_blocks']
        lcl_list.append(block_id)   #NB NB an in-line append did not work!
        seq_shelf['completed_blocks']= lcl_list
        plog('Appended completes contains:  ', seq_shelf['completed_blocks'])
        seq_shelf.close()
        return

    def is_in_completes(self, check_block_id):
        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + camera)
        #plog('Completes contains:  ', seq_shelf['completed_blocks'])
        if check_block_id in seq_shelf['completed_blocks']:
            seq_shelf.close()
            #plog("Block ID in completed blocks:  ",  check_block_id)
            return True
        else:
            seq_shelf.close()
            return False


    def reset_completes(self):
        try:
            camera = self.config['camera']['camera_1_1']['name']
            seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + str(camera))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            plog('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return