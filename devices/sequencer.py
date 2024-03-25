import time
import datetime
from datetime import timedelta,timezone
from dateutil import tz
import copy
import json
from global_yard import g_dev
from astropy.coordinates import SkyCoord, AltAz, get_moon, Angle, get_body
from astropy import units as u
from astropy.time import Time
from astropy.io import fits
#from astropy.utils.data import get_pkg_data_filename
#from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans #convolve,
#kernel = Gaussian2DKernel(x_stddev=3,y_stddev=3)
from astropy.stats import sigma_clip
import ephem
import shelve
from multiprocessing.pool import Pool
import math
import shutil
import numpy as np
from numpy import inf
import os
import gc
import bottleneck as bn
#from pyowm import OWM
#from pyowm.utils import config
#from scipy import interpolate
import warnings
import matplotlib.pyplot as plt
import queue
import threading

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

# def interpolate_missing_pixels(
#         image: np.ndarray,
#         mask: np.ndarray,
#         method: str = 'nearest',
#         fill_value: int = 0
# ):
#     """
#     from: https://stackoverflow.com/questions/37662180/interpolate-missing-values-2d-python

#     :param image: a 2D image
#     :param mask: a 2D boolean image, True indicates missing values
#     :param method: interpolation method, one of
#         'nearest', 'linear', 'cubic'.
#     :param fill_value: which value to use for filling up data outside the
#         convex hull of known pixel values.
#         Default is 0, Has no effect for 'nearest'.
#     :return: the image with missing values interpolated
#     """


#     h, w = image.shape[:2]
#     xx, yy = np.meshgrid(np.arange(w), np.arange(h))

#     known_x = xx[~mask]
#     known_y = yy[~mask]
#     known_v = image[~mask]
#     missing_x = xx[mask]
#     missing_y = yy[mask]

#     interp_values = interpolate.griddata(
#         (known_x, known_y), known_v, (missing_x, missing_y),
#         method=method, fill_value=fill_value
#     )

#     # interp_values = interpolate.interpn(
#     #     (known_x, known_y), known_v, (missing_x, missing_y),
#     #     method=method, fill_value=fill_value
#     # )

#     interp_image = image.copy()
#     interp_image[missing_y, missing_x] = interp_values

#     return interp_image


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

        # Centering RA and Dec for a project
        self.block_ra=False
        self.block_dec=False

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

        # A flag to remove some platesolves during mosaicing e.g. at the end of smartstacks.
        self.currently_mosaicing = False

        # Load up focus and pointing catalogues -- note all are all-sky in scope.
        # slight differences. Focus has more clumped bright stars but pointing catalogue contains a larger range
        # of stars and has full sky coverage, wheras focus does not.
        # TPOINT catalog is on a more strict spiraled grid, about 102 stars and there is amag 7.5 star center of the field.
        self.focus_catalogue = np.genfromtxt('support_info/focusCatalogue.csv', delimiter=',')
# =============================================================================
        self.pointing_catalogue = np.genfromtxt('support_info/pointingCatalogueTpoint.csv', delimiter=',')
