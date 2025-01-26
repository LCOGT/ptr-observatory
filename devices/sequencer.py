'''

sequencer.py  sequencer.py  sequencer.py  sequencer.py  sequencer.py

'''
import time
import datetime
from dateutil import tz
import copy
import json
from global_yard import g_dev
from astropy.coordinates import SkyCoord, AltAz,  Angle, get_body # get_moon,
from astropy import units as u
from astropy.time import Time
from astropy.io import fits
from astropy.stats import sigma_clip
import ephem
import shelve
import math
import shutil
import numpy as np
from numpy import inf
import os
import bottleneck as bn
from math import cos, radians
from PIL import Image
import warnings
import matplotlib.pyplot as plt
plt.ioff()
import queue
import threading

from glob import glob
import traceback
from ptr_utility import plog
import requests


# We only use Observatory in type hints, so use a forward reference to prevent circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from obs import Observatory

from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))
'''
'''


DEG_SYM = '°'
PI = math.pi
TWOPI = math.pi*2.
PIOVER2 = math.pi/2.
DTOR = math.pi/180.
RTOD = 180./math.pi
STOR = math.pi/180./3600.    # "S" stand for arc-seconds
RTOS = 3600.*180./math.pi
RTOH = 12./math.pi
HTOR = math.pi/12.
HTOS = 15*3600.
STOM = 1000.        # "M" stands for mas, milli arc-seconds
MTOS = 0.001
HTOD = 15.
DTOH = 1./15.
DTOS = 3600.
STOD = 1/3600.
STOH = 1/3600./15.
SecTOH = 1/3600.    # "Sec" means seconds of time.
HTOSec = 3600.
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029

LOOK_WEST = 0  #These four constants reflect ASCOM conventions
LOOK_EAST = 1  #Flipped
TEL_ON_EAST_SIDE = 0   #Not Flipped.
TEL_ON_WEST_SIDE = 1   #This means flipped.
IS_FLIPPED = 1
IS_NORMAL = 0

def ra_fix_h(ra):
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra += 24
    return ra



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

def ra_fix(ra):
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra +=24
    return ra

def ra_dec_fix_hd(ra, dec):
    if dec > 90:
        dec = 180 - dec
        ra += 12
    if dec < -90:
        dec = -180 - dec
        ra += 12
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra += 24
    return ra, dec





