

import time
import datetime
#from random import shuffle
import copy
from global_yard import g_dev
import ephem
import build_tycho as tycho
import config
import shelve
#from pprint import pprint
import ptr_utility
import redis
import math
import ephem

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
    if ra >= 24:
        ra -= 24
    if ra < 0:
        ra = 24
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
        print("sequencer connected.")
        print(self.description)
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
        self.bias_dark_latch = True
        self.sky_flat_latch = True
        #breakpoint()
        self.reset_completes()
        
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
            self.bias_dark_script(req, opt)
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
            print('Sequencer command:  ', command, ' not recognized.')
            
    def enc_to_skyflat_and_open(self ,enc_status, ocn_status, no_sky=False):
        #ocn_status = eval(self.redis_server.get('ocn_status'))
           #NB 120 is enough time to telescope to get pointed to East
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
                    print("Open and slew Dome to azimuth opposite the Sun:  ", round(flat_spot, 1))

                    # if enc_status['shutter_status'] in ['Closed', 'closed'] \
                    #     and ocn_status['hold_duration'] <= 0.1:
                    #     #breakpoint()
                    #     g_dev['enc'].open_command({}, {})
                    #     time.sleep(3)
                    g_dev['enc'].sync_mount_command({}, {})
                   #Prior to skyflats no dome following.

                    self.dome_homed = False
                    self.time_of_next_slew = time.time() + 120  # seconds between slews.
                except:
                    pass#
    def park_and_close(self, enc_status):
        try:
            if not g_dev['mnt'].mount.AtParK:   ###Test comment here
                g_dev['mnt'].park_command({}, {}) # Get there early
        except:
            pass
        if enc_status['shutter_status'] in ['open', ]:
            g_dev['enc'].close_command( {}, {})
        print("Park and Close was executed.")

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
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        try:
            ocn_status = eval(self.redis_server.get('ocn_status'))
            enc_status = eval(self.redis_server.get('enc_status'))
        except:
            print("Wema not reporting.")
            return
        events = g_dev['events']

        #g_dev['obs'].update_status()  #NB NEED to be sure we have current enclosure status.  Blows recursive limit
        self.current_script = "No current script"    #NB this is an unused remnant I think.
        #if True or     #Note this runs in Manual Mode as well.
        if self.bias_dark_latch and ((events['Eve Bias Dark'] <= ephem_now < events['End Eve Bias Dark']) and \
             self.config['auto_eve_bias_dark'] and g_dev['enc'].mode == 'Automatic' ):
            self.bias_dark_latch = False
            req = {'bin1': False, 'bin2': True, 'bin3': False, 'bin4': False, 'numOfBias': 45, \
                   'numOfDark': 15, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 360, \
                   'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }
            opt = {}
            #No action needed on  the enclosure at this level
            self.park_and_close(enc_status)
            #NB The above put dome closed and telescope at Park, Which is where it should have been upon entry.   
            self.bias_dark_script(req, opt)
            self.bias_dark_latch = False
        #elif  True or  
        elif ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Eve Sky Flats']) and \
               g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold:  
            self.enc_to_skyflat_and_open(enc_status, ocn_status)
        
        #elif True or 
        elif self.sky_flat_latch and ((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
               and g_dev['enc'].mode == 'Automatic' and not g_dev['ocn'].wx_hold and \
               self.config['auto_eve_sky_flat']):
            self.sky_flat_latch = False
            #if enc_status['shutter_status'] in ['Closed', 'closed', 'Closing', 'closing']:
            self.enc_to_skyflat_and_open(enc_status, ocn_status)   #Just in case a Wx hold stopped opening      

            self.current_script = "Eve Sky Flat script starting"
            #print('Skipping Eve Sky Flats')
            self.sky_flat_script({}, {})   #Null command dictionaries
            self.sky_flat_latch = False
        elif g_dev['enc'].mode == 'Automatic' and (events['Observing Begins'] <= ephem_now < events['Observing Ends']) and \
                   not g_dev['ocn'].wx_hold and  g_dev['obs'].blocks is not None and g_dev['obs'].projects is not None:
            blocks = g_dev['obs'].blocks
            projects = g_dev['obs'].projects
            debug = False
            if debug:
                print("# of Blocks, projects:  ", len(g_dev['obs'].blocks),  len(g_dev['obs'].projects))
            # NB without deepcopy decrementing counts in blocks will be local to the machine an subject
            # to over_write as the respons from AWS updates. This is particularly important for owner
            # and background blocks.
            
            #First, sort blocks to be in ascending order, just to promote clarity. Remove expired projects.
            for block in blocks:  #  This merges project spec into the blocks.
                for project in projects:
                    if block['project_id'] == project['project_name'] + '#' + project['created_at']:
                        block['project'] = project
                        #print('Scheduled so removing:  ', project['project_name'])
                        #projects.remove(project)
                        
            #The residual in projects can be treated as background.
            #print('Background:  ', len(projects), '\n\n', projects)
            
 
            house = []
            for project in projects:
                if project['user_id'] in config.site_config['owner']:  # and not expired, etc.
                     house.append(project)
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
            #print("Initial length:  ", len(blocks))
            for block in blocks:
                now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'           
                if not self.block_guard \
                    and (block['start'] <= now_date_timeZ < block['end']) \
                    and not self.is_in_completes(block['event_id']):
                    self.block_guard = True
                    completed_block = self.execute_block(block)  #In this we need to ultimately watch for weather holds.
                    self.append_completes(completed_block['event_id'])
                    self.block_guard = False
                    '''
                    When a scheduled block is completed it is not re-entered or the block needs to 
                    be restored.  IN the execute block we need to make a deepcopy of the input block
                    so it does not get modified.
                    '''
            #print('block list exhausted')  
            return
            
                
                # print("Here we would enter an observing block:  ",
                #       block)
                # breakpoint()
            #OK here we go to a generalized block execution routine that runs
            #until exhaustion of the observing window.
            # else:
            #     pass
            #print("Block tested for observatility")
                
                    
        else:
            self.current_script = "No current script, or site not in Automatic."
            #print("No active script is scheduled.")
            return
    def take_lrgb_stack(self, req_None, opt=None):

        self.redis_server.set('sim_hold', True, ex=120)
            
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
        ocn_status = eval(self.redis_server.get('ocn_status'))
        enc_status = eval(self.redis_server.get('enc_status'))
        self.block_guard = True
        # NB we assume the dome is open and already slaving.
        block = copy.deepcopy(block_specification)
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
        at some point, but af does not decrement. This is still left to do
        
        
        '''
        # if bock['project'] is None:
            #user controlled block...
        #NB NB NB  if no project found, need to say so not fault. 20210624
        #breakpoint()
        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            dest_ra = float(target['ra']) - \
                float(block_specification['project']['project_constraints']['ra_offset'])/15.
            dest_dec = float(target['dec']) - float(block_specification['project']['project_constraints']['dec_offset'])
            dest_ra, dest_dec = ra_dec_fix_hd(dest_ra,dest_dec)
            dest_name =target['name']
            
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
            self.redis_server.set('sync_enc', True, ex=1200)   #Should be redundant
            print("CAUTION:  rotator may block")
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
                    print('# of mosaic panes:  ', multiplex)
                else:
                    left_to_do += int(exposure['count'])
                    print('Singleton image')
                
            print("Left to do initial value:  ", left_to_do)
            req = {'target': 'near_tycho_star'}
            initial_focus = True
            af_delay = 45*60  #This must be a big number!

            while left_to_do > 0 and not ended:

                if initial_focus:
                    print("Enc Status:  ", g_dev['enc'].get_status())
                    

                    if not g_dev['enc'].shutter_is_closed:
                        self.auto_focus_script(req2, opt, throw = 750)
                        pass
                    else:
                        print('Shutter closed, skipping AF cycle.0')  #coarse_focus_script can be used here
                    just_focused = True
                    initial_focus = False    #  Make above on-time event per block
                    timer = time.time() + af_delay  # 45 minutes
                    #at block startup this should mean two AF cycles. Cosider using 5-point for the first.
                    
                #cycle through exposures decrementing counts    MAY want to double check left-to do but do nut remultiply by 4
                for exposure in block['project']['exposures']:
                    if block_specification['project']['project_constraints']['frequent_autofocus'] == True and (time.time() - timer) >= 0:
                        #What purpose does this code serve, it appears to be a debug remnant? WER 20200206
                        if not g_dev['enc'].shutter_is_closed:
                            self.auto_focus_script(req2, opt, throw = 500)
                        else:
                            print('Shutter closed, skipping AF cycle.0')
                        initial_focus = False
                        just_focused = True
                        timer = time.time() + af_delay  #40 minutes to refocus
                    print("Executing: ", exposure, left_to_do)
                    color = exposure['filter']
                    exp_time =  float(exposure['exposure']) 
                    #dither = exposure['dither']
                    breakpoint()
                    if exposure['bin'] in [2, '2,2', '2, 2', '2 2']:
                        binning = '2 2'
                    elif exposure['bin'] in [3, '3,3', '3, 3', '3 3']:
                        binning = '3 3'
                    else:
                        binning = '1 1'
                    count = int(exposure['count'])
                    #  We should add a frame repeat count
                    imtype = exposure['imtype'] 
                    #defocus = exposure['defocus']
#                    if g_dev['site'] == 'saf':   #THis should be in config.
                    if color[0] == 'B':  
                        color = 'PB'   #Map generic filters to site specific ones.
                    if color[0] == 'G':  
                        color = 'PG'   # NB NB THis needs a clean up, these mappings should be in config
                    if color[0] == 'R':  
                        color = 'PR'
                    if color[0] == 'L':  
                        color = 'PL'
                    if color[0] == 'W':  
                        color = 'w'
                    if color[0] == 'g':  
                        color = 'gp'
                    if color[0] == 'r':    #NB This is redundant for Sloans when small cap.
                        color = 'rp'
                    if color[0] == 'i':     #NB NB THIS IS WRONG For Johnson and Bessell
                        color = 'ip'
                    if color[0] == 'H':  
                        color = 'HA'
                    if color[0] == 'O':  
                        color = 'O3'
                    if color[0] == 'S':  
                        color = 'S2'
                    if color[0] == 'C':  
                        color = 'CR'
                    if count <= 0:
                         continue
                    #At this point we have 1 to 9 exposures to make in this filter.  Note different areas can be defined. 
                    if exposure['area'] in ['300', '300%', 300, '220', '220%', 220, '150', '150%', 150, '125', '125%', 125]:  # 4 or 5 expsoures.
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
                        if exposure['area'] in ['125', '125%', 125]:
                            pitch = 0.125
                    elif exposure['area'] in ['600', '600%', 600, '450', '450%', 450]:  # 9 exposures.
                        offset = [(0.5, 0.5), 
                                  (-0.5, 0.5), 
                                  (-1.5, 0.5), 
                                  (-1.5, -0.5), 
                                  (-0.5, -0.5), 
                                  (0.5, -0.5), 
                                  (1.5, -0.5 ), 
                                  (1.5, 0.5),
                                  (1.5, 1.5),  
                                  (0.5 , 1.5), 
                                  (-0.5, 1.5), 
                                  (-1.5, 1.5), 
                                  (-1.5, 0.5), 
                                  (1.5, -0.5), 
                                  (-1.5, -1.5),
                                  (-0.5, -1.5), 
                                  (0.5, -1.5), 
                                  (1.5, -1.5)] #Fifteen mosaic quadrants 36 x 24mm chip
                        if exposure['area'] in ['600', '600%', 600]:
                            pitch = 0.125

                        if exposure['area'] in ['450', '450%', 450]:
                            pitch = 0.1875
                        pane = 0
                    elif exposure['area'] in ['500', '500%',]:  # 6 or 7 exposures.  SQUARE
                        step = 1.466667
                        if block_specification['project']['project_constraints']['add_center_to_mosaic']:
                            offset = [(0., 0.), (-1, 0.), (-1, step), (1, step), (1, 0), \
                                      (1, -step), (-1, -step)] #Aimpoint + six mosaic quadrants 36 x 24mm chip
                            pane = 0
                        else:
                            offset = [(-1, 0.), (-1, step),  (1, step), (1, 0), \
                                      (1, -step), (-1, -step)] #Six mosaic quadrants 36 x 24mm chip  
                            pane = 1
                        pitch = .375
                    elif exposure['area'] in ['+SQ', '133%']:  # 2 exposures.  SQUARE
                        step = 1
                        offset = [(0, -1), (0, 1)] #Two mosaic steps 36 x 24mm chip  Square
                        pane = 1
                        pitch = 0.1875   #Try this out for small overlap and tall field.
                    else:
                        offset = [(0., 0.)] #Zero(no) mosaic offset
                        pitch = 0.
                        pane = 0
                    for displacement in offset:
                        x_field_deg = g_dev['cam'].config['camera']['camera_1']['settings']['x_field_deg']
                        y_field_deg = g_dev['cam'].config['camera']['camera_1']['settings']['y_field_deg']
                        
                        d_ra = displacement[0]*( 1 - pitch)*(x_field_deg/15.)  # 0.764243 deg = 0.0509496 Hours  These and pixscale should be computed in config.
                        d_dec = displacement[1]*(1 - pitch)*(y_field_deg)  # = 0.5102414999999999   #Deg
                        new_ra = dest_ra + d_ra
                        new_dec= dest_dec + d_dec
                        new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)
                        # offset = 44514.552766203706
                        # moon_time = ephem.now() - offset + 78/1440
                        # moon_ra = 0.787166667*moon_time + 1.0219444 + 0.01 - t*0.00025
                        # moon_dec = 8.3001964784*math.pow(moon_time, 0.6719299333) - 0.125 + t*0.002
                        # new_ra = moon_ra
                        # new_dec = moon_dec
                        print('Seeking to:  ', new_ra, new_dec)
                        g_dev['mnt'].go_coord(new_ra, new_dec)  # This needs full angle checks
                        if not just_focused:
                            g_dev['foc'].adjust_focus()
                        just_focused = False
                        if imtype in ['light'] and count > 0:
                            req = {'time': exp_time,  'alias':  str(self.config['camera']['camera_1']['name']), 'image_type': imtype}   #  NB Should pick up filter and constants from config
                            opt = {'area': 150, 'count': 1, 'bin': binning, 'filter': color, \
                                   'hint': block['project_id'] + "##" + dest_name, 'pane': pane}
                            print('Seq Blk sent to camera:  ', req, opt)
                            g_dev['cam'].expose_command(req, opt, no_AWS=False)
                            t +=1
                            count -= 1
                            exposure['count'] = count
                            left_to_do -= 1
                            print("Left to do:  ", left_to_do)
                            # offset = 44514.552766203706
                            # moon_time = ephem.now() - offset + 78/1440
                            # moon_ra = 0.787166667*moon_time + 1.0219444 + 0.01 + t*0.0001
                            # moon_dec = 8.3001964784*math.pow(moon_time, 0.6719299333) - 0.125 - t*0.01
                            # new_ra = moon_ra
                            # new_dec = moon_dec
                        pane += 1
                        
                    now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                    ephem_now = ephem.now()
                    events = g_dev['events']

                    ended = left_to_do <= 0 or now_date_timeZ >= block['end'] \
                            or ephem_now >= events['Observing Ends']
                    #                                                    ]\
                    #         or g_dev['airmass'] > float( block_specification['project']['project_constraints']['max_airmass']) \
                    #         or abs(g_dev['ha']) > float(block_specification['project']['project_constraints']['max_ha'])
                    #         # Or mount has flipped, too low, too bright, entering zenith..
                    
        print("Fini!")   #NB Should we consider turning off mount tracking?
        if block_specification['project']['project_constraints']['close_on_block_completion']:
            #g_dev['mnt'].park_command({}, {})
            # NB NBNeed to write a more robust and generalized clean up.
            try:
                pass#g_dev['enc'].enclosure.Slaved = False   NB with wema no longer exists
            except:
                pass
            self.redis_server.set('unsync_enc', True, ex=1200)
            #g_dev['enc'].close_command({}, {})
            g_dev['mnt'].park_command({}, {})

            print("Auto close attempted at end of block.")
        self.block_guard = False
        return block_specification #used to flush the queue as it completes.


    def bias_dark_script(self, req=None, opt=None):
        """

        20200618   This has been drastically simplied for now to deal with only QHY600M.

        May still have a bug where it latches up only outputting 2x2 frames.
                 
        """
        self.sequencer_hold = True
        self.current_script = 'Afternoon Bias Dark'
        #dark_time = 300   #seed for 3x3 binning
        #breakpoint()
        
        while ephem.now() < g_dev['events']['Morn Bias Dark'] :   #Do not overrun the window end
            #g_dev['mnt'].unpark_command({}, {}) # Get there early
            #g_dev['mnt'].slewToSkyFlatAsync()
            print("Expose Biases: b- 2, 1, 3;  300s darks.")
            dark_time = 300
            req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
            opt = {'area': "Full", 'count': 7, 'bin':'2 2', \
                    'filter': 'dark'}
            for bias in range(9):
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'area': "Full", 'count': 9, 'bin':'2 2', \
                        'filter': 'dark'}
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                do_sep=False, quick=False)
                g_dev['obs'].update_status()


                print("Expose d_2 using exposure:  ", dark_time )
                req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                opt = {'area': "Full", 'count':1, 'bin': '2 2', \
                        'filter': 'dark'} 
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                    do_sep=False, quick=False)

                g_dev['obs'].update_status()
                
                if ephem.now() >= g_dev['events']['End Eve Bias Dark']:
                    break
                
                print("Expose Biases: b_1")   
                dark_time = 300
                #for bias in range(9):
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'area': "Full", 'count': 7, 'bin':'1 1', \
                       'filter': 'dark'}
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                do_sep=False, quick=False)
                g_dev['obs'].update_status()
 

                print("Expose d_1 using exposure:  ", dark_time )
                req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                opt = {'area': "Full", 'count':1, 'bin': '1,1', \
                        'filter': 'dark'} 
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                    do_sep=False, quick=False)

                g_dev['obs'].update_status()

                if ephem.now() >= g_dev['events']['End Eve Bias Dark']:
                    break
           
                print("Expose Biases: b_3")   
                dark_time = 240
                #for bias in range(9):
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'area': "Full", 'count': 9, 'bin':'3 3', \
                        'filter': 'dark'}
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                do_sep=False, quick=False)
                g_dev['obs'].update_status()

                print("Expose d_3 using exposure:  ", dark_time )
                req = {'time':dark_time,  'script': 'True', 'image_type': 'dark'}
                opt = {'area': "Full", 'count':1, 'bin':'3 3', \
                        'filter': 'dark'} 
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                                    do_sep=False, quick=False)
                print('Last dark result:  ', result)
                g_dev['obs'].update_status()
                
                if ephem.now() >= g_dev['events']['End Eve Bias Dark']:
                    break
                # print("Expose Biases: b_4") 
                # dark_time = 120
                # for bias in range(9):
                #     req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                #     opt = {'area': "Full", 'count': 7, 'bin':'4 4', \
                #             'filter': 'dark'}
                #     result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                #                     do_sep=False, quick=False)
                #     g_dev['obs'].update_status()
    
    
                #     print("Expose d_4 using exposure:  ", dark_time )
                #     req = {'time':dark_time ,  'script': 'True', 'image_type': 'dark'}
                #     opt = {'area': "Full", 'count':1, 'bin': '4 4', \
                #             'filter': 'dark'} 
                #     result = g_dev['cam'].expose_command(req, opt, no_AWS=True, \
                #                         do_sep=False, quick=False)
    
                #     g_dev['obs'].update_status()

                if ephem.now() >= g_dev['events']['End Eve Bias Dark']:
                    break



            print(" Bias/Dark acquisition is finished.")
 

        self.sequencer_hold = False
        print("Bias/Dark acquisition has completed.")
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
        self.sky_guard = True
        print('Eve Sky Flat sequence Starting, Enclosure PRESUMED Open. Telescope will un-park.')
        camera_name = str(self.config['camera']['camera_1']['name'])
        flat_count = 7
        exp_time = .0015
        #  NB Sometime, try 2:2 binning and interpolate a 1:1 flat.  This might run a lot faster.
        if flat_count < 1: flat_count = 1

        if g_dev['mnt'].mount.AtPark:
            g_dev['mnt'].unpark_command({}, {})
        g_dev['mnt'].slewToSkyFlatAsync()
        self.redis_server.set('enc_cmd', 'sync_enc', ex=1200)   #Should be redundant.
        
        #NB NB we need to re-open is WX hold ends.
        # if g_dev['enc'].is_dome and not g_dev['enc'].mode == 'Automatic':
        #      g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        #     print('\n SERVOED THE DOME HOPEFULLY!\n')
        #g_dev['obs'].update_status()
        # try:
        #     g_dev['scr'].screen_dark()
        # except:
        #     pass
        #  We should probe to be sure dome is open, otherwise this is a test when closed and
        #  we can speed it up
        #Here we may need to switch off any
        #  Pick up list of filters is sky flat order of lowest to highest transparency.
        pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort'].copy()
        print('filters by low to high transmission:  ', pop_list)
        #length = len(pop_list)
        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        scale = 1.0
        prior_scale = 1
        
        collecting_area = self.config['telescope']['telescope1']['collecting_area']/32000.
        #  (g_dev['events']['Eve Sky Flats'] < 
        while len(pop_list) > 0 and (g_dev['events']['Eve Sky Flats'] < ephem_now - 2/1440 < g_dev['events']['End Eve Sky Flats']):

            current_filter = int(pop_list[0])
            acquired_count = 0
            #req = {'filter': current_filter}
            #opt =  {'filter': current_filter}

            g_dev['fil'].set_number_command(current_filter)
            g_dev['mnt'].slewToSkyFlatAsync()
            bright = 25000
            scale = 1.0    #1.15   #20201121 adjustment
            
            prior_scale = 1.0
            #breakpoint()
            while (acquired_count < flat_count): #and (ephem_now +3/1440) < g_dev['events']['End Eve Sky Flats' ]:
                #if g_dev['enc'].is_dome:   #Does not apply
                g_dev['mnt'].slewToSkyFlatAsync()
                g_dev['obs'].update_status()
                try:
                    try:
                        sky_lux = eval(self.redis_server.get('ocn_status'))['calc_HSI_lux']     #Why Eval, whould have float?
                    except:
                        print("Redis not running. lux set to 1000.")
                        sky_lux = 1000
                    exp_time = prior_scale*scale*13587/(collecting_area*sky_lux*float(g_dev['fil'].filter_data[current_filter][3]))  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                    
                    print('Ex:  ', exp_time, scale, prior_scale, sky_lux, float(g_dev['fil'].filter_data[current_filter][3]))
                    #exp_time*= 4.9/9/2
                    if exp_time > 120:
                        exp_time = 120    #Live with this limit.
                    if exp_time <0.001:
                        exp_time = 0.001
                    exp_time = round(exp_time, 4)
                    prior_scale = prior_scale*scale
                    print("Sky flat estimated exposure time, scale are:  ", exp_time, scale)
                except:
                    exp_time = 0.3
                req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}
                opt = { 'count': 1, 'bin':  '2,2', 'area': 150, 'filter': g_dev['fil'].filter_data[current_filter][0]}
                print("using:  ", g_dev['fil'].filter_data[current_filter][0])
               
                try:
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, do_sep = False)
                    bright = result['patch']    #  Patch should be circular and 20% of Chip area. ToDo project
                except:
                    print('*****NO result returned*****')
                    continue
                g_dev['obs'].update_status()
                try:
                    scale = 25000/bright
                    if scale > 5:
                        scale = 5
                    if scale < 0.33:
                        scale = 0.33
                except:
                    scale = 1.0

                print('\n\n\n', "Patch/Bright:  ", bright, g_dev['fil'].filter_data[current_filter][0], \
                      '  Gain: ', round(bright/(2.2*sky_lux*collecting_area*exp_time), 3), '\n\n\n')

                obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
                #  THE following code looks like a debug patch gone rogue.
                if bright > 30000 and (ephem_now < g_dev['events']['End Eve Sky Flats'] - 4/1440):    #NB should gate with end of skyflat window as well.
                    for i in range(1):
                        time.sleep(5)  #  #0 seconds of wait time.  Maybe shorten for wide bands?
                        g_dev['obs'].update_status()
                else:
                    acquired_count += 1
                    if acquired_count == flat_count:
                        pop_list.pop(0)
                        scale = 1
                        prior_scale = 1
                obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
                continue
        g_dev['mnt'].tracking = False   #  park_command({}, {})  #  NB this is provisional, Ok when simulating
        print('\nSky flat complete, or too early. Telescope Tracking is off.\n')
        self.sky_guard = False


    def screen_flat_script(self, req, opt):
        if req['numFrames'] > 1:
            flat_count = req['numFrames']
        else:
            flat_count = 1    #   A dedugging compromise

        #  NB here we need to check cam at reasonable temp, or dwell until it is.

        camera_name = str(self.config['camera']['camera_1']['name'])
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
        print('First dark 30-sec patch, filter = "air":  ', result['patch'])
        # g_dev['scr'].screen_light_on()

        for filt in g_dev['fil'].filter_screen_sort:
            #enter with screen dark
            filter_number = int(filt)
            print(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].update_status()
            print('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen pre-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
            print("Dark Screen flat, starting:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()
            print('Lighted Screen; filter, bright:  ', filter_number, screen_setting)
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
            print("Lighted Screen flat:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update_status()
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            g_dev['obs'].update_status()
            print('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen post-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
            print("Dark Screen flat, ending:  ",result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')


            #breakpoint()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].Tracking = False   #park_command({}, {})
        print('Sky Flat sequence completed, Telescope tracking is off.')
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
        self.sequencer_hold = False   #Allow comand checks.
        self.guard = False

        req2 = copy.deepcopy(req)
        opt2 = copy.deepcopy(opt)
        self.af_guard = True
        sim = g_dev['enc'].shutter_is_closed
        self.redis_server.set('enc_cmd', 'sync_enc', ex=1200)
        self.redis_server.set('enc_cmd', 'open', ex=1200)
        print('AF entered with:  ', req, opt, '\n .. and sim =  ', sim)
        #self.sequencer_hold = True  #Blocks command checks.
        #Here we jump in too  fast and need for mount to settle
        start_ra = g_dev['mnt'].mount.RightAscension   #Read these to go back.
        start_dec = g_dev['mnt'].mount.Declination
        focus_start = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        print("Saved ra, dec, focus:  ", start_ra, start_dec, focus_start)
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = "" 

            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                  g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'f>'
                if g_dev['rot'].rotator.IsMoving: st += 'r>'
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ""
                time.sleep(0.2)
                g_dev['obs'].update_status()
        except:
            print("Motion check faulted.")

        #  NBNBNB Need to preserve  and restore on exit, incoming filter setting

        if req2['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters

            #  Go to closest Mag 7.5 Tycho * with no flip

            focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
                                    g_dev['mnt'].current_sidereal)
            print("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
            g_dev['mnt'].go_coord(focus_star[0][1][1], focus_star[0][1][0])
            req = {'time': 12.5,  'alias':  str(self.config['camera']['camera_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'w'}
        else:
            pass   #Just take an image where currently pointed.
            req = {'time': 15,  'alias':  str(self.config['camera']['camera_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'w'}
        foc_pos0 = focus_start
        result = {}
        #print("temporary patch in Sim values")
        print('Autofocus Starting at:  ', foc_pos0, '\n\n')
        #throw = throw  # NB again, from config.  Units are microns  Passed as default paramter
        retry = 0
        while retry < 3:
            if not sim:
                result = g_dev['cam'].expose_command(req, opt, no_AWS=True) ## , script = 'auto_focus_script_0')  #  This is where we start.
            else:
                result['FWHM'] = 3
                result['mean_focus'] = foc_pos0

            spot1 = result['FWHM']
            foc_pos1 = result['mean_focus']
            if math.isnan(spot1):
                retry += 1
                print("Retry of central focus star)")
                continue
            else:
                break
        print('Autofocus Moving In.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 - throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
        else:
            result['FWHM'] = 4
            result['mean_focus'] = foc_pos0 - throw
        spot2 = result['FWHM']
        foc_pos2 = result['mean_focus']
        print('Autofocus Overtaveling Out.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 - 3*throw)*g_dev['foc'].micron_to_steps)   #It is important to overshoot to overcome any backlash
        print('Autofocus Moving back in half-way.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
        else:
            result['FWHM'] = 4.5
            result['mean_focus'] = foc_pos0 + throw
        spot3 = result['FWHM']
        foc_pos3 = result['mean_focus']
        x = [foc_pos2, foc_pos1, foc_pos3]
        y = [spot2, spot1, spot3]
        print('X, Y:  ', x, y, 'Desire center to be smallest.')
        if spot1 is None or spot2 is None or spot3 is None:  #New additon to stop crash when no spots
            print("No stars detected. Returning to starting focus and pointing.")
            g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
            self.sequencer_hold = False   #Allow comand checks.
            self.af_guard = False
            g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)
            return
        if spot1 < spot2 and spot1 < spot3:
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
    
            except:
    
                print('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
                self.sequencer_hold = False   #Allow comand checks.
                self.af_guard = False
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)
                return            
            if min(x) <= d1 <= max(x):
                print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                pos = int(d1*g_dev['foc'].micron_to_steps)
                
                
                g_dev['foc'].focuser.Move(pos)
                g_dev['foc'].last_known_focus = d1
                g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                g_dev['foc'].last_source = "auto_focus_script"
                if not sim:
                    result = g_dev['cam'].expose_command(req, opt, no_AWS=True, solve_it=True)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = d1
                spot4 = result['FWHM']
                foc_pos4 = result['mean_focus']
                print('\n\n\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot4, 2), '\n\n\n')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                print("Returning to:  ", start_ra, start_dec)
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
            if sim:
                g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
            #  NB here we could re-solve with the overlay spot just to verify solution is sane.
            self.sequencer_hold = False   #Allow comand checks.
            self.af_guard = False
            #  NB NB We may want to consider sending the result image patch to AWS
            return
        elif spot2 <= spot1 or spot3 <= spot1:
            if spot2 <= spot1: 
                min_focus = foc_pos2
            if spot3 <= spot1:
                min_focus = foc_pos3
            print("It appears camera is too far out; try again with coarse_focus_script.")
            self.coarse_focus_script(req2, opt2, throw=600, begin_at=min_focus)
        else:
            print('Spots are really wrong so moving back to starting focus:  ', focus_start)
            g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
        print("Returning to:  ", start_ra, start_dec)
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        if sim:
            g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
        #  NB here we could re-solve with the overlay spot just to verify solution is sane.
        self.sequencer_hold = False   #Allow comand checks.
        self.af_guard = False
        #  NB NB We may want to consider sending the result image patch to AWS
        return


    def coarse_focus_script(self, req, opt, throw=750, begin_at=None):
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
        sim = g_dev['enc'].status['shutter_status'] in ['Closed', 'closed', 'Closing', 'closing']
        print('AF entered with:  ', req, opt, '\n .. and sim =  ', sim)
        #self.sequencer_hold = True  #Blocks command checks.
        start_ra = g_dev['mnt'].mount.RightAscension
        start_dec = g_dev['mnt'].mount.Declination
        if begin_at is None:  #  ADDED 20120821 WER
            foc_start = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        else:
            foc_start = begin_at  #In this case we start at a place close to a 3 point minimum. 
            g_dev['foc'].focuser.Move((foc_start)*g_dev['foc'].micron_to_steps)
        print("Saved ra dec focus:  ", start_ra, start_dec, foc_start)
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = "" 
            while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                  g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'f>'
                if g_dev['rot'].rotator.IsMoving: st += 'r>'
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ""
                time.sleep(0.2)
                g_dev['obs'].update_status()
        except:
            print("Motion check faulted.")
        if req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters
            #  Go to closest Mag 7.5 Tycho * with no flip
            focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
                                    g_dev['mnt'].current_sidereal)
            print("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
            g_dev['mnt'].go_coord(focus_star[0][1][1], focus_star[0][1][0])
            req = {'time': 12.5,  'alias':  str(self.config['camera']['camera_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'w'}
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': 15,  'alias':  str(self.config['camera']['camera_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'w'}
        foc_pos0 = foc_start
        result = {}
        print('Autofocus Starting at:  ', foc_pos0, '\n\n')
        #throw = 100  # NB again, from config.  Units are microns
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        else:
            result['FWHM'] = 4
            result['mean_focus'] = foc_pos0
        spot1 = result['FWHM']
        foc_pos1 = result['mean_focus']  
        # if not sim:
        #     result = g_dev['cam'].expose_command(req, opt, no_AWS=True) ## , script = 'auto_focus_script_0')  #  This is where we start.
        # else:
        #     result['FWHM'] = 3
        #     result['mean_focus'] = foc_pos0
        # spot1 = result['FWHM']
        # foc_pos1 = result['mean_focus']
        
        
        
        g_dev['foc'].focuser.Move((foc_pos0 - throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        else:
            result['FWHM'] = 5
            result['mean_focus'] = foc_pos0 - throw
        spot2 = result['FWHM']
        foc_pos2 = result['mean_focus']
        print('Autofocus Moving In, second time.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 - 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        else:
            result['FWHM'] = 6
            result['mean_focus'] = foc_pos0 - 2*throw
        spot3 = result['FWHM']
        foc_pos3 = result['mean_focus']
        #Need to check we are not going out too far!
        print('Autofocus Moving out 4X.\n\n')
        g_dev['foc'].focuser.Move((foc_pos0 + 3*throw)*g_dev['foc'].micron_to_steps)
        print('Autofocus back in for backlash\n\n')#It is important to overshoot to overcome any backlash
        g_dev['foc'].focuser.Move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        else:
            result['FWHM'] = 6.5
            result['mean_focus'] = foc_pos0 + 2*throw
        spot4 = result['FWHM']
        foc_pos4 = result['mean_focus']
        g_dev['foc'].focuser.Move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            result = g_dev['cam'].expose_command(req, opt, no_AWS=True)
        else:
            result['FWHM'] = 5.75
            result['mean_focus'] = foc_pos0 + throw
        spot5 = result['FWHM']
        foc_pos5 = result['mean_focus']
        x = [foc_pos3, foc_pos2, foc_pos1, foc_pos5, foc_pos4]
        y = [spot3, spot2, spot1, spot5, spot4]
        print('X, Y:  ', x, y)
        try:
            #Digits are to help out pdb commands!
            a1, b1, c1, d1 = fit_quadratic(x, y)
            new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
        except:
            print('Autofocus quadratic equation not converge. Moving back to starting focus:  ', foc_start)
            g_dev['foc'].focuser.Move((foc_start)*g_dev['foc'].micron_to_steps)
            self.sequencer_hold = False   #Allow comand checks.
            self.af_guard = False
            return 
        if min(x) <= d1 <= max(x):
            print ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
            #Saves a base for relative focus adjusts.
            pos = int(d1*g_dev['foc'].micron_to_steps)
            g_dev['foc'].focuser.Move(pos)
            g_dev['foc'].last_known_focus = d1
            g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
            g_dev['foc'].last_source = "coarse_focus_script"
            if not sim:
                result = g_dev['cam'].expose_command(req, opt)
            else:
                result['FWHM'] = new_spot
                result['mean_focus'] = d1
            spot6 = result['FWHM']
            foc_pos4 = result['mean_focus']
            print('\n\n\nFound best focus at:  ', foc_pos4,' measured is:  ',  round(spot6, 2), '\n\n\n')
        else:
            print('Coarse_focus did not converge. Moving back to starting focus:  ', foc_pos0)
            g_dev['foc'].focuser.Move((foc_start)*g_dev['foc'].micron_to_steps)
        print("Returning to:  ", start_ra, start_dec)
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        if sim:
            g_dev['foc'].focuser.Move((foc_start)*g_dev['foc'].micron_to_steps)
        #  NB here we coudld re-solve with the overlay spot just to verify solution is sane.
        self.sequencer_hold = False   #Allow comand checks.
        self.guard = False


    def equatorial_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
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
       # ptr_utility.ModelOn = False
        
        self. sky_guard = True
        ha_deg_steps = (-72.5, -62.5, -52.5, -42.5, -32.5, -22.5, -12.5, -2.5, \
                         -7.5, -17.5, -27.5, -37.5, -47.5, -57.5, -67.5, \
                         2.5,  12.5, 22.5, 32.5, 42.5, 52.5, 62.5, 72.5, \
                         67.5, 57.5, 47.5, 37.5, 27.5, 17.5, 7.5)
        length = len(ha_deg_steps)
        count = 0
        print("Starting equatorial sweep.")
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1']['name'])
        for ha_degree_value in ha_deg_steps:
            target_ra = ra_fix(g_dev['mnt'].mount.SiderealTime - ha_degree_value/15.)
            target_dec = 0
            #     #  Go to closest Mag 7.5 Tycho * with no flip
            # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
            #                    g_dev['mnt'].mount.SiderealTime)
            # if focus_star is None:
            #     print("No near star, skipping.")   #This should not happen.
            #     continue
            #print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            #req = {'ra':  focus_star[1][1],
            #       'dec': focus_star[1][0]     #Note order in important (dec, ra)
            req = {'ra':  target_ra,
                   'dec': target_dec     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            st = ''
            enc_status = eval(self.redis_server.get('enc_status'))  #NB Is this current?
            while g_dev['mnt'].mount.Slewing or enc_status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)
            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 10,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator Run'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return
 
    def cross_pointing_run(self, req, opt, spacing=30, vertical=False, grid=False, alt_minimum=25):
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
       # ptr_utility.ModelOn = False
        
        self. sky_guard = True
        points = [(-2.5, 0), (-2.5, -30), (-30, 0), (-60, 0), (2.5, 75), (0.5, 45), \
                  (0.5, 0), (30, 0), (60, 0)]
        ha_deg_steps = (-72.5, -62.5, -52.5, -42.5, -32.5, -22.5, -12.5, -2.5, \
                         -7.5, -17.5, -27.5, -37.5, -47.5, -57.5, -67.5, \
                         2.5,  12.5, 22.5, 32.5, 42.5, 52.5, 62.5, 72.5, \
                         67.5, 57.5, 47.5, 37.5, 27.5, 17.5, 7.5)
        length = len(points)
        count = 0
        print("Starting cross, # of points:  ", length)
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1']['name'])
        for point_value in points:
            target_ra = ra_fix(g_dev['mnt'].mount.SiderealTime - point_value[0]/15.)
            target_dec = point_value[1]
            #     #  Go to closest Mag 7.5 Tycho * with no flip
            # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
            #                    g_dev['mnt'].mount.SiderealTime)
            # if focus_star is None:
            #     print("No near star, skipping.")   #This should not happen.
            #     continue
            #print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            #req = {'ra':  focus_star[1][1],
            #       'dec': focus_star[1][0]     #Note order in important (dec, ra)
            req = {'ra':  target_ra,
                   'dec': target_dec     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)
            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 30,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator Run'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return
    
    def sky_grid_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        #camera_name = str(self.config['camera']['camera_1']['name'])
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
        self.sky_guard = True
        #ptr_utility.ModelOn = False
        print("Starting sky sweep. ")
        g_dev['mnt'].unpark_command({}, {})
        if g_dev['enc'].is_dome:
            g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        g_dev['obs'].update_status()
        try:
            g_dev['scr'].screen_dark()
        except:
            pass
        g_dev['obs'].update_status()
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1']['name'])

        sid = g_dev['mnt'].mount.SiderealTime
        if req['gridType'] == 'medium':  # ~50
            grid = 4
        if req['gridType'] == 'coarse':  # ~30
            grid = 7
        if req['gridType'] == 'fine':    # ~100
            grid = 2

        grid_stars = tycho.az_sort_targets(sid, grid)  #4 produces about 50 targets.
        length = len(grid_stars)
        print(length, "Targets chosen for grid.")
        last_az = 0.25
        count = 0
        for grid_star in grid_stars:
            if grid_star is None:
                print("No near star, skipping.")   #This should not happen.
                count += 1
                continue
            if grid_star[0] < last_az:   #Consider also insisting on a reasonable HA, eg., >= altitude of the Pole.
               count += 1
               continue
            last_az = grid_star[0] + 0.01
            print("Going to near grid star " + str(grid_star) + " (az, (dec, ra)")
            req = {'ra':  grid_star[1][1],
                   'dec': grid_star[1][0]     #Note order is important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            time.sleep(0.5)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(1)  #Give a little extra time for mount to settle.
            g_dev['obs'].update_status()
            req = {'time': 30,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
            
        #g_dev['mnt'].park()
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return       

    def rel_sky_grid_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        #camera_name = str(self.config['camera']['camera_1']['name'])
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
        #breakpoint()
        self.sky_guard = True
        ptr_utility.ModelOn = False
        print("Starting sky sweep.")
        g_dev['mnt'].unpark_command({}, {})
        if g_dev['enc'].is_dome:
            g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1']['name'])

        sid = g_dev['mnt'].mount.SiderealTime
        if req['gridType'] == 'medium':  # ~50
            grid = 4
        if req['gridType'] == 'coarse':  # ~30
            grid = 7
        if req['gridType'] == 'fine':    # ~100
            grid = 2
        grid_stars = tycho.tpt_grid
        length = len(grid_stars)
        print(length, "Targets chosen for grid.")
        last_az = 0.25
        count = 0
        for grid_star in grid_stars:
            if grid_star is None:
                print("No near star, skipping.")   #This should not happen.
                count += 1
                continue
            if grid_star[0] < last_az:   #Consider also insisting on a reasonable HA
               count += 1
               continue
            last_az = grid_star[0] + 0.001
            print("Going to near grid star " + str(grid_star) + " (az, (dec, ra)")
            req = {'ra':  grid_star[1][1],
                   'dec': grid_star[1][0]     #Note order is important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            time.sleep(0.5)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 15,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
            
        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return    
       
    def vertical_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
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
        self.sky_guard = True
        #ptr_utility.ModelOn = False
        # dec_steps = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, \
        #              35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
        dec_steps = [-30, -20, -10, 0, 10, 20, 30, 40, 50, 55, 60, 65, 70, 75, 80, 82.5, \
                     77.5, 72.5, 67.5, 62.5, 57.5, 50, 45, 35, 25, 15, 5, -5, -15, -25]
        # dec_copy = dec_steps[:-1].copy()
        # dec_copy.reverse()
        # dec_steps += dec_copy
        length = len(dec_steps)*2
        count = 0
        print("Starting West dec sweep, ha = 0.1")
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1']['name'])
        for ha in [0.1, -0.1]:
            for degree_value in dec_steps:
                target_ra =  ra_fix(g_dev['mnt'].mount.SiderealTime - ha)

    
                #     #  Go to closest Mag 7.5 Tycho * with no flip
                # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
                #                    g_dev['mnt'].mount.SiderealTime)
                # if focus_star is None:
                #     print("No near star, skipping.")   #This should not happen.
                #     continue
                # print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
                req = {'ra':  target_ra,
                       'dec': degree_value} 
                opt = {}
                #Should have an Alt limit check here
                g_dev['mnt'].go_command(req, opt)
                st = ''
                while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                    if g_dev['mnt'].mount.Slewing: st += 'm>'
                    if g_dev['enc'].status['dome_slewing']: st += 'd>'
                    print(st)
                    st = ''
                    g_dev['obs'].update_status()
                    time.sleep(0.5)
                time.sleep(3)
                g_dev['obs'].update_status()
                req = {'time': 15,  'alias': 'sq01', 'image_type': 'experimental'}
                opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
                result = g_dev['cam'].expose_command(req, opt)
                g_dev['obs'].update_status()
                result = 'simulated result.'
                count += 1
                print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
                g_dev['obs'].update_status()
                result = 'simulated'
                print('Result:  ', result)
        g_dev['mnt'].stop_command()
        print("Vertical sweep completed. Happy reducing.")
        self.equitorial_pointing_run({},{})
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return

    def append_completes(self, block_id):
        camera = self.config['camera']['camera_1']['name']
        seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + camera)
        print("block_id:  ", block_id)
        lcl_list = seq_shelf['completed_blocks']
        lcl_list.append(block_id)   #NB NB an in-line append did not work!
        seq_shelf['completed_blocks']= lcl_list
        print('Appended completes contains:  ', seq_shelf['completed_blocks'])
        seq_shelf.close()
        return 
    
    def is_in_completes(self, check_block_id):
        camera = self.config['camera']['camera_1']['name']
        seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + camera)
        #print('Completes contains:  ', seq_shelf['completed_blocks'])
        if check_block_id in seq_shelf['completed_blocks']:
            seq_shelf.close()
            return True
        else:
            seq_shelf.close()
            return False

    
    def reset_completes(self):
        try:
            camera = self.config['camera']['camera_1']['name']
            seq_shelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + str(camera))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            print('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return 

    # import math
    # chip_x =1.4022
    # chip_y = 0.9362
    # def tile_field(field_x, field_y, chip_x, chip_y, overlap=12.5):
    #     trial_x = field_x/(chip_x* (100 - abs(overlap))/100)
    #     trial_y = field_y/(chip_y* (100 - abs(overlap))/100)
    #     proposed_x = round(trial_x + 0.25, 0)
    #     proposed_y = round(trial_y + 0.25, 0)
    #     span_x = chip_x*proposed_x
    #     span_y = chip_y*proposed_y
    #     over_span_x = span_x - field_x
    #     over_span_y = span_y - field_y
    #     span_y = chip_y*proposed_y
    #     if proposed_x - 1 >= 1:
    #         x_overlap = over_span_x/(proposed_x - 1)
    #     else:
    #         x_overlap =(field_x - span_x)/2
    #     if proposed_y - 1 >=  1:
    #         y_overlap = over_span_y/(proposed_y - 1)
    #     else:            
    #         y_overlap =(field_y - span_y)/2
    #     if 0 <= x_overlap  < overlap/100:
    #         proposed_x += 1
    #         span_x = chip_x*proposed_x
    #         over_span_x = span_x - field_x
    #         x_overlap = over_span_x/(proposed_x - 1)
    #     if 0 <= y_overlap < overlap/100:
    #         proposed_y += 1
    #         span_y = chip_y*proposed_y
    #         over_span_y = span_y - field_y
    #         y_overlap = over_span_y/(proposed_y - 1)          
    #     return(proposed_x, proposed_y, x_overlap, y_overlap)
    # for side in range(0,7):
    #     area = math.sqrt(2)**side
    #     print(side, round(area, 3))
    #     print(tile_field(side, side, chip_x, chip_y))