# =============================================================================


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
        self.project_call_timer = time.time() - 120

        self.rotator_has_been_homed_this_evening=False
        g_dev['obs'].request_update_calendar_blocks()
        #self.blocks=

        self.MTF_temporary_flat_timer=time.time()-310

        self.master_restack_queue = queue.Queue(maxsize=0)
        self.master_restack_thread = threading.Thread(target=self.master_restack, args=())
        self.master_restack_thread.daemon = True
        self.master_restack_thread.start()

    # Note this is a thread!
    def master_restack(self):
        """
        """

        one_at_a_time = 0
        while True:

            if (not self.master_restack_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.master_restack_queue.get(block=False)

                self.regenerate_local_masters()

                self.master_restack_queue.task_done()

                # EMPTY QUEUE SO THAT ONLY HAPPENS ONCE
                with self.master_restack_queue.mutex:
                    self.master_restack_queue.queue.clear()

                one_at_a_time = 0
                time.sleep(0.1)

            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(1)

    def wait_for_slew(self):
        """
        A function called when the code needs to wait for the telescope to stop slewing before undertaking a task.
        """
        try:
            if not g_dev['mnt'].rapid_park_indicator:
                movement_reporting_timer = time.time()
                while g_dev['mnt'].return_slewing():
                    #g_dev['mnt'].currently_slewing= True
                    if time.time() - movement_reporting_timer > g_dev['obs'].status_interval:
                        plog('m>')
                        movement_reporting_timer = time.time()
                        if not g_dev['obs'].currently_updating_status and g_dev['obs'].update_status_queue.empty():
                            g_dev['mnt'].get_mount_coordinates()
                            g_dev['obs'].request_update_status(mount_only=True)#, dont_wait=True)
                        #g_dev['obs'].update_status(mount_only=True, dont_wait=True)
                #g_dev['mnt'].currently_slewing= False
                # Then wait for slew_time to settle
                time.sleep(g_dev['mnt'].wait_after_slew_time)


        except Exception:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            if g_dev['mnt'].theskyx:
                self.kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)
            else:
                plog(traceback.format_exc())
                #
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
            req2 = {'target': 'near_tycho_star'}
            opt = {}
            self.extensive_focus_script(req2, opt, throw = g_dev['foc'].throw)
        elif action == "fixpointingscript":
            g_dev["obs"].send_to_user("Running a couple of auto-centering exposures.")
            self.centering_exposure()
        elif action == "autofocus": # this action is the front button on Camera, so FORCES an autofocus
            g_dev["obs"].send_to_user("Starting up the autofocus procedure.")
            g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow() - datetime.timedelta(
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
            self.master_restack_queue.put( 'g0', block=False)
            #self.regenerate_local_masters()
        elif action == "run" and script in ['pointingRun']:

            self.sky_grid_pointing_run(max_pointings=req['numPointingRuns'], alt_minimum=req['minAltitude'])
        elif action == "run" and script in ['equatorialSweep']:

            self.equatorial_pointing_run(max_pointings=req['points'], alt_minimum=req['minAltitude'])
        elif action == "run" and script in ("collectBiasesAndDarks"):
            self.bias_dark_script(req, opt, morn=True)
        # elif action == "run" and script == 'takeLRGBStack':
        #     self.take_lrgb_stack(req, opt)
        # elif action == "run" and script == "takeO3HaS2N2Stack":
        #     self.take_lrgb_stack(req, opt)
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
        elif action == "run" and script in [ 'estimateFocusOffset']:
            g_dev["obs"].send_to_user("Starting Filter Offset Run. Will take some time.")
            self.filter_focus_offset_estimator_script()
        else:
            plog('Sequencer command:  ', command, ' not recognized.')


    def park_and_close(self):
        try:
            if not g_dev['mnt'].rapid_park_indicator:   ###Test comment here
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

        #g_dev['seq'].blockend= None

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
                 self.nightly_reset_complete = True

        if ((g_dev['events']['Cool Down, Open'] <= ephem_now < g_dev['events']['Observing Ends'])):

            self.nightly_reset_complete = False

        # Don't attempt to start a sequence during an exposure OR when a function (usually TPOINT) has taken total control.
        if not self.total_sequencer_control and not g_dev['cam'].exposure_busy:
            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands
            # turned off.  So that if a sequencer script starts running, we don't get
            # an odd request out of nowhere that knocks it out
            g_dev['obs'].stop_processing_command_requests = True
            ###########################################################################

            # A little switch flip to make sure focus goes off when roof is simulated
            if  ephem_now < g_dev['events']['Clock & Auto Focus'] :
                self.night_focus_ready=True

            # This bit is really to get the scope up and running if the roof opens
            if ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends'])) \
                and not self.cool_down_latch and g_dev['obs'].open_and_enabled_to_observe \
                and not g_dev['obs'].scope_in_manual_mode and g_dev['mnt'].rapid_park_indicator \
                and ((time.time() - self.time_roof_last_opened) < 10) :

                self.nightly_reset_complete = False
                self.cool_down_latch = True
                self.reset_completes()

                if (g_dev['events']['Observing Begins'] < ephem_now < g_dev['events']['Observing Ends']):
                    # Move to reasonable spot
                    g_dev['mnt'].go_command(alt=70,az= 70)
                    g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow() - datetime.timedelta(
                        days=1
                    )  # Initialise last focus as yesterday
                    g_dev['foc'].set_initial_best_guess_for_focus()
                    g_dev['mnt'].set_tracking_on()
                    # Autofocus
                    req2 = {'target': 'near_tycho_star'}
                    opt = {}
                    plog ("Running initial autofocus upon opening observatory")

                    self.auto_focus_script(req2, opt)
                else:
                    self.night_focus_ready=True


                self.cool_down_latch = False


            # If in post-close and park era of the night, check those two things have happened!
            if (events['Close and Park'] <= ephem_now < events['End Morn Bias Dark']) and not g_dev['obs'].scope_in_manual_mode:

                if not g_dev['mnt'].rapid_park_indicator:
                    plog ("Found telescope unparked after Close and Park, parking the scope")
                    g_dev['mnt'].home_command()
                    g_dev['mnt'].park_command()


            if not self.bias_dark_latch and not g_dev['obs'].scope_in_manual_mode and ((events['Eve Bias Dark'] <= ephem_now < events['End Eve Bias Dark']) and \
                 self.config['auto_eve_bias_dark'] and not self.eve_bias_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations):   #events['End Eve Bias Dark']) and \

                self.bias_dark_latch = True   #Maybe long dark is a dark light leak check?
                req = {'numOfBias': 31, \
                       'numOfDark': 7, 'darkTime': 180, 'numOfDark2': 3, 'dark2Time': 540, \
                       'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  # NB NB All of the prior is obsolete
                opt = {}




                self.bias_dark_script(req, opt, morn=False,ending = g_dev['events']['End Eve Bias Dark'])
                self.eve_bias_done = True
                self.bias_dark_latch = False

            #print (self.MTF_temporary_flat_timer-time.time())

            if False and (time.time()-self.MTF_temporary_flat_timer > 300):
                self.MTF_temporary_flat_timer=time.time()
                plog ("EVESKY FLAG HUNTING")
                plog ("Roof open time: " + str(time.time() - g_dev['seq'].time_roof_last_opened))
                plog ("Sky flat latch: " + str(self.eve_sky_flat_latch))
                plog ("Scope in manual mode: " + str(g_dev['obs'].scope_in_manual_mode))
                plog ("Eve sky start: " + str(events['Eve Sky Flats']))
                plog ("Eve sky end: " + str(events['End Eve Sky Flats']))
                plog ("In between: " + str((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])))
                plog ("Open and enabled: " + str(g_dev['obs'].open_and_enabled_to_observe))
                plog ("Eve sky flats done: " + str(self.eve_flats_done))
                plog ("Camera cooled: " + str(g_dev['obs'].camera_sufficiently_cooled_for_calibrations))

            if (time.time() - g_dev['seq'].time_roof_last_opened > \
                   self.config['time_to_wait_after_roof_opens_to_take_flats'] ) and \
                   not self.eve_sky_flat_latch and not g_dev['obs'].scope_in_manual_mode and \
                   (events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
                   and self.config['auto_eve_sky_flat'] and g_dev['obs'].open_and_enabled_to_observe and\
                   not self.eve_flats_done \
                   and g_dev['obs'].camera_sufficiently_cooled_for_calibrations:

                self.eve_sky_flat_latch = True
                self.current_script = "Eve Sky Flat script starting"
                g_dev['obs'].send_to_user("Eve Sky Flat script starting")

                g_dev['foc'].set_initial_best_guess_for_focus()
                g_dev['mnt'].set_tracking_on()



                # Cycle through the flat script multiple times if new filters detected.
                # But only three times
                self.new_throughtputs_detected_in_flat_run=True
                flat_run_counter=0
                while self.new_throughtputs_detected_in_flat_run and flat_run_counter <3 and ephem_now < events['End Eve Sky Flats']:
                    self.new_throughtputs_detected_in_flat_run=False
                    flat_run_counter=flat_run_counter+1
                    self.sky_flat_script({}, {}, morn=False)   #Null command dictionaries


                g_dev['mnt'].set_tracking_on()

                self.eve_sky_flat_latch = False
                self.eve_flats_done = True
                g_dev['obs'].send_to_user("Eve Sky Flats gathered.")


            if ((g_dev['events']['Clock & Auto Focus']  <= ephem_now < g_dev['events']['Observing Begins'])) \
                    and self.night_focus_ready==True and not g_dev['obs'].scope_in_manual_mode and  g_dev['obs'].open_and_enabled_to_observe and not self.clock_focus_latch:

                self.nightly_reset_complete = False
                self.clock_focus_latch = True

                g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')


                g_dev['mnt'].go_command(alt=70,az= 70)
                g_dev['mnt'].set_tracking_on()

                # Super-duper double check that darkslide is open
                if g_dev['cam'].has_darkslide:
                    g_dev['cam'].openDarkslide()
                    # g_dev['cam'].darkslide_open = True
                    # g_dev['cam'].darkslide_state = 'Open'



                self.wait_for_slew()

                # Check it hasn't actually been homed this evening from the rotatorhome shelf
                homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                if 'lasthome' in homerotator_time_shelf:
                    if time.time() - homerotator_time_shelf['lasthome'] <  43200: # A home in the last twelve hours
                        self.rotator_has_been_homed_this_evening=True
                homerotator_time_shelf.close()
                if not self.rotator_has_been_homed_this_evening:
                    # Homing Rotator for the evening.
                    try:
                        while g_dev['rot'].rotator.IsMoving:
                            plog("home rotator wait")
                            time.sleep(1)
                        g_dev['obs'].send_to_user("Rotator being homed at beginning of night.", p_level='INFO')
                        time.sleep(0.5)
                        g_dev['rot'].home_command({},{})
                        while g_dev['rot'].rotator.IsMoving:
                            plog("home rotator wait")
                            time.sleep(1)
                        # Store last home time.
                        homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                        homerotator_time_shelf['lasthome'] = time.time()
                        homerotator_time_shelf.close()

                        g_dev['mnt'].go_command(alt=70,az= 70)
                        self.wait_for_slew()
                        while g_dev['rot'].rotator.IsMoving:
                            plog("home rotator wait")
                            time.sleep(1)
                        self.rotator_has_been_homed_this_evening=True
                        g_dev['obs'].rotator_has_been_checked_since_last_slew = True

                    except:
                        #plog ("no rotator to home or wait for.")
                        pass


                g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow() - datetime.timedelta(
                    days=1
                )  # Initialise last focus as yesterday

                g_dev['foc'].set_initial_best_guess_for_focus()

                # Autofocus
                req2 = {'target': 'near_tycho_star'}
                opt = {}
                self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)

                g_dev['obs'].send_to_user("End of Focus and Pointing Run. Waiting for Observing period to begin.", p_level='INFO')

                self.night_focus_ready=False
                self.clock_focus_latch = False

            if  (events['Observing Begins'] <= ephem_now \
                                       < events['Observing Ends']) and not self.block_guard and not g_dev["cam"].exposure_busy\
                                       and  (time.time() - self.project_call_timer > 10) and not g_dev['obs'].scope_in_manual_mode  and g_dev['obs'].open_and_enabled_to_observe and self.clock_focus_latch == False:

                try:
                    self.nightly_reset_complete = False
                    self.block_guard = True

                    if not self.reported_on_observing_period_beginning:
                        self.reported_on_observing_period_beginning=True
                        g_dev['obs'].send_to_user("Observing Period has begun.", p_level='INFO')

                    self.project_call_timer = time.time()

                    g_dev['obs'].request_update_calendar_blocks()

                    # only need to bother with the rest if there is more than 0 blocks.
                    self.block_guard=False
                    if not len(self.blocks) > 0:
                        self.block_guard=False
                        g_dev['seq'].blockend= None
                    else:
                        now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                        identified_block=None
                        #breakpoint()
                        for block in self.blocks:  #  This merges project spec into the blocks.
                                   #(block['start'] <= now_date_timeZ < block['end'])
                            if (block['start'] <= now_date_timeZ < block['end']) and not self.is_in_completes(block['event_id']):

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
                                    else:
                                        plog("Project response status code not 200")
                                        plog (str(project_response))
                                        plog (str(project_response.status_code))
                                        plog ("Project failed to be downloaded from Aws")
                                except:
                                    plog(traceback.format_exc())
                                    #

                        if identified_block == None:
                            self.block_guard = False   # Changed from True WER on 20221011@2:24 UTC
                            g_dev['seq'].blockend= None
                            pointing_good=False   # Do not try to execute an empty block.

                        elif identified_block['project_id'] in ['none', 'real_time_slot', 'real_time_block']:
                            self.block_guard = False   # Changed from True WER on 20221011@2:24 UTC
                            g_dev['seq'].blockend= None
                            pointing_good=False   # Do not try to execute an empty block.


                        elif identified_block['project'] == None:
                            plog (identified_block)
                            plog ("Skipping a block that contains an empty project")
                            self.block_guard=False
                            g_dev['seq'].blockend= None
                            pointing_good=False

                        elif identified_block['project'] != None:
                            pointing_good=True
                            # If a block is identified, check it is in the sky and not in a poor location
                            target=identified_block['project']['project_targets'][0]

                            ra = float(target['ra'])
                            dec = float(target['dec'])
                            temppointing=SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
                            temppointingaltaz=temppointing.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
                            alt = temppointingaltaz.alt.degree
                            # Check the moon isn't right in front of the project target
                            #moon_coords=get_moon(Time.now())
                            moon_coords=get_body("moon", time=Time.now())
                            moon_dist = moon_coords.separation(temppointing)
                            if moon_dist.degree <  self.config['closest_distance_to_the_moon']:
                                g_dev['obs'].send_to_user("Not running project as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                                plog("Not running project as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                                pointing_good=False
                            if alt < self.config['lowest_requestable_altitude']:
                                g_dev['obs'].send_to_user("Not running project as it is too low: " + str(alt) + " degrees.")
                                plog("Not running project as it is too low: " + str(alt) + " degrees.")
                                pointing_good=False

                        if pointing_good:
                            completed_block = self.execute_block(identified_block)  #In this we need to ultimately watch for weather holds.
                            #
                            try:
                                self.append_completes(completed_block['event_id'])
                            except:
                                plog ("block complete append didn't work")
                                plog(traceback.format_exc())
                            self.block_guard=False
                            self.currently_mosaicing = False
                            self.blockend = None
                        elif identified_block is None:
                            self.block_guard=False
                            self.currently_mosaicing = False
                            self.blockend = None
                        else:
                            plog ("Something didn't work, cancelling out of doing this project and putting it in the completes pile.")
                            self.append_completes(block['event_id'])
                            self.block_guard=False
                            self.currently_mosaicing = False
                            self.blockend = None


                except:
                    plog(traceback.format_exc())
                    plog("Hang up in sequencer.")
                    self.blockend = None
                    self.block_guard=False




            if (time.time() - g_dev['seq'].time_roof_last_opened > 1200 ) and not self.morn_sky_flat_latch and ((events['Morn Sky Flats'] <= ephem_now < events['End Morn Sky Flats']) and \
                   self.config['auto_morn_sky_flat'])  and not g_dev['obs'].scope_in_manual_mode and not self.morn_flats_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations and g_dev['obs'].open_and_enabled_to_observe:

                self.morn_sky_flat_latch = True

                self.current_script = "Morn Sky Flat script starting"


                # Cycle through the flat script multiple times if new filters detected.
                # But only three times
                self.new_throughtputs_detected_in_flat_run=True
                flat_run_counter=0
                while self.new_throughtputs_detected_in_flat_run and flat_run_counter <3 and ephem_now < events['End Morn Sky Flats']:
                    self.new_throughtputs_detected_in_flat_run=False
                    flat_run_counter=flat_run_counter+1
                    self.sky_flat_script({}, {}, morn=True)   #Null command dictionaries

                self.morn_sky_flat_latch = False
                self.morn_flats_done = True

            if not self.morn_bias_dark_latch and (events['Morn Bias Dark'] <= ephem_now < events['End Morn Bias Dark']) and \
                      self.config['auto_morn_bias_dark'] and not g_dev['obs'].scope_in_manual_mode and not  self.morn_bias_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations: # and g_dev['enc'].mode == 'Automatic' ):

                self.morn_bias_dark_latch = True
                req = {'numOfBias': 63, \
                        'numOfDark': 31, 'darkTime': 600, 'numOfDark2': 31, 'dark2Time': 600, \
                        'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  #This specificatin is obsolete
                opt = {}

                self.park_and_close()

                self.bias_dark_script(req, opt, morn=True, ending = g_dev['events']['End Morn Bias Dark'])

                self.park_and_close()
                self.morn_bias_dark_latch = False
                self.morn_bias_done = True


            if events['Sun Rise'] <= ephem_now and not self.end_of_night_token_sent:

                self.end_of_night_token_sent = True
                if self.config['ingest_raws_directly_to_archive']:
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
                                #moondata=get_moon(Time.now()).transform_to(currentaltazframe)
                                moondata=get_body("moon", time=Time.now()).transform_to(currentaltazframe)
                                if (moondata.alt.deg < -15):
                                    # If the moon is way below the horizon
                                    if g_dev['obs'].camera_sufficiently_cooled_for_calibrations:
                                        if self.nightime_bias_counter < self.config['camera']['camera_1_1']['settings']['number_of_bias_to_collect']:
                                            plog ("It is dark and the moon isn't up! Lets do a bias!")
                                            g_dev['mnt'].park_command({}, {})
                                            plog("Exposing 1x1 bias frame.")
                                            req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                                            opt = { 'count': 1,  \
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
                                            broadband_ss_biasdark_exp_time = self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
                                            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']

                                            # plog("Exposing 1x1 dark exposure:  " + str(dark_exp_time) )
                                            # req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                                            # opt = { 'count': 1,  \
                                            #         'filter': 'dark'}
                                            # self.nightime_dark_counter = self.nightime_dark_counter + 1
                                            # g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                            #                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                                            stride=1
                                            min_to_do=1
                                            # COLLECTING A TWO SECOND EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 2s exposure dark frames.")
                                            req = {'time': 2,  'script': 'True', 'image_type': 'twosec_exposure_dark'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                print (self.stop_script_called)
                                                print (g_dev['obs'].open_and_enabled_to_observe)
                                                print ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark']))
                                                return


                                            # COLLECTING A FIVE SECOND EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 5s exposure dark frames.")
                                            req = {'time': 5,  'script': 'True', 'image_type': 'fivesec_exposure_dark'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A TEN SECOND EXPOSURE DARK FRAME
                                            plog("Expose " + str(2*stride) +" 1x1 ten second exposure dark frames.")
                                            req = {'time': 10,  'script': 'True', 'image_type': 'tensec_exposure_dark'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A FIFTEEN SECOND EXPOSURE DARK FRAME
                                            plog("Expose " + str(2*stride) +" 1x1 15 second exposure dark frames.")
                                            req = {'time': 15,  'script': 'True', 'image_type': 'fifteensec_exposure_dark'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return


                                            # COLLECTING A TWENTY SECOND EXPOSURE DARK FRAME
                                            plog("Expose " + str(2*stride) +" 1x1 20 second exposure dark frames.")
                                            req = {'time': 20,  'script': 'True', 'image_type': 'twentysec_exposure_dark'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A BROADBAND SMARTSTACK BIASDARK FRAME
                                            plog("Expose " + str(stride) +" 1x1 broadband smstack biasdark frames.")
                                            req = {'time': broadband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'broadband_ss_biasdark'}
                                            opt = {'count': 2*min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A NARROWBAND SMARTSTACK BIASDARK FRAME
                                            plog("Expose " + str(stride) +" 1x1 narrowband smstack biasdark frames.")
                                            req = {'time': narrowband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'narrowband_ss_biasdark'}
                                            opt = {'count': 2*min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A 0.0045 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.0045 second exposure dark frames.")
                                            req = {'time': 0.0045,  'script': 'True', 'image_type': 'pointzerozerofourfive_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A 0.015 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.015 second exposure dark frames.")
                                            req = {'time': 0.015,  'script': 'True', 'image_type': 'onepointfivepercent_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A 0.05 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.05 second exposure dark frames.")
                                            req = {'time': 0.05,  'script': 'True', 'image_type': 'fivepercent_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A 0.1 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.1 second exposure dark frames.")
                                            req = {'time': 0.1,  'script': 'True', 'image_type': 'tenpercent_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return


                                            # COLLECTING A 0.25 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.25 second exposure dark frames.")
                                            req = {'time': 0.25,  'script': 'True', 'image_type': 'quartersec_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A Half Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 half-second exposure dark frames.")
                                            req = {'time': 0.5,  'script': 'True', 'image_type': 'halfsec_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A 0.75 Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1 0.75 second exposure dark frames.")
                                            req = {'time': 0.75,  'script': 'True', 'image_type': 'threequartersec_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A one Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1  1 second exposure dark frames.")
                                            req = {'time': 1,  'script': 'True', 'image_type': 'onesec_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A one and a half Second EXPOSURE DARK FRAME
                                            plog("Expose " + str(5*stride) +" 1x1  1.5 second exposure dark frames.")
                                            req = {'time': 1.5,  'script': 'True', 'image_type': 'oneandahalfsec_exposure_dark'}
                                            opt = {'count':  min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return

                                            # COLLECTING A BIAS FRAME
                                            # COLLECT BIAS FRAMES LATER as there is no way to know whether bias frames are affected
                                            # by slowly-closing shutters... whereas darks can be rejected.
                                            plog("Expose " + str(stride) +" 1x1 bias frames.")
                                            req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                                            opt = {'count': min_to_do,  \
                                                   'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                            do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            g_dev['obs'].request_scan_requests()
                                            if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
                                                return


                                            plog("Expose 1x1 dark of " \
                                                 + str(1) + " using exposure:  " + str(dark_exp_time) )
                                            req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                                            opt = {'count': 1, 'filter': 'dark'}
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                               do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)



                                            # these exposures shouldn't reset these timers
                                            g_dev['obs'].time_of_last_exposure = time.time() - 840
                                            g_dev['obs'].time_of_last_slew = time.time() - 840

            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands turned back on
            # So that we can process any new manual commands that come in.
            g_dev['obs'].stop_processing_command_requests = False
            g_dev['obs'].request_scan_requests()
            ###########################################################################


        return


    def reset_completes(self):

        """
        The sequencer keeps track of completed projects, but in certain situations,
        you want to flush that list (e.g. roof shut then opened again).
        """

        try:
            camera = self.config['camera']['camera_1_1']['name']
            seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) + '_completes_' + str(g_dev['obs'].name))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            plog('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return
    def append_completes(self, block_id):
        #
        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) +'_completes_' + str(g_dev['obs'].name))
        #plog("block_id:  ", block_id)
        lcl_list = seq_shelf['completed_blocks']
        if block_id in lcl_list:
            plog('Duplicate storage of block_id in pended completes blocked.')
            seq_shelf.close()
            return False
        lcl_list.append(block_id)   #NB NB an in-line append did not work!
        seq_shelf['completed_blocks']= lcl_list
        plog('Appended completes contains:  ', seq_shelf['completed_blocks'])
        seq_shelf.close()
        return True

    def is_in_completes(self, block_id):

        camera = self.config['camera']['camera_1_1']['name']
        seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) + '_completes_' + str(g_dev['obs'].name))
        if block_id in seq_shelf['completed_blocks']:
            seq_shelf.close()
            return True
        else:
            seq_shelf.close()
            return False


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
            return block_specification     #Added wer 20231103

        #g_dev["obs"].request_full_update()

        plog('|n|n Starting a new project!  \n')
        plog(block_specification, ' \n\n\n')

        calendar_event_id=block_specification['event_id']

        #breakpoint()
        # NB we assume the dome is open and already slaving.
        block = copy.deepcopy(block_specification)

        #g_dev['mnt'].unpark_command({}, {})
        #plog("unparked")


        # this variable is what we check to see if the calendar
        # event still exists on AWS. If not, we assume it has been
        # deleted or modified substantially.
        calendar_event_id = block_specification['event_id']

        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            try:
                #g_dev["obs"].request_full_update()
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
                self.blockend = None
                continue

            #try:
            #    g_dev['mnt'].get_mount_coordinates()
            #except:
            #    pass

            # Store this ra as the "block" ra for centering purposes
            self.block_ra=copy.deepcopy(dest_ra)
            self.block_dec=copy.deepcopy(dest_dec)

            g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
            g_dev['mnt'].set_tracking_on()
            plog("tracking on")

            # Check it hasn't actually been homed this evening from the rotatorhome shelf
            homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
            if 'lasthome' in homerotator_time_shelf:
                if time.time() - homerotator_time_shelf['lasthome'] <  43200: # A home in the last twelve hours
                    self.rotator_has_been_homed_this_evening=True
            homerotator_time_shelf.close()
            if not self.rotator_has_been_homed_this_evening:
                plog ("rotator hasn't been homed this evening, doing that now")
                # Homing Rotator for the evening.
                try:
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    g_dev['obs'].send_to_user("Rotator being homed as this has not been done this evening.", p_level='INFO')
                    time.sleep(0.5)
                    g_dev['rot'].home_command({},{})
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    # Store last home time.
                    homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                    homerotator_time_shelf['lasthome'] = time.time()
                    homerotator_time_shelf.close()

                    g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
                    self.wait_for_slew()
                    while g_dev['rot'].rotator.IsMoving:
                        plog("home rotator wait")
                        time.sleep(1)
                    self.rotator_has_been_homed_this_evening=True
                    g_dev['obs'].rotator_has_been_checked_since_last_slew = True

                except:
                    #plog ("no rotator to home or wait for.")
                    pass


            # Undertake a focus if necessary before starting observing the target
            if g_dev["foc"].last_focus_fwhm == None or g_dev["foc"].focus_needed == True:

                g_dev['obs'].send_to_user("Running an initial autofocus run.")

                req2 = {'target': 'near_tycho_star'}

                self.auto_focus_script(req2, {}, throw = g_dev['foc'].throw)
                g_dev["foc"].focus_needed = False



            # This actually replaces the "requested" dest_ra by the actual centered pointing ra and dec.
            #dest_ra = g_dev['mnt'].mount.RightAscension   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
            #dest_dec = g_dev['mnt'].mount.Declination



            #g_dev["obs"].request_full_update()

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

            for exposure in block['project']['exposures']:

                exposure['longstack'] = do_long_stack
                exposure['smartstack'] = do_smart_stack
                left_to_do += int(exposure['count'])

            plog("Left to do initial value:  ", left_to_do)
            req = {'target': 'near_tycho_star'}

            # Do first pointing exposure for all images
            # mosaics or not
            ################################
            # Get the pointing / central position of the
            g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)
            # Quick pointing check and re_seek at the start of each project block
            # Otherwise everyone will get slightly off-pointing images
            # Necessary
            plog ("Taking a quick pointing check and re_seek for new project block")
            result = self.centering_exposure(no_confirmation=True, try_hard=True, try_forever=True, calendar_event_id=calendar_event_id)
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            # Don't do a second repointing in the first pane of a mosaic
            # considering we just did that.
            mosaic_pointing_already_done=True

            while left_to_do > 0 and not ended:

                #cycle through exposures decrementing counts    MAY want to double check left-to do but do not remultiply by 4
                for exposure in block['project']['exposures']:

                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    g_dev['obs'].request_scan_requests()
                    foundcalendar=False
                    g_dev['obs'].request_update_calendar_blocks()
                    for tempblock in self.blocks:
                        if tempblock['event_id'] == calendar_event_id :
                            foundcalendar=True
                            g_dev['seq'].blockend=tempblock['end']
                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            if g_dev['seq'].blockend != None:
                                if now_date_timeZ >= g_dev['seq'].blockend :
                                    plog ("Block ended.")
                                    g_dev["obs"].send_to_user("Calendar Block Ended. Stopping project run.")
                                    left_to_do=0
                                    self.blockend = None
                                    return block_specification
                    if not foundcalendar:
                        plog ("could not find calendar entry, cancelling out of block.")
                        g_dev["obs"].send_to_user("Calendar block removed. Stopping project run.")
                        self.blockend = None
                        return block_specification

                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of exposure loop in seq:blk execute')

                        #left_to_do =0
                        self.blockend = None
                        return block_specification

                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Obs not longer open and enabled to observe. Cancelling out.")
                        self.blockend = None
                        return block_specification



                    plog ("Observing " + str(block['project']['project_targets'][0]['name']))

                    plog("Executing: ", exposure, left_to_do)
                    try:
                        filter_requested = exposure['filter']
                    except:
                        filter_requested = 'None'
                    exp_time =  float(exposure['exposure'])
                    count = int(exposure['count'])
                    #  We should add a frame repeat count
                    imtype = exposure['imtype']

                    #if count <= 0:
                    #     continue


                    # MUCH safer to calculate these from first principles
                    # Than rely on an owner getting this right!
                    dec_field_deg = (g_dev['cam'].pixscale * g_dev['cam'].imagesize_x) /3600
                    ra_field_deg = (g_dev['cam'].pixscale * g_dev['cam'].imagesize_y) /3600
                    self.currently_mosaicing = False

                    # A hack to get older projects working. should be deleted at some point.
                    try:
                        if exposure['area'] is not None:
                            exposure['zoom']=exposure['area']
                            plog("*****Line 1067 in Seq says key 'area' supplied:  ",exposure['area'] )
                            exposure.pop('area')
                    except:
                        pass

                    zoom_factor = exposure['zoom'].lower()
                    #plog("*****Zoom supplied line 1074 seq is:  ", zoom_factor)
                    #breakpoint()
                    if exposure['zoom'].lower() in ["full", 'Full'] or 'X' in exposure['zoom'] \
                        or  '%' in exposure['zoom'] or ( exposure['zoom'].lower() == 'small sq.') \
                        or (exposure['zoom'].lower() == 'small sq'):    # and dec_field_deg == ra_field_deg):

                        # These are not mosaic exposures
                        offset = [(0., 0.)] #Zero(no) mosaic offset
                        pane = 0
                        self.currently_mosaicing = False
                    else:
                        self.currently_mosaicing = True

                        if exposure['zoom'].lower() == 'mosaic deg.':
                            requested_mosaic_length_ra = float(exposure['width'])
                            requested_mosaic_length_dec = float(exposure['height'])
                        elif exposure['zoom'].lower() == 'mosaic arcmin.':
                            requested_mosaic_length_ra = float(exposure['width']) /60
                            requested_mosaic_length_dec = float(exposure['height']) /60
                        elif exposure['zoom'].lower() == 'big sq.':
                            if dec_field_deg > ra_field_deg:
                                requested_mosaic_length_ra = dec_field_deg
                                requested_mosaic_length_dec = dec_field_deg
                            else:
                                requested_mosaic_length_ra = ra_field_deg
                                requested_mosaic_length_dec = ra_field_deg

                        print ("ra field: " + str(ra_field_deg))
                        print ("dec field: " + str(dec_field_deg))

                        # Ok here we take the provided (eventually) mosaic lengths
                        # And assume a 10% overlap -- maybe an option in future but
                        # lets just set it as that for now.
                        # Then calculate the central coordinate offsets.
                        mosaic_length_fields_ra = requested_mosaic_length_ra / ra_field_deg
                        mosaic_length_fields_dec = requested_mosaic_length_dec / dec_field_deg
                        if mosaic_length_fields_ra % 1 > 0.8:
                            mosaic_length_fields_ra += 1
                        if mosaic_length_fields_dec % 1 > 0.8:
                            mosaic_length_fields_dec += 1
                        mosaic_length_fields_ra = np.ceil(mosaic_length_fields_ra)
                        mosaic_length_fields_dec = np.ceil(mosaic_length_fields_dec)

                        # Ok, so now we get the offset in degrees from the centre
                        # For the given number of frames. The frames should by
                        # definition already overlap.
                        ra_offsets=[]
                        ra_step=requested_mosaic_length_ra / (2 * mosaic_length_fields_ra)
                        for fieldnumber in range(int(mosaic_length_fields_ra)):
                            # offset is field spot minus the central spot
                            ra_offsets.append( (ra_step * ((fieldnumber*2)+1)) - (mosaic_length_fields_ra * ra_step) )
                        dec_offsets=[]
                        dec_step=requested_mosaic_length_dec / (2 * mosaic_length_fields_dec)
                        for fieldnumber in range(int(mosaic_length_fields_dec)):
                            dec_offsets.append((dec_step * ((fieldnumber*2)+1)) - (mosaic_length_fields_dec * dec_step)    )


                        # To get the overlap, we need to reduce the offsets by 10%
                        # I THINK this is the way to do it, but I dunno....
                        offset = []
                        for offsetra in range(len(ra_offsets)):
                            for offsetdec in range(len(dec_offsets)):
                                offset.append((ra_offsets[offsetra] * 0.9 ,dec_offsets[offsetdec] * 0.9))

                        plog ("Mosaic grid calculated")
                        plog ("Number of frames in RA: " + str(mosaic_length_fields_ra))
                        plog ("Number of frames in DEC: " + str(mosaic_length_fields_dec))
                        plog ("offset positions:  " + str(offset))

                        pane = 0



                    # Longstacks need to be defined out here for mosaicing purposes.
                    if exposure['longstack'] == False:
                        longstackswitch='no'
                        longstackname='no'
                    elif exposure['longstack'] == True:
                        longstackswitch='yes'
                        longstackname=block_specification['project']['created_at'].replace('-','').replace(':','')
                    else:
                        longstackswitch='no'
                        longstackname='no'



                    if mosaic_pointing_already_done:
                        mosaic_pointing_already_done = False
                    elif self.currently_mosaicing or g_dev['obs'].platesolve_errors_in_a_row > 4:
                        # Get the pointing / central position of the
                        g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)

                        # Quick pointing check and re_seek at the start of each project block
                        # Otherwise everyone will get slightly off-pointing images
                        # Necessary
                        plog ("Taking a quick pointing check and re_seek for new mosaic block")
                        result = self.centering_exposure(no_confirmation=True, try_hard=True, try_forever=True, calendar_event_id=calendar_event_id)
                        self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
                        self.mosaic_center_dec=g_dev['mnt'].return_declination()


                    if result == 'blockend':
                        plog ("End of Block, exiting project block.")
                        self.blockend = None
                        self.currently_mosaicing = False
                        return block_specification

                    if result == 'calendarend':
                        plog ("Calendar Item containing block removed from calendar")
                        plog ("Site bailing out of running project")
                        self.blockend = None
                        self.currently_mosaicing = False
                        return block_specification


                    if result == 'roofshut':
                        plog ("Roof Shut, Site bailing out of Project")
                        self.blockend = None
                        self.currently_mosaicing = False
                        return block_specification

                    if result == 'outsideofnighttime':
                        plog ("Outside of Night Time. Site bailing out of Project")
                        self.blockend = None
                        self.currently_mosaicing = False
                        return block_specification

                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of Project')
                        self.blockend = None
                        self.currently_mosaicing = False
                        return block_specification




                    for displacement in offset:

                        if self.currently_mosaicing:

                            plog ("Moving to new position of mosaic")
                            plog (displacement)
                            self.current_mosaic_displacement_ra= displacement[0]/15
                            self.current_mosaic_displacement_dec= displacement[1]
                            # Slew to new mosaic pane location.
                            new_ra = self.mosaic_center_ra + self.current_mosaic_displacement_ra
                            new_dec= self.mosaic_center_dec + self.current_mosaic_displacement_dec
                            new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)
                            #g_dev['mnt'].go_command(ra=new_ra, dec=new_dec)
                            try:
                                self.wait_for_slew()
                                g_dev['obs'].time_of_last_slew=time.time()
                                try:
                                    g_dev['mnt'].slew_async_directly(ra=new_ra, dec=new_dec)
                                    #g_dev['mnt'].mount.SlewToCoordinatesAsync(new_ra, new_dec)
                                except:
                                    plog(traceback.format_exc())
                                    if g_dev['mnt'].theskyx:
                                        self.kill_and_reboot_theskyx(new_ra, new_dec)
                                    else:
                                        plog(traceback.format_exc())
                                        #
                                self.wait_for_slew()
                            except Exception as e:
                                plog (traceback.format_exc())
                                if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                    plog("The SkyX had an error.")
                                    plog("Usually this is because of a broken connection.")
                                    plog("Killing then waiting 60 seconds then reconnecting")
                                    g_dev['seq'].kill_and_reboot_theskyx(new_ra,new_dec)


                            self.wait_for_slew()


                            if result == 'blockend':
                                plog ("End of Block, exiting project block.")
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if result == 'calendarend':
                                plog ("Calendar Item containing block removed from calendar")
                                plog ("Site bailing out of running project")
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification
                            if result == 'roofshut':
                                plog ("Roof Shut, Site bailing out of Project")
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if result == 'outsideofnighttime':
                                plog ("Outside of Night Time. Site bailing out of Project")
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if g_dev["obs"].stop_all_activity:
                                plog('stop_all_activity cancelling out of Project')
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                        if imtype in ['light']:

                            # Sort out Longstack and Smartstack names and switches

                            if exposure['smartstack'] == False:
                                smartstackswitch='no'
                            elif exposure['smartstack'] == True:
                                smartstackswitch='yes'
                            else:
                                smartstackswitch='no'

                            # Set up options for exposure and take exposure.
                            req = {'time': exp_time,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': imtype, 'smartstack' : smartstackswitch, 'longstackswitch' : longstackswitch, 'longstackname' : longstackname, 'block_end' : g_dev['seq'].blockend}   #  NB Should pick up filter and constants from config
                            opt = {'count': 1, 'filter': filter_requested, \
                                   'hint': block['project_id'] + "##" + dest_name, 'object_name': block['project']['project_targets'][0]['name'], 'pane': pane, 'zoom': zoom_factor}
                            plog('Seq Blk sent to camera:  ', req, opt)

                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            if g_dev['seq'].blockend != None:
                                if now_date_timeZ >= g_dev['seq'].blockend :
                                    left_to_do=0
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return
                            #g_dev["obs"].request_full_update()
                            #plog("*****Line 1304 Seg. Right before call expose:  req, opt:  ", req, opt)
                            result = g_dev['cam'].expose_command(req, opt, user_name=user_name, user_id=user_id, user_roles=user_roles, no_AWS=False, solve_it=False, calendar_event_id=calendar_event_id) #, zoom_factor=zoom_factor)
                            #g_dev["obs"].request_full_update()
                            try:
                                if result == 'blockend':
                                    plog ("End of Block, exiting project block.")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return block_specification

                                if result == 'calendarend':
                                    plog ("Calendar Item containing block removed from calendar")
                                    plog ("Site bailing out of running project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return block_specification

                                if result == 'roofshut':
                                    plog ("Roof Shut, Site bailing out of Project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return block_specification

                                if result == 'outsideofnighttime':
                                    plog ("Outside of Night Time. Site bailing out of Project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return block_specification

                                if g_dev["obs"].stop_all_activity:
                                    plog('stop_all_activity cancelling out of Project')
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    return block_specification

                            except:
                                pass




                            # Check that the observing time hasn't completed or then night has not completed.
                            # If so, set ended to True so that it cancels out of the exposure block.
                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            events = g_dev['events']
                            blockended=False
                            if g_dev['seq'].blockend != None:
                                blockended = now_date_timeZ >= g_dev['seq'].blockend
                            ended = left_to_do <= 0 or blockended \
                                    or ephem.now() >= events['Observing Ends']
                            #print ('gdev seq blockend: ' + str(g_dev['seq'].blockend))
                            if ephem.now() >= events['Observing Ends']:
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            #if now_date_timeZ >= g_dev['seq'].blockend:
                            #    return block_specification

                            if result == 'blockend':
                                #left_to_do=0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification


                            if blockended:
                                #left_to_do=0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification


                            if result == 'calendarend':
                                #left_to_do =0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if result == 'roofshut':
                                #left_to_do =0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if result == 'outsideofnighttime':
                                #left_to_do =0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification

                            if g_dev["obs"].stop_all_activity:
                                plog('stop_all_activity cancelling out of exposure loop')
                                #left_to_do =0
                                self.blockend = None
                                self.currently_mosaicing = False
                                return block_specification



                        pane += 1

                #count -= 1
                #exposure['count'] = count
                left_to_do -= 1
                plog("Left to do:  ", left_to_do)

        self.currently_mosaicing = False
        plog("Project block has finished!")
        self.blockend = None
        return block_specification


    def bias_dark_script(self, req=None, opt=None, morn=False, ending=None):
        """
        This functions runs through automatically collecting bias and darks for the local calibrations.
        """
        self.current_script = 'Bias Dark'
        # if morn:
        #     ending = g_dev['events']['End Morn Bias Dark']
        # else:
        #     ending = g_dev['events']['End Eve Bias Dark']

        # Set a timer. It is possible to ask for bias darks and it takes until the end of time. So we should put a limit on it for manually
        # requested collection. Auto-collection is limited by the events schedule.
        bias_darks_started=time.time()

        #breakpoint()

        ending = ephem.now() + 100000000000000000000000
            # g_dev['cam'].darkslide_open = False
            # g_dev['cam'].darkslide_state = 'Closed'

        while ephem.now() < ending :   #Do not overrun the window end

            if g_dev['cam'].has_darkslide:
                g_dev['cam'].closeDarkslide()

            if ending != None:
                if ephem.now() > ending:
                    self.bias_dark_latch = False
                    break


            # If we've been collecting bias darks for TWO HOURS, bail out... someone has asked for too many!
            if time.time() - bias_darks_started > 7200:
                self.bias_dark_latch = False
                break

            bias_count = self.config['camera']['camera_1_1']['settings']['number_of_bias_to_collect']
            dark_count = self.config['camera']['camera_1_1']['settings']['number_of_dark_to_collect']
            dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']
            cycle_time = self.config['camera']['camera_1_1']['settings']['cycle_time']

            # For 95% of our exposures we can collect biasdarks... so we don't have to
            # scale the darks with a master bias for our most common exposures
            # Non-scaled darks with the bias still contained IS better,
            # Just uncommon for observatories where there is all sorts of different exposure times.
            # But for PTR, we have some very frequent used exposure times, so this is a worthwhile endeavour.
            broadband_ss_biasdark_exp_time = self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']

            # Before parking, set the darkslide to close
            if g_dev['cam'].has_darkslide:
                if g_dev['cam'].darkslide_state != 'Closed':
                    if g_dev['cam'].darkslide_type=='COM':
                        g_dev['cam'].darkslide_instance.closeDarkslide()
                    elif g_dev['cam'].darkslide_type=='ASCOM_FLI_SHUTTER':
                        g_dev['cam'].camera.Action('SetShutter', 'close')

                    g_dev['cam'].darkslide_open = False
                    g_dev['cam'].darkslide_state = 'Closed'
            # Before parking, set the dark filter
            if g_dev["fil"].null_filterwheel == False:
                self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command({"filter": 'dark'}, {})

            g_dev['mnt'].park_command({}, {}) # Get there early

            # # Wait a significant fraction of time for darkslides, filters, scopes to settle
            # plog ("Waiting a few minutes for everything to settle down before taking bias and darks.")
            # plog ("To avoid light leaks from slow systems (e.g. darkslides, filter wheels etc.).")
            # dark_wait_time=time.time()
            # while (time.time() - dark_wait_time < 180):
            #     if self.stop_script_called:
            #         g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
            #         self.bias_dark_latch = False
            #         return
            #     if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
            #         self.bias_dark_latch = False
            #         break
            #     g_dev['obs'].request_scan_requests()
            #     time.sleep(5)


            if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:   #ephem is units of a day
                self.bias_dark_latch = False
                break     #Terminate Bias dark phase if within taking a dark woudl run over.



            b_d_to_do = dark_count
            try:
                stride = bias_count//dark_count
                plog("Tobor will interleave a long exposure dark every  " + str(stride) + "  biasdarks, short darks and biases.")
                single_dark = True
            except:
                stride = bias_count   #Just do all of the biases first.
                single_dark = False


            while b_d_to_do > 0:
                g_dev['obs'].request_scan_requests()
                min_to_do = 1
                b_d_to_do -= 1

                # COLLECTING A TWO SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 2s exposure dark frames.")
                req = {'time': 2,  'script': 'True', 'image_type': 'twosec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A THREEPOINTFIVE SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 3.5s exposure dark frames.")
                req = {'time': 3.5,  'script': 'True', 'image_type': 'threepointfivesec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A FIVE SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 5s exposure dark frames.")
                req = {'time': 5,  'script': 'True', 'image_type': 'fivesec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A SEVENPOINTFIVE SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 7.5s exposure dark frames.")
                req = {'time': 7.5,  'script': 'True', 'image_type': 'sevenpointfivesec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A TEN SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(2*stride) +" 1x1 ten second exposure dark frames.")
                req = {'time': 10,  'script': 'True', 'image_type': 'tensec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A FIFTEEN SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(2*stride) +" 1x1 15 second exposure dark frames.")
                req = {'time': 15,  'script': 'True', 'image_type': 'fifteensec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A TWENTY SECOND EXPOSURE DARK FRAME
                plog("Expose " + str(2*stride) +" 1x1 20 second exposure dark frames.")
                req = {'time': 20,  'script': 'True', 'image_type': 'twentysec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A BROADBAND SMARTSTACK BIASDARK FRAME
                plog("Expose " + str(stride) +" 1x1 broadband smstack biasdark frames.")
                req = {'time': broadband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'broadband_ss_biasdark'}
                opt = {'count': 2*min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A NARROWBAND SMARTSTACK BIASDARK FRAME
                plog("Expose " + str(stride) +" 1x1 narrowband smstack biasdark frames.")
                req = {'time': narrowband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'narrowband_ss_biasdark'}
                opt = {'count': 2*min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # If we've been collecting bias darks for TWO HOURS, bail out... someone has asked for too many!
                if time.time() - bias_darks_started > 7200:
                    self.bias_dark_latch = False
                    break

                # COLLECTING A 0.0045 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.0045 second exposure dark frames.")
                req = {'time': 0.0045,  'script': 'True', 'image_type': 'pointzerozerofourfive_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A 0.015 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.015 second exposure dark frames.")
                req = {'time': 0.015,  'script': 'True', 'image_type': 'onepointfivepercent_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A 0.05 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.05 second exposure dark frames.")
                req = {'time': 0.05,  'script': 'True', 'image_type': 'fivepercent_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A 0.1 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.1 second exposure dark frames.")
                req = {'time': 0.1,  'script': 'True', 'image_type': 'tenpercent_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A 0.25 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.25 second exposure dark frames.")
                req = {'time': 0.25,  'script': 'True', 'image_type': 'quartersec_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()



                # COLLECTING A Half Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 half-second exposure dark frames.")
                req = {'time': 0.5,  'script': 'True', 'image_type': 'halfsec_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A 0.75 Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1 0.75 second exposure dark frames.")
                req = {'time': 0.75,  'script': 'True', 'image_type': 'threequartersec_exposure_dark'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)



                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()



                # COLLECTING A one Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1  1 second exposure dark frames.")
                req = {'time': 1,  'script': 'True', 'image_type': 'onesec_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                # COLLECTING A one and a half Second EXPOSURE DARK FRAME
                plog("Expose " + str(5*stride) +" 1x1  1.5 second exposure dark frames.")
                req = {'time': 1.5,  'script': 'True', 'image_type': 'oneandahalfsec_exposure_dark'}
                opt = {'count':  min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()


                # COLLECTING A BIAS FRAME
                # COLLECT BIAS FRAMES LATER as there is no way to know whether bias frames are affected
                # by slowly-closing shutters... whereas darks can be rejected.
                plog("Expose " + str(stride) +" 1x1 bias frames.")
                req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                opt = {'count': min_to_do,  \
                       'filter': 'dark'}

                # Check it is in the park position and not pointing at the sky.
                # It can be pointing at the sky if cool down open is triggered during the biasdark process
                g_dev['mnt'].park_command({}, {})
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()

                if not single_dark:

                    plog("Expose 1x1 dark of " \
                         + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
                    opt = {'count': 1, 'filter': 'dark'}
                    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                       do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                        self.bias_dark_latch = False
                        return
                    #b_d_to_do -= 1
                    #g_dev["obs"].request_full_update()
                    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                        self.bias_dark_latch = False
                        break
                else:
                    plog("Expose 1x1 dark " + str(1) + " of " \
                             + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
                    req = {'time': dark_exp_time,  'script': 'True', 'image_type': 'dark'}
                    opt = {'count': 1, 'filter': 'dark'}
                    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                        do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                        self.bias_dark_latch = False
                        return
                    #b_d_to_do -= 1
                    #g_dev["obs"].request_full_update()
                    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                        self.bias_dark_latch = False
                        break

                g_dev['obs'].request_scan_requests()
                #g_dev["obs"].request_full_update()
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

        if g_dev['cam'].has_darkslide:
            g_dev['cam'].closeDarkslide()
            # g_dev['cam'].darkslide_open = False
            # g_dev['cam'].darkslide_state = 'Closed'

        self.reported_on_observing_period_beginning=False

        self.rotator_has_been_homed_this_evening=False

        # self.eve_flats_done = False
        # self.morn_flats_done = False
        # self.morn_bias_done = False
        # self.eve_bias_done = False

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
        if g_dev['obs'].config['ingest_raws_directly_to_archive']:

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

        # # If you are using TheSkyX, then update the autosave path
        # if self.config['camera']['camera_1_1']['driver'] == "CCDSoft2XAdaptor.ccdsoft5Camera":
        #     g_dev['cam'].camera.AutoSavePath = g_dev['obs'].obsid_path +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d')
        #     try:
        #         os.mkdir(g_dev['obs'].obsid_path +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d'))
        #     except:
        #         plog ("Couldn't make autosave directory")

        # Resetting complete projects
        plog ("Nightly reset of complete projects")
        self.reset_completes()
        g_dev['obs'].events_new = None
        g_dev['obs'].reset_last_reference()
        if self.config['mount']['mount1']['permissive_mount_reset'] == 'yes':
           g_dev['mnt'].reset_mount_reference()
        g_dev['obs'].last_solve_time = datetime.datetime.utcnow() - datetime.timedelta(days=1)
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

        self.eve_sky_flat_latch = False
        self.morn_sky_flat_latch = False
        self.morn_bias_dark_latch = False
        self.clock_focus_latch = False
        self.cool_down_latch = False
        self.clock_focus_latch = False

        self.flats_being_collected = False

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
        g_dev["foc"].time_of_last_focus = datetime.datetime.utcnow() - datetime.timedelta(
            days=1
        )  # Initialise last focus as yesterday
        g_dev["foc"].images_since_last_focus = (
            10000  # Set images since last focus as sillyvalue
        )
        g_dev["foc"].last_focus_fwhm = None
        g_dev["foc"].focus_tracker = [np.nan] * 1000


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

        #self.regenerate_local_masters()
        self.master_restack_queue.put( 'g0', block=False)

        # Daily reboot of necessary windows 32 programs *Cough* Theskyx *Cough*
        if g_dev['mnt'].theskyx: # It is only the mount that is the reason theskyx needs to reset
            plog ("Got here")
            self.kill_and_reboot_theskyx(-1,-1)
            plog ("But didn't get here")

        return

    def kill_and_reboot_theskyx(self, returnra, returndec): # Return to a given ra and dec or send -1,-1 to remain at park
        g_dev['mnt'].mount_update_paused=True
        #g_dev['mnt'].wait_for_mount_update()

        # if g_dev['cam'].theskyx:
        #     g_dev['cam'].updates_paused=True

        #time.sleep(10)
        print ("Paused at kill theskyx for bugtesting")
       #breakpoint()


        if g_dev['cam'].theskyx:
            g_dev['cam'].updates_paused=True
            g_dev["cam"].exposure_busy=True

        os.system("taskkill /IM TheSkyX.exe /F")
        os.system("taskkill /IM TheSky64.exe /F")
        time.sleep(5)
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
                    #g_dev['cam'].updates_paused=True
                    #time.sleep(3*g_dev['cam'].camera_update_period)
                    Camera(self.config['camera']['camera_1_1']['driver'],
                                    g_dev['cam'].name,
                                    self.config)
                    time.sleep(5)
                    g_dev['cam'].camera_update_reboot=True
                    time.sleep(5)
                    g_dev['cam'].updates_paused=False
                    g_dev["cam"].exposure_busy=False



                if self.config['filter_wheel']['filter_wheel1']['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                    FilterWheel('CCDSoft2XAdaptor.ccdsoft5Camera',
                                         g_dev['obs'].name,
                                         self.config)

                    time.sleep(5)

                if self.config['focuser']['focuser1']['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                    Focuser('CCDSoft2XAdaptor.ccdsoft5Camera',
                                         g_dev['obs'].name,  self.config)
                    time.sleep(5)



                time.sleep(5)
                retries=6
            except:
                retries=retries+1
                time.sleep(60)
                if retries ==4:
                    plog(traceback.format_exc())
                    #

        g_dev['mnt'].mount_update_reboot=True
        g_dev['mnt'].wait_for_mount_update()
        g_dev['mnt'].mount_update_paused=False

        if returnra == -1 or returndec == -1:
            g_dev['mnt'].park_command({}, {})
            #pass
        else:
            g_dev['mnt'].park_command({}, {})
            g_dev['mnt'].go_command(ra=returnra, dec=returndec)

        return


    def make_scaled_dark(self,input_folder, filename_start, masterBias, shapeImage, archiveDate, pipefolder):



            # CLEAR OUT OLD TEMPFILES
            darkdeleteList=(glob(input_folder +'/*tempbiasdark.n*'))
            for file in darkdeleteList:
                try:
                    os.remove(file)
                except:
                    plog ("Couldnt remove old dark file: " + str(file))

            calibration_timer=time.time()

            # NOW we have the master bias, we can move onto the dark frames
            inputList=(glob( input_folder +'/*.n*'))

            # Test each flat file actually opens
            for file in inputList:
                try:
                    np.load(file, mmap_mode='r')
                except:
                    plog ("corrupt dark skipped: " + str(file))
                    inputList.remove(file)

            # # Array to hold loaded images
            # PLDrive = np.empty((shapeImage[0],shapeImage[1],len(inputList)), dtype=np.float32)

            # # D  frames and stick them in the memmap
            # i=0
            # for file in inputList:
            #     hdu1exp=float(file.split('_')[-2])
            #     #darkdeexp=(np.load(file)-masterBias)/hdu1exp
            #     PLDrive[:,:,i] = np.asarray((np.load(file)-masterBias)/hdu1exp,dtype=np.float32)
            #     #del darkdeexp
            #     i=i+1

            # # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
            # finalImage=np.zeros(shapeImage,dtype=float)


            # # MULTIPROCESSED VERSION
            # mptask=[]
            # counter=0
            # for goog in range(shapeImage[0]):
            #     mptask.append(PLDrive[counter,:,:])
            #     counter=counter+1

            # counter=0
            # with Pool(os.cpu_count()) as pool:
            #     for result in pool.map(stack_nanmedian_row, mptask):
            #         finalImage[counter,:]=result
            #         #lst[counter] = result
            #         counter=counter+1


            # create an empty array to hold each chunk
            # the size of this array will determine the amount of RAM usage

            finalImage=np.zeros(shapeImage,dtype=float)

            # Store the biases in the memmap file
            PLDrive= [None] * len(inputList)
            exposures= [None] * len(inputList)
            i=0
            for file in inputList:
                #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                PLDrive[i] = np.load(file, mmap_mode='r')
                try:
                    exposures[i]=float(file.split('_')[-2])
                except:
                    plog(traceback.format_exc())
                    breakpoint()

                i=i+1

            # Get a chunk size that evenly divides the array
            chunk_size=8
            while not ( shapeImage[0] % chunk_size ==0):
                chunk_size=chunk_size+1
                #print (chunk_size)
            chunk_size=int(shapeImage[0]/chunk_size)

            holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

            # iterate through the input, replace with ones, and write to output
            for i in range(shapeImage[0]):
                if i % chunk_size == 0:
                    #print (i)
                    counter=0
                    for imagefile in range(len(PLDrive)):
                        #breakpoint() holder[counter][0:chunk_size,:] = copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)
                        holder[counter][0:chunk_size,:] = (copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)-copy.deepcopy(masterBias[i:i+chunk_size,:]).astype(np.float32))/exposures[counter]
                        counter=counter+1

                    finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)

                    # Wipe and restore files in the memmap file
                    # To clear RAM usage
                    PLDrive= [None] * len(inputList)
                    i=0
                    for file in inputList:
                        #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                        PLDrive[i] = np.load(file, mmap_mode='r')
                        i=i+1



            masterDark=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
            del finalImage


            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            try:
                #fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)

                # Save and upload master bias
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), None, g_dev['obs'].calib_masters_folder, tempfrontcalib + filename_start+'_master_bin1.fits' ))

                 # Store a version of the bias for the archive too
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), None, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits' ))


                # fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias, overwrite=True)

                # filepathaws=g_dev['obs'].calib_masters_folder
                # filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits'
                # g_dev['obs'].enqueue_for_calibrationUI(80, filepathaws,filenameaws)


                if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                    #fits.writeto(pipefolder + '/' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #fits.writeto(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #np.save(pipefolder + '/'+tempfrontcalib + 'BIAS_master_bin1.npy', masterBias)
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + filename_start+'_master_bin1.npy',copy.deepcopy(masterDark)))

            except Exception as e:
                plog ("Could not save dark frame: ",e)


            plog (filename_start+ " Exposure Dark reconstructed: " +str(time.time()-calibration_timer))

            g_dev["obs"].send_to_user(filename_start+ " Exposure Dark calibration frame created.")

            return masterDark

    def make_bias_dark(self,input_folder, filename_start, masterBias, shapeImage, archiveDate, pipefolder):


            # CLEAR OUT OLD TEMPFILES
            darkdeleteList=(glob(input_folder +'/*tempbiasdark.n*'))
            for file in darkdeleteList:
                try:
                    os.remove(file)
                except:
                    plog ("Couldnt remove old dark file: " + str(file))

            calibration_timer=time.time()



            # NOW we have the master bias, we can move onto the dark frames
            inputList=(glob( input_folder +'/*.n*'))

            # Test each flat file actually opens
            for file in inputList:
                try:
                    np.load(file, mmap_mode='r')
                except:
                    plog ("corrupt dark skipped: " + str(file))
                    inputList.remove(file)




            # # Array to hold loaded images
            # PLDrive = np.empty((shapeImage[0],shapeImage[1],len(inputList)), dtype=np.float32)

            # # D  frames and stick them in the memmap
            # i=0
            # for file in inputList:
            #     hdu1exp=float(file.split('_')[-2])
            #     #darkdeexp=(np.load(file)-masterBias)/hdu1exp
            #     PLDrive[:,:,i] = np.asarray((np.load(file))/hdu1exp,dtype=np.float32)
            #     #del darkdeexp
            #     i=i+1

            # # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
            # finalImage=np.zeros(shapeImage,dtype=float)


            # # MULTIPROCESSED VERSION
            # mptask=[]
            # counter=0
            # for goog in range(shapeImage[0]):
            #     mptask.append(PLDrive[counter,:,:])
            #     counter=counter+1

            # counter=0
            # with Pool(os.cpu_count()) as pool:
            #     for result in pool.map(stack_nanmedian_row, mptask):
            #         finalImage[counter,:]=result
            #         #lst[counter] = result
            #         counter=counter+1



            # create an empty array to hold each chunk
            # the size of this array will determine the amount of RAM usage

            finalImage=np.zeros(shapeImage,dtype=float)

            # Store the biases in the memmap file
            PLDrive= [None] * len(inputList)
            exposures= [None] * len(inputList)
            i=0
            for file in inputList:
                #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                PLDrive[i] = np.load(file, mmap_mode='r')
                exposures[i]=float(file.split('_')[-2])
                i=i+1

            # Get a chunk size that evenly divides the array
            chunk_size=8
            while not ( shapeImage[0] % chunk_size ==0):
                chunk_size=chunk_size+1
                #print (chunk_size)
            chunk_size=int(shapeImage[0]/chunk_size)

            holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

            # iterate through the input, replace with ones, and write to output
            for i in range(shapeImage[0]):
                if i % chunk_size == 0:
                    #print (i)
                    counter=0
                    for imagefile in range(len(PLDrive)):
                        holder[counter][0:chunk_size,:] = copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)
                        counter=counter+1



                    finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)

                    # Wipe and restore files in the memmap file
                    # To clear RAM usage
                    PLDrive= [None] * len(inputList)
                    i=0
                    for file in inputList:
                        #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                        PLDrive[i] = np.load(file, mmap_mode='r')
                        i=i+1



            masterDark=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
            del finalImage


            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            try:
                #fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)

                # Save and upload master bias
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), None, g_dev['obs'].calib_masters_folder, tempfrontcalib +filename_start+'_master_bin1.fits' ))

                 # Store a version of the bias for the archive too
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), None, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits' ))


                # fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias, overwrite=True)

                # filepathaws=g_dev['obs'].calib_masters_folder
                # filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits'
                # g_dev['obs'].enqueue_for_calibrationUI(80, filepathaws,filenameaws)


                if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                    #fits.writeto(pipefolder + '/' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #fits.writeto(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #np.save(pipefolder + '/'+tempfrontcalib + 'BIAS_master_bin1.npy', masterBias)
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + filename_start+'_master_bin1.npy',copy.deepcopy(masterDark)))

            except Exception as e:
                plog ("Could not save dark frame: ",e)


            plog (filename_start+ " Exposure Dark reconstructed: " +str(time.time()-calibration_timer))

            g_dev["obs"].send_to_user(filename_start+ " Exposure Dark calibration frame created.")

            return masterDark



    def regenerate_local_masters(self):


        #self.total_sequencer_control = True


        plog ("killing local problem programs")


        try:
            os.system("taskkill /IM FitsLiberator.exe /F")
            os.system("taskkill /IM Mira_Pro_x64_8.exe /F")
            os.system("taskkill /IM Aladin.exe /F")
        except:
            pass
        g_dev["obs"].send_to_user("Currently regenerating local masters.")

        if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
            pipefolder = g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias
            if not os.path.exists(g_dev['obs'].config['pipe_archive_folder_path']+'/calibrations'):
                os.makedirs(g_dev['obs'].config['pipe_archive_folder_path'] + '/calibrations')

            if not os.path.exists(g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias):
                os.makedirs(g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias)
        else:
            pipefolder=''




        # # Remove the current master calibrations
        # # Not doing this can leave old faulty calibrations
        # # in the directory.
        # tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'DARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'DARK_master_bin1.fits'))


        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'halfsecondDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'halfsecondDARK_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + '2secondDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + '2secondDARK_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + '10secondDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + '10secondDARK_master_bin1.fits'))



        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'broadbandssDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'broadbandssDARK_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'broadbandssBIASDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'broadbandssBIASDARK_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'narrowbandssDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'narrowbandssDARK_master_bin1.fits'))

        # try:
        #     os.remove(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'narrowbandssBIASDARK_master_bin1.fits')
        # except:
        #     plog ("Could not remove " + str(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'narrowbandssBIASDARK_master_bin1.fits'))



        # tempfrontcalib=g_dev['obs'].calib_masters_folder + g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_masterFlat*'
        # deletelist=glob(tempfrontcalib)
        # for item in deletelist:
        #     try:
        #         os.remove(item)
        #     except:
        #         plog ("Could not remove " + str(item))

        # tempfrontcalib=g_dev['obs'].calib_masters_folder +'masterFlat*'

        # deletelist=glob(tempfrontcalib)
        # for item in deletelist:
        #     try:
        #         os.remove(item)
        #     except:
        #         plog ("Could not remove " + str(item))


        # also masterflat*.npy





        # NOW to get to the business of constructing the local calibrations
        # Start with biases
        # Get list of biases
        #plog (datetime.datetime.now().strftime("%H:%M:%S"))
        plog ("Regenerating bias")
        calibration_timer=time.time()

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
        # try:
        #     del g_dev['cam'].flatFiles
        # except:
        #     pass

        if len(inputList) == 0 or len(darkinputList) == 0 or len(inputList) == 1 or len(darkinputList) == 1:
            plog ("Not reprocessing local masters as there are not enough biases or darks")
        else:
            # Clear held bias and darks and flats to save memory and garbage collect.
            #del g_dev['cam'].biasFiles
            #del g_dev['cam'].darkFiles
            #g_dev['cam'].biasFiles = {}
            #g_dev['cam'].darkFiles = {}
            #g_dev['cam'].flatFiles = {}
            #g_dev['cam'].hotFiles = {}
            #gc.collect()


            #flat_biasdarks={}

            # Get the size of the camera
            hdutest=np.load(inputList[0], mmap_mode='r')
            shapeImage=hdutest.shape
            del hdutest

            # Make an array for the bad pixel map
            bad_pixel_mapper_array=np.full((shapeImage[0],shapeImage[1]), False)

            # Array to hold loaded images
            #PLDrive = np.empty((shapeImage[0],shapeImage[1],len(inputList)), dtype=np.float32)

            # Store the biases in the memmap file
            PLDrive= [None] * len(inputList)
            i=0
            for file in inputList:
                #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                PLDrive[i] = np.load(file, mmap_mode='r')
                i=i+1

            #breakpoint()

            #PLDrive_holder = copy.deepcopy(PLDrive)

            # finalImage array
            finalImage=np.zeros(shapeImage, dtype=np.float32)



            try:

                # create an empty array to hold each chunk
                # the size of this array will determine the amount of RAM usage

                # Get a chunk size that evenly divides the array
                chunk_size=8
                while not ( shapeImage[0] % chunk_size ==0):
                    chunk_size=chunk_size+1
                    #print (chunk_size)
                chunk_size=int(shapeImage[0]/chunk_size)

                holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                # iterate through the input, replace with ones, and write to output
                for i in range(shapeImage[0]):
                    if i % chunk_size == 0:
                        #print (i)
                        counter=0
                        for imagefile in range(len(PLDrive)):
                            holder[counter][0:chunk_size,:] = copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)
                            counter=counter+1

                        finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)


                        # # Clear out memory
                        # del holder
                        # holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                        # Wipe and restore files in the memmap file
                        # To clear RAM usage
                        PLDrive= [None] * len(inputList)
                        i=0
                        for file in inputList:
                            #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                            PLDrive[i] = np.load(file, mmap_mode='r')
                            i=i+1

                        #PLDrive=copy.deepcopy(PLDrive_holder)



            except:
                plog(traceback.format_exc())
                breakpoint()

            #plog ("Bias reconstructed: " +str(time.time()-calibration_timer))

            #breakpoint()
            # counter=0
            # with Pool(os.cpu_count()) as pool:
            #     for result in pool.map(stack_nanmedian_row, mptask):
            #         finalImage[counter,:]=result
            #         #lst[counter] = result
            #         counter=counter+1

            # # MULTIPROCESSED VERSION
            # mptask=[]
            # counter=0
            # for goog in range(shapeImage[0]):
            #     #mptask.append(PLDrive[counter,:,:])
            #     counter=counter+1

            # counter=0
            # with Pool(os.cpu_count()) as pool:
            #     for result in pool.map(stack_nanmedian_row, mptask):
            #         finalImage[counter,:]=result
            #         #lst[counter] = result
            #         counter=counter+1

            masterBias=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
            del finalImage
            del holder
            #del PLDrive


            #plog ("Bias File Created: " +str(time.time()-calibration_timer))
            #calibration_timer=time.time()


            # Bad pixel accumulator for the bias frame
            img_temp_median=np.nanmedian(masterBias)
            img_temp_stdev=np.nanstd(masterBias)
            above_array=(masterBias > (img_temp_median + (10 * img_temp_stdev)))
            below_array=(masterBias < (img_temp_median - (10 * img_temp_stdev)))
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array+below_array

            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            try:
                #fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)

                # Save and upload master bias
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', copy.deepcopy(masterBias), None, g_dev['obs'].calib_masters_folder, tempfrontcalib + 'BIAS_master_bin1.fits' ))

                 # Store a version of the bias for the archive too
                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', copy.deepcopy(masterBias), None, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits' ))


                # fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', masterBias, overwrite=True)

                # filepathaws=g_dev['obs'].calib_masters_folder
                # filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits'
                # g_dev['obs'].enqueue_for_calibrationUI(80, filepathaws,filenameaws)


                if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                    #fits.writeto(pipefolder + '/' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #fits.writeto(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' +tempfrontcalib + 'BIAS_master_bin1.fits', masterBias,  overwrite=True)
                    #np.save(pipefolder + '/'+tempfrontcalib + 'BIAS_master_bin1.npy', masterBias)
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + 'BIAS_master_bin1.npy',copy.deepcopy(masterBias)))
            except Exception as e:
                plog ("Could not save bias frame: ",e)


            #plog ("Bias File Pixel Mapped and Saved: " +str(time.time()-calibration_timer))
            #calibration_timer=time.time()



            # Now that we have the master bias, we can estimate the readnoise actually
            # by comparing the standard deviations between the bias and the masterbias
            if g_dev['cam'].camera_known_gain <1000:
                readnoise_array=[]
                post_readnoise_array=[]
                #plog ("Calculating Readnoise. Please Wait.")
                #for file in inputList:
                    #hdu1data = np.load(file, mmap_mode='r')
                    #hdu1data = np.load(file)

                #counter=0
                i=0
                for file in inputList:
                    #PLDrive[:,:,i] = np.load(file)


                    hdu1data=PLDrive[i]-masterBias
                    hdu1data = hdu1data[500:-500,500:-500]
                    stddiffimage=np.nanstd(pow(pow(hdu1data,2),0.5))
                    #est_read_noise= (stddiffimage * g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["camera_gain"]) / 1.414

                    est_read_noise= (stddiffimage * g_dev['cam'].camera_known_gain) / 1.414
                    readnoise_array.append(est_read_noise)
                    post_readnoise_array.append(stddiffimage)
                    i=i+1

                readnoise_array=np.array(readnoise_array)
                #plog ("Raw Readnoise outputs: " +str(readnoise_array))

                #plog ("Final Readnoise: " + str(np.nanmedian(readnoise_array)) + " std: " + str(np.nanstd(readnoise_array)))
           # else:
                #plog ("Skipping readnoise estimation as we don't currently have a reliable camera gain estimate.")

            try:
                g_dev['cam'].biasFiles.update({'1': masterBias.astype(np.float32)})
            except:
                plog("Bias frame master re-upload did not work.")




            plog ("Bias reconstructed: " +str(time.time()-calibration_timer))
            calibration_timer=time.time()
            g_dev["obs"].send_to_user("Bias calibration frame created.")



############################################# DARK





            scaled_darklist=[
                [g_dev['obs'].local_dark_folder                 , 'DARK','1'],
                [g_dev['obs'].local_dark_folder+ 'halfsecdarks/', 'halfsecondDARK', 'halfsec_exposure_dark' ],
                [g_dev['obs'].local_dark_folder+ 'twosecdarks/', '2secondDARK', 'twosec_exposure_dark' ],
                [g_dev['obs'].local_dark_folder+ 'tensecdarks/', '10secondDARK', 'tensec_exposure_dark'],
                [g_dev['obs'].local_dark_folder+ 'broadbanddarks/', 'broadbandssDARK', 'broadband_ss_dark' ],
                [g_dev['obs'].local_dark_folder+ 'narrowbanddarks/', 'narrowbandssDARK','narrowband_ss_dark']
                ]

            bias_darklist=[

                [g_dev['obs'].local_dark_folder+ 'pointzerozerofourfivedarks/', 'pointzerozerofourfiveBIASDARK','pointzerozerofourfive' ],
                [g_dev['obs'].local_dark_folder+ 'onepointfivepercentdarks/', 'onepointfivepercentBIASDARK','onepointfivepercent' ],

                [g_dev['obs'].local_dark_folder+ 'fivepercentdarks/', 'fivepercentBIASDARK','fivepercent' ],
                [g_dev['obs'].local_dark_folder+ 'tenpercentdarks/','tenpercentBIASDARK','tenpercent'],
                [g_dev['obs'].local_dark_folder+ 'quartersecdarks/','quartersecBIASDARK', 'quartersec' ],
                [g_dev['obs'].local_dark_folder+ 'halfsecdarks/','halfsecBIASDARK', 'halfsec'],
                [g_dev['obs'].local_dark_folder+ 'sevenfivepercentdarks/', 'sevenfivepercentBIASDARK', 'sevenfivepercent'],
                [g_dev['obs'].local_dark_folder+ 'onesecdarks/', 'onesecBIASDARK', 'onesec'],
                [g_dev['obs'].local_dark_folder+ 'oneandahalfsecdarks/', 'oneandahalfsecBIASDARK','oneandahalfsec'],
                [g_dev['obs'].local_dark_folder+ 'twosecdarks/', 'twosecBIASDARK', 'twosec' ],
                [g_dev['obs'].local_dark_folder+ 'threepointfivesecdarks/', 'threepointfivesecBIASDARK', 'threepointfivesec'],
                [g_dev['obs'].local_dark_folder+ 'fivesecdarks/', 'fivesecBIASDARK','fivesec' ],
                [g_dev['obs'].local_dark_folder+ 'sevenpointfivesecdarks/', 'sevenpointfivesecBIASDARK','sevenpointfivesec' ],
                [g_dev['obs'].local_dark_folder+ 'tensecdarks/','tensecBIASDARK', 'tensec' ],
                [g_dev['obs'].local_dark_folder+ 'fifteensecdarks/', 'fifteensecBIASDARK','fifteensec' ],
                [g_dev['obs'].local_dark_folder+ 'twentysecdarks/', 'twentysecBIASDARK', 'twentysec'],
                [g_dev['obs'].local_dark_folder+ 'broadbanddarks/', 'broadbandssBIASDARK', 'broadband_ss_biasdark'],
                [g_dev['obs'].local_dark_folder+ 'narrowbanddarks/', 'narrowbandssBIASDARK', 'narrowband_ss_biasdark']
                ]

            # CLEAR OUT OLD TEMPFILES
            darkdeleteList=(glob(g_dev['obs'].local_dark_folder +'/*tempbiasdark.n*'))
            for file in darkdeleteList:
                try:
                    os.remove(file)
                except:
                    plog ("Couldnt remove old dark file: " + str(file))



            for entry in scaled_darklist:

                processedDark = self.make_scaled_dark(entry[0],entry[1], masterBias, shapeImage, archiveDate, pipefolder)

                try:
                    g_dev['cam'].darkFiles.update({entry[2]: processedDark.astype(np.float32)})
                except:
                    plog("Dark frame master re-upload did not work.")


            for entry in bias_darklist:

                processedDark = self.make_bias_dark(entry[0],entry[1], masterBias, shapeImage, archiveDate, pipefolder)


                if entry[2] ==  'broadband_ss_biasdark' or entry[2] == 'narrowband_ss_biasdark':
                    g_dev['cam'].darkFiles.update({entry[2]: processedDark.astype(np.float32)})
                else:

                    try:
                        #flat_biasdarks[entry[2]]=processedDark
                        np.save(g_dev['obs'].local_dark_folder +'/'+entry[2] +'tempbiasdark.npy', processedDark.astype(np.float32))
                    except:
                        plog("Dark frame master re-upload did not work.")



                #'fivepercent'






            # Bad pixel accumulator from long exposure dark
            img_temp_median=np.nanmedian(g_dev['cam'].darkFiles['1'])
            img_temp_stdev=np.nanstd(g_dev['cam'].darkFiles['1'])
            above_array=(g_dev['cam'].darkFiles['1'] > 20)
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array


            # Bad pixel accumulator from broadband exposure dark
            img_temp_median=np.nanmedian(g_dev['cam'].darkFiles['broadband_ss_dark' ])
            img_temp_stdev=np.nanstd(g_dev['cam'].darkFiles['broadband_ss_dark' ])
            above_array=(g_dev['cam'].darkFiles['broadband_ss_dark' ] > 20)
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

            # Bad pixel accumulator from narrowband exposure dark
            img_temp_median=np.nanmedian(g_dev['cam'].darkFiles['narrowband_ss_dark'])
            img_temp_stdev=np.nanstd(g_dev['cam'].darkFiles['narrowband_ss_dark'])
            above_array=(g_dev['cam'].darkFiles['narrowband_ss_dark'] > 20)
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array




            #breakpoint()


            # NOW that we have a master bias and a master dark, time to step through the flat frames!
            tempfilters=glob(g_dev['obs'].local_flat_folder + "*/")
            # plog (datetime.datetime.now().strftime("%H:%M:%S"))
            # plog ("Regenerating flats")
            # plog (tempfilters)

            estimated_flat_gain=[]

            flat_gains={}

            broadband_ss_biasdark_exp_time = self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']
            dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']

            #plog ("flat_biasdarks")
            #plog (flat_biasdarks)
            if len(tempfilters) == 0:
                plog ("there are no filter directories, so not processing flats")
            else:
                for filterfolder in tempfilters:

                    calibration_timer=time.time()
                    filtercode=filterfolder.split('\\')[-2]

                    # DELETE ALL TEMP FILES FROM FLAT DIRECTORY
                    deleteList= (glob(g_dev['obs'].local_flat_folder + filtercode + '/tempcali_*.n*'))
                    for file in deleteList:
                        try:
                            os.remove(file)
                        except:
                            plog ("couldn't remove tempflat: " + str(file))

                    # plog (datetime.datetime.now().strftime("%H:%M:%S"))

                    # plog ("Regenerating flat for " + str(filtercode))
                    inputList=(glob(g_dev['obs'].local_flat_folder + filtercode + '/*.n*'))

                    # Test each flat file actually opens
                    for file in inputList:
                        try:
                            hdu1data = np.load(file, mmap_mode='r')
                        except:
                            plog ("corrupt flat skipped: " + str(file))
                            inputList.remove(file)

                    # Generate temp memmap
                    # plog ("Loading files into memmap")
                    single_filter_camera_gains=[]
                    if len(inputList) == 0 or len(inputList) == 1:
                        plog ("Not doing " + str(filtercode) + " flat. Not enough available files in directory.")
                    else:

                        while True:

                            #PLDrive = np.memmap(g_dev['obs'].local_flat_folder  + 'tempfile', dtype='float32', mode= 'w+', shape = (shapeImage[0],shapeImage[1],len(inputList)))
                            #PLDrive = np.empty((shapeImage[0],shapeImage[1],len(inputList)), dtype=np.float32)

                            # DELETE ALL TEMP FILES FROM FLAT DIRECTORY
                            deleteList= (glob(g_dev['obs'].local_flat_folder + filtercode + '/tempcali_*.n*'))
                            for file in deleteList:
                                try:
                                    os.remove(file)
                                except:
                                    plog ("couldn't remove tempflat: " + str(file))

                            PLDrive = [None] * len(inputList)


                            # Debias and dedark flat frames and stick them in the memmap
                            i=0
                            temp_flat_file_list=[]
                            for file in inputList:
                                #plog("Storing flat in a memmap array: " + str(file))
                                #hdu1data = np.load(file, mmap_mode='r')
                                hdu1data = np.load(file)
                                #PLDrive[i] = np.load(file, mmap_mode='r')

                                hdu1exp=float(file.split('_')[-2])
                                #plog ("EXP")
                                #plog (hdu1exp)
                                fraction_through_range=0



#g_dev['obs'].local_dark_folder +'/'+'fivepercent' +'tempbiasdark.npy'


                                # This try/except is here because if there is a missing dark
                                # we can always just revert to using the long dark.
                                try:

                                    if hdu1exp == 0.0045 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'pointzerozerofourfive' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'pointzerozerofourfive' +'tempbiasdark.npy')
                                        #print("five percent")
                                    elif hdu1exp == 0.015 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'onepointfivepercent' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'onepointfivepercent' +'tempbiasdark.npy')
                                        #print("five percent")
                                    elif hdu1exp == 0.05 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fivepercent' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fivepercent' +'tempbiasdark.npy')
                                        #print("five percent")
                                    elif hdu1exp == 0.1 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'tenpercent' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'tenpercent' +'tempbiasdark.npy')
                                        #print("ten percent")
                                    elif hdu1exp == 0.25 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'quartersec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'quartersec' +'tempbiasdark.npy')
                                        #print("quartersec")
                                    elif hdu1exp == 0.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'halfsec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'halfsec' +'tempbiasdark.npy')
                                        #plog("halfsec")
                                    elif hdu1exp == 0.75 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'sevenfivepercent' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'sevenfivepercent' +'tempbiasdark.npy')
                                        #plog("sevenfivepercent")
                                    elif hdu1exp == 1.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'onesec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'onesec' +'tempbiasdark.npy')
                                        #plog("onesec")
                                    elif hdu1exp == 1.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'oneandahalfsec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'oneandahalfsec' +'tempbiasdark.npy')
                                        #plog("one and a half sec")
                                    elif hdu1exp == 2.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'twosec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'twosec' +'tempbiasdark.npy')
                                        #plog("two sec")
                                    elif hdu1exp == 3.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'threepointfivesec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'threepointfivesec' +'tempbiasdark.npy')
                                        #plog("threepointfive sec")
                                    elif hdu1exp == 5.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fivesec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fivesec' +'tempbiasdark.npy')
                                        #plog("five sec")
                                    elif hdu1exp == 7.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'sevenpointfivesec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'sevenpointfivesec' +'tempbiasdark.npy')
                                        #plog("sevenpointfive sec")
                                    elif hdu1exp == 10.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'tensec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'tensec' +'tempbiasdark.npy')
                                        #plog("ten sec")
                                    elif hdu1exp == 15.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fifteensec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fifteensec' +'tempbiasdark.npy')
                                        #plog("fiveteen sec")
                                    elif hdu1exp == 20.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'twentysec' +'tempbiasdark.npy'):
                                        flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'twentysec' +'tempbiasdark.npy')
                                        #plog("twenty sec")
                                    elif hdu1exp == broadband_ss_biasdark_exp_time:
                                        flatdebiaseddedarked=hdu1data -g_dev['cam'].darkFiles['broadband_ss_biasdark']
                                        #plog ("broady")
                                    elif hdu1exp == narrowband_ss_biasdark_exp_time:
                                        flatdebiaseddedarked=hdu1data -g_dev['cam'].darkFiles['narrowband_ss_biasdark']
                                        #plog ("Narrowy")
                                    elif hdu1exp < 0.5:
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['halfsec_exposure_dark']*hdu1exp)
                                    elif hdu1exp <= 2.0:
                                        fraction_through_range=(hdu1exp-0.5)/(2.0-0.5)
                                        tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['twosec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['halfsec_exposure_dark'])
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                        del tempmasterDark
                                    elif hdu1exp <= 10.0:
                                        fraction_through_range=(hdu1exp-2)/(10.0-2.0)
                                        tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['tensec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['twosec_exposure_dark'])
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                        del tempmasterDark
                                    elif hdu1exp <= broadband_ss_biasdark_exp_time:
                                        fraction_through_range=(hdu1exp-10)/(broadband_ss_biasdark_exp_time-10.0)
                                        tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['broadband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['tensec_exposure_dark'])
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                        del tempmasterDark
                                    elif hdu1exp <= narrowband_ss_biasdark_exp_time:
                                        fraction_through_range=(hdu1exp-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                                        tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['narrowband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['broadband_ss_dark'])
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                        del tempmasterDark
                                    elif dark_exp_time > narrowband_ss_biasdark_exp_time:
                                        fraction_through_range=(hdu1exp-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                                        tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['1']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['narrowband_ss_dark'])
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                        del tempmasterDark
                                    else:
                                        flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['narrowband_ss_dark']*hdu1exp)
                                except:
                                    flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['1']*hdu1exp)

                                #plog ("Fraction through range")
                                #plog (fraction_through_range)
                                del hdu1data

                                # Normalising flat file
                                if not g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                                    normalising_factor=np.nanmedian(flatdebiaseddedarked)
                                    flatdebiaseddedarked = flatdebiaseddedarked/normalising_factor
                                    # Naning bad entries into master flat
                                    flatdebiaseddedarked[flatdebiaseddedarked < 0.25] = np.nan
                                    flatdebiaseddedarked[flatdebiaseddedarked > 2.0] = np.nan
                                    # Rescaling median once nan'ed
                                    flatdebiaseddedarked = flatdebiaseddedarked/np.nanmedian(flatdebiaseddedarked)
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
                                    # Naning bad entries into master flat
                                    flatdebiaseddedarked[flatdebiaseddedarked < 0.25] = np.nan
                                    flatdebiaseddedarked[flatdebiaseddedarked > 2.0] = np.nan
                                    # Rescaling median once nan'ed
                                    flatdebiaseddedarked = flatdebiaseddedarked/np.nanmedian(flatdebiaseddedarked)

                                #PLDrive[:,:,i] = copy.deepcopy(flatdebiaseddedarked)

                                #breakpoint()
                                # Make new filename
                                tempfile=file.replace('\\','/').split('/')
                                tempfile[-1]='tempcali_' + tempfile[-1]
                                tempfile="/".join(tempfile)

                                np.save(tempfile, flatdebiaseddedarked)
                                del flatdebiaseddedarked
                                temp_flat_file_list.append(tempfile)
                                PLDrive[i] = np.load(tempfile, mmap_mode='r')

                                i=i+1

                            plog ("Insert flats into megaarray: " +str(time.time()-calibration_timer))

                            #

                            finalImage=np.zeros(shapeImage, dtype=np.float32)

                            #try:

                            # create an empty array to hold each chunk
                            # the size of this array will determine the amount of RAM usage

                            # Get a chunk size that evenly divides the array
                            chunk_size=8
                            while not ( shapeImage[0] % chunk_size ==0):
                                chunk_size=chunk_size+1
                                #print (chunk_size)
                            chunk_size=int(shapeImage[0]/chunk_size)

                            holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                            # iterate through the input, replace with ones, and write to output
                            for i in range(shapeImage[0]):
                                if i % chunk_size == 0:
                                    #print (i)
                                    counter=0
                                    for imagefile in range(len(PLDrive)):
                                        holder[counter][0:chunk_size,:] = copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)
                                        counter=counter+1

                                    finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)

                                    # Wipe and restore files in the memmap file
                                    # To clear RAM usage
                                    PLDrive= [None] * len(temp_flat_file_list)
                                    i=0
                                    for file in temp_flat_file_list:
                                        #PLDrive[:,:,i] = np.load(file, mmap_mode='r')
                                        PLDrive[i] = np.load(file, mmap_mode='r')
                                        i=i+1


                            # # plog ("**********************************")
                            # # plog ("Median Stacking each " + str (filtercode) + " flat frame row individually")
                            # # plog (datetime.datetime.now().strftime("%H:%M:%S"))
                            # # Go through each pixel and calculate nanmedian. Can't do all arrays at once as it is hugely memory intensive
                            # finalImage=np.zeros(shapeImage,dtype=float)

                            # mptask=[]
                            # counter=0
                            # for goog in range(shapeImage[0]):
                            #     #mptask.append((g_dev['obs'].local_flat_folder + 'tempfile',counter, (shapeImage[0],shapeImage[1],len(inputList))))
                            #     mptask.append(PLDrive[counter,:,:])
                            #     counter=counter+1

                            # counter=0
                            # with Pool(math.floor(os.cpu_count()*0.85)) as pool:
                            #     for result in pool.map(stack_nanmedian_row, mptask):
                            #         finalImage[counter,:]=result
                            #         counter=counter+1

                            # plog (datetime.datetime.now().strftime("%H:%M:%S"))
                            # #plog ("**********************************")
                            plog ("Median stack flat: " +str(time.time()-calibration_timer))

                            # plog ("Assessing flat components")
                            #nanmedian_collector=[]
                            nanstd_collector=[]
                            for flat_component in range(len(inputList)):
                                #plog (flat_component)
                                #tempdivide=PLDrive[:,:,flat_component] / finalImage
                                tempdivide=PLDrive[flat_component] / finalImage

                                #tempnanmedian=np.nanmedian(tempdivide)
                                tempstd=np.nanstd(tempdivide)
                                #plog ("nanmedian: " + str(tempnanmedian ))
                                #plog ("nanstdev: " + str(tempstd))
                                #nanmedian_collector.append(tempnanmedian)
                                nanstd_collector.append(tempstd)

                            # plog ("*********************************")
                            # #plog (nanmedian_collector)
                            # plog (nanstd_collector)
                            # #plog ("Median of median: " + str(np.array(np.nanmedian(nanmedian_collector))))
                            # #plog ("Std of median: " + str(np.array(np.std(nanmedian_collector))))
                            # plog ("Median of stdev: " + str(np.array(np.nanmedian(nanstd_collector))))
                            # plog ("Std of stdev: " + str(np.array(np.std(nanstd_collector))))
                            med_std=np.array(np.nanmedian(nanstd_collector))
                            std_std=np.array(np.std(nanstd_collector))
                            # plog ("*********************************")
                            # plog ("Assessing component flat fits to stacked flat")

                            delete_flat_components=[]
                            for counterflat in range(len(nanstd_collector)):
                                #plog ("Image " + str(counterflat) + " assessment")
                                if nanstd_collector[counterflat] > (med_std + 5 * std_std):
                                    # plog ("FOUND A REJECTION: " + str(round(nanstd_collector[counterflat],5)) + " > " + str(round(med_std + 3 * std_std,5)))
                                    delete_flat_components.append(counterflat)

                            if len(delete_flat_components) < math.ceil(0.1*len(nanstd_collector)):
                                break

                            # plog ("REPROCESSING FLAT WITH BAD COMPONENTS REMOVED")
                            # Remove problematic flat images from squishener so we can re-run the flat.
                            for index in sorted(delete_flat_components, reverse=True):
                                del inputList[index]
                            #PLDrive._mmap.close()
                            del PLDrive
                            #gc.collect()
                            #os.remove(g_dev['obs'].local_flat_folder  + 'tempfile')

                            plog ("REDOING FLAT. TOO MANY OUTLIERS: " + str(len(delete_flat_components)))

                        plog ("Checked component flats vs stacked flat: " +str(time.time()-calibration_timer))

                        del PLDrive
                        #del flat_biasdarks

                        temporaryFlat=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
                        del finalImage

                        # Bad pixel accumulator
                        img_temp_median=np.nanmedian(temporaryFlat)
                        img_temp_stdev=np.nanstd(temporaryFlat)
                        above_array=(temporaryFlat > (img_temp_median + (10 * img_temp_stdev)))
                        # BELOW IS A BAD IDEA FOR FLATS, BECAUSE HEAVY VIGNETTING WILL CAUSE BAD PIXELS
                        #below_array=(temporaryFlat < (img_temp_median - (10 * img_temp_stdev)))
                        # plog ("Bad pixels above: " + str(above_array.sum()))
                        #plog ("Bad pixels below: " + str(below_array.sum()))
                        bad_pixel_mapper_array=bad_pixel_mapper_array+above_array


                        temporaryFlat[temporaryFlat == inf] = np.nan
                        temporaryFlat[temporaryFlat == -inf] = np.nan
                        temporaryFlat[temporaryFlat < 0.5] = np.nan
                        temporaryFlat[temporaryFlat > 2.0] = np.nan
                        pre_num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))

                        # plog ("Interpolating Nans")
                        last_num_of_nans=846753876359.0
                        while pre_num_of_nans > 0:
                            # Fix up any glitches in the flat


                            num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))
                            #plog ("Number of Nans in flat this iteration: " + str(num_of_nans))

                            if num_of_nans == last_num_of_nans:
                                break
                            last_num_of_nans=copy.deepcopy(num_of_nans)
                            while num_of_nans > 0:

                                # List the coordinates that are nan in the array
                                nan_coords=np.argwhere(np.isnan(temporaryFlat))
                                x_size=temporaryFlat.shape[0]
                                y_size=temporaryFlat.shape[1]

                                # For each coordinate pop out the 3x3 grid
                                try:
                                    for nancoord in nan_coords:
                                        x_nancoord=nancoord[0]
                                        y_nancoord=nancoord[1]
                                        countervalue=0
                                        countern=0
                                        # left
                                        if x_nancoord != 0:
                                            value_here=temporaryFlat[x_nancoord-1,y_nancoord]
                                            if not np.isnan(value_here):
                                                countervalue=countervalue+value_here
                                                countern=countern+1
                                        # right
                                        if x_nancoord != (x_size-1):
                                            value_here=temporaryFlat[x_nancoord+1,y_nancoord]
                                            if not np.isnan(value_here):
                                                countervalue=countervalue+value_here
                                                countern=countern+1
                                        # below
                                        if y_nancoord != 0:
                                            value_here=temporaryFlat[x_nancoord,y_nancoord-1]
                                            if not np.isnan(value_here):
                                                countervalue=countervalue+value_here
                                                countern=countern+1
                                        # above
                                        if y_nancoord != (y_size-1):
                                            value_here=temporaryFlat[x_nancoord,y_nancoord+1]
                                            if not np.isnan(value_here):
                                                countervalue=countervalue+value_here
                                                countern=countern+1

                                        if countern == 0:
                                            temporaryFlat[x_nancoord,y_nancoord]=np.nan
                                        else:
                                            temporaryFlat[x_nancoord,y_nancoord]=countervalue/countern


                                except:
                                    plog(traceback.format_exc())

                                num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))
                                #plog ("Number of Nans in flat this iteration: " + str(num_of_nans))




                            #plog ("Round Flat Max: " + str(np.max(temporaryFlat)))

                            #plog ("Round Flat Min: " + str(np.min(temporaryFlat)))
                            #plog ("Round Flat Median: " + str(np.median(temporaryFlat)))
                            #plog ("Round Flat Average: " + str(np.average(temporaryFlat)))
                            #plog ("Round Flat Stdev: " + str(np.std(temporaryFlat)))

                            temporaryFlat[temporaryFlat == inf] = np.nan
                            temporaryFlat[temporaryFlat == -inf] = np.nan
                            temporaryFlat[temporaryFlat < 0.5] = np.nan
                            temporaryFlat[temporaryFlat > 2.0] = np.nan


                            pre_num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))


                        # plog ("Final Flat Max: " + str(np.nanmax(temporaryFlat)))
                        # plog ("Final Flat Min: " + str(np.nanmin(temporaryFlat)))
                        # plog ("Final Flat Median: " + str(np.nanmedian(temporaryFlat)))

                        # plog ("Final Flat Average: " + str(np.nanmean(temporaryFlat)))  #<<WER changed average to mean

                        # plog ("Final Flat Stdev: " + str(np.nanstd(temporaryFlat)))

                        #breakpoint()

                        if np.count_nonzero(np.isnan(temporaryFlat)) > 0:
                            plog ("No improvement with last interpolation attempt.")
                            plog ("Filling remaining nans with median")
                            temporaryFlat=np.nan_to_num(temporaryFlat, nan = np.nanmedian(temporaryFlat))



                        plog ("Interpolated flat: " +str(time.time()-calibration_timer))




                        # # plog ('debanding flatfield')
                        # ###### We have to deband the flat to stop banded flats band light images.
                        # # If that makes sense.

                        # # Remove horizontal and vertical banding
                        # # If there isn't banding this should not alter the array really
                        # sigma_clipped_array=copy.deepcopy(temporaryFlat)

                        # # REMOVE LOW VALUES

                        # #Do some fiddle faddling to figure out the value that goes to zero less
                        # int_array_flattened=sigma_clipped_array.astype(int).ravel()
                        # unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
                        # m=counts.argmax()
                        # imageMode=unique[m]

                        # # Collect unique values and counts
                        # histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                        # zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
                        # breaker=1
                        # counter=0
                        # while (breaker != 0):
                        #     counter=counter+1
                        #     if not (imageMode-counter) in zeroValueArray[:,0]:

                        #         zeroValue=(imageMode-counter)
                        #         breaker =0
                        # sigma_clipped_array[sigma_clipped_array < zeroValue] = np.nan
                        # #histogramdata=histogramdata[histogramdata[:,0] > zeroValue]

                        # # REMOVE HIGH VALUES
                        # while True:
                        #     tempstd=np.nanstd(sigma_clipped_array)
                        #     tempmedian=np.nanmedian(sigma_clipped_array)
                        #     clipped_areas=sigma_clipped_array > tempmedian + 4*tempstd
                        #     if np.sum(clipped_areas) == 0:
                        #         break
                        #     #plog (np.sum(clipped_areas))
                        #     sigma_clipped_array[clipped_areas] = np.nan
                        #     #breakpoint()

                        # # REMOVE LOW VALUES
                        # while True:
                        #     tempstd=np.nanstd(sigma_clipped_array)
                        #     tempmedian=np.nanmedian(sigma_clipped_array)
                        #     clipped_areas=sigma_clipped_array < tempmedian - 4*tempstd
                        #     if np.sum(clipped_areas) == 0:
                        #         break
                        #     #plog (np.sum(clipped_areas))
                        #     sigma_clipped_array[clipped_areas] = np.nan
                        #     #breakpoint()


                        # # Do rows
                        # rows_median = np.nanmedian(sigma_clipped_array,axis=1)
                        # #rows_x = np.arange(0,len(rows_median),1.0)
                        # #plt.scatter(columns_median)
                        # rows_median[np.isnan(rows_median)] = np.nanmedian(rows_median) # This should bea more thorough nearest neighbour thing when I get to it

                        # row_debanded_image= temporaryFlat-rows_median[:,None]
                        # #debanded_rows_median=np.nanmedian(row_debanded_image,axis=1)
                        # #plt.scatter(columns_x,debanded_columns_medain)

                        # # plog ("Done rows. Now columns.")

                        # # Then run this on columns
                        # sigma_clipped_array=copy.deepcopy(row_debanded_image)
                        # # REMOVE HIGH VALUES
                        # while True:
                        #     tempstd=np.nanstd(sigma_clipped_array)
                        #     tempmedian=np.nanmedian(sigma_clipped_array)
                        #     clipped_areas=sigma_clipped_array > tempmedian + 4*tempstd
                        #     if np.sum(clipped_areas) == 0:
                        #         break
                        #     #plog (np.sum(clipped_areas))
                        #     sigma_clipped_array[clipped_areas] = np.nan
                        #     #breakpoint()

                        # # REMOVE LOW VALUES
                        # while True:
                        #     tempstd=np.nanstd(sigma_clipped_array)
                        #     tempmedian=np.nanmedian(sigma_clipped_array)
                        #     clipped_areas=sigma_clipped_array < tempmedian - 4*tempstd
                        #     if np.sum(clipped_areas) == 0:
                        #         break
                        #     #plog (np.sum(clipped_areas))
                        #     sigma_clipped_array[clipped_areas] = np.nan
                        #     #breakpoint()


                        # columns_median = np.nanmedian(sigma_clipped_array,axis=0)
                        # #columns_x = np.arange(0,len(columns_median),1.0)
                        # columns_median[np.isnan(columns_median)] = np.nanmedian(columns_median)

                        # both_debanded_image= row_debanded_image-columns_median[None,:]
                        # #debanded_both_median=np.nanmedian(both_debanded_image,axis=0)

                        # # Reinstitute pedestal
                        # both_debanded_image=both_debanded_image+1

                        # #both_debanded_image = thresh(both_debanded_image, image_saturation_level)
                        # temporaryFlat=both_debanded_image

                        # plog ("Debanded flat: " +str(time.time()-calibration_timer))



                        try:




                            g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy', copy.deepcopy(temporaryFlat)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


                            #np.save(g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy', temporaryFlat)

                            # # Write to and upload current master flat
                            # fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat, overwrite=True)

                            # filepathaws=g_dev['obs'].calib_masters_folder
                            # filenameaws=tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits'
                            # g_dev['obs'].enqueue_for_calibrationUI(50, filepathaws,filenameaws)


                            # Save and upload master bias
                            g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', copy.deepcopy(temporaryFlat), None, g_dev['obs'].calib_masters_folder, tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits' ))


                            # # Store a version of the flat for the archive too
                            # fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat, overwrite=True)

                            # filepathaws=g_dev['obs'].calib_masters_folder
                            # filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits'
                            # g_dev['obs'].enqueue_for_calibrationUI(80, filepathaws,filenameaws)

                            # Store a version of the bias for the archive too
                            g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', copy.deepcopy(temporaryFlat), None, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits' ))



                            if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                                #fits.writeto(pipefolder + '/' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat,  overwrite=True)
                                #fits.writeto(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', temporaryFlat,  overwrite=True)
                                #np.save(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.npy', temporaryFlat)
                                #np.save(pipefolder + '/' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.npy', temporaryFlat)
                                g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', pipefolder + '/' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.npy', copy.deepcopy(temporaryFlat)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))



                        except Exception as e:
                            plog ("Could not save flat frame: ",e)

                        plog ("Saved flat: " +str(time.time()-calibration_timer))


                        # Now to estimate gain from flats
                        for fullflat in inputList:
                            #hdu1data = np.load(fullflat, mmap_mode='r')
                            hdu1data = np.load(fullflat)

                            hdu1exp=float(file.split('_')[-2])

                            camera_gain_estimate_image=((hdu1data-masterBias)-(g_dev['cam'].darkFiles['1']*hdu1exp))
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
                            plog ("Camera gain median: " + str(cge_median) + " stdev: " +str(cge_stdev)+ " sqrt: " + str(cge_sqrt) + " gain: " +str(cge_gain))

                            estimated_flat_gain.append(cge_gain)

                            single_filter_camera_gains.append(cge_gain)

                        single_filter_camera_gains=np.array(single_filter_camera_gains)
                        single_filter_camera_gains = sigma_clip(single_filter_camera_gains, masked=False, axis=None)
                        plog ("Filter Gain Sigma Clipped Estimates: " + str(np.nanmedian(single_filter_camera_gains)) + " std " + str(np.std(single_filter_camera_gains)) + " N " + str(len(single_filter_camera_gains)))
                        flat_gains[filtercode]=[np.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]

                        # Chuck camera gain and number of images into the shelf
                        try:
                            # for every filter hold onto an estimate of the current camera gain.
                            # Each filter will have a different flat field and variation in the flat.
                            # The 'true' camera gain is very likely to be the filter with the least
                            # variation, so we go with that as the true camera gain...... but ONLY after we have a full set of flats
                            # with which to calculate the gain. This is the shelf to hold this data.
                            # There is no hope for individual owners with a multitude of telescopes to keep up with
                            # this estimate, so we need to automate it with a first best guess given in the config.
                            self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))
                            self.filter_camera_gain_shelf[filtercode]=[np.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]
                            self.filter_camera_gain_shelf.close()
                        except:
                            plog("************* FAILED TO WRITE TO FILTER GAIN SHELF. Usually while flats are being taken at the same time. Follow-up if this becomes relatively frequent.")


                        #PLDrive._mmap.close()
                        #del PLDrive
                        #gc.collect()
                        #os.remove(g_dev['obs'].local_flat_folder  + 'tempfile')

                        plog (str(filtercode) + " flat camera gains measured : " +str(time.time()-calibration_timer))


                    # DELETE ALL TEMP FILES FROM FLAT DIRECTORY
                    deleteList= (glob(g_dev['obs'].local_flat_folder + filtercode + '/tempcali_*.n*'))
                    for file in deleteList:
                        try:
                            os.remove(file)
                        except:
                            plog ("couldn't remove tempflat: " + str(file))

                    #for file in fileList:
                    if self.config['camera'][g_dev['cam'].name]['settings']['hold_flats_in_memory']:
                        #tempflatframe=np.load(file)
                        #
                        g_dev['cam'].flatFiles.update({filtercode: copy.deepcopy(temporaryFlat)})
                        #del tempflatframe
                    else:
                        g_dev['cam'].flatFiles.update({filtercode: g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy'})

                    g_dev["obs"].send_to_user(str(filtercode) + " flat calibration frame created.")
                    plog (str(filtercode) + " flat calibration frame created: " +str(time.time()-calibration_timer))
                    calibration_timer=time.time()



                # Now finished with the biasdarks specifically for flats,
                # delete them
                #del flat_biasdarks





                # Bung in the readnoise estimates and then
                # Close up the filter camera gain shelf.
                try:
                    self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))
                    self.filter_camera_gain_shelf['readnoise']=[np.nanmedian(post_readnoise_array) , np.nanstd(post_readnoise_array), len(post_readnoise_array)]
                    self.filter_camera_gain_shelf.close()
                except:
                    plog ("cannot write the readnoise array to the shelf. Probs because this is the first time estimating gains")


                textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'cameragain' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.txt'
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
                        #plog ("Raw List of Gains: " +str(estimated_flat_gain))
                        #f.write ("Raw List of Gains: " +str(estimated_flat_gain)+ "\n"+ "\n")

                        #plog ("Camera Gain Non-Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain)))
                        #f.write ("Camera Gain Non-Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain))+ "\n")

                        estimated_flat_gain = sigma_clip(estimated_flat_gain, masked=False, axis=None)
                       # plog ("Camera Gain Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain)))
                        #f.write ("Camera Gain Sigma Clipped Estimates: " + str(np.nanmedian(estimated_flat_gain)) + " std " + str(np.std(estimated_flat_gain)) + " N " + str(len(estimated_flat_gain))+ "\n")

                        est_read_noise=[]
                        try:
                            for rnentry in post_readnoise_array:
                                est_read_noise.append( (rnentry * np.nanmedian(estimated_flat_gain)) / 1.414)

                            est_read_noise=np.array(est_read_noise)
                            #plog ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise)))
                            f.write ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise))+ "\n")
                            est_read_noise = sigma_clip(est_read_noise, masked=False, axis=None)
                            #plog ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise)))
                            f.write ("Non Sigma Clipped Readnoise with this gain: " + str(np.nanmedian(est_read_noise)) + " std: " + str(np.nanstd(est_read_noise))+ "\n")
                        except:
                            plog ("Did not estimate readnoise as probs no previous known gains.")
                            #plog(traceback.format_exc())

                        plog ("Gains by filter")
                        for filterline in flat_gains:
                            plog (filterline+ " " + str(flat_gains[filterline]))
                            f.write(filterline + " " + str(flat_gains[filterline]) + "\n")

                except:
                    plog ("hit some snag with reporting gains")
                    plog(traceback.format_exc())
                    #




                # THEN reload them to use for the next night.
                # First delete the calibrations out of memory.

                # g_dev['cam'].flatFiles = {}
                # g_dev['cam'].hotFiles = {}
                # try:
                #     fileList = glob(g_dev['obs'].calib_masters_folder + '/masterFlat*_bin1.npy')
                #     for file in fileList:
                #         if self.config['camera'][g_dev['cam'].name]['settings']['hold_flats_in_memory']:
                #             tempflatframe=np.load(file)
                #             #
                #             g_dev['cam'].flatFiles.update({file.split('_')[-2]: np.array(tempflatframe)})
                #             del tempflatframe
                #         else:
                #             g_dev['cam'].flatFiles.update({file.split("_")[1].replace ('.npy','') + '_bin1': file})
                #     # To supress occasional flatfield div errors
                #     np.seterr(divide="ignore")
                # except:
                #     plog(traceback.format_exc())
                #     plog("Flat frames not loaded or available")


                plog ("Regenerated Flat Masters and Re-loaded them into memory.")

            plog ("Re-loading Bias and Dark masters into memory.")
            # Reload the bias and dark frames

            #g_dev['cam'].darkFiles = {}

            # Create the bad pixel map fits and npy
            # Save the local boolean array
            plog ("Total bad pixels in image: " + str(bad_pixel_mapper_array.sum()))
            plog ("Writing out bad pixel map npy and fits.")
            np.save(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'badpixelmask_bin1.npy', bad_pixel_mapper_array)

            # pipefolder = g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias
            # g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', pipefolder + '/' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.npy', copy.deepcopy(temporaryFlat)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


            # convert the boolean

            #breakpoint()
            fits.writeto(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'badpixelmask_bin1.fits', bad_pixel_mapper_array*1,  overwrite=True)

            filepathaws=g_dev['obs'].calib_masters_folder
            filenameaws=tempfrontcalib + 'badpixelmask_bin1.fits'
            g_dev['obs'].enqueue_for_calibrationUI(50, filepathaws,filenameaws)

            # Store a version of the flat for the archive too
            fits.writeto(g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'badpixelmask_bin1.fits', bad_pixel_mapper_array*1, overwrite=True)

            filepathaws=g_dev['obs'].calib_masters_folder
            filenameaws='ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'badpixelmask_bin1.fits'
            g_dev['obs'].enqueue_for_calibrationUI(80, filepathaws,filenameaws)
            if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                #fits.writeto(pipefolder + '/' + tempfrontcalib + 'badpixelmask_bin1.fits', bad_pixel_mapper_array*1,  overwrite=True)
                #fits.writeto(pipefolder + '/' + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'badpixelmask_bin1.fits', bad_pixel_mapper_array*1,  overwrite=True)
                #np.save(pipefolder + '/' + tempfrontcalib + 'badpixelmask_bin1.npy', bad_pixel_mapper_array)
                g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', pipefolder + '/' + tempfrontcalib + 'badpixelmask_bin1.npy', copy.deepcopy( bad_pixel_mapper_array)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

            try:
                g_dev['cam'].bpmFiles = {}
                g_dev['cam'].bpmFiles.update({'1': bad_pixel_mapper_array})
            except:
                plog("Dark frame master re-upload did not work.")




            # CLEAR OUT OLD TEMPFILES
            darkdeleteList=(glob(g_dev['obs'].local_dark_folder +'/*tempbiasdark.n*'))
            for file in darkdeleteList:
                try:
                    os.remove(file)
                except:
                    plog ("Couldnt remove old dark file: " + str(file))


            try:
                del masterBias
            except:
                pass
            try:
                del masterDark
            except:
                pass

            try:
                del twosecond_masterDark
            except:
                pass
            try:
                del tensecond_masterDark
            except:
                pass
            try:
                del broadbandss_masterDark
            except:
                pass
            try:
                del broadbandss_masterBiasDark
            except:
                pass
            try:
                del narrowbandss_masterDark
            except:
                pass
            try:
                del narrowbandss_masterBiasDark
            except:
                pass


            try:
                del bad_pixel_mapper_array
            except:
                pass



        # Regenerate gain and readnoise
        g_dev['cam'].camera_known_gain=70000.0
        g_dev['cam'].camera_known_gain_stdev=70000.0
        g_dev['cam'].camera_known_readnoise=70000.0
        g_dev['cam'].camera_known_readnoise_stdev=70000.0

        #breakpoint()
        # if True:
        try:

            gain_collector=[]
            stdev_collector=[]

            g_dev['cam'].filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))

            for entry in g_dev['cam'].filter_camera_gain_shelf:
                if entry != 'readnoise':
                    singlentry=g_dev['cam'].filter_camera_gain_shelf[entry]
                    #if singlentry[2] > int(0.8 * g_dev['cam'].config['camera'][g_dev['cam'].name]['settings']['number_of_flat_to_store']):
                    gain_collector.append(singlentry[0])
                    stdev_collector.append(singlentry[1])
                        # if singlentry[0] < g_dev['cam'].camera_known_gain:
                        #     g_dev['cam'].camera_known_gain=singlentry[0]
                        #     g_dev['cam'].camera_known_gain_stdev=singlentry[1]



            while True:
                print (gain_collector)
                gainmed=np.nanmedian(gain_collector)
                print (gainmed)
                gainstd=np.nanstd(gain_collector)
                print (gainstd)
                new_gain_pile=[]
                new_stdev_pile=[]
                counter=0
                if len(gain_collector) > 1:
                    for entry in gain_collector:
                        if entry < gainmed + 3* gainstd:
                            new_gain_pile.append(entry)
                            new_stdev_pile.append(stdev_collector[counter])
                        counter=counter+1
                    if len(new_gain_pile) == len(gain_collector):
                        break
                    gain_collector=copy.deepcopy(new_gain_pile)
                    stdev_collector=copy.deepcopy(new_stdev_pile)
                else:
                    break

            if len(gain_collector) == 1:
                g_dev['cam'].camera_known_gain=gain_collector[0]
                g_dev['cam'].camera_known_gain_stdev=stdev_collector[0]
            else:

                g_dev['cam'].camera_known_gain=gainmed
                g_dev['cam'].camera_known_gain_stdev=np.nanstd(gain_collector)

            #breakpoint()

            singlentry=g_dev['cam'].filter_camera_gain_shelf['readnoise']
            g_dev['cam'].camera_known_readnoise= (singlentry[0] * g_dev['cam'].camera_known_gain) / 1.414
            g_dev['cam'].camera_known_readnoise_stdev = (singlentry[1] * g_dev['cam'].camera_known_gain) / 1.414
        except:
            plog('failed to estimate gain and readnoise from flats and such')
        #         g_dev['cam'].camera_known_gain=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["camera_gain"]
        #         g_dev['cam'].camera_known_gain_stdev=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['camera_gain_stdev']
        #         g_dev['cam'].camera_known_readnoise=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['read_noise']
        #         g_dev['cam'].camera_known_readnoise_stdev=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['read_noise_stdev']

        # else:
        #     g_dev['cam'].camera_known_gain=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["camera_gain"]
        #     g_dev['cam'].camera_known_gain_stdev=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['camera_gain_stdev']
        #     g_dev['cam'].camera_known_readnoise=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['read_noise']
        #     g_dev['cam'].camera_known_readnoise_stdev=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['read_noise_stdev']

        if np.isnan(g_dev['cam'].camera_known_gain):
            g_dev['cam'].camera_known_gain = 70000
        plog ("Used Camera Gain: " + str(g_dev['cam'].camera_known_gain))
        plog ("Used Readnoise  : "+ str(g_dev['cam'].camera_known_readnoise))

        g_dev["obs"].send_to_user("All calibration frames completed.")

        #self.total_sequencer_control = False

        return


    def check_zenith_and_move_to_flat_spot(self, ending=None, dont_wait_after_slew=False):

        too_close_to_zenith=True
        while too_close_to_zenith:
            alt, az = g_dev['mnt'].flat_spot_now()
            alt=g_dev['mnt'].flatspot_alt
            #az=g_dev['mnt'].flatspot_az
            if self.config['degrees_to_avoid_zenith_area_for_calibrations'] > 0:
                plog ('zenith distance: ' + str(90-alt))
                if abs(90-alt) < self.config['degrees_to_avoid_zenith_area_for_calibrations']:
                    parkalt=90-self.config['degrees_to_avoid_zenith_area_for_calibrations']
                    plog ("waiting for the flat spot to move through the zenith")

                    plog ("Moving the scope ahead of the zenith spot and keeping it there and waiting for the sun to set a little more.")
                    g_dev['mnt'].go_command(alt=parkalt, az=270, skyflatspot=True)

                    # Check it hasn't actually been homed this evening from the rotatorhome shelf
                    homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                    if 'lasthome' in homerotator_time_shelf:
                        if time.time() - homerotator_time_shelf['lasthome'] <  43200: # A home in the last twelve hours
                            self.rotator_has_been_homed_this_evening=True
                    homerotator_time_shelf.close()
                    # Homing Rotator for the evening.
                    if not self.rotator_has_been_homed_this_evening:
                        plog ("If rotator isn't homed, waiting for the zenith is a great time to do this!")
                        try:
                            while g_dev['rot'].rotator.IsMoving:
                                plog("home rotator wait")
                                time.sleep(1)
                            g_dev['obs'].send_to_user("Rotator being homed to be certain of appropriate skyflat positioning.", p_level='INFO')
                            time.sleep(0.5)
                            g_dev['rot'].home_command({},{})
                            temptimer=time.time()
                            while g_dev['rot'].rotator.IsMoving:
                                plog("home rotator wait")
                                time.sleep(1)
                                if (time.time() - temptimer) > 20:
                                    #g_dev["obs"].request_full_update()
                                    temptimer=time.time()
                            # Store last home time.
                            homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                            homerotator_time_shelf['lasthome'] = time.time()
                            homerotator_time_shelf.close()

                            self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=dont_wait_after_slew)
                            if not dont_wait_after_slew:
                                self.wait_for_slew()
                            while g_dev['rot'].rotator.IsMoving:
                                plog("home rotator wait")
                                time.sleep(1)
                            self.rotator_has_been_homed_this_evening=True
                            g_dev['obs'].rotator_has_been_checked_since_last_slew = True

                        except:
                            #plog ("no rotator to home or wait for.")
                            pass

                    time.sleep(30)

                    g_dev['obs'].request_scan_requests()
                    #g_dev["obs"].request_full_update()

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
                    g_dev['mnt'].go_command(skyflatspot=True, dont_wait_after_slew=dont_wait_after_slew)
                    too_close_to_zenith=False
            else:
                g_dev['mnt'].go_command(skyflatspot=True, dont_wait_after_slew=dont_wait_after_slew)
                too_close_to_zenith=False

    def sky_flat_script(self, req, opt, morn=False, skip_moon_check=False):
        """
        This is the evening and morning sky automated skyflat routine.
        """
        self.flats_being_collected = True
        self.eve_sky_flat_latch = True
        self.morn_sky_flat_latch = True

        #morn=True
        #skip_moon_check=True
        #breakpoint()

        #breakpoint()
        to_zone = tz.gettz(g_dev['evnt'].wema_config['TZ_database_name'])
        hourtime=datetime.datetime.now().astimezone(to_zone).hour

        if hourtime > 0 and hourtime < 12:
            morn = True
        else:
            morn = False




        if not g_dev['obs'].moon_checks_on:
            skip_moon_check=True

        if not (g_dev['obs'].enc_status['shutter_status'] == 'Open') and not (g_dev['obs'].enc_status['shutter_status'] == 'Sim. Open'):
            plog ("NOT DOING FLATS -- THE ROOF IS SHUT!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as the roof is shut.")
            self.flats_being_collected = False
            self.eve_sky_flat_latch = False
            self.morn_sky_flat_latch = False
            return

        if  ((ephem.now() < g_dev['events']['Cool Down, Open']) or \
            (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['Nightly Reset'])):
            plog ("NOT DOING FLATS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it is during the daytime.")
            self.flats_being_collected = False
            self.eve_sky_flat_latch = False
            self.morn_sky_flat_latch = False
            return

        if (g_dev['events']['Naut Dusk'] < ephem.now() < g_dev['events']['Naut Dawn']) :
            plog ("NOT DOING FLATS -- IT IS THE NIGHTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it too dark.")
            self.flats_being_collected = False
            self.eve_sky_flat_latch = False
            self.morn_sky_flat_latch = False
            return


        #self.flats_being_collected = True

        # This variable will trigger a re-run of the flat script if it detects that it had to estimate a new throughput
        # So that a proper full flat script is run after the estimates
        self.new_throughtputs_detected_in_flat_run=False

        g_dev['seq'].blockend= None

        # Moon check.
        if (skip_moon_check==False):
            # Moon current alt/az
            currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
            #moondata=get_moon(Time.now()).transform_to(currentaltazframe)
            moondata=get_body("moon", time=Time.now()).transform_to(currentaltazframe)

            # Flatspot position.
            flatspotalt, flatspotaz = g_dev['mnt'].flat_spot_now()
            temp_separation=((ephem.separation( (flatspotaz,flatspotalt), (moondata.az.deg,moondata.alt.deg))))

            if (moondata.alt.deg < -5):
                plog ("Moon is far below the ground, alt " + str(moondata.alt.deg) + ", sky flats going ahead.")

            elif temp_separation < math.radians(self.config['minimum_distance_from_the_moon_when_taking_flats']): #and (ephem.Moon(datetime.datetime.now()).moon_phase) > 0.05:
                plog ("Moon is in the sky and less than " + str(self.config['minimum_distance_from_the_moon_when_taking_flats']) + " degrees ("+str(temp_separation)+") away from the flat spot, skipping this flat time.")
                #return


        #self.flats_being_collected = True
        plog('Sky Flat sequence Starting.')
        self.next_flat_observe = time.time()
        g_dev['obs'].send_to_user('Sky Flat sequence Starting.', p_level='INFO')
        evening = not morn
        camera_name = str(self.config['camera']['camera_1_1']['name'])
        flat_count = self.config['camera']['camera_1_1']['settings']['number_of_flat_to_collect']
        min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_flat_exposure'])
        max_exposure = float(self.config['camera']['camera_1_1']['settings']['max_flat_exposure'])

        exp_time = min_exposure


        broadband_ss_biasdark_exp_time = float(self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time'])
        narrowband_ss_biasdark_exp_time = float(broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier'])

        sky_exposure_snap_to_grid = [ 0.0045, 0.015, 0.05,0.1, 0.25, 0.5 , 0.75, 1, 1.5, 2.0, 3.5, 5.0, 7.5, 10, 15, 20, broadband_ss_biasdark_exp_time, narrowband_ss_biasdark_exp_time]

        # Load up the pickled list of gains or start a new one.
        self.filter_throughput_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].alias + str(g_dev['obs'].name))

        # if self.config['filter_wheel']['filter_wheel1']['override_automatic_filter_throughputs']:
        #     plog ("Config is set to not use the automatically estimated")
        #     plog ("Filter throughputs. Starting with config throughput entries.")



        if len(self.filter_throughput_shelf)==0:
            plog ("Looks like a new filter throughput shelf.")


        else:
            plog ("Beginning stored filter throughputs")
            for filtertempgain in list(self.filter_throughput_shelf.keys()):
                plog (str(filtertempgain) + " " + str(self.filter_throughput_shelf[filtertempgain]))

        #  Pick up list of filters in sky flat order of lowest to highest transparency.
        if g_dev["fil"].null_filterwheel == True:
            plog ("No Filter Wheel, just getting non-filtered flats")
            pop_list = [0]
        else:

            # First get the list of filters from the config list.
            list_of_filters_for_this_run=[]
            for entry in g_dev['fil'].filter_data:
                list_of_filters_for_this_run.append(entry[0])
            plog (list_of_filters_for_this_run)
            if 'dark' in list_of_filters_for_this_run:
                list_of_filters_for_this_run.remove('dark')

            # Second, check that that all filters have a stored throughput value
            # If not, we will only run on those filters that have yet to get a throughput recorded
            # After we have a throughput, the sequencer should re-run a normal run with all filters

            all_throughputs_known=True
            no_throughputs_filters=[]
            for entry in list_of_filters_for_this_run:
                if not entry in self.filter_throughput_shelf.keys():
                    plog (entry + " is not in known throughputs lis. Prioritising collecting this flat.")
                    no_throughputs_filters.append(entry)
                    all_throughputs_known=False

            temp_filter_sort_dict={}

            if all_throughputs_known == False:
                for entry in no_throughputs_filters:
                    temp_filter_sort_dict[entry]= g_dev['fil'].get_starting_throughput_value(entry)
            else:
                for entry in list_of_filters_for_this_run:
                    temp_filter_sort_dict[entry]= self.filter_throughput_shelf[entry]


            # This sorts the filters by throughput. Smallest first, so appropriate for a eve flats run.
            # A future command reverses the pop_list for the morn
            temp_filter_sort_dict = dict(sorted(temp_filter_sort_dict.items(), key=lambda temp_filter_sort_dict: temp_filter_sort_dict[1]))


            pop_list = list(temp_filter_sort_dict.keys())



        #create pop list
        #breakpoint()



        #240101 WER Sometimes the throughuts can get spoiled by starting late, restarts, and the like.
        #when this happens, the throuputs get corrupt -- generally are lower. So one thing to do
        # is clamp the automatic values to say 80% to 120% of the config file values.  That will keep
        #things stable.  Second point is to make sure the input list is ordered from lowest to highest
        #throughput for evening operation.  If the flat acquisiton works the resulting gain list is
        #correct for the next run, with an exception. The throughput is a function of how bright the
        #sky is:  so something is not qite right about the scaling of the throughput.  So starting late
        #causes the automatic throughuts to be smaller than otherwise.



        # else:
        #     pop_list = self.config['filter_wheel']['filter_wheel1']['settings']['filter_sky_sort'].copy()

        #     # Check that filters are actually in the filter_list
        #     for filter_name in pop_list:
        #         filter_identified=0
        #         for match in range(
        #             len(g_dev['fil'].filter_data)
        #         ):

        #             if filter_name.lower() in str(g_dev['fil'].filter_data[match][0]).lower():
        #                 filter_identified = 1

        #         if filter_identified == 0:
        #             plog ("Could not find filter: "+str(filter_name) +" in main filter list. Removing it from flat filter list.")
        #             pop_list.remove(filter_name)

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
        collecting_area = self.config['telescope']['telescope1']['collecting_area']/31808.  #Ratio to ARO Ceravolo 300mm



        # First pointing towards flatspot
        if g_dev['mnt'].rapid_park_indicator:
            g_dev['mnt'].unpark_command({}, {})

        self.check_zenith_and_move_to_flat_spot(ending=ending)



        # Check it hasn't actually been homed this evening from the rotatorhome shelf
        homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
        if 'lasthome' in homerotator_time_shelf:
            if time.time() - homerotator_time_shelf['lasthome'] <  43200: # A home in the last twelve hours
                self.rotator_has_been_homed_this_evening=True
        homerotator_time_shelf.close()

        if not self.rotator_has_been_homed_this_evening:
            # Homing Rotator for the evening.
            try:
                while g_dev['rot'].rotator.IsMoving:
                    plog("home rotator wait")
                    time.sleep(1)
                g_dev['obs'].send_to_user("Rotator being homed to be certain of appropriate skyflat positioning.", p_level='INFO')
                time.sleep(0.5)
                g_dev['rot'].home_command({},{})
                while g_dev['rot'].rotator.IsMoving:
                    plog("home rotator wait")
                    time.sleep(1)
                # Store last home time.
                homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                homerotator_time_shelf['lasthome'] = time.time()
                homerotator_time_shelf.close()

                self.check_zenith_and_move_to_flat_spot(ending=ending)
                self.wait_for_slew()
                while g_dev['rot'].rotator.IsMoving:
                    plog("home rotator wait")
                    time.sleep(1)
                self.rotator_has_been_homed_this_evening=True
                g_dev['obs'].rotator_has_been_checked_since_last_slew = True

            except:
                #plog ("no rotator to home or wait for.")
                #g_dev['mnt']
                pass

        camera_gain_collector=[]

        # Super-duper double check that darkslide is open
        #NB this is the only reference to darkslide outside of the Camera and obs_config modules.
        if g_dev['cam'].has_darkslide:   #NB we should rename to 'has_darkslide' WER
            g_dev['cam'].openDarkslide()
            #g_dev['cam'].darkslide_open = True
            #g_dev['cam'].darkslide_state = 'Open'

        self.check_zenith_and_move_to_flat_spot(ending=ending)

        while len(pop_list) > 0  and ephem.now() < ending and g_dev['obs'].open_and_enabled_to_observe:

                # # This is just a very occasional slew to keep it pointing in the same general vicinity
                # if time.time() >= self.time_of_next_slew:
                #     if g_dev['mnt'].rapid_park_indicator:
                #         g_dev['mnt'].unpark_command({}, {})

                #     self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=True)
                #     self.time_of_next_slew = time.time() + 45

                #g_dev['obs'].request_scan_requests()
                #g_dev["obs"].request_full_update()

                if g_dev["fil"].null_filterwheel == False:
                    current_filter = pop_list[0]
                    plog("Beginning flat run for filter: " + str(current_filter))
                else:
                    current_filter='No Filter'
                    plog("Beginning flat run for filterless observation")

                sky_exposure_snap_this_filter=copy.deepcopy(sky_exposure_snap_to_grid)


                min_exposure = float(self.config['camera']['camera_1_1']['settings']['min_flat_exposure'])
                max_exposure = float(self.config['camera']['camera_1_1']['settings']['max_flat_exposure'])

                g_dev['obs'].send_to_user("\n\nBeginning flat run for filter: " + str(current_filter) )
                if (current_filter in self.filter_throughput_shelf.keys()):# and (not self.config['filter_wheel']['filter_wheel1']['override_automatic_filter_throughputs']):
                    filter_throughput=self.filter_throughput_shelf[current_filter]
                    plog ("Using stored throughput : " + str(filter_throughput))
                    known_throughput= True




                else:
                    if g_dev["fil"].null_filterwheel == False:
                        #filter_throughput = float(self.config['filter_wheel']['filter_wheel1']['flat_sky_gain'])
                        filter_throughput = g_dev["fil"].get_starting_throughput_value(current_filter)
                        plog ("Using initial attempt at a throughput : "+ str(filter_throughput))
                        plog ("Widening min and max exposure times to find a good estimate also.")
                        plog ("Normal exposure limits will return once a good throughput is found.")

                        min_exposure= float(self.config['camera']['camera_1_1']['settings']['min_exposure'])

                        max_exposure=max_exposure*3
                        flat_count=1
                        known_throughput=False
                        self.new_throughtputs_detected_in_flat_run=True

                    else:
                        filter_throughput = 150.0

                        plog ("Using initial throughput from config : "+ str(filter_throughput))
                        plog ("Widening min and max exposure times to find a good estimate also.")
                        plog ("Normal exposure limits will return once a good throughput is found.")
                        min_exposure=min_exposure*0.33
                        max_exposure=max_exposure*3
                        flat_count=1
                        known_throughput=False
                        self.new_throughtputs_detected_in_flat_run=True

                # else:
                #     if g_dev["fil"].null_filterwheel == False:
                #         filter_throughput = g_dev['fil'].return_filter_throughput({"filter": current_filter}, {})
                #     else:
                #         filter_throughput = float(self.config['filter_wheel']['filter_wheel1']['flat_sky_gain'])
                #     plog ("Using initial throughput from config : "+ str(filter_throughput))


                # Pick up previous camera_gain specific for this filter
                self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))
                try:
                    self.current_filter_last_camera_gain=self.filter_camera_gain_shelf[current_filter.lower()][0]
                    if self.filter_camera_gain_shelf[current_filter.lower()][1] > 15:
                        self.current_filter_last_camera_gain_stdev=self.filter_camera_gain_shelf[current_filter.lower()][1]
                    else:
                        self.current_filter_last_camera_gain_stdev=200
                except:
                    self.current_filter_last_camera_gain=200
                    self.current_filter_last_camera_gain_stdev=200
                self.filter_camera_gain_shelf.close()


                # If the known_throughput is false, then do not reject flats by camera gain.
                if known_throughput==False:
                    self.current_filter_last_camera_gain=200
                    self.current_filter_last_camera_gain_stdev=200

                acquired_count = 0
                flat_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]

                if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                    target_flat = 0.65 * flat_saturation_level
                else:
                    target_flat = 0.5 * flat_saturation_level

                scale = 1
                self.estimated_first_flat_exposure = False
                in_wait_mode=False

                slow_report_timer=time.time()-180

                while (acquired_count < flat_count):
                    #g_dev['obs'].request_scan_requests()
                    #g_dev["obs"].request_full_update()
                    g_dev["obs"].request_update_status()

                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Observatory closed or disabled during flat script. Cancelling out of flat acquisition loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        self.eve_sky_flat_latch = False
                        self.morn_sky_flat_latch = False
                        return

                    # Check that Flat time hasn't ended
                    if ephem.now() > ending:
                        plog ("Flat acquisition time finished. Breaking out of the flat loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        self.eve_sky_flat_latch = False
                        self.morn_sky_flat_latch = False
                        return


                    if self.next_flat_observe < time.time():
                        try:
                            sky_lux, _ = g_dev['evnt'].illuminationNow()    # NB NB Eventually we should MEASURE this.
                        except:
                            sky_lux = None


                        # MF SHIFTING EXPOSURE TIME CALCULATOR EQUATION TO BE MORE GENERAL FOR ALL TELESCOPES
                        # This bit here estimates the initial exposure time for a telescope given the skylux
                        # or given no skylux at all!
                        if self.estimated_first_flat_exposure == False:
                            self.estimated_first_flat_exposure = True
                            if sky_lux != None:

                                #pixel_area=pow(float(g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["onebyone_pix_scale"]),2)
                                if g_dev['cam'].pixscale == None:
                                    pixel_area=0.25
                                else:
                                    pixel_area=pow(float(g_dev['cam'].pixscale),2)
                                exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(filter_throughput))  #g_dev['ocn'].calc_HSI_lux)  #meas_sky_lux)
                                # snap the exposure time to a discrete grid
                                if exp_time > 0.002:
                                    exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                                else:
                                    exp_time = 0.5*min_exposure

                                new_throughput_value  =filter_throughput
                            else:
                                if morn:
                                    exp_time = 5.0
                                else:
                                    exp_time = min_exposure
                                    # snap the exposure time to a discrete grid
                                    if exp_time > 0.002:
                                        exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                                    else:
                                        exp_time = 0.5*min_exposure
                        elif in_wait_mode:
                            exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(new_throughput_value ))
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.002:
                                exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                            else:
                                exp_time = 0.5*min_exposure

                        else:
                            exp_time = scale * exp_time
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.002:
                                exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                            else:
                                exp_time = 0.5*min_exposure


                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                            self.filter_throughput_shelf.close()
                            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                            self.flats_being_collected = False
                            self.eve_sky_flat_latch = False
                            self.morn_sky_flat_latch = False
                            return

                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            self.filter_throughput_shelf.close()
                            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                            self.flats_being_collected = False
                            self.eve_sky_flat_latch = False
                            self.morn_sky_flat_latch = False
                            return


                        # Here it makes four tests and if it doesn't match those tests, then it will attempt a flat.
                        if evening and exp_time > max_exposure:
                             plog('Break because proposed evening exposure > maximum flat exposure: ' + str(max_exposure) + ' seconds:  ', exp_time)
                             pop_list.pop(0)
                             acquired_count = flat_count + 1 # trigger end of loop
                             in_wait_mode=False

                        elif morn and exp_time < min_exposure:
                             plog('Break because proposed morning exposure < minimum flat exposure time:  ', exp_time)
                             pop_list.pop(0)
                             acquired_count = flat_count + 1 # trigger end of loop
                             in_wait_mode=False

                        elif evening and exp_time < min_exposure:
                             if time.time()-slow_report_timer > 120:
                                 plog("Too bright for " + str(current_filter) + " filter, waiting. Est. Exptime: " + str(exp_time))
                                 g_dev["obs"].send_to_user("Sky is too bright for " + str(current_filter) + " filter, waiting for sky to dim. Current estimated Exposure time: " + str(round(exp_time,2)) +'s')
                                 slow_report_timer=time.time()
                                 in_wait_mode=True

                             #exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(new_throughput_value ))

                             #self.estimated_first_flat_exposure = False
                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=True)

                                self.time_of_next_slew = time.time() + 45
                             self.next_flat_observe = time.time() + 5
                        elif morn and exp_time > max_exposure :
                             if time.time()-slow_report_timer > 120:
                                 plog("Too dim for " + str(current_filter) + " filter, waiting. Est. Exptime:  " + str(exp_time))
                                 g_dev["obs"].send_to_user("Sky is too dim for " + str(current_filter) + " filter, waiting for sky to brighten. Current estimated Exposure time: " + str(round(exp_time,2))+'s')
                                 slow_report_timer=time.time()
                                 in_wait_mode=True
                             #self.estimated_first_flat_exposure = False
                             #exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(new_throughput_value ))

                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=True)

                                self.time_of_next_slew = time.time() + 45
                             self.next_flat_observe = time.time() + 5
                             exp_time = min_exposure
                             # snap the exposure time to a discrete grid
                             if exp_time > 0.002:
                                 exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                             else:
                                 exp_time = 0.5*min_exposure

                        else:
                            in_wait_mode=False
                            exp_time = round(exp_time, 5)
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.002:
                                exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                            else:
                                exp_time = 0.5*min_exposure


                            # If scope has gone to bed due to inactivity, wake it up!
                            if g_dev['mnt'].rapid_park_indicator:
                                g_dev['mnt'].unpark_command({}, {})
                                self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=True)

                                self.time_of_next_slew = time.time() + 45

                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                return
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                return

                            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'sky flat', 'script': 'On'}

                            if g_dev["fil"].null_filterwheel == False:
                                opt = { 'count': 1, 'filter': current_filter}
                            else:
                                opt = { 'count': 1, }

                            if ephem.now() >= ending:
                                if morn: # This needs to be here because some scopes do not do morning bias and darks
                                    try:
                                        g_dev['mnt'].park_command({}, {})
                                    except:
                                        plog("Mount did not park at end of morning skyflats.")
                                self.filter_throughput_shelf.close()
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
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

                                # If there is a rotator, give it a second
                                # to settle down after rotation complete
                                if g_dev['rot'] != None:
                                    time.sleep(1)

                                fred = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, do_sep = False,skip_daytime_check=True)
                                #breakpoint()
                                try:
                                    if self.stop_script_called:
                                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        self.eve_sky_flat_latch = False
                                        self.morn_sky_flat_latch = False
                                        return

                                    if not g_dev['obs'].open_and_enabled_to_observe:
                                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        self.eve_sky_flat_latch = False
                                        self.morn_sky_flat_latch = False
                                        return

                                except Exception as e:
                                    plog ('something funny in stop_script still',e)



                                if fred == 'roofshut' :
                                    plog ("roof was shut during flat period, cancelling out of flat scripts")
                                    g_dev["obs"].send_to_user("Roof shut during sky flats. Stopping sky_flats")
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    self.eve_sky_flat_latch = False
                                    self.morn_sky_flat_latch = False
                                    return

                                if fred == 'blockend':
                                    plog ("blockend detected during flat period, cancelling out of flat scripts")
                                    g_dev["obs"].send_to_user("Roof shut during sky flats. Stopping sky_flats")
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    self.eve_sky_flat_latch = False
                                    self.morn_sky_flat_latch = False
                                    return

                                if g_dev["obs"].stop_all_activity:
                                    plog('stop_all_activity cancelling out of exposure loop')
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    self.eve_sky_flat_latch = False
                                    self.morn_sky_flat_latch = False
                                    return

                                try:
                                    bright = fred['patch']
                                except:
                                    bright = None
                                    plog ("patch broken?")
                                    plog(traceback.format_exc())
                                    plog (fred)
                                   #breakpoint()


                            except Exception as e:
                                plog('Failed to get a flat image: ', e)
                                plog(traceback.format_exc())
                                #g_dev["obs"].request_full_update()
                                continue

                            #g_dev['obs'].request_scan_requests()
                            #g_dev["obs"].request_full_update()

                            try:
                                scale = target_flat / bright
                            except:
                                scale = 1.0



                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                return

                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                return

                            got_a_flat_this_round=False
                            # If camera has not already rejected taking the image
                            # usually because the temperature isn't cold enough.
                            if not bright == None:

                                if g_dev["fil"].null_filterwheel == False:
                                    if sky_lux != None:
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        plog(current_filter,' New Throughput Value: ', round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3), '\n\n')
                                        new_throughput_value = round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3)
                                    else:
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        plog(current_filter,' New Throughput Value: ', round(bright/(collecting_area*pixel_area*exp_time), 3), '\n\n')
                                        new_throughput_value = round(bright/(collecting_area*pixel_area*exp_time), 3)

                                else:
                                    if sky_lux != None:
                                        try:

                                            plog('New Throughput Value: ', round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3), '\n\n')
                                        except:
                                            plog ("this seems to be a bug that occurs when the temperature is out of range, here is a breakpoint for you to test it")
                                            breakpoint()
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        new_throughput_value = round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3)
                                    else:
                                        plog('New Throughput Value: ', round(bright/(collecting_area*pixel_area*exp_time), 3), '\n\n')
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        new_throughput_value = round(bright/(collecting_area*pixel_area*exp_time), 3)

                                if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:

                                    if (
                                        bright
                                        <= 0.8* flat_saturation_level and

                                        bright
                                        >= 0.5 * flat_saturation_level
                                    ):
                                        acquired_count += 1
                                        got_a_flat_this_round=True
                                        self.filter_throughput_shelf[current_filter]=new_throughput_value
                                        try:
                                            camera_gain_collector.append(fred["camera_gain"])
                                        except:
                                            plog ("camera gain not avails")
                                    elif morn and (bright > (flat_saturation_level * 0.8)) and (old_throughput_value/new_throughput_value > 0.95) and (old_throughput_value/new_throughput_value < 1.05):
                                        plog ("Morning and overexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)

                                    elif not morn and (bright < (flat_saturation_level * 0.5)) and 0.95 < old_throughput_value/new_throughput_value < 1.05:
                                        plog ("Evening and underexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)

                                else:
                                    if (
                                        bright
                                        <= 0.75* flat_saturation_level and

                                        bright
                                        >= 0.25 * flat_saturation_level
                                    ):
                                        acquired_count += 1
                                        got_a_flat_this_round=True
                                        self.filter_throughput_shelf[current_filter]=new_throughput_value
                                        try:
                                            camera_gain_collector.append(fred["camera_gain"])
                                        except:
                                            plog ("camera gain not avails")
                                    elif morn and ( bright > (flat_saturation_level * 0.75)) and 0.95 < old_throughput_value/new_throughput_value < 1.05:
                                        plog ("Morning and overexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)

                                    elif not morn and (bright < (flat_saturation_level * 0.25)) and 0.95 < old_throughput_value/new_throughput_value < 1.05:
                                        plog ("Evening and underexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)


                            if bright == None:
                                plog ("Seems like the camera isn't liking taking flats. This is usually because it hasn't been able to cool sufficiently, bailing out of flats. ")

                                acquired_count += 1 # trigger end of loop


                            if acquired_count == flat_count or acquired_count > flat_count:
                                pop_list.pop(0)
                                scale = 1
                            elif got_a_flat_this_round: # Only nudge if you got a good flat. No point otherwise.
                                # Give it a bit of a nudge, not necessary if it is the last shot of the filter.
                                # There is no reason to wait for it to finish slewing either.
                                self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=True)


                            continue
                    else:
                        time.sleep(1)

        if morn:
            self.morn_sky_flat_latch = False
        else:
            self.eve_sky_flat_latch = False

        textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.txt'
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

        # Park scope at the end of flats but not if it is just about to do another run.
        if not self.new_throughtputs_detected_in_flat_run:
            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
            plog ("Scope parked at the end of flats.")

        if morn:
            self.morn_flats_done = True
        else:
            self.eve_flats_done = True

        self.flats_being_collected = False
        self.eve_sky_flat_latch = False
        self.morn_sky_flat_latch = False




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
        #g_dev["obs"].request_full_update()
        g_dev['obs'].request_scan_requests()
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        time.sleep(5)
        #g_dev["obs"].request_full_update()
        g_dev['obs'].request_scan_requests()
        #Here we need to switch off any IR or dome lighting.
        #Take a 10 s dark screen air flat to record ambient
        # Park Telescope
        req = {'time': exp_time,  'alias': camera_name, 'image_type': 'screen flat'}
        opt = {'count': dark_count, 'filter': 'dark', 'hint': 'screen dark'}  #  air has highest throughput

        result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
            return
        plog('First dark 30-sec patch, filter = "air":  ', result['patch'])
        # g_dev['scr'].screen_light_on()

        for filt in g_dev['fil'].filter_screen_sort:
            #enter with screen dark
            g_dev['obs'].request_scan_requests()
            filter_number = int(filt)
            plog(filter_number, g_dev['fil'].filter_data[filter_number][0])
            screen_setting = g_dev['fil'].filter_data[filter_number][4][1]
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            exp_time  = g_dev['fil'].filter_data[filter_number][4][0]
            g_dev['obs'].request_scan_requests()
            #g_dev["obs"].request_full_update()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen pre-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                return
            plog("Dark Screen flat, starting:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            #g_dev["obs"].request_full_update()
            plog('Lighted Screen; filter, bright:  ', filter_number, screen_setting)
            g_dev['scr'].set_screen_bright(int(screen_setting))
            g_dev['scr'].screen_light_on()
            time.sleep(10)
            # #g_dev["obs"].request_full_update()
            # time.sleep(10)
            # #g_dev["obs"].request_full_update()
            # time.sleep(10)
            g_dev['obs'].request_scan_requests()
            #g_dev["obs"].request_full_update()
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = {'count': flat_count, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen filter light'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                return
            # if no exposure, wait 10 sec
            plog("Lighted Screen flat:  ", result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')
            g_dev['obs'].request_scan_requests()
            #g_dev["obs"].request_full_update()
            g_dev['scr'].set_screen_bright(0)
            g_dev['scr'].screen_dark()
            time.sleep(5)
            g_dev['obs'].request_scan_requests()
            #g_dev["obs"].request_full_update()
            plog('Dark Screen; filter, bright:  ', filter_number, 0)
            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'screen flat'}
            opt = { 'count': 1, 'filter': g_dev['fil'].filter_data[filter_number][0], 'hint': 'screen post-filter dark'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, skip_open_check=True,skip_daytime_check=True)
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                return
            plog("Dark Screen flat, ending:  ",result['patch'], g_dev['fil'].filter_data[filter_number][0], '\n\n')


            #
        g_dev['scr'].set_screen_bright(0)
        g_dev['scr'].screen_dark()
        #g_dev["obs"].request_full_update()
        g_dev['mnt'].set_tracking_off()   #park_command({}, {})
        plog('Sky Flat sequence completed, Telescope tracking is off.')


        g_dev['mnt'].park_command({}, {})



    def filter_focus_offset_estimator_script(self):

        plog ("Determining offsets between filters")

        plog ("First doing a normal run on the 'focus' filter first")


        # Slewing to a relatively random high spot
        g_dev['mnt'].go_command(alt=75,az= 270)

        req2 = {'target': 'near_tycho_star'}
        opt = {}
        foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, filter_choice='focus')

        plog ("focus position: " + str(foc_pos))
        plog ("focus fwhm: " + str(foc_fwhm))

        if np.isnan(foc_pos):
            plog ("initial focus on offset run failed, giving it another shot after extensive focus attempt.")
            foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, filter_choice='focus')

            plog ("focus position: " + str(foc_pos))
            plog ("focus fwhm: " + str(foc_fwhm))
            if np.isnan(foc_pos):
                plog ("Second initial focus on offset run failed, we really need a very good initial estimate, so bailing out.")

                return

        focus_filter_focus_point=foc_pos

        # First get the list of filters from the config list.
        list_of_filters_for_this_run=[]
        for entry in g_dev['fil'].filter_data:
            list_of_filters_for_this_run.append(entry[0])
        plog(list_of_filters_for_this_run)
        if 'dark' in list_of_filters_for_this_run:
            list_of_filters_for_this_run.remove('dark')


        filter_offset_collector={}

        for chosen_filter in list_of_filters_for_this_run:
            plog ("Running offset test for " + str(chosen_filter))
            foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, begin_at=focus_filter_focus_point, filter_choice=chosen_filter)
            plog ("focus position: " + str(foc_pos))
            plog ("focus fwhm: " + str(foc_fwhm))

            if np.isnan(foc_pos):
                plog ("initial focus on offset run failed, giving it another shot after extensive focus attempt.")
                foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=chosen_filter)

                plog ("focus position: " + str(foc_pos))
                plog ("focus fwhm: " + str(foc_fwhm))
                if np.isnan(foc_pos):
                    plog ("Second attempt on offset run failed, couldn't update the offset for this filter.")


            if not np.isnan(foc_pos):
                filter_offset_collector[chosen_filter]=focus_filter_focus_point-foc_pos
                filteroffset_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filteroffsets_' + g_dev['cam'].alias + str(g_dev['obs'].name))
                filteroffset_shelf[chosen_filter]=focus_filter_focus_point-foc_pos
                g_dev['fil'].filter_offsets[chosen_filter]=focus_filter_focus_point-foc_pos
                filteroffset_shelf.close()

        plog ("Final determined offsets this run")
        plog (filter_offset_collector)
        plog ("Current filter offset shelf")
        filteroffset_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filteroffsets_' + g_dev['cam'].alias + str(g_dev['obs'].name))
        #plog (filteroffset_shelf)
        for filtername in filteroffset_shelf:
            plog (str(filtername) + " " + str(filteroffset_shelf[filtername]))
        filteroffset_shelf.close()

        #breakpoint()
        self.auto_focus_script(req2, opt,skip_pointing=True)


    def auto_focus_script(self, req, opt, throw=None, begin_at=None, skip_timer_check=False, dont_return_scope=False, dont_log_focus=False, skip_pointing=False, extensive_focus=None, filter_choice='focus'):
     
        self.focussing=True


        if throw==None:
            throw= self.config['focuser']['focuser1']['throw']

        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING AUTO FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An auto focus was rejected as it is during the daytime.")
            self.focussing=False
            return np.nan, np.nan

        # First check how long it has been since the last focus
        plog ("Time of last focus")
        plog (g_dev['foc'].time_of_last_focus)
        plog ("Time since last focus")
        plog (datetime.datetime.now() - g_dev['foc'].time_of_last_focus)


        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
            self.focussing=False
            return np.nan, np.nan
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
            self.focussing=False
            return np.nan, np.nan


        plog ("Threshold time between auto focus routines (hours)")
        plog (self.config['periodic_focus_time'])

        if skip_timer_check == False:
            if ((datetime.datetime.utcnow() - g_dev['foc'].time_of_last_focus)) > datetime.timedelta(hours=self.config['periodic_focus_time']):
                plog ("Sufficient time has passed since last focus to do auto_focus")

            else:
                plog ("too soon since last autofocus")
                self.focussing=False
                return np.nan, np.nan


        g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow()

        # Reset focus tracker
        g_dev['foc'].focus_tracker = [np.nan] * 1000

        throw = g_dev['foc'].throw

        self.af_guard = True

        req2 = copy.deepcopy(req)

        #unpark before anything else.
        position_after_unpark=False
        if g_dev['mnt'].rapid_park_indicator:
            position_after_unpark=True
        g_dev['mnt'].unpark_command({}, {})
        if position_after_unpark:
            g_dev['mnt'].go_command(alt=70,az= 70)
            g_dev['mnt'].set_tracking_on()



        sim = False
        start_ra = g_dev['mnt'].return_right_ascension()   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
        start_dec = g_dev['mnt'].return_declination()
        #focus_start = g_dev['foc'].current_focus_position

        if not begin_at is None:
            focus_start = begin_at  #In this case we start at a place close to a 3 point minimum.
        elif not extensive_focus == None:
            focus_start=extensive_focus
        else:
            focus_start=g_dev['foc'].current_focus_position
        foc_pos0 = focus_start

        #breakpoint()
        #
# =============================================================================
# =============================================================================
# =============================================================================
        plog("Saved  *mounting* ra, dec, focus:  ", start_ra, start_dec, focus_start)

        if not skip_pointing:
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

            g_dev['obs'].request_scan_requests()
            g_dev['obs'].send_to_user("Slewing to a focus field", p_level='INFO')
            try:
                plog("\nGoing to near focus patch of " + str(int(focus_patch_n)) + " 9th to 12th mag stars " + str(d2d.deg[0]) + "  degrees away.\n")
                g_dev['mnt'].go_command(ra=focus_patch_ra, dec=focus_patch_dec)
            except Exception as e:
                plog ("Issues pointing to a focus patch. Focussing at the current pointing." , e)
                plog(traceback.format_exc())
            #g_dev["obs"].request_full_update()
            req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

            opt = { 'count': 1, 'filter': 'focus'}


            result = {}


            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                self.focussing=False
                return np.nan, np.nan

            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                return np.nan, np.nan


            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)


            # If no extensive_focus has been done, centre the focus field.
            if extensive_focus == None:
                g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')

                result = self.centering_exposure(no_confirmation=True, try_hard=True)#), try_forever=True)
                # Wait for platesolve
                reported=0
                temptimer=time.time()
                while True:
                    if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                        break
                    else:
                        if reported ==0:
                            plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                            reported=1
                        if (time.time() - temptimer) > 20:
                            #g_dev["obs"].request_full_update()
                            temptimer=time.time()
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                            self.focussing=False
                            return np.nan, np.nan
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            self.focussing=False
                            return np.nan, np.nan
                        pass

                g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')


        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
            self.focussing=False
            return np.nan, np.nan
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
            self.focussing=False
            return np.nan, np.nan



        g_dev['obs'].request_scan_requests()
        #g_dev["obs"].request_full_update()

        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')
        req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

        opt = { 'count': 1, 'filter': filter_choice}

        g_dev['foc'].guarded_move((foc_pos0 - 0* throw)*g_dev['foc'].micron_to_steps)   # NB added 20220209 Nasty bug, varies with prior state


        # THE LOOP
        position_counter=0 # At various stages of the algorithm we attempt different things, this allows us to make that happen.
        central_starting_focus=copy.deep_copy(foc_pos0)
        
        
        focus_spots=[]
        #focus_fwhms=[]
        
        while True:
            position_counter=position_counter+1
            # General command bailout section
            g_dev['obs'].request_scan_requests()
            if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                    self.focussing=False
                    return np.nan, np.nan
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                return np.nan, np.nan

            # What focus position should i be using?
            if position_counter==1:
                focus_position_this_loop=central_starting_focus
            elif position_counter==2:
                focus_position_this_loop=central_starting_focus - throw
            elif position_counter==3:
                focus_position_this_loop=central_starting_focus - 2* throw
            elif position_counter==4:
                focus_position_this_loop=central_starting_focus + throw
            elif position_counter==5:
                focus_position_this_loop=central_starting_focus + 2* throw
            elif position_counter>5:
                focus_position_this_loop=new_focus_position_to_attempt
            
            #  If more than 10 attempts, fail and bail out.
            if position_counter > 10:
                
                if extensive_focus == None:

                    plog('Autofocus quadratic equation did not converge. Moving back to starting focus:  ', focus_start)
                    plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
                    g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus routine')

                    req2 = {'target': 'near_tycho_star', 'image_type': 'focus'}
                    opt = {'filter': filter_choice}
                    g_dev['seq'].extensive_focus_script(req2,opt,dont_return_scope=dont_return_scope, begin_at=focus_start, no_auto_after_solve=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=filter_choice)
                    if not dont_return_scope:

                        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                        g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                        self.wait_for_slew()
                    self.focussing=False
                    return np.nan, np.nan
                else:
                    plog('Autofocus quadratic equation did not converge. Moving back to extensive focus:  ', extensive_focus)
                    g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ' + str(extensive_focus))

                    g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)

                    g_dev['foc'].last_known_focus=(extensive_focus)
                    #g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)


                    self.af_guard = False
                    if not dont_return_scope:

                        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                        g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)   #NB NB Does this really take us back to starting point?
                        self.wait_for_slew()

                    self.af_guard = False
                    self.focussing=False
                    return np.nan, np.nan
            
            
            spot=np.nan
            
            while np.isnan(spot):
                # Move the focuser
                g_dev['foc'].guarded_move((focus_position_this_loop)*g_dev['foc'].micron_to_steps)
    
                # Take the shot
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
                
                spot = g_dev['obs'].fwhmresult['FWHM']
                foc_pos=g_dev['foc'].current_focus_position
                
                g_dev['obs'].send_to_user("Focus position:" + str(focus_position_this_loop) + " FWHM: " + str(spot), p_level='INFO')
                
                if not np.isnan(spot):
                    focus_spots.append((foc_pos,spot))
                    #focus_fwhms.append(spot)
                    
            # If you have the starting of a v-curve then now you can decide what to do.
            if position_counter >=5:
                
                # If the minimum is at one side of the v curve take another point beyond that point, otherwise try to fit a parabola
                
                print ("blah")
                # Start off by sorting in order of focus positions
                
                # If you can fit a parabola, then you've got the focus
                # If fit, then break
                
                x = list()
                y = list()
                for i in focus_spots:
                    x.append(i[0])
                    y.append(i[1])
                
                fit = np.polyfit(x, y, 2)
                f = np.poly1d(fit)
                
                plt.scatter(x,y)
                plt.plot(x,f(x))
                #plt.xlim(0.16888549099999922 - 0.000000001,0.1688855399999992 + 0.000000001)
                plt.show()
                
                breakpoint()
            
            
                # If successful, then move to focus and live long and prosper
                solved_focus_position=1
                solved_focus_fwhm=1
                plog ('Moving to Solved focus:  ', round(solved_focus_position, 2), ' calculated:  ',  solved_focus_fwhm)

                pos = int(solved_focus_position*g_dev['foc'].micron_to_steps)
                g_dev['foc'].guarded_move(pos)

                g_dev['foc'].last_known_focus = solved_focus_position
                g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)
                
                if not dont_return_scope:
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                    self.wait_for_slew()

            
                self.af_guard = False
                self.focussing=False
                return solved_focus_position, solved_focus_fwhm
            

                



                # If not, where are you? and which way do you go?
                if True:
                    # If both ends are > 5 arcseconds out, then start hunting around the minimum value
                    
                    new_focus_position_to_attempt=1
                
                    # Else add a point to the "lowest end" as long as it is not larger than 5 arcseconds out.
                    
                    new_focus_position_to_attempt=1
                    
                    
                    
                
                
                
    
                






        # rot_report=0
        # while g_dev['foc'].is_moving():
        # #     if rot_report == 0:
        # #         plog('Waiting for Focuser to shift.\n')
        # #         rot_report =1
        # #     time.sleep(0.2)



        
        # retry = 0
        # while retry < 3:
        #     if not sim:
        #         g_dev['obs'].request_scan_requests()
        #         #g_dev["obs"].request_full_update()
        #         result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
                
        #     else:

        #         g_dev['obs'].fwhmresult['FWHM'] = 3
        #         g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position

        #     try:
        #         spot1 = g_dev['obs'].fwhmresult['FWHM']
        #         #foc_pos1 = g_dev['obs'].fwhmresult['mean_focus']
        #         foc_pos1=g_dev['foc'].current_focus_position
        #     except:
        #         spot1 = False
        #         foc_pos1 = False
        #         plog ("spot1 failed in autofocus script")
        #         #plog(traceback.format_exc())
        #         #breakpoint()
        #     #breakpoint()
        #     plog (spot1)
        #     g_dev['obs'].send_to_user("Central focus FWHM: " + str(spot1), p_level='INFO')

        #     if math.isnan(spot1) or spot1 ==False:

        #         retry += 1
        #         plog("Retry of central focus star)")
        #         #breakpoint()
        #         continue
        #     else:
        #         break
        # plog('Autofocus Moving In.\n\n')

        # g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)

        # if not sim:
        #     g_dev['obs'].request_scan_requests()
        #     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
        #     if self.stop_script_called:
        #         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
        #         self.focussing=False
        #         return np.nan, np.nan
        #     if not g_dev['obs'].open_and_enabled_to_observe:
        #         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
        #         self.focussing=False
        #         return np.nan, np.nan
        # else:
        #     g_dev['obs'].fwhmresult['FWHM'] = 4
        #     g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
        # try:
        #     spot2 = g_dev['obs'].fwhmresult['FWHM']
        #     foc_pos2 = g_dev['foc'].current_focus_position
        # except:
        #     spot2 = False
        #     foc_pos2 = False
        #     plog ("spot2 failed on autofocus moving in")

        # g_dev['obs'].send_to_user("Inward focus FWHM: " + str(spot2), p_level='INFO')

        # plog('Autofocus Overtaveling Out.\n\n')
        # g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
        # plog('Autofocus Moving back in half-way.\n\n')
        # #this is to overcoma any gravity induced backlash
        # g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)

        # if not sim:
        #     g_dev['obs'].request_scan_requests()
        #     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
        #     if self.stop_script_called:
        #         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
        #         self.focussing=False
        #         return np.nan, np.nan
        #     if not g_dev['obs'].open_and_enabled_to_observe:
        #         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
        #         self.focussing=False
        #         return np.nan, np.nan
        # else:
        #     g_dev['obs'].fwhmresult['FWHM'] = 4.5
        #     g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
        # try:
        #     spot3 = g_dev['obs'].fwhmresult['FWHM']
        #     foc_pos3 = g_dev['foc'].current_focus_position
        # except:
        #     spot3 = False
        #     foc_pos3 = False
        #     plog ("spot3 failed on autofocus moving in")

        # g_dev['obs'].send_to_user("Outward focus FWHM: " + str(spot3), p_level='INFO')

        # x = [foc_pos2, foc_pos1, foc_pos3]
        # y = [spot2, spot1, spot3]
        # plog('X, Y:  ', x, y, 'Desire center to be smallest.')