class Sequencer:

    def __init__(self, observatory: 'Observatory'):
        self.obs = observatory # the parent observatory object
        self.config = self.obs.config

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

        # A flag to keep track of this. Some functions need to not run while this is happening
        self.currently_regenerating_masters = False

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

        # Initialise
        self.measuring_focus_offsets=False

        # We keep track on when we poll for projects
        # It doesn't have to be quite as swift as real-time.
        self.project_call_timer = time.time() - 120

        self.rotator_has_been_homed_this_evening=False
        g_dev['obs'].request_update_calendar_blocks()
        #self.blocks=

        self.MTF_temporary_flat_timer=time.time()-310
        self.got_a_flat_this_round=False

        self.master_restack_queue = queue.Queue(maxsize=0)
        self.master_restack_thread = threading.Thread(target=self.master_restack, args=())
        self.master_restack_thread.daemon = True
        self.master_restack_thread.start()


        self.check_incoming_darks_for_light_leaks=True

        # Clear archive drive on initialisation
        self.clear_archive_drive_of_old_files()


    def run_archive_clearing_thread(self):

        # Culling the archive. This removes old files
        # which allows us to maintain some reasonable harddisk space usage
        if self.config['archive_age'] > 0 :
            plog ("Clearing archive of old files")
            #plog (g_dev['obs'].obsid_path + 'archive/')
            dir_path=g_dev['obs'].obsid_path + 'archive/'
            cameras=glob(dir_path + "*/")
            #plog (cameras)
            for camera in cameras:  # Go through each camera directory
                #plog ("*****************************************")
                #plog ("Camera: " + str(camera))
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
                    # Check that there isn't empty directories lying around -
                    # this happens with theskyx
                    # Check if the directory is empty
                    if not os.listdir(directories[q]):
                        # Remove the empty directory
                        try:
                            os.rmdir(directories[q])
                            plog(f"The directory {directories[q]} was empty and has been removed.")
                        except:
                            pass

                    # else:
                    #     p(f"The directory {directories[q]} is not empty.")
                #plog ("These are the directories earmarked for  ")
                #plog ("Eternal destruction. And how old they are")
                #plog ("in weeks\n")
                #g_dev['obs'].send_to_user("Culling " + str(len(deleteDirectories)) +" from the local archive.", p_level='INFO')
                for entry in range(len(deleteDirectories)):
                    #plog (deleteDirectories[entry] + ' ' + str(deleteTimes[entry]) + ' weeks old.')
                    try:
                        shutil.rmtree(deleteDirectories[entry])
                    except:
                        plog ("Could not remove: " + str(deleteDirectories[entry]) + ". Usually a file is open in that directory.")
            plog ("Finished clearing archive of old files")

    def clear_archive_drive_of_old_files(self):

        thread = threading.Thread(target=self.run_archive_clearing_thread, args=())
        thread.daemon = True
        thread.start()




    def construct_focus_jpeg_and_save(self, packet):

        (x, y, f, current_focus_jpg, jpeg_name, fitted_focus_position,fitted_focus_fwhm) = packet

        # Just plot and fling up the jpeg
        fig,ax=plt.subplots(1, figsize=(5.5, 4), dpi=100)
        plt.ioff()
        ax.scatter(x,y)

        if f:
            ax.plot(x,f(x), color = 'green')
            ax.scatter(fitted_focus_position,fitted_focus_fwhm,  color = 'red', marker = 'X')

        fig.canvas.draw()
        temp_canvas = fig.canvas
        plt.close()
        pil_image=Image.frombytes('RGB', temp_canvas.get_width_height(),  temp_canvas.tostring_rgb())

        current_focus_jpg.paste(pil_image)
        current_focus_jpg.save(jpeg_name.replace('.jpg','temp.jpg'))
        os.rename(jpeg_name.replace('.jpg','temp.jpg'),jpeg_name)


    # Note this is a thread!
    def master_restack(self):
        """
        This is a thread that restackss the local calibrations.
        """

        one_at_a_time = 0
        while True:

            if (not self.master_restack_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                requesttype=self.master_restack_queue.get(block=False)

                self.regenerate_local_masters(requesttype)

                self.master_restack_queue.task_done()

                # EMPTY QUEUE SO THAT ONLY HAPPENS ONCE
                with self.master_restack_queue.mutex:
                    self.master_restack_queue.queue.clear()

                one_at_a_time = 0
                time.sleep(10)

            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(10)

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

        plog (command['user_roles'])

        try:
            script = command['required_params']['script']
        except:
            script = None

        if action.lower() in ["stop", "cancel"] or ( action == "run" and script == "stopScript"):

            #A stop script command flags to the running scripts that it is time to stop
            #activity and return. This period runs for about 30 seconds.
            g_dev["obs"].send_to_user("A Stop Script has been called. Cancelling out of running scripts over 30 seconds.")
            self.stop_script_called=True
            self.stop_script_called_time=time.time()
            # Cancel out of all running exposures.
            g_dev['obs'].cancel_all_activity()
        elif not ("admin" in command['user_roles']) or ("owner" in command['user_roles']):

            g_dev["obs"].send_to_user("Only admin and Owners can run most script commands.")
            plog("Ignored script command from non-admin, non-owner.")


        elif action == "run" and script == 'focusAuto':
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
            self.master_restack_queue.put( 'force', block=False)
        elif action == "run" and script in ['pointingRun']:

            self.sky_grid_pointing_run(max_pointings=req['numPointingRuns'], alt_minimum=req['minAltitude'])
        elif action == "run" and script in ['equatorialSweep']:

            self.equatorial_pointing_run(max_pointings=req['points'], alt_minimum=req['minAltitude'])
        elif action == "run" and script in ("collectBiasesAndDarks"):
            self.bias_dark_script(req, opt, morn=True)


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


    def collect_midnight_frame(self, time, image_type, count, stride, min_exposure=0, check_exposure=False):
        if check_exposure and min_exposure > time:
            return

        plog(f"Expose {count * stride} 1x1 {time}s {image_type.replace('_', ' ')} frames.")
        req = {'time': time, 'script': 'True', 'image_type': image_type}
        opt = {'count': count, 'filter': 'dk'}

        g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False,
                                    do_sep=False, quick=False, skip_open_check=True, skip_daytime_check=True)
        g_dev['obs'].request_scan_requests()

        if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or (
            not (g_dev['events']['Astro Dark'] <= ephem.now() < g_dev['events']['End Astro Dark'])
        ):
            plog(self.stop_script_called)
            plog(g_dev['obs'].open_and_enabled_to_observe)
            plog(not (g_dev['events']['Astro Dark'] <= ephem.now() < g_dev['events']['End Astro Dark']))
            return False
        return True


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

        ephem_now = ephem.now()

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

        not_slewing=False
        if g_dev['obs'].mountless_operation:
            not_slewing=True
        elif not g_dev['mnt'].return_slewing():
            not_slewing=True

        # Don't attempt to start a sequence during an exposure OR when a function (usually TPOINT) has taken total control OR if it is doing something else or waiting to readjust.
        if not self.total_sequencer_control and not g_dev['cam'].running_an_exposure_set and not_slewing and not g_dev['obs'].pointing_recentering_requested_by_platesolve_thread and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands
            # turned off.  So that if a sequencer script starts running, we don't get
            # an odd request out of nowhere that knocks it out
            g_dev['obs'].stop_processing_command_requests = True
            #self.total_sequencer_control = True
            ###########################################################################

            # A little switch flip to make sure focus goes off when roof is simulated
            if  ephem_now < g_dev['events']['Clock & Auto Focus'] :
                self.night_focus_ready=True

            # This bit is really to get the scope up and running if the roof opens
            if ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends'])) \
                and not self.cool_down_latch and g_dev['obs'].open_and_enabled_to_observe \
                and not g_dev['obs'].scope_in_manual_mode and g_dev['mnt'].rapid_park_indicator \
                and ((time.time() - self.time_roof_last_opened) < 20) :

                self.nightly_reset_complete = False
                self.cool_down_latch = True
                self.reset_completes()


                # If the roof opens later then sync and refocus
                if (g_dev['events']['Observing Begins'] < ephem_now < g_dev['events']['Observing Ends']):

                    self.total_sequencer_control=True
                    g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')
                    g_dev['mnt'].go_command(alt=70,az= 70)
                    g_dev['mnt'].set_tracking_on()

                    # Super-duper double check that darkslide is open
                    if g_dev['cam'].has_darkslide:
                        g_dev['cam'].openDarkslide()
                    g_dev['mnt'].wait_for_slew(wait_after_slew=False)

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
                            g_dev['mnt'].wait_for_slew(wait_after_slew=False)
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

                    g_dev['obs'].sync_after_platesolving=True

                    # Autofocus
                    req2 = {'target': 'near_tycho_star'}
                    opt = {}
                    self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)

                    g_dev['obs'].sync_after_platesolving=False

                    g_dev['obs'].send_to_user("End of Focus and Pointing Run. Waiting for Observing period to begin.", p_level='INFO')

                    g_dev['obs'].flush_command_queue()
                    self.total_sequencer_control=False



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

            # This is a block sometimes used for debugging.
            if False and (time.time()-self.MTF_temporary_flat_timer > 300):
                self.MTF_temporary_flat_timer=time.time()
                # plog ("EVESKY FLAG HUNTING")
                # plog ("Roof open time: " + str(time.time() - self.time_roof_last_opened))
                # plog ("Sky flat latch: " + str(self.eve_sky_flat_latch))
                # plog ("Scope in manual mode: " + str(g_dev['obs'].scope_in_manual_mode))
                # plog ("Eve sky start: " + str(events['Eve Sky Flats']))
                # plog ("Eve sky end: " + str(events['End Eve Sky Flats']))
                # plog ("In between: " + str((events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])))
                # plog ("Open and enabled: " + str(g_dev['obs'].open_and_enabled_to_observe))
                # plog ("Eve sky flats done: " + str(self.eve_flats_done))
                # plog ("Camera cooled: " + str(g_dev['obs'].camera_sufficiently_cooled_for_calibrations))
                plog("******")
                plog (events['Observing Begins'] <= ephem_now  < events['Observing Ends'])
                plog(self.block_guard)
                plog( g_dev["cam"].running_an_exposure_set)
                plog(time.time() - self.project_call_timer > 10)
                plog(g_dev['obs'].scope_in_manual_mode)
                plog(g_dev['obs'].open_and_enabled_to_observe)
                plog(self.clock_focus_latch)


            if ((time.time() - self.time_roof_last_opened > self.config['time_to_wait_after_roof_opens_to_take_flats'] ) or g_dev['obs'].assume_roof_open) and \
                   not self.eve_sky_flat_latch and not g_dev['obs'].scope_in_manual_mode and \
                   (events['Eve Sky Flats'] <= ephem_now < events['End Eve Sky Flats'])  \
                   and self.config['auto_eve_sky_flat'] and g_dev['obs'].open_and_enabled_to_observe and\
                   not self.eve_flats_done \
                   and g_dev['obs'].camera_sufficiently_cooled_for_calibrations:

                self.eve_sky_flat_latch = True

                # Cycle through the flat script multiple times if new filters detected.
                # But only three times
                self.new_throughtputs_detected_in_flat_run=True
                flat_run_counter=0
                while self.new_throughtputs_detected_in_flat_run and flat_run_counter <3 and ephem_now < events['End Eve Sky Flats']:
                    self.current_script = "Eve Sky Flat script starting"
                    #g_dev['obs'].send_to_user("Eve Sky Flat script starting")
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
                self.total_sequencer_control=True

                # Make sure folder is empty and clear for the evening
                self.clear_archive_drive_of_old_files()



                g_dev['obs'].send_to_user("Beginning start of night Focus and Pointing Run", p_level='INFO')
                g_dev['mnt'].go_command(alt=70,az= 70)
                g_dev['mnt'].set_tracking_on()

                # Super-duper double check that darkslide is open
                if g_dev['cam'].has_darkslide:
                    g_dev['cam'].openDarkslide()
                g_dev['mnt'].wait_for_slew(wait_after_slew=False)

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
                        g_dev['mnt'].wait_for_slew(wait_after_slew=False)
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

                g_dev['obs'].sync_after_platesolving=True

                # Autofocus
                req2 = {'target': 'near_tycho_star'}
                opt = {}
                self.auto_focus_script(req2, opt, throw = g_dev['foc'].throw)




                # If we don't have a pixelscale, it is highly necessary
                # If it just successfully focused or at least got in the ballpark,
                # then we should attempt to get a pixelscale at this point
                # If we don't do it at this point, it will attempt to at the start of a project anyway
                if g_dev['cam'].pixscale == None:
                    plog ("As we have no recorded pixel scale yet, we are running a quite platesolve to measure it")
                    g_dev['obs'].send_to_user("Using a platesolve to measure the pixelscale of the camera", p_level='INFO')
                    self.centering_exposure(no_confirmation=True, try_hard=True, try_forever=False)

                g_dev['obs'].sync_after_platesolving=False

                g_dev['obs'].send_to_user("End of Focus and Pointing Run. Waiting for Observing period to begin.", p_level='INFO')

                g_dev['obs'].flush_command_queue()

                self.total_sequencer_control=False

                self.night_focus_ready=False
                self.clock_focus_latch = False

            if  (events['Observing Begins'] <= ephem_now \
                                       < events['Observing Ends']) and not self.block_guard and not g_dev["cam"].running_an_exposure_set\
                                       and  (time.time() - self.project_call_timer > 10) and not g_dev['obs'].scope_in_manual_mode  and g_dev['obs'].open_and_enabled_to_observe and self.clock_focus_latch == False:

                try:
                    self.nightly_reset_complete = False
                    self.block_guard = True

                    if not self.reported_on_observing_period_beginning:
                        self.reported_on_observing_period_beginning=True
                        g_dev['obs'].send_to_user("Observing Period has begun.", p_level='INFO')

                    self.project_call_timer = time.time()

                    # Mission critical calendar block update
                    self.update_calendar_blocks()

                    # only need to bother with the rest if there is more than 0 blocks.
                    if not len(self.blocks) > 0:
                        self.block_guard=False
                        self.blockend= None
                    else:
                        now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                        identified_block=None

                        for block in self.blocks:  #  This merges project spec into the blocks.

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
                                        plog ("Not attempting to download again.")
                                        self.append_completes(block['event_id'])
                                        identified_block=None
                                except:
                                    plog(traceback.format_exc())

                                if identified_block == None:
                                    plog ("identified block is None")
                                    pointing_good=False

                                elif identified_block['project_id'] in ['none', 'real_time_slot', 'real_time_block']:
                                    plog ("identified block is real_time or none")
                                    pointing_good=False

                                elif identified_block['project'] == None:
                                    plog (identified_block)
                                    plog ("Skipping a block that contains an empty project")
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
                                    self.blockend = None
                                elif identified_block is None:
                                    self.blockend = None
                                else:
                                    plog ("Something didn't work, cancelling out of doing this project and putting it in the completes pile.")
                                    plog (block)
                                    self.append_completes(block['event_id'])
                                    self.blockend = None

                    self.block_guard=False
                    self.currently_mosaicing = False
                    self.blockend = None

                except:
                    plog(traceback.format_exc())
                    plog("Hang up in sequencer.")
                    self.blockend = None
                    self.block_guard=False
                    self.currently_mosaicing = False

                # Double check
                self.block_guard = False


            if ((time.time() - self.time_roof_last_opened > self.config['time_to_wait_after_roof_opens_to_take_flats'] ) or g_dev['obs'].assume_roof_open) and not self.morn_sky_flat_latch and ((events['Morn Sky Flats'] <= ephem_now < events['End Morn Sky Flats']) and \
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
                      self.config['auto_morn_bias_dark'] and not g_dev['obs'].scope_in_manual_mode and not  self.morn_bias_done and g_dev['obs'].camera_sufficiently_cooled_for_calibrations:

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
                    if not isExist:
                        os.makedirs(g_dev['obs'].obsid_path + 'tokens')
                    runNightToken= g_dev['obs'].obsid_path + 'tokens/' + self.config['obs_id'] + g_dev["day"] + '.token'
                    with open(runNightToken, 'w') as f:
                        f.write('Night Completed')
                    image = (g_dev['obs'].obsid_path + 'tokens/', self.config['obs_id'] + g_dev["day"] + '.token', time.time())
                    g_dev['obs'].ptrarchive_queue.put((56000001, image), block=False)
                    g_dev['obs'].send_to_user("End of Night Token sent to AWS.", p_level='INFO')
                    plog ('token filename: ' + str(runNightToken))

            #Here is where observatories who do their biases at night... well.... do their biases!
            #If it hasn't already been done tonight.
            if self.config['auto_midnight_moonless_bias_dark'] and not g_dev['obs'].scope_in_manual_mode:
                # Check it is in the dark of night
                if  (events['Astro Dark'] <= ephem_now < events['End Astro Dark']):
                    # Check that there isn't any activity indicating someone using it...
                    if (time.time() - g_dev['obs'].time_of_last_exposure) > 900 and (time.time() - g_dev['obs'].time_of_last_slew) > 900:
                        # Check no other commands or exposures are happening
                        if g_dev['obs'].cmd_queue.empty() and not g_dev["cam"].running_an_exposure_set:
                            # If enclosure is shut for maximum darkness
                            if 'Closed' in enc_status['shutter_status']  or 'closed' in enc_status['shutter_status']:
                                # Check the temperature is in range
                                currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
                                moondata=get_body("moon", time=Time.now()).transform_to(currentaltazframe)
                                if (moondata.alt.deg < -15):
                                    # If the moon is way below the horizon
                                    if g_dev['obs'].camera_sufficiently_cooled_for_calibrations:


                                        # When we are getting darks, we are collecting darks for the NEXT night's temperature
                                        # not tonights. So if tomrorow night the season changes and the camera temperature changes
                                        # We need to have the bias/darks already.
                                        if g_dev['cam'].temp_setpoint_by_season:

                                            current_night_setpoint=copy.deepcopy(g_dev['cam'].setpoint)

                                            tomorrow_night=datetime.datetime.now() +datetime.timedelta(days=1)
                                            tempmonth = tomorrow_night.month
                                            tempday= tomorrow_night.day

                                            if tempmonth == 12 or tempmonth == 1 or (tempmonth ==11 and tempday >15) or (tempmonth ==2 and tempday <=15):
                                                tommorow_night_setpoint=  float(
                                                    g_dev['cam'].settings['temp_setpoint_nov_to_feb'][0])

                                            elif tempmonth == 3 or tempmonth == 4 or (tempmonth ==2 and tempday >15) or (tempmonth ==5 and tempday <=15):
                                                tommorow_night_setpoint=  float(
                                                    g_dev['cam'].settings['temp_setpoint_feb_to_may'][0])

                                            elif tempmonth == 6 or tempmonth == 7 or (tempmonth ==5 and tempday >15) or (tempmonth ==8 and tempday <=15):

                                                tommorow_night_setpoint=  float(
                                                    g_dev['cam'].settings['temp_setpoint_may_to_aug'][0])

                                            elif tempmonth == 9 or tempmonth == 10 or (tempmonth ==8 and tempday >15) or (tempmonth ==11 and tempday <=15):

                                                tommorow_night_setpoint=  float(
                                                    g_dev['cam'].settings['temp_setpoint_aug_to_nov'][0])

                                            # Here change the setpoint tomorrow nights setpoint
                                            g_dev['cam'].current_setpoint = tommorow_night_setpoint
                                            g_dev['cam'].setpoint = tommorow_night_setpoint
                                            g_dev['cam']._set_setpoint(tommorow_night_setpoint)

                                            # Need to trim th ecalibration directories of all files
                                            # Not within the tolerance limit from the setpoint
                                            darks_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/darks/'
                                            bias_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/biases/'

                                            # First check darks in root directory
                                            print ("ROOT DIRECTORY DARKS")
                                            for darkfile in glob(darks_path + '*.npy'):
                                                tempdarktemp=float(darkfile.split('_')[-3])
                                                #print (tempdarktemp)
                                                if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                                    try:
                                                        os.remove(darkfile)
                                                    except:
                                                        pass

                                            # Then check each of the darks folder
                                            for darkfolder in glob(darks_path + "*/"):
                                                print (darkfolder)
                                                for darkfile in glob(darkfolder + '*.npy'):
                                                    tempdarktemp=float(darkfile.split('_')[-3])
                                                    #print (tempdarktemp)
                                                    if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                                        try:
                                                            os.remove(darkfile)
                                                        except:
                                                            pass

                                            # NEED TO CHECK BIASES LATER!
                                            # First check darks in root directory
                                            print ("ROOT DIRECTORY BIASES")
                                            for darkfile in glob(bias_path + '*.npy'):
                                                tempdarktemp=float(darkfile.split('_')[-3])
                                                #print (tempdarktemp)
                                                if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                                    try:
                                                        os.remove(darkfile)
                                                    except:
                                                        pass


                                            if abs(tommorow_night_setpoint-current_night_setpoint) > 4:
                                                plog("waiting an extra three minutes for camera to cool to different temperature")
                                                time.sleep(180)

                                        # If there are no biases, then don't check for lightleaks.
                                        # This catches a bias and dark refresh... manually or at the transition of seasons.
                                        bias_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/biases/'

                                        if len (glob(bias_path + '*.npy')) == 0:
                                            self.check_incoming_darks_for_light_leaks=False
                                        else:
                                            self.check_incoming_darks_for_light_leaks=True

                                        if self.nightime_bias_counter < (g_dev['cam'].settings['number_of_bias_to_collect'] / 4):
                                            plog ("It is dark and the moon isn't up! Lets do a bias!")
                                            g_dev['mnt'].park_command({}, {})
                                            plog("Exposing 1x1 bias frame.")
                                            req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
                                            opt = { 'count': 1,  \
                                                   'filter': 'dk'}
                                            self.nightime_bias_counter = self.nightime_bias_counter + 1
                                            g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                                                                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
                                            # these exposures shouldn't reset these timers
                                            g_dev['obs'].time_of_last_exposure = time.time() - 840
                                            g_dev['obs'].time_of_last_slew = time.time() - 840
                                        if self.nightime_dark_counter < (g_dev['cam'].settings['number_of_dark_to_collect']/ 4):
                                            plog ("It is dark and the moon isn't up! Lets do a dark!")
                                            g_dev['mnt'].park_command({}, {})
                                            dark_exp_time = g_dev['cam'].settings['dark_exposure']
                                            broadband_ss_biasdark_exp_time = g_dev['cam'].settings['smart_stack_exposure_time']
                                            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * g_dev['cam'].settings['smart_stack_exposure_NB_multiplier']

                                            # There is no point getting biasdark exposures below the min_flat_exposure time aside from the scaled dark values.
                                            min_exposure = min(float(g_dev['cam'].settings['min_flat_exposure']), float(g_dev['cam'].settings['min_exposure']))
                                            stride=1
                                            min_to_do=1


                                            # Define frames to collect
                                            frames_to_collect = [
                                                (2, "twosec_exposure_dark", 5),
                                                (3.5, "threepointfivesec_exposure_dark", 5),
                                                (5, "fivesec_exposure_dark", 5),
                                                (7.5, "sevenpointfivesec_exposure_dark", 5),
                                                (10, "tensec_exposure_dark", 2),
                                                (15, "fifteensec_exposure_dark", 2),
                                                (20, "twentysec_exposure_dark", 2),
                                                (30, "thirtysec_exposure_dark", 2),
                                                (broadband_ss_biasdark_exp_time, "broadband_ss_biasdark", 2),
                                                (narrowband_ss_biasdark_exp_time, "narrowband_ss_biasdark", 2, True),
                                                (0.0045, "pointzerozerofourfive_exposure_dark", 5, True),
                                                (0.0004, "fortymicrosecond_exposure_dark", 5, True),
                                                (0.00004, "fourhundredmicrosecond_exposure_dark", 5, True),
                                                (0.015, "onepointfivepercent_exposure_dark", 5, True),
                                                (0.05, "fivepercent_exposure_dark", 5, True),
                                                (0.1, "tenpercent_exposure_dark", 5, True),
                                                (0.25, "quartersec_exposure_dark", 5, True),
                                                (0.5, "halfsec_exposure_dark", 5),
                                                (0.75, "threequartersec_exposure_dark", 5, True),
                                                (1.0, "onesec_exposure_dark", 5, True),
                                                (1.5, "oneandahalfsec_exposure_dark", 5, True),
                                                (0.0, "bias", min_to_do),
                                                (dark_exp_time, "dark", 1),
                                            ]

                                            # Collect frames
                                            for frame in frames_to_collect:
                                                exposure_time, image_type, count_multiplier = frame[:3]
                                                check_exposure = frame[3] if len(frame) > 3 else False
                                                if not self.collect_midnight_frame(exposure_time, image_type, count_multiplier, stride, min_exposure, check_exposure):
                                                    break

                                            if g_dev['cam'].temp_setpoint_by_season:
                                                # Here change the setpoint back to tonight's setpoint
                                                g_dev['cam'].current_setpoint = current_night_setpoint
                                                g_dev['cam'].setpoint = current_night_setpoint
                                                g_dev['cam']._set_setpoint(current_night_setpoint)

                                            # these exposures shouldn't reset these timers
                                            g_dev['obs'].time_of_last_exposure = time.time() - 840
                                            g_dev['obs'].time_of_last_slew = time.time() - 840

            ###########################################################################
            # While in this part of the sequencer, we need to have manual UI commands turned back on
            # So that we can process any new manual commands that come in.
            g_dev['obs'].stop_processing_command_requests = False
            #self.total_sequencer_control = False
            g_dev['obs'].request_scan_requests()
            ###########################################################################
        return


    def reset_completes(self):

        """
        The sequencer keeps track of completed projects, but in certain situations,
        you want to flush that list (e.g. roof shut then opened again).
        """

        try:
            camera = self.obs.devices['main_cam'].name
            seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) + '_completes_' + str(g_dev['obs'].name))
            seq_shelf['completed_blocks'] = []
            seq_shelf.close()
        except:
            plog('Found an empty shelf.  Reset_(block)completes for:  ', camera)
        return

    def append_completes(self, block_id):
        #
        camera = self.obs.devices['main_cam'].name
        seq_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + str(camera) +'_completes_' + str(g_dev['obs'].name))
        lcl_list = seq_shelf['completed_blocks']
        if block_id in lcl_list:
            plog('Duplicate storage of block_id in pended completes blocked.')
            seq_shelf.close()
            return False
        lcl_list.append(block_id)   #NB NB an in-line append did not work!
        seq_shelf['completed_blocks']= lcl_list
        plog('Appended completes contains:  ', seq_shelf['completed_blocks'])
        seq_shelf.close()
        self.block_guard=False
        return True

    def is_in_completes(self, block_id):

        camera = self.obs.devices['main_cam'].name
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


        if (ephem.now() < g_dev['events']['Civil Dusk'] ) or \
            (g_dev['events']['Civil Dawn']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT RUNNING PROJECT BLOCK -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A project block was rejected as it is during the daytime.")
            return block_specification     #Added wer 20231103

        self.block_guard = True
        self.total_sequencer_control=True

        plog('|n|n Starting a new project!  \n')
        plog(block_specification, ' \n\n\n')

        calendar_event_id=block_specification['event_id']

        block = copy.deepcopy(block_specification)

        # this variable is what we check to see if the calendar
        # event still exists on AWS. If not, we assume it has been
        # deleted or modified substantially.
        calendar_event_id = block_specification['event_id']

        for target in block['project']['project_targets']:   #  NB NB NB Do multi-target projects make sense???
            try:
                dest_ra = float(target['ra']) + \
                    float(block_specification['project']['project_constraints']['ra_offset'])/15.

                dest_dec = float(target['dec']) + float(block_specification['project']['project_constraints']['dec_offset'])
                dest_ra, dest_dec = ra_dec_fix_hd(dest_ra, dest_dec)
                dest_name =target['name']

                user_name = block_specification['creator']
                user_id = block_specification['creator_id']
                user_roles = ['project']

            except Exception as e:
                plog ("Could not execute project due to poorly formatted or corrupt project")
                plog (e)
                g_dev['obs'].send_to_user("Could not execute project due to poorly formatted or corrupt project", p_level='INFO')
                self.blockend = None
                continue

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
                    g_dev['mnt'].wait_for_slew(wait_after_slew=False)
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

            pa = float(block_specification['project']['project_constraints']['position_angle'])
            if abs(pa) > 0.01:
                try:
                    g_dev['rot'].rotator.MoveAbsolute(pa)   #Skip rotator move if nominally 0
                except:
                    pass

            # Input the global smartstack and substack request from the project
            # Into the individual exposure requests
            try:
                try:
                    # This is the "proper" way of doing things.
                    do_sub_stack=block['project']['project_constraints']['sub_stack']
                    plog ("Picked up project substack properly")
                except:
                    # This is the old way for old projects
                    do_sub_stack=block['project']['exposures'][0]['substack']
            except:
                do_sub_stack=True

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
                exposure['substack'] = do_sub_stack
                exposure['smartstack'] = do_smart_stack
                left_to_do += int(exposure['count'])

            plog("Left to do initial value:  ", left_to_do)
            req = {'target': 'near_tycho_star'}

            g_dev['mnt'].go_command(ra=dest_ra, dec=dest_dec)

            # If you are just doing single frames, then the initial pointing isn't
            # too stringent. But if you are doing a giant mosaic, then you need
            # a reference that is very close to the target
            if exposure['zoom'].lower() in ["full", 'Full'] or 'X' in exposure['zoom'] \
                or  '%' in exposure['zoom'] or ( exposure['zoom'].lower() == 'small sq.') \
                or (exposure['zoom'].lower() == 'small sq'):
                absolute_distance_threshold=10
            else:
                absolute_distance_threshold=2

            #plog ("Checking whether the pointing reference is nearby. If so, we can skip the centering exposure...")
            skip_centering=False
            HAtemp=g_dev['mnt'].current_sidereal-dest_ra
            # NB NB WER 20240710  the long key was missing and the following code appeared to be looping forever....
            if g_dev['mnt'].rapid_pier_indicator == 0:

                distance_from_current_reference_in_ha = abs(g_dev['mnt'].last_mount_reference_ha - HAtemp)
                distance_from_current_reference_in_dec = abs(g_dev['mnt'].last_mount_reference_dec- dest_dec)
                absolute_distance=pow(pow(distance_from_current_reference_in_ha*cos(radians(distance_from_current_reference_in_dec)),2)+pow(distance_from_current_reference_in_dec,2),0.5)
                plog ("absolute_distance from reference to requested position: " + str(round(absolute_distance,2)))
                if absolute_distance < absolute_distance_threshold and not self.config['always_do_a_centering_exposure_regardless_of_nearby_reference']:
                    plog ("reference close enough to requested position, skipping centering exposure")
                    skip_centering=True

            else:
                distance_from_current_reference_in_ha = abs(g_dev['mnt'].last_flip_reference_ha - HAtemp)
                distance_from_current_reference_in_dec = abs(g_dev['mnt'].last_flip_reference_dec- dest_dec)
                #plog ("Dist in RA: " + str(round(distance_from_current_reference_in_ha,2)) + "Dist in Dec: " + str(round(distance_from_current_reference_in_dec,2)))
                absolute_distance=pow(pow(distance_from_current_reference_in_ha*cos(radians(distance_from_current_reference_in_dec)),2)+pow(distance_from_current_reference_in_dec,2),0.5)
                plog ("absolute_distance from reference to requested position: " + str(round(absolute_distance,2)))
                if absolute_distance < absolute_distance_threshold and not self.config['always_do_a_centering_exposure_regardless_of_nearby_reference']:
                    plog ("reference close enough to requested position, skipping centering exposure")
                    skip_centering=True

            if not skip_centering:
                plog ("Taking a quick pointing check and re_seek for new project block")
                result = self.centering_exposure(no_confirmation=True, try_hard=True, try_forever=True, calendar_event_id=calendar_event_id)

            # It may be the case that reference pointing isn't quite good enough for mosaics? We shall find out.
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            # Don't do a second repointing in the first pane of a mosaic
            # considering we just did that.
            mosaic_pointing_already_done=True

            while left_to_do > 0 and not ended:
                block_exposure_counter=0
                for exposure in block['project']['exposures']:
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    g_dev['obs'].request_scan_requests()
                    foundcalendar=False
                    g_dev['obs'].request_update_calendar_blocks()
                    for tempblock in self.blocks:
                        if tempblock['event_id'] == calendar_event_id :
                            foundcalendar=True
                            self.blockend=tempblock['end']
                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            if self.blockend != None:
                                if now_date_timeZ >= self.blockend :
                                    plog ("Block ended.")
                                    g_dev["obs"].send_to_user("Calendar Block Ended. Stopping project run.")
                                    left_to_do=0
                                    self.blockend = None
                                    self.total_sequencer_control=False
                                    return block_specification
                    if not foundcalendar:
                        plog ("could not find calendar entry, cancelling out of block.")
                        g_dev["obs"].send_to_user("Calendar block removed. Stopping project run.")
                        self.blockend = None
                        self.total_sequencer_control=False
                        return block_specification

                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of exposure loop in seq:blk execute')
                        self.blockend = None
                        self.total_sequencer_control=False
                        return block_specification

                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Obs not longer open and enabled to observe. Cancelling out.")
                        self.blockend = None
                        self.total_sequencer_control=False
                        return block_specification

                    plog ("Observing " + str(block['project']['project_targets'][0]['name']))

                    plog("Executing: ", exposure, left_to_do)
                    try:
                        filter_requested = exposure['filter']
                    except:
                        filter_requested = 'None'

                    # Try next block in sequence

                    if g_dev["fil"].null_filterwheel == False:
                        try:
                            if not (block_exposure_counter + 1) ==len(block['project']['exposures']):
                                self.block_next_filter_requested=block['project']['exposures'][block_exposure_counter+1]['filter']
                            else:
                                self.block_next_filter_requested=block['project']['exposures'][0]['filter']
                        except:
                            plog(traceback.format_exc())
                            #breakpoint()
                            self.block_next_filter_requested='None'
                    else:
                        self.block_next_filter_requested='None'


                    exp_time =  float(exposure['exposure'])
                    try:
                        repeat_count = int(exposure['repeat'])
                        if repeat_count < 1: repeat_count = 1
                    except:
                        repeat_count = 1
                    #  We should add a frame repeat count
                    imtype = exposure['imtype']

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
                    if exposure['zoom'].lower() in ["full", 'Full'] or 'X' in exposure['zoom'] \
                        or  '%' in exposure['zoom'] or ( exposure['zoom'].lower() == 'small sq.') \
                        or (exposure['zoom'].lower() == 'small sq'):

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

                        # Ok here we take the provided (eventually) mosaic lengths
                        # And assume a 10% overlap -- maybe an option in future but
                        # lets just set it as that for now.
                        # Then calculate the central coordinate offsets.
                        mosaic_length_fields_ra = requested_mosaic_length_ra / ra_field_deg
                        mosaic_length_fields_dec = requested_mosaic_length_dec / dec_field_deg
                        #if mosaic_length_fields_ra % 1 > 0.8:
                        if mosaic_length_fields_ra % 1 > 0.6:
                            mosaic_length_fields_ra += 1
                        #if mosaic_length_fields_dec % 1 > 0.8:
                        if mosaic_length_fields_dec % 1 > 0.6:
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
                            self.total_sequencer_control=False
                            return block_specification

                        if result == 'calendarend':
                            plog ("Calendar Item containing block removed from calendar")
                            plog ("Site bailing out of running project")
                            self.blockend = None
                            self.currently_mosaicing = False
                            self.total_sequencer_control=False
                            return block_specification

                        if result == 'roofshut':
                            plog ("Roof Shut, Site bailing out of Project")
                            self.blockend = None
                            self.currently_mosaicing = False
                            self.total_sequencer_control=False
                            return block_specification

                        if result == 'outsideofnighttime':
                            plog ("Outside of Night Time. Site bailing out of Project")
                            self.blockend = None
                            self.currently_mosaicing = False
                            self.total_sequencer_control=False
                            return block_specification

                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of Project')
                        self.blockend = None
                        self.currently_mosaicing = False
                        self.total_sequencer_control=False
                        return block_specification

                    for displacement in offset:     #NB it would be convenient for odd panel mosaics
                                                    #if we start in the center and then wrap around.
                        if self.currently_mosaicing:
                            plog ("Moving to new position of mosaic")
                            plog (displacement)
                            self.current_mosaic_displacement_ra= displacement[0]/15
                            self.current_mosaic_displacement_dec= displacement[1]
                            # Slew to new mosaic pane location.
                            new_ra = self.mosaic_center_ra + self.current_mosaic_displacement_ra
                            new_dec= self.mosaic_center_dec + self.current_mosaic_displacement_dec
                            new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)
                            try:
                                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                                g_dev['obs'].time_of_last_slew=time.time()
                                try:
                                    g_dev['mnt'].slew_async_directly(ra=new_ra, dec=new_dec)
                                except:
                                    plog(traceback.format_exc())
                                    if g_dev['mnt'].theskyx:
                                        self.obs.kill_and_reboot_theskyx(new_ra, new_dec)
                                    else:
                                        plog(traceback.format_exc())
                                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                            except Exception as e:
                                plog (traceback.format_exc())
                                if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                    plog("The SkyX had an error.")
                                    plog("Usually this is because of a broken connection.")
                                    plog("Killing then waiting 60 seconds then reconnecting")
                                    self.obs.kill_and_reboot_theskyx(new_ra,new_dec)

                            g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                            # try:
                            # if result == 'blockend':
                            #     plog ("End of Block, exiting project block.")
                            #     self.blockend = None
                            #     self.currently_mosaicing = False
                            #     self.total_sequencer_control=False
                            #     return block_specification

                            # if result == 'calendarend':
                            #     plog ("Calendar Item containing block removed from calendar")
                            #     plog ("Site bailing out of running project")
                            #     self.blockend = None
                            #     self.currently_mosaicing = False
                            #     self.total_sequencer_control=False
                            #     return block_specification

                            # if result == 'roofshut':
                            #     plog ("Roof Shut, Site bailing out of Project")
                            #     self.blockend = None
                            #     self.currently_mosaicing = False
                            #     self.total_sequencer_control=False
                            #     return block_specification

                            # if result == 'outsideofnighttime':
                            #     plog ("Outside of Night Time. Site bailing out of Project")
                            #     self.blockend = None
                            #     self.currently_mosaicing = False
                            #     self.total_sequencer_control=False
                            #     return block_specification

                            # if g_dev["obs"].stop_all_activity:
                            #     plog('stop_all_activity cancelling out of Project')
                            #     self.blockend = None
                            #     self.currently_mosaicing = False
                            #     self.total_sequencer_control=False
                            #     return block_specification

                        if imtype in ['light']:

                            # Sort out Longstack and Smartstack names and switches
                            if exposure['smartstack'] == False:
                                smartstackswitch='no'
                            elif exposure['smartstack'] == True:
                                smartstackswitch='yes'
                            else:
                                smartstackswitch='no'
                            if exposure['substack'] == False:
                                substackswitch=False
                            elif exposure['substack'] == True:
                                substackswitch=True
                            else:
                                substackswitch=True

                            # Set up options for exposure and take exposure.
                            req = {'time': exp_time,  'alias':  str(g_dev['cam'].name), 'image_type': imtype, 'smartstack' : smartstackswitch, 'substack': substackswitch, 'block_end' : self.blockend}   #  NB Should pick up filter and constants from config
                            opt = {'count': repeat_count, 'filter': filter_requested, \
                                   'hint': block['project_id'] + "##" + dest_name, 'object_name': block['project']['project_targets'][0]['name'], 'pane': pane, 'zoom': zoom_factor}
                            plog('Seq Blk sent to camera:  ', req, opt)

                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            if self.blockend != None:
                                if now_date_timeZ >= self.blockend :
                                    left_to_do=0
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return
                            result = g_dev['cam'].expose_command(req, opt, user_name=user_name, user_id=user_id, user_roles=user_roles, no_AWS=False, solve_it=False, calendar_event_id=calendar_event_id) #, zoom_factor=zoom_factor)

                            try:
                                if result == 'blockend':
                                    plog ("End of Block, exiting project block.")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return block_specification

                                if result == 'calendarend':
                                    plog ("Calendar Item containing block removed from calendar")
                                    plog ("Site bailing out of running project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return block_specification

                                if result == 'roofshut':
                                    plog ("Roof Shut, Site bailing out of Project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return block_specification

                                if result == 'outsideofnighttime':
                                    plog ("Outside of Night Time. Site bailing out of Project")
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return block_specification

                                if g_dev["obs"].stop_all_activity:
                                    plog('stop_all_activity cancelling out of Project')
                                    self.blockend = None
                                    self.currently_mosaicing = False
                                    self.total_sequencer_control=False
                                    return block_specification

                            except:
                                pass

                            # Check that the observing time hasn't completed or then night has not completed.
                            # If so, set ended to True so that it cancels out of the exposure block.
                            now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                            events = g_dev['events']
                            blockended=False
                            if self.blockend != None:
                                blockended = now_date_timeZ >= self.blockend
                            ended = left_to_do <= 0 or blockended \
                                    or ephem.now() >= events['Observing Ends']
                            if ephem.now() >= events['Observing Ends']:
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if result == 'blockend':
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if blockended:
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if result == 'calendarend':
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if result == 'roofshut':
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if result == 'outsideofnighttime':
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                            if g_dev["obs"].stop_all_activity:
                                plog('stop_all_activity cancelling out of exposure loop')
                                self.blockend = None
                                self.currently_mosaicing = False
                                self.total_sequencer_control=False
                                return block_specification

                        pane += 1
                    block_exposure_counter=block_exposure_counter+1

                left_to_do -= 1
                plog("Left to do:  ", left_to_do)

        self.currently_mosaicing = False
        plog("Project block has finished!")
        self.blockend = None

        g_dev['obs'].flush_command_queue()
        self.total_sequencer_control=False
        return block_specification


    def collect_dark_frame(self, exposure_time, image_type, count, stride, min_to_do, dark_exp_time, cycle_time, ending):
        plog(f"Expose {count * stride} 1x1 {exposure_time}s exposure dark frames.")
        req = {'time': exposure_time, 'script': 'True', 'image_type': image_type}
        opt = {'count': count, 'filter': 'dk'}

        # Ensure the mount is parked
        if not g_dev['obs'].mountless_operation:
            g_dev['mnt'].park_command({}, {})

        # Trigger exposure
        g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system',
                                    no_AWS=False, do_sep=False, quick=False, skip_open_check=True, skip_daytime_check=True)

        # Handle cancellation or timeout
        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
            self.bias_dark_latch = False
            return False
        if ephem.now() + (dark_exp_time + cycle_time + 30) / 86400 > ending:
            self.bias_dark_latch = False
            return False

        g_dev['obs'].request_scan_requests()
        return True

    def collect_bias_frame(self, count, stride, min_to_do, dark_exp_time, cycle_time, ending):
        plog(f"Expose {count * stride} 1x1 bias frames.")
        req = {'time': 0.0, 'script': 'True', 'image_type': 'bias'}
        opt = {'count': min_to_do, 'filter': 'dk'}

        if not g_dev['obs'].mountless_operation:
            g_dev['mnt'].park_command({}, {})

        g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system',
                                    no_AWS=False, do_sep=False, quick=False, skip_open_check=True, skip_daytime_check=True)

        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
            self.bias_dark_latch = False
            return False
        if ephem.now() + (dark_exp_time + cycle_time + 30) / 86400 > ending:
            self.bias_dark_latch = False
            return False

        g_dev['obs'].request_scan_requests()
        return True


    def bias_dark_script(self, req=None, opt=None, morn=False, ending=None):
        """
        This functions runs through automatically collecting bias and darks for the local calibrations.
        """
        self.current_script = 'Bias Dark'

        self.total_sequencer_control=True
        if morn:
            ending = g_dev['events']['End Morn Bias Dark']
        else:
            ending = g_dev['events']['End Eve Bias Dark']

        # Set a timer. It is possible to ask for bias darks and it takes until the end of time. So we should put a limit on it for manually
        # requested collection. Auto-collection is limited by the events schedule.
        bias_darks_started=time.time()

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

            bias_count = g_dev['cam'].settings['number_of_bias_to_collect']
            dark_count = g_dev['cam'].settings['number_of_dark_to_collect']
            dark_exp_time = g_dev['cam'].settings['dark_exposure']
            cycle_time = g_dev['cam'].settings['cycle_time']

            # For 95% of our exposures we can collect biasdarks... so we don't have to
            # scale the darks with a master bias for our most common exposures
            # Non-scaled darks with the bias still contained IS better,
            # Just uncommon for observatories where there is all sorts of different exposure times.
            # But for PTR, we have some very frequent used exposure times, so this is a worthwhile endeavour.
            broadband_ss_biasdark_exp_time = g_dev['cam'].settings['smart_stack_exposure_time']
            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * g_dev['cam'].settings['smart_stack_exposure_NB_multiplier']
            # There is no point getting biasdark exposures below the min_flat_exposure time aside from the scaled dark values.
            # min_exposure = min(float(g_dev['cam'].settings['min_flat_exposure']),float(g_dev['cam'].settings['min_exposure']))


            ####
            # When we are getting darks, we are collecting darks for the NEXT night's temperature
            # not tonights. So if tomrorow night the season changes and the camera temperature changes
            # We need to have the bias/darks already.
            if g_dev['cam'].temp_setpoint_by_season:

                current_night_setpoint=copy.deepcopy(g_dev['cam'].setpoint)

                tomorrow_night=datetime.datetime.now() +datetime.timedelta(days=1)
                tempmonth = tomorrow_night.month
                tempday= tomorrow_night.day

                if tempmonth == 12 or tempmonth == 1 or (tempmonth ==11 and tempday >15) or (tempmonth ==2 and tempday <=15):
                    tommorow_night_setpoint=  float(
                        g_dev['cam'].settings['temp_setpoint_nov_to_feb'][0])

                elif tempmonth == 3 or tempmonth == 4 or (tempmonth ==2 and tempday >15) or (tempmonth ==5 and tempday <=15):
                    tommorow_night_setpoint=  float(
                        g_dev['cam'].settings['temp_setpoint_feb_to_may'][0])

                elif tempmonth == 6 or tempmonth == 7 or (tempmonth ==5 and tempday >15) or (tempmonth ==8 and tempday <=15):

                    tommorow_night_setpoint=  float(
                        g_dev['cam'].settings['temp_setpoint_may_to_aug'][0])

                elif tempmonth == 9 or tempmonth == 10 or (tempmonth ==8 and tempday >15) or (tempmonth ==11 and tempday <=15):

                    tommorow_night_setpoint=  float(
                        g_dev['cam'].settings['temp_setpoint_aug_to_nov'][0])

                # Here change the setpoint tomorrow nights setpoint
                g_dev['cam'].current_setpoint = tommorow_night_setpoint
                g_dev['cam'].setpoint = tommorow_night_setpoint
                g_dev['cam']._set_setpoint(tommorow_night_setpoint)


                # Need to trim th ecalibration directories of all files
                # Not within the tolerance limit from the setpoint
                darks_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/darks/'
                bias_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/biases/'

                # Need to not change things in the folder if regenerating masters
                if not self.currently_regenerating_masters:
                    # First check darks in root directory
                    print ("ROOT DIRECTORY DARKS")
                    for darkfile in glob(darks_path + '*.npy'):
                        if not 'temp' in darkfile:
                            tempdarktemp=float(darkfile.split('_')[-3])
                            #print (tempdarktemp)
                            if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                try:
                                    os.remove(darkfile)
                                except:
                                    pass
                        else:
                            try:
                                os.remove(darkfile)
                            except:
                                pass

                    # Then check each of the darks folder
                    for darkfolder in glob(darks_path + "*/"):
                        print (darkfolder)
                        for darkfile in glob(darkfolder + '*.npy'):
                            if not 'temp' in darkfile:
                                tempdarktemp=float(darkfile.split('_')[-3])
                                #print (tempdarktemp)
                                if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                    try:
                                        os.remove(darkfile)
                                    except:
                                        pass
                            else:
                                try:
                                    os.remove(darkfile)
                                except:
                                    pass

                    # First check biasess in root directory
                    print ("ROOT DIRECTORY BIASES")
                    for darkfile in glob(bias_path + '*.npy'):
                        if not 'temp' in darkfile:
                            tempdarktemp=float(darkfile.split('_')[-3])
                            #print (tempdarktemp)
                            if not (tempdarktemp-g_dev['cam'].temp_tolerance < tommorow_night_setpoint < tempdarktemp+g_dev['cam'].temp_tolerance):
                                try:
                                    os.remove(darkfile)
                                except:
                                    pass
                        else:
                            try:
                                os.remove(darkfile)
                            except:
                                pass

                if abs(tommorow_night_setpoint-current_night_setpoint) > 4:
                    plog("waiting an extra three minutes for camera to cool to different temperature")
                    time.sleep(180)

            # If there are no biases, then don't check for lightleaks.
            # This catches a bias and dark refresh... manually or at the transition of seasons.
            bias_path=g_dev['obs'].obsid_path + 'archive/' + g_dev['cam'].alias +'/localcalibrations/biases/'

            if len (glob(bias_path + '*.npy')) == 0:
                self.check_incoming_darks_for_light_leaks=False
            else:
                self.check_incoming_darks_for_light_leaks=True
            #breakpoint()
            #breakpoint()

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
                self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command({"filter": 'dk'}, {})

            if not g_dev['obs'].mountless_operation:
                g_dev['mnt'].park_command({}, {}) # Get there early

            # # Wait  aperiod of time for darkslides, filters, scopes to settle
            plog ("Waiting a one minute for everything to settle down before taking bias and darks.")
            plog ("To avoid light leaks from slow systems (e.g. darkslides, filter wheels etc.).")
            dark_wait_time=time.time()
            while (time.time() - dark_wait_time < 60):
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    self.bias_dark_latch = False
                    return
                if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
                    self.bias_dark_latch = False
                    break
                g_dev['obs'].request_scan_requests()
                time.sleep(5)

            if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:   #ephem is units of a day
                self.bias_dark_latch = False
                break     #Terminate Bias dark phase if within taking a dark would run over.

            b_d_to_do = dark_count
            try:
                stride = bias_count//dark_count
                plog("Tobor will interleave a long exposure dark every  " + str(stride) + "  biasdarks, short darks and biases.")
            except:
                stride = bias_count   #Just do all of the biases first.

            while b_d_to_do > 0:
                g_dev['obs'].request_scan_requests()
                min_to_do = 1
                b_d_to_do -= 1

                # Define exposure parameters
                exposures = [
                    (0.00004, "fourhundredmicrosecond_exposure_dark", 5),

                    (broadband_ss_biasdark_exp_time, "broadband_ss_biasdark", 2),
                    (2, "twosec_exposure_dark", 5),
                    (3.5, "threepointfivesec_exposure_dark", 5),
                    (5, "fivesec_exposure_dark", 5),
                    (7.5, "sevenpointfivesec_exposure_dark", 5),
                    (10, "tensec_exposure_dark", 2),
                    (15, "fifteensec_exposure_dark", 2),
                    (20, "twentysec_exposure_dark", 2),
                    (30, "thirtysec_exposure_dark", 2),
                    (0.0045, "pointzerozerofourfive_exposure_dark", 5),
                    (0.0004, "fortymicrosecond_exposure_dark", 5),
                    (0.015, "onepointfivepercent_exposure_dark", 5),
                    (0.05, "fivepercent_exposure_dark", 5),
                    (0.1, "tenpercent_exposure_dark", 5),
                    (0.25, "quartersec_exposure_dark", 5),
                    (0.5, "halfsec_exposure_dark", 5),
                    (0.75, "threequartersec_exposure_dark", 5),
                    (1.0, "onesec_exposure_dark", 5),
                    (1.5, "oneandahalfsec_exposure_dark", 5),
                ]

                # Iterate over exposure settings
                for exposure_time, image_type, count_multiplier in exposures:
                    #if exposure_time >= min_exposure:
                    if not self.collect_dark_frame(exposure_time, image_type, count_multiplier, stride, min_to_do, dark_exp_time, cycle_time, ending):
                        break

                # Collect additional frames
                if not self.collect_bias_frame(stride, stride, min_to_do, dark_exp_time, cycle_time, ending):
                    pass

                # Check for narrowband frame
                if not g_dev["fil"].null_filterwheel:
                    self.collect_dark_frame(narrowband_ss_biasdark_exp_time, "narrowband_ss_biasdark", 2, stride, min_to_do, dark_exp_time, cycle_time, ending)

                # Final long-exposure dark frame
                self.collect_dark_frame(dark_exp_time, "dark", 1, stride, min_to_do, dark_exp_time, cycle_time, ending)

                g_dev['obs'].request_scan_requests()
                if ephem.now() + 30/86400 >= ending:
                    self.bias_dark_latch = False
                    break

            plog(" Bias/Dark acquisition is finished normally.")
            if not g_dev['obs'].mountless_operation:
                g_dev['mnt'].park_command({}, {})


            # If the camera pixelscale is None then we are in commissioning mode and
            # need to restack the calibrations straight away
            # so this triggers off the stacking process to happen in a thread.
            if g_dev['cam'].pixscale == None:
                self.master_restack_queue.put( 'force', block=False)

            self.bias_dark_latch = False
            break
        self.bias_dark_latch = False

        if g_dev['cam'].temp_setpoint_by_season:
            # Here change the setpoint back to tonight's setpoint
            g_dev['cam'].current_setpoint = current_night_setpoint
            g_dev['cam'].setpoint = current_night_setpoint
            g_dev['cam']._set_setpoint(current_night_setpoint)

        g_dev['obs'].flush_command_queue()
        self.total_sequencer_control=False
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
                        plog ("Couldn't move orphan: " + str(orphanfile) +', deleting.')
                        g_dev['obs'].laterdelete_queue.put(orphanfile, block=False)

        # Add all fits.fz members to the AWS queue
        bigfzs=glob(orphan_path + '*.fz')

        for fzneglect in bigfzs:
            # If it is todays image, put it in priority ahead of the token, otherwise place it behind the token because it is some old potentially broken file.
            if str(g_dev["day"]) in fzneglect.split('orphans')[-1].replace('\\',''):
                g_dev['obs'].enqueue_for_PTRarchive(56000000, orphan_path, fzneglect.split('orphans')[-1].replace('\\',''))
            else:
                g_dev['obs'].enqueue_for_PTRarchive(56000002, orphan_path, fzneglect.split('orphans')[-1].replace('\\',''))
        bigtokens=glob(g_dev['obs'].obsid_path + 'tokens/*.token')
        for fzneglect in bigtokens:
            g_dev['obs'].enqueue_for_PTRarchive(56000001, g_dev['obs'].obsid_path + 'tokens/', fzneglect.split('tokens')[-1].replace('\\',''))


    def nightly_reset_script(self):
        # UNDERTAKING END OF NIGHT ROUTINES
        # Never hurts to make sure the telescope is parked for the night
        self.park_and_close()

        if g_dev['cam'].has_darkslide:
            g_dev['cam'].closeDarkslide()

        self.reported_on_observing_period_beginning=False

        self.rotator_has_been_homed_this_evening=False

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

        # Nightly clear out
        self.clear_archive_drive_of_old_files()


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
        self.obs.astro_events.calculate_events(endofnightoverride='yes')
        self.obs.astro_events.display_events()

        '''
        Send the config to aws.
        '''
        uri = f"{self.config['obs_id']}/config/"
        self.config['events'] = self.obs.astro_events.event_dict
        response = authenticated_request("PUT", uri, self.config)
        if response:
            plog("Config uploaded successfully.")

        # Resetting complete projects
        plog ("Nightly reset of complete projects")
        self.reset_completes()
        g_dev['obs'].events_new = None
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
        self.blockend= None
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
        g_dev["foc"].focus_tracker = [np.nan] * 10

        self.nightly_reset_complete = True

        g_dev['mnt'].theskyx_tracking_rescues = 0

        self.opens_this_evening=0

        self.stop_script_called=False
        self.stop_script_called_time=time.time()

        # No harm in doubly checking it has parked
        g_dev['mnt'].park_command({}, {})

        self.end_of_night_token_sent = False

        # Now time to regenerate the local masters
        self.master_restack_queue.put( 'g0', block=False)

        # Daily reboot of necessary windows 32 programs *Cough* Theskyx *Cough*
        if g_dev['mnt'].theskyx: # It is only the mount that is the reason theskyx needs to reset
            plog ("Got here")
            self.obs.kill_and_reboot_theskyx(-1,-1)
            plog ("But didn't get here")
        return


    def make_scaled_dark(self,input_folder, filename_start, masterBias, shapeImage, archiveDate, pipefolder, requesttype, temp_bias_level_min, calibhduheader):

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
            notcorrupt=True
            for file in inputList:
                try:
                    tempy=np.load(file, mmap_mode='r')
                    tempy=np.load(file)
                    tempmedian=bn.nanmedian(tempy)
                    if tempy.size < 1000:
                        plog ("corrupt dark skipped: " + str(file))
                        notcorrupt=False
                        del tempy
                        os.remove(file)
                        inputList.remove(file)

                    elif tempmedian < max(30, temp_bias_level_min) or tempmedian > 55000:
                        plog ("dark file with strange median skipped: " + str(file))
                        notcorrupt=False
                        del tempy
                        os.remove(file)
                        inputList.remove(file)

                except:
                    plog ("corrupt dark skipped: " + str(file))
                    notcorrupt=False
                    os.remove(file)
                    inputList.remove(file)

            if not notcorrupt:
                time.sleep(10)

            # Check if the latest file is older than the latest calibration
            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            latestfile=0
            for tem in inputList:
                filetime=os.path.getmtime(tem)
                if filetime > latestfile:
                    latestfile=copy.deepcopy(filetime)

            try:
                latestcalib=os.path.getmtime(g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits')
            except:
                latestcalib=time.time()-10000000000

            plog ("Inspecting dark set: " +str(filename_start))
            if latestfile < latestcalib and requesttype != 'force':
                plog ("There are no new darks since last super-dark was made. Skipping construction")
                masterDark=fits.open(g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits')
                masterDark= np.array(masterDark[0].data, dtype=np.float32)

            else:
                plog ("There is a new dark frame since the last super-dark was made")
                finalImage=np.zeros(shapeImage,dtype=float)
                # Store the biases in the memmap file
                PLDrive= [None] * len(inputList)
                exposures= [None] * len(inputList)
                i=0
                for file in inputList:
                    PLDrive[i] = np.load(file, mmap_mode='r')
                    try:
                        exposures[i]=float(file.split('_')[-2])
                    except:
                        plog(traceback.format_exc())
                    i=i+1

                # Get a chunk size that evenly divides the array
                chunk_size=8
                while not ( shapeImage[0] % chunk_size ==0):
                    chunk_size=chunk_size+1
                chunk_size=int(shapeImage[0]/chunk_size)

                holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                # iterate through the input, replace with ones, and write to output
                for i in range(shapeImage[0]):
                    if i % chunk_size == 0:
                        counter=0
                        for imagefile in range(len(PLDrive)):
                            holder[counter][0:chunk_size,:] = (copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)-copy.deepcopy(masterBias[i:i+chunk_size,:]).astype(np.float32))/exposures[counter]
                            counter=counter+1
                        finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)

                        # Wipe and restore files in the memmap file
                        # To clear RAM usage
                        PLDrive= [None] * len(inputList)
                        i=0
                        for file in inputList:
                            PLDrive[i] = np.load(file, mmap_mode='r')
                            i=i+1

                masterDark=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
                del finalImage


                tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
                calibhduheader['OBSTYPE'] = 'DARK'
                try:
                    # Save and upload master bias
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), calibhduheader, g_dev['obs'].calib_masters_folder, tempfrontcalib + filename_start+'_master_bin1.fits' ))

                    if filename_start in ['DARK','halfsecondDARK', '2secondDARK', '10secondDARK', '30secondDARK', 'broadbandssDARK', '1']:
                        g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.npy', copy.deepcopy(masterDark)))

                    # Store a version of the bias for the archive too
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark), calibhduheader, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits' ))

                    if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + filename_start+'_master_bin1.npy',copy.deepcopy(masterDark)))

                except Exception as e:
                    plog(traceback.format_exc())
                    plog ("Could not save dark frame: ",e)
                    # # breakpoint()

                plog (filename_start+ " Exposure Dark reconstructed: " +str(time.time()-calibration_timer))
                g_dev["obs"].send_to_user(filename_start+ " Exposure Dark calibration frame created.")

            return masterDark

    def make_bias_dark(self,input_folder, filename_start, masterBias, shapeImage, archiveDate, pipefolder,requesttype,temp_bias_level_min, calibhduheader):


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
            notcorrupt=True
            for file in inputList:
                try:
                    tempy=np.load(file, mmap_mode='r')
                    tempy=np.load(file)
                    tempmedian=bn.nanmedian(tempy)
                    if tempy.size < 1000:
                        plog ("corrupt dark skipped: " + str(file))
                        del tempy
                        notcorrupt=False
                        os.remove(file)
                        inputList.remove(file)
                    elif tempmedian < max(30, temp_bias_level_min) or tempmedian > 55000:
                        plog ("dark file with strange median skipped: " + str(file))
                        del tempy
                        notcorrupt=False
                        os.remove(file)
                        inputList.remove(file)
                except:
                    plog ("corrupt dark skipped: " + str(file))
                    os.remove(file)
                    notcorrupt=False
                    inputList.remove(file)

            if not notcorrupt:
                time.sleep(10)

            # Check if the latest file is older than the latest calibration
            tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
            latestfile=0
            for tem in inputList:
                filetime=os.path.getmtime(tem)
                if filetime > latestfile:
                    latestfile=copy.deepcopy(filetime)
            try:
                latestcalib=os.path.getmtime(g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits')
            except:
                latestcalib=time.time()-10000000000

            plog ("Inspecting dark set: " +str(filename_start))
            if latestfile < latestcalib and requesttype != 'force':
                plog ("There are no new darks since last super-dark was made. Skipping construction")
                masterDark=fits.open(g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits')
                masterDark= np.array(masterDark[0].data, dtype=np.float32)

            else:
                plog ("There is a new dark frame since the last super-dark was made")

                finalImage=np.zeros(shapeImage,dtype=float)

                # Store the biases in the memmap file
                PLDrive= [None] * len(inputList)
                exposures= [None] * len(inputList)
                i=0
                for file in inputList:
                    PLDrive[i] = np.load(file, mmap_mode='r')
                    exposures[i]=float(file.split('_')[-2])
                    i=i+1

                # Get a chunk size that evenly divides the array
                chunk_size=8
                while not ( shapeImage[0] % chunk_size ==0):
                    chunk_size=chunk_size+1
                    #plog (chunk_size)
                chunk_size=int(shapeImage[0]/chunk_size)

                holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                # iterate through the input, replace with ones, and write to output
                for i in range(shapeImage[0]):
                    if i % chunk_size == 0:
                        #plog (i)
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
                            PLDrive[i] = np.load(file, mmap_mode='r')
                            i=i+1

                masterDark=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
                del finalImage


                tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
                calibhduheader['OBSTYPE'] = 'DARK'
                try:

                    # Save and upload master bias
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark.astype(np.uint16)), calibhduheader, g_dev['obs'].calib_masters_folder, tempfrontcalib +filename_start+'_master_bin1.fits' ))


                    #if filename_start in ['tensecBIASDARK','thirtysecBIASDARK']:
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + tempfrontcalib + filename_start+'_master_bin1.npy', copy.deepcopy(masterDark.astype(np.uint16))))



                    # Store a version of the bias for the archive too
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits', copy.deepcopy(masterDark.astype(np.uint16)), calibhduheader, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + filename_start+'_master_bin1.fits' ))


                    if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + filename_start+'_master_bin1.npy',copy.deepcopy(masterDark.astype(np.uint16))))

                except Exception as e:
                    plog(traceback.format_exc())
                    plog ("Could not save dark frame: ",e)
                    #breakpoint()

                plog (filename_start+ " Exposure Dark reconstructed: " +str(time.time()-calibration_timer))
                g_dev["obs"].send_to_user(filename_start+ " Exposure Dark calibration frame created.")

            return masterDark

    def regenerate_local_masters(self, requesttype):


        plog ("killing local problem programs")


        try:
            os.system("taskkill /IM FitsLiberator.exe /F")
            os.system("taskkill /IM Mira_Pro_x64_8.exe /F")
            os.system("taskkill /IM Aladin.exe /F")
        except:
            pass

        self.currently_regenerating_masters = True

        g_dev["obs"].send_to_user("Currently regenerating local masters.")

        if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
            pipefolder = g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias
            if not os.path.exists(g_dev['obs'].config['pipe_archive_folder_path']+'/calibrations'):
                os.makedirs(g_dev['obs'].config['pipe_archive_folder_path'] + '/calibrations')

            if not os.path.exists(g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias):
                os.makedirs(g_dev['obs'].config['pipe_archive_folder_path'] +'/calibrations/'+ g_dev['cam'].alias)
        else:
            pipefolder=''


        # Make header for calibration files
        calibhdu = fits.PrimaryHDU()
        calibhduheader=copy.deepcopy(calibhdu.header)
        calibhduheader['RLEVEL'] = 99
        calibhduheader['PROPID'] = 'INGEST-CALIB'
        calibhduheader['DATE-OBS'] = (
            datetime.datetime.isoformat(
                datetime.datetime.utcfromtimestamp(time.time())
            ),
            "Start date and time of observation"
        )
        calibhduheader["DAY-OBS"] = (g_dev["day"],
                                "Date at start of observing night")   #20250112 WER conservative addition of thie keyword so injestion less likely to fail.
        calibhduheader['INSTRUME'] = g_dev['cam'].config["name"], "Name of camera"
        calibhduheader['SITEID'] = g_dev['obs'].config["wema_name"].replace("-", "").replace("_", "")
        calibhduheader['TELID'] = g_dev['obs'].obs_id
        calibhduheader['OBSTYPE'] = 'DARK'
        calibhduheader['BLKUID'] = 1234
        calibhduheader["OBSID"] = g_dev['obs'].obs_id

        # NOW to get to the business of constructing the local calibrations
        # Start with biases
        # Get list of biases
        plog ("Regenerating bias")
        calibration_timer=time.time()
        darkinputList=(glob(g_dev['obs'].local_dark_folder +'*.n*'))
        inputList=(glob(g_dev['obs'].local_bias_folder +'*.n*'))
        archiveDate=str(datetime.date.today()).replace('-','')
        # Test each file actually opens
        notcorrupt=True
        for file in inputList:
            try:
                tempy=np.load(file, mmap_mode='r')
                tempy=np.load(file)
                tempmedian=bn.nanmedian(tempy)
                if tempy.size < 1000:
                    plog ("tiny bias file skipped: " + str(file))
                    del tempy
                    os.remove(file)
                    notcorrupt=False
                    inputList.remove(file)

                elif tempmedian < 30 or tempmedian > 3000:
                    plog ("bias file with strange median skipped: " + str(file))
                    del tempy
                    os.remove(file)
                    notcorrupt=False
                    inputList.remove(file)

            except:
                plog ("corrupt bias skipped: " + str(file))
                os.remove(file)
                notcorrupt=False
                inputList.remove(file)

        if not notcorrupt:
            time.sleep(10)

        tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'

        if len(inputList) == 0 or len(darkinputList) == 0:# or len(inputList) == 1 or len(darkinputList) == 1:
            plog ("Not reprocessing local masters as there are not enough biases or darks")
        else:

            # Get the size of the camera
            hdutest=np.load(inputList[0], mmap_mode='r')
            shapeImage=hdutest.shape
            del hdutest

            # Make an array for the bad pixel map
            bad_pixel_mapper_array=np.full((shapeImage[0],shapeImage[1]), False)

            # Check if the latest file is older than the latest calibration
            latestfile=0
            for tem in inputList:
                filetime=os.path.getmtime(tem)
                if filetime > latestfile:
                    latestfile=copy.deepcopy(filetime)
            try:
                latestcalib=os.path.getmtime(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits')
            except:
                latestcalib=time.time()-10000000000

            plog ("Inpecting bias set")
            if latestfile < latestcalib and requesttype != 'force':
                plog ("There are no new biases since last super-bias was made. Skipping construction")
                masterBias=fits.open(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits')
                masterBias= np.array(masterBias[0].data, dtype=np.float32)
                temp_bias_level_median=bn.nanmedian(masterBias)
                temp_bias_level_min=bn.nanmin(masterBias)

            else:
                plog ("There is a new bias frame since the last super-bias was made")

                # Store the biases in the memmap file
                PLDrive = [None] * len(inputList)
                i=0
                for file in inputList:
                    PLDrive[i] = np.load(file, mmap_mode='r')
                    i=i+1
                # finalImage array
                finalImage=np.zeros(shapeImage, dtype=np.float32)

                try:
                    # create an empty array to hold each chunk
                    # the size of this array will determine the amount of RAM usage


                    # Get a chunk size that evenly divides the array
                    chunk_size=8
                    while not ( shapeImage[0] % chunk_size ==0):
                        chunk_size=chunk_size+1
                    chunk_size=int(shapeImage[0]/chunk_size)
                    #plog("Calculated chunk_size:  ", chunk_size)
                    holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                    # iterate through the input, replace with ones, and write to output

                    # Maybe also only reform the memmap if chunk size bigger.
                    reloader_trigger=0
                    for i in range(shapeImage[0]):
                        #plog("Line 3117 @  ", time.time(), "i= ", i)
                        if i % chunk_size == 0:
                            counter=0
                            for imagefile in range(len(PLDrive)):
                                holder[counter][0:chunk_size,:] = copy.deepcopy(PLDrive[counter][i:i+chunk_size,:]).astype(np.float32)
                                counter=counter+1
                            finalImage[i:i+chunk_size,:]=bn.nanmedian(holder, axis=0)
                            reloader_trigger=reloader_trigger+chunk_size
                            if reloader_trigger > 1000:
                                # Wipe and restore files in the memmap file
                                # To clear RAM usage
                                PLDrive= [None] * len(inputList)
                                i=0
                                for file in inputList:
                                    PLDrive[i] = np.load(file, mmap_mode='r')
                                    i=i+1
                                reloader_trigger=0

                except:
                    plog(traceback.format_exc())

                masterBias=copy.deepcopy(np.asarray(finalImage).astype(np.float32))

                temp_bias_level_median=bn.nanmedian(masterBias)
                temp_bias_level_min=bn.nanmin(masterBias)
                del finalImage
                del holder

                # calibhduheader['OBSTYPE'] = 'BIAS'

                try:
                    # Save and upload master bias
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.fits', copy.deepcopy(masterBias.astype(np.uint16)), calibhduheader, g_dev['obs'].calib_masters_folder, tempfrontcalib + 'BIAS_master_bin1.fits' ))
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'BIAS_master_bin1.npy', copy.deepcopy(masterBias.astype(np.uint16))))

                     # Store a version of the bias for the archive too
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits', copy.deepcopy(masterBias.astype(np.uint16)), calibhduheader, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'BIAS_master_bin1.fits' ))

                    if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        g_dev['obs'].to_slow_process(200000000, ('numpy_array_save',pipefolder + '/'+tempfrontcalib + 'BIAS_master_bin1.npy',copy.deepcopy(masterBias.astype(np.uint16))))
                except Exception as e:
                    plog ("Could not save bias frame: ",e)

                try:
                    g_dev['cam'].biasFiles.update({'1': masterBias.astype(np.float32)})
                except:
                    plog("Bias frame master re-upload did not work.")

                plog ("Bias reconstructed: " +str(time.time()-calibration_timer))
                calibration_timer=time.time()
                g_dev["obs"].send_to_user("Bias calibration frame created.")

            # A theskyx reboot catch
            while True:
                try:
                    g_dev['cam'].camera_known_gain <1000
                    break
                except:
                    plog ("waiting for theskyx to reboot")

            num_of_biases=len(inputList)

            # Now that we have the master bias, we can estimate the readnoise actually
            # by comparing the standard deviations between the bias and the masterbias
            if g_dev['cam'].camera_known_gain <1000:
                # readnoise_array=[]
                # post_readnoise_array=[]
                # i=0
                # for file in inputList:

                #     hdu1data=np.load(file)-masterBias
                #     hdu1data = hdu1data[500:-500,500:-500]
                #     stddiffimage=bn.nanstd(pow(pow(hdu1data,2),0.5))

                #     est_read_noise= (stddiffimage * g_dev['cam'].camera_known_gain) / 1.414
                #     readnoise_array.append(est_read_noise)
                #     post_readnoise_array.append(stddiffimage)
                #     i=i+1

                # readnoise_array=np.array(readnoise_array)

                # #breakpoint()



                def estimate_read_noise_chunked(bias_frames, frame_shape, gain=1.0, chunk_size=10, masterBias=None):
                    """
                    Estimate the read noise of a CMOS sensor from a set of bias frames processed in chunks.

                    Parameters:
                        bias_frame_generator (generator): A generator that yields 2D NumPy arrays representing bias frames.
                        frame_shape (tuple): The shape of each bias frame (height, width).
                        num_frames (int): The total number of bias frames.
                        gain (float): The gain in electrons per ADU (default is 1.0).

                    Returns:
                        float: The estimated read noise in electrons.
                        float: The estimated read noise in ADU.
                        np.ndarray: The variance frame (pixel-wise variance).
                    """
                    num_frames = len(bias_frames)

                    pixel_variance = np.zeros(frame_shape, dtype=np.float64)

                    for frame in bias_frames:
                        residual = frame - masterBias
                        pixel_variance += (residual ** 2) / (num_frames - 1)

                    # Step 3: Compute the mean variance across all pixels
                    mean_variance = bn.nanmean(pixel_variance)
                    #stdev_variance = bn.nanstd(pixel_variance)

                    # Step 4: Compute the read noise in ADU
                    read_noise_adu = np.sqrt(mean_variance)
                    read_noise_adu_stdev= np.std(np.sqrt(pixel_variance))

                    # Step 5: Convert read noise to electrons using the gain
                    read_noise_electrons = read_noise_adu * gain
                    read_noise_electrons_stdev = read_noise_adu_stdev * gain

                    return read_noise_electrons, read_noise_adu, read_noise_electrons_stdev, read_noise_adu_stdev,  pixel_variance


                frame_shape=masterBias.shape

                # Load the memmap files into a list
                bias_frames= [np.load(file, mmap_mode='r') for file in inputList]

                # Estimate the read noise
                read_noise_electrons, read_noise_adu, read_noise_electrons_stdev, read_noise_adu_stdev, variance_frame = estimate_read_noise_chunked(bias_frames, frame_shape, g_dev['cam'].camera_known_gain, chunk_size=10, masterBias=masterBias)

                del bias_frames

                print(f"Estimated Read Noise: {read_noise_electrons:.2f} e- (electrons), stdev: "+ str(read_noise_electrons_stdev))
                print(f"Estimated Read Noise: {read_noise_adu:.2f} ADU, stdev: " + str(read_noise_adu_stdev))

                # Write out the variance array
                try:
                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + 'readnoise_variance_adu.npy', copy.deepcopy(variance_frame.astype('float32'))))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    # Save and upload master bias
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'readnoise_variance_adu.fits', copy.deepcopy(variance_frame.astype('float32')), calibhduheader, g_dev['obs'].calib_masters_folder, tempfrontcalib + 'readnoise_variance_adu.fits' ))

                    # Store a version of the bias for the archive too
                    g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'readnoise_variance_adu.fits', copy.deepcopy(variance_frame.astype('float32')), calibhduheader, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'readnoise_variance_adu.fits' ))

                    if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', pipefolder + '/' + tempfrontcalib + 'readnoise_variance_adu.npy', copy.deepcopy(variance_frame.astype('float32'))))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                except Exception as e:
                    plog ("Could not save variance frame: ",e)





            # Bad pixel accumulator for the bias frame
            img_temp_median=bn.nanmedian(masterBias)
            img_temp_stdev=bn.nanstd(masterBias)
            above_array=(masterBias > (img_temp_median + (10 * img_temp_stdev)))
            below_array=(masterBias < (img_temp_median - (10 * img_temp_stdev)))
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array+below_array

