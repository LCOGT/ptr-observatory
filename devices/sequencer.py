import time
import datetime
from datetime import timedelta
import copy
import json
from global_yard import g_dev
from astropy.coordinates import SkyCoord, AltAz, get_moon, Angle
from astropy import units as u
from astropy.time import Time
from astropy.io import fits
#from astropy.utils.data import get_pkg_data_filename
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans #convolve,
kernel = Gaussian2DKernel(x_stddev=2,y_stddev=2)
from astropy.stats import sigma_clip
import ephem
import shelve

import math
import shutil
import numpy as np
from numpy import inf
import os
import gc
from pyowm import OWM
from pyowm.utils import config

from devices.camera import Camera
from devices.filter_wheel import FilterWheel
from devices.mount import Mount
from devices.focuser import Focuser

#from pyowm.utils import timestamps
from glob import glob
import traceback
from ptr_utility import plog
#from pprint import pprint
import requests
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))
'''
'''

def authenticated_request(method: str, uri: str, payload: dict = None) -> str:

    # Populate the request parameters. Include data only if it was sent.
    base_url="https://api.photonranch.org/api"
    request_kwargs = { 
        "method": method,
        "timeout" : 10,
        "url": f"{base_url}/{uri}",
    }
    if payload is not None: 
        request_kwargs["data"] = json.dumps(payload)

    response = requests.request(**request_kwargs)
    return response.json()


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

        self.sequencer_message = '-'
        plog("sequencer connected.")       
        
        # Various on/off switches that block multiple actions occuring at a single time.
        self.af_guard = False
        self.block_guard = False
        self.bias_dark_latch = False   #NB NB NB Should these initially be defined this way?
        self.sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.morn_bias_dark_latch = False   #NB NB NB Should these initially be defined this way?
        self.cool_down_latch = False
        self.focussing=False
        self.flats_being_collected=False
        self.morn_bias_done = False
        self.eve_bias_done = False
        self.eve_bias_done = False
        self.eve_flats_done = False
        self.morn_flats_done = False
        self.eve_sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.clock_focus_latch=False        
        # A command so that some scripts can prevent all other scripts  and exposures from occuring.
        # quite important
        self.total_sequencer_control = False
        
        # Time of next slew is a variable that helps keep the scope positioned on the solar flat spot during flats
        self.time_of_next_slew = time.time()
        
        # During the night if the roof is shut (plus other conditions)
        # it will take a bias and a dark. These counters keep track of how many.
        self.nightime_bias_counter = 0
        self.nightime_dark_counter = 0
        
        
        # Nightly_reset resets all the values back to normal at the end of the night
        # In preparation for the next one.
        self.nightly_reset_complete = False
        
        # An end of night token is put into the upload queue
        # once the evening has ended.
        self.end_of_night_token_sent = False
        
        # Makes sure only one big focus occurs at start of night
        self.night_focus_ready=False
        
        # This command flushes the list of completed projects,
        # allowing them to be run tongiht
        self.reset_completes()  

        # Only need to report the observing has begun once.
        self.reported_on_observing_period_beginning=False

        # Pulse timer is set to send a simple '.' every 30 seconds so the console knows it is alive
        self.pulse_timer=time.time()
                
        
        # Load up focus and pointing catalogues
        # slight differences. Focus has more clumped bright stars but pointing catalogue contains a larger range
        # of stars and has full sky coverage, wheras focus does not.
        self.focus_catalogue = np.genfromtxt('support_info/focusCatalogue.csv', delimiter=',')
        self.pointing_catalogue = np.genfromtxt('support_info/pointingCatalogue.csv', delimiter=',')

       
        # The stop script flag sends a signal to all running threads to break out
        # and return to nothing doing.
        self.stop_script_called=False
        self.stop_script_called_time=time.time()

        # There are some automations that start up when a roof recently opens
        # that need to respond to that.         
        self.last_roof_status = 'Closed'
        self.time_roof_last_opened = time.time() - 1300
        
        # Sequencer keeps track of the endtime of a
        # currently running block so that seq and others
        # can know when to cancel out of the block        
        self.blockend = None
        
        
        # We keep track on when we poll for projects
        # It doesn't have to be quite as swift as real-time.
        self.project_call_timer = time.time() -60
        
        self.rotator_has_been_homed_this_evening=False

    def wait_for_slew(self):    
        """
        A function called when the code needs to wait for the telescope to stop slewing before undertaking a task.
        """    
        try:
            if not g_dev['mnt'].mount.AtPark:              
                movement_reporting_timer=time.time()
                while g_dev['mnt'].mount.Slewing: 
                    if time.time() - movement_reporting_timer > 2.0:
                        plog( 'm>')
                        movement_reporting_timer=time.time()

                    g_dev['obs'].update_status(mount_only=True, dont_wait=True)            
                
        except Exception:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            if g_dev['mnt'].theskyx:
                self.kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)
            else:
                plog(traceback.format_exc())
                breakpoint() 
        return 

    def get_status(self):
        status = {
            "active_script": None,
            "sequencer_busy":  False
        }
        
        return status


    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        g_dev['cam'].user_id = command['user_id']
        g_dev['cam'].user_name = command['user_name']
        action = command['action']
        try:
            script = command['required_params']['script']
        except:
            script = None
        if action == "run" and script == 'focusAuto':
            self.auto_focus_script(req, opt, skip_timer_check=True)
        elif action == "run" and script == 'focusExtensive':   
             # Autofocus
            req2 = {'target': 'near_tycho_star', 'area': 150}
            opt = {}
            self.extensive_focus_script(req2, opt, throw = g_dev['foc'].throw)
        elif action == "fixpointingscript":
            g_dev["obs"].send_to_user("Running a couple of auto-centering exposures.")
            self.centering_exposure()
        elif action == "autofocus": # this action is the front button on Camera, so FORCES an autofocus
            g_dev["obs"].send_to_user("Starting up the autofocus procedure.")
            g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                days=1
            )  # Initialise last focus as yesterday
            self.auto_focus_script(req, opt, skip_timer_check=True)
        elif action == "run" and script == 'focusFine':
            self.coarse_focus_script(req, opt)
        elif action == "run" and script == 'collectScreenFlats':
            self.screen_flat_script(req, opt)
        elif action == "run" and script == 'collectSkyFlats':
            self.sky_flat_script(req, opt)
        elif action == "run" and script == 'restackLocalCalibrations':
            self.regenerate_local_masters()
        elif action == "run" and script in ['pointingRun']:
            self.sky_grid_pointing_run(max_pointings=req['numPointingRuns'], alt_minimum=req['minAltitude'])
        elif action == "run" and script in ("collectBiasesAndDarks"):
            self.bias_dark_script(req, opt, morn=True)
        elif action == "run" and script == 'takeLRGBStack':
            self.take_lrgb_stack(req, opt)
        elif action == "run" and script == "takeO3HaS2N2Stack":
            self.take_lrgb_stack(req, opt)
        elif action.lower() in ["stop", "cancel"] or ( action == "run" and script == "stopScript"):
            
            #A stop script command flags to the running scripts that it is time to stop 
            #activity and return. This period runs for about 30 seconds.
            g_dev["obs"].send_to_user("A Stop Script has been called. Cancelling out of running scripts over 30 seconds.")
            self.stop_script_called=True
            self.stop_script_called_time=time.time()
            # Cancel out of all running exposures. 
            g_dev['obs'].cancel_all_activity()          
            
        elif action == "home":
            g_dev["obs"].send_to_user("Sending the mount to home.")
            g_dev['mnt'].home_command()

        elif action == 'run' and script == 'findFieldCenter':
            g_dev['mnt'].go_command(ra=req['ra'], dec=req['dec'], calibrate=True, auto_center=True)
        elif action == 'run' and script == 'calibrateAtFieldCenter':
            g_dev['mnt'].go_command(ra=req['ra'], dec=req['dec'], calibrate=True, auto_center=False)
        else:
            plog('Sequencer command:  ', command, ' not recognized.')


    def park_and_close(self):
        try:
            if not g_dev['mnt'].mount.AtParK:   ###Test comment here
                g_dev['mnt'].park_command({}, {}) # Get there early
        except:
            plog("Park not executed during Park and Close" )



    ###############################
    #       Sequencer Commands and Scripts
    ###############################
    def manager(self):
        '''
        This is called by the update loop.   Call from local status probe was removed
        #on 20211026 WER
        This is where scripts are automagically started.  Be careful what you put in here.
        Scripts must not block too long or they must provide for periodic calls to check status.
        '''
        

        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

        if time.time()-self.pulse_timer >30:
            self.pulse_timer=time.time()
            plog('.')
        
        if (
            (datetime.datetime.now() - g_dev['obs'].observing_status_timer)
        ) > datetime.timedelta(minutes=g_dev['obs'].observing_check_period):
            g_dev['obs'].ocn_status = g_dev['obs'].get_weather_status_from_aws()
            g_dev['obs'].observing_status_timer = datetime.datetime.now()

        
        if (
            (datetime.datetime.now() - g_dev['obs'].enclosure_status_timer)
        ) > datetime.timedelta(minutes=g_dev['obs'].enclosure_check_period):
            g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()
            g_dev['obs'].enclosure_status_timer = datetime.datetime.now()
        
        enc_status = g_dev['obs'].enc_status
        events = g_dev['events']
        
        
        # Do this in case of WEMA faults.... they can crash these sequencer 
        # things when it looks for shutter_status
        if enc_status == None:
            enc_status = {'shutter_status': 'Unknown'}
            enc_status['enclosure_mode'] = 'Automatic'        
       
        
        if (events['Nightly Reset'] <= ephem_now < events['End Nightly Reset']):
             if self.nightly_reset_complete == False:
                 self.nightly_reset_complete = True
                 self.nightly_reset_script()
                
        if ((g_dev['events']['Cool Down, Open'] <= ephem_now < g_dev['events']['Observing Ends'])):

            self.nightly_reset_complete = False            
        
        if not self.total_sequencer_control:
            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands turned off
            # So that if a sequencer script starts running, we don't get an odd request out 
            # of nowhere that knocks it out
            g_dev['obs'].stop_processing_command_requests = True
            ###########################################################################
            
            # This bit is really to get the scope up and running if the roof opens
            if ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends'])) and not self.cool_down_latch and \
                g_dev['obs'].open_and_enabled_to_observe and not g_dev['obs'].scope_in_manual_mode and g_dev['mnt'].mount.AtPark and ((time.time() - self.time_roof_last_opened) < 300) :
    
                self.nightly_reset_complete = False
                self.cool_down_latch = True
                self.reset_completes()                    
    
                if (g_dev['events']['Observing Begins'] < ephem_now < g_dev['events']['Observing Ends']):
                    # Move to reasonable spot
                    if g_dev['mnt'].mount.Tracking == False:
                        if g_dev['mnt'].mount.CanSetTracking:   
                            g_dev['mnt'].mount.Tracking = True
                        else:
                            plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
    
                    g_dev['mnt'].go_command(alt=70,az= 70)
                    g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                        days=1
                    )  # Initialise last focus as yesterday
                    g_dev['foc'].set_initial_best_guess_for_focus()
                    # Autofocus
                    req2 = {'target': 'near_tycho_star', 'area': 150}
                    opt = {}
                    plog ("Running initial autofocus upon opening observatory")
                    
                    self.auto_focus_script(req2, opt)
                else:
                    self.night_focus_ready=True
                        
                       
                self.cool_down_latch = False
    
                    
            # If in post-close and park era of the night, check those two things have happened!       
            if (events['Close and Park'] <= ephem_now < events['End Morn Bias Dark']) and not g_dev['obs'].scope_in_manual_mode:
                
                if not g_dev['mnt'].mount.AtPark:  
                    plog ("Found telescope unparked after Close and Park, parking the scope")
                    g_dev['mnt'].home_command()
                    g_dev['mnt'].park_command()                
                
            if not self.bias_dark_latch and not g_dev['obs'].scope_in_manual_mode and ((events['Eve Bias Dark'] <= ephem_now < events['End Eve Bias Dark']) and \
                 self.config['auto_eve_bias_dark'] and not self.eve_bias_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations):   #events['End Eve Bias Dark']) and \
                
                self.bias_dark_latch = True
                req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 45, \
                       'numOfDark': 15, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 360, \
                       'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  # NB NB All of the prior is obsolete
                opt = {}
                
             
                self.bias_dark_script(req, opt, morn=False)
                self.eve_bias_done = True
                self.bias_dark_latch = False
                
            if (time.time() - g_dev['seq'].time_roof_last_opened > 1200 ) and not self.eve_sky_flat_latch and not g_dev['obs'].scope_in_manual_mode and ((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
                   and self.config['auto_eve_sky_flat'] and g_dev['obs'].open_and_enabled_to_observe and not self.eve_flats_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations):
    
                self.eve_sky_flat_latch = True
                self.current_script = "Eve Sky Flat script starting"
                
                g_dev['foc'].set_initial_best_guess_for_focus()
                
                self.sky_flat_script({}, {}, morn=False)   #Null command dictionaries
                
                if g_dev['mnt'].mount.Tracking == False:
                    if g_dev['mnt'].mount.CanSetTracking:   
                        g_dev['mnt'].mount.Tracking = True
                    else:
                        plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
                self.eve_sky_flat_latch = False
                self.eve_flats_done = True
                
    
            if ((g_dev['events']['Clock & Auto Focus']  <= ephem_now < g_dev['events']['Observing Begins'])) \
                    and self.night_focus_ready==True and not g_dev['obs'].scope_in_manual_mode and  g_dev['obs'].open_and_enabled_to_observe and not self.clock_focus_latch:
    
                self.nightly_reset_complete = False
                self.clock_focus_latch = True
    
                g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')
    
                # Move to reasonable spot
                if g_dev['mnt'].mount.Tracking == False:
                    if g_dev['mnt'].mount.CanSetTracking:   
                        g_dev['mnt'].mount.Tracking = True
                    else:
                        plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
    
                g_dev['mnt'].go_command(alt=70,az= 70)
                
                self.wait_for_slew()
                
                # Homing Rotator for the evening.
                try:
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    g_dev['obs'].send_to_user("Rotator being homed at beginning of night.", p_level='INFO')
                    time.sleep(0.5)
                    g_dev['rot'].home_command()
                    g_dev['mnt'].go_command(alt=70,az= 70)
                    self.wait_for_slew()
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    self.rotator_has_been_homed_this_evening=True
                except:
                    plog ("no rotator to home or wait for.")
                
                
                g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                    days=1
                )  # Initialise last focus as yesterday
                
                g_dev['foc'].set_initial_best_guess_for_focus()
    
                # Autofocus
                req2 = {'target': 'near_tycho_star', 'area': 150}
                opt = {}
                self.extensive_focus_script(req2, opt, throw = g_dev['foc'].throw)
                
                g_dev['obs'].send_to_user("End of Focus and Pointing Run. Waiting for Observing period to begin.", p_level='INFO')
                
                self.night_focus_ready=False
                self.clock_focus_latch = False
    
    
            if (events['Observing Begins'] <= ephem_now \
                                       < events['Observing Ends']) and not self.block_guard and not g_dev["cam"].exposure_busy\
                                       and  (time.time() - self.project_call_timer > 10) and not g_dev['obs'].scope_in_manual_mode  and g_dev['obs'].open_and_enabled_to_observe and self.clock_focus_latch == False:
                                         
                try:
                    self.nightly_reset_complete = False
                    self.block_guard = True
                    
                    if not self.reported_on_observing_period_beginning:
                        self.reported_on_observing_period_beginning=True
                        g_dev['obs'].send_to_user("Observing Period has begun.", p_level='INFO')
                   
                    self.project_call_timer = time.time()
                    
                    self.update_calendar_blocks()
    
                    # only need to bother with the rest if there is more than 0 blocks. 
                    if not len(self.blocks) > 0:
                        self.block_guard=False
                        g_dev['seq'].blockend= None
                    else:
                        now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'                    
                        identified_block=None
                        
                        for block in self.blocks:  #  This merges project spec into the blocks.
                           
                            if (block['start'] <= now_date_timeZ < block['end'])  and not self.is_in_completes(block['event_id']):
                                                                   
                                try:
                                    
                                    url_proj = "https://projects.photonranch.org/projects/get-project"
                                    request_body = json.dumps({
                                      "project_name": block['project_id'].split('#')[0],
                                      "created_at": block['project_id'].split('#')[1],
                                    })
                                    project_response=reqs.post(url_proj, request_body, timeout=10)
                                    
    
                                    if project_response.status_code ==200:  
                                        self.block_guard = True
                                        block['project']=project_response.json()
                                        identified_block=copy.deepcopy(block)
                                except:
                                    plog(traceback.format_exc())
                                    breakpoint()
                                    
                        if identified_block == None:
                            self.block_guard = False   # Changed from True WER on 20221011@2:24 UTC
                            g_dev['seq'].blockend= None
                            return   # Do not try to execute an empty block.
                        
                        if identified_block['project_id'] in ['none', 'real_time_slot', 'real_time_block']:
                            self.block_guard = False   # Changed from True WER on 20221011@2:24 UTC
                            g_dev['seq'].blockend= None
                            return   # Do not try to execute an empty block.
                        
    
                        if identified_block['project'] == None:
                            plog (identified_block)
                            plog ("Skipping a block that contains an empty project")
                            self.block_guard=False
                            g_dev['seq'].blockend= None
                            return
    
                        completed_block = self.execute_block(identified_block)  #In this we need to ultimately watch for weather holds.
                        try:
                            self.append_completes(completed_block['event_id'])
                        except:
                            plog ("block complete append didn't work")
                            plog(traceback.format_exc())
                        self.block_guard=False
                        g_dev['seq'].blockend = None                        
                                                             
                except:
                    plog(traceback.format_exc())
                    plog("Hang up in sequencer.")
                    
            if (time.time() - g_dev['seq'].time_roof_last_opened > 1200 ) and not self.morn_sky_flat_latch and ((events['Morn Sky Flats'] <= ephem_now < events['End Morn Sky Flats']) and \
                   self.config['auto_morn_sky_flat']) and not g_dev['obs'].scope_in_manual_mode and not self.morn_flats_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations and g_dev['obs'].open_and_enabled_to_observe:
    
                self.morn_sky_flat_latch = True
                
                self.current_script = "Morn Sky Flat script starting"
                
                self.sky_flat_script({}, {}, morn=True)   #Null command dictionaries
                                        
                self.morn_sky_flat_latch = False
                self.morn_flats_done = True
                
            
            if not self.morn_bias_dark_latch and (events['Morn Bias Dark'] <= ephem_now < events['End Morn Bias Dark']) and \
                      self.config['auto_morn_bias_dark'] and not g_dev['obs'].scope_in_manual_mode and not  self.morn_bias_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations: # and g_dev['enc'].mode == 'Automatic' ):
    
                self.morn_bias_dark_latch = True
                req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 63, \
                        'numOfDark': 31, 'darkTime': 600, 'numOfDark2': 31, 'dark2Time': 600, \
                        'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  #This specificatin is obsolete
                opt = {}
    
                self.park_and_close()
                
                self.bias_dark_script(req, opt, morn=True)
    
                self.park_and_close()
                self.morn_bias_dark_latch = False
                self.morn_bias_done = True
            
            
            if events['Sun Rise'] <= ephem_now and not self.end_of_night_token_sent:
                
                self.end_of_night_token_sent = True
                # Sending token to AWS to inform it that all files have been uploaded
                plog ("sending end of night token to AWS")
                
                isExist = os.path.exists(g_dev['obs'].obsid_path + 'tokens')
                yesterday = datetime.datetime.now() - timedelta(1)
                runNight=datetime.datetime.strftime(yesterday, '%Y%m%d') 
                if not isExist:
                    os.makedirs(g_dev['obs'].obsid_path + 'tokens')
                runNightToken= g_dev['obs'].obsid_path + 'tokens/' + self.config['obs_id'] + runNight + '.token'
                with open(runNightToken, 'w') as f:
                    f.write('Night Completed')
                image = (g_dev['obs'].obsid_path + 'tokens/', self.config['obs_id'] + runNight + '.token')
                g_dev['obs'].ptrarchive_queue.put((30000000000, image), block=False)
                g_dev['obs'].send_to_user("End of Night Token sent to AWS.", p_level='INFO')
                
            #Here is where observatories who do their biases at night... well.... do their biases!
            #If it hasn't already been done tonight.        
            if self.config['auto_midnight_moonless_bias_dark'] and not g_dev['obs'].scope_in_manual_mode:
                # Check it is in the dark of night
                if  (events['Astro Dark'] <= ephem_now < events['End Astro Dark']):     
                    # Check that there isn't any activity indicating someone using it...
                    if (time.time() - g_dev['obs'].time_of_last_exposure) > 900 and (time.time() - g_dev['obs'].time_of_last_slew) > 900:
                        # Check no other commands or exposures are happening
                        if g_dev['obs'].cmd_queue.empty() and not g_dev["cam"].exposure_busy:
                            # If enclosure is shut for maximum darkness
                            if 'Closed' in enc_status['shutter_status']  or 'closed' in enc_status['shutter_status']:
                                # Check the temperature is in range
                                currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
                                moondata=get_moon(Time.now()).transform_to(currentaltazframe)                        
                                if (moondata.alt.deg < -15):
                                    # If the moon is way below the horizon                        
                                    if g_dev['obs'].camera_sufficiently_cooled_for_calibrations:
                                        if self.nightime_bias_counter < self.config['camera']['camera_1_1']['settings']['number_of_bias_to_collect']:
                                            plog ("It is dark and the moon isn't up! Lets do a bias!")  
                                            g_dev['mnt'].park_command({}, {})
                                            plog("Exposing 1x1 bias frame.")
                                            req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                                            opt = {'area': "Full", 'count': 1, 'bin': 1 , \
                                                   'filter': 'dark'}
                                            self.nightime_bias_counter = self.nightime_bias_counter + 1
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            # these exposures shouldn't reset these timers
                                            g_dev['obs'].time_of_last_exposure = time.time() - 840
                                            g_dev['obs'].time_of_last_slew = time.time() - 840
                                        if self.nightime_dark_counter < self.config['camera']['camera_1_1']['settings']['number_of_dark_to_collect']:
                                            plog ("It is dark and the moon isn't up! Lets do a dark!")  
                                            g_dev['mnt'].park_command({}, {})
                                            dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']
                                            plog("Exposing 1x1 dark exposure:  " + str(dark_exp_time) )
                                            req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                                            opt = {'area': "Full", 'count': 1, 'bin': 1, \
                                                    'filter': 'dark'}
                                            self.nightime_dark_counter = self.nightime_dark_counter + 1
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                               do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            # these exposures shouldn't reset these timers
                                            g_dev['obs'].time_of_last_exposure = time.time() - 840
                                            g_dev['obs'].time_of_last_slew = time.time() - 840                                    
            
            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands turned back on
            # So that we can process any new manual commands that come in.
            g_dev['obs'].stop_processing_command_requests = False
            g_dev['obs'].scan_requests()
            ###########################################################################                            
        
        
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

    def execute_block(self, block_specification):
        """
        This function executes an observing block provided by a calendar event.
        """    
        
        self.block_guard = True        
        
        if (ephem.now() < g_dev['events']['Civil Dusk'] ) or \
            (g_dev['events']['Civil Dawn']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT RUNNING PROJECT BLOCK -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A project block was rejected as it is during the daytime.")            
            return
        
        g_dev['obs'].update()
        
        plog('|n|n Starting a new project!  \n')
        plog(block_specification, ' \n\n\n')

        calendar_event_id=block_specification['event_id']

        
        # NB we assume the dome is open and already slaving.
        block = copy.deepcopy(block_specification)
        
        g_dev['mnt'].unpark_command({}, {})
        g_dev['mnt'].Tracking = True   
        
                
        # this variable is what we check to see if the calendar
        # event still exists on AWS. If not, we assume it has been
        # deleted or modified substantially.
        calendar_event_id = block_specification['event_id']

        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            try:
                g_dev['obs'].update()
                dest_ra = float(target['ra']) - \
                    float(block_specification['project']['project_constraints']['ra_offset'])/15.

                dest_dec = float(target['dec']) - float(block_specification['project']['project_constraints']['dec_offset'])
                dest_ra, dest_dec = ra_dec_fix_hd(dest_ra, dest_dec)
                dest_name =target['name']

                user_name = block_specification['creator']
                user_id = block_specification['creator_id']
                user_roles = ['project']
                
                longstackname=block_specification['project']['created_at'].replace('-','').replace(':','') # If longstack is to be used.

            except Exception as e:                
                plog ("Could not execute project due to poorly formatted or corrupt project")
                plog (e)
                g_dev['obs'].send_to_user("Could not execute project due to poorly formatted or corrupt project", p_level='INFO')
                continue

            try:
                g_dev['mnt'].get_mount_coordinates()
            except:
                pass            
            
            g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
            
            
            if not self.rotator_has_been_homed_this_evening:
                plog ("rotator hasn't been homed this evening, doing that now")
                # Homing Rotator for the evening.
                try:
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    g_dev['obs'].send_to_user("Rotator being homed as this has not been done this evening.", p_level='INFO')
                    time.sleep(0.5)
                    g_dev['rot'].home_command()
                    g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
                    self.wait_for_slew()
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    self.rotator_has_been_homed_this_evening=True
                except:
                    plog ("no rotator to home or wait for.")
            
            # Undertake a focus if necessary before starting observing the target
            if g_dev["foc"].last_focus_fwhm == None or g_dev["foc"].focus_needed == True:

                g_dev['obs'].send_to_user("Running an initial autofocus run.")

                req2 = {'target': 'near_tycho_star', 'area': 150}
                
                self.auto_focus_script(req2, {}, throw = g_dev['foc'].throw)
                g_dev["foc"].focus_needed = False
                
            g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
            
            # Quick pointing check and re_seek at the start of each project block
            # Otherwise everyone will get slightly off-pointing images
            # Necessary
            plog ("Taking a quick pointing check and re_seek for new project block")
            result = self.centering_exposure(no_confirmation=True, try_hard=True)
                        
            # This actually replaces the "requested" dest_ra by the actual centered pointing ra and dec. 
            dest_ra = g_dev['mnt'].mount.RightAscension   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
            dest_dec = g_dev['mnt'].mount.Declination
            
            if result == 'blockend':
                plog ("End of Block, exiting project block.")      
                return block_specification
            
            if result == 'calendarend':
                plog ("Calendar Item containing block removed from calendar")
                plog ("Site bailing out of running project")
                return block_specification
            
            g_dev['obs'].update()
            
            pa = float(block_specification['project']['project_constraints']['position_angle'])
            if abs(pa) > 0.01:
                try:
                    g_dev['rot'].rotator.MoveAbsolute(pa)   #Skip rotator move if nominally 0
                except:
                    pass

            # Input the global smartstack and longstack request from the project
            # Into the individual exposure requests
            try:
                # This is the "proper" way of doing things.
                do_long_stack=block['project']['project_constraints']['long_stack']
            except:
                # This is the old way for old projects
                do_long_stack=block['project']['exposures'][0]['longstack']
            try:                                
                # This is the "proper" way of doing things.
                do_smart_stack=block['project']['project_constraints']['smart_stack']
            except:
                # This is the old way for old projects
                do_smart_stack=block['project']['exposures'][0]['smartstack']

            #Compute how many to do.
            left_to_do = 0
            ended = False
            #  NB NB NB Any mosaic larger than +SQ should be specified in degrees and be square
            #  NB NB NB NB this is the source of a big error$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$!!!! WER 20220814
            for exposure in block['project']['exposures']:
                
                exposure['longstack'] = do_long_stack
                exposure['smartstack'] = do_smart_stack
                left_to_do += int(exposure['count'])

            plog("Left to do initial value:  ", left_to_do)
            req = {'target': 'near_tycho_star'}

            while left_to_do > 0 and not ended:                
                
                #cycle through exposures decrementing counts    MAY want to double check left-to do but do nut remultiply by 4
                for exposure in block['project']['exposures']:
                                        
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    g_dev['obs'].scan_requests()
                    foundcalendar=False
                    self.update_calendar_blocks()                    
                    for tempblock in self.blocks:
                        if tempblock['event_id'] == calendar_event_id :
                            foundcalendar=True
                            g_dev['seq'].blockend=tempblock['end']
                    if not foundcalendar:
                        plog ("could not find calendar entry, cancelling out of block.")
                        g_dev["obs"].send_to_user("Calendar block removed. Stopping project run.")   
                        
                        return block_specification
                    
                    plog ("Observing " + str(block['project']['project_targets'][0]['name']))

                    plog("Executing: ", exposure, left_to_do)
                    color = exposure['filter']
                    exp_time =  float(exposure['exposure'])
                    count = int(exposure['count'])
                    #  We should add a frame repeat count
                    imtype = exposure['imtype']

                    if count <= 0:
                         continue
                    
                    # These are waiting for a mosaic approach
                    offset = [(0., 0.)] #Zero(no) mosaic offset
                    pitch = 0.
                    pane = 0

                    for displacement in offset:

                        # MUCH safer to calculate these from first principles
                        # Than rely on an owner getting this right!
                        x_field_deg = (g_dev['cam'].pixscale * g_dev['cam'].imagesize_x) /3600
                        y_field_deg = (g_dev['cam'].pixscale * g_dev['cam'].imagesize_y) /3600
                        
                        # CURRENTLY NOT USED
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
                        # CURRENTLY NOT USED
                        
                        
                        if imtype in ['light'] and count > 0:                            

                            # Sort out Longstack and Smartstack names and switches
                            if exposure['longstack'] == False:
                                longstackswitch='no'
                                longstackname='no'
                            elif exposure['longstack'] == True:
                                longstackswitch='yes'
                                longstackname=block_specification['project']['created_at'].replace('-','').replace(':','')
                            else:
                                longstackswitch='no'
                                longstackname='no'
                            if exposure['smartstack'] == False:
                                smartstackswitch='no'
                            elif exposure['smartstack'] == True:
                                smartstackswitch='yes'
                            else:
                                smartstackswitch='no'

                            # Set up options for exposure and take exposure.
                            req = {'time': exp_time,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': imtype, 'smartstack' : smartstackswitch, 'longstackswitch' : longstackswitch, 'longstackname' : longstackname, 'block_end' : g_dev['seq'].blockend}   #  NB Should pick up filter and constants from config
                            opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': color, \
                                   'hint': block['project_id'] + "##" + dest_name, 'object_name': block['project']['project_targets'][0]['name'], 'pane': pane}
                            plog('Seq Blk sent to camera:  ', req, opt)

                            now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                            if g_dev['seq'].blockend != None:
                                if now_date_timeZ >= g_dev['seq'].blockend :                                
                                    left_to_do=0
                                    return
                            g_dev['obs'].update()
                            result = g_dev['cam'].expose_command(req, opt, user_name=user_name, user_id=user_id, user_roles=user_roles, no_AWS=False, solve_it=False, calendar_event_id=calendar_event_id)
                            g_dev['obs'].update()
                            try:
                                if result['stopped'] is True:
                                    g_dev['obs'].send_to_user("Project Stopped because Exposure cancelled")
                                    return block_specification
                            except:
                                pass
                           
                            count -= 1
                            exposure['count'] = count
                            left_to_do -= 1
                            plog("Left to do:  ", left_to_do)
                            
                            
                            if result == 'blockend':
                                left_to_do=0
                            
                            if result == 'calendarend':
                                left_to_do =0
                            
                            if result == 'roofshut':
                                left_to_do =0
                                
                            if result == 'outsideofnighttime':
                                left_to_do =0
                            
                            if g_dev["obs"].stop_all_activity:
                                plog('stop_all_activity cancelling out of exposure loop')
                                left_to_do =0  
                            
                            
                            
                        pane += 1

                    # Check that the observing time hasn't completed or then night has not completed. 
                    # If so, set ended to True so that it cancels out of the exposure block.
                    now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                    events = g_dev['events']
                    ended = left_to_do <= 0 or now_date_timeZ >= g_dev['seq'].blockend \
                            or ephem.now() >= events['Observing Ends']
                            
        plog("Project block has finished!")   
        return block_specification 


    def bias_dark_script(self, req=None, opt=None, morn=False):
        """
        This functions runs through automatically collecting bias and darks for the local calibrations.
        """    
        self.current_script = 'Bias Dark'
        if morn:
            ending = g_dev['events']['End Morn Bias Dark']
        else:
            ending = g_dev['events']['End Eve Bias Dark']
        while ephem.now() < ending :   #Do not overrun the window end
  
            bias_count = self.config['camera']['camera_1_1']['settings']['number_of_bias_to_collect']
            dark_count = self.config['camera']['camera_1_1']['settings']['number_of_dark_to_collect']
            dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']
            cycle_time = self.config['camera']['camera_1_1']['settings']['cycle_time']
            
            if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:   #ephem is units of a day
                self.bias_dark_latch = False
                break     #Terminate Bias dark phase if within taking a dark woudl run over.             
            
            g_dev['mnt'].park_command({}, {}) # Get there early

            b_d_to_do = bias_count + dark_count
            try:
                stride = bias_count//dark_count
                plog("Tobor will interleave a dark every  " + str(stride) + "  biases.")
                single_dark = True
            except:
                stride = bias_count   #Just do all of the biases first.
                single_dark = False
                
           
            while b_d_to_do > 0:
                g_dev['obs'].scan_requests()
                min_to_do = min(b_d_to_do, stride)
                plog("Expose " + str(stride) +" 1x1 bias frames.")
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'area': "Full", 'count': min_to_do, 'bin': 1 , \
                       'filter': 'dark'}                    
                    
                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                
                  
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                b_d_to_do -= min_to_do
                
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                    self.bias_dark_latch = False
                    return
                
                g_dev['obs'].update()
                
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                
                g_dev['obs'].scan_requests()
                
                if not single_dark:
                    
                    plog("Expose 1x1 dark of " \
                         + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count': 1, 'bin': 1, \
                            'filter': 'dark'}
                    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                       do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.") 
                        self.bias_dark_latch = False
                        return
                    b_d_to_do -= 1
                    g_dev['obs'].update()
                    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                        self.bias_dark_latch = False
                        break
                else:
                    plog("Expose 1x1 dark " + str(1) + " of " \
                             + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count': 1, 'bin': 1, \
                            'filter': 'dark'}
                    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                       do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.") 
                        self.bias_dark_latch = False
                        return
                    b_d_to_do -= 1
                    g_dev['obs'].update()
                    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                        self.bias_dark_latch = False
                        break
                        
                g_dev['obs'].scan_requests()
                g_dev['obs'].update()
                if ephem.now() + 30/86400 >= ending:
                    self.bias_dark_latch = False
                    break

            plog(" Bias/Dark acquisition is finished normally.")

            g_dev['mnt'].park_command({}, {}) # Get there early
            plog("Bias/Dark Phase has passed.")
            self.bias_dark_latch = False
            break
        self.bias_dark_latch = False
        return
            
    def collect_and_queue_neglected_fits(self):
        # UNDERTAKING END OF NIGHT ROUTINES
        
        # Go through and add any remaining fz files to the aws queue 
        plog ('Collecting orphaned fits and tokens to go up to PTR archive')
        dir_path=self.config['archive_path'] +'/' + g_dev['obs'].name + '/' + 'archive/'
        
        orphan_path=g_dev['obs'].orphan_path 
        cameras=glob(dir_path + "*/")
        
        # Move all fits.fz to the orphan folder
        for camera in cameras:
            nights = glob(camera + '*/')
            
            for obsnight in nights:
                orphanfits=glob(obsnight + 'raw/*.fits.fz')
                
                for orphanfile in orphanfits:
                    try:
                        shutil.move(orphanfile, orphan_path)
                    except:
                        print ("Couldn't move orphan: " + str(orphanfile) +', deleting.')
                        g_dev['obs'].laterdelete_queue.put(orphanfile, block=False)
                        
        # Add all fits.fz members to the AWS queue
        bigfzs=glob(orphan_path + '*.fz')

        for fzneglect in bigfzs:         
            g_dev['obs'].enqueue_for_PTRarchive(56000000, orphan_path, fzneglect.split('orphans')[-1].replace('\\',''))
           
        bigtokens=glob(g_dev['obs'].obsid_path + 'tokens/*.token')
        for fzneglect in bigtokens:
            g_dev['obs'].enqueue_for_PTRarchive(56000001, g_dev['obs'].obsid_path + 'tokens/', fzneglect.split('tokens')[-1].replace('\\',''))
   
    
    def nightly_reset_script(self):
        # UNDERTAKING END OF NIGHT ROUTINES
        # Never hurts to make sure the telescope is parked for the night        
        self.park_and_close()

        self.reported_on_observing_period_beginning=False

        self.rotator_has_been_homed_this_evening=False

        self.eve_flats_done = False
        self.morn_flats_done = False
        self.morn_bias_done = False
        self.eve_bias_done = False
        
        self.nightime_bias_counter = 0
        self.nightime_dark_counter = 0
        self.night_focus_ready=False

        # set safety defaults at startup
        g_dev['obs'].scope_in_manual_mode=g_dev['obs'].config['scope_in_manual_mode']        
        g_dev['obs'].sun_checks_on=g_dev['obs'].config['sun_checks_on']
        g_dev['obs'].moon_checks_on=g_dev['obs'].config['moon_checks_on']
        g_dev['obs'].altitude_checks_on=g_dev['obs'].config['altitude_checks_on']
        g_dev['obs'].daytime_exposure_time_safety_on=g_dev['obs'].config['daytime_exposure_time_safety_on']
        g_dev['obs'].mount_reference_model_off= g_dev['obs'].config['mount_reference_model_off'],
        g_dev['obs'].admin_owner_commands_only = False
        g_dev['obs'].assume_roof_open=False

        # Check the archive directory and upload any big fits that haven't been uploaded
        # wait until the queue is empty before mopping up
        self.collect_and_queue_neglected_fits()
        
        # At this stage, we want to empty the AWS Queue!
        # We are about to pull all the fits.fz out from their folders
        # And dump them in the orphans folder so we want the queue
        # cleared to reconstitute it.
        plog ("Emptying AWS Queue To Reconstitute it from the Orphan Directory")
        with g_dev['obs'].ptrarchive_queue.mutex:
            g_dev['obs'].ptrarchive_queue.queue.clear()

        while (not g_dev['obs'].ptrarchive_queue.empty()):
            plog ("Waiting for the AWS queue to complete it's last job")
            time.sleep(1)              

        # Before Culling, making sure we go through and harvest
        # all the orphaned and neglected files that actually
        # do need to get to the PTRarchive
        self.collect_and_queue_neglected_fits()
        
        
        # Culling the archive. This removes old files
        # which allows us to maintain some reasonable harddisk space usage
        if self.config['archive_age'] > 0 :
            plog (g_dev['obs'].obsid_path + 'archive/')
            dir_path=g_dev['obs'].obsid_path + 'archive/'
            cameras=glob(dir_path + "*/")
            plog (cameras)
            for camera in cameras:  # Go through each camera directory
                plog ("*****************************************")
                plog ("Camera: " + str(camera))
                timenow_cull=time.time()
                directories=glob(camera + "*/")
                deleteDirectories=[]
                deleteTimes=[]
                for q in range(len(directories)):
                    if 'localcalibrations' in directories[q] or 'orphans' in directories[q] or 'calibmasters' in directories[q] or 'lng' in directories[q] or 'seq' in directories[q]:
                        pass
                    elif ((timenow_cull)-os.path.getmtime(directories[q])) > (self.config['archive_age'] * 24* 60 * 60) :
                        deleteDirectories.append(directories[q])
                        deleteTimes.append(((timenow_cull)-os.path.getmtime(directories[q])) /60/60/24/7)
                plog ("These are the directories earmarked for  ")
                plog ("Eternal destruction. And how old they are")
                plog ("in weeks\n")
                g_dev['obs'].send_to_user("Culling " + str(len(deleteDirectories)) +" from the local archive.", p_level='INFO')
                for entry in range(len(deleteDirectories)):
                    plog (deleteDirectories[entry] + ' ' + str(deleteTimes[entry]) + ' weeks old.')
                    try:
                        shutil.rmtree(deleteDirectories[entry])
                    except:
                        plog ("Could not remove: " + str(deleteDirectories[entry]) + ". Usually a file is open in that directory.")

        # Clear out smartstacks directory
        plog ("removing and reconstituting smartstacks directory")
        try:
            shutil.rmtree(g_dev['obs'].obsid_path + "smartstacks")
        except:
            plog ("problems with removing the smartstacks directory... usually a file is open elsewhere")
        time.sleep(20)
        if not os.path.exists(g_dev['obs'].obsid_path + "smartstacks"):
            os.makedirs(g_dev['obs'].obsid_path + "smartstacks")

        # Reopening config and resetting all the things.
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events(endofnightoverride='yes')
        self.astro_events.display_events()
        g_dev['obs'].astro_events = self.astro_events


        
        '''
        Send the config to aws.
        '''
        uri = f"{self.config['obs_id']}/config/"
        self.config['events'] = g_dev['events']
        response = authenticated_request("PUT", uri, self.config)
        if response:
            plog("Config uploaded successfully.")

        # If you are using TheSkyX, then update the autosave path
        if self.config['camera']['camera_1_1']['driver'] == "CCDSoft2XAdaptor.ccdsoft5Camera":
            g_dev['cam'].camera.AutoSavePath = g_dev['obs'].obsid_path +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d')
            try:
                os.mkdir(g_dev['obs'].obsid_path +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d'))
            except:
                plog ("Couldn't make autosave directory")

        # Resetting complete projects
        plog ("Nightly reset of complete projects")
        self.reset_completes()
        g_dev['obs'].events_new = None
        g_dev['obs'].reset_last_reference()
        if self.config['mount']['mount1']['permissive_mount_reset'] == 'yes':
           g_dev['mnt'].reset_mount_reference()
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000

        # Resetting sequencer stuff
        self.connected = True
        self.description = "Sequencer for script execution."        
        self.sequencer_message = '-'
        plog("sequencer reconnected.")
        plog(self.description)
        self.af_guard = False
        self.block_guard = False
        g_dev['seq'].blockend= None
        self.time_of_next_slew = time.time()
        self.bias_dark_latch = False
        self.sky_flat_latch = False
        self.eve_sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.morn_bias_dark_latch = False
        self.clock_focus_latch = False
        self.cool_down_latch = False
        self.clock_focus_latch = False
        
        self.morn_bias_done = False
        self.eve_bias_done = False
        self.eve_flats_done = False
        self.morn_flats_done = False
        
        self.reset_completes()

        # Allow early night focus
        self.night_focus_ready==True
        
        self.nightime_bias_counter = 0
        self.nightime_dark_counter = 0
        
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


        # Reopening config and resetting all the things.
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events()
        self.astro_events.display_events()
        g_dev['obs'].astro_events = self.astro_events

        self.nightly_reset_complete = True
        
        g_dev['mnt'].theskyx_tracking_rescues = 0

        self.opens_this_evening=0
        
        
        self.stop_script_called=False
        self.stop_script_called_time=time.time()
        
        # No harm in doubly checking it has parked
        g_dev['mnt'].park_command({}, {})
        
        
        self.end_of_night_token_sent = False
        
        # Now time to regenerate the local masters
        
        self.regenerate_local_masters()
        
        # Daily reboot of necessary windows 32 programs *Cough* Theskyx *Cough*
        if g_dev['mnt'].theskyx: # It is only the mount that is the reason theskyx needs to reset
            self.kill_and_reboot_theskyx(-1,-1)      
        
        return
    
    def kill_and_reboot_theskyx(self, returnra, returndec): # Return to a given ra and dec or send -1,-1 to remain at park
        os.system("taskkill /IM TheSkyX.exe /F")
        os.system("taskkill /IM TheSky64.exe /F")
        time.sleep(16) 
        retries=0
        while retries <5:
            try:
                Mount(self.config['mount']['mount1']['driver'], 
                               g_dev['obs'].name,
                               self.config['mount']['mount1']['settings'], 
                               g_dev['obs'].config, 
                               g_dev['obs'].astro_events, 
                               tel=True)
                
                
                # If theskyx is controlling the camera and filter wheel, reconnect the camera and filter wheel
                if g_dev['cam'].theskyx:
                    Camera(self.config['camera']['camera_1_1']['driver'], 
                                    g_dev['cam'].name, 
                                    self.config)
                    time.sleep(10)
                if self.config['filter_wheel']['filter_wheel1']['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                    FilterWheel('CCDSoft2XAdaptor.ccdsoft5Camera', 
                                         g_dev['obs'].name, 
                                         self.config)
                
                    time.sleep(10)
                
                if self.config['focuser']['focuser1']['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                    Focuser('CCDSoft2XAdaptor.ccdsoft5Camera', 
                                         g_dev['obs'].name,  self.config)
                    time.sleep(10)
                
                if returnra == -1 or returndec == -1:
                    g_dev['mnt'].park_command({}, {})
                    #pass
                else:
                    g_dev['mnt'].park_command({}, {})
                    g_dev['mnt'].go_command(ra=returnra, dec=returndec)
            
                time.sleep(10)
                retries=6
            except:
                retries=retries+1
                time.sleep(60)
                if retries ==4:
                    plog(traceback.format_exc())
                    breakpoint()
        
        return
        
    def regenerate_local_masters(self):
        
        
        g_dev["obs"].send_to_user("Currently regenerating local masters. System may be unresponsive during this period.")
        
        
        # for every filter hold onto an estimate of the current camera gain.
        # Each filter will have a different flat field and variation in the flat.
        # The 'true' camera gain is very likely to be the filter with the least
        # variation, so we go with that as the true camera gain...... but ONLY after we have a full set of flats
        # with which to calculate the gain. This is the shelf to hold this data. 
        # There is no hope for individual owners with a multitude of telescopes to keep up with
        # this estimate, so we need to automate it with a first best guess given in the config.        
        self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].name + str(g_dev['obs'].name))
        
        
        # NOW to get to the business of constructing the local calibrations
        # Start with biases
        # Get list of biases
        plog (datetime.datetime.now().strftime("%H:%M:%S"))
        plog ("Regenerating bias")
        darkinputList=(glob(g_dev['obs'].local_dark_folder +'*.n*'))
        inputList=(glob(g_dev['obs'].local_bias_folder +'*.n*'))
        archiveDate=str(datetime.date.today()).replace('-','')
        # Test each file actually opens
        for file in inputList:
            try:
                hdu1data = np.load(file, mmap_mode='r')
            except:
                plog ("corrupt bias skipped: " + str(file))
                inputList.remove(file)
                
        
        
        # have to remove flats from memory to make room for.... flats!
        try:
            del g_dev['cam'].flatFiles
        except:
            pass
        
        if len(inputList) == 0 or len(darkinputList) == 0 or len(inputList) == 1 or len(darkinputList) == 1:
            plog ("Not reprocessing local masters as there are not enough biases or darks")
        else:
            # Clear held bias and darks and flats to save memory and garbage collect.
            del g_dev['cam'].biasFiles
            del g_dev['cam'].darkFiles
            g_dev['cam'].biasFiles = {}
            g_dev['cam'].darkFiles = {}
            g_dev['cam'].flatFiles = {}
            g_dev['cam'].hotFiles = {} 
            gc.collect()
            
            hdutest=np.load(inputList[0], mmap_mode='r')
            shapeImage=hdutest.shape
            del hdutest

            # Make a temporary memmap file
            PLDrive = np.memmap(g_dev['obs'].local_bias_folder + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
            # Store the biases in the memmap file
            i=0
            n = len(inputList)
            for file in inputList:
                plog (datetime.datetime.now().strftime("%H:%M:%S"))

                starttime=datetime.datetime.now() 
                plog("Storing in a memmap array: " + str(file))

                #hdu1data = np.load(file, mmap_mode='r')
                hdu1data = np.load(file)
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to load array: " + str(timetaken))
                                
                starttime=datetime.datetime.now() 
                PLDrive[:,:,i] = hdu1data    
                del hdu1data
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to put in memmap: " + str(timetaken), "To Go:  ", n - i -1)
                i=i+1                

            plog ("**********************************")
            plog ("Median Stacking each bias row individually from the Reprojections")
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
            finalImage=np.zeros(shapeImage,dtype=float)
            for xi in range(shapeImage[0]):
                if xi % 500 == 0:
                    print ("Up to Row" + str(xi))
                    print (datetime.datetime.now().strftime("%H:%M:%S"))
                finalImage[xi,:]=np.nanmedian(PLDrive[xi,:,:], axis=1)
            plog(datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("**********************************")
            
            masterBias=np.asarray(finalImage).astype(np.float32)
            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            try:
                fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)                
                filepathaws=g_dev['obs'].calib_masters_folder
                filenameaws=tempfrontcalib + 'BIAS_master_bin1.fits'
                g_dev['obs'].enqueue_for_AWS(50, filepathaws,filenameaws)
                
                # Store a version of the bias for the archive too
                fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias, overwrite=True)
                
                filepathaws=g_dev['obs'].calib_masters_folder
                filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits'
                g_dev['obs'].enqueue_for_AWS(80, filepathaws,filenameaws)
                
            except Exception as e:
                plog ("Could not save bias frame: ",e)
                
            PLDrive._mmap.close()
            del PLDrive
            gc.collect()
            os.remove(g_dev['obs'].local_bias_folder  + 'tempfile')
    
            # Now that we have the master bias, we can estimate the readnoise actually
            # by comparing the standard deviations between the bias and the masterbias
            readnoise_array=[]
            post_readnoise_array=[]
            plog ("Calculating Readnoise. Please Wait.")
            for file in inputList:
                hdu1data = np.load(file, mmap_mode='r')
                hdu1data=hdu1data-masterBias
                hdu1data = hdu1data[500:-500,500:-500]
                stddiffimage=np.nanstd(pow(pow(hdu1data,2),0.5))                
                est_read_noise= (stddiffimage * g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["camera_gain"]) / 1.414    
                readnoise_array.append(est_read_noise)
                post_readnoise_array.append(stddiffimage)
            
            readnoise_array=np.array(readnoise_array)
            plog ("Raw Readnoise outputs: " +str(readnoise_array))
            plog ("WARNING, THIS VALUE IS ONLY TRUE IF YOU HAVE THE CORRECT GAIN IN reference_gain")
            plog ("Final Readnoise: " + str(np.nanmedian(readnoise_array)) + " std: " + str(np.nanstd(readnoise_array)))
    
    
            g_dev["obs"].send_to_user("Bias calibration frame created.")
            
    
            # NOW we have the master bias, we can move onto the dark frames
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("Regenerating dark") 
            inputList=(glob(g_dev['obs'].local_dark_folder +'*.n*'))
            
            # Test each flat file actually opens
            for file in inputList:
                try:
                    hdu1data = np.load(file, mmap_mode='r')
                except:
                    plog ("corrupt dark skipped: " + str(file))
                    inputList.remove(file)
                    
            PLDrive = np.memmap(g_dev['obs'].local_dark_folder  + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
            # Debias dark frames and stick them in the memmap
            i=0
            for file in inputList:   
                plog (datetime.datetime.now().strftime("%H:%M:%S"))                
                starttime=datetime.datetime.now() 
                plog("Storing dark in a memmap array: " + str(file))
                hdu1data = np.load(file, mmap_mode='r')               
                hdu1exp=float(file.split('_')[-2])                
                darkdeexp=(hdu1data-masterBias)/hdu1exp
                del hdu1data
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to load array and debias and divide dark: " + str(timetaken))
                starttime=datetime.datetime.now() 
                PLDrive[:,:,i] = np.asarray(darkdeexp,dtype=np.float32)
                del darkdeexp
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to put in memmap: " + str(timetaken))                
                i=i+1
    
            plog ("**********************************")
            plog ("Median Stacking each darkframe row individually from the Reprojections")
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
            finalImage=np.zeros(shapeImage,dtype=float)
            for xi in range(shapeImage[0]):
                if xi % 500 == 0:
                    print ("Up to Row" + str(xi))
                    print (datetime.datetime.now().strftime("%H:%M:%S"))    
                finalImage[xi,:]=np.nanmedian(PLDrive[xi,:,:], axis=1)
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("**********************************")
            
            masterDark=np.asarray(finalImage).astype(np.float32)
            try:
                fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'DARK_master_bin1.fits', masterDark,  overwrite=True)                
                filepathaws=g_dev['obs'].calib_masters_folder
                filenameaws=tempfrontcalib + 'DARK_master_bin1.fits'
                g_dev['obs'].enqueue_for_AWS(50, filepathaws,filenameaws)
                
                # Store a version of the dark for the archive too
                fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'DARK_master_bin1.fits', masterDark, overwrite=True)
                
                filepathaws=g_dev['obs'].calib_masters_folder
                filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'DARK_master_bin1.fits'
                g_dev['obs'].enqueue_for_AWS(80, filepathaws,filenameaws)
                
                
            except Exception as e:
                plog ("Could not save dark frame: ",e)
            
            PLDrive._mmap.close()
            del PLDrive
            gc.collect()
            os.remove(g_dev['obs'].local_dark_folder  + 'tempfile')    
            
            g_dev["obs"].send_to_user("Dark calibration frame created.")
            
            # NOW that we have a master bias and a master dark, time to step through the flat frames!
            tempfilters=glob(g_dev['obs'].local_flat_folder + "*/")
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("Regenerating flats")        
            plog (tempfilters)
            
            estimated_flat_gain=[]
            
            flat_gains={}
            
            if len(tempfilters) == 0:
                plog ("there are no filter directories, so not processing flats")
            else:
                for filterfolder in tempfilters:    
                    
                    plog (datetime.datetime.now().strftime("%H:%M:%S"))
                    filtercode=filterfolder.split('\\')[-2]
                    plog ("Regenerating flat for " + str(filtercode))
                    inputList=(glob(g_dev['obs'].local_flat_folder + filtercode + '/*.n*'))
                    
                    # Test each flat file actually opens
                    for file in inputList:
                        try:
                            hdu1data = np.load(file, mmap_mode='r')
                        except:
                            plog ("corrupt flat skipped: " + str(file))
                            inputList.remove(file)     
                    
                    # Generate temp memmap
                    single_filter_camera_gains=[]
                    if len(inputList) == 0 or len(inputList) == 1:
                        plog ("Not doing " + str(filtercode) + " flat. Not enough available files in directory.")
                    else:
                        PLDrive = np.memmap(g_dev['obs'].local_flat_folder  + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
  
                        # Debias and dedark flat frames and stick them in the memmap
                        i=0
                        for file in inputList:   
                            plog (datetime.datetime.now().strftime("%H:%M:%S"))
                            starttime=datetime.datetime.now() 
                            plog("Storing flat in a memmap array: " + str(file))
                            hdu1data = np.load(file, mmap_mode='r')     
                            hdu1exp=float(file.split('_')[-2])

                            flatdebiaseddedarked=(hdu1data-masterBias)-(masterDark*hdu1exp) 
                            del hdu1data
                            # Normalising flat file
                            if not g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                                normalising_factor=np.nanmedian(flatdebiaseddedarked)
                                flatdebiaseddedarked = flatdebiaseddedarked/normalising_factor
                            else:                                
                                
                                debayered=[]
                                max_median=0                    
                                
                                debayered.append(flatdebiaseddedarked[::2, ::2])
                                debayered.append(flatdebiaseddedarked[::2, 1::2])
                                debayered.append(flatdebiaseddedarked[1::2, ::2])
                                debayered.append(flatdebiaseddedarked[1::2, 1::2])                               
                                
                                osc_normalising_factor=[]
                                # crop each of the images to the central region

                                for oscimage in debayered:
                                    cropx = int( (oscimage.shape[0] -500)/2)
                                    cropy = int((oscimage.shape[1] -500) /2)
                                    oscimage=oscimage[cropx:-cropx, cropy:-cropy]
                                    oscmedian=np.nanmedian(oscimage)                                    
                                    osc_normalising_factor.append(oscmedian)
                                
                                del debayered
                                
                                flatdebiaseddedarked[::2, ::2]=flatdebiaseddedarked[::2, ::2]/osc_normalising_factor[0]
                                flatdebiaseddedarked[::2, 1::2]=flatdebiaseddedarked[::2, 1::2]/osc_normalising_factor[1]
                                flatdebiaseddedarked[1::2, ::2]=flatdebiaseddedarked[1::2, ::2]/osc_normalising_factor[2]
                                flatdebiaseddedarked[1::2, 1::2]=flatdebiaseddedarked[1::2, 1::2]/osc_normalising_factor[3]                              
                                                           
                            
                            timetaken=datetime.datetime.now() -starttime
                            plog ("Time Taken to load array and debias and dedark and normalise flat: " + str(timetaken))
                            
                            starttime=datetime.datetime.now() 
                            PLDrive[:,:,i] = flatdebiaseddedarked
                            del flatdebiaseddedarked
                            timetaken=datetime.datetime.now() -starttime
                            plog ("Time Taken to put in memmap: " + str(timetaken))
                            i=i+1
                      
                        plog ("**********************************")
                        plog ("Median Stacking each " + str (filtercode) + " flat frame row individually from the Reprojections")
                        plog (datetime.datetime.now().strftime("%H:%M:%S"))
                        # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
                        finalImage=np.zeros(shapeImage,dtype=float)
                        for xi in range(shapeImage[0]):
                            if xi % 500 == 0:
                                print ("Up to Row" + str(xi))
                                print (datetime.datetime.now().strftime("%H:%M:%S"))
            
                            finalImage[xi,:]=np.nanmedian(PLDrive[xi,:,:], axis=1)
                        plog (datetime.datetime.now().strftime("%H:%M:%S"))
                        plog ("**********************************")
                        
                        temporaryFlat=np.asarray(finalImage).astype(np.float32)
                        del finalImage
                        # Fix up any glitches in the flat
                        temporaryFlat[temporaryFlat < 0.1] = np.nan
                        temporaryFlat[temporaryFlat > 2.0] = np.nan
                        
                        temporaryFlat=interpolate_replace_nans(temporaryFlat, kernel)
                        temporaryFlat[temporaryFlat == inf] = np.nan
                        temporaryFlat[temporaryFlat == -inf] = np.nan
                        temporaryFlat[temporaryFlat < 0.1 ] = np.nan
                        
                        try:
                            np.save(g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy', temporaryFlat)            
                            
                            # Write to and upload current master flat                            
                            fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat, overwrite=True)
                            
                            filepathaws=g_dev['obs'].calib_masters_folder
                            filenameaws=tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits'
                            g_dev['obs'].enqueue_for_AWS(50, filepathaws,filenameaws)
                            
                            # Store a version of the flat for the archive too
                            fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat, overwrite=True)
                            
                            filepathaws=g_dev['obs'].calib_masters_folder
                            filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits'
                            g_dev['obs'].enqueue_for_AWS(80, filepathaws,filenameaws)
                                                        
                        except Exception as e:
                            plog ("Could not save flat frame: ",e)
                        
                        # Now to estimate gain from flats
                        for fullflat in inputList:                            
                            hdu1data = np.load(fullflat, mmap_mode='r')     
                            hdu1exp=float(file.split('_')[-2])
                            
                            camera_gain_estimate_image=((hdu1data-masterBias)-(masterDark*hdu1exp))
                            camera_gain_estimate_image[camera_gain_estimate_image == inf] = np.nan
                            camera_gain_estimate_image[camera_gain_estimate_image == -inf] = np.nan
                            
                            # If an OSC, just use the brightest bayer bit.
                            if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                                
                                osc_fits=copy.deepcopy(camera_gain_estimate_image)
                                
                                debayered=[]
                                max_median=0                    
                                
                                debayered.append(osc_fits[::2, ::2])
                                debayered.append(osc_fits[::2, 1::2])
                                debayered.append(osc_fits[1::2, ::2])
                                debayered.append(osc_fits[1::2, 1::2])
                                
                                # crop each of the images to the central region
                                oscounter=0
                                for oscimage in debayered:
                                    cropx = int( (oscimage.shape[0] -500)/2)
                                    cropy = int((oscimage.shape[1] -500) /2)
                                    oscimage=oscimage[cropx:-cropx, cropy:-cropy]
                                    oscmedian=np.nanmedian(oscimage)
                                    if oscmedian > max_median:
                                        max_median=oscmedian
                                        brightest_bayer=copy.deepcopy(oscounter)
                                    oscounter=oscounter+1
                                
                                camera_gain_estimate_image=copy.deepcopy(debayered[brightest_bayer])
                                
                                del osc_fits
                                del debayered
                                
                                                            
                            cropx = int( (camera_gain_estimate_image.shape[0] -500)/2)
                            cropy = int((camera_gain_estimate_image.shape[1] -500) /2)
                            camera_gain_estimate_image=camera_gain_estimate_image[cropx:-cropx, cropy:-cropy]
                            camera_gain_estimate_image = sigma_clip(camera_gain_estimate_image, masked=False, axis=None)
                            
                            
                            cge_median=np.nanmedian(camera_gain_estimate_image)
                            cge_stdev=np.nanstd(camera_gain_estimate_image)
                            cge_sqrt=pow(cge_median,0.5)
                            cge_gain=1/pow(cge_sqrt/cge_stdev, 2)
                            print ("Camera gain median: " + str(cge_median) + " stdev: " +str(cge_stdev)+ " sqrt: " + str(cge_sqrt) + " gain: " +str(cge_gain))
                            
                            estimated_flat_gain.append(cge_gain)
                        
                            single_filter_camera_gains.append(cge_gain)
                            
                        single_filter_camera_gains=np.array(single_filter_camera_gains)
                        single_filter_camera_gains = sigma_clip(single_filter_camera_gains, masked=False, axis=None)
                        plog ("Filter Gain Sigma Clipped Estimates: " + str(np.nanmedian(single_filter_camera_gains)) + " std " + str(np.std(single_filter_camera_gains)) + " N " + str(len(single_filter_camera_gains)))
                        flat_gains[filtercode]=[np.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]
                        
                        # Chuck camera gain and number of images into the shelf
                        self.filter_camera_gain_shelf[filtercode]=[np.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]
                        
                        
                        PLDrive._mmap.close()
                        del PLDrive
                        gc.collect()
                        os.remove(g_dev['obs'].local_flat_folder  + 'tempfile')       
                        
                    g_dev["obs"].send_to_user(str(filtercode) + " flat calibration frame created.")
                        
                # Bung in the readnoise estimates and then
                # Close up the filter camera gain shelf.
                self.filter_camera_gain_shelf['readnoise']=[np.nanmedian(post_readnoise_array) , np.nanstd(post_readnoise_array), len(post_readnoise_array)]
                self.filter_camera_gain_shelf.close()
                
                textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'cameragain' + g_dev['cam'].name + str(g_dev['obs'].name) +'.txt'
                try:
                    os.remove(textfilename)
                except:
                    pass
                

                # Report on camera estimated gains
                # Report on camera gain estimation
                try:
                    with open(textfilename, 'w') as f:                                                                 
                        plog ("Ending stored filter throughputs")
                        
                            
                        estimated_flat_gain=np.array(estimated_flat_gain)
                        plog ("Raw List of Gains: " +str(estimated_flat_gain))
                        f.write ("Raw List of Gains: " +str(estimated_flat_gain)+ "\n"+ "\n")
                        
                        plog ("Camera Gain Non-Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain)))
                        f.write ("Camera Gain Non-Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain))+ "\n")
                        
                        estimated_flat_gain = sigma_clip(estimated_flat_gain, masked=False, axis=None)
                        plog ("Camera Gain Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain)))
                        f.write ("Camera Gain Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain))+ "\n")
                        
                        est_read_noise=[]
                        for rnentry in post_readnoise_array:                        
                            est_read_noise.append( (rnentry * np.nanmedian(estimated_flat_gain)) / 1.414)
            
                        est_read_noise=np.array(est_read_noise)
                        plog ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise)))
                        f.write ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise))+ "\n")
                        est_read_noise = sigma_clip(est_read_noise, masked=False, axis=None)
                        plog ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise)))
                        f.write ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise))+ "\n")
                        
                        plog ("Gains by filter")
                        for filterline in flat_gains:                            
                            plog (filterline+ " " + str(flat_gains[filterline]))
                            f.write(filterline + " " + str(flat_gains[filterline]) + "\n") 
                            
                except:
                    plog ("hit some snag with reporting gains")
                    plog(traceback.format_exc()) 
                    breakpoint()
                                
                
                # THEN reload them to use for the next night.                
                # First delete the calibrations out of memory.
                
                g_dev['cam'].flatFiles = {}
                g_dev['cam'].hotFiles = {}    
                try:         
                    fileList = glob(g_dev['obs'].calib_masters_folder + '/masterFlat*_bin1.npy')
                    for file in fileList:
                        if self.config['camera'][g_dev['cam'].name]['settings']['hold_flats_in_memory']:
                            tempflatframe=np.load(file)
                            #breakpoint()
                            g_dev['cam'].flatFiles.update({file.split('_')[-2]: np.array(tempflatframe)})
                            del tempflatframe
                        else:
                            g_dev['cam'].flatFiles.update({file.split("_")[1].replace ('.npy','') + '_bin1': file})
                    # To supress occasional flatfield div errors
                    np.seterr(divide="ignore")
                except:
                    plog(traceback.format_exc()) 
                    plog("Flat frames not loaded or available")
                    

                plog ("Regenerated Flat Masters and Re-loaded them into memory.")

            plog ("Re-loading Bias and Dark masters into memory.")
            # Reload the bias and dark frames
            g_dev['cam'].biasFiles = {}
            g_dev['cam'].darkFiles = {}
            
            try:                
                g_dev['cam'].biasFiles.update({'1': masterBias})
            except:
                plog("Bias frame master re-upload did not work.")
                
            try:                
                g_dev['cam'].darkFiles.update({'1': masterDark})
            except:
                plog("Dark frame master re-upload did not work.")  
            
            try:
                del masterBias
            except:
                pass
            try:
                del masterDark
            except:
                pass

        g_dev["obs"].send_to_user("All calibration frames completed.")
          
        return
    
    
    def check_zenith_and_move_to_flat_spot(self, ending=None):
        too_close_to_zenith=True
        while too_close_to_zenith:
            alt, az = self.astro_events.flat_spot_now()  
            if self.config['degrees_to_avoid_zenith_area_for_calibrations'] > 0:
                plog ('zentih distance: ' + str(90-alt))
                if (90-alt) < self.config['degrees_to_avoid_zenith_area_for_calibrations']:
                    alt=90-self.config['degrees_to_avoid_zenith_area_for_calibrations']
                    plog ("waiting for the flat spot to move through the zenith")
                    time.sleep(30)
                    
                    g_dev['obs'].scan_requests()
                    g_dev['obs'].update() 
                    
                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Observatory closed or disabled during flat script. Cancelling out of flat acquisition loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        return 'cancel'
                    
                    # Check that Flat time hasn't ended
                    if ephem.now() > ending:
                        plog ("Flat acquisition time finished. Breaking out of the flat loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        return 'cancel'
                    
                else:
                    g_dev['mnt'].go_command(skyflatspot=True) 
                    too_close_to_zenith=False                       
            else:
                g_dev['mnt'].go_command(skyflatspot=True)
                too_close_to_zenith=False

    def sky_flat_script(self, req, opt, morn=False, skip_moon_check=False):
        """
        This is the evening and morning sky automated skyflat routine.
        """

        
        if  ((ephem.now() < g_dev['events']['Eve Sky Flats']) or \
            (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['Nightly Reset'])):
            plog ("NOT DOING FLATS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it is during the daytime.")            
            return

        if (g_dev['events']['Naut Dusk'] < ephem.now() < g_dev['events']['Naut Dawn']) :
            plog ("NOT DOING FLATS -- IT IS THE NIGHTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it too dark.")            
            return
               
        
        # Moon check.
        if (skip_moon_check==False):
            # Moon current alt/az
            currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
            moondata=get_moon(Time.now()).transform_to(currentaltazframe)
            # Flatspot position.
            flatspotaz, flatspotalt = self.astro_events.flat_spot_now()
            temp_separation=((ephem.separation( (flatspotaz,flatspotalt), (moondata.az.deg,moondata.alt.deg))))
           
            if (moondata.alt.deg < -15):
                plog ("Moon is far below the ground, alt " + str(moondata.alt.deg) + ", sky flats going ahead.")
            
            elif temp_separation < self.config['minimum_distance_from_the_moon_when_taking_flats']: #and (ephem.Moon(datetime.datetime.now()).moon_phase) > 0.05:
                plog ("Moon is in the sky and less than " + str(self.config['minimum_distance_from_the_moon_when_taking_flats']) + " degrees ("+str(temp_separation)+") away from the flat spot, skipping this flat time.")
                return
           
        
        self.flats_being_collected = True
        plog('Sky Flat sequence Starting.')
        self.next_flat_observe = time.time()
        g_dev['obs'].send_to_user('Sky Flat sequence Starting.', p_level='INFO')
        evening = not morn
        camera_name = str(self.config['camera']['camera_1_1']['name'])
        flat_count = self.config['camera']['camera_1_1']['settings']['number_of_flat_to_collect']
        min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_flat_exposure'])
        max_exposure = float(self.config['camera']['camera_1_1']['settings']['max_flat_exposure'])

        exp_time = min_exposure 
        
        # Load up the pickled list of gains or start a new one. 
        self.filter_throughput_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].name + str(g_dev['obs'].name))
        
        if self.config['filter_wheel']['filter_wheel1']['override_automatic_filter_throughputs']:
            plog ("Config is set to not use the automatically estimated")
            plog ("Filter throughputs. Starting with config throughput entries.")
        elif len(self.filter_throughput_shelf)==0:
            plog ("Looks like a new filter throughput shelf.")
        else:
            plog ("Beginning stored filter throughputs")
            for filtertempgain in list(self.filter_throughput_shelf.keys()):
                plog (str(filtertempgain) + " " + str(self.filter_throughput_shelf[filtertempgain]))       
        
        
        #  Pick up list of filters is sky flat order of lowest to highest transparency.
        if g_dev["fil"].null_filterwheel == True:
            plog ("No Filter Wheel, just getting non-filtered flats")
            pop_list = [0]            
        else:
            pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort'].copy()

            # Check that filters are actually in the filter_list
            for filter_name in pop_list:
                filter_identified=0
                for match in range(           
                    len(g_dev['fil'].filter_data)
                ):  

                    if filter_name.lower() in str(g_dev['fil'].filter_data[match][0]).lower():                                    
                        filter_identified = 1
                        
                if filter_identified == 0:
                    plog ("Could not find filter: "+str(filter_name) +" in main filter list. Removing it from flat filter list.")
                    pop_list.remove(filter_name)

            if morn:
                pop_list.reverse()
                plog('filters by high to low transmission:  ', pop_list)                
            else:
                plog('filters by low to high transmission:  ', pop_list)                
            
        if morn:            
            ending = g_dev['events']['End Morn Sky Flats']
        else:            
            ending = g_dev['events']['End Eve Sky Flats']

        #obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        exp_time = 0
        scale = 1.0
        collecting_area = self.config['telescope']['telescope1']['collecting_area']/31808.   
        
        
        
        # First pointing towards flatspot
        if g_dev['mnt'].mount.AtParK:
            g_dev['mnt'].unpark_command({}, {})
                
        self.check_zenith_and_move_to_flat_spot(ending=ending)
        
        # Homing Rotator for the evening.
        try:
            while g_dev['rot'].rotator.IsMoving:
                plog("home rotator wait")
                time.sleep(1)
            g_dev['obs'].send_to_user("Rotator being homed to be certain of appropriate skyflat positioning.", p_level='INFO')
            time.sleep(0.5)
            g_dev['rot'].home_command()
            self.check_zenith_and_move_to_flat_spot(ending=ending)
            self.wait_for_slew()
            while g_dev['rot'].rotator.IsMoving:
                plog("home rotator wait")
                time.sleep(1)
            self.rotator_has_been_homed_this_evening=True
        except:
            plog ("no rotator to home or wait for.")
        
        camera_gain_collector=[]
                
        while len(pop_list) > 0  and ephem.now() < ending and g_dev['obs'].open_and_enabled_to_observe:
            
                # This is just a very occasional slew to keep it pointing in the same general vicinity                
                if time.time() >= self.time_of_next_slew:
                    if g_dev['mnt'].mount.AtParK:
                        g_dev['mnt'].unpark_command({}, {})
                    
                    self.check_zenith_and_move_to_flat_spot(ending=ending)
                    self.time_of_next_slew = time.time() + 45
                
                g_dev['obs'].scan_requests()
                g_dev['obs'].update() 
            
                if g_dev["fil"].null_filterwheel == False:
                    current_filter = pop_list[0]                    
                    plog("Beginning flat run for filter: " + str(current_filter))
                else:
                    current_filter='No Filter'
                    plog("Beginning flat run for filterless observation")
                    
                g_dev['obs'].send_to_user("Beginning flat run for filter: " + str(current_filter))  
                if (current_filter in self.filter_throughput_shelf.keys()) and (not self.config['filter_wheel']['filter_wheel1']['override_automatic_filter_throughputs']):
                    filter_throughput=self.filter_throughput_shelf[current_filter]
                    plog ("Using stored throughput : " + str(filter_throughput))
                else:  
                    if g_dev["fil"].null_filterwheel == False:                      
                        filter_throughput = g_dev['fil'].return_filter_throughput({"filter": current_filter}, {})  
                    else:
                        filter_throughput = float(self.config['filter_wheel']['filter_wheel1']['flat_sky_gain'])
                    plog ("Using initial gain from config : "+ str(filter_throughput))
                
                        
                acquired_count = 0                
                flat_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                
                if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                    target_flat = 0.65 * flat_saturation_level
                else:
                    target_flat = 0.5 * flat_saturation_level

                scale = 1
                self.estimated_first_flat_exposure = False
                
                slow_report_timer=time.time()-180                
                
                while (acquired_count < flat_count):
                    g_dev['obs'].scan_requests()
                    g_dev['obs'].update()                    
                    
                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Observatory closed or disabled during flat script. Cancelling out of flat acquisition loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        return
                    
                    # Check that Flat time hasn't ended
                    if ephem.now() > ending:
                        plog ("Flat acquisition time finished. Breaking out of the flat loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        return
                    
                                        
                    if self.next_flat_observe < time.time():    
                        try:                            
                            sky_lux, _ = g_dev['evnt'].illuminationNow()
                        except:
                            sky_lux = None
        
                       
                        # MF SHIFTING EXPOSURE TIME CALCULATOR EQUATION TO BE MORE GENERAL FOR ALL TELESCOPES
                        # This bit here estimates the initial exposure time for a telescope given the skylux
                        # or given no skylux at all!
                        if self.estimated_first_flat_exposure == False:
                            self.estimated_first_flat_exposure = True
                            if sky_lux != None:     

                                pixel_area=pow(float(g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["1x1_pix_scale"]),2)
                                exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(filter_throughput))  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                                
                            else: 
                                if morn:
                                    exp_time = 5.0
                                else:
                                    exp_time = min_exposure
                        else:
                            exp_time = scale * exp_time
            
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                            self.filter_throughput_shelf.close()
                            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                            self.flats_being_collected = False
                            return
                        
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                            self.filter_throughput_shelf.close()
                            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                            self.flats_being_collected = False
                            return
                        
                        
                        # Here it makes four tests and if it doesn't match those tests, then it will attempt a flat. 
                        if evening and exp_time > max_exposure:                             
                             plog('Break because proposed evening exposure > maximum flat exposure: ' + str(max_exposure) + ' seconds:  ', exp_time)
                             pop_list.pop(0)
                             acquired_count = flat_count + 1 # trigger end of loop
                             
                        elif morn and exp_time < min_exposure:
                             plog('Break because proposed morning exposure < minimum flat exposure time:  ', exp_time)
                             pop_list.pop(0)
                             acquired_count = flat_count + 1 # trigger end of loop
                            
                        elif evening and exp_time < min_exposure:
                             if time.time()-slow_report_timer > 120:
                                 plog("Too bright for " + str(current_filter) + " filter, waiting. Est. Exptime: " + str(exp_time))
                                 g_dev["obs"].send_to_user("Sky is too bright for " + str(current_filter) + " filter, waiting for sky to dim. Current estimated Exposure time: " + str(round(exp_time,2)) +'s')  
                                 slow_report_timer=time.time()
                             self.estimated_first_flat_exposure = False
                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=ending)
                                  
                                self.time_of_next_slew = time.time() + 45
                             self.next_flat_observe = time.time() + 10
                        elif morn and exp_time > max_exposure :  
                             if time.time()-slow_report_timer > 120:                                 
                                 plog("Too dim for " + str(current_filter) + " filter, waiting. Est. Exptime:  " + str(exp_time))
                                 g_dev["obs"].send_to_user("Sky is too dim for " + str(current_filter) + " filter, waiting for sky to brighten. Current estimated Exposure time: " + str(round(exp_time,2))+'s') 
                                 slow_report_timer=time.time()
                             self.estimated_first_flat_exposure = False
                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=ending)
                                  
                                self.time_of_next_slew = time.time() + 45
                             self.next_flat_observe = time.time() + 10
                             exp_time = min_exposure
                        else:
                            exp_time = round(exp_time, 5)
                            
                            # If scope has gone to bed due to inactivity, wake it up!
                            if g_dev['mnt'].mount.AtParK:
                                g_dev['mnt'].unpark_command({}, {})
                                self.check_zenith_and_move_to_flat_spot(ending=ending)
                                
                                self.time_of_next_slew = time.time() + 45
                            
                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                return
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                return                                      
                                            
                            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}
                                      
                            if g_dev["fil"].null_filterwheel == False:
                                opt = { 'count': 1, 'bin':  1, 'area': 150, 'filter': current_filter}     
                            else:
                                opt = { 'count': 1, 'bin':  1, 'area': 150}   
                            
                            if ephem.now() >= ending:
                                if morn: # This needs to be here because some scopes do not do morning bias and darks
                                    try:
                                        g_dev['mnt'].park_command({}, {})
                                    except:
                                        plog("Mount did not park at end of morning skyflats.")
                                self.filter_throughput_shelf.close()
                                self.flats_being_collected = False
                                return
                            try:
                                # Particularly for AltAz, the slew and rotator rotation must have ended before exposing.
                                self.wait_for_slew()
                                try:
                                    while g_dev['rot'].rotator.IsMoving:
                                        plog("flat rotator wait")
                                        time.sleep(0.2)
                                except:
                                    pass
                                
                                fred = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, do_sep = False,skip_daytime_check=True)
                                
                                try:
                                    if self.stop_script_called:
                                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        return
                                    
                                    if not g_dev['obs'].open_and_enabled_to_observe:
                                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        return
                                    
                                except Exception as e:
                                    plog ('something funny in stop_script still',e)
                                    
                                    
                                    
                                if fred == 'roofshut' :
                                    plog ("roof was shut during flat period, cancelling out of flat scripts")
                                    g_dev["obs"].send_to_user("Roof shut during sky flats. Stopping sky_flats")  
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    return
                                
                                if fred == 'blockend':
                                    plog ("blockend detected during flat period, cancelling out of flat scripts")
                                    g_dev["obs"].send_to_user("Roof shut during sky flats. Stopping sky_flats")  
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    return
                                
                                if g_dev["obs"].stop_all_activity:
                                    plog('stop_all_activity cancelling out of exposure loop')
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    return                                    
                                    
                                try:
                                    bright = fred['patch']   
                                except:
                                    plog ("patch broken?")
                                    plog(traceback.format_exc())
                                    plog (fred)
                                    
                                                                                                    
                            except Exception as e:
                                plog('Failed to get a flat image: ', e)
                                plog(traceback.format_exc())                                
                                g_dev['obs'].update()
                                continue
                            
                            g_dev['obs'].scan_requests()
                            g_dev['obs'].update()
                            
                            try:
                                scale = target_flat / bright
                            except:
                                scale = 1.0                                
                                                    
                            self.check_zenith_and_move_to_flat_spot(ending=ending)
                            
                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                return
                            
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                return
                            
                            if g_dev["fil"].null_filterwheel == False:
                                if sky_lux != None:
                                    plog(current_filter,' New Throughput Value: ', round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3), '\n\n')
                                    new_throughput_value = round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3)
                                else:
                                    plog(current_filter,' New Throughput Value: ', round(bright/(collecting_area*pixel_area*exp_time), 3), '\n\n')
                                    new_throughput_value = round(bright/(collecting_area*pixel_area*exp_time), 3)
                            else:
                                if sky_lux != None:
                                    plog('New Throughput Value: ', round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3), '\n\n')
                                    new_throughput_value = round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3)
                                else:
                                    plog('New Throughput Value: ', round(bright/(collecting_area*pixel_area*exp_time), 3), '\n\n')
                                    new_throughput_value = round(bright/(collecting_area*pixel_area*exp_time), 3)
            
                            if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
            
                                if (
                                    bright
                                    <= 0.75* flat_saturation_level and
                                
                                    bright
                                    >= 0.5 * flat_saturation_level
                                ):
                                    self.filter_throughput_shelf[current_filter]=new_throughput_value
                                    try:
                                        camera_gain_collector.append(fred["camera_gain"])
                                    except:
                                        plog ("camera gain not avails")
                            else:
                                if (
                                    bright
                                    <= 0.75* flat_saturation_level and
                                
                                    bright
                                    >= 0.25 * flat_saturation_level
                                ):
                                    self.filter_throughput_shelf[current_filter]=new_throughput_value
                                    try:
                                        camera_gain_collector.append(fred["camera_gain"])
                                    except:
                                        plog ("camera gain not avails")
                                        
                            acquired_count += 1
                            if acquired_count == flat_count:
                                pop_list.pop(0)
                                scale = 1            
                            
                            continue
                    else:
                        time.sleep(10)

        if morn: 
            self.morn_sky_flat_latch = False                 
        else:
            self.eve_sky_flat_latch = False
            
        textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].name + str(g_dev['obs'].name) +'.txt'
        try:
            os.remove(textfilename)
        except:
            pass
        

        with open(textfilename, 'w') as f:                                                                 
            plog ("Ending stored filter throughputs")
            for filtertempgain in list(self.filter_throughput_shelf.keys()):
                filtline=str(filtertempgain) + " " + str(self.filter_throughput_shelf[filtertempgain])
                plog (filtline)
                f.write(filtline +"\n")
                

        self.filter_throughput_shelf.close()
        
        # Report on camera gain estimation
        try:
            camera_gain_collector=np.array(camera_gain_collector)
            plog ("Camera Gain Estimates: " + str(np.nanmedian(camera_gain_collector)) + " std " + str(np.std(camera_gain_collector)) + " N " + str(len(camera_gain_collector)))
            plog ("Raw List of Gains: " +str(camera_gain_collector))
        except:
            plog ("hit some snag with reporting gains")
            plog(traceback.format_exc()) 
                   
                
        plog('\nSky flat sequence complete.\n')
        g_dev["obs"].send_to_user("Sky flat collection complete.")            
        
        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
        self.flats_being_collected = False


    def screen_flat_script(self, req, opt):
        
        
        #### CURRENTLY THIS IS NOT AN IMPLEMENTED FUNCTION.
        
        if self.config['screen']['screen1']['driver'] == None:
            plog ("NOT DOING SCREEN FLATS - SITE HAS NO SCREEN!!")
            g_dev["obs"].send_to_user("A screen flat script request was rejected as the site does not have a screen.")            
            return
        
        if (ephem.now() < g_dev['events']['Eve Sky Flats']) or \
            (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING SCREEN FLATS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A screen script request was rejected as it is during the daytime.")            
            return
        
        
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
        g_dev['obs'].update() 
        g_dev['obs'].scan_requests()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        time.sleep(5)
        g_dev['obs'].update() 
        g_dev['obs'].scan_requests()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': exp_time,  'alias': camera_name, 'image_type': 'screen flat'}
        opt = {'area': 100, 'count': dark_count, 'filter': 'dark', 'hint': 'screen dark'}  #  air has highest throughput

        result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
            return
        plog('First dark 30-sec patch, filter = "air":  ', result['patch'])
        # g_dev['scr'].screen_light_on()

        for filt in g_dev['fil'].filter_screen_sort:
            #enter with screen dark
            g_dev['obs'].scan_requests()
            filter_number = int(filt)
            plog(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].scan_requests()
            g_dev['obs'].update()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen pre-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                return
            plog("Dark Screen flat, starting:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].update()
            plog('Lighted Screen; filter, bright:  ', filter_number, screen_setting)
            g_dev['scr'].set_screen_bright(int(screen_setting))
            g_dev['scr'].screen_light_on()
            time.sleep(10)
            # g_dev['obs'].update()
            # time.sleep(10)
            # g_dev['obs'].update()
            # time.sleep(10)
            g_dev['obs'].scan_requests()
            g_dev['obs'].update()
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen filter light'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                return
            # if no exposure, wait 10 sec
            plog("Lighted Screen flat:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].scan_requests()
            g_dev['obs'].update()
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            g_dev['obs'].scan_requests()
            g_dev['obs'].update()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'area': 100, 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen post-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                return
            plog("Dark Screen flat, ending:  ",result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')


            #breakpoint()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        g_dev['obs'].update()
        g_dev['mnt'].Tracking = False   #park_command({}, {})
        plog('Sky Flat sequence completed, Telescope tracking is off.')
        
        
        g_dev['mnt'].park_command({}, {})



    def auto_focus_script(self, req, opt, throw=None, skip_timer_check=False, extensive_focus=None):
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
        
        self.focussing=True


        if throw==None:
            throw= self.config['focuser']['focuser1']['throw']

        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING AUTO FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An auto focus was rejected as it is during the daytime.")    
            self.focussing=False
            return

        # First check how long it has been since the last focus
        plog ("Time of last focus")
        plog (g_dev['foc'].time_of_last_focus)
        plog ("Time since last focus")
        plog (datetime.datetime.now() - g_dev['foc'].time_of_last_focus)


        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            self.focussing=False
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            self.focussing=False
            return
            

        plog ("Threshold time between auto focus routines (hours)")
        plog (self.config['periodic_focus_time'])
        
        if skip_timer_check == False:
            if ((datetime.datetime.now() - g_dev['foc'].time_of_last_focus)) > datetime.timedelta(hours=self.config['periodic_focus_time']):
                plog ("Sufficient time has passed since last focus to do auto_focus")
                
            else:
                plog ("too soon since last autofacus")
                self.focussing=False
                return
        
                
        g_dev['foc'].time_of_last_focus = datetime.datetime.now()
        
        # Reset focus tracker
        g_dev['foc'].focus_tracker = [np.nan] * 10

        throw = g_dev['foc'].throw
        
        self.af_guard = True

        req2 = copy.deepcopy(req)
        
        sim = False  
        start_ra = g_dev['mnt'].mount.RightAscension   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
        start_dec = g_dev['mnt'].mount.Declination
        focus_start = g_dev['foc'].get_position()
        #breakpoint()
# =============================================================================
# =============================================================================
# =============================================================================
        plog("Saved  *mounting* ra, dec, focus:  ", start_ra, start_dec, focus_start)
        
       
        # Trim catalogue so that only fields 45 degrees altitude are in there.
        self.focus_catalogue_skycoord= SkyCoord(ra = self.focus_catalogue[:,0]*u.deg, dec = self.focus_catalogue[:,1]*u.deg)
        aa = AltAz (location=g_dev['mnt'].site_coordinates, obstime=Time.now())
        self.focus_catalogue_altitudes=self.focus_catalogue_skycoord.transform_to(aa)            
        above_altitude_patches=[]

        for ctr in range(len(self.focus_catalogue_altitudes)):
            if self.focus_catalogue_altitudes[ctr].alt /u.deg > 45.0:
                above_altitude_patches.append([self.focus_catalogue[ctr,0], self.focus_catalogue[ctr,1], self.focus_catalogue[ctr,2]])
        above_altitude_patches=np.asarray(above_altitude_patches)
        self.focus_catalogue_skycoord= SkyCoord(ra = above_altitude_patches[:,0]*u.deg, dec = above_altitude_patches[:,1]*u.deg)  
        
        # d2d of the closest field.
        teststar = SkyCoord(ra = g_dev['mnt'].current_icrs_ra*15*u.deg, dec = g_dev['mnt'].current_icrs_dec*u.deg)
        idx, d2d, _ = teststar.match_to_catalog_sky(self.focus_catalogue_skycoord)
        
        focus_patch_ra=above_altitude_patches[idx,0] /15
        focus_patch_dec=above_altitude_patches[idx,1]
        focus_patch_n=above_altitude_patches[idx,2]                
        
        g_dev['obs'].scan_requests()
        g_dev['obs'].send_to_user("Slewing to a focus field", p_level='INFO')
        try:
            plog("\nGoing to near focus patch of " + str(int(focus_patch_n)) + " 9th to 12th mag stars " + str(d2d.deg[0]) + "  degrees away.\n")
            g_dev['mnt'].go_command(ra=focus_patch_ra, dec=focus_patch_dec)
        except Exception as e:
            plog ("Issues pointing to a focus patch. Focussing at the current pointing." , e)
            plog(traceback.format_exc())

        req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

        opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
       
        foc_pos0 = focus_start
        result = {}
        
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            self.focussing=False
            return
        
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            self.focussing=False
            return
                
                  
        g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
        
        
        # If no extensive_focus has been done, centre the focus field.
        if extensive_focus == None:
            g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')
            
            result = self.centering_exposure(no_confirmation=True)
            # Wait for platesolve            
            reported=0
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                        self.focussing=False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.focussing=False
                        return
                    pass
            
            g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')
        
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            self.focussing=False
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            self.focussing=False
            return
        
        
                       
        rot_report=0
        while g_dev['foc'].is_moving():
            if rot_report == 0:                    
                plog('Waiting for Focuser to shift.\n')
                rot_report =1
            time.sleep(0.2)
                
               
        g_dev['obs'].scan_requests()
        g_dev['obs'].update()
        
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')


        g_dev['foc'].guarded_move((foc_pos0 - 0* throw)*g_dev['foc'].micron_to_steps)   # NB added 20220209 Nasty bug, varies with prior state

        retry = 0
        while retry < 3:
            if not sim:
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    self.focussing=False
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    self.focussing=False
                    return

            else:

                result['FWHM'] = 3
                result['mean_focus'] = g_dev['foc'].get_position()

            try:
                spot1 = result['FWHM']
                foc_pos1 = result['mean_focus']
            except:
                spot1 = False
                foc_pos1 = False
                plog ("spot1 failed in autofocus script")

            plog (spot1)
            g_dev['obs'].send_to_user("Central focus FWHM: " + str(spot1), p_level='INFO')

            if math.isnan(spot1) or spot1 ==False:
                retry += 1
                plog("Retry of central focus star)")
                continue
            else:
                break
        plog('Autofocus Moving In.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)
        
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                self.focussing=False
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                self.focussing=False
                return
        else:
            result['FWHM'] = 4
            result['mean_focus'] = g_dev['foc'].get_position()
        try:
            spot2 = result['FWHM']
            foc_pos2 = result['mean_focus']
        except:
            spot2 = False
            foc_pos2 = False
            plog ("spot2 failed on autofocus moving in")
        
        g_dev['obs'].send_to_user("Inward focus FWHM: " + str(spot2), p_level='INFO')
        
        plog('Autofocus Overtaveling Out.\n\n')
        g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
        plog('Autofocus Moving back in half-way.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!

        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                self.focussing=False
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                self.focussing=False
                return
        else:
            result['FWHM'] = 4.5
            result['mean_focus'] = g_dev['foc'].get_position()
        try:
            spot3 = result['FWHM']
            foc_pos3 = result['mean_focus']
        except:
            spot3 = False
            foc_pos3 = False
            plog ("spot3 failed on autofocus moving in")
            
        g_dev['obs'].send_to_user("Outward focus FWHM: " + str(spot3), p_level='INFO')
        
        x = [foc_pos2, foc_pos1, foc_pos3]
        y = [spot2, spot1, spot3]
        plog('X, Y:  ', x, y, 'Desire center to be smallest.')

        

        if spot1 is None or spot2 is None or spot3 is None or spot1 == False or spot2 == False or spot3 == False:  #New additon to stop crash when no spots
            plog("Autofocus was not successful. Returning to original focus setting and pointing.")
            g_dev['obs'].send_to_user("Autofocus was not successful. Returning to original focus setting and pointing.")
            
            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)  #NB NB 20221002 THis unit fix shoudl be in the routine. WER
                        
            g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
            self.wait_for_slew()
            
            self.af_guard = False
            self.focussing=False
            return
        elif spot1 < spot2 and spot1 < spot3:
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

            except:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
                
                self.af_guard = False
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
                self.wait_for_slew()
                
                self.af_guard = False
                self.focussing=False
                return
            
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                g_dev['obs'].send_to_user('Moving to Solved focus:  ' +str(round(d1, 2)), p_level='INFO')
                pos = int(d1*g_dev['foc'].micron_to_steps)



                g_dev['foc'].guarded_move(pos)
                
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        self.focussing=False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.focussing=False
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].get_position()
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    plog ("spot4 failed ")
                plog('\nFound best focus at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
                g_dev['obs'].send_to_user('Found best focus at:  ' +str(foc_pos4) +' measured FWHM is:  ' + str(round(spot4, 2)), p_level='INFO')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                self.wait_for_slew()
                
            if sim:
                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
           
            self.af_guard = False
            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            self.focussing=False
            return
        
        elif spot2  <= spot1 < spot3:      #Add to the inside
            pass
            plog('Autofocus Moving In 2nd time.\n\n')
            g_dev['foc'].guarded_move((foc_pos0 - 2.5*throw)*g_dev['foc'].micron_to_steps)
            if not sim:
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.") 
                    self.focussing=False
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    self.focussing=False
                    return
            else:
                result['FWHM'] = 6
                result['mean_focus'] = g_dev['foc'].get_position()
            try:
                spot4 = result['FWHM']
                foc_pos4 = result['mean_focus']
            except:
                spot4 = False
                foc_pos4 = False
                plog ("spot4 failed on autofocus moving in 2nd time.")
            x = [foc_pos4, foc_pos2, foc_pos1, foc_pos3]
            y = [spot4, spot2, spot1, spot3]
            plog('X, Y:  ', x, y, 'Desire center to be smallest.')
            g_dev['obs'].send_to_user('X, Y:  '+ str(x) + " " + str(y)+ ' Desire center to be smallest.', p_level='INFO')
            if foc_pos4 != False and foc_pos2 != False and foc_pos1 != False and foc_pos3 != False:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)
                
            else:                          

                if extensive_focus == None:

                    plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                    plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                    g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus routine')
                    
                    req2 = {'target': 'near_tycho_star', 'area': 150, 'image_type': 'focus'}
                    opt = {'filter': 'focus'}
                    g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                    self.wait_for_slew()
                    self.focussing=False
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ' + str(extensive_focus))
                    
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)

                    g_dev['foc'].last_known_focus=(extensive_focus)*g_dev['foc'].micron_to_steps

                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)   #NB NB Does this really take us back to starting point?
                    self.wait_for_slew()
                    
                    self.af_guard = False
                    self.focussing=False
                    return
                
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                
                pos = int(d1*g_dev['foc'].micron_to_steps)
                g_dev['foc'].guarded_move(pos)
                
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                        self.focussing=False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.focussing=False
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].get_position()
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    plog ("spot4 failed ")
                plog('\nFound best focus position at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
                g_dev['obs'].send_to_user('Found best focus at: ' + str(foc_pos4) +' measured FWHM is: ' + str(round(spot4, 2)), p_level='INFO')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec) #Return to pre-focus pointing.
                self.wait_for_slew()
            if sim:

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
            
            self.af_guard = False
            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            self.focussing=False
            return

        elif spot2 > spot1 >= spot3:       #Add to the outside
            pass
            plog('Autofocus Moving back in half-way.\n\n')

            g_dev['foc'].guarded_move((foc_pos0 + 2.5*throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!
            if not sim:
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    self.focussing=False
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    self.focussing=False
                    return
            else:
                result['FWHM'] = 5.5
                result['mean_focus'] = g_dev['foc'].get_position()
            try:
                spot4 = result['FWHM']
                foc_pos4 = result['mean_focus']
            except:
                spot4 = False
                foc_pos4 = False
                plog ("spot4 failed on autofocus moving out 2nd time.")
            x = [foc_pos2, foc_pos1, foc_pos3, foc_pos4]
            y = [spot2, spot1, spot3, spot4]
            plog('X, Y:  ', x, y, 'Desire center to be smallest.')
            g_dev['obs'].send_to_user('X, Y:  '+ str(x) + " " + str(y)+ ' Desire center to be smallest.', p_level='INFO')
            try:
                #Digits are to help out pdb commands!
                a1, b1, c1, d1 = fit_quadratic(x, y)
                new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

            except:

                if extensive_focus == None:
                    plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                    plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                    g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')                    
                    req2 = {'target': 'near_tycho_star', 'area': 150}
                    opt = {}
                    g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
                    self.wait_for_slew()
                    self.focussing=False
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus:', extensive_focus)
                    
                    #self.sequencer_hold = False   #Allow comand checks.
                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
                    self.wait_for_slew()
                    
                    self.af_guard = False
                    self.focussing=False
                    return
                
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                pos = int(d1*g_dev['foc'].micron_to_steps)
                g_dev['foc'].guarded_move(pos)
                g_dev['foc'].last_known_focus = d1
                try:
                    g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
                except:
                    g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
                g_dev['foc'].last_source = "auto_focus_script"

                if not sim:
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                        self.focussing=False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.focussing=False
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].get_position()
                try:
                    spot4 = result['FWHM']
                    foc_pos4 = result['mean_focus']
                except:
                    spot4 = False
                    foc_pos4 = False
                    plog ("spot4 failed ")
                plog('\nFound best focus position at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
                g_dev['obs'].send_to_user('Found best focus at: ' + str(foc_pos4) +' measured FWHM is: ' + str(round(spot4, 2)), p_level='INFO')
                g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
                self.wait_for_slew()
            else:
                if extensive_focus == None:

                    plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                    plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                    g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')
                    
                    req2 = {'target': 'near_tycho_star', 'area': 150}
                    opt = {}
                    g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
                    self.wait_for_slew()
                    self.focussing=False
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ', extensive_focus)
                    
                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                    self.wait_for_slew()
                   
                    self.af_guard = False
                    self.focussing=False
                    return
            
            
            if sim:

                g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
            
            self.af_guard = False

            g_dev['foc'].last_focus_fwhm = round(spot4, 2)
            self.focussing=False
            return
        
        else:
            
            if extensive_focus == None:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')                
                req2 = {'target': 'near_tycho_star', 'area': 150}
                opt = {}
                g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                self.wait_for_slew()
                self.focussing=False
                return
            else:
                plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                g_dev['obs'].send_to_user('V-curve focus failed, moving back to extensive focus: ', extensive_focus)                
                self.af_guard = False
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
                self.wait_for_slew()                
                self.af_guard = False
                self.focussing=False
                return
        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
        self.wait_for_slew()

        if sim:
            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
        
                
        self.af_guard = False
        self.focussing=False
        return


    def extensive_focus_script(self, req, opt, throw=None, begin_at=None, no_auto_after_solve=False):
        '''
        This is an extensive focus that covers a wide berth of central values
        and throws.
        
        It first trys 6 throws inwards, 6 throws outwards
        
        then moves to the minimum focus found there
        
        and runs a normal focus
        
        '''
        self.focussing=True
        if throw==None:
            throw= self.config['focuser']['focuser1']['throw']
        
        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
                

            plog ("NOT DOING EXTENSIVE FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An extensive focus was rejected as it is during the daytime.")
            self.focussing=False
            return
        
        
        plog('AF entered with:  ', req, opt)
        
        self.af_guard = True
        sim = False
        # Reset focus tracker
        if begin_at is None:  
            foc_start = g_dev['foc'].get_position()
        else:
            foc_start = begin_at  #In this case we start at a place close to a 3 point minimum.            
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
            
        start_ra = g_dev['mnt'].mount.RightAscension
        start_dec = g_dev['mnt'].mount.Declination
        plog("Saved ra, dec, focus:  ", start_ra, start_dec, foc_start)
                
           
        # Trim catalogue so that only fields 45 degrees altitude are in there.
        self.focus_catalogue_skycoord= SkyCoord(ra = self.focus_catalogue[:,0]*u.deg, dec = self.focus_catalogue[:,1]*u.deg)
        aa = AltAz (location=g_dev['mnt'].site_coordinates, obstime=Time.now())
        self.focus_catalogue_altitudes=self.focus_catalogue_skycoord.transform_to(aa)            
        above_altitude_patches=[]

        for ctr in range(len(self.focus_catalogue_altitudes)):
            if self.focus_catalogue_altitudes[ctr].alt /u.deg > 45.0:
                above_altitude_patches.append([self.focus_catalogue[ctr,0], self.focus_catalogue[ctr,1], self.focus_catalogue[ctr,2]])
        above_altitude_patches=np.asarray(above_altitude_patches)
        self.focus_catalogue_skycoord= SkyCoord(ra = above_altitude_patches[:,0]*u.deg, dec = above_altitude_patches[:,1]*u.deg)  
        
        # d2d of the closest field.
        teststar = SkyCoord(ra = g_dev['mnt'].current_icrs_ra*15*u.deg, dec = g_dev['mnt'].current_icrs_dec*u.deg)
        idx, d2d, _ = teststar.match_to_catalog_sky(self.focus_catalogue_skycoord)
        
        focus_patch_ra=above_altitude_patches[idx,0] /15
        focus_patch_dec=above_altitude_patches[idx,1]
        focus_patch_n=above_altitude_patches[idx,2]   
        
        
        #g_dev['mnt'].go_coord(focus_star[0][1][1], focus_star[0][1][0])
        
        g_dev['obs'].send_to_user("Slewing to a focus field", p_level='INFO')
        g_dev['mnt'].go_command(ra=focus_patch_ra, dec=focus_patch_dec)            
        g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            self.focussing=False
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            self.focussing=False
            return
        
        # If no auto_focus has been done, centre the focus field.
        if no_auto_after_solve == False:            
            g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')
            
            result = self.centering_exposure(no_confirmation=True)
            # Wait for platesolve
            #queue_clear_time = time.time()
            reported=0
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    #plog ("we are free from platesolving!")
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        self.focussing=False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.focussing=False
                        return
                    pass
            
            g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            self.focussing=False
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            self.focussing=False
            return           
            
        
        foc_pos0 = foc_start
        result = {}
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')
        
        # In extensive focus, we widen the throw as we are searching a wider range
        throw=throw*1.5
        
        extensive_focus=[]
        for ctr in range(4):
            g_dev['foc'].guarded_move((foc_pos0 - (ctr+0)*throw)*g_dev['foc'].micron_to_steps)  
           
            if not sim:
                g_dev['obs'].scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    self.focussing=False
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    self.focussing=False
                    return
            else:
                try:
                    result['FWHM'] = 4
                    result['mean_focus'] = g_dev['foc'].get_position()
                except:
                    plog(traceback.format_exc())
                    breakpoint()
            try:
                spot = result['FWHM']
                lsources = result['No_of_sources']
                if np.isnan(lsources):
                    spot=False               
                
                foc_pos = (foc_pos0 - (ctr+0)*throw)                
                        
            except:
                spot = False
                foc_pos = False                
                lsources=0
                plog ("spot failed on extensive focus script")
                plog(traceback.format_exc())

            g_dev['obs'].send_to_user("Extensive focus position " + str(foc_pos) + " FWHM: " + str(spot), p_level='INFO')
            
            if spot != False:
                extensive_focus.append([foc_pos, spot, lsources])
                
            plog("Extensive focus so far (pos, fwhm, sources): "+ str(extensive_focus))
        
        for ctr in range(3):
            g_dev['foc'].guarded_move((foc_pos0 + (ctr+1)*throw)*g_dev['foc'].micron_to_steps)  
            if not sim:
                g_dev['obs'].scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    self.focussing=False
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    self.focussing=False
                    return
            else:
                result['FWHM'] = 4
                result['mean_focus'] = g_dev['foc'].get_position()
            try:
                spot = result['FWHM']
                lsources = result['No_of_sources']
                if np.isnan(lsources):
                    spot=False
                
                foc_pos = (foc_pos0 + (ctr+1)*throw)
                
            except:
                spot = False
                foc_pos = False
                lsources=0
                plog ("spot failed on extensive focus script")
                plog(traceback.format_exc())

            g_dev['obs'].send_to_user("Extensive focus position " + str(foc_pos) + " FWHM: " + str(spot), p_level='INFO')
            extensive_focus.append([foc_pos, spot, lsources])
            plog(extensive_focus)
        
        minimumFWHM = 100.0
        
        # Remove Faulty measurements
        trimmed_list=[]
        for focentry in extensive_focus:
            if focentry[1] != False:
                trimmed_list.append(focentry)
        
        extensive_focus=trimmed_list
        
        # Find the maximum number of sources detected
        # if it fails, it fails.... usually fails because there are no sources detected in any images
        try:
            maxsources=max(np.asarray(extensive_focus)[:,2])
        except:
            maxsources=1
        
        for focentry in extensive_focus:
            # Has to have detected a FWHM as well as have a lot of sources
            if focentry[1] != False and focentry[2] > 0.2 * maxsources:
                if focentry[1] < minimumFWHM:
                    solved_pos = focentry[0]
                    minimumFWHM = focentry[1]
        try:
            plog (extensive_focus)
            plog (solved_pos)
            plog (minimumFWHM)
            g_dev['foc'].guarded_move((solved_pos)*g_dev['foc'].micron_to_steps)
            g_dev['foc'].last_known_focus=(solved_pos)*g_dev['foc'].micron_to_steps

            if not no_auto_after_solve:
                self.auto_focus_script(None,None, skip_timer_check=True, extensive_focus=solved_pos) 
        except:
            plog ("Something went wrong in the extensive focus routine")
            plog(traceback.format_exc())
            plog ("Moving back to the starting focus")
            g_dev['obs'].send_to_user("Extensive focus attempt failed. Returning to initial focus.")
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
                    
        
        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
        self.wait_for_slew()
        
        self.af_guard = False
        self.focussing = False
        
    def append_completes(self, block_id):
        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + camera + str(g_dev['obs'].name))
        plog("block_id:  ", block_id)
        lcl_list = seq_shelf['completed_blocks']
        lcl_list.append(block_id)   #NB NB an in-line append did not work!
        seq_shelf['completed_blocks']= lcl_list
        plog('Appended completes contains:  ', seq_shelf['completed_blocks'])
        seq_shelf.close()
        return

    def is_in_completes(self, check_block_id):
        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + camera + str(g_dev['obs'].name))
        if check_block_id in seq_shelf['completed_blocks']:
            seq_shelf.close()            
            return True
        else:
            seq_shelf.close()
            return False



    def sky_grid_pointing_run(self, max_pointings=25, alt_minimum=35):
        
        g_dev['obs'].get_enclosure_status_from_aws()        
        if not g_dev['obs'].assume_roof_open and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
            plog('Roof is shut, so cannot do requested pointing run.')
            g_dev["obs"].send_to_user('Roof is shut, so cannot do requested pointing run.')
            return
        
        self.total_sequencer_control = True
        g_dev['obs'].stop_processing_command_requests = True
        
        prev_auto_centering = g_dev['obs'].auto_centering_off
        g_dev['obs'].auto_centering_off = True
        
        plog("Starting pointing run. ")
        time.sleep(0.1)
        
        g_dev['mnt'].unpark_command({}, {})
        
        g_dev['obs'].update_status()
        
        catalogue=self.pointing_catalogue
        
        g_dev["obs"].send_to_user("Starting pointing run. Constructing altitude catalogue. This can take a while.")
        plog("Constructing sweep catalogue above altitude " + str(alt_minimum))
        
        sweep_catalogue=[]
        #First remove all entries below given altitude
        for ctr in range(len(catalogue)):
            teststar = SkyCoord(ra = catalogue[ctr][0]*u.deg, dec = catalogue[ctr][1]*u.deg)
			
            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            if alt > alt_minimum:
                sweep_catalogue.append([catalogue[ctr][0],catalogue[ctr][1],catalogue[ctr][2]])
            
        
        plog (sweep_catalogue)

        del catalogue
        
        spread =3600.0 # Initial spread is about a degree
        too_many=True
        
        g_dev["obs"].send_to_user("Constructing grid of pointings. This can take a while.")
        plog("Finding a good set of pointings")
        
        while too_many:
        
            finalCatalogue=[]
            for ctr in range(len(sweep_catalogue)):
            	if sweep_catalogue[ctr][2] < 20:
            		if len(finalCatalogue) == 0 or len(finalCatalogue) == 1:
            			finalCatalogue.append(sweep_catalogue[ctr])
            		else:
            
            			testcat= SkyCoord(ra = np.asarray(finalCatalogue)[:,0]*u.deg, dec = np.asarray(finalCatalogue)[:,1]*u.deg)
            			teststar = SkyCoord(ra = sweep_catalogue[ctr][0]*u.deg, dec = sweep_catalogue[ctr][1]*u.deg)
            			
            			idx, d2d, _ = teststar.match_to_catalog_sky(testcat)
            			if (d2d.arcsecond > spread):
            				finalCatalogue.append(sweep_catalogue[ctr])
            				
            
            plog ("Number of Pointings: " + str(len(finalCatalogue)))

            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of script as stop script has been called.")  
                self.total_sequencer_control = False
                g_dev['obs'].stop_processing_command_requests = False
                return
            if not g_dev['obs'].open_and_enabled_to_observe and not g_dev['obs'].scope_in_manual_mode:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                self.total_sequencer_control = False
                g_dev['obs'].stop_processing_command_requests = False
                return

            if len(finalCatalogue) > max_pointings:
                print ("still too many:  ", len(finalCatalogue))
                if len(finalCatalogue) < 20:
                    spread=spread+2400
                elif len(finalCatalogue) < 10:
                    spread=spread+4800
                elif (len(finalCatalogue) / max_pointings) > 4:
                    spread=spread+3600                    
                else:
                    spread=spread + 1200
            else:
                too_many=False
                    
        length = len(finalCatalogue)
        g_dev["obs"].send_to_user(str(length) + " Targets chosen for grid.")
        plog(str(length) + " Targets chosen for grid.")
        
        count = 0
        
        deviation_catalogue_for_tpoint=[]
        
        plog ("Note that mount references and auto-centering are automatically turned off for a tpoint run.")
        
        for grid_star in finalCatalogue:
            
            
            teststar = SkyCoord(ra = grid_star[0]*u.deg, dec = grid_star[1]*u.deg)
			
            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            az = temppointingaltaz.az.degree
            
            g_dev["obs"].send_to_user(str(("Slewing to near grid field, RA: " + str(grid_star[0] / 15) + " DEC: " + str(grid_star[1])+ " AZ: " + str(az)+ " ALT: " + str(alt))))
            plog("Slewing to near grid field " + str(grid_star) )
            
            # Use the mount RA and Dec to go directly there
            try:
                g_dev['mnt'].mount.SlewToCoordinatesAsync(grid_star[0] / 15 , grid_star[1])
            except:
                plog ("Difficulty in directly slewing to object")
                plog(traceback.format_exc())
                if g_dev['mnt'].theskyx:
                    self.kill_and_reboot_theskyx(grid_star[0] / 15, grid_star[1])
                else:
                    plog(traceback.format_exc())
                    breakpoint()  

            self.wait_for_slew()
                
                
            g_dev['obs'].update_status()
            req = { 'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'light'}
            opt = { 'area': 100, 'count': 1,  'filter': 'pointing'}
            result = g_dev['cam'].expose_command(req, opt)
            
            g_dev["obs"].send_to_user("Platesolving image.")
            # Wait for platesolve
            reported=0
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of script as stop script has been called.")  
                        self.total_sequencer_control = False
                        g_dev['obs'].stop_processing_command_requests = False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        self.total_sequencer_control = False
                        g_dev['obs'].stop_processing_command_requests = False
                        return
                    pass
            
            g_dev["obs"].send_to_user("Finished platesolving")
            plog ("Finished platesolving")
            
            sid = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            
            # Get RA, DEC, ra deviation, dec deviation and add to the list
            try:
                g_dev['mnt'].pier_side = g_dev[
                    "mnt"
                ].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
                
            except Exception as e:
                plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            ra_mount=g_dev['mnt'].mount.RightAscension
            dec_mount = g_dev['mnt'].mount.Declination    
            result=[ra_mount, dec_mount, g_dev['obs'].last_platesolved_ra, g_dev['obs'].last_platesolved_dec,g_dev['obs'].last_platesolved_ra_err, g_dev['obs'].last_platesolved_dec_err, sid, g_dev["mnt"].pier_side,g_dev['cam'].start_time_of_observation,g_dev['cam'].current_exposure_time]
            deviation_catalogue_for_tpoint.append (result)
            plog(result)
            
            g_dev['obs'].update_status()
            count += 1
            plog('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')

        g_dev["obs"].send_to_user("Tpoint collection completed. Happy reducing.")
        plog("Tpoint collection completed. Happy reducing.")
        
        deviation_catalogue_for_tpoint = np.asarray(deviation_catalogue_for_tpoint, dtype=float)
        np.savetxt(self.config['archive_path'] +'/'+'tpointmodel' + str(time.time()).replace('.','d') + '.csv', deviation_catalogue_for_tpoint, delimiter=',')
        
        
        tpointnamefile=self.config['archive_path'] +'/'+'TPOINTDAT'+str(time.time()).replace('.','d')+'.DAT'
        
        with open(tpointnamefile, "a+") as f:            	
            	f.write(self.config["name"] +"\n")
        with open(tpointnamefile, "a+") as f:            	        
            f.write(":NODA\n")
            f.write(":EQUAT\n")
            latitude = float(g_dev['evnt'].wema_config['latitude'])
            f.write(Angle(latitude,u.degree).to_string(sep=' ')+ "\n")
        for entry in deviation_catalogue_for_tpoint:
            if not np.isnan(entry[2]):
                #print (entry[0], entry[1])        
                ra_wanted=Angle(entry[0],u.hour).to_string(sep=' ')
                dec_wanted=Angle(entry[1],u.degree).to_string(sep=' ')
                ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                
                
                if entry[7] == 0:
                    pierstring='0  1'
                    entry[2] += 12.
                    while entry[2] >= 24:
                        entry[2] -= 24.
                    ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                
                    if latitude >= 0:
                        dec_got=Angle(180 - entry[3],u.degree).to_string(sep=' ')  # as in 89 90 91 92 when going 'under the pole'.
                    else:
                        dec_got=Angle(-(180 + entry[3]),u.degree).to_string(sep=' ')                     
                else:
                    pierstring='0  0'
                    ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                    dec_got=Angle(entry[3],u.degree).to_string(sep=' ')
            
    
                sid_str = Angle(entry[6], u.hour).to_string(sep=' ')[:5]
                writeline = ra_wanted + " " + dec_wanted + " " + ra_got + " " + dec_got + " "+ sid_str + " "+ pierstring
    
                            
                with open(tpointnamefile, "a+") as f:            	
                    	f.write(writeline+"\n")
                        
                plog(writeline) 
        
        try:
            os.path.expanduser('~')
            print (os.path.expanduser('~'))
            print (os.path.expanduser('~')+ "/Desktop/TPOINT/")
            
            if not os.path.exists(os.path.expanduser('~')+ "/Desktop/TPOINT"):
                os.makedirs(os.path.expanduser('~')+ "/Desktop/TPOINT")
            
            shutil.copy (tpointnamefile, os.path.expanduser('~') + "/Desktop/TPOINT/" + 'TPOINTDAT'+str(time.time()).replace('.','d')+'.DAT')
        except:
            plog('Could not copy file to tpoint directory... you will have to do it yourself!')
        
        plog ("Final devation catalogue for Tpoint")
        plog (deviation_catalogue_for_tpoint)
        
        
        g_dev['obs'].auto_centering_off = prev_auto_centering

        self.total_sequencer_control = False
        g_dev['obs'].stop_processing_command_requests = False
        return


    def centering_exposure(self, no_confirmation=False, try_hard=False):

        """
        A pretty regular occurance - the pointing on the scopes isn't great usually.
        This gets the image within a few arcseconds usually. Called from a variety of spots,
        but the most important is centering the requested RA and Dec just prior to starting
        a longer project block.
        """         

        if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
            plog("Too bright to consider platesolving!")
            plog("Hence too bright to do a centering exposure.")   
            g_dev["obs"].send_to_user("Too bright to auto-center the image.")  
            
            return
        
        
        req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
        opt = {'area': 100, 'count': 1, 'filter': 'pointing'}
        
        successful_platesolve=False
        
        # Make sure platesolve queue is clear
        reported=0
        while True:
            
            if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                break
            else:
                if reported ==0:
                    plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                    reported=1
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
                pass
        
        g_dev["obs"].send_to_user(
            "Taking a pointing calibration exposure",
            p_level="INFO",
        )
        # Take a pointing shot to reposition
        result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)
                
        # Wait for platesolve
        queue_clear_time = time.time()
        reported=0
        while True:
            if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                #plog ("we are free from platesolving!")
                break
            else:
                if reported ==0:
                    plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                    reported=1
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
                pass
            
        plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))
        
        if g_dev['obs'].last_platesolved_ra != np.nan:
            successful_platesolve=True        
        
        # Nudge if needed.
        if not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
            g_dev["obs"].send_to_user("Pointing adequate on first slew. Slew & Center complete.") 
            return result
        else:
            g_dev['obs'].check_platesolve_and_nudge()        
            # Wait until pointing correction fixed before moving on
            while g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                plog ("waiting for pointing_correction_to_finish")
                time.sleep(0.5)
            
        if try_hard and not successful_platesolve:
            plog("Didn't get a successful platesolve at an important time for pointing, trying a double exposure")
            
            req = {'time': float(self.config['pointing_exposure_time']) * 2,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'pointing'}
            
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)
            
            queue_clear_time = time.time()
            reported=0
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        return
                    pass
            plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))
            
            if g_dev['obs'].last_platesolved_ra == np.nan:
                plog("Didn't get a successful platesolve at an important time for pointing AGAIN, trying a Lum filter")
                
                req = {'time': float(self.config['pointing_exposure_time']) * 2.5,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'area': 100, 'count': 1, 'filter': 'Lum'}
                
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)
                
                queue_clear_time = time.time()
                reported=0
                while True:
                    if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                        #plog ("we are free from platesolving!")
                        break
                    else:
                        if reported ==0:
                            plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                            reported=1
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                            return
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                            return
                        pass
                plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))
        
                
        # Nudge if needed.
        if not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
            g_dev["obs"].send_to_user("Pointing adequate on first slew. Slew & Center complete.") 
            return result
        else:
            g_dev['obs'].check_platesolve_and_nudge()        
            # Wait until pointing correction fixed before moving on
            while g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                plog ("waiting for pointing_correction_to_finish")
                time.sleep(0.5)
        
        
        if no_confirmation == True:
            return result
        else:
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
            
            g_dev["obs"].send_to_user(
                "Taking a pointing confirmation exposure",
                p_level="INFO",
            )
            
            # Taking a confirming shot. 
            req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'pointing'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)
            
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
            
            g_dev["obs"].send_to_user("Pointing confirmation exposure complete. Slew & Center complete.") 
            
            return result

    def update_calendar_blocks(self):

        """
        A function called that updates the calendar blocks - both to get new calendar blocks and to
        check that any running calendar blocks are still there with the same time window.
        """            

        url_blk = "https://calendar.photonranch.org/calendar/siteevents"
        # UTC VERSION
        start_aperture = str(g_dev['events']['Eve Sky Flats']).split()
        close_aperture = str(g_dev['events']['End Morn Sky Flats']).split()

        # Reformat ephem.Date into format required by the UI
        startapyear = start_aperture[0].split('/')[0]
        startapmonth = start_aperture[0].split('/')[1]
        startapday = start_aperture[0].split('/')[2]
        closeapyear = close_aperture[0].split('/')[0]
        closeapmonth = close_aperture[0].split('/')[1]
        closeapday = close_aperture[0].split('/')[2]

        if len(str(startapmonth)) == 1:
            startapmonth = '0' + startapmonth
        if len(str(startapday)) == 1:
            startapday = '0' + str(startapday)
        if len(str(closeapmonth)) == 1:
            closeapmonth = '0' + closeapmonth
        if len(str(closeapday)) == 1:
            closeapday = '0' + str(closeapday)

        start_aperture_date = startapyear + '-' + startapmonth + '-' + startapday
        close_aperture_date = closeapyear + '-' + closeapmonth + '-' + closeapday

        start_aperture[0] = start_aperture_date
        close_aperture[0] = close_aperture_date

        body = json.dumps(
            {
                "site": self.config["obs_id"],
                "start": start_aperture[0].replace('/', '-') + 'T' + start_aperture[1] + 'Z',
                "end": close_aperture[0].replace('/', '-') + 'T' + close_aperture[1] + 'Z',
                "full_project_details:": False,
            }
        )
        try:
            self.blocks = reqs.post(url_blk, body, timeout=20).json()
        except:
            plog ("glitch out in the blocks reqs post")
            
    def reset_completes(self):
        
        """
        The sequencer keeps track of completed projects, but in certain situations, you want to flush that list (e.g. roof shut then opened again).
        """    
        
        try:
            camera = self.config['camera']['camera_1_1']['name']
            seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) + str(g_dev['obs'].name))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            plog('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return
    
    