#     def auto_focus_script(self, req, opt, throw=None, begin_at=None, skip_timer_check=False, dont_return_scope=False, dont_log_focus=False, skip_pointing=False, extensive_focus=None, filter_choice='focus'):
#         '''
#         V curve is a big move focus designed to fit two lines adjacent to the more normal focus curve.
#         It finds the approximate focus, particulary for a new instrument. It requires 8 points plus
#         a verify.
#         Auto focus consists of three points plus a verify.
#         Fine focus consists of five points plus a verify.
#         Optionally individual images can be multiples of one to average out seeing.
#         NBNBNB This code needs to go to known stars to be moe relaible and permit subframes
#         # Result format:
#         #                 result['mean_focus'] = avg_foc[1]
#         #                 result['mean_rotation'] = avg_rot[1]
#         #                 result['FWHM'] = spot   What is returned is a close proxy to real fitted FWHM.
#         #                 result['half_FD'] = None
#         #                 result['patch'] = cal_result
#         #                 result['temperature'] = avg_foc[2]  This is probably tube not reported by Gemini.

#         returns foc_pos - the focus position and foc_fwhm - the estimated fwhm
#         '''

#         self.focussing=True


#         if throw==None:
#             throw= self.config['focuser']['focuser1']['throw']

#         if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
#             (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
#             plog ("NOT DOING AUTO FOCUS -- IT IS THE DAYTIME!!")
#             g_dev["obs"].send_to_user("An auto focus was rejected as it is during the daytime.")
#             self.focussing=False
#             return np.nan, np.nan

