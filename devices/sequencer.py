import time
import datetime
from datetime import timedelta
import copy
from global_yard import g_dev
from astropy.coordinates import SkyCoord, AltAz, get_moon
from astropy import units as u
from astropy.time import Time
from astropy.io import fits
#from astropy.utils.data import get_pkg_data_filename
from astropy.convolution import Gaussian2DKernel, convolve, interpolate_replace_nans
kernel = Gaussian2DKernel(x_stddev=2,y_stddev=2)

import ephem
import build_tycho as tycho
import shelve
import redis
import math
import shutil
import numpy as np
import os
import gc
from pyowm import OWM
from pyowm.utils import config

from pyowm.utils import timestamps
from glob import glob
import traceback
from ptr_utility import plog
from pprint import pprint

'''
'''

def wait_for_slew():    
    
    try:
        if not g_dev['mnt'].mount.AtPark:              
            movement_reporting_timer=time.time()
            while g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                #if g_dev['mnt'].mount.Slewing: plog( 'm>')
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if time.time() - movement_reporting_timer > 2.0:
                    plog( 'm>')
                    movement_reporting_timer=time.time()
                #time.sleep(0.1)
                g_dev['obs'].update_status(mount_only=True, dont_wait=True)            
            
    except Exception as e:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        if 'pywintypes.com_error' in str(e):
            plog ("Mount disconnected. Recovering.....")
            time.sleep(30)
            g_dev['mnt'].mount.Connected = True
            #g_dev['mnt'].home_command()
        else:
            breakpoint()
    return 

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
        self.bias_dark_latch = False   #NB NB NB Should these initially be defined this way?
        self.sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.morn_bias_dark_latch = False   #NB NB NB Should these initially be defined this way?
        self.cool_down_latch = False
        self.night_focus_ready=True
        
        self.nightime_bias_counter = 0
        self.nightime_dark_counter = 0
        
        self.nightly_reset_complete = False
        
        self.reset_completes()  # NB NB Note this is reset each time sequencer is restarted.

        try:
            self.is_in_completes(None)
        except:
            self.reset_completes()
            
        # Load up focus catalogue
        self.focus_catalogue = np.genfromtxt('support_info/focusCatalogue.csv', delimiter=',')

        # This variable prevents the roof being called to open every loop...        
        self.enclosure_next_open_time = time.time()
        # This keeps a track of how many times the roof has been open this evening
        # Which is really a measure of how many times the observatory has
        # attempted to observe but been shut on....
        # If it is too many, then it shuts down for the whole evening. 
        self.opens_this_evening = 0
        
        self.morn_bias_done = False
        self.eve_bias_done = False
        self.eve_bias_done = False
        self.eve_flats_done = False
        self.morn_flats_done = False
        self.eve_sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.bias_dark_latch = False

        self.clock_focus_latch=False

        self.stop_script_called=False
        self.stop_script_called_time=time.time()

        # The weather report has to be at least passable at some time of the night in order to 
        # allow the observatory to become active and observe. This doesn't mean that it is 
        # necessarily a GOOD night at all, just that there are patches of feasible
        # observing during the night.
        self.nightly_weather_report_complete = False
        self.weather_report_is_acceptable_to_observe = False
        # If the night is patchy, the weather report can identify a later time to open
        # or to close the observatory early during the night.
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        self.weather_report_wait_until_open=False
        self.weather_report_wait_until_open_time=ephem_now
        self.weather_report_close_during_evening=False
        self.weather_report_close_during_evening_time=ephem_now + 86400
        self.nightly_weather_report_complete=False
        # Run a weather report on bootup so observatory can run if need be. 
        if not g_dev['debug']:
            #self.global_wx()

            self.run_nightly_weather_report()
        else:
            self.nightly_weather_report_complete = True
            self.weather_report_is_acceptable_to_observe = True
            self.weather_report_wait_until_open=False
            #g_dev['obs'].open_and_enabled_to_observe = True
            
            #Consider running this once when in debug mode
        

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
        elif action == "run" and script in ['32TargetPointingRun', 'pointingRun', 'makeModel']:
            if req['gridType'] == 'sweep':
               self.equatorial_pointing_run(req, opt)
            elif req['gridType'] == 'cross':
                self.cross_pointing_run(req, opt)
            else:
                self.sky_grid_pointing_run(req, opt)
        elif action == "run" and script in ("collectBiasesAndDarks"):
            self.bias_dark_script(req, opt, morn=True)
        elif action == "run" and script == 'takeLRGBStack':
            self.take_lrgb_stack(req, opt)
        elif action == "run" and script == "takeO3HaS2N2Stack":
            self.take_lrgb_stack(req, opt)
        elif action.lower() in ["stop", "cancel"] or ( action == "run" and script == "stopScript"):
            #self.stop_command(req, opt)
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
            g_dev['mnt'].go_command(req, opt, calibrate=True, auto_center=True)
        elif action == 'run' and script == 'calibrateAtFieldCenter':
            g_dev['mnt'].go_command(req, opt, calibrate=True, auto_center=False)
        else:
            plog('Sequencer command:  ', command, ' not recognized.')

    def open_observatory(self,enc_status, ocn_status, no_sky=False):
        
        if not self.config['obsid_roof_control']:
            #plog("A request to open observatory was made even though this platform has no roof control. Returning.")
            return
        
        
        flat_spot, flat_alt = g_dev['evnt'].flat_spot_now()
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        
        # Only send an enclosure open command if the weather 
        if g_dev['seq'].weather_report_is_acceptable_to_observe:

            if not g_dev['debug'] and not g_dev['enc'].mode in [ 'Manual'] and (ephem.now() < g_dev['events']['Cool Down, Open'] ) or \
                (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
                plog ("NOT OPENING THE OBSERVATORY -- IT IS THE DAYTIME!!")
                g_dev["obs"].send_to_user("An open observatory request was rejected as it is during the daytime.")
                return
            else:
            
                try: 
                    # First unpark and move telescope away from the sun or just to the home position. 
                    plog("Unparking Scope in preparation for observatory opening.")
                    if g_dev['mnt'].mount.AtParK:
                        g_dev['mnt'].unpark_command({}, {})
                    
                    # If during the flat period, point it away from the sun, otherwise point the telescope at the home position                
                    if (g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['End Eve Sky Flats']):
                        plog("Unparking Scope and pointing it away from the sun.")
                        g_dev['mnt'].slewToSkyFlatAsync(skip_open_test=True)                
                    elif (g_dev['events']['Morn Sky Flats'] <= ephem_now < g_dev['events']['End Morn Sky Flats']):
                        plog("Unparking Scope and pointing it away from the sun.")
                        g_dev['mnt'].slewToSkyFlatAsync(skip_open_test=True)
                    else:
                        plog("Unparking Scope and pointing it to the home position.")
                        g_dev['mnt'].home_command()
                    
                    
                    self.time_of_next_slew = time.time() + 600 
                    #time.sleep(10)
                    #plog("Open and slew Dome to azimuth opposite the Sun:  ", round(flat_spot, 1))
                    plog("Attempting to open the roof.")
                    #breakpoint()
                    if ocn_status == None:
                            if self.config['obsid_roof_control'] and not enc_status['shutter_status'] in ['Open', 'open','Opening', 'opening'] and g_dev['enc'].mode == 'Automatic'\
                            and (self.config['obsid_allowed_to_open_roof']) and self.weather_report_is_acceptable_to_observe:
                            #breakpoint()
                                self.opens_this_evening= self.opens_this_evening+1                    
                                
                                g_dev['enc'].open_roof_directly({}, {})
                                #g_dev['enc'].open_command({}, {})
                                #plog("blip")
                        
                                
                                
                    elif self.config['obsid_roof_control']  and not enc_status['shutter_status'] in ['Open', 'open','Opening', 'opening'] and g_dev['enc'].mode == 'Automatic' \
                        and ocn_status['hold_duration'] <= 0.1 and self.config['obsid_allowed_to_open_roof'] and self.weather_report_is_acceptable_to_observe:   #NB
                        #breakpoint()
                        self.opens_this_evening= self.opens_this_evening+1                    
                        
                        g_dev['enc'].open_roof_directly({}, {})
                        #g_dev['enc'].open_command({}, {})
                        #plog("plop")            
                        
                    plog("Attempting to Open Shutter. Waiting until shutter opens")
                    if not g_dev['enc'].enclosure.ShutterStatus == 0:
                        time.sleep(self.config['period_of_time_to_wait_for_roof_to_open'])
                    
                    self.enclosure_next_open_time = time.time() + (self.config['roof_open_safety_base_time']*60) * g_dev['seq'].opens_this_evening
                    
                    if g_dev['enc'].enclosure.ShutterStatus == 0:                    
                        g_dev['obs'].open_and_enabled_to_observe = True                    
                        
                        try:
                            plog("Synchronising dome.")
                            g_dev['enc'].sync_mount_command({}, {})
                        except:
                            pass
                        #Prior to skyflats no dome following.
                        self.dome_homed = False
                        
                        return
                    
                    else:
                        plog("Failed to open roof, parking telescope again and sending the close command to the roof.")
                        #g_dev['enc'].close_roof_directly()
                        plog ("opens this eve: " + str(g_dev['seq'].opens_this_evening))
                        plog ("minutes until next open attempt ALLOWED: " + str( (g_dev['seq'].enclosure_next_open_time - time.time()) /60))
                        g_dev['enc'].close_roof_directly({}, {})
                        
                        #g_dev['enc'].close_command({}, {})
                        if not g_dev['mnt'].mount.AtParK:   ###Test comment here
                            g_dev['mnt'].park_command({}, {}) # Get there early
                        return
                        
                        
                    
                except Exception as e:
                    plog ("Enclosure opening glitched out: ", e)
                    plog(traceback.format_exc())
        
        else:
            plog("An enclosure command was rejected because the weather report was not acceptable.")
        
        return

    def park_and_close(self, enc_status):
        try:
            if not g_dev['mnt'].mount.AtParK:   ###Test comment here
                g_dev['mnt'].park_command({}, {}) # Get there early
        except:
            plog("Park not executed during Park and Close" )
        try:
            if self.config['obsid_roof_control']  and g_dev['enc'].mode == 'Automatic': # and enc_status['shutter_status'] in ['open', ] $ Don't check, just close!
                #g_dev['enc'].close_command( {}, {})
                g_dev['obs'].send_to_user("Closing the Shutter", p_level='INFO')
                plog("Closing the Shutter")
                g_dev['enc'].enclosure.CloseShutter()
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
        #self.global_wx()

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
        
        
        # Do this in case of WEMA faults.... they can crash these sequencer 
        # things when it looks for shutter_status
        if enc_status == None:
            enc_status = {'shutter_status': 'Unknown'}
        
        # Check for delayed opening of the observatory and act accordingly.

        # If the observatory is simply delayed until opening, then wait until then, then attempt to start up the observatory
        if self.weather_report_wait_until_open and not self.cool_down_latch:
            if ephem_now >  self.weather_report_wait_until_open_time:
                
                self.cool_down_latch=True
                self.weather_report_wait_until_open == False
                # Things may have changed! So re-checking the weather and such
                
                # Reopening config and resetting all the things.
                # This is necessary just in case a previous weather report was done today
                # That can sometimes change the timing. 
                self.astro_events.compute_day_directory()
                self.astro_events.calculate_events()
                #self.astro_events.display_events()
                g_dev['obs'].astro_events = self.astro_events
                # Run nightly weather report
                self.run_nightly_weather_report()
                
                
                
                if not g_dev['obs'].open_and_enabled_to_observe and self.weather_report_is_acceptable_to_observe==True:
                    if (g_dev['events']['Cool Down, Open'] < ephem.now() < g_dev['events']['Observing Ends']):
                        if time.time() > self.enclosure_next_open_time and self.opens_this_evening < self.config['maximum_roof_opens_per_evening']:
                            #self.enclosure_next_open_time = time.time() + 300 # Only try to open the roof every five minutes
                            
                            #self.weather_report_is_acceptable_to_observe=True
                            self.open_observatory(enc_status, ocn_status)
                            
                            # If the observatory opens, set clock and auto focus and observing to now
                            if g_dev['obs'].open_and_enabled_to_observe:
                                self.weather_report_is_acceptable_to_observe=False
                                self.night_focus_ready=True
                                obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
                                #g_dev['events']['Clock & Auto Focus'] = ephem_now - 0.1/24
                                #g_dev['events']['Observing Begins'] = ephem_now + 0.1/24
                                self.weather_report_wait_until_open=False
                                self.weather_report_is_acceptable_to_observe=True
                                if (g_dev['events']['Observing Begins '] < ephem.now() < g_dev['events']['Observing Ends']):
                                    # Move to reasonable spot
                                    if g_dev['mnt'].mount.Tracking == False:
                                        if g_dev['mnt'].mount.CanSetTracking:   
                                            g_dev['mnt'].mount.Tracking = True
                                        else:
                                            plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
    
                                    g_dev['mnt'].move_to_azalt(70, 70)
                                    g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                                        days=1
                                    )  # Initialise last focus as yesterday
    
                                    # Autofocus
                                    req2 = {'target': 'near_tycho_star', 'area': 150}
                                    opt = {}
                                    plog ("Running initial autofocus upon opening observatory")
                                    self.extensive_focus_script(req2, opt)
                self.cool_down_latch = False
        
        # If the observatory is meant to shut during the evening
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        if self.weather_report_close_during_evening==True :
            if ephem_now >  self.weather_report_close_during_evening_time and ephem_now < events['Morn Bias Dark']: # Don't want scope to cancel all activity during bias/darks etc.
                if self.config['obsid_roof_control']  and g_dev['enc'].mode == 'Automatic':
                    self.weather_report_is_acceptable_to_observe=False
                    plog ("End of Observing Period due to weather. Closing up observatory early.")
                    g_dev['obs'].cancel_all_activity()
                    g_dev['obs'].open_and_enabled_to_observe=False
                    g_dev['enc'].enclosure.CloseShutter()
                    #while g_dev['enc'].enclosure.ShutterStatus == 3:
                    #plog ("closing")
                    plog ("Also Parking the Scope")    
                    if not g_dev['mnt'].mount.AtPark:  
                        g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command() 
                    self.weather_report_close_during_evening=False 
                    
                    
                    
        # Do nightly weather report at cool down open 
        if (g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends']) and not self.nightly_weather_report_complete and not g_dev['debug']:

            # Reopening config and resetting all the things.
            # This is necessary just in case a previous weather report was done today
            # That can sometimes change the timing. 
            self.astro_events.compute_day_directory()
            self.astro_events.calculate_events()
            #self.astro_events.display_events()
            g_dev['obs'].astro_events = self.astro_events
            # Run nightly weather report
            self.run_nightly_weather_report()
            self.nightly_weather_report_complete=True
            
            # Also make sure nightly reset is switched to go off
            self.nightly_reset_complete = False
            # As well as nightly focus routine.
            self.night_focus_ready=True
        
        if ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends']) and \
               g_dev['enc'].mode == 'Automatic') and not self.cool_down_latch  and not g_dev['ocn'].wx_hold and not enc_status['shutter_status'] in ['Software Fault', 'Closing', 'Error']:

            self.cool_down_latch = True
            
            if not g_dev['obs'].open_and_enabled_to_observe and self.weather_report_is_acceptable_to_observe==True and self.weather_report_wait_until_open==False:
                #print (self.enclosure_next_open_time)
                #print (self.enclosure_next_open_time - time.time()                       )
                #print (self.opens_this_evening)
                if time.time() > self.enclosure_next_open_time and self.opens_this_evening < self.config['maximum_roof_opens_per_evening']:
                    
                    #self.enclosure_next_open_time = time.time() + 300 # Only try to open the roof every five minutes maximum
                    if self.config['obsid_roof_control']:
                        self.open_observatory(enc_status, ocn_status)
                    
                    # If the observatory opens, set clock and auto focus and observing to now
                    if g_dev['obs'].open_and_enabled_to_observe:
                        self.night_focus_ready=False
                        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
                        #g_dev['events']['Clock & Auto Focus'] = ephem_now - 0.1/24
                        #g_dev['events']['Observing Begins'] = ephem_now + 0.1/24
                        self.weather_report_wait_until_open=False
                        #self.weather_report_is_acceptable_to_observe=True
                        if (g_dev['events']['Observing Begins'] < ephem.now() < g_dev['events']['Observing Ends']):
                            # Move to reasonable spot
                            if g_dev['mnt'].mount.Tracking == False:
                                if g_dev['mnt'].mount.CanSetTracking:   
                                    g_dev['mnt'].mount.Tracking = True
                                else:
                                    plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")

                            g_dev['mnt'].move_to_azalt(70, 70)
                            g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                                days=1
                            )  # Initialise last focus as yesterday

                            # Autofocus
                            req2 = {'target': 'near_tycho_star', 'area': 150}
                            opt = {}
                            plog ("Running initial autofocus upon opening observatory")
                            
                            self.extensive_focus_script(req2, opt)
                        else:
                            self.night_focus_ready=True
                            
                   
            self.cool_down_latch = False

        # Check that nightly reset switch is reset at start of observing eve. 
        #if self.nightly_reset_complete == True:
        #    if events['Eve Bias Dark'] <= ephem_now :
        #        self.nightly_reset_complete == False
                
        # If in post-close and park era of the night, check those two things have happened!       
        if (events['Close and Park'] <= ephem_now < events['End Morn Bias Dark'])  \
               and g_dev['enc'].mode == 'Automatic':
            
            if not g_dev['mnt'].mount.AtPark:  
                plog ("Found telescope unparked after Close and Park, parking the scope")
                g_dev['mnt'].home_command()
                g_dev['mnt'].park_command()
            
            if g_dev['enc'].status['shutter_status'] in ['Open', 'open']:
                plog ("Found shutter open after Close and Park, shutting up the shutter")
                self.park_and_close(enc_status)
            
            


        if not self.bias_dark_latch and ((events['Eve Bias Dark'] <= ephem_now < events['End Eve Bias Dark']) and \
             self.config['auto_eve_bias_dark'] and not  self.eve_bias_done and g_dev['enc'].mode in ['Automatic', 'Autonomous', 'Manual'] and g_dev['obs'].camera_temperature_in_range_for_calibrations):   #events['End Eve Bias Dark']) and \
            
            self.bias_dark_latch = True
            req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 45, \
                   'numOfDark': 15, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 360, \
                   'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  # NB NB All of the prior is obsolete
            opt = {}
            
            # We don't want to close the enclosure in the evening as it may be open cooling it off
            # The bias_dark_script parks the scope anyway. 
            
            self.bias_dark_script(req, opt, morn=False)
            self.eve_bias_done = True
            self.bias_dark_latch = False
            
            

            #g_dev['mnt'].park_command({}, {})       


        elif not self.eve_sky_flat_latch and ((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
               and g_dev['enc'].mode in [ 'Automatic', 'Autonomous'] and not g_dev['ocn'].wx_hold and \

               self.config['auto_eve_sky_flat'] and g_dev['obs'].open_and_enabled_to_observe and not self.eve_flats_done and g_dev['obs'].camera_temperature_in_range_for_calibrations):

            self.eve_sky_flat_latch = True
            self.current_script = "Eve Sky Flat script starting"
            #plog('Skipping Eve Sky Flats')
            
            self.sky_flat_script({}, {}, morn=False)   #Null command dictionaries
            
            if g_dev['mnt'].mount.Tracking == False:
                if g_dev['mnt'].mount.CanSetTracking:   
                    g_dev['mnt'].mount.Tracking = True
                else:
                    plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
            self.eve_sky_flat_latch = False
            self.eve_flats_done = True
            

        elif ((g_dev['events']['Clock & Auto Focus']  <= ephem_now < g_dev['events']['Observing Begins']) and \
               g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold  \
                and self.night_focus_ready==True and  g_dev['obs'].open_and_enabled_to_observe and not self.clock_focus_latch:

            
            self.clock_focus_latch = True
            #if self.night_focus_ready==True and g_dev['obs'].open_and_enabled_to_observe:
            g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')

            # Move to reasonable spot
            if g_dev['mnt'].mount.Tracking == False:
                if g_dev['mnt'].mount.CanSetTracking:   
                    g_dev['mnt'].mount.Tracking = True
                else:
                    plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")

            g_dev['mnt'].move_to_azalt(70, 70)
            g_dev['foc'].time_of_last_focus = datetime.datetime.now() - datetime.timedelta(
                days=1
            )  # Initialise last focus as yesterday

            # Autofocus
            req2 = {'target': 'near_tycho_star', 'area': 150}
            opt = {}
            self.extensive_focus_script(req2, opt, throw = g_dev['foc'].throw)

            # Pointing
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
            opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, solve_it=True)
            
            self.night_focus_ready=False
            self.clock_focus_latch = False

# =============================================================================
#         NB NB Note below often faults, should be in a try except instead of this
#         complex nested if construct.  Enc_status can be None if Wema is not  operating.
#         Perhaps we should default set enc_status['enclosure_mode'] = 'Shutdown' as a default?
# =============================================================================
        elif (events['Observing Begins'] <= ephem_now \
                                   < events['Observing Ends']) and not g_dev['ocn'].wx_hold \
                                   and  g_dev['obs'].blocks is not None and g_dev['obs'].projects \
                                   is not None and g_dev['obs'].open_and_enabled_to_observe:

            try:
                
               
                self.nightly_reset_complete = False
                
                if enc_status['enclosure_mode'] in ['Autonomous!', 'Automatic']:
                    blocks = g_dev['obs'].blocks
                    projects = g_dev['obs'].projects
                    debug = False
                    
                    
                    # MTF COMMENTED THIS OUT AS THE ROOF CONTROL IS NOT UP TO THIS
                    # BLOCK OF SEQUENCER COMMANDS
                    # if self.config['obsid_roof_control']  and  enc_status['shutter_status'] in ['Closed', 'closed'] \
                    #     and float(ocn_status['hold_duration']) <= 0.1 and self.weather_report_is_acceptable_to_observe:
                    #     #breakpoint()
                    #     g_dev['enc'].open_command({}, {})
                    #     plog("Opening dome, will set Synchronize in 10 seconds.")
                    #     time.sleep(10)
                    # try:
                    #     g_dev['enc'].sync_mount_command({}, {})
                    # except: 
                    #     pass
        
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
                                plog (block)
                                plog ("Skipping a block that contains an empty project")
                                return
        
                            g_dev['obs'].update()
                            completed_block = self.execute_block(block)  #In this we need to ultimately watch for weather holds.
                            try:
                                self.append_completes(completed_block['event_id'])
                            except:
                                plog ("block complete append didn't work")
                                plog(traceback.format_exc())
                                
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
                
                
                
                                
                                
                                


            except:
                plog(traceback.format_exc())
                plog("Hang up in sequencer.")
        
        
        
        elif not self.morn_sky_flat_latch and ((events['Morn Sky Flats'] <= ephem_now < events['End Morn Sky Flats'])  \
               and g_dev['enc'].mode == 'Automatic' and not g_dev['ocn'].wx_hold and \
               self.config['auto_morn_sky_flat']) and not self.morn_flats_done and g_dev['obs'].camera_temperature_in_range_for_calibrations and g_dev['obs'].open_and_enabled_to_observe:

                   #self.config['auto_morn_sky_flat']) and not self.morn_flats_done and g_dev['obs'].open_and_enabled_to_observe :

            #self.time_of_next_slew = time.time() -1
            self.morn_sky_flat_latch = True
            
          
            
            self.current_script = "Morn Sky Flat script starting"
            
            self.sky_flat_script({}, {}, morn=True)   #Null command dictionaries
                        
            
            self.morn_sky_flat_latch = False
            self.morn_flats_done = True
            
        
                   
            
        elif not self.morn_bias_dark_latch and (events['Morn Bias Dark'] <= ephem_now < events['End Morn Bias Dark']) and \
                  self.config['auto_morn_bias_dark'] and not  self.morn_bias_done and g_dev['obs'].camera_temperature_in_range_for_calibrations: # and g_dev['enc'].mode == 'Automatic' ):
            #breakpoint()
            self.morn_bias_dark_latch = True
            req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 63, \
                    'numOfDark': 31, 'darkTime': 600, 'numOfDark2': 31, 'dark2Time': 600, \
                    'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  #This specificatin is obsolete
            opt = {}
            #No action needed on  the enclosure at this level
            self.park_and_close(enc_status)
            #NB The above put dome closed and telescope at Park, Which is where it should have been upon entry.
            self.bias_dark_script(req, opt, morn=True)

            self.park_and_close(enc_status)
            self.morn_bias_dark_latch = False
            self.morn_bias_done = True
            
        elif (events['Nightly Reset'] <= ephem_now < events['End Nightly Reset']): # and g_dev['enc'].mode == 'Automatic' ):
            
            if self.nightly_reset_complete == False:
                self.nightly_reset_script()

            
        
        else:
            self.current_script = "No current script, or site not in Automatic."
            try:
                pass
                #self.park_and_close(enc_status)
            except:
                plog("Park and close failed at end of sequencer loop.")
                
                
        #Here is where observatories who do their biases at night... well.... do their biases!
        #If it hasn't already been done tonight.

        
        if self.config['auto_midnight_moonless_bias_dark']:
            # Check it is in the dark of night
            if  (events['Astro Dark'] <= ephem_now < events['End Astro Dark']):     
                # Check that there isn't any activity indicating someone using it...
                if (time.time() - g_dev['obs'].time_of_last_exposure) > 900 and (time.time() - g_dev['obs'].time_of_last_slew) > 900:
                    # Check no other commands or exposures are happening
                    if g_dev['obs'].cmd_queue.empty() and not g_dev["cam"].exposure_busy:
                        # If enclosure is shut for maximum darkness
                        if enc_status['shutter_status'] in ['Closed', 'closed']:
                            # Check the temperature is in range
                            currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
                            moondata=get_moon(Time.now()).transform_to(currentaltazframe)                        
                            if (moondata.alt.deg < -15):
                                # If the moon is way below the horizon                        
                                if g_dev['obs'].camera_temperature_in_range_for_calibrations:
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
        
        if (ephem.now() < g_dev['events']['Naut Dusk'] ) or \
            (g_dev['events']['Naut Dawn']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT RUNNING PROJECT BLOCK -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A project block was rejected as it is during the daytime.")            
            return
        
        g_dev['obs'].update()
        
        plog('|n|n Staring a new project!  \n')
        plog(block_specification, ' \n\n\n')

        calendar_event_id=block_specification['event_id']

        self.block_guard = True
        # NB we assume the dome is open and already slaving.
        block = copy.deepcopy(block_specification)
        ocn_status = g_dev['ocn'].status
        enc_status = g_dev['enc'].status
        # #unpark, open dome etc.
        # #if not end of block
        try:
            g_dev['enc'].sync_mount_command({}, {})
        except:
            pass
        g_dev['mnt'].unpark_command({}, {})
        g_dev['mnt'].Tracking = True   # unpark_command({}, {})
        g_dev['cam'].user_name = 'tobor'
        g_dev['cam'].user_id = 'tobor'
        #NB  Servo the Dome??
        #timer = time.time() - 1  #This should force an immediate autofocus.
        
        opt = {}
        t = 0
        '''
        # to do is Targets*Mosaic*(sum of filters * count)
        Assume for now we only have one target and no mosaic factor.
        The the first thing to do is figure out how many exposures
        in the series.  If enhance AF is true they need to be injected
        at some point, but it does not decrement. This is still left to do
        '''
        #breakpoint()
        
        # this variable is what we check to see if the calendar
        # event still exists on AWS. If not, we assume it has been
        # deleted or modified substantially.
        calendar_event_id = block_specification['event_id']

        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            try:
                #breakpoint()
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

            #if self.config['obsid_roof_control']  and enc_status['shutter_status'] in ['Closed', 'closed'] and ocn_status['hold_duration'] <= 0.1 and self.weather_report_is_acceptable_to_observe:   #NB  # \  NB NB 20220901 WER fix this!

                #breakpoint()
            #    g_dev['enc'].open_command({}, {})
            #    plog("Opening dome, will set Synchronize in 10 seconds.")
            #    time.sleep(10)
            #try:
            #    g_dev['enc'].sync_mount_command({}, {})
            #except: 
            #    pass

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
            
            # Quick pointing check and re_seek at the start of each project block
            # Otherwise everyone will get slightly off-pointing images
            # Necessary
            # Pointing
            # Reset Solve timers

            plog ("Taking a quick pointing check and re_seek for new project block")
            #g_dev['obs'].last_solve_time = datetime.datetime.now()
            ##g_dev['obs'].images_since_last_solve = 0
            #req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
            #opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
            #g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, solve_it=True)
            
            result = self.centering_exposure()
            
            if result == 'blockend':
                plog ("End of Block, exiting project block.")
                if block_specification['project']['project_constraints']['close_on_block_completion']:
                    try:
                        pass#g_dev['enc'].enclosure.Slaved = False   NB with wema no longer exists
                    except:
                        pass
                    #self.redis_server.set('unsync_enc', True, ex=1200)
                    #g_dev['enc'].close_command({}, {})
                    g_dev['mnt'].park_command({}, {})
                    plog("Auto PARK (not Close) attempted at end of block.")
                self.block_guard = False
                
                return block_specification
            
            if result == 'calendarend':
                plog ("Calendar Item containing block removed from calendar")
                plog ("Site bailing out of running project")
                self.block_guard = False                
                return block_specification
            

            
            g_dev['obs'].update()


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

                    req2 = {'target': 'near_tycho_star', 'area': 150}
                    if not g_dev['debug']:
                        self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)
                    just_focused = True
                    g_dev["foc"].focus_needed = False

                # A flag to make sure the first image after a slew in an exposure set is solved, but then onto the normal solve timer
                reset_solve = True
                
                #cycle through exposures decrementing counts    MAY want to double check left-to do but do nut remultiply by 4
                for exposure in block['project']['exposures']:
                    
                    
                    
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    g_dev['obs'].scan_requests()
                    foundcalendar=False
                    for tempblock in g_dev['obs'].blocks:
                        plog (tempblock['event_id'])
                        if tempblock['event_id'] == calendar_event_id :
                            foundcalendar=True
                            block['end']=tempblock['end']
                    if not foundcalendar:
                        plog ("could not find calendar entry, cancelling out of block.")
                        g_dev["obs"].send_to_user("Calendar block removed. Stopping project run.")   
                        self.block_guard = False
                        return block_specification

                    just_focused = True

                    plog ("Observing " + str(block['project']['project_targets'][0]['name']))

                    plog("Executing: ", exposure, left_to_do)
                    color = exposure['filter']
                    exp_time =  float(exposure['exposure'])
                    binning = '1 1'

                    # if exposure['bin'] == '"optimal"':
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['optimal_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
                    # elif exposure['bin'] == '"fine"' :
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['fine_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
                    # elif exposure['bin'] == '"coarse"' :
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['coarse_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
                    # elif exposure['bin'] == '"eng"' :
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['eng_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
                    # elif exposure['bin'] in[0, '0', '0,0', '0, 0', '0 0']:
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['fine_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
                    # elif exposure['bin'] in [1, '1,1', '1, 1', '1 1']:
                    #     binning = '1 1'
                    # elif exposure['bin'] in [2, '2,2', '2, 2', '2 2']:
                    #     binning = '2 2'
                    # elif exposure['bin'] in [3, '3,3', '3, 3', '3 3']:
                    #     binning = '3 3'
                    # elif exposure['bin'] in [4, '4,4', '4, 4', '4 4']:
                    #     binning = '4 4'
                    # else:
                    #     tempBinString=str(g_dev['cam'].config['camera']['camera_1_1']['settings']['optimal_bin'][0])
                    #     binning = tempBinString + ' ' + tempBinString
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
                            req = {'time': exp_time,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': imtype, 'smartstack' : smartstackswitch, 'longstackswitch' : longstackswitch, 'longstackname' : longstackname, 'block_end' : block['end']}   #  NB Should pick up filter and constants from config
                            opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': color, \
                                   'hint': block['project_id'] + "##" + dest_name, 'object_name': block['project']['project_targets'][0]['name'], 'pane': pane}
                            plog('Seq Blk sent to camera:  ', req, opt)
                            obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

                            now_date_timeZ = datetime.datetime.now().isoformat().split('.')[0] +'Z'
                            if now_date_timeZ >= block['end'] :
                                break
                            g_dev['obs'].update()
                            result = g_dev['cam'].expose_command(req, opt, user_name=user_name, user_id=user_id, user_roles=user_roles, no_AWS=False, solve_it=False, calendar_event_id=calendar_event_id)
                            g_dev['obs'].update()
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

                    # Check that the observing time hasn't completed or then night has not completed. 
                    # If so, set ended to True so that it cancels out of the exposure block.
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

        self.sequencer_hold = True
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

            #plog("Expose Biases and normal darks by configured binning.")

            #short_dark_time = self.config['camera']['camera_1_1']['settings']['ref_dark']
            #long_dark_time = self.config['camera']['camera_1_1']['settings']['long_dark']
            # NB NB Long term it would be slightly better to interleave bias and darks
            #bias_dark_bin_spec=self.config['camera']['camera_1_1']['settings']['bias_dark_bin_spec']  #Each is these is a list.
            #enable_bin= self.config['camera']['camera_1_1']['settings']['enable_bin']
            #for n_of_bias in range(bias_count):   #9*(9 +1) per cycle.
            
            
            # The way we make different binnings for CMOS camera is derived from a single
            # exposure of 1x1. So if it is a cmos camera, it is just 1x1.
            # Do not fear, the bin specs are used later on.
            #bias_dark_bin_spec=['1,1']
            
            # For each enabled binning in biasdark_bin_spec
            # Take.... biases and darks, then advance to another binning and repeat
            
            
            b_d_to_do = bias_count + dark_count
            try:
                stride = bias_count//dark_count
                plog("Tobor will interleave a dark every  " + str(stride) + "  biases.")
                single_dark = True
            except:
                stride = bias_count   #Just do all of the biases first.
                single_dark = False
                
            cool_down_opened_already=False
            while b_d_to_do > 0:
                g_dev['obs'].scan_requests()
                
                # The biasdark script can sometimes overrun the time that the roof should open, 
                # So a check for whether it hits cool down time in this loop is appropriate
                obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
                if ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Eve Sky Flats']) and \
                       g_dev['enc'].mode == 'Automatic') and not g_dev['ocn'].wx_hold and cool_down_opened_already == False:

                    
                    if not self.nightly_weather_report_complete and not g_dev['debug']:
                        self.run_nightly_weather_report()
                        self.nightly_weather_report_complete=True

                    #self.time_of_next_slew = time.time() -1
                    #plog ("got here")
                    
                    if self.config['obsid_roof_control'] and not g_dev['obs'].open_and_enabled_to_observe and self.weather_report_is_acceptable_to_observe==True and self.weather_report_wait_until_open==False and not self.cool_down_latch:
                        if time.time() > self.enclosure_next_open_time and self.opens_this_evening < self.config['maximum_roof_opens_per_evening']:
                            #self.enclosure_next_open_time = time.time() + 300 # Only try to open the roof every five minutes
                            self.cool_down_latch = True
                            g_dev['ocn'].status = g_dev['ocn'].get_status()
                            g_dev['enc'].status = g_dev['enc'].get_status()
                            ocn_status = g_dev['ocn'].status
                            enc_status = g_dev['enc'].status
                            self.open_observatory(enc_status, ocn_status)    
                            
                            if g_dev['enc'].enclosure.ShutterStatus == 0:                    
                                g_dev['obs'].open_and_enabled_to_observe = True 
                                cool_down_opened_already=True
                                self.night_focus_ready=True
                            self.cool_down_latch = False
                
                
                min_to_do = min(b_d_to_do, stride)
                plog("Expose " + str(stride) +" 1x1 bias frames.")
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'area': "Full", 'count': min_to_do, 'bin': 1 , \
                       'filter': 'dark'}
                    
                    
                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                
                  
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                b_d_to_do -= min_to_do
                
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                    return
                

                g_dev['obs'].update()
                
                # if ephem.now() + 210/86400 > ending:   #NB NB needs to be checked out
                #     break
                #I am changing this so the darks for the above binning are done after the biases  WER
                    
                #for ctr_darks in range((dark_count[ctr_dbb])):
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    break
                
                g_dev['obs'].scan_requests()
                
                if not single_dark:
                    
                    plog("Expose 1x1 dark of " \
                         + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count': 1, 'bin': 1, \
                            'filter': 'dark'}
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                       do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                        return
                    b_d_to_do -= 1
                    g_dev['obs'].update()
                    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                        break
                else:
                    plog("Expose 1x1 dark " + str(1) + " of " \
                             + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time,  'script': 'True', 'image_type': 'dark'}
                    opt = {'area': "Full", 'count': 1, 'bin': 1, \
                            'filter': 'dark'}
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                       do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
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

            self.sequencer_hold = False
            g_dev['mnt'].park_command({}, {}) # Get there early
            plog("Bias/Dark Phase has passed.")
            self.bias_dark_latch = False
            break
        self.bias_dark_latch = False
        return
            
    def collect_and_queue_neglected_fits(self):
        # UNDERTAKING END OF NIGHT ROUTINES
        
        # Go through and add any remaining fz files to the aws queue .... hopefully that is enough? If not, I will make it keep going until it is sure.
        #while True:
            
        plog ('Collecting orphaned fits and tokens to go up to BANZAI')
        dir_path=self.config['client_path'] +'/' + g_dev['obs'].name + '/' + 'archive/'
        
        orphan_path=self.config['client_path'] +'/' + g_dev['obs'].name + '/' + 'orphans/'
        if not os.path.exists(orphan_path):
            os.makedirs(orphan_path)
        
        
        cameras=glob(dir_path + "*/")
        #plog (cameras)
        # Setting runnight for mop up scripts
        
        #breakpoint()
        # Move all fits.fz to the orphan folder
        for camera in cameras:
            yesterday = datetime.datetime.now() - timedelta(1)
            runNight=datetime.datetime.strftime(yesterday, '%Y%m%d')     
            
            #breakpoint()
            nights = glob(camera + '*/')
            
            for obsnight in nights:
                orphanfits=glob(obsnight + 'raw/*.fits.fz')
                
                for orphanfile in orphanfits:
                    try:
                        shutil.move(orphanfile, orphan_path)
                    except:
                        print ("Couldn't move orphan: " + str(orphanfile))
        
                
        # Add all fits.fz members to the AWS queue
        #breakpoint() 
        bigfzs=glob(orphan_path + '*.fz')
        #breakpoint()
        
        
        for fzneglect in bigfzs:
            plog ("Reattempting upload of " + str(os.path.basename(fzneglect)))
            #breakpoint()
            #image = (im_path, name)
            #g_dev["obs"].aws_queue.put((priority, image), block=False)

            # Enqueue into the stream but at the lowest priority ever.
            g_dev['cam'].enqueue_for_AWS(56000000, orphan_path, fzneglect.split('orphans')[-1].replace('\\',''))
            #g_dev['obs'].send_to_aws()
        
        
        bigtokens=glob(g_dev['obs'].obsid_path + 'tokens/*.token')
        for fzneglect in bigtokens:
            plog ("Reattempting upload of " + str(os.path.basename(fzneglect)))
            #breakpoint()
            #image = (im_path, name)
            #g_dev["obs"].aws_queue.put((priority, image), block=False)

            # Enqueue into the stream but at the lowest priority ever.
            g_dev['cam'].enqueue_for_AWS(56000000, g_dev['obs'].obsid_path + 'tokens/', fzneglect.split('tokens')[-1].replace('\\',''))
            #g_dev['obs'].send_to_aws()
    
    
    def nightly_reset_script(self):
        # UNDERTAKING END OF NIGHT ROUTINES

        # Never hurts to make sure the telescope is parked for the night
        #g_dev['mnt'].park_command({}, {})
        self.park_and_close(enc_status = g_dev['enc'].status)

        self.eve_flats_done = False
        self.morn_flats_done = False
        self.morn_bias_done = False
        self.eve_bias_done = False
        self.nightime_bias_counter = 0
        self.nightime_dark_counter = 0

        self.nightly_weather_report_complete=False
        # Set weather report to false because it is daytime anyways.
        self.weather_report_is_acceptable_to_observe=False
        
        # Setting runnight for mop up scripts
        yesterday = datetime.datetime.now() - timedelta(1)
        runNight=datetime.datetime.strftime(yesterday, '%Y%m%d')

        # Check the archive directory and upload any big fits that haven't been uploaded
        # wait until the queue is empty before mopping up
        self.collect_and_queue_neglected_fits()
        

        #time.sleep(300)
        #if (g_dev['obs'].aws_queue.empty()):
        #break

        


        # At this stage, we want to empty the AWS Queue!
        # We are about to pull all the fits.fz out from their folders
        # And dump them in the orphans folder so we want the queue
        # cleared to reconstitute it.
        plog ("Emptying AWS Queue To Reconstitute it from the Orphan Directory")
        with g_dev['obs'].aws_queue.mutex:
            g_dev['obs'].aws_queue.queue.clear()

        while (not g_dev['obs'].aws_queue.empty()):
            plog ("Waiting for the AWS queue to complete it's last job")
            time.sleep(1)
              

        # Before Culling, making sure we go through and harvest
        # all the orphaned and neglected files that actually
        # do need to get to BANZAI
        self.collect_and_queue_neglected_fits()
        
        
        
        # Sending token to AWS to inform it that all files have been uploaded
        plog ("sending end of night token to AWS")
        #g_dev['cam'].enqueue_for_AWS(jpeg_data_size, paths['im_path'], paths['jpeg_name10'])
        
        isExist = os.path.exists(g_dev['obs'].obsid_path + 'tokens')
        if not isExist:
            os.makedirs(g_dev['obs'].obsid_path + 'tokens')
        runNightToken= g_dev['obs'].obsid_path + 'tokens/' + self.config['site'] + runNight + '.token'
        with open(runNightToken, 'w') as f:
            f.write('Night Completed')
        image = (g_dev['obs'].obsid_path + 'tokens/', self.config['site'] + runNight + '.token')
        g_dev['obs'].aws_queue.put((30000000000, image), block=False)
        g_dev['obs'].send_to_user("End of Night Token sent to AWS.", p_level='INFO')
        

        # while True:
        #     if (not g_dev['obs'].aws_queue.empty()):
        #         g_dev['obs'].send_to_AWS()
        #         plog ("Emptying AWS queue at the end of the night")
        #         time.sleep(1)
        #     else:
        #         break

        # Culling the archive
        #FORTNIGHT=60*60*24*7*2
        if self.config['archive_age'] > 0 :
            plog (g_dev['obs'].obsid_path + 'archive/')
            dir_path=g_dev['obs'].obsid_path + 'archive/'
            #cameras=[d for d in os.listdir(dir_path) if os.path.isdir(d)]
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


        # sending this up to AWS
        '''
        Send the config to aws.
        '''
        uri = f"{self.config['site']}/config/"
        self.config['events'] = g_dev['events']
        response = g_dev['obs'].api.authenticated_request("PUT", uri, self.config)
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

        # Trying to figure out why sequencer isn't restarting.
        events = g_dev['events']
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

        # Reopening config and resetting all the things.
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events()
        self.astro_events.display_events()
        g_dev['obs'].astro_events = self.astro_events

        
        
        # Allow midnight calibrations
        #self.midnight_calibration_done = False
        self.nightly_reset_complete = True
        
        g_dev['mnt'].theskyx_tracking_rescues = 0

        self.opens_this_evening=0
        
        # Set weather report back to False until ready to check the weather again. 
        self.nightly_weather_report_complete=False
        self.weather_report_is_acceptable_to_observe=False
        self.weather_report_wait_until_open=False
        self.weather_report_wait_until_open_time=ephem_now
        self.weather_report_close_during_evening=False
        self.weather_report_close_during_evening_time=ephem_now + 86400
        self.nightly_weather_report_complete=False
        
        self.stop_script_called=False
        self.stop_script_called_time=time.time()
        
        # No harm in doubly checking it has parked
        g_dev['mnt'].park_command({}, {})
        
        # Now time to regenerate the local masters
        
        self.regenerate_local_masters()
        
        return
        
    def regenerate_local_masters(self):
        
        # NOW to get to the business of constructing the local calibrations
              
        
        # Start with biases
        # Get list of biases
        plog (datetime.datetime.now().strftime("%H:%M:%S"))
        plog ("Regenerating bias")
        darkinputList=(glob(g_dev['obs'].local_dark_folder +'*.n*'))
        inputList=(glob(g_dev['obs'].local_bias_folder +'*.n*'))
# =============================================================================
        inputList = inputList[-19:] # WER used for speed testing
# =============================================================================
        
        
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
            
            
            #hdutest = fits.open(inputList[0])[1]
            hdutest=np.load(inputList[0], mmap_mode='r')
            #breakpoint()
            shapeImage=hdutest.shape
            #headHold=hdutest.header 
            del hdutest

            # Make a temporary memmap file

            PLDrive = np.memmap(g_dev['obs'].local_bias_folder + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
            # Store the biases in the memmap file
            i=0
            for file in inputList:
                plog (datetime.datetime.now().strftime("%H:%M:%S"))

                
                
                starttime=datetime.datetime.now() 
                plog("Storing in a memmap array: " + str(file))
                
                #hdu1data = np.array(fits.open(file, memmap=True)[1].data, dtype=np.float32)
                
                #hdu1data = fits.open(file, memmap=True)[1].data
                hdu1data = np.load(file, mmap_mode='r')
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to load array: " + str(timetaken))
                                
                starttime=datetime.datetime.now() 
                PLDrive[:,:,i] = hdu1data    
                del hdu1data
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to put in memmap: " + str(timetaken))
                
                
                #starttime=datetime.datetime.now() 
                #PLDrive.flush()
                #timetaken=datetime.datetime.now() -starttime
                #plog ("Time Taken to flush memmap: " + str(timetaken))
                i=i+1
                
            # hold onto the header info            
                #plog ("Inputting bias: " + str(file) + " into memmap.")
                #hdu1 = fits.open(file)[1]            
                #PLDrive[:,:,i] = np.asarray(hdu1.data,dtype=np.float32)        
                #i=i+1
                #headHold=hdu1.header
                #hdu1.close()
                #del hdu1
            # hold onto the header info
            #headHold=hdu1.header
            #del hdu1

            plog ("**********************************")
            plog ("Median Stacking each bias row individually from the Reprojections")
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
            finalImage=np.zeros(shapeImage,dtype=float)
            for xi in range(shapeImage[0]):
                if xi % 500 == 0:
                    print ("Up to Row" + str(xi))
                    print (datetime.datetime.now().strftime("%H:%M:%S"))
                #for yi in range(shape_out[1]):
                #    
                finalImage[xi,:]=np.nanmedian(PLDrive[xi,:,:], axis=1)
            plog(datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("**********************************")
            
            
            masterBias=np.asarray(finalImage).astype(np.float32)
            #breakpoint()
            # Save this out to calibmasters
            #g_dev['obs'].obs_id
            #g_dev['cam'].alias
            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            #print (tempfrontcalib)
            try:
                fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                
                
                filepathaws=g_dev['obs'].calib_masters_folder
                filenameaws=tempfrontcalib + 'BIAS_master_bin1.fits'
                g_dev['cam'].enqueue_for_AWS(50, filepathaws,filenameaws)
            except Exception as e:
                plog ("Could not save bias frame: ",e)
                
            PLDrive._mmap.close()
            del PLDrive
            gc.collect()
            os.remove(g_dev['obs'].local_bias_folder  + 'tempfile')
    
            
            
            # NOW we have the master bias, we can move onto the dark frames
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("Regenerating dark") 
            inputList=(glob(g_dev['obs'].local_dark_folder +'*.n*'))
# =============================================================================
            inputList = inputList[-19:]  # Speed improvement WER 
# =============================================================================           
            PLDrive = np.memmap(g_dev['obs'].local_dark_folder  + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
            # Debias dark frames and stick them in the memmap
            i=0
            for file in inputList:   
                
                
                plog (datetime.datetime.now().strftime("%H:%M:%S"))
                
                
                starttime=datetime.datetime.now() 
                plog("Storing dark in a memmap array: " + str(file))
                
                
                
                #hdu1 = fits.open(file, memmap=True)[1]
                hdu1data = np.load(file, mmap_mode='r')
                #hdu1data = hdu1.
                #breakpoint()
                hdu1exp=float(file.split('_')[-2])
                #if any("EXPTIME" in s for s in hdu1.header.keys()):
                #    hdu1exp=hdu1.header['EXPTIME']
                #else:
                #    hdu1exp=hdu1.header['EXPOSURE']
                #del hdu1               
                #hdu1data= hdu1[0].data
                #hdu1header= hdu1.header
                #breakpoint()
                darkdeexp=(hdu1data-masterBias)/hdu1exp
                del hdu1data
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to load array and debias and divide dark: " + str(timetaken))
                    
                #if any("EXPTIME" in s for s in hdu1.header.keys()):
                #    darkdeexp=darkdebias/hdu1.header['EXPTIME']
                #else:
                #    darkdeexp=darkdebias/hdu1.header['EXPOSURE']
                starttime=datetime.datetime.now() 
                PLDrive[:,:,i] = np.asarray(darkdeexp,dtype=np.float32)
                del darkdeexp
                timetaken=datetime.datetime.now() -starttime
                plog ("Time Taken to put in memmap: " + str(timetaken))
                
                
                #starttime=datetime.datetime.now() 
                #PLDrive.flush()
                #timetaken=datetime.datetime.now() -starttime
                #plog ("Time Taken to flush memmap: " + str(timetaken))
                
                i=i+1
            # Hold onto the header
            #headHold=hdu1.header
            #del hdu1
    
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
                g_dev['cam'].enqueue_for_AWS(50, filepathaws,filenameaws)
            except Exception as e:
                plog ("Could not save dark frame: ",e)
            
            #g_dev['cam'].enqueue_for_AWS(50, '',g_dev['obs'].calib_masters_folder + tempfrontcalib + 'DARK_master_bin1.fits')
            
            
            PLDrive._mmap.close()
            del PLDrive
            gc.collect()
            os.remove(g_dev['obs'].local_dark_folder  + 'tempfile')
    
            
    
    
            
            # NOW that we have a master bias and a master dark, time to step through the flat frames!
            tempfilters=glob(g_dev['obs'].local_flat_folder + "*/")
            plog (datetime.datetime.now().strftime("%H:%M:%S"))
            plog ("Regenerating flats")        
            plog (tempfilters)
            
            if len(tempfilters) == 0:
                plog ("there are no filter directories, so not processing flats")
            else:
                
                
                
                
                for filterfolder in tempfilters:    
                    
                    plog (datetime.datetime.now().strftime("%H:%M:%S"))
                    filtercode=filterfolder.split('\\')[-2]
                    plog ("Regenerating flat for " + str(filtercode))
                    inputList=(glob(g_dev['obs'].local_flat_folder + filtercode + '/*.n*'))
                    # Generate temp memmap
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
                            #hdu1 = fits.open(file, memmap=True)[1]
                            #hdu1data = hdu1.data       
                            hdu1exp=float(file.split('_')[-2])
                            #if any("EXPTIME" in s for s in hdu1.header.keys()):
                            #    hdu1exp=hdu1.header['EXPTIME']
                            #else:
                            #    hdu1exp=hdu1.header['EXPOSURE']
                            #del hdu1               
                            
                            flatdebiaseddedarked=(hdu1data-masterBias)-(masterDark*hdu1exp) 
                            del hdu1data
                            # Normalising flat file
                            flatdebiaseddedarked = flatdebiaseddedarked/np.nanmedian(flatdebiaseddedarked)
                            
                            #hdu1data= hdu1[0].data
                            #hdu1header= hdu1.header
                            #breakpoint()
                            #darkdeexp=(hdu1data-masterBias)/hdu1exp
                            timetaken=datetime.datetime.now() -starttime
                            plog ("Time Taken to load array and debias and dedark and normalise flat: " + str(timetaken))
                            
                            
                            
                            #hdu1 = fits.open(file)[1]
                                           
                            #if any("EXPTIME" in s for s in hdu1.header.keys()):
                            #objdedark = objdebias-(masterDark.multiply(hdu1.header['EXPTIME']))
                            #    flatdebiaseddedarked = flatdebiased-(masterDark*(float(hdu1.header['EXPTIME'])))
                            #else:
                                #objdedark = objdebias-(masterDark.multiply(hdu1.header['EXPOSURE']))
                            #    flatdebiaseddedarked = flatdebiased-(masterDark*(float(hdu1.header['EXPOSURE'])))
                            
                            
                            starttime=datetime.datetime.now() 
                            #PLDrive[:,:,i] = np.asarray(flatdebiaseddedarked,dtype=np.float32)
                            PLDrive[:,:,i] = flatdebiaseddedarked
                            del flatdebiaseddedarked
                            timetaken=datetime.datetime.now() -starttime
                            plog ("Time Taken to put in memmap: " + str(timetaken))
                            
                            
                            #starttime=datetime.datetime.now() 
                            #PLDrive.flush()
                            #timetaken=datetime.datetime.now() -starttime
                            #plog ("Time Taken to flush memmap: " + str(timetaken))
                            
                            
                            i=i+1
                        # Hold onto the header
                        #headHold=hdu1.header
                        #del hdu1
            
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
                        #temporaryFlat=np.asarray(temporaryFlat, dtype=np.float32)
                        temporaryFlat[temporaryFlat < 0.1] = np.nan
                        
                        temporaryFlat=interpolate_replace_nans(temporaryFlat, kernel)
                        temporaryFlat[temporaryFlat < 0.1] = 0.8
                        temporaryFlat[np.isnan(temporaryFlat)] = 0.8
                        try:
                            np.save(g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy', temporaryFlat)            
                            
                            fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat, overwrite=True)
                            
                            filepathaws=g_dev['obs'].calib_masters_folder
                            filenameaws=tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits'
                            g_dev['cam'].enqueue_for_AWS(50, filepathaws,filenameaws)
                        except Exception as e:
                            plog ("Could not save flat frame: ",e)
                        #g_dev['cam'].enqueue_for_AWS(50, '',g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits')
                        
                        PLDrive._mmap.close()
                        del PLDrive
                        gc.collect()
                        os.remove(g_dev['obs'].local_flat_folder  + 'tempfile')
            
        
                # THEN reload them to use for the next night.
                
                # First delete the calibrations out of memory.
                
                g_dev['cam'].flatFiles = {}
                g_dev['cam'].hotFiles = {}              
                
        
                # try:            
                #     fileList = glob(g_dev['obs'].calib_masters_folder \
                #                          + "/masterFlat*_bin1.npy")
                    
                #     for file in fileList:
                #         g_dev['cam'].flatFiles.update({file.split("_")[1].replace ('.npy','') + '_bin1': file})
        
                # except:
                #     #breakpoint()
                #     plog("Flat frame re-upload did not work")
                
                try:           
                  
                    fileList = glob(g_dev['obs'].calib_masters_folder + '/masterFlat*_bin1.npy')
                    #breakpoint()
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
                    #breakpoint()
                
                #del masterBias
                #del masterDark

                plog ("Regenerated Flat Masters and Re-loaded them into memory.")

            plog ("Re-loading Bias and Dark masters into memory.")
            # Reload the bias and dark frames
            g_dev['cam'].biasFiles = {}
            g_dev['cam'].darkFiles = {}
            
            try:
                #self.biasframe = fits.open(
                #tempbiasframe = fits.open(self.archive_path  + self.alias + "/calibmasters" \
                #                          + "/BIAS_master_bin1.fits")
                #tempbiasframe = np.array(tempbiasframe[0].data, dtype=np.float32)
                g_dev['cam'].biasFiles.update({'1': masterBias})
                #del masterBias
                #del tempbiasframe
            except:
                plog("Bias frame master re-upload did not work.")
                #plog(traceback.format_exc()) 
                #breakpoint()               
                
            
            try:
                #self.darkframe = fits.open(
                #tempdarkframe = fits.open(self.archive_path  + self.alias + "/calibmasters" \
                #                          + "/DARK_master_bin1.fits")
    
                #tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
                g_dev['cam'].darkFiles.update({'1': masterDark})
                #del masterDark
                #del tempdarkframe
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
        
        
        if (ephem.now() < g_dev['events']['Eve Sky Flats']) or \
            (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING FLATS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it is during the daytime.")            
            return

        if (g_dev['events']['Naut Dusk'] < ephem.now() < g_dev['events']['Naut Dawn']):
            plog ("NOT DOING FLATS -- IT IS THE NIGHTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it too dark.")            
            return

        self.sky_guard = True   #20220409 I think this is obsolete or unused.
        plog('Sky Flat sequence Starting.')
        self.next_flat_observe = time.time()
        g_dev['obs'].send_to_user('Sky Flat sequence Starting.', p_level='INFO')
        evening = not morn
        camera_name = str(self.config['camera']['camera_1_1']['name'])
        flat_count = self.config['camera']['camera_1_1']['settings']['number_of_flat_to_collect']
        min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_flat_exposure'])
        max_exposure = float(self.config['camera']['camera_1_1']['settings']['max_flat_exposure'])

        exp_time = min_exposure # added 20220207 WER  0.2 sec for SRO


        #  Pick up list of filters is sky flat order of lowest to highest transparency.
        if g_dev["fil"].null_filterwheel == True:
            plog ("No Filter Wheel, just getting non-filtered flats")
            pop_list = [0]
        else:
            pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort'].copy()

            if morn:
                pop_list.reverse()
                plog('filters by high to low transmission:  ', pop_list)                
            else:
                plog('filters by low to high transmission:  ', pop_list)
                
            
        if morn:            
            ending = g_dev['events']['End Morn Sky Flats']
            #min_exposure=100 * min_exposure
        else:            
            ending = g_dev['events']['End Eve Sky Flats']
        #length = len(pop_list)
        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        exp_time = 0
        scale = 1.0
        #prior_scale = 1   #THIS will be inhereted upon completion of the prior filter
        collecting_area = self.config['telescope']['telescope1']['collecting_area']/31808.   # SAF at F4.9 is the reference
        #   and (g_dev['events']['Eve Sky Flats'] <
        


        while len(pop_list) > 0  and ephem.now() < ending and g_dev['obs'].open_and_enabled_to_observe:
            
                # This is just a very occasional slew to keep it pointing in the same general vicinity
                
                if time.time() >= self.time_of_next_slew:
                    if g_dev['mnt'].mount.AtParK:
                        g_dev['mnt'].unpark_command({}, {})
                        
                    g_dev['mnt'].slewToSkyFlatAsync()  
                    self.time_of_next_slew = time.time() + 600
                
                g_dev['obs'].scan_requests()
                g_dev['obs'].update() 
            
                if g_dev["fil"].null_filterwheel == False:
                    current_filter = pop_list[0]
                    plog("Beginning flat run for filter: " + str(current_filter))
                    g_dev['obs'].send_to_user("Beginning flat run for filter: " + str(current_filter))
                    
                    #g_dev['fil'].set_number_command(current_filter)  #  20220825  NB NB NB Change this to using a list of filter names.
                    
                    filter_gain = g_dev['fil'].return_filter_gain({"filter": current_filter}, {})  #  20220825  NB NB NB Chan
                
                    
                    # try:
                    #     _, filt_pointer = g_dev['fil'].set_name_command({"filter": current_filter}, {})  #  20220825  NB NB NB Chan
                    # except Exception as e:
                    #     plog('Failed to change filter in flat script: ', e)
                    #     plog("I think this happens if it can't find a substitute filter.... but need to check that! - MTF")
                    #     plog(traceback.format_exc())
                    #filter number for skylux colle
                
                acquired_count = 0
                
                flat_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                
                    
                target_flat = 0.5 * flat_saturation_level
                # if not g_dev['enc'].status['shutter_status'] in ['Open', 'open']:
                #     g_dev['obs'].send_to_user("Wait for roof to be open to take skyflats. 60 sec delay loop.", p_level='INFO')
                #     time.sleep(60)
                #     g_dev['obs'].update()
                #     continue
                scale = 1
                self.estimated_first_flat_exposure = False
                while (acquired_count < flat_count):# and g_dev['enc'].status['shutter_status'] in ['Open', 'open']: # NB NB NB and roof is OPEN! and (ephem_now +3/1440) < g_dev['events']['End Eve Sky Flats' ]:
                    #if g_dev['enc'].is_dome:   #Does not apply
                    g_dev['obs'].scan_requests()
                    g_dev['obs'].update()                    
                    
                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Observatory closed or disabled during flat script. Cancelling out of flat acquisition loop.")
                        return
                    
                    # Check that Flat time hasn't ended
                    if ephem.now() > ending:
                        plog ("Flat acquisition time finished. Breaking out of the flat loop.")
                        return
                    
                    if self.next_flat_observe < time.time():                
                        
                            
                        try:
                            try:
                                sky_lux = eval(self.redis_server.get('ocn_status'))['calc_HSI_lux']     #Why Eval, whould have float?
                            except:
                                #plog("Redis not running. lux set to 1000.")
                                try:
                                    sky_lux = float(g_dev['ocn'].status['calc_HSI_lux'])
                                except:
                                    sky_lux, _ = g_dev['evnt'].illuminationNow()
                                    
                        except:
                            sky_lux = None
        
                        #plog ("sky lux " + str(sky_lux))
        
                        # MF SHIFTING EXPOSURE TIME CALCULATOR EQUATION TO BE MORE GENERAL FOR ALL TELESCOPES
                        # This bit here estimates the initial exposure time for a telescope given the skylux
                        # or given no skylux at all!
                        if self.estimated_first_flat_exposure == False:
                            self.estimated_first_flat_exposure = True
                            if sky_lux != None:
                                if g_dev["fil"].null_filterwheel == False:                                    
                                    exp_time = target_flat/(collecting_area*sky_lux*float(filter_gain))  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                                    plog('Exposure time:  ', exp_time, scale, sky_lux, float(filter_gain))
                                else:
                                    #exp_time = scale*min_exposure
                                    exp_time = target_flat/(collecting_area*sky_lux*self.config['filter_wheel']['filter_wheel1']['flat_sky_gain'])  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                                    plog('Exposure time:  ', exp_time, scale)
                            else:                    
                                #exp_time = prior_scale*scale*target_flat
                                if morn:
                                
                                    exp_time = 5.0
                                else:
                                    exp_time = min_exposure
                                plog('Exposure time:  ', exp_time, scale)
                        else:
                            exp_time = scale * exp_time
            
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                            return
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                            return
                        
                        # Here it makes four tests and if it doesn't match those tests, then it will attempt a flat. 
                        if evening and exp_time > max_exposure:
                             #exp_time = 60    #Live with this limit.  Basically started too late
                             plog('Break because proposed evening exposure > maximum flat exposure: ' + str(max_exposure) + ' seconds:  ', exp_time)
                             #g_dev['obs'].send_to_user('Try next filter because proposed  flat exposure > 120 seconds.', p_level='INFO')
                             pop_list.pop(0)
                             acquired_count = flat_count + 1 # trigger end of loop
                             #break
                        elif morn and exp_time < min_exposure:
                             #exp_time = 60    #Live with this limit.  Basically started too late
                             plog('Break because proposed morning exposure < minimum flat exposure time:  ', exp_time)
                             #g_dev['obs'].send_to_user('Try next filter because proposed  flat exposure < min_exposure.', p_level='INFO')
                             pop_list.pop(0)
                             #min_exposure=min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_exposure'])
                             acquired_count = flat_count + 1 # trigger end of loop
                             #break
                        elif evening and exp_time < min_exposure:   #NB it is too bright, should consider a delay here.
                         #**************THIS SHOUD BE A WHILE LOOP! WAITING FOR THE SKY TO GET DARK AND EXP TIME TO BE LONGER********************
                             plog("Too bright for current filter, waiting 10s. Est. Exptime: " + str(exp_time))
                             #g_dev['obs'].send_to_user('Delay 60 seconds to let it get darker.', p_level='INFO')
                             self.estimated_first_flat_exposure = False
                             if time.time() >= self.time_of_next_slew:
                                g_dev['mnt'].slewToSkyFlatAsync()  
                                self.time_of_next_slew = time.time() + 600
                             self.next_flat_observe = time.time() + 10
                        elif morn and exp_time > max_exposure :   #NB it is too bright, should consider a delay here.
                          #**************THIS SHOUD BE A WHILE LOOP! WAITING FOR THE SKY TO GET DARK AND EXP TIME TO BE LONGER********************
                             plog("Too dim for current filter, waiting 10s Est. Exptime:  " + str(exp_time))
                             #g_dev['obs'].send_to_user('Delay 60 seconds to let it get lighterer.', p_level='INFO')
                             self.estimated_first_flat_exposure = False
                             if time.time() >= self.time_of_next_slew:
                                g_dev['mnt'].slewToSkyFlatAsync()  
                                self.time_of_next_slew = time.time() + 600
                             self.next_flat_observe = time.time() + 10
                             #*****************NB Recompute exposure or otherwise wait
                             exp_time = min_exposure
                        else:
                            exp_time = round(exp_time, 5)
                            
                            # If scope has gone to bed due to inactivity, wake it up!
                            if g_dev['mnt'].mount.AtParK:
                                g_dev['mnt'].unpark_command({}, {})
                                g_dev['mnt'].slewToSkyFlatAsync()  
                                self.time_of_next_slew = time.time() + 600
                            
                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                return
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                return
                            
                            # prior_scale = prior_scale*scale  #Only update prior scale when changing filters
                            #plog("Sky flat estimated exposure time: " + str(exp_time) + ", Scale:  " +str(scale))               
                                            
                            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}
                            
                            
                            # FIRST, lets get the highest resolution flat
            
                            if g_dev["fil"].null_filterwheel == False:
                                opt = { 'count': 1, 'bin':  1, 'area': 150, 'filter': current_filter}   #nb nb nb BIN CHNAGED FROM 2,2 ON 20220618 wer
                                #plog("using:  ", g_dev['fil'].filter_data[filt_pointer][0])
                            else:
                                opt = { 'count': 1, 'bin':  1, 'area': 150}   
                            
                            if ephem.now() >= ending:
                                if morn: # This needs to be here because some scopes do not do morning bias and darks
                                    try:
                                        g_dev['mnt'].park_command({}, {})
                                    except:
                                        plog("Mount did not park at end of morning skyflats.")
                                return
                            try:
                                self.time_of_next_slew = time.time()
                                fred = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, do_sep = False,skip_daytime_check=True)
                                
                                
                                try:
                                    if self.stop_script_called:
                                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                        return
                                    if not g_dev['obs'].open_and_enabled_to_observe:
                                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                        return
                                except Exception as e:
                                    plog ('something funny in stop_script still',e)
                                bright = fred['patch']    #  Patch should be circular and 20% of Chip area. ToDo project
                                #breakpoint()
                                #plog('Returned:  ', bright)
                                                                
                            except Exception as e:
                                plog('Failed to get a flat image: ', e)
                                plog(traceback.format_exc())
                                #plog("*****NO result returned*****  Will need to restart Camera")  #NB NB  NB this is drastic action needed.
                                
                                #breakpoint()
                                g_dev['obs'].update()
                                continue
                            
                            g_dev['obs'].scan_requests()
                            g_dev['obs'].update()
                            
                            try:
                                scale = target_flat / bright
                                #plog("New scale is:  ", scale)
                            except:
                                scale = 1.0
                                
                            # We only want to move after a successful set of independant binning flats
                            # If we move before we calculate exposure, we are wasting time slewing. 
                            g_dev['mnt'].slewToSkyFlatAsync()
                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")  
                                return
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                                return
                            
                            
            
                            if g_dev["fil"].null_filterwheel == False:
                                if sky_lux != None:
                                    #plog('\n\n', "Patch/Bright:  ", bright, g_dev['fil'].filter_data[filt_pointer][0], \
                                    plog(current_filter,' New Gain value: ', round(bright/(sky_lux*collecting_area*exp_time), 3), '\n\n')
                                else:
                                    #plog('\n\n', "Patch/Bright:  ", bright, g_dev['fil'].filter_data[filt_pointer][0], \
                                    plog(current_filter,' New Gain value: ', round(bright/(collecting_area*exp_time), 3), '\n\n')
                            else:
                                if sky_lux != None:
                                    #plog('\n\n', "Patch/Bright:  ", bright, \
            
                                    plog('New Gain value: ', round(bright/(sky_lux*collecting_area*exp_time), 3), '\n\n')
                                else:
                                    #plog('\n\n', "Patch/Bright:  ", bright,  \
                                    plog('New Gain value: ', round(bright/(collecting_area*exp_time), 3), '\n\n')
            

                            acquired_count += 1
                            if acquired_count == flat_count:
                                pop_list.pop(0)
                                #plog("SCALE USED *************************:  ", scale)
                                #prior_scale = scale     #Here is where we pre-scale the next filter. TEMPORARILLY TAKE THIS OUT
                                scale = 1
            
                            #obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
                            #g_dev['obs'].update()
                            continue
                    else:
                        time.sleep(10)

        if morn: 
            self.morn_sky_flat_latch = False
            #self.park_and_close(enc_status = g_dev['enc'].status)            
        else:
            self.eve_sky_flat_latch = False
            
                       
            
        plog('\nSky flat sequence complete.\n')
        g_dev["obs"].send_to_user("Sky flat collection complete.")            
        
        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
        self.sky_guard = False


    def screen_flat_script(self, req, opt):
        
        
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
        self.guard = False
        
        g_dev['mnt'].park_command({}, {})



    def auto_focus_script(self, req, opt, throw=600, skip_timer_check=False, extensive_focus=None):
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

        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING AUTO FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An auto focus was rejected as it is during the daytime.")            
            return

        # First check how long it has been since the last focus
        plog ("Time of last focus")
        plog (g_dev['foc'].time_of_last_focus)
        plog ("Time since last focus")
        plog (datetime.datetime.now() - g_dev['foc'].time_of_last_focus)


        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            return
            

        plog ("Threshold time between auto focus routines (hours)")
        plog (self.config['periodic_focus_time'])
        
        if skip_timer_check == False:
            if ((datetime.datetime.now() - g_dev['foc'].time_of_last_focus)) > datetime.timedelta(hours=self.config['periodic_focus_time']):
                plog ("Sufficient time has passed since last focus to do auto_focus")
                
            else:
                plog ("too soon since last autofacus")
                return
        
        
        
        
        
        g_dev['foc'].time_of_last_focus = datetime.datetime.now()
        
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

        if True: #req2['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters

            #  Go to closest Mag 7.5 Tycho * with no flip
            #focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec,g_dev['mnt'].current_sidereal)
            
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
                #plog("RA " + str(focus_patch_ra) + " DEC " + str(focus_patch_dec) )
                g_dev['mnt'].go_coord(focus_patch_ra, focus_patch_dec)
            except Exception as e:
                plog ("Issues pointing to a focus patch. Focussing at the current pointing." , e)
                plog(traceback.format_exc())

            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

            opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
        else:
            pass   #Just take an image where currently pointed.
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
        foc_pos0 = focus_start
        result = {}
        
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            return
        
        
        #g_dev['mnt'].go_coord(focus_patch_ra, focus_patch_dec)            
        g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
        
        
        # If no extensive_focus has been done, centre the focus field.
        if extensive_focus == None:
            g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')
            
            self.centering_exposure()
            
            g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')
        
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            return
        
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = ""
            
            #breakpoint()
            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            rot_report=0
            while g_dev['foc'].focuser.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'Waiting for Focuser to shift.\n'
                if g_dev['mnt'].mount.Slewing: st += 'Waiting for Mount to Slew\n'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if rot_report == 0:
                    plog(st)
                    st = ""
                    rot_report =1
                time.sleep(0.2)
                g_dev['obs'].scan_requests()
                g_dev['obs'].update()
            
            
            # if g_dev['rot']!=None:  
            #     rot_report=0
            #     while g_dev['rot'].rotator.IsMoving:                                                           
            #         #if g_dev['enc'].status['dome_slewing']: st += 'd>'
            #         if rot_report == 0:
            #             plog ("Waiting for Rotator to rotation")
            #             g_dev["obs"].send_to_user("Waiting for camera rotator to catch up before exposing.")
            #             rot_report =1
            #         time.sleep(0.2)
            #         g_dev['obs'].update()
                
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
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return

            else:

                result['FWHM'] = 3
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron

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
        #opt['fwhm_sim'] = 4.
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 4
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
       #time.sleep(10)#It is important to overshoot to overcome any backlash  WE need to be sure Exposure waits.
        plog('Autofocus Moving back in half-way.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!

        #time.sleep(10)#opt['fwhm_sim'] = 5
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 4.5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
            self.sequencer_hold = False   #Allow comand checks.
            self.af_guard = False
            g_dev["mnt"].last_ra = start_ra
            g_dev["mnt"].last_dec = start_dec
            g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)  #MAKE sure same style coordinates.
            wait_for_slew()
            self.sequencer_hold = False
            self.guard = False
            self.af_guard = False
            return
        elif spot1 < spot2 and spot1 < spot3:
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
                wait_for_slew()
                self.sequencer_hold = False
                self.guard = False
                self.af_guard = False
                return
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                g_dev['obs'].send_to_user('Moving to Solved focus:  ' +str(round(d1, 2)), p_level='INFO')
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
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
                g_dev["mnt"].last_ra = start_ra
                g_dev["mnt"].last_dec = start_dec
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                wait_for_slew()
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
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
            else:
                result['FWHM'] = 6
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
                focus_worked=True
            else:
                focus_worked=False            

                if extensive_focus == None:

                    plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                    plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                    g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus routine')
                    
                    req2 = {'target': 'near_tycho_star', 'area': 150, 'image_type': 'focus'}
                    opt = {'filter': 'focus'}
                    g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                    wait_for_slew()
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ' + str(extensive_focus))
                    
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)

                    self.sequencer_hold = False   #Allow comand checks.
                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                    wait_for_slew()
                    self.sequencer_hold = False
                    self.guard = False
                    self.af_guard = False
                    return
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
                
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
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
                g_dev["mnt"].last_ra = start_ra
                g_dev["mnt"].last_dec = start_dec
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                wait_for_slew()
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
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
            else:
                result['FWHM'] = 5.5
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                    wait_for_slew()
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus:', extensive_focus)
                    
                    self.sequencer_hold = False   #Allow comand checks.
                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                    wait_for_slew()
                    self.sequencer_hold = False
                    self.guard = False
                    self.af_guard = False
                    return


                # g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
                # time.sleep(5)
                # self.sequencer_hold = False   #Allow comand checks.
                # self.af_guard = False
                # g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                # wait_for_slew()
                # self.sequencer_hold = False
                # self.guard = False
                # self.af_guard = False
                # return
            if min(x) <= d1 <= max(x):
                plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
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
                    g_dev['obs'].scan_requests()
                    result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                        return
                else:
                    result['FWHM'] = new_spot
                    result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
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
                g_dev["mnt"].last_ra = start_ra
                g_dev["mnt"].last_dec = start_dec
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                wait_for_slew()
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
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                    wait_for_slew()
                    return
                else:
                    plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ', extensive_focus)
                    
                    self.sequencer_hold = False   #Allow comand checks.
                    self.af_guard = False
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["mnt"].last_ra = start_ra
                    g_dev["mnt"].last_dec = start_dec
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                    wait_for_slew()
                    self.sequencer_hold = False
                    self.guard = False
                    self.af_guard = False
                    return
            
            
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
        # elif spot2 <= spot1 or spot3 <= spot1:
        #     if spot2 <= spot3:
        #         min_focus = foc_pos2
        #     elif spot3 <= spot2:
        #         min_focus = foc_pos3
        #     else:
        #         min_focus = foc_pos0

        #     ##  HERE we could add a fourth or fifth try.  The parabola cannot really invert, nor should we ever be at a wild point after the first focus is
        #     ##  set up.
        #     #plog("It appears camera is too far out; try again with coarse_focus_script.")
        #     #self.coarse_focus_script(req2, opt2, throw=throw + 75, begin_at=min_focus)
        #     self.sequencer_hold = False
        #     self.guard = False
        #     self.af_guard = False
        #     return
        else:
            #plog('Spots are really wrong so moving back to starting focus:  ', focus_start)
            #g_dev['foc'].focuser.Move((focus_start)*g_dev['foc'].micron_to_steps)
            if extensive_focus == None:

                plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
                plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')
                
                req2 = {'target': 'near_tycho_star', 'area': 150}
                opt = {}
                g_dev['seq'].extensive_focus_script(req2,opt, no_auto_after_solve=True)
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["mnt"].last_ra = start_ra
                g_dev["mnt"].last_dec = start_dec
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
                wait_for_slew()
                return
            else:
                plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
                g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
                g_dev['obs'].send_to_user('V-curve focus failed, moving back to extensive focus: ', extensive_focus)
                
                self.sequencer_hold = False   #Allow comand checks.
                self.af_guard = False
                plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                g_dev["mnt"].last_ra = start_ra
                g_dev["mnt"].last_dec = start_dec
                g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #NB NB Does this really take us back to starting point?
                wait_for_slew()
                self.sequencer_hold = False
                self.guard = False
                self.af_guard = False
                return
        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["mnt"].last_ra = start_ra
        g_dev["mnt"].last_dec = start_dec
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        wait_for_slew()
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


    def extensive_focus_script(self, req, opt, throw=700, begin_at=None, no_auto_after_solve=False):
        '''
        This is an extensive focus that covers a wide berth of central values
        and throws.
        
        It first trys 6 throws inwards, 6 throws outwards
        
        then moves to the minimum focus found there
        
        and runs a normal focus
        
        '''
        
        
        
        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
                

            plog ("NOT DOING EXTENSIVE FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An extensive focus was rejected as it is during the daytime.")
            return
        
        
        plog('AF entered with:  ', req, opt)
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = True
        sim = False
        # Reset focus tracker
        if begin_at is None:  #  ADDED 20120821 WER
            foc_start = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        else:
            foc_start = begin_at  #In this case we start at a place close to a 3 point minimum.
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        start_ra = g_dev['mnt'].mount.RightAscension
        start_dec = g_dev['mnt'].mount.Declination
        plog("Saved ra, dec, focus:  ", start_ra, start_dec, foc_start)
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = ""
            
            #breakpoint()
            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            rot_report=0
            while g_dev['foc'].focuser.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'Waiting for Focuser to shift.\n'
                if g_dev['mnt'].mount.Slewing: st += 'Waiting for Mount to Slew\n'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if rot_report == 0:
                    plog(st)
                    st = ""
                    rot_report =1
                time.sleep(0.2)
                g_dev['obs'].update()
            
            
            # if g_dev['rot']!=None:  
            #     rot_report=0
            #     while g_dev['rot'].rotator.IsMoving:                                                           
            #         #if g_dev['enc'].status['dome_slewing']: st += 'd>'
            #         if rot_report == 0:
            #             plog ("Waiting for Rotator to rotation")
            #             rot_report =1
            #         time.sleep(0.2)
            #         g_dev['obs'].update()
                
        except:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            breakpoint()
        
        if req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters
            #  Go to closest Mag 7.5 Tycho * with no flip
            #focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
            #                        g_dev['mnt'].current_sidereal)
            #plog("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
            
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
            g_dev['mnt'].go_coord(focus_patch_ra, focus_patch_dec)            
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
            
            
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
            
            # If no auto_focus has been done, centre the focus field.
            if no_auto_after_solve == False:            
                g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')
                
                self.centering_exposure()
                
                g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')
            
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
            
            
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        foc_pos0 = foc_start
        result = {}
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')
        
        extensive_focus=[]
        for ctr in range(4):
            g_dev['foc'].guarded_move((foc_pos0 - (ctr+0)*throw)*g_dev['foc'].micron_to_steps)  #Added 20220209! A bit late
            #g_dev['foc'].guarded_move((foc_pos0 - (ctr+0)*throw))  #Added 20220209! A bit late
            #throw = 100  # NB again, from config.  Units are microns
            if not sim:
                g_dev['obs'].scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
            else:
                result['FWHM'] = 4
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot = result['FWHM']
                lsources = result['No_of_sources']
                if np.isnan(lsources):
                    spot=False
                
                #foc_pos = result['mean_focus']
                #foc_pos = (foc_pos0 - (ctr+0)*throw)*g_dev['foc'].micron_to_steps
                foc_pos = (foc_pos0 - (ctr+0)*throw)
                # if np.isnan(result['FWHM']):
                #     req = {'time': 2*float(self.config['focus_exposure_time']),  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                #     opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                #     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                #     if self.stop_script_called:
                #         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                #         return
                #     if not g_dev['obs'].open_and_enabled_to_observe:
                #         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                #         return
                #     spot = result['FWHM']
                #     if np.isnan(result['FWHM']) or np.isnan(lsources):
                #         spot = False
                #         foc_pos = False
                #         plog ("spot failed on extensive focus script")
                        
            except:
                spot = False
                foc_pos = False
                plog ("spot failed on extensive focus script")
                plog(traceback.format_exc())

            g_dev['obs'].send_to_user("Extensive focus center " + str(foc_pos) + " FWHM: " + str(spot), p_level='INFO')
            
            if spot != False:
                extensive_focus.append([foc_pos, spot, lsources])
                
            plog("Extensive focus so far (pos, fwhm, sources): "+ str(extensive_focus))
        
        for ctr in range(3):
            g_dev['foc'].guarded_move((foc_pos0 + (ctr+1)*throw)*g_dev['foc'].micron_to_steps)  #Added 20220209! A bit late
            #g_dev['foc'].guarded_move((foc_pos0 + (ctr+1)*throw))  #Added 20220209! A bit late
            #throw = 100  # NB again, from config.  Units are microns
            if not sim:
                g_dev['obs'].scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
            else:
                result['FWHM'] = 4
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot = result['FWHM']
                lsources = result['No_of_sources']
                if np.isnan(lsources):
                    spot=False
                #foc_pos = result['mean_focus']
                #foc_pos = (foc_pos0 + (ctr+1)*throw)*g_dev['foc'].micron_to_steps
                foc_pos = (foc_pos0 + (ctr+1)*throw)
                # if np.isnan(result['FWHM']):
                #     req = {'time': 3*float(self.config['focus_exposure_time']),  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                #     opt = {'area': 100, 'count': 1, 'filter': 'focus'}
                #     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
                #     if self.stop_script_called:
                #         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                #         return
                #     if not g_dev['obs'].open_and_enabled_to_observe:
                #         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                #         return
                #     spot = result['FWHM']
                #     if np.isnan(result['FWHM'])  or np.isnan(lsources):
                #         spot = False
                #         foc_pos = False
                #         plog ("spot failed on extensive focus script")
            except:
                spot = False
                foc_pos = False
                plog ("spot failed on extensive focus script")
                plog(traceback.format_exc())

            g_dev['obs'].send_to_user("Extensive focus center " + str(foc_pos) + " FWHM: " + str(spot), p_level='INFO')
            extensive_focus.append([foc_pos, spot, lsources])
            plog(extensive_focus)
        
        minimumFWHM = 100.0
        #breakpoint()
        # Find the maximum number of sources detected
        maxsources=max(np.asarray(extensive_focus)[:,2])
        
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
            if not no_auto_after_solve:
                self.auto_focus_script(None,None, skip_timer_check=True, extensive_focus=solved_pos) 
        except:
            plog ("Something went wrong in the extensive focus routine")
            plog(traceback.format_exc())
            plog ("Moving back to the starting focus")
            g_dev['obs'].send_to_user("Extensive focus attempt failed. Returning to initial focus.")
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
            
        
        try:
            #Check here for filter, guider, still moving  THIS IS A CLASSIC
            #case where a timeout is a smart idea.
            #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
            st = ""
            
            #breakpoint()
            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            rot_report=0
            while g_dev['foc'].focuser.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'Waiting for Focuser to shift.\n'
                if g_dev['mnt'].mount.Slewing: st += 'Waiting for Mount to Slew\n'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if rot_report == 0:
                    plog(st)
                    st = ""
                    rot_report =1
                time.sleep(0.2)
                g_dev['obs'].update()
            
            
            # if g_dev['rot']!=None:  
            #     rot_report=0
            #     while g_dev['rot'].rotator.IsMoving:                                                           
            #         #if g_dev['enc'].status['dome_slewing']: st += 'd>'
            #         if rot_report == 0:
            #             plog ("Waiting for Rotator to rotation")
            #             rot_report =1
            #         time.sleep(0.2)
            #         g_dev['obs'].update()
                
        except:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            breakpoint()
            
        
        
        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["mnt"].last_ra = start_ra
        g_dev["mnt"].last_dec = start_dec
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        wait_for_slew()
        #if sim:
        #    g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)
        #  NB here we could re-solve with the overlay spot just to verify solution is sane.
        #self.sequencer_hold = False   #Allow comand checks.
        #self.af_guard = False
        #  NB NB We may want to consider sending the result image patch to AWS
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = False
        
        
            
            
        

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
        
        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING COARSE FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A coarse focus was rejected as it is during the daytime.")
            return
        
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
            
            #breakpoint()
            #20210817  g_dev['enc'] does not exist,  so this faults. Cascade problem with user_id...
            rot_report=0
            while g_dev['foc'].focuser.IsMoving or \
                  g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if g_dev['foc'].focuser.IsMoving: st += 'Waiting for Focuser to shift.\n'
                if g_dev['mnt'].mount.Slewing: st += 'Waiting for Mount to Slew\n'
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if rot_report == 0:
                    plog(st)
                    st = ""
                    rot_report =1
                time.sleep(0.2)
                g_dev['obs'].update()
            
            
            if g_dev['rot']!=None:  
                rot_report=0
                while g_dev['rot'].rotator.IsMoving:                                                           
                    #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                    if rot_report == 0:
                        plog ("Waiting for Rotator to rotation")
                        rot_report =1
                    time.sleep(0.2)
                    g_dev['obs'].update()
                
        except:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            breakpoint()
        
        if True: #req['target'] == 'near_tycho_star':   ## 'bin', 'area'  Other parameters
            #  Go to closest Mag 7.5 Tycho * with no flip
            #focus_star = tycho.dist_sort_targets(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec, \
            #                        g_dev['mnt'].current_sidereal)
            #plog("Going to near focus star " + str(focus_star[0][0]) + "  degrees away.")
            
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
            g_dev['mnt'].go_coord(focus_patch_ra, focus_patch_dec)
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        else:
            pass   #Just take time image where currently pointed.
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'auto_focus'}   #  NB Should pick up filter and constats from config
            opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        foc_pos0 = foc_start
        result = {}
        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 0*throw)*g_dev['foc'].micron_to_steps)  #Added 20220209! A bit late
        #throw = 100  # NB again, from config.  Units are microns
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 4
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot1 = result['FWHM']
            foc_pos1 = result['mean_focus']
        except:
            spot1 = False
            foc_pos1 = False
            plog ("spot1 failed on coarse focus script")

        g_dev['obs'].send_to_user("Coarse focus center FWHM: " + str(spot1), p_level='INFO')


        plog('Autofocus Moving In -1x, second time.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot2 = result['FWHM']
            foc_pos2 = result['mean_focus']
        except:
            spot2 = False
            foc_pos2 = False
            plog ("spot2 failed on coarse focus script")
        g_dev['obs'].send_to_user("First Inward focus center FWHM: " + str(spot2), p_level='INFO')
        
        plog('Autofocus Moving In -2x, second time.\n\n')
        

        g_dev['foc'].guarded_move((foc_pos0 - 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 6
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot3 = result['FWHM']
            foc_pos3 = result['mean_focus']
        except:
            spot3 = False
            foc_pos3 = False
            plog ("spot3 failed on coarse focus script")
        g_dev['obs'].send_to_user("Second Inward focus center FWHM: " + str(spot3), p_level='INFO')
        #Need to check we are not going out too far!
        plog('Autofocus Moving out +3X.\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + 3*throw)*g_dev['foc'].micron_to_steps)
        plog('Autofocus back in for backlash to +2X\n\n')#It is important to overshoot to overcome any backlash
        g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 5
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 6.5
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot4 = result['FWHM']
            foc_pos4 = result['mean_focus']
        except:
            spot4 = False
            foc_pos4 = False
            plog ("spot4 failed on coarse focus script")
        
        g_dev['obs'].send_to_user("First Outward focus center FWHM: " + str(spot4), p_level='INFO')
            
        plog('Autofocus back in for backlash to +1X\n\n')

        g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)
        #opt['fwhm_sim'] = 4.
        if not sim:
            g_dev['obs'].scan_requests()
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                return
        else:
            result['FWHM'] = 5.75
            result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
        try:
            spot5 = result['FWHM']
            foc_pos5 = result['mean_focus']
        except:
            spot5 = False
            foc_pos5 = False
            plog ("spot5 failed on coarse focus script")
        
        g_dev['obs'].send_to_user("Second Outward focus center FWHM: " + str(spot2), p_level='INFO')
        
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
            plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
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
                g_dev['obs'].scan_requests()
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', solve_it=False)
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
                    return
            else:
                result['FWHM'] = new_spot
                result['mean_focus'] = g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
            try:
                spot6 = result['FWHM']
                foc_pos4 = result['mean_focus']
                plog('\n\n\nFound best focus position at:  ', foc_pos4,' measured FWHM is:  ',  round(spot6, 2), '\n\n\n')
                g_dev['obs'].send_to_user("Found best focus position at: " +str(foc_pos4) + ' measured FWHM is: ' + str(round(spot6, 2)), p_level='INFO')
            except:
                plog('Known bug, Verifcation did not work. Returing to target using solved focus.')
        else:
            plog('Coarse_focus did not converge. Moving back to starting focus:  ', foc_pos0)
            g_dev['obs'].send_to_user('Coarse_focus did not converge. Moving back to starting focus:  ' + str(foc_pos0), p_level='INFO')
            g_dev['obs'].send_to_user('Coarse focus failed, moving back to starting focus')
            
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
        g_dev["mnt"].last_ra = start_ra
        g_dev["mnt"].last_dec = start_dec
        g_dev['mnt'].mount.SlewToCoordinatesAsync(start_ra, start_dec)   #Return to pre-focus pointing.
        wait_for_slew()
        if sim:
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        self.sequencer_hold = False
        self.guard = False
        self.af_guard = False
        return result

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
        #plog('Completes contains:  ', seq_shelf['completed_blocks'])
        if check_block_id in seq_shelf['completed_blocks']:
            seq_shelf.close()
            #plog("Block ID in completed blocks:  ",  check_block_id)
            return True
        else:
            seq_shelf.close()
            return False


    def run_nightly_weather_report(self):
        
        g_dev['ocn'].status = g_dev['ocn'].get_status()
        g_dev['enc'].status = g_dev['enc'].get_status()
        ocn_status = g_dev['ocn'].status
        enc_status = g_dev['enc'].status
        events = g_dev['events']
        
        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        #if self.nightly_weather_report_complete==False:
        #    self.nightly_weather_report_complete=True
            # First thing to do at the Cool Down, Open time is to calculate the quality of the evening
            # using the broad weather report.

        plog("Appraising quality of evening from Open Weather Map.")
        owm = OWM('d5c3eae1b48bf7df3f240b8474af3ed0')
        mgr = owm.weather_manager() 
        try:
            #34.459375 -119.681172
            plog('Wx at:  ', self.config["latitude"], self.config["longitude"])
            one_call = mgr.one_call(lat=self.config["latitude"], lon=self.config["longitude"])
            ownsuccess=True
        except:
            plog ("call to OWM failed. Starting a retry schedule.")
            plog(traceback.format_exc())
            owncounter=0
            while owncounter <5:
                time.sleep(10)
                try:
                    one_call = mgr.one_call(lat=self.config["latitude"], lon=self.config["longitude"])
                    owncounter=6
                    ownsuccess=True
                except:                   
                    plog ("try "+ str(owncounter+1) + " for owm failed")
                    owncounter=owncounter+1
                    plog(traceback.format_exc())
                    ownsuccess=False
        
        if ownsuccess==False:
            plog("Failed to get a weather report. setting weather report safety to False")
            self.weather_report_is_acceptable_to_observe=False
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
            return
        
        # Collect relevant info for fitzgerald weather number calculation
        hourcounter=0
        fitzgerald_weather_number_grid=[]
        hours_until_end_of_observing= math.ceil((events['Observing Ends'] - ephem_now) * 24)
        plog("Hours until end of observing: " + str(hours_until_end_of_observing))
        
        
        for hourly_report in one_call.forecast_hourly:
            
            if hourcounter > hours_until_end_of_observing:
                pass
            else:
                fitzgerald_weather_number_grid.append([hourly_report.humidity,hourly_report.clouds,hourly_report.wind()['speed'], hourly_report.status, hourly_report.detailed_status])
                hourcounter=hourcounter + 1
        plog (fitzgerald_weather_number_grid)    
        
        
        # Fitzgerald weather number calculation.
        hourly_fitzgerald_number=[]
        for entry in fitzgerald_weather_number_grid:
            tempFn=0
            # Add humidity score up
            if 80 < entry[0] <= 85:
                tempFn=tempFn+1
            elif 85 < entry[0] <= 90:
                tempFn=tempFn+4
            elif 90 < entry[0] <= 100:
                tempFn=tempFn+40
            
            # Add cloud score up
            if 20 < entry[1] <= 40:
                tempFn=tempFn+1
            elif 40 < entry[1] <= 60:
                tempFn=tempFn+4
            elif 60 < entry[1] <= 80:
                tempFn=tempFn+40
            elif 80 < entry[1] <= 100:
                tempFn=tempFn+100
            
            # Add wind score up
            if 8 < entry[2] <=12:
                tempFn=tempFn+1
            elif 12 < entry[2] <= 15:
                tempFn=tempFn+4
            elif 15 < entry[2] <= 20:
                tempFn=tempFn+40
            elif 20 < entry[2] :
                tempFn=tempFn+100
            hourly_fitzgerald_number.append(tempFn)
            
        plog ("Hourly Fitzgerald number")
        plog (hourly_fitzgerald_number)
        plog ("Night's total fitzgerald number")
        plog (sum(hourly_fitzgerald_number))
        
        if hours_until_end_of_observing < 2:
            plog("Not enough hours left in the day to bother opening!")
            self.weather_report_is_acceptable_to_observe=False
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
        elif hourly_fitzgerald_number == []:
            plog("Looks like there isn't enough hours left in the night!")
            self.weather_report_is_acceptable_to_observe=False
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
        elif sum(hourly_fitzgerald_number) < 10:
            plog ("This is a good observing night!")
            self.weather_report_is_acceptable_to_observe=True
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
        elif sum(hourly_fitzgerald_number) > 1000:
            plog ("This is a horrible observing night!")
            self.weather_report_is_acceptable_to_observe=False
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
        elif sum(hourly_fitzgerald_number) < 100:
            plog ("This is perhaps not the best night, but we will give it a shot!")
            self.weather_report_is_acceptable_to_observe=True
            self.weather_report_wait_until_open=False
            self.weather_report_wait_until_open_time=ephem_now
            self.weather_report_close_during_evening=False
            self.weather_report_close_during_evening_time=ephem_now
        else:
            plog ("This is a problematic night, lets check if one part of the night is clearer than the other.")
            TEMPhourly_restofnight_fitzgerald_number=hourly_fitzgerald_number.copy()
            TEMPhourly_nightuptothen_fitzgerald_number=hourly_fitzgerald_number.copy()
            hourly_restofnight_fitzgerald_number=[]                
            
            for entry in range(len(TEMPhourly_restofnight_fitzgerald_number)):
                hourly_restofnight_fitzgerald_number.append(sum(TEMPhourly_restofnight_fitzgerald_number))
                TEMPhourly_restofnight_fitzgerald_number.pop(0)
            
            plog ("Hourly Fitzgerald Number for the Rest of the Night")
            plog (hourly_restofnight_fitzgerald_number)
            
            later_clearing_hour=99
            for q in range(len(hourly_restofnight_fitzgerald_number)):
                if hourly_restofnight_fitzgerald_number[q] < 100:
                    plog ("looks like it is clear for the rest of the night after hour " + str(q+1) )
                    later_clearing_hour=q+1
                    number_of_hours_left_after_later_clearing_hour= len(hourly_restofnight_fitzgerald_number) - q
                    break                  
            
            hourly_nightuptothen_fitzgerald_number=[]
            counter=0
            for entry in TEMPhourly_nightuptothen_fitzgerald_number:
                temp_value=0        
                for q in range(len(TEMPhourly_nightuptothen_fitzgerald_number)):
                    if q < counter:
                        temp_value = temp_value + TEMPhourly_nightuptothen_fitzgerald_number[q]
                counter=counter+1
                
                hourly_nightuptothen_fitzgerald_number.append(temp_value)
            
            plog ("Hourly Fitzgerald Number up until that point in the night")
            plog (hourly_nightuptothen_fitzgerald_number)
            
            clear_until_hour=99
            for q in range(len(hourly_nightuptothen_fitzgerald_number)):
                if hourly_nightuptothen_fitzgerald_number[q] < 100:
                    #plog ("looks like it is clear until hour " + str(q+1) )
                    clear_until_hour=q+1            
                        
            if clear_until_hour != 99:
                if clear_until_hour > 2:                        
                    plog ("looks like it is clear until hour " + str(clear_until_hour) )
                    plog ("Will observe until then then close down observatory")
                    self.weather_report_is_acceptable_to_observe=True
                    self.weather_report_close_during_evening=True
                    self.weather_report_close_during_evening_time=ephem_now + (clear_until_hour/24)
                    g_dev['events']['Observing Ends'] = ephem_now + (clear_until_hour/24)
                else:
                    plog ("looks like it is clear until hour " + str(clear_until_hour) )
                    plog ("But that isn't really long enough to rationalise opening the observatory")
                    self.weather_report_is_acceptable_to_observe=False
                    self.weather_report_close_during_evening=False
            
            if later_clearing_hour != 99:
                if number_of_hours_left_after_later_clearing_hour > 2:
                    plog ("looks like clears up at hour " + str(later_clearing_hour) )
                    plog ("Will attempt to open/re-open observatory then.")                    
                    self.weather_report_wait_until_open=True
                    self.weather_report_wait_until_open_time=ephem_now + (later_clearing_hour/24) 
                else:
                    plog ("looks like it clears up at hour " + str(later_clearing_hour) )
                    plog ("But there isn't much time after then, so not going to open then. ")
                    self.weather_report_wait_until_open=False
                    
            # if self.weather_report_close_during_evening==True or self.weather_report_wait_until_open==True:
            #     self.weather_report_is_acceptable_to_observe=True
            # else:
            #     self.weather_report_is_acceptable_to_observe=False
                
            if clear_until_hour==99 and later_clearing_hour ==99:
                plog ("It doesn't look like there is a clear enough patch to observe tonight")
                self.weather_report_is_acceptable_to_observe=False
                    
                
            
        
        
        
        

        # However, if the observatory is under manual control, leave this switch on.
        if g_dev['enc'].mode == 'Manual':
            self.weather_report_is_acceptable_to_observe=True
            
    def global_wx(self):
        '''
        THIS ROUTINE IS A COMPLETE HACK -- BEWARE.
 
        '''
        # g_dev['ocn'].status = g_dev['ocn'].get_status()
        # g_dev['enc'].status = g_dev['enc'].get_status()
        # ocn_status = g_dev['ocn'].status
        # enc_status = g_dev['enc'].status
        # events = g_dev['events']
        #breakpoint()
        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        if self.nightly_weather_report_complete==False:
            self.nightly_weather_report_complete=True
            # First thing to do at the Cool Down, Open time is to calculate the quality of the evening
            # using the broad weather report.
            #             site    >0m5 small
            lat_lons = [['mrc' , 1.75, 1,  34.459375, -119.681172], 
                        ['sqa' ,  1.0, 0,  34.691481, -120.042251], 
                        ['sro' ,    1, 1,  37.070365, -119.413107], 
                        ['udro',    1, 1,  37.737001, -113.691774], 
                        ['aro' ,    0, 3,  35.554307, -105.870189], 
                        ['elp' , 0.75, 1,  30.679280, -104.024396], 
                        ['roc' , 0.75, 1,  42.250616, -77.7850655], 
                        ['lsc' ,    1, 1, -30.167654, -70.804709 ], 
                        ['tfn' ,    1, 2,  28.302079, -16.5113277], 
                        ['cpt' ,    0, 2,  32.380561,  20.810137 ], 
                        ['tlv' ,    0, 1,  30.597529,  34.7623430], 
                        ['nsq' ,    1, 1,  32.354453,  80.0531263],
                        ['coj' ,    1, 2, -31.272856,  149.070813],
                        ['eco' ,    0, 2, -37.700976,  145.191672],
                        ['whs' ,    0, 1,  21.388383, -157.993459],
                        ['ogg' ,    1, 3,  20.707034, -156.257481],
                        ]
            plog("Appraising quality of evening from Open Weather Map.")
            owm = OWM('d5c3eae1b48bf7df3f240b8474af3ed0')
            mgr = owm.weather_manager()
            clear_hrs = 0
            cloudy_hrs = 0
            for site in lat_lons:            
                one_call = mgr.one_call(lat=site[2], lon=site[3])
                two_day = one_call.forecast_hourly

                print( '\n' + site[0], two_day, '\n' + site[0], '\n\n')
                for hourly_report in two_day:
                    if hourly_report.status in ['Clear']:
                        clear_hrs += 1
                        print("Bingo")
                    else:
                        cloudy_hrs += 1
            print('Clear Fraction:  ', clear_hrs*100/(clear_hrs + cloudy_hrs))        
            
            # # Collect relevant info for fitzgerald weather number calculation
            hourcounter=0
            # fitzgerald_weather_number_grid=[]
            # hours_until_end_of_observing= math.ceil((events['Observing Ends'] - ephem_now) * 24)
            # plog("Hours until end of observing: " + str(hours_until_end_of_observing))
            
            
            # for hourly_report in one_call.forecast_hourly:
                
            #     if hourcounter > hours_until_end_of_observing:
            #         pass
            #     else:
            #         fitzgerald_weather_number_grid.append([hourly_report.humidity,hourly_report.clouds,hourly_report.wind()['speed'],hourly_report.status, hourly_report.detailed_status])
            #         hourcounter=hourcounter + 1
            # plog (fitzgerald_weather_number_grid)    
            
            
            # Fitzgerald weather number calculation.
            hourly_fitzgerald_number=[]
            fitzgerald_weather_number_grid = 0  #Hack!!
            for entry in fitzgerald_weather_number_grid:
                tempFn=0
                # Add humidity score up
                if 80 < entry[0] <= 85:
                    tempFn=tempFn+1
                elif 85 < entry[0] <= 90:
                    tempFn=tempFn+4
                elif 90 < entry[0] <= 100:
                    tempFn=tempFn+40
                
                # Add cloud score up
                if 20 < entry[1] <= 40:
                    tempFn=tempFn+1
                elif 40 < entry[1] <= 60:
                    tempFn=tempFn+4
                elif 60 < entry[1] <= 80:
                    tempFn=tempFn+40
                elif 80 < entry[1] <= 100:
                    tempFn=tempFn+100
                
                # Add wind score up
                if 8 < entry[2] <=12:
                    tempFn=tempFn+1
                elif 12 < entry[2] <= 15:
                    tempFn=tempFn+4
                elif 15 < entry[2] <= 20:
                    tempFn=tempFn+40
                elif 15 < entry[2] :
                    tempFn=tempFn+100
                hourly_fitzgerald_number.append(tempFn)
                
            plog ("Hourly Fitzgerald number")
            plog (hourly_fitzgerald_number)
            plog ("Night's total fitzgerald number")
            plog (sum(hourly_fitzgerald_number))
            
            if sum(hourly_fitzgerald_number) < 10:
                plog ("This is a good observing night!")
                self.weather_report_is_acceptable_to_observe=True
                self.weather_report_wait_until_open=True
                self.weather_report_wait_until_open_time=ephem_now
                self.weather_report_close_during_evening=False
                self.weather_report_close_during_evening_time=ephem_now
            elif sum(hourly_fitzgerald_number) > 1000:
                plog ("This is a horrible observing night!")
                self.weather_report_is_acceptable_to_observe=False
                self.weather_report_wait_until_open=False
                self.weather_report_wait_until_open_time=ephem_now
                self.weather_report_close_during_evening=False
                self.weather_report_close_during_evening_time=ephem_now
            elif sum(hourly_fitzgerald_number) < 100:
                plog ("This is perhaps not the best night, but we will give it a shot!")
                self.weather_report_is_acceptable_to_observe=True
                self.weather_report_wait_until_open=True
                self.weather_report_wait_until_open_time=ephem_now
                self.weather_report_close_during_evening=False
                self.weather_report_close_during_evening_time=ephem_now
            else:
                plog ("This is a problematic night, lets check if one part of the night is clearer than the other.")
                TEMPhourly_restofnight_fitzgerald_number=hourly_fitzgerald_number.copy()
                TEMPhourly_nightuptothen_fitzgerald_number=hourly_fitzgerald_number.copy()
                hourly_restofnight_fitzgerald_number=[]                
                
                for entry in range(len(TEMPhourly_restofnight_fitzgerald_number)):
                    hourly_restofnight_fitzgerald_number.append(sum(TEMPhourly_restofnight_fitzgerald_number))
                    TEMPhourly_restofnight_fitzgerald_number.pop(0)
                
                plog ("Hourly Fitzgerald Number for the Rest of the Night")
                plog (hourly_restofnight_fitzgerald_number)
                
                later_clearing_hour=99
                for q in range(len(hourly_restofnight_fitzgerald_number)):
                    if hourly_restofnight_fitzgerald_number[q] < 100:
                        plog ("looks like it is clear for the rest of the night after hour " + str(q+1) )
                        later_clearing_hour=q+1
                        number_of_hours_left_after_later_clearing_hour= len(hourly_restofnight_fitzgerald_number) - q
                        break                  
                
                hourly_nightuptothen_fitzgerald_number=[]
                counter=0
                for entry in TEMPhourly_nightuptothen_fitzgerald_number:
                    temp_value=0        
                    for q in range(len(TEMPhourly_nightuptothen_fitzgerald_number)):
                        if q < counter:
                            temp_value = temp_value + TEMPhourly_nightuptothen_fitzgerald_number[q]
                    counter=counter+1
                    
                    hourly_nightuptothen_fitzgerald_number.append(temp_value)
                
                plog ("Hourly Fitzgerald Number up until that point in the night")
                plog (hourly_nightuptothen_fitzgerald_number)
                
                clear_until_hour=99
                for q in range(len(hourly_nightuptothen_fitzgerald_number)):
                    if hourly_nightuptothen_fitzgerald_number[q] < 100:
                        #plog ("looks like it is clear until hour " + str(q+1) )
                        clear_until_hour=q+1            
                            
                if clear_until_hour != 99:
                    if clear_until_hour > 2:                        
                        plog ("looks like it is clear until hour " + str(clear_until_hour) )
                        plog ("Will observe until then then close down observatory")
                        self.weather_report_is_acceptable_to_observe=True
                        self.weather_report_close_during_evening=True
                        self.weather_report_close_during_evening_time=ephem_now + (clear_until_hour/24)
                        g_dev['events']['Observing Ends'] = ephem_now + (clear_until_hour/24)
                    else:
                        plog ("looks like it is clear until hour " + str(clear_until_hour) )
                        plog ("But that isn't really long enough to rationalise opening the observatory")
                        self.weather_report_is_acceptable_to_observe=False
                        self.weather_report_close_during_evening=False
                
                if later_clearing_hour != 99:
                    if number_of_hours_left_after_later_clearing_hour > 2:
                        plog ("looks like clears up at hour " + str(later_clearing_hour) )
                        plog ("Will attempt to open/re-open observatory then.")                    
                        self.weather_report_wait_until_open=True
                        self.weather_report_wait_until_open_time=ephem_now + (later_clearing_hour/24) 
                    else:
                        plog ("looks like it clears up at hour " + str(later_clearing_hour) )
                        plog ("But there isn't much time after then, so not going to open then. ")
                        self.weather_report_wait_until_open=False
                        
                # if self.weather_report_close_during_evening==True or self.weather_report_wait_until_open==True:
                #     self.weather_report_is_acceptable_to_observe=True
                # else:
                #     self.weather_report_is_acceptable_to_observe=False
                    
                if clear_until_hour==99 and later_clearing_hour ==99:
                    plog ("It doesn't look like there is a clear enough patch to observe tonight")
                    self.weather_report_is_acceptable_to_observe=False
                    
                
            
        
        
        
        

        # However, if the observatory is under manual control, leave this switch on.
        if g_dev['enc'].mode == 'Manual':
            self.weather_report_is_acceptable_to_observe=True

    def centering_exposure(self):

        req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
        opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        
        
        
        # Make sure platesolve queue is clear
        reported=0
        while True:
            #if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
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
        
        # Nudge if needed.
        g_dev['obs'].check_platesolve_and_nudge()
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            return
        
        # Taking a confirming shot. 
        req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
        opt = {'area': 100, 'count': 1, 'filter': 'focus'}
        result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)
        
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")  
            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")  
            return
        
        return result


    def reset_completes(self):
        try:
            camera = self.config['camera']['camera_1_1']['name']
            seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) + str(g_dev['obs'].name))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            plog('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return
    
    