############################################# DARK

            scaled_darklist=[
                [g_dev['obs'].local_dark_folder                 , 'DARK','1'],
                [g_dev['obs'].local_dark_folder+ 'halfsecdarks/', 'halfsecondDARK', 'halfsec_exposure_dark' ],
                [g_dev['obs'].local_dark_folder+ 'twosecdarks/', '2secondDARK', 'twosec_exposure_dark' ],
                [g_dev['obs'].local_dark_folder+ 'tensecdarks/', '10secondDARK', 'tensec_exposure_dark'],
                [g_dev['obs'].local_dark_folder+ 'tensecdarks/', '30secondDARK', 'thirtysec_exposure_dark'],
                [g_dev['obs'].local_dark_folder+ 'broadbanddarks/', 'broadbandssDARK', 'broadband_ss_dark' ]
                ]

            # If you don't have a filter wheel, then you don't have any distinction between broadband or narrowband darks
            if not g_dev["fil"].null_filterwheel:
                scaled_darklist.append([g_dev['obs'].local_dark_folder+ 'narrowbanddarks/', 'narrowbandssDARK','narrowband_ss_dark'])

            bias_darklist=[
                [g_dev['obs'].local_dark_folder+ 'halfsecdarks/','halfsecBIASDARK', 'halfsec'],
                [g_dev['obs'].local_dark_folder+ 'twosecdarks/', 'twosecBIASDARK', 'twosec' ],
                [g_dev['obs'].local_dark_folder+ 'threepointfivesecdarks/', 'threepointfivesecBIASDARK', 'threepointfivesec'],
                [g_dev['obs'].local_dark_folder+ 'fivesecdarks/', 'fivesecBIASDARK','fivesec' ],
                [g_dev['obs'].local_dark_folder+ 'sevenpointfivesecdarks/', 'sevenpointfivesecBIASDARK','sevenpointfivesec' ],
                [g_dev['obs'].local_dark_folder+ 'tensecdarks/','tensecBIASDARK', 'tensec' ],
                [g_dev['obs'].local_dark_folder+ 'fifteensecdarks/', 'fifteensecBIASDARK','fifteensec' ],
                [g_dev['obs'].local_dark_folder+ 'twentysecdarks/', 'twentysecBIASDARK', 'twentysec'],
                [g_dev['obs'].local_dark_folder+ 'thirtysecdarks/', 'thirtysecBIASDARK', 'thirtysec'],
                [g_dev['obs'].local_dark_folder+ 'broadbanddarks/', 'broadbandssBIASDARK', 'broadband_ss_biasdark']
                ]

            # There is no point creating biasdark exposures below the min_flat_exposure or min_exposure time aside from the scaled dark values.
            min_flat_exposure = min(float(g_dev['cam'].settings['min_flat_exposure']),float(g_dev['cam'].settings['min_exposure']))

            if min_flat_exposure <= 0.00004:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'fortymicroseconddarks/', 'fortymicrosecondBIASDARK','fortymicrosecond' ])

            if min_flat_exposure <= 0.0004:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'fourhundredmicroseconddarks/', 'fourhundredmicrosecondBIASDARK','fourhundredmicrosecond' ])

            if min_flat_exposure <= 0.0045:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'pointzerozerofourfivedarks/', 'pointzerozerofourfiveBIASDARK','pointzerozerofourfive' ])

            if min_flat_exposure <= 0.015:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'onepointfivepercentdarks/', 'onepointfivepercentBIASDARK','onepointfivepercent' ])

            if min_flat_exposure <= 0.05:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'fivepercentdarks/', 'fivepercentBIASDARK','fivepercent' ])

            if min_flat_exposure <= 0.1:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'tenpercentdarks/','tenpercentBIASDARK','tenpercent'])

            if min_flat_exposure <= 0.25:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'quartersecdarks/','quartersecBIASDARK', 'quartersec' ])


            if min_flat_exposure <= 0.75:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'sevenfivepercentdarks/', 'sevenfivepercentBIASDARK', 'sevenfivepercent'])

            if min_flat_exposure <= 1.0:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'onesecdarks/', 'onesecBIASDARK', 'onesec'])

            if min_flat_exposure <= 1.5:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'oneandahalfsecdarks/', 'oneandahalfsecBIASDARK','oneandahalfsec'])

            # If you don't have a filter wheel, then you don't have any distinction between broadband or narrowband darks
            if not g_dev["fil"].null_filterwheel:
                bias_darklist.append([g_dev['obs'].local_dark_folder+ 'narrowbanddarks/', 'narrowbandssBIASDARK', 'narrowband_ss_biasdark'])

            # CLEAR OUT OLD TEMPFILES
            darkdeleteList=(glob(g_dev['obs'].local_dark_folder +'/*tempbiasdark.n*'))
            for file in darkdeleteList:
                try:
                    os.remove(file)
                except:
                    plog ("Couldnt remove old dark file: " + str(file))

            for entry in scaled_darklist:
                processedDark = self.make_scaled_dark(entry[0],entry[1], masterBias, shapeImage, archiveDate, pipefolder,requesttype,temp_bias_level_min, calibhduheader)
                try:
                    g_dev['cam'].darkFiles.update({entry[2]: processedDark.astype(np.float32)})
                except:
                    plog("Dark frame master re-upload did not work.")

            for entry in bias_darklist:
                processedDark = self.make_bias_dark(entry[0],entry[1], masterBias, shapeImage, archiveDate, pipefolder,requesttype,temp_bias_level_min,calibhduheader)
                if entry[2] ==  'broadband_ss_biasdark' or entry[2] == 'narrowband_ss_biasdark':
                    g_dev['cam'].darkFiles.update({entry[2]: processedDark.astype(np.float32)})
                else:
                    try:
                        np.save(g_dev['obs'].local_dark_folder +'/'+entry[2] +'tempbiasdark.npy', processedDark.astype(np.float32))
                    except:
                        plog("Dark frame master re-upload did not work.")

            # Bad pixel accumulator from long exposure dark
            img_temp_median=bn.nanmedian(g_dev['cam'].darkFiles['1'])
            img_temp_stdev=bn.nanstd(g_dev['cam'].darkFiles['1'])
            above_array=(g_dev['cam'].darkFiles['1'] > 20)
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

            # Bad pixel accumulator from broadband exposure dark
            img_temp_median=bn.nanmedian(g_dev['cam'].darkFiles['broadband_ss_dark' ])
            img_temp_stdev=bn.nanstd(g_dev['cam'].darkFiles['broadband_ss_dark' ])
            above_array=(g_dev['cam'].darkFiles['broadband_ss_dark' ] > 20)
            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

            # Bad pixel accumulator from narrowband exposure dark
            if not g_dev["fil"].null_filterwheel:
                img_temp_median=bn.nanmedian(g_dev['cam'].darkFiles['narrowband_ss_dark'])
                img_temp_stdev=bn.nanstd(g_dev['cam'].darkFiles['narrowband_ss_dark'])
                above_array=(g_dev['cam'].darkFiles['narrowband_ss_dark'] > 20)
                bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

            # NOW that we have a master bias and a master dark, time to step through the flat frames!
            tempfilters=glob(g_dev['obs'].local_flat_folder + "*/")
            estimated_flat_gain=[]
            flat_gains={}

            broadband_ss_biasdark_exp_time = g_dev['cam'].settings['smart_stack_exposure_time']
            narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * g_dev['cam'].settings['smart_stack_exposure_NB_multiplier']
            dark_exp_time = g_dev['cam'].settings['dark_exposure']

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

                    inputList=(glob(g_dev['obs'].local_flat_folder + filtercode + '/*.n*'))

                    # Test each flat file actually opens
                    notcorrupt=True
                    for file in inputList:
                        try:
                            hdu1data = np.load(file, mmap_mode='r')
                            hdu1data = np.load(file)
                            tempmedian=bn.nanmedian(hdu1data)
                            if hdu1data.size < 1000:
                                plog ("corrupt flat skipped: " + str(file))

                                del hdu1data
                                os.remove(file)
                                notcorrupt=False
                                time.sleep(0.2)
                                inputList.remove(file)

                            elif os.stat(file).st_size < 5000:
                                plog ("corrupt flat skipped: " + str(file))

                                del hdu1data
                                os.remove(file)
                                notcorrupt=False
                                time.sleep(0.2)
                                inputList.remove(file)

                            elif tempmedian < max(1000, temp_bias_level_median+200) or tempmedian > 55000:
                                plog ("flat file with strange median skipped: " + str(file))
                                del hdu1data
                                os.remove(file)
                                notcorrupt=False
                                time.sleep(0.2)
                                inputList.remove(file)

                        except:
                            plog ("corrupt flat skipped: " + str(file))

                            os.remove(file)
                            inputList.remove(file)

                    if not notcorrupt:
                        time.sleep(10)

                    inputList=(glob(g_dev['obs'].local_flat_folder + filtercode + '/*.n*'))

                    # FLATS
                    single_filter_camera_gains=[]
                    if len(inputList) == 0 or len(inputList) == 1:
                        plog ("Not doing " + str(filtercode) + " flat. Not enough available files in directory.")
                    else:

                        # Check if the latest file is older than the latest calibration
                        tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
                        latestfile=0
                        for tem in inputList:
                            filetime=os.path.getmtime(tem)
                            if filetime > latestfile:
                                latestfile=copy.deepcopy(filetime)
                        try:
                            latestcalib=os.path.getmtime(g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy')
                        except:
                            latestcalib=time.time()-10000000000

                        plog ("Inspecting flats for filter: " + str(filtercode))
                        if latestfile < latestcalib and requesttype != 'force':
                            plog ("There are no new flats since last super-flat was made. Skipping construction")
                            temporaryFlat=np.load(g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy')
                            # Bad pixel accumulator
                            img_temp_median=bn.nanmedian(temporaryFlat)
                            img_temp_stdev=bn.nanstd(temporaryFlat)
                            above_array=(temporaryFlat > (img_temp_median + (10 * img_temp_stdev)))
                            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

                        else:
                            plog ("There is a new flat frame since the last super-flat was made")

                            while True:

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
                                    try:
                                        hdu1data = np.load(file)
                                        tempmedian=bn.nanmedian(hdu1data)
                                        # Last line of defence against dodgy images sneaking through.
                                        if tempmedian < max(1000, temp_bias_level_median+200) or tempmedian > 55000:
                                            a = np.empty((shapeImage[0],shapeImage[1]))
                                            a[:] = np.nan
                                            PLDrive[i] = copy.deepcopy(a)
                                            plog ("failed on a flat component. Placing an nan array. ")
                                        else:

                                            hdu1exp=float(file.split('_')[-2])
                                            fraction_through_range=0
                                            # This try/except is here because if there is a missing dark
                                            # we can always just revert to using the long dark.
                                            try:
                                                if hdu1exp == 0.00004 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fortymicrosecond' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fortymicrosecond' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.0004 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fourhundredmicrosecond' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fourhundredmicrosecond' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.0045 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'pointzerozerofourfive' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'pointzerozerofourfive' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.015 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'onepointfivepercent' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'onepointfivepercent' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.05 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fivepercent' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fivepercent' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.1 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'tenpercent' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'tenpercent' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.25 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'quartersec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'quartersec' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'halfsec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'halfsec' +'tempbiasdark.npy')
                                                elif hdu1exp == 0.75 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'sevenfivepercent' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'sevenfivepercent' +'tempbiasdark.npy')
                                                elif hdu1exp == 1.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'onesec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'onesec' +'tempbiasdark.npy')
                                                elif hdu1exp == 1.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'oneandahalfsec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'oneandahalfsec' +'tempbiasdark.npy')
                                                elif hdu1exp == 2.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'twosec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'twosec' +'tempbiasdark.npy')
                                                elif hdu1exp == 3.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'threepointfivesec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'threepointfivesec' +'tempbiasdark.npy')
                                                elif hdu1exp == 5.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fivesec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fivesec' +'tempbiasdark.npy')
                                                elif hdu1exp == 7.5 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'sevenpointfivesec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'sevenpointfivesec' +'tempbiasdark.npy')
                                                elif hdu1exp == 10.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'tensec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'tensec' +'tempbiasdark.npy')
                                                elif hdu1exp == 15.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'fifteensec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'fifteensec' +'tempbiasdark.npy')
                                                elif hdu1exp == 20.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'twentysec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'twentysec' +'tempbiasdark.npy')
                                                elif hdu1exp == 30.0 and os.path.exists(g_dev['obs'].local_dark_folder +'/'+'thirtysec' +'tempbiasdark.npy'):
                                                    flatdebiaseddedarked=hdu1data -np.load(g_dev['obs'].local_dark_folder +'/'+'thirtysec' +'tempbiasdark.npy')
                                                elif hdu1exp == broadband_ss_biasdark_exp_time:
                                                    flatdebiaseddedarked=hdu1data -g_dev['cam'].darkFiles['broadband_ss_biasdark']
                                                elif hdu1exp == narrowband_ss_biasdark_exp_time and not g_dev["fil"].null_filterwheel:
                                                    flatdebiaseddedarked=hdu1data -g_dev['cam'].darkFiles['narrowband_ss_biasdark']
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
                                                elif hdu1exp <= narrowband_ss_biasdark_exp_time and not g_dev["fil"].null_filterwheel:
                                                    fraction_through_range=(hdu1exp-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                                                    tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['narrowband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['broadband_ss_dark'])
                                                    flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                                    del tempmasterDark
                                                elif dark_exp_time > narrowband_ss_biasdark_exp_time and not g_dev["fil"].null_filterwheel:
                                                    fraction_through_range=(hdu1exp-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                                                    tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['1']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['narrowband_ss_dark'])
                                                    flatdebiaseddedarked=(hdu1data-masterBias)-(tempmasterDark*hdu1exp)
                                                    del tempmasterDark
                                                elif not g_dev["fil"].null_filterwheel:
                                                    flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['narrowband_ss_dark']*hdu1exp)
                                                else:
                                                    flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['1']*hdu1exp)
                                            except:
                                                flatdebiaseddedarked=(hdu1data-masterBias)-(g_dev['cam'].darkFiles['1']*hdu1exp)

                                            del hdu1data

                                            # Normalising flat file
                                            if not g_dev['cam'].settings["is_osc"]:
                                                normalising_factor=bn.nanmedian(flatdebiaseddedarked)
                                                flatdebiaseddedarked = flatdebiaseddedarked/normalising_factor
                                                # Naning bad entries into master flat
                                                flatdebiaseddedarked[flatdebiaseddedarked < 0.25] = np.nan
                                                flatdebiaseddedarked[flatdebiaseddedarked > 2.0] = np.nan
                                                # Rescaling median once nan'ed
                                                flatdebiaseddedarked = flatdebiaseddedarked/bn.nanmedian(flatdebiaseddedarked)
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
                                                    oscmedian=bn.nanmedian(oscimage)
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
                                                flatdebiaseddedarked = flatdebiaseddedarked/bn.nanmedian(flatdebiaseddedarked)

                                            # Make new filename
                                            tempfile=file.replace('\\','/').split('/')
                                            tempfile[-1]='tempcali_' + tempfile[-1]
                                            tempfile="/".join(tempfile)

                                            np.save(tempfile, flatdebiaseddedarked)
                                            del flatdebiaseddedarked
                                            temp_flat_file_list.append(tempfile)
                                            PLDrive[i] = np.load(tempfile, mmap_mode='r')
                                            i=i+1
                                    except:
                                        a = np.empty((shapeImage[0],shapeImage[1]))
                                        a[:] = np.nan
                                        PLDrive[i] = copy.deepcopy(a)
                                        plog ("failed on a flat component. Placing an nan array. ")
                                        plog(traceback.format_exc())
                                        i=i+1

                                plog ("Insert flats into megaarray: " +str(time.time()-calibration_timer))

                                finalImage=np.zeros(shapeImage, dtype=np.float32)

                                # create an empty array to hold each chunk
                                # the size of this array will determine the amount of RAM usage
                                # Get a chunk size that evenly divides the array
                                chunk_size=8
                                while not ( shapeImage[0] % chunk_size ==0):
                                    chunk_size=chunk_size+1
                                chunk_size=int(shapeImage[0]/chunk_size)

                                holder = np.zeros([len(PLDrive),chunk_size,shapeImage[1]], dtype=np.float32)

                                # iterate through the input, replace with ones, and write to output
                                for i in range(shapeImage[0]):
                                    if i % chunk_size == 0:
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
                                            PLDrive[i] = np.load(file, mmap_mode='r')
                                            i=i+1

                                plog ("Median stack flat: " +str(time.time()-calibration_timer))

                                # Assessing flat components
                                nanstd_collector=[]
                                for flat_component in range(len(inputList)):
                                    tempdivide=PLDrive[flat_component] / finalImage
                                    tempstd=bn.nanstd(tempdivide)
                                    nanstd_collector.append(tempstd)

                                med_std=np.array(bn.nanmedian(nanstd_collector))
                                std_std=np.array(np.std(nanstd_collector))

                                delete_flat_components=[]
                                for counterflat in range(len(nanstd_collector)):
                                    if nanstd_collector[counterflat] > (med_std + 5 * std_std):
                                        delete_flat_components.append(counterflat)

                                if len(delete_flat_components) < math.ceil(0.1*len(nanstd_collector)):
                                    break

                                # Remove problematic flat images from squishener so we can re-run the flat.
                                for index in sorted(delete_flat_components, reverse=True):
                                    del inputList[index]
                                del PLDrive

                                plog ("REDOING FLAT. TOO MANY OUTLIERS: " + str(len(delete_flat_components)))

                            plog ("Checked component flats vs stacked flat: " +str(time.time()-calibration_timer))

                            del PLDrive

                            temporaryFlat=copy.deepcopy(np.asarray(finalImage).astype(np.float32))
                            del finalImage

                            # Bad pixel accumulator
                            img_temp_median=bn.nanmedian(temporaryFlat)
                            img_temp_stdev=bn.nanstd(temporaryFlat)
                            above_array=(temporaryFlat > (img_temp_median + (10 * img_temp_stdev)))
                            bad_pixel_mapper_array=bad_pixel_mapper_array+above_array

                            temporaryFlat[temporaryFlat == inf] = np.nan
                            temporaryFlat[temporaryFlat == -inf] = np.nan
                            temporaryFlat[temporaryFlat < 0.5] = np.nan
                            temporaryFlat[temporaryFlat > 2.0] = np.nan
                            pre_num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))

                            # Interpolating Nans
                            last_num_of_nans=846753876359.0
                            while pre_num_of_nans > 0:
                                # Fix up any glitches in the flat
                                num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))

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

                                temporaryFlat[temporaryFlat == inf] = np.nan
                                temporaryFlat[temporaryFlat == -inf] = np.nan
                                temporaryFlat[temporaryFlat < 0.5] = np.nan
                                temporaryFlat[temporaryFlat > 2.0] = np.nan

                                pre_num_of_nans=np.count_nonzero(np.isnan(temporaryFlat))

                            if np.count_nonzero(np.isnan(temporaryFlat)) > 0:
                                plog ("No improvement with last interpolation attempt.")
                                plog ("Filling remaining nans with median")
                                temporaryFlat=np.nan_to_num(temporaryFlat, nan = bn.nanmedian(temporaryFlat))

                            plog ("Interpolated flat: " +str(time.time()-calibration_timer))

                            calibhduheader['OBSTYPE'] = 'SKYFLAT'

                            try:
                                g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy', copy.deepcopy(temporaryFlat)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                                # Save and upload master bias
                                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', copy.deepcopy(temporaryFlat), calibhduheader, g_dev['obs'].calib_masters_folder, tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits' ))

                                # Store a version of the bias for the archive too
                                g_dev['obs'].to_slow_process(200000000, ('fits_file_save_and_UIqueue', g_dev['obs'].calib_masters_folder + 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits', copy.deepcopy(temporaryFlat), calibhduheader, g_dev['obs'].calib_masters_folder, 'ARCHIVE_' +  archiveDate + '_' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.fits' ))

                                if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                                    g_dev['obs'].to_slow_process(200000000, ('numpy_array_save', pipefolder + '/' + tempfrontcalib + 'masterFlat_'+ str(filtercode) + '_bin1.npy', copy.deepcopy(temporaryFlat)))#, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                            except Exception as e:
                                plog ("Could not save flat frame: ",e)

                            plog ("Saved flat: " +str(time.time()-calibration_timer))

                            # Now to estimate gain from flats
                            for fullflat in inputList:
                                hdu1data = np.load(fullflat)

                                hdu1exp=float(file.split('_')[-2])

                                camera_gain_estimate_image=((hdu1data-masterBias)-(g_dev['cam'].darkFiles['1']*hdu1exp))
                                camera_gain_estimate_image[camera_gain_estimate_image == inf] = np.nan
                                camera_gain_estimate_image[camera_gain_estimate_image == -inf] = np.nan

                                # If an OSC, just use the brightest bayer bit.
                                if g_dev['cam'].settings["is_osc"]:

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
                                        oscmedian=bn.nanmedian(oscimage)
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

                                cge_median=bn.nanmedian(camera_gain_estimate_image)
                                cge_stdev=bn.nanstd(camera_gain_estimate_image)
                                cge_sqrt=pow(cge_median,0.5)
                                #cge_gain=1/pow(cge_sqrt/cge_stdev, 2)
                                cge_gain=pow(cge_sqrt/cge_stdev, 2)
                                plog ("Camera gain median: " + str(cge_median) + " stdev: " +str(cge_stdev)+ " sqrt: " + str(cge_sqrt) + " gain: " +str(cge_gain))

                                if cge_median > 0:
                                    estimated_flat_gain.append(cge_gain)
                                    single_filter_camera_gains.append(cge_gain)
                                else:
                                    plog ("Something weird and fishy..... a negative median?")

                            single_filter_camera_gains=np.array(single_filter_camera_gains)
                            single_filter_camera_gains = sigma_clip(single_filter_camera_gains, masked=False, axis=None)
                            plog ("Filter Gain Sigma Clipped Estimates: " + str(bn.nanmedian(single_filter_camera_gains)) + " std " + str(np.std(single_filter_camera_gains)) + " N " + str(len(single_filter_camera_gains)))
                            flat_gains[filtercode]=[bn.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]

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
                                self.filter_camera_gain_shelf[filtercode.lower()]=[bn.nanmedian(single_filter_camera_gains), np.std(single_filter_camera_gains),len(single_filter_camera_gains)]
                                self.filter_camera_gain_shelf.close()
                            except:
                                plog("************* FAILED TO WRITE TO FILTER GAIN SHELF. Usually while flats are being taken at the same time. Follow-up if this becomes relatively frequent.")


                            plog (str(filtercode) + " flat camera gains measured : " +str(time.time()-calibration_timer))

                            # DELETE ALL TEMP FILES FROM FLAT DIRECTORY
                            deleteList= (glob(g_dev['obs'].local_flat_folder + filtercode + '/tempcali_*.n*'))
                            for file in deleteList:
                                try:
                                    os.remove(file)
                                except:
                                    plog ("couldn't remove tempflat: " + str(file))

                            g_dev['cam'].flatFiles.update({filtercode: g_dev['obs'].calib_masters_folder + 'masterFlat_'+ str(filtercode) + '_bin1.npy'})

                            g_dev["obs"].send_to_user(str(filtercode) + " flat calibration frame created.")
                            plog (str(filtercode) + " flat calibration frame created: " +str(time.time()-calibration_timer))
                            calibration_timer=time.time()





                plog ("Regenerated Flat Masters and Re-loaded them into memory.")

            # Create the bad pixel map fits and npy
            # Save the local boolean array
            plog ("Total bad pixels in image: " + str(bad_pixel_mapper_array.sum()))
            plog ("Writing out bad pixel map npy and fits.")
            np.save(g_dev['obs'].calib_masters_folder + tempfrontcalib + 'badpixelmask_bin1.npy', bad_pixel_mapper_array)

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


        # Bung in the readnoise estimates and then
        # Close up the filter camera gain shelf.
        try:
            self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))
            #self.filter_camera_gain_shelf['readnoise']=[bn.nanmedian(post_readnoise_array) , bn.nanstd(post_readnoise_array), len(post_readnoise_array)]
            self.filter_camera_gain_shelf['readnoise']=[read_noise_electrons , read_noise_electrons_stdev, num_of_biases]
            self.filter_camera_gain_shelf.close()
        except:
            plog ("cannot write the readnoise array to the shelf. Probs because this is the first time estimating gains")

        textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'cameragain' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.txt'
        try:
            os.remove(textfilename)
        except:
            pass

        try:
            gain_collector=[]
            stdev_collector=[]

            g_dev['cam'].filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))

            for entry in g_dev['cam'].filter_camera_gain_shelf:
                if entry != 'readnoise':
                    singlentry=g_dev['cam'].filter_camera_gain_shelf[entry]
                    gain_collector.append(singlentry[0])
                    stdev_collector.append(singlentry[1])
                    plog (str(entry) +" gain: " + str(singlentry[0]) + " stdev " + str(singlentry[1]))

            while True:
                gainmed=bn.nanmedian(gain_collector)
                gainstd=bn.nanstd(gain_collector)
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
                g_dev['cam'].camera_known_gain_stdev=bn.nanstd(gain_collector)


            #read_noise_electrons, read_noise_adu, read_noise_electrons_stdev, read_noise_adu_stdev

            g_dev['cam'].camera_known_readnoise= read_noise_electrons
            g_dev['cam'].camera_known_readnoise_stdev = read_noise_electrons_stdev

            # singlentry=g_dev['cam'].filter_camera_gain_shelf['readnoise']
            # g_dev['cam'].camera_known_readnoise= (singlentry[0] * g_dev['cam'].camera_known_gain) / 1.414
            # g_dev['cam'].camera_known_readnoise_stdev = (singlentry[1] * g_dev['cam'].camera_known_gain) / 1.414
        except:
            plog('failed to estimate gain and readnoise from flats and such')

        if np.isnan(g_dev['cam'].camera_known_gain):
            g_dev['cam'].camera_known_gain = 70000
        plog ("Used Camera Gain: " + str(g_dev['cam'].camera_known_gain))
        plog ("Used Readnoise  : "+ str(g_dev['cam'].camera_known_readnoise))

        self.currently_regenerating_masters = False
        g_dev["obs"].send_to_user("All calibration frames completed.")

        return


    def check_zenith_and_move_to_flat_spot(self, ending=None, dont_wait_after_slew=False):

        too_close_to_zenith=True
        while too_close_to_zenith:
            alt, az = g_dev['mnt'].flat_spot_now()
            alt=g_dev['mnt'].flatspot_alt
            if self.config['degrees_to_avoid_zenith_area_for_calibrations'] > 0:
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
                                    temptimer=time.time()
                            # Store last home time.
                            homerotator_time_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'homerotatortime' + g_dev['cam'].alias + str(g_dev['obs'].name))
                            homerotator_time_shelf['lasthome'] = time.time()
                            homerotator_time_shelf.close()

                            self.check_zenith_and_move_to_flat_spot(ending=ending, dont_wait_after_slew=dont_wait_after_slew)
                            if not dont_wait_after_slew:
                                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
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
        self.total_sequencer_control=True

        to_zone = tz.gettz(self.obs.astro_events.wema_config['TZ_database_name'])
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
            self.total_sequencer_control = False
            return

        if  ((ephem.now() < g_dev['events']['Cool Down, Open']) or \
            (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['Nightly Reset'])):
            plog ("NOT DOING FLATS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it is during the daytime.")
            self.flats_being_collected = False
            self.eve_sky_flat_latch = False
            self.morn_sky_flat_latch = False
            self.total_sequencer_control = False
            return

        if (g_dev['events']['Naut Dusk'] < ephem.now() < g_dev['events']['Naut Dawn']) :
            plog ("NOT DOING FLATS -- IT IS THE NIGHTIME!!")
            g_dev["obs"].send_to_user("A sky flat script request was rejected as it too dark.")
            self.flats_being_collected = False
            self.eve_sky_flat_latch = False
            self.morn_sky_flat_latch = False
            self.total_sequencer_control = False
            return

        # This variable will trigger a re-run of the flat script if it detects that it had to estimate a new throughput
        # So that a proper full flat script is run after the estimates
        self.new_throughtputs_detected_in_flat_run=False

        self.blockend= None

        # Moon check.
        if (skip_moon_check==False):
            # Moon current alt/az
            currentaltazframe = AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now())
            moondata=get_body("moon", time=Time.now()).transform_to(currentaltazframe)

            # Flatspot position.
            flatspotalt, flatspotaz = g_dev['mnt'].flat_spot_now()
            temp_separation=((ephem.separation( (flatspotaz,flatspotalt), (moondata.az.deg,moondata.alt.deg))))

            if (moondata.alt.deg < -5):
                plog ("Moon is far below the horizon, alt: " + str(moondata.alt.deg) + ", sky flats going ahead.")
            elif temp_separation < math.radians(self.config['minimum_distance_from_the_moon_when_taking_flats']): #and (ephem.Moon(datetime.datetime.now()).moon_phase) > 0.05:
                plog ("Moon is in the sky and less than " + str(self.config['minimum_distance_from_the_moon_when_taking_flats']) + " degrees ("+str(temp_separation)+") away from the flat spot, skipping this flat time.")
                self.flats_being_collected = False
                self.eve_sky_flat_latch = False
                self.morn_sky_flat_latch = False
                self.total_sequencer_control = False
                return
            else:
                plog ("Moon is in the sky but far enough way to take flats.")


        g_dev['foc'].set_initial_best_guess_for_focus()
        g_dev['mnt'].set_tracking_on()

        plog('Sky Flat sequence Starting.')
        self.next_flat_observe = time.time()
        g_dev['obs'].send_to_user('Sky Flat sequence Starting.', p_level='INFO')
        evening = not morn
        camera_name = str(g_dev['cam'].name)
        flat_count = g_dev['cam'].settings['number_of_flat_to_collect']
        min_exposure = float(g_dev['cam'].settings['min_flat_exposure'])
        max_exposure = float(g_dev['cam'].settings['max_flat_exposure'])
        exp_time = min_exposure
        broadband_ss_biasdark_exp_time = float(g_dev['cam'].settings['smart_stack_exposure_time'])
        narrowband_ss_biasdark_exp_time = float(broadband_ss_biasdark_exp_time * g_dev['cam'].settings['smart_stack_exposure_NB_multiplier'])
        sky_exposure_snap_to_grid = [ 0.00004, 0.0004, 0.0045, 0.015, 0.05,0.1, 0.25, 0.5 , 0.75, 1, 1.5, 2.0, 3.5, 5.0, 7.5, 10, 15, 20, 30, broadband_ss_biasdark_exp_time]

        if not g_dev["fil"].null_filterwheel:
            sky_exposure_snap_to_grid.append(narrowband_ss_biasdark_exp_time)

        # Load up the pickled list of gains or start a new one.
        self.filter_throughput_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].alias + str(g_dev['obs'].name))

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
            if 'dk' in list_of_filters_for_this_run:
                list_of_filters_for_this_run.remove('dk')
            if 'dark' in list_of_filters_for_this_run:
                list_of_filters_for_this_run.remove('dark')
            # Second, check that that all filters have a stored throughput value
            # If not, we will only run on those filters that have yet to get a throughput recorded
            # After we have a throughput, the sequencer should re-run a normal run with all filters
            all_throughputs_known=True
            no_throughputs_filters=[]
            for entry in list_of_filters_for_this_run:
                if not entry in self.filter_throughput_shelf.keys():
                    plog (entry + " is not in known throughputs list. Prioritising collecting this flat.")
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

        if morn:
            pop_list.reverse()
            plog('filters by high to low transmission:  ', pop_list)
        else:
            plog('filters by low to high transmission:  ', pop_list)

        if morn:
            self.flats_ending = g_dev['events']['End Morn Sky Flats']
        else:
            self.flats_ending = g_dev['events']['End Eve Sky Flats']

        exp_time = 0
        scale = 1.0
        collecting_area = self.config['telescope']['Main OTA']['collecting_area']/31808.  #Ratio to ARO Ceravolo 300mm


        # First pointing towards flatspot
        if g_dev['mnt'].rapid_park_indicator:
            g_dev['mnt'].unpark_command({}, {})

        self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending)
        self.time_of_next_slew = time.time() + 600

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

                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending)
                self.time_of_next_slew = time.time() + 600
                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                while g_dev['rot'].rotator.IsMoving:
                    plog("home rotator wait")
                    time.sleep(1)
                self.rotator_has_been_homed_this_evening=True
                g_dev['obs'].rotator_has_been_checked_since_last_slew = True

            except:
                #plog ("no rotator to home or wait for.")
                pass

        camera_gain_collector=[]

        # Super-duper double check that darkslide is open
        if g_dev['cam'].has_darkslide:
            g_dev['cam'].openDarkslide()

        if time.time() >= self.time_of_next_slew:
            self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending)
            self.time_of_next_slew = time.time() + 600

        while len(pop_list) > 0  and ephem.now() < self.flats_ending and g_dev['obs'].open_and_enabled_to_observe:

                if g_dev["fil"].null_filterwheel == False:
                    current_filter = pop_list[0]
                    plog("Beginning flat run for filter: " + str(current_filter))
                else:
                    current_filter='No Filter'
                    plog("Beginning flat run for filterless observation")

                # For each filter, there are a few properties that drive the logic
                sky_exposure_snap_this_filter=copy.deepcopy(sky_exposure_snap_to_grid)
                number_of_exposures_so_far=0


                min_exposure = float(g_dev['cam'].settings['min_flat_exposure'])
                max_exposure = float(g_dev['cam'].settings['max_flat_exposure'])

                g_dev['obs'].send_to_user("\n\nBeginning flat run for filter: " + str(current_filter) )
                if (current_filter in self.filter_throughput_shelf.keys()):
                    filter_throughput=self.filter_throughput_shelf[current_filter]
                    plog ("Using stored throughput : " + str(filter_throughput))
                    known_throughput= True
                else:
                    if g_dev["fil"].null_filterwheel == False:
                        filter_throughput = g_dev["fil"].get_starting_throughput_value(current_filter)
                        plog ("Using initial attempt at a throughput : "+ str(filter_throughput))
                        plog ("Widening min and max exposure times to find a good estimate also.")
                        plog ("Normal exposure limits will return once a good throughput is found.")
                        min_exposure= float(g_dev['cam'].settings['min_exposure'])
                        max_exposure=max_exposure*3
                        flat_count=1
                        known_throughput=False
                        self.new_throughtputs_detected_in_flat_run=True
                    else:
                        filter_throughput = 150.0
                        plog ("Using initial throughput: "+ str(filter_throughput))
                        plog ("Widening min and max exposure times to find a good estimate also.")
                        plog ("Normal exposure limits will return once a good throughput is found.")
                        min_exposure=min_exposure*0.33
                        max_exposure=max_exposure*3
                        flat_count=1
                        known_throughput=False
                        self.new_throughtputs_detected_in_flat_run=True

                # Pick up previous camera_gain specific for this filter
                if known_throughput:
                    self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))
                    try:
                        plog(self.filter_camera_gain_shelf[current_filter.lower()])
                        self.current_filter_last_camera_gain=float(self.filter_camera_gain_shelf[current_filter.lower()][0])
                        if float(self.filter_camera_gain_shelf[current_filter.lower()][1]) < 25:
                            self.current_filter_last_camera_gain_stdev=self.filter_camera_gain_shelf[current_filter.lower()][1]
                        else:
                            self.current_filter_last_camera_gain_stdev=200
                    except:
                        plog ("perhaps can't find filter in shelf")
                        plog(traceback.format_exc())
                        self.current_filter_last_camera_gain=200
                        self.current_filter_last_camera_gain_stdev=200
                    self.filter_camera_gain_shelf.close()

                # If the known_throughput is false, then do not reject flats by camera gain.
                else:
                    self.current_filter_last_camera_gain=200
                    self.current_filter_last_camera_gain_stdev=200

                plog ("MTF tracking this issue: current_filter_last_camera_gain: " + str(self.current_filter_last_camera_gain))

                #breakpoint()

                acquired_count = 0
                flat_saturation_level = g_dev['cam'].settings["saturate"]

                if g_dev['cam'].settings["is_osc"]:
                    target_flat = 0.65 * flat_saturation_level
                else:
                    target_flat = 0.5 * flat_saturation_level

                scale = 1
                self.estimated_first_flat_exposure = False
                in_wait_mode=False

                slow_report_timer=time.time()-180

                while (acquired_count < flat_count):
                    g_dev["obs"].request_update_status()

                    if g_dev['obs'].open_and_enabled_to_observe == False:
                        plog ("Observatory closed or disabled during flat script. Cancelling out of flat acquisition loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        self.eve_sky_flat_latch = False
                        self.morn_sky_flat_latch = False
                        self.total_sequencer_control = False
                        return

                    # Check that Flat time hasn't ended
                    if ephem.now() > self.flats_ending:
                        plog ("Flat acquisition time finished. Breaking out of the flat loop.")
                        self.filter_throughput_shelf.close()
                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                        self.flats_being_collected = False
                        self.eve_sky_flat_latch = False
                        self.morn_sky_flat_latch = False
                        self.total_sequencer_control = False
                        return

                    if self.next_flat_observe < time.time():
                        try:
                            sky_lux, _ = self.obs.astro_events.illuminationNow()    # NB NB Eventually we should MEASURE this.
                        except:
                            sky_lux = None

                        # MF SHIFTING EXPOSURE TIME CALCULATOR EQUATION TO BE MORE GENERAL FOR ALL TELESCOPES
                        # This bit here estimates the initial exposure time for a telescope given the skylux
                        # or given no skylux at all!
                        if self.estimated_first_flat_exposure == False:
                            self.estimated_first_flat_exposure = True
                            if sky_lux != None:

                                if g_dev['cam'].pixscale == None:
                                    pixel_area=0.25
                                else:
                                    pixel_area=pow(float(g_dev['cam'].pixscale),2)
                                exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(filter_throughput))
                                # snap the exposure time to a discrete grid
                                if exp_time > 0.00002 and len(sky_exposure_snap_this_filter) > 0:
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
                                    if exp_time > 0.00002 and len(sky_exposure_snap_this_filter) > 0:
                                        exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                                    else:
                                        exp_time = 0.5*min_exposure
                        elif in_wait_mode:
                            exp_time = target_flat/(collecting_area*pixel_area*sky_lux*float(new_throughput_value ))
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.00002 and len(sky_exposure_snap_this_filter) > 0:
                                exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                            else:
                                exp_time = 0.5*min_exposure
                        else:
                            exp_time = scale * exp_time
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.00002 and len(sky_exposure_snap_this_filter) > 0:
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
                            self.total_sequencer_control = False
                            return

                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            self.filter_throughput_shelf.close()
                            g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                            self.flats_being_collected = False
                            self.eve_sky_flat_latch = False
                            self.morn_sky_flat_latch = False
                            self.total_sequencer_control = False
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

                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending, dont_wait_after_slew=True)

                                self.time_of_next_slew = time.time() + 600
                             self.next_flat_observe = time.time() + 5
                        elif morn and exp_time > max_exposure :
                             if time.time()-slow_report_timer > 120:
                                 plog("Too dim for " + str(current_filter) + " filter, waiting. Est. Exptime:  " + str(exp_time))
                                 g_dev["obs"].send_to_user("Sky is too dim for " + str(current_filter) + " filter, waiting for sky to brighten. Current estimated Exposure time: " + str(round(exp_time,2))+'s')
                                 slow_report_timer=time.time()
                                 in_wait_mode=True

                             if time.time() >= self.time_of_next_slew:
                                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending, dont_wait_after_slew=True)

                                self.time_of_next_slew = time.time() + 600
                             self.next_flat_observe = time.time() + 5
                             exp_time = min_exposure
                             # snap the exposure time to a discrete grid
                             if exp_time > 0.00002:
                                 exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                             else:
                                 exp_time = 0.5*min_exposure

                        else:
                            in_wait_mode=False
                            exp_time = round(exp_time, 5)
                            # snap the exposure time to a discrete grid
                            if exp_time > 0.00002:
                                exp_time=min(sky_exposure_snap_this_filter, key=lambda x:abs(x-exp_time))
                            else:
                                exp_time = 0.5*min_exposure

                            # If scope has gone to bed due to inactivity, wake it up!
                            if g_dev['mnt'].rapid_park_indicator:
                                g_dev['mnt'].unpark_command({}, {})
                                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending, dont_wait_after_slew=True)
                                self.time_of_next_slew = time.time() + 600

                            # If scope has drifted quite a lot from the null spot while waiting, nudge it back up.
                            if time.time() >= (self.time_of_next_slew-270):
                                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending, dont_wait_after_slew=True)
                                self.time_of_next_slew = time.time() + 600

                            if self.stop_script_called:
                                g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                self.total_sequencer_control = False
                                return
                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                self.total_sequencer_control = False
                                return

                            req = {'time': float(exp_time),  'alias': camera_name, 'image_type': 'skyflat', 'script': 'On'}

                            if g_dev["fil"].null_filterwheel == False:
                                opt = { 'count': 1, 'filter': current_filter}
                            else:
                                opt = { 'count': 1, }

                            if ephem.now() >= self.flats_ending:
                                if morn: # This needs to be here because some scopes do not do morning bias and darks
                                    try:
                                        g_dev['mnt'].park_command({}, {})
                                    except:
                                        plog("Mount did not park at end of morning skyflats.")
                                self.filter_throughput_shelf.close()
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                self.total_sequencer_control = False
                                return
                            try:
                                # Particularly for AltAz, the slew and rotator rotation must have ended before exposing.
                                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
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

                                # Variable to notify the camera thread that its the last of the flat set, so free to nudge
                                if (acquired_count + 1) == flat_count:
                                    self.last_image_of_a_filter_flat_set=True
                                else:
                                    self.last_image_of_a_filter_flat_set=False

                                self.scope_already_nudged_by_camera_thread=False
                                # Report the next filter in the queue
                                if len (pop_list) == 1:
                                    self.next_filter_in_flat_run = 'none'
                                else:
                                    self.next_filter_in_flat_run = pop_list[1]

                                fred = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, do_sep = False,skip_daytime_check=True)
                                number_of_exposures_so_far=number_of_exposures_so_far+1

                                try:
                                    if self.stop_script_called:
                                        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        self.eve_sky_flat_latch = False
                                        self.morn_sky_flat_latch = False
                                        self.total_sequencer_control = False
                                        return

                                    if not g_dev['obs'].open_and_enabled_to_observe:
                                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                        self.filter_throughput_shelf.close()
                                        g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                        self.flats_being_collected = False
                                        self.eve_sky_flat_latch = False
                                        self.morn_sky_flat_latch = False
                                        self.total_sequencer_control = False
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
                                    self.total_sequencer_control = False
                                    return

                                if fred == 'blockend':
                                    plog ("blockend detected during flat period, cancelling out of flat scripts")
                                    g_dev["obs"].send_to_user("Roof shut during sky flats. Stopping sky_flats")
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    self.eve_sky_flat_latch = False
                                    self.morn_sky_flat_latch = False
                                    self.total_sequencer_control = False
                                    return

                                if g_dev["obs"].stop_all_activity:
                                    plog('stop_all_activity cancelling out of exposure loop')
                                    self.filter_throughput_shelf.close()
                                    g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                    self.flats_being_collected = False
                                    self.eve_sky_flat_latch = False
                                    self.morn_sky_flat_latch = False
                                    self.total_sequencer_control = False
                                    return

                                try:
                                    bright = fred['patch']
                                except:
                                    bright = None
                                    plog ("patch broken?")
                                    plog(traceback.format_exc())
                                    plog (fred)

                            except Exception as e:
                                plog('Failed to get a flat image: ', e)
                                plog(traceback.format_exc())
                                continue

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
                                self.total_sequencer_control = False
                                return

                            if not g_dev['obs'].open_and_enabled_to_observe:
                                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                                self.filter_throughput_shelf.close()
                                g_dev['mnt'].park_command({}, {}) # You actually always want it to park, TheSkyX can't stop the telescope tracking, so park is safer... it is before focus anyway.
                                self.flats_being_collected = False
                                self.eve_sky_flat_latch = False
                                self.morn_sky_flat_latch = False
                                self.total_sequencer_control = False
                                return

                            self.got_a_flat_this_round=False

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
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        new_throughput_value = round(bright/(sky_lux*collecting_area*pixel_area*exp_time), 3)
                                    else:
                                        plog('New Throughput Value: ', round(bright/(collecting_area*pixel_area*exp_time), 3), '\n\n')
                                        old_throughput_value=copy.deepcopy(new_throughput_value)
                                        new_throughput_value = round(bright/(collecting_area*pixel_area*exp_time), 3)

                                if g_dev['cam'].settings["is_osc"]:
                                    # Check the first image is not unnaturally low (during non-commissioning with a known filter)
                                    # and wait again
                                    if bright < 0.3 * flat_saturation_level and number_of_exposures_so_far == 1 and self.current_filter_last_camera_gain < 200:
                                        plog("Got an abnormally low value on the first shot")
                                        plog("Retrying again after a little wait to check the filter is in place")
                                        new_throughput_value=copy.deepcopy(old_throughput_value)
                                        scale=1
                                        time.sleep(3)
                                    # Same with unnaturally high
                                    elif bright > 0.8 * flat_saturation_level and number_of_exposures_so_far == 1 and self.current_filter_last_camera_gain < 200:
                                        plog("Got an abnormally high value on the first shot")
                                        plog("Retrying again after a little wait to check the filter is in place")
                                        new_throughput_value=copy.deepcopy(old_throughput_value)
                                        scale=1
                                        time.sleep(3)
                                    elif (
                                        bright
                                        <= 0.8* flat_saturation_level and
                                        bright
                                        >= 0.5 * flat_saturation_level
                                    ):
                                        acquired_count += 1
                                        self.got_a_flat_this_round=True
                                        self.filter_throughput_shelf[current_filter]=new_throughput_value
                                        try:
                                            camera_gain_collector.append(fred["camera_gain"])
                                        except:
                                            plog ("camera gain not avails")
                                    elif morn and (bright > (flat_saturation_level * 0.8)) and (old_throughput_value/new_throughput_value > 0.85) and (old_throughput_value/new_throughput_value < 1.15):
                                        plog ("Morning and overexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)
                                        # Remove all exposure times below this exposure
                                        # Also remove other useless exposure times
                                        for expentry in sky_exposure_snap_this_filter:
                                            if float(expentry) > exp_time:
                                                try:
                                                    sky_exposure_snap_this_filter.remove(expentry)
                                                except:
                                                    plog(traceback.format_exc())

                                    elif not morn and (bright < (flat_saturation_level * 0.5)) and 0.85 < old_throughput_value/new_throughput_value < 1.15:
                                        plog ("Evening and underexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)
                                        # Remove all exposure times below this exposure time
                                        # Also remove other useless exposure times
                                        for expentry in sky_exposure_snap_this_filter:
                                            if float(expentry) < exp_time:
                                                try:
                                                    sky_exposure_snap_this_filter.remove(expentry)
                                                except:
                                                    plog(traceback.format_exc())

                                else:
                                    if bright < 0.1 * flat_saturation_level and number_of_exposures_so_far == 1 and self.current_filter_last_camera_gain < 200:
                                        plog("Got an abnormally low value on the first shot")
                                        plog("Retrying again after a little wait to check the filter is in place")
                                        new_throughput_value=copy.deepcopy(old_throughput_value)
                                        scale=1
                                        time.sleep(3)
                                    if bright > 0.8 * flat_saturation_level and number_of_exposures_so_far == 1  and self.current_filter_last_camera_gain < 200:
                                        plog("Got an abnormally high value on the first shot")
                                        plog("Retrying again after a little wait to check the filter is in place")
                                        new_throughput_value=copy.deepcopy(old_throughput_value)
                                        scale=1
                                        time.sleep(3)
                                    elif (
                                        bright
                                        <= 0.75* flat_saturation_level and
                                        bright
                                        >= 0.25 * flat_saturation_level
                                    ):
                                        acquired_count += 1
                                        self.got_a_flat_this_round=True
                                        self.filter_throughput_shelf[current_filter]=new_throughput_value
                                        try:
                                            camera_gain_collector.append(fred["camera_gain"])
                                        except:
                                            plog ("camera gain not avails")
                                    elif morn and ( bright > (flat_saturation_level * 0.75)) and 0.85 < old_throughput_value/new_throughput_value < 1.15:
                                        plog ("Morning and overexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)
                                        # Also remove other useless exposure times
                                        for expentry in sky_exposure_snap_this_filter:
                                            if float(expentry) > exp_time:
                                                try:
                                                    sky_exposure_snap_this_filter.remove(expentry)
                                                except:
                                                    plog(traceback.format_exc())

                                    elif not morn and (bright < (flat_saturation_level * 0.25)) and 0.85 < old_throughput_value/new_throughput_value < 1.15:
                                        plog ("Evening and underexposing at this exposure time: " + str(exp_time) + ". Dropping that out")
                                        sky_exposure_snap_this_filter.remove(exp_time)
                                        # Also remove other useless exposure times
                                        for expentry in sky_exposure_snap_this_filter:
                                            if float(expentry) < exp_time:
                                                try:
                                                    sky_exposure_snap_this_filter.remove(expentry)
                                                except:
                                                    plog(traceback.format_exc())


                            if len(sky_exposure_snap_this_filter) <1:
                                acquired_count=flat_count+1

                            if bright == None:
                                plog ("Seems like the camera isn't liking taking flats. This is usually because it hasn't been able to cool sufficiently, bailing out of flats. ")
                                acquired_count += 1 # trigger end of loop

                            if acquired_count == flat_count or acquired_count > flat_count or (self.last_image_of_a_filter_flat_set and not flat_count == 1):
                                acquired_count=acquired_count+1
                                pop_list.pop(0)
                                scale = 1
                            elif self.got_a_flat_this_round and not self.scope_already_nudged_by_camera_thread: # Only nudge if you got a good flat. No point otherwise.
                                # Give it a bit of a nudge, not necessary if it is the last shot of the filter.
                                # There is no reason to wait for it to finish slewing either.
                                self.check_zenith_and_move_to_flat_spot(ending=self.flats_ending, dont_wait_after_slew=True)
                                self.time_of_next_slew = time.time() + 600
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
            plog ("Camera Gain Estimates: " + str(bn.nanmedian(camera_gain_collector)) + " std " + str(np.std(camera_gain_collector)) + " N " + str(len(camera_gain_collector)))
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

        g_dev['obs'].flush_command_queue()


        # If the camera pixelscale is None then we are in commissioning mode and
        # need to restack the calibrations straight away
        # so this triggers off the stacking process to happen in a thread.
        if g_dev['cam'].pixscale == None:
            self.master_restack_queue.put( 'force', block=False)

        self.total_sequencer_control = False


    def screen_flat_script(self, req, opt):


        #### CURRENTLY THIS IS NOT AN IMPLEMENTED FUNCTION.
        pass


    def filter_focus_offset_estimator_script(self):

        self.measuring_focus_offsets=True
        plog ("Determining offsets between filters")
        plog ("First doing a normal run on the 'focus' filter first")

        # Slewing to a relatively random high spot
        g_dev['mnt'].go_command(alt=75,az= 270)

        req2 = {'target': 'near_tycho_star'}
        opt = {}
        foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, filter_choice='focus')

        plog ("focus position: " + str(foc_pos))
        plog ("focus fwhm: " + str(foc_fwhm))

        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
            self.focussing=False

            return
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
            self.focussing=False

            return

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
        if 'dk' in list_of_filters_for_this_run:
            list_of_filters_for_this_run.remove('dk')
        if 'dark' in list_of_filters_for_this_run:
            list_of_filters_for_this_run.remove('dark')

        filter_offset_collector={}

        for chosen_filter in list_of_filters_for_this_run:
            plog ("Running offset test for " + str(chosen_filter))
            try:
                foc_pos, foc_fwhm=self.auto_focus_script(req2, opt, dont_return_scope=True, skip_timer_check=True, dont_log_focus=True, skip_pointing=True, begin_at=focus_filter_focus_point, filter_choice=chosen_filter)
            except:
                plog(traceback.format_exc())
                plog ("dodgy auto focus return")
                foc_pos=np.nan
                foc_fwhm=np.nan
            plog ("focus position: " + str(foc_pos))
            plog ("focus fwhm: " + str(foc_fwhm))

            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                self.focussing=False
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                return

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

            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                self.focussing=False
                return
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                return

        plog ("Final determined offsets this run")
        plog (filter_offset_collector)
        plog ("Current filter offset shelf")
        filteroffset_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filteroffsets_' + g_dev['cam'].alias + str(g_dev['obs'].name))
        for filtername in filteroffset_shelf:
            plog (str(filtername) + " " + str(filteroffset_shelf[filtername]))
        filteroffset_shelf.close()

        self.auto_focus_script(req2, opt,skip_pointing=True)
        self.measuring_focus_offsets=False


    def auto_focus_script(self, req, opt, throw=None, begin_at=None, skip_timer_check=False, dont_return_scope=False, dont_log_focus=False, skip_pointing=False, extensive_focus=None, filter_choice='focus'):

        self.focussing=True
        self.total_sequencer_control = True

        # assume we are using the main focuser
        focuser = self.obs.devices['main_focuser']

        if throw==None:
            throw= focuser.config['throw']

        if (ephem.now() < g_dev['events']['End Eve Bias Dark'] ) or \
            (g_dev['events']['End Morn Bias Dark']  < ephem.now() < g_dev['events']['Nightly Reset']):
            plog ("NOT DOING AUTO FOCUS -- IT IS THE DAYTIME!!")
            g_dev["obs"].send_to_user("An auto focus was rejected as it is during the daytime.")
            self.focussing=False
            self.total_sequencer_control = False
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
                self.total_sequencer_control = False
                return np.nan, np.nan

        g_dev['foc'].time_of_last_focus = datetime.datetime.utcnow()

        # Reset focus tracker
        g_dev['foc'].focus_tracker = [np.nan] * 10
        throw = g_dev['foc'].throw
        self.af_guard = True

        #unpark before anything else.
        position_after_unpark=False
        if g_dev['mnt'].rapid_park_indicator:
            position_after_unpark=True
        g_dev['mnt'].unpark_command({}, {})
        if position_after_unpark:
            g_dev['mnt'].go_command(alt=70,az= 70)
            g_dev['mnt'].set_tracking_on()

        start_ra = g_dev['mnt'].return_right_ascension()   #Read these to go back.  NB NB Need to cleanly pass these on so we can return to proper target.
        start_dec = g_dev['mnt'].return_declination()


        #breakpoint()

        if not begin_at is None:
            focus_start = begin_at  #In this case we start at a place close to a 3 point minimum.
        # elif not extensive_focus == None:
        #     focus_start=extensive_focus
        else:
            focus_start=g_dev['foc'].current_focus_position
        foc_pos0 = focus_start

# =============================================================================
# =============================================================================
# =============================================================================
        plog("Saved  *mounting* ra, dec, focus:  ", start_ra, start_dec, focus_start)

        if not skip_pointing:
            # Trim catalogue so that only fields 45 degrees altitude are in there.
            self.focus_catalogue_skycoord= SkyCoord(ra = self.focus_catalogue[:,0]*u.deg, dec = self.focus_catalogue[:,1]*u.deg)
            aa = AltAz (location=g_dev['mnt'].site_coordinates, obstime=Time.now())
            self.focus_catalogue_altitudes=self.focus_catalogue_skycoord.transform_to(aa)

            # Also avoid being to close to the meridian
            # This is to avoid flips but also
            # If we are syncing the mount during this period, we need to sync safely away from the meridian
            sid = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            self.focus_catalogue_hourangles=[]
            for splot in self.focus_catalogue[:,0]:
                self.focus_catalogue_hourangles.append( abs(sid - (splot / 15)))

            above_altitude_patches=[]

            for ctr in range(len(self.focus_catalogue_altitudes)):
                if self.focus_catalogue_altitudes[ctr].alt /u.deg > 45.0 and self.focus_catalogue_hourangles[ctr] > 1:
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

            req = {'time': self.config['focus_exposure_time'],  'alias':  str(g_dev['cam'].name), 'image_type': 'focus'}
            opt = { 'count': 1, 'filter': 'focus'}

            if self.stop_script_called:
                g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                self.focussing=False
                self.total_sequencer_control = False
                return np.nan, np.nan

            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                self.total_sequencer_control = False
                return np.nan, np.nan

            g_dev['foc'].guarded_move((focus_start)*g_dev['foc'].micron_to_steps)

            # First check if we are doing a sync
            if g_dev['obs'].sync_after_platesolving and not (g_dev['cam'].pixscale == None):
                g_dev['obs'].send_to_user("Running a platesolve to sync the mount", p_level='INFO')

                self.centering_exposure(no_confirmation=True, try_hard=True)
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
                            self.total_sequencer_control = False
                            return np.nan, np.nan
                        if not g_dev['obs'].open_and_enabled_to_observe:
                            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                            self.focussing=False
                            self.total_sequencer_control = False
                            return np.nan, np.nan
                        pass

                    g_dev['obs'].sync_after_platesolving = False

                    # Once the mount is synced, then re-slew the mount to where it thinks it should be
                    g_dev['mnt'].go_command(ra=focus_patch_ra, dec=focus_patch_dec)

                    g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field and test the sync", p_level='INFO')
            else:
                g_dev['obs'].send_to_user("Running a quick platesolve to center the focus field", p_level='INFO')


            # To get a good pixelscale, we need to be in focus,
            # So if we haven't got a good pixelscale yet, then we likely
            # haven't got a good focus yet anyway.
            if g_dev['cam'].pixscale == None:
                plog ("skipping centering exposure as we don't even have a pixelscale yet")
            else:
                self.centering_exposure(no_confirmation=True, try_hard=True)

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
                        self.total_sequencer_control = False
                        return np.nan, np.nan
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                        self.focussing=False
                        self.total_sequencer_control = False
                        return np.nan, np.nan
                    pass

                g_dev['obs'].send_to_user("Focus Field Centered", p_level='INFO')

        if self.stop_script_called:
            g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
            self.focussing=False
            self.total_sequencer_control = False
            return np.nan, np.nan
        if not g_dev['obs'].open_and_enabled_to_observe:
            g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
            self.focussing=False
            self.total_sequencer_control = False
            return np.nan, np.nan

        g_dev['obs'].request_scan_requests()

        plog('Autofocus Starting at:  ', foc_pos0, '\n\n')

        focus_exposure_time=self.config['focus_exposure_time']

        # Boost broadband
        if filter_choice.lower() in [ "blue", "b", "jb", "bb", "pb","green", "jv", "bv", "pg","red", "r", "br", "r", "pr", "rc", "rp","i", "ic", "ip", "bi","gp", "g"]:
            focus_exposure_time=focus_exposure_time*2

        # Boost Narrowband and low throughput broadband
        if filter_choice.lower() in ["u", "ju", "bu", "up","z", "zs", "zp","ha", "h", "o3", "o","s2", "s","cr", "c","n2", "n"]:
            focus_exposure_time=focus_exposure_time*3

        req = {'time': focus_exposure_time,  'alias':  str(g_dev['cam'].name), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
        opt = { 'count': 1, 'filter': filter_choice}

        g_dev['foc'].guarded_move((foc_pos0 - 0* throw)*g_dev['foc'].micron_to_steps)   # NB added 20220209 Nasty bug, varies with prior state

        # THE LOOP
        position_counter=0 # At various stages of the algorithm we attempt different things, this allows us to make that happen.
        central_starting_focus=copy.deepcopy(foc_pos0)
        focus_spots=[]
        spots_tried=[]
        extra_tries=0
        new_focus_position_to_attempt = central_starting_focus # Initialise this variable
        while True:

            im_path_r = g_dev['cam'].camera_path
            im_type = "EX"
            im_path = im_path_r + g_dev["day"] + "/to_AWS/"

            text_name = (
                g_dev['obs'].config["obs_id"]
                + "-"
                + g_dev['cam'].config["name"]
                + "-"
                + g_dev["day"]
                + "-"
                + g_dev['cam'].next_seq
                + "-"
                + im_type
                + "00.txt"
            )

            position_counter=position_counter+1
            # General command bailout section
            g_dev['obs'].request_scan_requests()
            if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of autofocus script as stop script has been called.")
                    self.focussing=False
                    self.total_sequencer_control = False
                    return np.nan, np.nan
            if not g_dev['obs'].open_and_enabled_to_observe:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                self.focussing=False
                self.total_sequencer_control = False
                return np.nan, np.nan

            # What focus position should i be using?
            if position_counter==1:
                focus_position_this_loop=central_starting_focus
            elif position_counter==2:
                focus_position_this_loop=central_starting_focus - throw
            elif position_counter==3:
                focus_position_this_loop=central_starting_focus - 2* throw
            elif position_counter==4:
                focus_position_this_loop=central_starting_focus + 2*throw
            elif position_counter==5:
                focus_position_this_loop=central_starting_focus + throw
            elif position_counter>5:
                focus_position_this_loop=new_focus_position_to_attempt


            #  If more than 15 attempts, fail and bail out.
            # But don't bail out if the scope isn't commissioned yet, keep on finding.
            if position_counter > 15 and g_dev['foc'].focus_commissioned:
                g_dev['foc'].set_initial_best_guess_for_focus()
                if not dont_return_scope:
                    plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                    g_dev['obs'].send_to_user("Attempt at V-curve Focus Failed, using calculated values", p_level='INFO')
                    g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                    g_dev['mnt'].wait_for_slew(wait_after_slew=False)

                self.focussing=False
                self.total_sequencer_control = False
                return np.nan, np.nan

            spot=np.nan
            retry_attempts=0
            spots_tried.append(focus_position_this_loop)
            while retry_attempts < 3:

                retry_attempts=retry_attempts+1

                # Check in with stop scripts and roof
                if self.stop_script_called:
                    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
                    g_dev['mnt'].park_command({}, {})
                    self.total_sequencer_control = False
                    self.focussing=False

                    return

                if not g_dev['obs'].open_and_enabled_to_observe:
                    g_dev['mnt'].park_command({}, {})
                    self.total_sequencer_control = False
                    self.focussing=False
                    return


                # Insert overtavelling at strategic points
                if position_counter == 1 or position_counter ==6:
                    plog ("Overtravelling out at this focus attempt")
                    g_dev['foc'].guarded_move((focus_position_this_loop+ 6*throw)*g_dev['foc'].micron_to_steps )



                # Move the focuser
                plog ("Changing focus to " + str(round(focus_position_this_loop,1)))
                g_dev['foc'].guarded_move((focus_position_this_loop)*g_dev['foc'].micron_to_steps)
                g_dev['mnt'].wait_for_slew(wait_after_slew=False)

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

                # Take the shot
                g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=False) ## , script = 'auto_focus_script_0')  #  This is where we start.
                spot = g_dev['obs'].fwhmresult['FWHM']
                foc_pos=g_dev['foc'].current_focus_position

                g_dev['obs'].send_to_user("Focus at test position: " + str(foc_pos) + " is FWHM: " + str(round(spot,2)), p_level='INFO')

                if not np.isnan(spot):
                    if spot < 30.0:
                        focus_spots.append((foc_pos,spot))
                        break
                elif g_dev['foc'].focus_commissioned:
                    plog ("retrying this position - could not get a FWHM ")

                else:
                    plog ("Probably out of focus, skipping this point")
                    retry_attempts=4

            # If you have the starting of a v-curve then now you can decide what to do.
            # Start off by sorting in order of focus positions
            if len(focus_spots) > 0:
                focus_spots=sorted(focus_spots)
                lowerbound=min(focus_spots)[0]
                upperbound=max(focus_spots)[0]
                bounds=[lowerbound,upperbound]
                x = list()
                y = list()
                for i in focus_spots:
                    x.append(i[0])
                    y.append(i[1])
                x=np.asarray(x, dtype=float)
                y=np.asarray(y, dtype=float)

            if position_counter < 5:
                if len(focus_spots) > 0:
                    thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                    thread.daemon = True
                    thread.start()
                    # Fling the jpeg up
                    g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)
                else:
                    plog ("Haven't found a starting point yet..... travelling left and right to find a good starting point ")
                    if position_counter & 1:
                        new_focus_position_to_attempt=min(spots_tried) - int(position_counter/2) * throw

                    else:
                        new_focus_position_to_attempt=max(spots_tried) + int(position_counter/2) * throw

                    print ("trying fwhm point: " + str(new_focus_position_to_attempt))



            else:
                if len(focus_spots) == 0 or len(focus_spots) == 1:
                    plog ("Sheesh, not one spot found yet!")
                    plog ("Having a crack at a further spot")
                    if position_counter & 1:
                        new_focus_position_to_attempt=min(spots_tried) - throw
                    else:
                        new_focus_position_to_attempt=max(spots_tried) + throw
                else:
                    # Check that from the minimum value, each of the points always increases in both directions.
                    # If not, we don't have a parabola shaped data-set
                    # Cull these wonky spots.
                    # From the minima step out in one direction to check it is increasing.
                    minimumfind=[]
                    for entry in focus_spots:
                        minimumfind.append(entry[1])
                    minimum_index=minimumfind.index(min(minimumfind))
                    minimum_value=min(minimumfind)

                    # Check that after five successful measurements
                    # If the seeing is too bad, just run with the expected
                    # If there is only two or three throw out from the lowest edge
                    if len(focus_spots) == 2 or len(focus_spots) == 3:
                        if focus_spots[0][1] < focus_spots[-1][1]:
                            plog ("smaller focus spot has lower fwhm value, trying out a spot out there")
                            new_focus_position_to_attempt=focus_spots[0][0] - throw
                        else:
                            plog ("higher focus spot has lower fwhm value, trying out a spot out there")
                            new_focus_position_to_attempt=focus_spots[-1][0] + throw

                    else:
                        # If the seeing is too poor to bother focussing, bail o ut
                        # But ONLY if the focus is commissioned. If the focus is not
                        # commissioned then it is highly likely just to be in the wrong
                        # focus region
                        if (minimum_value > focuser.config['maximum_good_focus_in_arcsecond']) and focuser.focus_commissioned:
                            plog ("Minimum value: " + str(minimum_value) + " is too high to bother focussing, just going with the estimated value from previous focus")
                            thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                            thread.daemon = True
                            thread.start()
                            g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)
                            g_dev['foc'].set_initial_best_guess_for_focus()
                            self.total_sequencer_control = False
                            self.focussing=False
                            return

                        # First check if the minimum is too close to the edge
                        if minimum_index == 0 or minimum_index == 1:
                            plog ("Minimum too close to the sampling edge, getting another dot")
                            new_focus_position_to_attempt=focus_spots[0][0] - throw
                            thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                            thread.daemon = True
                            thread.start()

                            # Fling the jpeg up
                            g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)

                        elif minimum_index == len(minimumfind)-1 or  minimum_index == len(minimumfind)-2:

                            plog ("Minimum too close to the sampling edge, getting another dot")
                            new_focus_position_to_attempt=focus_spots[len(minimumfind)-1][0] + throw
                            thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                            thread.daemon = True
                            thread.start()
                            # Fling the jpeg up
                            g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)



                        # Then check whether the values on the edge are high enough.

                        # If left side is too low get another dot
                        elif focus_spots[0][1] < (minimum_value * 1.5):

                            plog ("Left hand side of curve is too low for a good fit, getting another dot")
                            new_focus_position_to_attempt=focus_spots[0][0] - throw
                            thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                            thread.daemon = True
                            thread.start()
                            # Fling the jpeg up
                            g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)

                        # If right hand side is too low get another dot
                        elif focus_spots[-1][1] < (minimum_value * 1.5):
                            plog ("Right hand side of curve is too low for a good fit, getting another dot")
                            new_focus_position_to_attempt=focus_spots[len(minimumfind)-1][0] + throw
                            thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                            thread.daemon = True
                            thread.start()
                            # Fling the jpeg up
                            g_dev['obs'].enqueue_for_fastUI( im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)


                        # If the parabola is not centered roughly on the minimum point, then get another dot on
                        # The necessary side
                        # elif True:
                            # I've hit a point where it tries to solve, but it is the wrong point at the moment!
                            # breakpoint()


                        # Otherwise if it seems vaguely plausible to get a fit... give it a shot
                        else:
                            # If you can fit a parabola, then you've got the focus
                            # If fit, then break



                            fit_failed=False
                            try:
                                fit = np.polyfit(x, y, 2)
                                f = np.poly1d(fit)
                            except:
                                plog ("focus fit didn't work dunno y yet.")
                                plog(traceback.format_exc())
                                fit_failed=True
                            crit_points = bounds + [x for x in f.deriv().r if x.imag == 0 and bounds[0] < x.real < bounds[1]]
                            try:
                                fitted_focus_position=crit_points[2]
                            except:
                                plog ("crit points didn't work dunno y yet.")
                                plog(traceback.format_exc())
                                fit_failed=True

                            #breakpoint()

                            if fit_failed:
                                plog ("Fit failed. Usually due to a lack of data on one side of the curve. Grabbing another dot on the smaller side of the curve")
                                minimumfind=[]
                                for entry in focus_spots:
                                    minimumfind.append(entry[1])
                                minimum_index=minimumfind.index(min(minimumfind))
                                if minimum_index == 0 or minimum_index == 1:
                                    plog ("Minimum too close to the sampling edge, getting another dot")
                                    new_focus_position_to_attempt=focus_spots[0][0] - throw
                                    thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                                    thread.daemon = True
                                    thread.start()
                                    # Fling the jpeg up
                                    g_dev['obs'].enqueue_for_fastUI(im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)

                                elif minimum_index == len(minimumfind)-1 or  minimum_index == len(minimumfind)-2:

                                    plog ("Minimum too close to the sampling edge, getting another dot")
                                    new_focus_position_to_attempt=focus_spots[len(minimumfind)-1][0] + throw
                                    thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, False, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),False,False),)))
                                    thread.daemon = True
                                    thread.start()
                                    # Fling the jpeg up
                                    g_dev['obs'].enqueue_for_fastUI(im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)

                            else:
                                plog ("focus pos: " + str(fitted_focus_position))
                                fitted_focus_fwhm=f(fitted_focus_position)
                                thread = threading.Thread(target=self.construct_focus_jpeg_and_save, args=(((x, y, f, copy.deepcopy(g_dev['cam'].current_focus_jpg), copy.deepcopy(im_path + text_name.replace('EX00.txt', 'EX10.jpg')),fitted_focus_position,fitted_focus_fwhm),)))
                                thread.daemon = True
                                thread.start()
                                # Fling the jpeg up
                                g_dev['obs'].enqueue_for_fastUI(im_path, text_name.replace('EX00.txt', 'EX10.jpg'), g_dev['cam'].current_exposure_time, info_image_channel=2)

                                # Check that the solved minimum focussed position actually fits in between the lowest measured point and
                                # the two next door measured points.
                                minimumfind=[]
                                for entry in focus_spots:
                                    minimumfind.append(entry[1])
                                minimum_index=minimumfind.index(min(minimumfind))

                                minimum_position_value_left=focus_spots[minimum_index-1][0] - max(0.5,(len(focus_spots)-4)*0.5) * throw
                                minimum_position_value_right=focus_spots[minimum_index+1][0] + max(0.5,(len(focus_spots)-4)*0.5) * throw

                                # If the dot is in the center of the distribution
                                # OR we have tried four or more extra points
                                if (minimum_position_value_left < fitted_focus_position and minimum_position_value_right > fitted_focus_position) or extra_tries > 4:

                                    # If successful, then move to focus and live long and prosper
                                    plog ('Moving to Solved focus:  ', round(fitted_focus_position, 2), ' calculated:  ', fitted_focus_fwhm)
                                    g_dev['obs'].send_to_user("Solved focus is at: " + str(fitted_focus_position) + " with FWHM: " + str(round(fitted_focus_fwhm,2)), p_level='INFO')

                                    pos = int(fitted_focus_position*g_dev['foc'].micron_to_steps)
                                    g_dev['foc'].guarded_move(pos)

                                    g_dev['foc'].last_known_focus = fitted_focus_position
                                    g_dev['foc'].previous_focus_temperature = copy.deepcopy(g_dev['foc'].current_focus_temperature)

                                    # We don't take a confirming exposure because there is no point actually and just wastes time.
                                    # You can see if it is focussed with the first target shot.
                                    if not dont_return_scope:
                                        plog("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                                        g_dev["obs"].send_to_user("Returning to RA:  " +str(start_ra) + " Dec: " + str(start_dec))
                                        g_dev['mnt'].go_command(ra=start_ra, dec=start_dec)
                                        g_dev['mnt'].wait_for_slew(wait_after_slew=False)

                                    self.af_guard = False
                                    self.focussing=False
                                    if not dont_log_focus:
                                        g_dev['foc'].af_log(fitted_focus_position, fitted_focus_fwhm, spot)

                                    # Store fitted focus as last result
                                    g_dev['obs'].fwhmresult={}
                                    g_dev['obs'].fwhmresult["FWHM"] = fitted_focus_fwhm
                                    g_dev['obs'].fwhmresult["mean_focus"] = fitted_focus_position
                                    self.total_sequencer_control = False
                                    return fitted_focus_position,fitted_focus_fwhm

                                else:
                                    # Lets step out from the minimum value and delete any points that are wonky.
                                    plog ("We don't have a good fit where the minimum fit is near the minimum measured value, attempting to examine the data points, potential trim them and trying another point")
                                    extra_tries=extra_tries+1
                                    delete_list=[]

                                    # step lower
                                    step=1
                                    minimum_value=focus_spots[minimum_index][1]
                                    previous_value=copy.deepcopy(minimum_value)
                                    while minimum_index-step > -1:
                                        plog (focus_spots[minimum_index-step][1])
                                        if focus_spots[minimum_index-step][1] > previous_value:
                                            plog ("Good")
                                        else:
                                            plog ("Bad")
                                            delete_list.append(focus_spots[minimum_index-step])
                                        previous_value=focus_spots[minimum_index-step][1]
                                        step=step+1

                                    # step higher
                                    step=1
                                    minimum_value=focus_spots[minimum_index][1]
                                    previous_value=copy.deepcopy(minimum_value)
                                    while minimum_index+step < len(focus_spots):
                                        plog (focus_spots[minimum_index+step][1])
                                        if focus_spots[minimum_index+step][1] > previous_value:
                                            plog ("Good")
                                        else:
                                            plog ("Bad")
                                            delete_list.append(focus_spots[minimum_index+step])
                                        previous_value=focus_spots[minimum_index+step][1]
                                        step=step+1

                                    # If there seems to be a wonky spot, remove it and try again
                                    if len(delete_list) > 1:
                                        plog ("Found possible problem spots: " + str(delete_list))
                                        for entry in delete_list:
                                            new_focus_position_to_attempt=entry[0]
                                            focus_spots.remove(entry)
                                        plog ("Attempting this spot again: " + str(new_focus_position_to_attempt))
                                    else:
                                        plog ("Couldn't find a problem spot, attempting another point on the smaller end of the curve")
                                        if focus_spots[0][1] < focus_spots[-1][1]:
                                            plog ("smaller focus spot has lower fwhm value, trying out a spot out there")
                                            new_focus_position_to_attempt=focus_spots[0][0] - throw
                                        else:
                                            plog ("higher focus spot has lower fwhm value, trying out a spot out there")
                                            new_focus_position_to_attempt=focus_spots[-1][0] + throw


    def equatorial_pointing_run(self, max_pointings=16, alt_minimum=22.5):

        g_dev['obs'].get_enclosure_status_from_aws()
        if not g_dev['obs'].assume_roof_open and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
            plog('Roof is shut, so cannot do requested pointing run.')
            g_dev["obs"].send_to_user('Roof is shut, so cannot do requested pointing run.')
            return


        previous_mount_reference_model_off = copy.deepcopy(g_dev['obs'].mount_reference_model_off)
        g_dev['obs'].mount_reference_model_off = True

        self.total_sequencer_control = True
        g_dev['obs'].stop_processing_command_requests = True

        prev_auto_centering = g_dev['obs'].auto_centering_off
        g_dev['obs'].auto_centering_off = True
        plog ("Note that mount references and auto-centering are automatically turned off for a tpoint run.")
        plog("Starting pointing run. ")
        time.sleep(0.1)

        g_dev['mnt'].unpark_command({}, {})

        g_dev["obs"].request_update_status()
        sidereal_h = g_dev['mnt'].get_sidereal_time_h()
        catalogue = []
        #This code is a bit ad-hoc since thw hour range was chosen for ARO...
        if max_pointings == 8:
            ha_cat = [3., 2., 1., .5, -0.5, -1., -2., -2.4]  #8 points
            for hour in ha_cat:
                ra = ra_fix_h(sidereal_h + hour)  #This step could be done just before the seek below so hitting flips would be eliminated
                catalogue.append([round(ra*HTOD, 3), 0.0, 19])
        elif max_pointings == 12:
            ha_cat = [3.5, 3, 2.5, 2, 1.5, 1, 0.5, -0.5,  -1, -1.5, -2, -2.2 ,-2.4]  #114oints
            for hour in ha_cat:
                ra = ra_fix_h(sidereal_h + hour)  # NB Note my stupid sign change! WER
                catalogue.append([round(ra*HTOD, 3), 0.0, 19])
        else:
            max_pointings == 16
            ha_cat = [3.5, 3.25, 3. , 2.75, 2.5, 2.25, 2, 1.75, 1.5, 1.25, 1, 0.75,  0.5, 0.25, -.25, -0.5, -0.75 -1, -1.25, -1.5, -1.75, -2, -2.1,  -2.25,-2.5 ]  #28 points
            for hour in ha_cat:
                ra = ra_fix_h(sidereal_h + hour)  #Take note of the odd sign change.
                catalogue.append([round(ra*HTOD, 3), 0.0, 19])


        g_dev["obs"].send_to_user("Starting pointing run. Constructing altitude catalogue. This can take a while.")
        plog("Constructing sweep catalogue above altitude " + str(alt_minimum))

        sweep_catalogue=[]
        #First remove all entries below given altitude
        for ctr in range(len(catalogue)):
            teststar = SkyCoord(ra = catalogue[ctr][0]*u.deg, dec = catalogue[ctr][1]*u.deg)

            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            if alt >= alt_minimum:
                sweep_catalogue.append([catalogue[ctr][0],catalogue[ctr][1],catalogue[ctr][2],temppointingaltaz.alt.degree, temppointingaltaz.az.degree  ])

        if max_pointings > 16:
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
            teststar = SkyCoord(ra=grid_star[0]*u.deg, dec=grid_star[1]*u.deg)

            temppointingaltaz=teststar.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            az = temppointingaltaz.az.degree

            g_dev["obs"].send_to_user(str(("Slewing to near grid field, RA: " + str(round(grid_star[0] / 15, 2)) + " DEC: " + str(round(grid_star[1], 2))+ " AZ: " + str(round(az, 2))+ " ALT: " + str(round(alt,2)))))

            plog("Slewing to near grid field " + str(grid_star) )
            # if count == 3 or count == 4:
            #     pass   #Breaakpoint()

            # Use the mount RA and Dec to go directly there
            try:
                g_dev['obs'].time_of_last_slew=time.time()
                g_dev["mnt"].last_ra_requested = grid_star[0]/15.
                g_dev["mnt"].last_dec_requested = grid_star[1]
                print("sweep: ", grid_star[0]/15. , grid_star[1])
                rah=grid_star[0]/15.
                decd=grid_star[1]
                #g_dev['mnt'].slew_async_directly(ra=grid_star[0] /15, dec=grid_star[1])

                g_dev['mnt'].go_command(ra=rah, dec=decd)  # skip_open_test=True)  Goto takes keword ra and dec
            except:
                plog ("Difficulty in directly slewing to object")
                plog(traceback.format_exc())
                if g_dev['mnt'].theskyx:
                    self.obs.kill_and_reboot_theskyx(grid_star[0]/15, grid_star[1])
                else:
                    plog(traceback.format_exc())

            g_dev['mnt'].wait_for_slew(wait_after_slew=False)

            g_dev["obs"].update_status()


            g_dev["mnt"].last_ra_requested=grid_star[0]/15.
            g_dev["mnt"].last_dec_requested=grid_star[1]

            req = { 'time': self.config['pointing_exposure_time'], 'smartstack': False, 'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}
            opt = { 'count': 1,  'filter': 'w'} #  pointing'} WNB NB WER20240927
            sid1 = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            result = g_dev['cam'].expose_command(req, opt)
            sid2 = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            #NB should we check for a valid result from the exposure? WER 2240319

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
                        g_dev['obs'].flush_command_queue()
                        self.total_sequencer_control = False
                        g_dev['obs'].stop_processing_command_requests = False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                        g_dev['obs'].flush_command_queue()
                        self.total_sequencer_control = False
                        g_dev['obs'].stop_processing_command_requests = False
                        return
                    pass

            g_dev["obs"].send_to_user("Finished platesolving")
            plog ("Finished platesolving")
            ##NB this time is after the exposure and the platesolve!  Needs to be closer to reality.
            sid = (sid1 + sid2)/2.0  #float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

            # Get RA, DEC, ra deviation, dec deviation and add to the list
            try:
                g_dev['mnt'].pier_side = g_dev[
                    "mnt"
                ].return_side_of_pier()  # 0 == Tel Looking West, is NOT flipped.

            except Exception:
                plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            ra_mount=g_dev["mnt"].last_ra_requested #g_dev['mnt'].return_right_ascension()
            dec_mount = g_dev["mnt"].last_dec_requested #g_dev['mnt'].return_declination()
            # # # breakpoint()
            #ra_2 = g_dev['obs'].last_platesolved_ra
            #dec_2 = g_dev['obs'].last_platesolved_dec

            # NB NB Note if the platsove thorows back a nan the last_latesolved may be a stale value
            result=[ra_mount, dec_mount, g_dev['obs'].last_platesolved_ra, g_dev['obs'].last_platesolved_dec,g_dev['obs'].last_platesolved_ra_err, g_dev['obs'].last_platesolved_dec_err, sid, g_dev["mnt"].pier_side,g_dev['cam'].start_time_of_observation,g_dev['cam'].current_exposure_time]
            deviation_catalogue_for_tpoint.append (result)
            plog("Pointing run:  ", result)
            plog("Deviation Catalog:  ", deviation_catalogue_for_tpoint)
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
            latitude = float(self.obs.astro_events.wema_config['latitude'])
            f.write(Angle(latitude,u.degree).to_string(sep=' ')+ "\n")
        for entry in deviation_catalogue_for_tpoint:

            if (not np.isnan(entry[2]))and (not np.isnan(entry[3])):
                ra_wanted=Angle(entry[0],u.hour).to_string(sep=' ')
                dec_wanted=Angle(entry[1],u.degree).to_string(sep=' ')
                ra_got=Angle(entry[2], u.hour).to_string(sep=' ')


                if entry[7] == 0:
                    #NEED TO BREAKPOINT HERE AND FIX  NB NB What is the unit of the vales like entry[3]???
                    pierstring='0  1'
                    entry[2] += 12.
                    while entry[2] >= 24:
                        entry[2] -= 24.
                    while entry[2] < 0:   #This case should never occur
                        entry[2] += 24.
                    ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                    # # # breakpoint()
                    if latitude >= 0:
                        #I think the signs below *may be* incorrect WER 20240618
                        dec_got=Angle((180 - entry[3]),u.degree).to_string(sep=' ')  # as in 89 90 91 92 when going 'under the pole'.
                    else:
                        #These signs need testing and verification for the Southern Hemisphere.
                        dec_got=Angle((-180 + entry[3]),u.degree).to_string(sep=' ')
                else:
                    pierstring='0  0'
                    ra_got=Angle(entry[2], u.hour).to_string(sep=' ')
                    dec_got=Angle(entry[3], u.degree).to_string(sep=' ')




                sid_str = Angle(entry[6], u.hour).to_string(sep=' ')[:5]
                writeline = ra_wanted + " " + dec_wanted + " " + ra_got + " " + dec_got + " " + sid_str + " " + pierstring
                with open(tpointnamefile, "a+") as f:
                    f.write(writeline+"\n")
                plog(writeline)

        try:
            os.path.expanduser('~')
            plog (os.path.expanduser('~'))
            plog (os.path.expanduser('~')+ "/Desktop/TPOINT/")
            if not os.path.exists(os.path.expanduser('~')+ "/Desktop/TPOINT"):
                os.makedirs(os.path.expanduser('~')+ "/Desktop/TPOINT")
            shutil.copy (tpointnamefile, os.path.expanduser('~') + "/Desktop/TPOINT/" + 'TPOINTDAT'+str(time.time()).replace('.','d')+'.DAT')
        except:
            plog('Could not copy file to tpoint directory... you will have to do it yourself!')

        plog ("Final devation catalogue for Tpoint")
        plog (deviation_catalogue_for_tpoint)

        g_dev['obs'].auto_centering_off = prev_auto_centering

        g_dev['obs'].mount_reference_model_off = previous_mount_reference_model_off

        g_dev['obs'].flush_command_queue()

        self.total_sequencer_control = False
        g_dev['obs'].stop_processing_command_requests = False

        return



    def sky_grid_pointing_run(self, max_pointings=50, alt_minimum=30):

        g_dev['obs'].get_enclosure_status_from_aws()
        if not g_dev['obs'].assume_roof_open and 'Closed' in g_dev['obs'].enc_status['shutter_status']:
            plog('Roof is shut, so cannot do requested pointing run.')
            g_dev["obs"].send_to_user('Roof is shut, so cannot do requested pointing run.')
            return

        self.total_sequencer_control = True
        g_dev['obs'].stop_processing_command_requests = True

        prev_auto_centering = g_dev['obs'].auto_centering_off
        g_dev['obs'].auto_centering_off = True

        previous_mount_reference_model_off = copy.deepcopy(g_dev['obs'].mount_reference_model_off)
        g_dev['obs'].mount_reference_model_off = True

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
                g_dev['obs'].flush_command_queue()
                self.total_sequencer_control = False
                g_dev['obs'].stop_processing_command_requests = False
                return
            if not g_dev['obs'].open_and_enabled_to_observe and not g_dev['obs'].scope_in_manual_mode:
                g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")

                g_dev['obs'].flush_command_queue()
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
                #g_dev['mnt'].slew_async_directly(ra=grid_star[0] /15, dec=grid_star[1])

                g_dev['mnt'].go_command(ra=grid_star[0] /15, dec=grid_star[1])
            except:
                plog ("Difficulty in directly slewing to object")
                plog(traceback.format_exc())
                if g_dev['mnt'].theskyx:
                    self.obs.kill_and_reboot_theskyx(grid_star[0] / 15, grid_star[1])
                else:
                    plog(traceback.format_exc())

            g_dev['mnt'].wait_for_slew(wait_after_slew=False)

            g_dev["obs"].update_status()


            g_dev["mnt"].last_ra_requested=grid_star[0] / 15
            g_dev["mnt"].last_dec_requested=grid_star[1]

            req = { 'time': self.config['pointing_exposure_time'], 'smartstack': False, 'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}
            opt = { 'count': 1,  'filter': 'pointing'}
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
                        g_dev['obs'].flush_command_queue()
                        self.total_sequencer_control = False
                        g_dev['obs'].stop_processing_command_requests = False
                        return
                    if not g_dev['obs'].open_and_enabled_to_observe:
                        g_dev["obs"].send_to_user("Cancelling out of activity as no longer open and enabled to observe.")
                        g_dev['obs'].flush_command_queue()
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
            # # # breakpoint()
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
            latitude = float(self.obs.astro_events.wema_config['latitude'])
            f.write(Angle(latitude,u.degree).to_string(sep=' ')+ "\n")
        for entry in deviation_catalogue_for_tpoint:
            if (not np.isnan(entry[2])) and (not np.isnan(entry[3]) ):
                ra_wanted=Angle(entry[0],u.hour).to_string(sep=' ')
                dec_wanted=Angle(entry[1],u.degree).to_string(sep=' ')
                ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                if entry[7] == 0:
                    pierstring='0  1'
                    entry[2] += 12.
                    while entry[2] >= 24:
                        entry[2] -= 24.
                    ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                    # # breakpoint()
                    if latitude >= 0:
                        dec_got=Angle((180 - entry[3]),u.degree).to_string(sep=' ')  # as in 89 90 91 92 when going 'under the pole'.
                    else:
                        dec_got=Angle(-(180 + entry[3]),u.degree).to_string(sep=' ')
                else:
                    pierstring='0  0'  #NB NB I think this is supposed to be '1   0'.  WER
                    ra_got=Angle(entry[2],u.hour).to_string(sep=' ')
                    dec_got=Angle(entry[3],u.degree).to_string(sep=' ')
                sid_str = Angle(entry[6], u.hour).to_string(sep=' ')[:5]
                writeline = ra_wanted + " " + dec_wanted + " " + ra_got + " " + dec_got + " "+ sid_str + " "+ pierstring
                with open(tpointnamefile, "a+") as f:
                    f.write(writeline+"\n")
                plog(writeline)

        try:
            os.path.expanduser('~')
            plog (os.path.expanduser('~'))
            plog (os.path.expanduser('~')+ "/Desktop/TPOINT/")
            if not os.path.exists(os.path.expanduser('~')+ "/Desktop/TPOINT"):
                os.makedirs(os.path.expanduser('~')+ "/Desktop/TPOINT")
            shutil.copy (tpointnamefile, os.path.expanduser('~') + "/Desktop/TPOINT/" + 'TPOINTDAT'+str(time.time()).replace('.','d')+'.DAT')
        except:
            plog('Could not copy file to tpoint directory... you will have to do it yourself!')

        plog ("Final devation catalogue for Tpoint")
        plog (deviation_catalogue_for_tpoint)


        g_dev['obs'].mount_reference_model_off = previous_mount_reference_model_off
        g_dev['obs'].auto_centering_off = prev_auto_centering

        g_dev['obs'].flush_command_queue()

        self.total_sequencer_control = False

        g_dev['obs'].stop_processing_command_requests = False
        return


    def centering_exposure(self, no_confirmation=False, try_hard=False, try_forever=False, calendar_event_id=None):

        """
        A pretty regular occurance - when the pointing on the scopes isn't tuned up.
        This gets the image within a few arcseconds usually. Called from a variety of spots,
        but the most important is centering the requested RA and Dec just prior to starting
        a longer project block.
        """
        if g_dev['obs'].auto_centering_off:  #Auto centering off means OFF!
            plog('auto_centering is off.')
            return

        if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
            plog("Too bright to consider platesolving!")
            plog("Hence too bright to do a centering exposure.")
            g_dev["obs"].send_to_user("Too bright, or early, to auto-center the image.")

            return

        # Don't try forever if focussing
        if self.focussing:
            try_hard=True
            try_forever=False

        # Turn off the pier flip detection if we enter a centering exposure to fix the pier flip
        g_dev['mnt'].pier_flip_detected=False
        if g_dev['cam'].pixscale == None: # or np.isnan(g_dev['cam'].pixscale):
            plog ("Finding pixelscale for the first time. This could take a whilE! 5-10 Minutes.")
            g_dev["obs"].send_to_user("Finding pixelscale for the first time. This could take a while! 5-10 Minutes.")
            req = {'time': self.config['pointing_exposure_time'] * 3,  'alias':  str(g_dev["cam"].config["name"]), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
            opt = {'count': 1, 'filter': 'focus'}

        else:
            req = {'time': self.config['pointing_exposure_time'],  'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
            opt = {'count': 1, 'filter': 'pointing'}

        successful_platesolve=False

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
            plog('stop_all_activity, so cancelling out of Centering')
            return

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
                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                time.sleep(1)
            self.mosaic_center_ra=g_dev['mnt'].return_right_ascension()
            self.mosaic_center_dec=g_dev['mnt'].return_declination()
            return result

        if (try_hard or try_forever) and not successful_platesolve:
            plog("Didn't get a successful platesolve at an important time for pointing, trying a double exposure")

            if g_dev['cam'].pixscale == None:
                plog ("Didn't find a solution with the first exposure, trying again.")
                g_dev["obs"].send_to_user("Finding pixelscale for the second time. This could take a whilE!")
                req = {'time': float(self.config['pointing_exposure_time']) * 5,  'alias':  g_dev['cam'].name, 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'focus'}
            else:
                req = {'time': float(self.config['pointing_exposure_time']) * 2,  'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
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
                    if g_dev["obs"].stop_all_activity:
                        plog('stop_all_activity cancelling out of centering')
                        return
                    pass

            if not (g_dev['obs'].last_platesolved_ra != np.nan and str(g_dev['obs'].last_platesolved_ra) != 'nan'):

                plog("Didn't get a successful platesolve at an important time for pointing AGAIN, trying a Lum filter")

                req = {'time': float(self.config['pointing_exposure_time']) * 2.5,  'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
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

                reported=0
                temptimer=time.time()
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
                        if g_dev["obs"].stop_all_activity:
                            plog('stop_all_activity cancelling out of centering')
                            return
                        pass

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
                g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                g_dev['obs'].time_of_last_slew=time.time()
                try:
                    g_dev['mnt'].slew_async_directly(ra=g_dev["mnt"].last_ra_requested, dec=g_dev["mnt"].last_dec_requested)
                except:
                    plog(traceback.format_exc())
                    if g_dev['mnt'].theskyx:
                        self.obs.kill_and_reboot_theskyx(g_dev["mnt"].last_ra_requested, g_dev["mnt"].last_dec_requested)
                    else:
                        plog(traceback.format_exc())

                g_dev['mnt'].wait_for_slew(wait_after_slew=False)

                req = {'time': float(self.config['pointing_exposure_time']) * 3,  'alias':  str(g_dev['cam'].name), 'image_type': 'pointing'}   #  NB Should pick up filter and constats from config
                opt = {'count': 1, 'filter': 'pointing'}
                result = g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=True, solve_it=True,useastrometrynet=True)

                # test for blockend
                if self.blockend != None:
                    g_dev['obs'].request_update_calendar_blocks()
                    endOfExposure = datetime.datetime.utcnow() + datetime.timedelta(seconds=float(self.config['pointing_exposure_time']) * 3)
                    now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'
                    blockended = now_date_timeZ  >= self.blockend
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

                    foundcalendar=False

                    for tempblock in self.blocks:
                        try:
                            if tempblock['event_id'] == calendar_event_id :
                                foundcalendar=True
                                self.blockend=tempblock['end']
                        except:
                            plog("glitch in calendar finder")
                            plog(str(tempblock))
                    now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                    if foundcalendar == False or now_date_timeZ >= self.blockend:
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
            req = {'time': self.config['pointing_exposure_time'],  'alias':  str(g_dev['cam'].name), 'image_type': 'light'}   #  NB Should pick up filter and constats from config
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

        def ephem_date_to_utc_iso_string(ephem_date):
            return ephem_date.datetime().isoformat().split(".")[0] + "Z"

        calendar_update_url = "https://calendar.photonranch.org/calendar/siteevents"

        start_time = ephem_date_to_utc_iso_string(g_dev['events']['Eve Sky Flats'])
        end_time = ephem_date_to_utc_iso_string(g_dev['events']['End Morn Sky Flats'])
        body = json.dumps({
            "site": self.config["obs_id"],
            "start": start_time,
            "end": end_time,
            "full_project_details:": False,
        })
        try:
            self.blocks = reqs.post(calendar_update_url, body, timeout=20).json()
        except Exception as e:
            plog(e)
            plog("Failed to update the calendar. This is not normal. Request url was {calendar_update_url} and body was {body}.")


def stack_nanmedian_row_memmapped(inputinfo):
    (pldrivetempfiletemp,counter,shape) = inputinfo
    tempPLDrive = np.memmap(pldrivetempfiletemp, dtype='float32', mode= 'r', shape = shape )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return bn.nanmedian(tempPLDrive[counter,:,:], axis=1)


def stack_nanmedian_row(inputline):
    return bn.nanmedian(inputline, axis=1).astype(np.float32)