#         # First check how long it has been since the last focus
#         plog ("Time of last focus")
#         plog (g_dev['foc'].time_of_last_focus)
#         plog ("Time since last focus")
#         plog (datetime.datetime.now() - g_dev['foc'].time_of_last_focus)


#         if self.stop_script_called:
#             g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#             self.focussing=False
#             return np.nan, np.nan
#         if not g_dev['obs'].open_and_enabled_to_observe:
#             g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#             self.focussing=False
#             return np.nan, np.nan


#         plog ("Threshold time between auto focus routines (hours)")
#         plog (self.config['periodic_focus_time'])

#         if skip_timer_check == False:
#             if ((datetime.datetime.utcnow() - g_dev['foc'].time_of_last_focus)) > datetime.timedelta(hours=self.config['periodic_focus_time']):
#                 plog ("Sufficient time has passed since last focus to do auto_focus")

#             else:
#                 plog ("too soon since last autofocus")
#                 self.focussing=False
#                 return np.nan, np.nan


#         g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow()

#         # Reset focus tracker
#         g_dev['foc'].focus_tracker = [np.nan] * 1000

#         throw = g_dev['foc'].throw

#         self.af_guard = True

#         req2 = copy.deepcopy(req)

#         #unpark before anything else.
#         position_after_unpark=False
#         if g_dev['mnt'].rapid_park_indicator:
#             position_after_unpark=True
#         g_dev['mnt'].unpark_command({}, {})
#         if position_after_unpark:
#             g_dev['mnt'].go_command(alt=70,az= 70)
#             g_dev['mnt'].set_tracking_on()



#         sim = False
#         start_ra = g_dev['mnt'].return_right_ascension()   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
#         start_dec = g_dev['mnt'].return_declination()
#         #focus_start = g_dev['foc'].current_focus_position

#         if not begin_at is None:
#             focus_start = begin_at  #In this case we start at a place close to a 3 point minimum.
#         elif not extensive_focus == None:
#             focus_start=extensive_focus
#         else:
#             focus_start=g_dev['foc'].current_focus_position
#         foc_pos0 = focus_start

#         #breakpoint()
#         #
# # =============================================================================
# # =============================================================================
# # =============================================================================
#         plog("Saved  *mounting* ra, dec, focus:  ", start_ra, start_dec, focus_start)

#         if not skip_pointing:
#             # Trim catalogue so that only fields 45 degrees altitude are in there.
#             self.focus_catalogue_skycoord= SkyCoord(ra = self.focus_catalogue[:,0]*u.deg, dec = self.focus_catalogue[:,1]*u.deg)
#             aa = AltAz (location=g_dev['mnt'].site_coordinates, obstime=Time.now())
#             self.focus_catalogue_altitudes=self.focus_catalogue_skycoord.transform_to(aa)
#             above_altitude_patches=[]

#             for ctr in range(len(self.focus_catalogue_altitudes)):
#                 if self.focus_catalogue_altitudes[ctr].alt /u.deg > 45.0:
#                     above_altitude_patches.append([self.focus_catalogue[ctr,0], self.focus_catalogue[ctr,1], self.focus_catalogue[ctr,2]])
#             above_altitude_patches=np.asarray(above_altitude_patches)
#             self.focus_catalogue_skycoord= SkyCoord(ra = above_altitude_patches[:,0]*u.deg, dec = above_altitude_patches[:,1]*u.deg)

#             # d2d of the closest field.
#             teststar = SkyCoord(ra = g_dev['mnt'].current_icrs_ra*15*u.deg, dec = g_dev['mnt'].current_icrs_dec*u.deg)
#             idx, d2d, _ = teststar.match_to_catalog_sky(self.focus_catalogue_skycoord)

#             focus_patch_ra=above_altitude_patches[idx,0] /15
#             focus_patch_dec=above_altitude_patches[idx,1]
#             focus_patch_n=above_altitude_patches[idx,2]

#             g_dev['obs'].request_scan_requests()
#             g_dev['obs'].send_to_user("Slewing to a focus field", p_level='INFO')
#             try:
#                 plog("\nGoing to near focus patch of " + str(int(focus_patch_n)) + " 9th to 12th mag stars " + str(d2d.deg[0]) + "  degrees away.\n")
#                 g_dev['mnt'].go_command(ra=focus_patch_ra, dec=focus_patch_dec)
#             except Exception as e:
#                 plog ("Issues pointing to a focus patch. Focussing at the current pointing." , e)
#                 plog(traceback.format_exc())
#             #g_dev["obs"].request_full_update()
#             req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

#             opt = { 'count': 1, 'filter': 'focus'}


#             result = {}


#             if self.stop_script_called:
#                 g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                 self.focussing=False
#                 return np.nan, np.nan

#             if not g_dev['obs'].open_and_enabled_to_observe:
#                 g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                 self.focussing=False
#                 return np.nan, np.nan


#             g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)


#             # If no extensive_focus has been done, centre the focus field.
#             if extensive_focus == None:
#                 g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')

#                 result = self.centering_exposure(no_confirmation=True, try_hard=True)#), try_forever=True)
#                 # Wait for platesolve
#                 reported=0
#                 temptimer=time.time()
#                 while True:
#                     if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
#                         break
#                     else:
#                         if reported ==0:
#                             plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
#                             reported=1
#                         if (time.time() - temptimer) > 20:
#                             #g_dev["obs"].request_full_update()
#                             temptimer=time.time()
#                         if self.stop_script_called:
#                             g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                             self.focussing=False
#                             return np.nan, np.nan
#                         if not g_dev['obs'].open_and_enabled_to_observe:
#                             g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                             self.focussing=False
#                             return np.nan, np.nan
#                         pass

#                 g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')


#         if self.stop_script_called:
#             g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#             self.focussing=False
#             return np.nan, np.nan
#         if not g_dev['obs'].open_and_enabled_to_observe:
#             g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#             self.focussing=False
#             return np.nan, np.nan



#         # rot_report=0
#         # while g_dev['foc'].is_moving():
#         #     if rot_report == 0:
#         #         plog('Waiting for Focuser to shift.\n')
#         #         rot_report =1
#         #     time.sleep(0.2)


#         g_dev['obs'].request_scan_requests()
#         #g_dev["obs"].request_full_update()

#         plog('Autofocus Starting at:  ', foc_pos0, '\n\n')
#         req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config

#         opt = { 'count': 1, 'filter': filter_choice}

#         g_dev['foc'].guarded_move((foc_pos0 - 0* throw)*g_dev['foc'].micron_to_steps)   # NB added 20220209 Nasty bug, varies with prior state

#         retry = 0
#         while retry < 3:
#             if not sim:
#                 g_dev['obs'].request_scan_requests()
#                 #g_dev["obs"].request_full_update()
#                 result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
#                 if self.stop_script_called:
#                     g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                     self.focussing=False
#                     return np.nan, np.nan
#                 if not g_dev['obs'].open_and_enabled_to_observe:
#                     g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                     self.focussing=False
#                     return np.nan, np.nan

#             else:

#                 g_dev['obs'].fwhmresult['FWHM'] = 3
#                 g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position

#             try:
#                 spot1 = g_dev['obs'].fwhmresult['FWHM']
#                 #foc_pos1 = g_dev['obs'].fwhmresult['mean_focus']
#                 foc_pos1=g_dev['foc'].current_focus_position
#             except:
#                 spot1 = False
#                 foc_pos1 = False
#                 plog ("spot1 failed in autofocus script")
#                 #plog(traceback.format_exc())
#                 #breakpoint()
#             #breakpoint()
#             plog (spot1)
#             g_dev['obs'].send_to_user("Central focus FWHM: " + str(spot1), p_level='INFO')

#             if math.isnan(spot1) or spot1 ==False:

#                 retry += 1
#                 plog("Retry of central focus star)")
#                 #breakpoint()
#                 continue
#             else:
#                 break
#         plog('Autofocus Moving In.\n\n')

#         g_dev['foc'].guarded_move((foc_pos0 - 1*throw)*g_dev['foc'].micron_to_steps)

#         if not sim:
#             g_dev['obs'].request_scan_requests()
#             result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
#             if self.stop_script_called:
#                 g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                 self.focussing=False
#                 return np.nan, np.nan
#             if not g_dev['obs'].open_and_enabled_to_observe:
#                 g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                 self.focussing=False
#                 return np.nan, np.nan
#         else:
#             g_dev['obs'].fwhmresult['FWHM'] = 4
#             g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#         try:
#             spot2 = g_dev['obs'].fwhmresult['FWHM']
#             foc_pos2 = g_dev['foc'].current_focus_position
#         except:
#             spot2 = False
#             foc_pos2 = False
#             plog ("spot2 failed on autofocus moving in")

#         g_dev['obs'].send_to_user("Inward focus FWHM: " + str(spot2), p_level='INFO')

#         plog('Autofocus Overtaveling Out.\n\n')
#         g_dev['foc'].guarded_move((foc_pos0 + 2*throw)*g_dev['foc'].micron_to_steps)
#         plog('Autofocus Moving back in half-way.\n\n')
#         #this is to overcoma any gravity induced backlash
#         g_dev['foc'].guarded_move((foc_pos0 + throw)*g_dev['foc'].micron_to_steps)

#         if not sim:
#             g_dev['obs'].request_scan_requests()
#             result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
#             if self.stop_script_called:
#                 g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                 self.focussing=False
#                 return np.nan, np.nan
#             if not g_dev['obs'].open_and_enabled_to_observe:
#                 g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                 self.focussing=False
#                 return np.nan, np.nan
#         else:
#             g_dev['obs'].fwhmresult['FWHM'] = 4.5
#             g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#         try:
#             spot3 = g_dev['obs'].fwhmresult['FWHM']
#             foc_pos3 = g_dev['foc'].current_focus_position
#         except:
#             spot3 = False
#             foc_pos3 = False
#             plog ("spot3 failed on autofocus moving in")

#         g_dev['obs'].send_to_user("Outward focus FWHM: " + str(spot3), p_level='INFO')

#         x = [foc_pos2, foc_pos1, foc_pos3]
#         y = [spot2, spot1, spot3]
#         plog('X, Y:  ', x, y, 'Desire center to be smallest.')



#         if spot1 is None or spot2 is None or spot3 is None or spot1 == False or spot2 == False or spot3 == False:  #New additon to stop crash when no spots
#             plog("Autofocus was not successful. Returning to original focus setting and pointing.")
#             g_dev['obs'].send_to_user("Autofocus was not successful. Returning to original focus setting and pointing.")

#             g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)  #NB NB 20221002 THis unit fix shoudl be in the routine. WER

#             if not dont_return_scope:

#                 g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#                 #g_dev["obs"].request_full_update()
#                 self.wait_for_slew()

#             self.af_guard = False
#             self.focussing=False
#             return np.nan, np.nan
#         elif spot1 < spot2 and spot1 < spot3:
#             try:
#                 #Digits are to help out pdb commands!
#                 a1, b1, c1, d1 = fit_quadratic(x, y)
#                 new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

#             except:

#                 plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

#                 g_dev['obs'].send_to_user("Autofocus was not successful. Returning to original focus setting and pointing.")

#                 g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

#                 self.af_guard = False
#                 if not dont_return_scope:

#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
#                     self.wait_for_slew()

#                 self.af_guard = False
#                 self.focussing=False
#                 return np.nan, np.nan

#             if min(x) <= d1 <= max(x):
#                 plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
#                 g_dev['obs'].send_to_user('Moving to Solved focus:  ' +str(round(d1, 2)), p_level='INFO')
#                 pos = int(d1*g_dev['foc'].micron_to_steps)



#                 g_dev['foc'].guarded_move(pos)

#                 g_dev['foc'].last_known_focus = d1
#                 g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)

#                 # try:
#                 #     g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
#                 # except:
#                 #     g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
#                 g_dev['foc'].last_source = "auto_focus_script"

#                 if not sim:
#                     g_dev['obs'].request_scan_requests()
#                     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
#                     if self.stop_script_called:
#                         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                     if not g_dev['obs'].open_and_enabled_to_observe:
#                         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                 else:
#                     g_dev['obs'].fwhmresult['FWHM'] = new_spot
#                     g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#                 try:
#                     spot4 = g_dev['obs'].fwhmresult['FWHM']
#                     foc_pos4 = g_dev['foc'].current_focus_position
#                 except:
#                     spot4 = False
#                     foc_pos4 = False
#                     plog ("spot4 failed ")
#                 plog('\nFound best focus at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
#                 g_dev['obs'].send_to_user('Successful focus complete at:  ' +str(foc_pos4) +' measured FWHM is:  ' + str(round(spot4, 2)), p_level='INFO')
#                 if not dont_log_focus:
#                     g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
#                 try:
#                     g_dev['foc'].last_focus_fwhm = round(spot4, 2)
#                 except:
#                     plog("MTF hunting this bug")
#                     plog(traceback.format_exc())
#                 #g_dev["obs"].request_full_update()
#                 if not dont_return_scope:

#                     plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#                     self.wait_for_slew()
#             else:
#                 plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)

#                 g_dev['obs'].send_to_user("Autofocus was not successful. Returning to original focus setting and pointing.")

#                 g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

#                 self.af_guard = False
#                 if not dont_return_scope:

#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
#                     self.wait_for_slew()

#                 self.af_guard = False
#                 self.focussing=False
#                 return np.nan, np.nan


#             # if sim:
#             #     g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

#             self.af_guard = False

#                     #
#             self.focussing=False
#             return foc_pos4, spot4

#         elif spot2  <= spot1 < spot3:      #Add to the inside
#             pass
#             plog('Autofocus Moving In 2nd time.\n\n')
#             g_dev['foc'].guarded_move((foc_pos0 - 2.5*throw)*g_dev['foc'].micron_to_steps)
#             if not sim:
#                 g_dev['obs'].request_scan_requests()
#                 result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_1')  #  This is moving in one throw.
#                 if self.stop_script_called:
#                     g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                     self.focussing=False
#                     return np.nan, np.nan
#                 if not g_dev['obs'].open_and_enabled_to_observe:
#                     g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                     self.focussing=False
#                     return np.nan, np.nan
#             else:
#                 g_dev['obs'].fwhmresult['FWHM'] = 6
#                 g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#             try:
#                 spot4 = g_dev['obs'].fwhmresult['FWHM']
#                 foc_pos4 = g_dev['foc'].current_focus_position
#             except:
#                 spot4 = False
#                 foc_pos4 = False
#                 plog ("spot4 failed on autofocus moving in 2nd time.")
#             x = [foc_pos4, foc_pos2, foc_pos1, foc_pos3]
#             y = [spot4, spot2, spot1, spot3]
#             plog('X, Y:  ', x, y, 'Desire center to be smallest.')
#             g_dev['obs'].send_to_user('X, Y:  '+ str(x) + " " + str(y)+ ' Desire center to be smallest.', p_level='INFO')
#             if foc_pos4 != False and foc_pos2 != False and foc_pos1 != False and foc_pos3 != False:
#                 #Digits are to help out pdb commands!
#                 a1, b1, c1, d1 = fit_quadratic(x, y)
#                 new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

#             else:

#                 if extensive_focus == None:

#                     plog('Autofocus quadratic equation did not converge. Moving back to starting focus:  ', focus_start)
#                     plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
#                     g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus routine')

#                     req2 = {'target': 'near_tycho_star', 'image_type': 'focus'}
#                     opt = {'filter': filter_choice}
#                     g_dev['seq'].extensive_focus_script(req2,opt,dont_return_scope=dont_return_scope, begin_at=focus_start, no_auto_after_solve=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=filter_choice)
#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#                         self.wait_for_slew()
#                     self.focussing=False
#                     return np.nan, np.nan
#                 else:
#                     plog('Autofocus quadratic equation did not converge. Moving back to extensive focus:  ', extensive_focus)
#                     g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ' + str(extensive_focus))

#                     g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)

#                     g_dev['foc'].last_known_focus=(extensive_focus)
#                     #g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)


#                     self.af_guard = False
#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)   #NB NB Does this really take us back to starting point?
#                         self.wait_for_slew()

#                     self.af_guard = False
#                     self.focussing=False
#                     return np.nan, np.nan

#             if min(x) <= d1 <= max(x):
#                 plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)

#                 pos = int(d1*g_dev['foc'].micron_to_steps)
#                 g_dev['foc'].guarded_move(pos)

#                 g_dev['foc'].last_known_focus = d1
#                 g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)

#                 # try:
#                 #     g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
#                 # except:
#                 #     g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
#                 g_dev['foc'].last_source = "auto_focus_script"

#                 if not sim:
#                     g_dev['obs'].request_scan_requests()
#                     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
#                     if self.stop_script_called:
#                         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                     if not g_dev['obs'].open_and_enabled_to_observe:
#                         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                 else:
#                     g_dev['obs'].fwhmresult['FWHM'] = new_spot
#                     g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#                 try:
#                     spot4 = g_dev['obs'].fwhmresult['FWHM']
#                     foc_pos4 = g_dev['foc'].current_focus_position
#                 except:
#                     spot4 = False
#                     foc_pos4 = False
#                     plog ("spot4 failed ")
#                 plog('\nFound best focus position at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
#                 g_dev['obs'].send_to_user('Successfully focussed at: ' + str(foc_pos4) +' measured FWHM is: ' + str(round(spot4, 2)), p_level='INFO')
#                 if not dont_log_focus:
#                     g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
#                 if not dont_return_scope:

#                     plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec) #Return to pre-focus pointing.
#                     self.wait_for_slew()
#             # if sim:

#             #     g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

#             self.af_guard = False
#             g_dev['foc'].last_focus_fwhm = round(spot4, 2)
#             self.focussing=False
#             return foc_pos4, spot4

#         elif spot2 > spot1 >= spot3:       #Add to the outside
#             pass
#             plog('Autofocus Moving back in half-way.\n\n')

#             g_dev['foc'].guarded_move((foc_pos0 + 2.5*throw)*g_dev['foc'].micron_to_steps)  #NB NB NB THIS IS WRONG!
#             if not sim:
#                 g_dev['obs'].request_scan_requests()
#                 result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_2')  #  This is moving out one throw.
#                 if self.stop_script_called:
#                     g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                     self.focussing=False
#                     return np.nan, np.nan
#                 if not g_dev['obs'].open_and_enabled_to_observe:
#                     g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                     self.focussing=False
#                     return np.nan, np.nan
#             else:
#                 g_dev['obs'].fwhmresult['FWHM'] = 5.5
#                 g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#             try:
#                 spot4 = g_dev['obs'].fwhmresult['FWHM']
#                 foc_pos4 = g_dev['foc'].current_focus_position
#             except:
#                 spot4 = False
#                 foc_pos4 = False
#                 plog ("spot4 failed on autofocus moving out 2nd time.")
#             x = [foc_pos2, foc_pos1, foc_pos3, foc_pos4]
#             y = [spot2, spot1, spot3, spot4]
#             plog('X, Y:  ', x, y, 'Desire center to be smallest.')
#             g_dev['obs'].send_to_user('X, Y:  '+ str(x) + " " + str(y)+ ' Desire center to be smallest.', p_level='INFO')
#             try:
#                 #Digits are to help out pdb commands!
#                 a1, b1, c1, d1 = fit_quadratic(x, y)
#                 new_spot = round(a1*d1*d1 + b1*d1 + c1, 2)

#             except:

#                 if extensive_focus == None:
#                     plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
#                     plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
#                     g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')
#                     req2 = {'target': 'near_tycho_star'}
#                     opt = {}
#                     g_dev['seq'].extensive_focus_script(req2,opt,dont_return_scope=dont_return_scope,begin_at=focus_start, no_auto_after_solve=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=filter_choice)
#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
#                         self.wait_for_slew()
#                     self.focussing=False
#                     return np.nan, np.nan
#                 else:
#                     plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
#                     g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
#                     g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus:', extensive_focus)

#                     #self.sequencer_hold = False   #Allow comand checks.
#                     self.af_guard = False
#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
#                         self.wait_for_slew()

#                     self.af_guard = False
#                     self.focussing=False
#                     return np.nan, np.nan

#             if min(x) <= d1 <= max(x):
#                 plog ('Moving to Solved focus:  ', round(d1, 2), ' calculated:  ',  new_spot)
#                 pos = int(d1*g_dev['foc'].micron_to_steps)
#                 g_dev['foc'].guarded_move(pos)
#                 g_dev['foc'].last_known_focus = d1

#                 g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)

#                 # try:
#                 #     g_dev['foc'].last_temperature = g_dev['foc'].focuser.Temperature
#                 # except:
#                 #     g_dev['foc'].last_temperature = 7.5    #NB NB NB this should be a config file default.
#                 g_dev['foc'].last_source = "auto_focus_script"

#                 if not sim:
#                     g_dev['obs'].request_scan_requests()
#                     result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False)  #   script = 'auto_focus_script_3')  #  This is verifying the new focus.
#                     if self.stop_script_called:
#                         g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                     if not g_dev['obs'].open_and_enabled_to_observe:
#                         g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
#                         self.focussing=False
#                         return np.nan, np.nan
#                 else:
#                     g_dev['obs'].fwhmresult['FWHM'] = new_spot
#                     g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
#                 try:
#                     spot4 = g_dev['obs'].fwhmresult['FWHM']
#                     foc_pos4 = g_dev['foc'].current_focus_position
#                 except:
#                     spot4 = False
#                     foc_pos4 = False
#                     plog ("spot4 failed ")
#                 plog('\nFound best focus position at:  ', foc_pos4,' measured FWHM is:  ',  round(spot4, 2), '\n')
#                 g_dev['obs'].send_to_user('Successfully found focus at: ' + str(foc_pos4) +' measured FWHM is: ' + str(round(spot4, 2)), p_level='INFO')
#                 if not dont_log_focus:
#                     g_dev['foc'].af_log(foc_pos4, spot4, new_spot)
#                 if not dont_return_scope:

#                     plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
#                     self.wait_for_slew()
#             else:
#                 if extensive_focus == None:

#                     plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
#                     plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
#                     g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')

#                     req2 = {'target': 'near_tycho_star'}
#                     opt = {}
#                     g_dev['seq'].extensive_focus_script(req2,opt,dont_return_scope=dont_return_scope,begin_at=focus_start, no_auto_after_solve=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=filter_choice)

#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #Return to pre-focus pointing.
#                         self.wait_for_slew()
#                     self.focussing=False
#                     return np.nan, np.nan
#                 else:
#                     plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
#                     g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
#                     g_dev['obs'].send_to_user('V-curve focus failed, Moving back to extensive focus: ', extensive_focus)

#                     self.af_guard = False
#                     if not dont_return_scope:

#                         plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                         g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#                         self.wait_for_slew()

#                     self.af_guard = False
#                     self.focussing=False
#                     return np.nan, np.nan


#             # if sim:

#             #     g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

#             self.af_guard = False

#             g_dev['foc'].last_focus_fwhm = round(spot4, 2)
#             self.focussing=False
#             return foc_pos4, spot4

#         else:

#             if extensive_focus == None:

#                 plog('Autofocus quadratic equation not converge. Moving back to starting focus:  ', focus_start)
#                 plog  ("NORMAL FOCUS UNSUCCESSFUL, TRYING EXTENSIVE FOCUS")
#                 g_dev['obs'].send_to_user('V-curve focus failed, trying extensive focus')
#                 req2 = {'target': 'near_tycho_star'}
#                 opt = {}
#                 g_dev['seq'].extensive_focus_script(req2,opt,dont_return_scope=dont_return_scope,begin_at=focus_start, no_auto_after_solve=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, filter_choice=filter_choice)
#                 if not dont_return_scope:

#                     plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#                 self.wait_for_slew()
#                 self.focussing=False
#                 return np.nan, np.nan
#             else:
#                 plog('Autofocus quadratic equation not converge. Moving back to extensive focus:  ', extensive_focus)
#                 g_dev['foc'].guarded_move((extensive_focus)*g_dev['foc'].micron_to_steps)
#                 g_dev['obs'].send_to_user('V-curve focus failed, moving back to extensive focus: ', extensive_focus)
#                 self.af_guard = False
#                 if not dont_return_scope:

#                     plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#                     g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)  #NB NB Does this really take us back to starting point?
#                     self.wait_for_slew()
#                 self.af_guard = False
#                 self.focussing=False
#                 return np.nan, np.nan

#        #breakpoint()

#         if not dont_return_scope:
#             plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#             g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
#             g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
#             self.wait_for_slew()

#        #breakpoint()

#         # if sim:
#         #     g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)


#         self.af_guard = False
#         self.focussing=False
#         return np.nan, np.nan


    def extensive_focus_script(self, req, opt, throw=None, begin_at=None, no_auto_after_solve=False, dont_return_scope=False, skip_timer_check=False, dont_log_focus=False, skip_pointing=False,  filter_choice='focus'):
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
        #breakpoint()
        if begin_at is None:
            foc_start = g_dev['foc'].current_focus_position
        else:
            foc_start = begin_at  #In this case we start at a place close to a 3 point minimum.
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)

        start_ra = g_dev['mnt'].return_right_ascension()
        start_dec = g_dev['mnt'].return_declination()
        plog("Saved ra, dec, focus:  ", start_ra, start_dec, foc_start)

        if not skip_pointing:

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
            #breakpoint()
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

                result = self.centering_exposure(no_confirmation=True, try_hard=True)#), try_forever=True)
                # Wait for platesolve
                #queue_clear_time = time.time()
                reported=0
                temptimer=time.time()
                while True:
                    if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                        #plog ("we are free from platesolving!")
                        break
                    else:
                        if reported ==0:
                            plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                            reported=1
                        if (time.time() - temptimer) > 20:
                            #g_dev["obs"].request_full_update()
                            temptimer=time.time()
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
                g_dev['obs'].request_scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': filter_choice}
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
                    g_dev['obs'].fwhmresult['FWHM'] = 4
                    g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
                except:
                    plog(traceback.format_exc())
                    #
            try:
                spot = g_dev['obs'].fwhmresult['FWHM']
                lsources = g_dev['obs'].fwhmresult['No_of_sources']
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
            #g_dev["obs"].request_full_update()
            if not sim:
                g_dev['obs'].request_scan_requests()
                req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
                opt = { 'count': 1, 'filter': filter_choice}
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
                g_dev['obs'].fwhmresult['FWHM'] = 4
                g_dev['obs'].fwhmresult['mean_focus'] = g_dev['foc'].current_focus_position
            try:
                spot = g_dev['obs'].fwhmresult['FWHM']
                lsources = g_dev['obs'].fwhmresult['No_of_sources']
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
            try:
                plog (extensive_focus)
                plog (solved_pos)
                plog (minimumFWHM)
                g_dev['foc'].guarded_move((solved_pos)*g_dev['foc'].micron_to_steps)
                g_dev['foc'].last_known_focus=(solved_pos)
                g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)

            except:
                plog ("extensive focus failed :(")
            if not no_auto_after_solve:
                self.auto_focus_script(None,None, dont_return_scope=dont_return_scope,skip_timer_check=True, extensive_focus=solved_pos)
            else:
                try:
                    if not dont_log_focus:
                        g_dev['foc'].af_log(solved_pos,minimumFWHM, minimumFWHM)
                except:
                    plog ("Likely no focus positions were found in the extensive focus routine. Investigate if this isn't true.")
                    #plog(traceback.format_exc())
                    plog ("Moving back to the starting focus")
                    g_dev['obs'].send_to_user("Extensive focus attempt failed. Returning to initial focus.")
                    g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)
        except:
            plog ("Something went wrong in the extensive focus routine")
            plog(traceback.format_exc())
            plog ("Moving back to the starting focus")
            g_dev['obs'].send_to_user("Extensive focus attempt failed. Returning to initial focus.")
            g_dev['foc'].guarded_move((foc_start)*g_dev['foc'].micron_to_steps)

        if not dont_return_scope:

            plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
            g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
            g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
            self.wait_for_slew()

        self.af_guard = False
        self.focussing = False

    def equatorial_pointing_run(self, max_pointings=15, alt_minimum=30):

        #breakpoint()
        g_dev['obs'].get_enclosure_status_from_aws()
        if not g_dev['obs'].assume_roof_open and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
            plog('Roof is shut, so cannot do requested pointing run.')
            g_dev["obs"].send_to_user('Roof is shut, so cannot do requested pointing run.')
            return



        self.total_sequencer_control = True
        g_dev['obs'].stop_processing_command_requests = True

        prev_auto_centering = g_dev['obs'].auto_centering_off
        g_dev['obs'].auto_centering_off = True
        plog ("Note that mount references and auto-centering are automatically turned off for a tpoint run.")
        plog("Starting pointing run. ")
        time.sleep(0.1)

        g_dev['mnt'].unpark_command({}, {})

        g_dev["obs"].request_update_status()

        step = (180.0 - 2*alt_minimum)/max_pointings
        ra = 0
        catalogue = []
        while ra < 360:
            catalogue.append([round(ra, 3), 0.0, 19])
            ra += step


       # catalogue=self.pointing_catalogue

        g_dev["obs"].send_to_user("Starting pointing run. Constructing altitude catalogue. This can take a while.")
        plog("Constructing sweep catalogue above altitude " + str(alt_minimum))

        sweep_catalogue=[]
        #First remove all entries below given altitude
        for ctr in range(len(catalogue)):
            teststar = SkyCoord(ra = catalogue[ctr][0]*u.deg, dec = catalogue[ctr][1]*u.deg)

            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            if alt > alt_minimum:
                sweep_catalogue.append([catalogue[ctr][0],catalogue[ctr][1],catalogue[ctr][2],temppointingaltaz.alt.degree, temppointingaltaz.az.degree  ])

        sweep_catalogue = sorted(sweep_catalogue, key= lambda az: az[4])
        plog (len(sweep_catalogue), sweep_catalogue)

        del catalogue




        length = len(sweep_catalogue)
        g_dev["obs"].send_to_user(str(length) + " Targets chosen for sweep.")
        plog(str(length) + " Targets chosen for sweep.")

        count = 0

        deviation_catalogue_for_tpoint=[]

        plog ("Note that mount references and auto-centering are automatically turned off for a tpoint run.")

        for grid_star in sweep_catalogue:


            teststar = SkyCoord(ra = grid_star[0]*u.deg, dec = grid_star[1]*u.deg)

            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            az = temppointingaltaz.az.degree

            g_dev["obs"].send_to_user(str(("Slewing to near grid field, RA: " + str(round(grid_star[0] / 15, 2)) + " DEC: " + str(round(grid_star[1], 2))+ " AZ: " + str(round(az, 2))+ " ALT: " + str(round(alt,2)))))

            plog("Slewing to near grid field " + str(grid_star) )

            # Use the mount RA and Dec to go directly there
            try:
                g_dev['obs'].time_of_last_slew=time.time()
                g_dev["mnt"].last_ra_requested = grid_star[0] / 15
                g_dev["mnt"].last_dec_requested = grid_star[1]
                g_dev['mnt'].slew_async_directly(ra=grid_star[0] /15, dec=grid_star[1])
                #g_dev['mnt'].mount.SlewToCoordinatesAsync(grid_star[0] / 15 , grid_star[1])
            except:
                plog ("Difficulty in directly slewing to object")
                plog(traceback.format_exc())
                if g_dev['mnt'].theskyx:
                    self.kill_and_reboot_theskyx(grid_star[0] / 15, grid_star[1])
                else:
                    plog(traceback.format_exc())
                    #

            self.wait_for_slew()


            #g_dev["obs"].request_update_status()
            g_dev["obs"].update_status()


            g_dev["mnt"].last_ra_requested=grid_star[0] / 15
            g_dev["mnt"].last_dec_requested=grid_star[1]

            req = { 'time': self.config['pointing_exposure_time'], 'smartstack': False, 'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}
            opt = { 'count': 1,  'filter': 'pointing'}
            result = g_dev['cam'].expose_command(req, opt)

            #NB should we check for a valid result from the exposure? WER 2240319

            g_dev["obs"].send_to_user("Platesolving image.")
            # Wait for platesolve
            reported=0
            #temptimer=time.time()
            #g_dev['obs'].platesolve_is_processing = True
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    # if (time.time() - temptimer) > 20:
                    #     #g_dev["obs"].request_full_update()
                    #     temptimer=time.time()
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
                ].return_side_of_pier()  # 0 == Tel Looking West, is flipped.

            except Exception:
                plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            ra_mount=g_dev['mnt'].return_right_ascension()
            dec_mount = g_dev['mnt'].return_declination()
            result=[ra_mount, dec_mount, g_dev['obs'].last_platesolved_ra, g_dev['obs'].last_platesolved_dec,g_dev['obs'].last_platesolved_ra_err, g_dev['obs'].last_platesolved_dec_err, sid, g_dev["mnt"].pier_side,g_dev['cam'].start_time_of_observation,g_dev['cam'].current_exposure_time]
            deviation_catalogue_for_tpoint.append (result)
            plog(result)

            g_dev["obs"].request_update_status()
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



    def sky_grid_pointing_run(self, max_pointings=50, alt_minimum=30):

        #breakpoint()
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

        g_dev["obs"].request_update_status()

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
                sweep_catalogue.append([catalogue[ctr][0],catalogue[ctr][1],catalogue[ctr][2],temppointingaltaz.alt.degree, temppointingaltaz.az.degree  ])

        sweep_catalogue = sorted(sweep_catalogue, key= lambda az: az[4])
        plog (len(sweep_catalogue), sweep_catalogue)

        del catalogue


        spread =3600.0 # Initial spread is about a degree
        too_many=True

        g_dev["obs"].send_to_user("Constructing grid of pointings. This can take a while.")
        plog("Finding a good set of pointings")
        #breakpoint()

        while too_many:

            finalCatalogue=[]
            for ctr in range(len(sweep_catalogue)):
            	if sweep_catalogue[ctr][2] < 20:
                    if len(finalCatalogue) == 0 or len(finalCatalogue) == 1:

                        finalCatalogue.append(sweep_catalogue[ctr])
                    else:
                        idx=(np.abs(np.asarray(finalCatalogue)[:,0] - sweep_catalogue[ctr][0]) + np.abs(np.asarray(finalCatalogue)[:,1] - sweep_catalogue[ctr][1])).argmin()
                        d2d=pow(pow(np.asarray(finalCatalogue)[idx,0] - sweep_catalogue[ctr][0],2) + pow(np.asarray(finalCatalogue)[idx,1] - sweep_catalogue[ctr][1],2),0.5) * 3600


                        if (d2d > spread):
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
                plog ("still too many:  ", len(finalCatalogue))
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

            g_dev["obs"].send_to_user(str(("Slewing to near grid field, RA: " + str(round(grid_star[0] / 15, 2)) + " DEC: " + str(round(grid_star[1], 2))+ " AZ: " + str(round(az, 2))+ " ALT: " + str(round(alt,2)))))

            plog("Slewing to near grid field " + str(grid_star) )

            # Use the mount RA and Dec to go directly there
            try:
                g_dev['obs'].time_of_last_slew=time.time()
                g_dev["mnt"].last_ra_requested = grid_star[0] / 15
                g_dev["mnt"].last_dec_requested = grid_star[1]
                g_dev['mnt'].slew_async_directly(ra=grid_star[0] /15, dec=grid_star[1])
                #g_dev['mnt'].mount.SlewToCoordinatesAsync(grid_star[0] / 15 , grid_star[1])
            except:
                plog ("Difficulty in directly slewing to object")
                plog(traceback.format_exc())
                if g_dev['mnt'].theskyx:
                    self.kill_and_reboot_theskyx(grid_star[0] / 15, grid_star[1])
                else:
                    plog(traceback.format_exc())
                    #

            self.wait_for_slew()


            #g_dev["obs"].request_update_status()
            g_dev["obs"].update_status()


            g_dev["mnt"].last_ra_requested=grid_star[0] / 15
            g_dev["mnt"].last_dec_requested=grid_star[1]

            req = { 'time': self.config['pointing_exposure_time'], 'smartstack': False, 'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}
            opt = { 'count': 1,  'filter': 'pointing'}
            result = g_dev['cam'].expose_command(req, opt)

            g_dev["obs"].send_to_user("Platesolving image.")
            # Wait for platesolve
            reported=0
            temptimer=time.time()
            #g_dev['obs'].platesolve_is_processing = True
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    # if (time.time() - temptimer) > 20:
                    #     #g_dev["obs"].request_full_update()
                    #     temptimer=time.time()
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
                ].return_side_of_pier()  # 0 == Tel Looking West, is flipped.

            except Exception:
                plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            ra_mount=g_dev['mnt'].return_right_ascension()
            dec_mount = g_dev['mnt'].return_declination()
            result=[ra_mount, dec_mount, g_dev['obs'].last_platesolved_ra, g_dev['obs'].last_platesolved_dec,g_dev['obs'].last_platesolved_ra_err, g_dev['obs'].last_platesolved_dec_err, sid, g_dev["mnt"].pier_side,g_dev['cam'].start_time_of_observation,g_dev['cam'].current_exposure_time]
            deviation_catalogue_for_tpoint.append (result)
            plog(result)

            g_dev["obs"].request_update_status()
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


    def centering_exposure(self, no_confirmation=False, try_hard=False, try_forever=False, calendar_event_id=None):

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

        # Don't try forever if focussing
        if self.focussing:
            try_hard=True
            try_forever=False

        # Turn off the pier flip detection if we enter a centering exposure to fix the pier flip
        g_dev['mnt'].pier_flip_detected=False

        #breakpoint()

        if g_dev['cam'].pixscale == None:
            plog ("Finding pixelscale for the first time. This could take a whilE!")
            g_dev["obs"].send_to_user("Finding pixelscale for the first time. This could take a whilE!")
            req = {'time': 180,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
            opt = {'count': 1, 'filter': 'focus'}

        else:
            req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
            opt = {'count': 1, 'filter': 'pointing'}

        successful_platesolve=False

        # # Completely clear platesolve thread
        # with g_dev['obs'].platesolve_queue.mutex:
        #     g_dev['obs'].platesolve_queue.queue.clear()

        # while (not g_dev['obs'].platesolve_queue.empty()):
        #     plog ("Waiting for the platesolve queue to complete it's last job")
        #     print ( g_dev['obs'].platesolve_queue.empty())
        #     time.sleep(1)

        # Make sure platesolve queue is clear
        reported=0
        temptimer=time.time()
        while True:

            if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                break
            else:
                if reported ==0:
                    plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                    reported=1
                if (time.time() - temptimer) > 20:
                    temptimer=time.time()
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
        result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True,useastrometrynet=False)

        if result == 'blockend':
            plog ("End of Block, exiting Centering.")
            return

        if result == 'calendarend':
            plog ("Calendar Item containing block removed from calendar")
            plog ("Site bailing out of Centering")
            return

        if result == 'roofshut':
            plog ("Roof Shut, Site bailing out of Centering")
            return

        if result == 'outsideofnighttime':
            plog ("Outside of Night Time. Site bailing out of Centering")
            return

        if g_dev["obs"].stop_all_activity:
            plog('stop_all_activity cancelling out of centering')
            return

        # Wait for platesolve
        queue_clear_time = time.time()
        reported=0
        temptimer=time.time()
        while True:
            if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                #plog ("we are free from platesolving!")
                break
            else:
                if reported ==0:
                    plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                    reported=1
                if (time.time() - temptimer) > 20:
                    ##g_dev["obs"].request_full_update()
                    temptimer=time.time()
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                    return
                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                    return
                if g_dev["obs"].stop_all_activity:
                    plog('stop_all_activity cancelling out of centering')
                    return
                pass

        plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))
        #


        if g_dev['obs'].last_platesolved_ra != np.nan and str(g_dev['obs'].last_platesolved_ra) != 'nan':
            successful_platesolve=True

        # Nudge if needed.
        if not g_dev['obs'].pointing_correction_requested_by_platesolve_thread and successful_platesolve:
            g_dev["obs"].send_to_user("Slew & Center complete.")
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result
        elif successful_platesolve:
            g_dev['obs'].check_platesolve_and_nudge()
            # Wait until pointing correction fixed before moving on
            while g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                plog ("waiting for pointing_correction_to_finish")
                self.wait_for_slew()
                time.sleep(1)
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result



        if (try_hard or try_forever) and not successful_platesolve:
            plog("Didn't get a successful platesolve at an important time for pointing, trying a double exposure")

            if g_dev['cam'].pixscale == None:
                plog ("Didn't find a solution with the first exposure, trying again.")
                g_dev["obs"].send_to_user("Finding pixelscale for the second time. This could take a whilE!")
                req = {'time': 300,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'focus'}
            else:

                req = {'time': float(self.config['pointing_exposure_time']) * 2,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'pointing'}

            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True,useastrometrynet=True)

            if result == 'blockend':
                plog ("End of Block, exiting Centering.")
                return

            if result == 'calendarend':
                plog ("Calendar Item containing block removed from calendar")
                plog ("Site bailing out of Centering")
                return

            if result == 'roofshut':
                plog ("Roof Shut, Site bailing out of Centering")
                return

            if result == 'outsideofnighttime':
                plog ("Outside of Night Time. Site bailing out of Centering")
                return

            if g_dev["obs"].stop_all_activity:
                plog('stop_all_activity cancelling out of centering')
                return

            queue_clear_time = time.time()
            reported=0
            temptimer=time.time()
            while True:
                if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                    break
                else:
                    if reported ==0:
                        plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                        reported=1
                    if (time.time() - temptimer) > 20:
                        ##g_dev["obs"].request_full_update()
                        temptimer=time.time()
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                        return
                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of centering')
                        return
                    pass
            plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))

            if not (g_dev['obs'].last_platesolved_ra != np.nan and str(g_dev['obs'].last_platesolved_ra) != 'nan'):

                plog("Didn't get a successful platesolve at an important time for pointing AGAIN, trying a Lum filter")

                req = {'time': float(self.config['pointing_exposure_time']) * 2.5,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'Lum'}

                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True,useastrometrynet=True)

                if result == 'blockend':
                    plog ("End of Block, exiting Centering.")
                    return

                if result == 'calendarend':
                    plog ("Calendar Item containing block removed from calendar")
                    plog ("Site bailing out of Centering")
                    return

                if result == 'roofshut':
                    plog ("Roof Shut, Site bailing out of Centering")
                    return

                if result == 'outsideofnighttime':
                    plog ("Outside of Night Time. Site bailing out of Centering")
                    return

                if g_dev["obs"].stop_all_activity:
                    plog('stop_all_activity cancelling out of centering')
                    return


                queue_clear_time = time.time()
                reported=0
                temptimer=time.time()
                while True:
                    if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                        #plog ("we are free from platesolving!")
                        break
                    else:
                        if reported ==0:
                            plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                            reported=1
                        if (time.time() - temptimer) > 20:
                            ##g_dev["obs"].request_full_update()
                            temptimer=time.time()
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                            return
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            return
                        if g_dev["obs"].stop_all_activity:
                            plog('stop_all_activity cancelling out of centering')
                            return
                        pass
                plog ("Time Taken for queue to clear post-exposure: " + str(time.time() - queue_clear_time))



        if try_forever and (g_dev['obs'].last_platesolved_ra == np.nan or str(g_dev['obs'].last_platesolved_ra) == 'nan'):

            while g_dev['obs'].last_platesolved_ra == np.nan or str(g_dev['obs'].last_platesolved_ra) == 'nan':

                plog ("Still haven't got a pointing lock at an important time. Waiting then trying again.")
                g_dev["obs"].send_to_user("Still haven't got a pointing lock at an important time. Waiting then trying again.")

                g_dev['obs'].time_of_last_slew=time.time()



                if result == 'blockend':
                    plog ("End of Block, exiting Centering.")
                    return

                if result == 'calendarend':
                    plog ("Calendar Item containing block removed from calendar")
                    plog ("Site bailing out of Centering")
                    return


                if result == 'roofshut':
                    plog ("Roof Shut, Site bailing out of Centering")
                    return

                if not g_dev['obs'].assume_roof_open and not g_dev['obs'].scope_in_manual_mode and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
                    plog ("Roof Shut, Site bailing out of Centering")
                    return


                if result == 'outsideofnighttime':
                    plog ("Outside of Night Time. Site bailing out of Centering")
                    return
                if not g_dev['obs'].scope_in_manual_mode and g_dev['events']['Observing Ends'] < ephem.Date(ephem.now()):
                    plog ("Outside of Night Time. Site bailing out of Centering")
                    return

                if g_dev["obs"].stop_all_activity:
                    plog('stop_all_activity cancelling out of centering')
                    return


                wait_a_minute=time.time()
                while (time.time() - wait_a_minute < 60):
                    if (time.time() - temptimer) > 20:
                        #g_dev["obs"].request_full_update()
                        temptimer=time.time()
                    if self.stop_script_called:
                        g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                        return
                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of centering')
                        return
                    time.sleep(1)

                # Try shifting to where it is meant to be pointing
                # This can sometimes rescue a lost mount.
                # But most of the time doesn't do anything.
                self.wait_for_slew()
                g_dev['obs'].time_of_last_slew=time.time()
                try:
                    g_dev['mnt'].slew_async_directly(ra=g_dev["mnt"].last_ra_requested, dec=g_dev["mnt"].last_dec_requested)
                    #g_dev['mnt'].mount.SlewToCoordinatesAsync(g_dev["mnt"].last_ra_requested, g_dev["mnt"].last_dec_requested)
                except:
                    plog(traceback.format_exc())
                    if g_dev['mnt'].theskyx:
                        self.kill_and_reboot_theskyx(g_dev["mnt"].last_ra_requested, g_dev["mnt"].last_dec_requested)
                    else:
                        plog(traceback.format_exc())

                self.wait_for_slew()

                req = {'time': float(self.config['pointing_exposure_time']) * 3,  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'pointing'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True,useastrometrynet=True)



                # test for blockend
                if g_dev['seq'].blockend != None:
                    g_dev['obs'].request_update_calendar_blocks()
                    endOfExposure = datetime.datetime.utcnow() + datetime.timedelta(seconds=float(self.config['pointing_exposure_time']) * 3)
                    now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'

                    #plog (now_date_timeZ)
                    #plog (g_dev['seq'].blockend)

                    blockended = now_date_timeZ  >= g_dev['seq'].blockend
                    if blockended:
                        plog ("End of Block, exiting Centering.")
                        return

                if result == 'blockend':
                    plog ("End of Block, exiting Centering.")
                    return

                if result == 'calendarend':
                    plog ("Calendar Item containing block removed from calendar")
                    plog ("Site bailing out of Centering")
                    return

                if not calendar_event_id == None:
                    #print ("ccccccc")

                    foundcalendar=False

                    for tempblock in g_dev['seq'].blocks:
                        try:
                            if tempblock['event_id'] == calendar_event_id :
                                foundcalendar=True
                                g_dev['seq'].blockend=tempblock['end']

                                #breakpoint()
                        except:
                            plog("glitch in calendar finder")
                            plog(str(tempblock))
                    now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                    if foundcalendar == False or now_date_timeZ >= g_dev['seq'].blockend:
                        plog ("could not find calendar entry, cancelling out of block.")
                        plog ("And Cancelling SmartStacks.")
                        return 'calendarend'


                if result == 'roofshut':
                    plog ("Roof Shut, Site bailing out of Centering")
                    return

                if not g_dev['obs'].assume_roof_open and not g_dev['obs'].scope_in_manual_mode and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
                    plog ("Roof Shut, Site bailing out of Centering")
                    return


                if result == 'outsideofnighttime':
                    plog ("Outside of Night Time. Site bailing out of Centering")
                    return
                if not g_dev['obs'].scope_in_manual_mode and g_dev['events']['Observing Ends'] < ephem.Date(ephem.now()):
                    plog ("Outside of Night Time. Site bailing out of Centering")
                    return

                if g_dev["obs"].stop_all_activity:
                    plog('stop_all_activity cancelling out of centering')
                    return


                while True:
                    if g_dev['obs'].platesolve_is_processing ==False and g_dev['obs'].platesolve_queue.empty():
                        #plog ("we are free from platesolving!")
                        break
                    else:
                        if reported ==0:
                            plog ("PLATESOLVE: Waiting for platesolve processing to complete and queue to clear")
                            reported=1
                        if (time.time() - temptimer) > 20:
                            #g_dev["obs"].request_full_update()
                            temptimer=time.time()
                        if self.stop_script_called:
                            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                            return
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            return
                        if g_dev["obs"].stop_all_activity:
                            plog('stop_all_activity cancelling out of centering')
                            return
                        pass


        # Nudge if needed.
        if not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
            g_dev["obs"].send_to_user("Pointing adequate on first slew. Slew & Center complete.")
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result
        else:
            g_dev['obs'].check_platesolve_and_nudge()
            # Wait until pointing correction fixed before moving on
            while g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                plog ("waiting for pointing_correction_to_finish")
                time.sleep(0.5)


        if no_confirmation == True:
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result
        else:
            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                return
            if g_dev["obs"].stop_all_activity:
                plog('stop_all_activity cancelling out of centering')
                return

            g_dev["obs"].send_to_user(
                "Taking a pointing confirmation exposure",
                p_level="INFO",
            )

            # Taking a confirming shot.
            req = {'time': self.config['pointing_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
            opt = {'count': 1, 'filter': 'pointing'}
            result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True)

            if result == 'blockend':
                plog ("End of Block, exiting Centering.")
                return

            if result == 'calendarend':
                plog ("Calendar Item containing block removed from calendar")
                plog ("Site bailing out of Centering")
                return

            if result == 'roofshut':
                plog ("Roof Shut, Site bailing out of Centering")
                return

            if result == 'outsideofnighttime':
                plog ("Outside of Night Time. Site bailing out of Centering")
                return

            if g_dev["obs"].stop_all_activity:
                plog('stop_all_activity cancelling out of centering')
                return

            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                return

            g_dev["obs"].send_to_user("Pointing confirmation exposure complete. Slew & Center complete.")
            g_dev['obs'].check_platesolve_and_nudge()
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result

    def update_calendar_blocks(self):

        """
        A function called that updates the calendar blocks - both to get new calendar blocks and to
        check that any running calendar blocks are still there with the same time window.
        """

        url_blk = "https://calendar.photonranch.org/calendar/siteevents"
        # UTC VERSION
        #start_aperture = str(g_dev['events']['Prior Moon Transit']).split()
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
            plog ("A glitch found in the blocks reqs post, probably date format")


def stack_nanmedian_row_memmapped(inputinfo):
    (pldrivetempfiletemp,counter,shape) = inputinfo
    tempPLDrive = np.memmap(pldrivetempfiletemp, dtype='float32', mode= 'r', shape = shape )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmedian(tempPLDrive[counter,:,:], axis=1)


def stack_nanmedian_row(inputline):
    # try:
    #     return bn.nanmedian(inputline, axis=1).astype(np.float32)
    # except:
    return bn.nanmedian(inputline, axis=1).astype(np.float32)


    # (pldrivetempfiletemp,counter,shape) = inputinfo
    # tempPLDrive = np.memmap(pldrivetempfiletemp, dtype='float32', mode= 'r', shape = shape )
    # with warnings.catch_warnings():
    #     warnings.simplefilter("ignore", category=RuntimeWarning)
    #     return np.nanmedian(tempPLDrive[counter,:,:], axis=1)

