
"""
Observatory is the central organising part of a given observatory system.

It deals with connecting all the devices together and deals with decisions that
involve multiple devices and fundamental operations of the OBS.

It also organises the various queues that process, send, slice and dice data.
"""

import ephem
import datetime
import json
import os
import queue
import shelve
import threading
from multiprocessing.pool import ThreadPool
import time
import sys
import copy
import shutil
import glob
import subprocess
import pickle
from math import sqrt
from astropy.io import fits
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord, get_sun, AltAz
from astropy.time import Time
from astropy import units as u
from astropy.table import Table

from astropy.nddata import block_reduce
from dotenv import load_dotenv
import numpy as np

import requests
import urllib.request
import traceback
import psutil
from global_yard import g_dev
import ptr_config
from devices.camera import Camera
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
from devices.mount import Mount
from devices.telescope import Telescope
from devices.rotator import Rotator
from devices.selector import Selector
from devices.screen import Screen
from devices.sequencer import Sequencer
import ptr_events
from ptr_utility import plog
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)

# Incorporate better request retry strategy
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))

# The ingester should only be imported after environment variables are loaded in.
load_dotenv(".env")
from ocs_ingester.ingester import frame_exists, upload_file_and_ingest_to_archive
import ocs_ingester.exceptions



def test_connect(host='http://google.com'):
    try:
        urllib.request.urlopen(host)  # Python 3.x
        return True
    except:
        return False

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

def findProcessIdByName(processName):
    '''
    Get a list of all the PIDs of a all the running process whose name contains
    the given string processName
    '''
    listOfProcessObjects = []
    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name', 'create_time'])
            # Check if process name contains the given name string.
            if processName.lower() in pinfo['name'].lower():
                listOfProcessObjects.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return listOfProcessObjects


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


def send_status(obsy, column, status_to_send):
    """Sends an update to the status endpoint."""
    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    payload = {"statusType": str(column), "status": status_to_send}
    try:
        data = json.dumps(payload)
    except Exception as e:
        plog("Failed to create status payload. Usually not fatal:  ", e)

    try:
        reqs.post(uri_status, data=data, timeout=20)
    except Exception as e:
        plog("Failed to send_status. Usually not fatal:  ", e)


class Observatory:
    """

    Observatory is the central organising part of a given observatory system.

    It deals with connecting all the devices together and deals with decisions that
    involve multiple devices and fundamental operations of the OBS.

    It also organises the various queues that process, send, slice and dice data.

    """

    def __init__(self, name, ptr_config):


        self.name = name
        self.obs_id = name
        g_dev['name'] = name

        self.config = ptr_config
        self.wema_name = self.config['wema_name']

        # Creation of directory structures if they do not exist already
        self.obsid_path = str(ptr_config["archive_path"] + '/' + self.name + '/').replace('//','/')
        g_dev["obsid_path"] = self.obsid_path
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)
        self.local_calibration_path = ptr_config['local_calibration_path'] + self.config['obs_id'] + '/'
        if not os.path.exists(ptr_config['local_calibration_path']):
            os.makedirs(ptr_config['local_calibration_path'])
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path)

        if self.config["save_to_alt_path"] == "yes":
            self.alt_path= ptr_config['alt_path'] + self.config['obs_id'] + '/'
            if not os.path.exists(ptr_config['alt_path']):
                os.makedirs(ptr_config['alt_path'])
            if not os.path.exists(self.alt_path):
                os.makedirs(self.alt_path)

        if not os.path.exists(self.obsid_path + "ptr_night_shelf"):
            os.makedirs(self.obsid_path + "ptr_night_shelf")
        if not os.path.exists(self.obsid_path + "archive"):
            os.makedirs(self.obsid_path + "archive")
        if not os.path.exists(self.obsid_path + "tokens"):
            os.makedirs(self.obsid_path + "tokens")
        if not os.path.exists(self.obsid_path + "astropycache"):
            os.makedirs(self.obsid_path + "astropycache")


        # Local Calibration Paths
        camera_name = self.config['camera']['camera_1_1']['name']
        if not os.path.exists(self.local_calibration_path + "archive/" + camera_name + "/calibmasters"):
            os.makedirs(self.local_calibration_path + "archive/" + camera_name + "/calibmasters")
        if not os.path.exists(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations"):
            os.makedirs(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations")
        if not os.path.exists(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/darks"):
            os.makedirs(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/darks")
        if not os.path.exists(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/biases"):
            os.makedirs(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/biases")
        if not os.path.exists(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/flats"):
            os.makedirs(self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/flats")

        self.calib_masters_folder = self.local_calibration_path + "archive/" + camera_name + "/calibmasters" + '/'
        self.local_dark_folder = self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/darks" + '/'
        self.local_bias_folder = self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/biases" + '/'
        self.local_flat_folder = self.local_calibration_path + "archive/" + camera_name + "/localcalibrations/flats" + '/'

        # Directories for broken and orphaned upload files
        self.orphan_path=self.config['archive_path'] +'/' + self.name + '/' + 'orphans/'
        if not os.path.exists(self.orphan_path):
            os.makedirs(self.orphan_path)

        self.broken_path=self.config['archive_path'] +'/' + self.name + '/' + 'broken/'
        if not os.path.exists(self.broken_path):
            os.makedirs(self.broken_path)


        # Clear out smartstacks directory
        try:
            shutil.rmtree(self.local_calibration_path + "smartstacks")
        except:
            pass
        if not os.path.exists(self.local_calibration_path + "smartstacks"):
            os.makedirs(self.local_calibration_path + "smartstacks")

        # Orphan and Broken paths
        self.orphan_path=self.config['archive_path'] +'/' + self.name + '/' + 'orphans/'
        if not os.path.exists(self.orphan_path):
            os.makedirs(self.orphan_path)

        self.broken_path=self.config['archive_path'] +'/' + self.name + '/' + 'broken/'
        if not os.path.exists(self.broken_path):
            os.makedirs(self.broken_path)


        # Software Kills.
        # There are some software that really benefits from being restarted from
        # scratch on Windows, so on bootup of obs.py, the system closes them down
        # Reconnecting the devices reboots the softwares later on.
        try:
            os.system("taskkill /IM AltAzDSConfig.exe /F")
        except:
            pass
        try:
            os.system('taskkill /IM "Gemini Software.exe" /F')

        except:
            pass
        try:
            os.system("taskkill /IM ASCOM.AltAzDS.exe /F")
        except:
            pass
        try:
            os.system("taskkill /IM TheSkyX.exe /F")
        except:
            pass
        try:
            os.system("taskkill /IM TheSky64.exe /F")
        except:
            pass

        listOfProcessIds = findProcessIdByName('maxim_dl')
        for pid in listOfProcessIds:
            pid_num = pid['pid']
            plog("Terminating existing Maxim process:  ", pid_num)
            p2k = psutil.Process(pid_num)
            p2k.terminate()


        # Initialisation of variables best explained elsewhere
        self.status_interval = 0
        self.status_count = 0
        self.status_upload_time = 0.5
        self.time_last_status = time.time() - 3
        self.all_device_types = ptr_config["device_types"]  # May not be needed
        self.device_types = ptr_config["device_types"]  # ptr_config['short_status_devices']


        # This prevents ascom calls from update_status colliding with the full_update section
        self.full_update_lock = False

        # Timers to only update status at regular specified intervals.
        self.observing_status_timer = datetime.datetime.now() - datetime.timedelta(
            days=1
        )
        self.observing_check_period = self.config[
            "observing_check_period"
        ]
        self.enclosure_status_timer = datetime.datetime.now() - datetime.timedelta(
            days=1
        )
        self.enclosure_check_period = self.config[
            "enclosure_check_period"
        ]
        self.obs_settings_upload_timer = time.time() - 20
        self.obs_settings_upload_period = 60

        self.last_time_report_to_console = time.time()-700

        self.last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        self.images_since_last_solve = 10000

        self.project_call_timer = time.time()
        self.get_new_job_timer = time.time()
        self.scan_request_timer = time.time()

        # Sometimes we update the status in a thread. This variable prevents multiple status updates occuring simultaneously
        self.currently_updating_status=False



        # Create this actual thread
        self.update_status_queue = queue.Queue(maxsize=0)
        self.update_status_thread=threading.Thread(target=self.update_status_thread)
        self.update_status_thread.start()
        # Also this is true for the FULL update.
        self.currently_updating_FULL=False

        self.FULL_update_thread_queue = queue.Queue(maxsize=0)
        self.FULL_update_thread=threading.Thread(target=self.full_update_thread)
        self.FULL_update_thread.start()

        self.too_hot_temperature=self.config['temperature_at_which_obs_too_hot_for_camera_cooling']
        self.warm_report_timer = time.time()-600

        # Keep track of how long it has been since the last activity of slew or exposure
        # This is useful for various functions... e.g. if telescope idle for an hour, park.
        self.time_of_last_exposure = time.time()
        self.time_of_last_slew = time.time()

        # Only poll the broad safety checks (altitude and inactivity) every 5 minutes
        self.safety_check_period = self.config['safety_check_period']
        self.time_since_safety_checks = time.time() - (2* self.safety_check_period)

        # Keep track of how long it has been since the last live connection to the internet
        self.time_of_last_live_net_connection = time.time()

        # Initialising various flags best explained elsewhere
        self.env_exists = os.path.exists(os.getcwd() + '\.env')  # Boolean, check if .env present
        self.stop_processing_command_requests = False
        self.platesolve_is_processing = False
        self.stop_all_activity = False  # This is used to stop the camera or sequencer
        self.exposure_halted_indicator = False
        self.camera_sufficiently_cooled_for_calibrations = True
        self.last_slew_was_pointing_slew = False
        self.open_and_enabled_to_observe = False
        self.net_connection_dead = False


        # Set default obs safety settings at bootup
        self.scope_in_manual_mode = self.config['scope_in_manual_mode']
        self.moon_checks_on = self.config['moon_checks_on']
        self.sun_checks_on = self.config['sun_checks_on']
        self.altitude_checks_on = self.config['altitude_checks_on']
        self.daytime_exposure_time_safety_on = self.config['daytime_exposure_time_safety_on']
        self.mount_reference_model_off = self.config['mount_reference_model_off']
        self.admin_owner_commands_only = False
        self.assume_roof_open = False
        self.auto_centering_off = False

        # Instantiate the helper class for astronomical events
        # Soon the primary event / time values can come from AWS.  NB NB   I send them there! Why do we want to put that code in AWS???
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events()
        self.astro_events.display_events()

        # If the camera is detected as substantially (20 degrees) warmer than the setpoint
        # during safety checks, it will keep it warmer for about 20 minutes to make sure
        # the camera isn't overheating, then return it to its usual temperature.
        self.camera_overheat_safety_warm_on = False
        self.camera_overheat_safety_timer = time.time()
        # Some things you don't want to check until the camera has been cooling for a while.
        self.camera_time_initialised = time.time()
        # You want to make sure that the camera has been cooling for a while at the setpoint
        # Before taking calibrations to ensure the sensor is evenly cooled
        self.last_time_camera_was_warm = time.time() - 6000

        # If there is a pointing correction needed, then it is REQUESTED
        # by the platesolve thread and then the code will interject
        # a pointing correction at an appropriate stage.
        # But if the telescope moves in the meantime, this is cancelled.
        # A telescope move itself should already correct for this pointing in the process of moving.
        # This is sort of a more elaborate and time-efficient version of the previous "re-seek"
        self.pointing_correction_requested_by_platesolve_thread = False
        self.pointing_recentering_requested_by_platesolve_thread = False
        self.pointing_correction_request_time = time.time()
        self.pointing_correction_request_ra = 0.0
        self.pointing_correction_request_dec = 0.0
        self.pointing_correction_request_ra_err = 0.0
        self.pointing_correction_request_dec_err = 0.0
        self.last_platesolved_ra = np.nan
        self.last_platesolved_dec =np.nan
        self.last_platesolved_ra_err = np.nan
        self.last_platesolved_dec_err =np.nan
        self.platesolve_errors_in_a_row=0

        g_dev["obs"] = self
        obsid_str = ptr_config["obs_id"]
        g_dev["obsid"]: obsid_str
        self.g_dev = g_dev

        # Use the configuration to instantiate objects for all devices.
        self.create_devices()

        self.last_update_complete = time.time() -5

        # Reset mount reference for delta_ra and delta_dec on bootup
        g_dev["mnt"].reset_mount_reference()
        g_dev['mnt'].get_mount_coordinates()

        # Boot up the various queues to process

        if self.config['ingest_raws_directly_to_archive']:
            self.ptrarchive_queue = queue.PriorityQueue(maxsize=0)
            self.ptrarchive_queue_thread = threading.Thread(target=self.send_to_ptrarchive, args=())
            self.ptrarchive_queue_thread.start()


        if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
            self.pipearchive_queue = queue.Queue(maxsize=0)
            self.pipearchive_queue_thread = threading.Thread(target=self.copy_to_pipearchive, args=())
            self.pipearchive_queue_thread.start()

        if self.config['save_to_alt_path'] == 'yes':

            self.altarchive_queue = queue.Queue(maxsize=0)
            self.altarchive_queue_thread = threading.Thread(target=self.copy_to_altarchive, args=())
            self.altarchive_queue_thread.start()

        self.fast_queue = queue.PriorityQueue(maxsize=0)
        self.fast_queue_thread = threading.Thread(target=self.fast_to_ui, args=())
        self.fast_queue_thread.start()

        self.mediumui_queue = queue.PriorityQueue(maxsize=0)
        self.mediumui_thread = threading.Thread(target=self.medium_to_ui, args=())
        self.mediumui_thread.start()

        self.calibrationui_queue = queue.PriorityQueue(maxsize=0)
        self.calibrationui_thread = threading.Thread(target=self.calibration_to_ui, args=())
        self.calibrationui_thread.start()

        self.slow_camera_queue = queue.PriorityQueue(maxsize=0)
        self.slow_camera_queue_thread = threading.Thread(target=self.slow_camera_process, args=())
        self.slow_camera_queue_thread.start()

        self.send_status_queue = queue.Queue(maxsize=0)
        self.send_status_queue_thread = threading.Thread(target=self.send_status_process, args=())
        self.send_status_queue_thread.start()

        self.platesolve_queue = queue.Queue(maxsize=0)
        self.platesolve_queue_thread = threading.Thread(target=self.platesolve_process, args=())
        self.platesolve_queue_thread.start()

        self.sep_queue = queue.Queue(maxsize=0)
        self.sep_queue_thread = threading.Thread(target=self.sep_process, args=())
        self.sep_queue_thread.start()

        self.mainjpeg_queue = queue.Queue(maxsize=0)
        self.mainjpeg_queue_thread = threading.Thread(target=self.mainjpeg_process, args=())
        self.mainjpeg_queue_thread.start()

        self.laterdelete_queue = queue.Queue(maxsize=0)
        self.laterdelete_queue_thread = threading.Thread(target=self.laterdelete_process, args=())
        self.laterdelete_queue_thread.start()


        self.sendtouser_queue = queue.Queue(maxsize=0)
        self.sendtouser_queue_thread = threading.Thread(target=self.sendtouser_process, args=())
        self.sendtouser_queue_thread.start()

        self.cmd_queue = queue.Queue(
            maxsize=0
        )

        self.smartstack_queue = queue.Queue(
            maxsize=0
        )
        self.smartstack_queue_thread = threading.Thread(target=self.smartstack_image, args=())
        self.smartstack_queue_thread.start()



        # send up obs status immediately
        self.obs_settings_upload_timer = time.time() - 2*self.obs_settings_upload_period
        self.update_status(dont_wait=True)


        # A dictionary that holds focusresults for the SEP queue.
        self.fwhmresult={}
        self.fwhmresult["error"] = True
        self.fwhmresult['FWHM'] = np.nan
        self.fwhmresult["mean_focus"] = np.nan
        self.fwhmresult['No_of_sources'] = np.nan

        # On initialisation, there should be no commands heading towards the site
        # So this command reads the commands waiting and just ... ignores them
        # essentially wiping the command queue coming from AWS.
        # This prevents commands from previous nights/runs suddenly running
        # when obs.py is booted (has happened a bit in the past!)
        reqs.request(
            "POST", "https://jobs.photonranch.org/jobs/getnewjobs", data=json.dumps({"site": self.name}), timeout=30
        ).json()

        # On startup, collect orphaned fits files that may have been dropped from the queue
        # when the site crashed or was rebooted.
        if self.config['ingest_raws_directly_to_archive']:
            g_dev['seq'].collect_and_queue_neglected_fits()

        # Inform UI of reboot
        self.send_to_user("Observatory code has been rebooted. Manually queued commands have been flushed.")

        # Upload the config to the UI
        self.update_config()

        # Report previously calculated Camera Gains as part of bootup
        textfilename= g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'cameragain' + g_dev['cam'].name + str(g_dev['obs'].name) +'.txt'
        if os.path.exists(textfilename):
            try:
                 with open(textfilename, 'r') as f:
                     lines=f.readlines()
                     #print (lines)
                     for line in lines:
                         plog (line.replace('\n',''))
            except:
                plog ("something wrong with opening camera gain text file")
                # breakpoint()
                pass

        # Report filter throughputs as part of bootup
        filter_throughput_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filterthroughput' + g_dev['cam'].name + str(g_dev['obs'].name))

        if len(filter_throughput_shelf)==0:
            plog ("Looks like there is no filter throughput shelf.")
        else:
            plog ("Stored filter throughputs")
            for filtertempgain in list(filter_throughput_shelf.keys()):
                plog (str(filtertempgain) + " " + str(filter_throughput_shelf[filtertempgain]))
        filter_throughput_shelf.close()


        # Temporary toggle to turn auto-centering off
        #self.auto_centering_off = True



        # Initialisation complete!



    def set_last_reference(self, delta_ra, delta_dec, last_time):
        mnt_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/" + "last" + str(self.name))
        mnt_shelf["ra_cal_offset"] = delta_ra
        mnt_shelf["dec_cal_offset"] = delta_dec
        mnt_shelf["time_offset"] = last_time
        mnt_shelf.close()
        return

    def get_last_reference(self):
        mnt_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/" + "last" + str(self.name))
        delta_ra = mnt_shelf["ra_cal_offset"]
        delta_dec = mnt_shelf["dec_cal_offset"]
        last_time = mnt_shelf["time_offset"]
        mnt_shelf.close()
        return delta_ra, delta_dec, last_time

    def reset_last_reference(self):

        mnt_shelf = shelve.open(self.obsid_path + "ptr_night_shelf/" + "last" + str(self.name))
        mnt_shelf["ra_cal_offset"] = None
        mnt_shelf["dec_cal_offset"] = None
        mnt_shelf["time_offset"] = None
        mnt_shelf.close()
        return

    def create_devices(self):
        """Dictionary to store created devices, subcategorized by device type."""

        self.all_devices = {}
        # Create device objects by type, going through the config by type.
        for dev_type in self.all_device_types:
            self.all_devices[dev_type] = {}
            # Get the names of all the devices from each dev_type.
            devices_of_type = self.config.get(dev_type, {})
            device_names = devices_of_type.keys()

            # Instantiate each device object based on its type
            for name in device_names:

                try:
                    driver = devices_of_type[name]["driver"]
                except:
                    pass
                settings = devices_of_type[name].get("settings", {})

                if dev_type == "mount":
                    device = Mount(
                        driver, name, settings, self.config, self.astro_events, tel=True
                    )  # NB this needs to be straightened out.
                elif dev_type == "telescope":  # order of attaching is sensitive
                     device = Telescope(driver, name, settings, self.config, tel=True)
                elif dev_type == "rotator":
                    device = Rotator(driver, name, self.config)
                elif dev_type == "focuser":
                    device = Focuser(driver, name, self.config)
                elif dev_type == "screen":
                    device = Screen(driver, name, self.config)
                elif dev_type == "filter_wheel":
                    device = FilterWheel(driver, name, self.config)
                elif dev_type == "selector":
                    device = Selector(driver, name, self.config)
                elif dev_type == "camera":
                    device = Camera(driver, name, self.config)
                elif dev_type == "sequencer":
                    device = Sequencer(driver, name, self.config, self.astro_events)
                else:
                    plog(f"Unknown device: {name}")
                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device
        plog("Finished creating devices.")

    def update_config(self):
        """Sends the config to AWS."""

        uri = f"{self.config['obs_id']}/config/"
        self.config["events"] = g_dev["events"]
        # Insert camera size into config
        self.config['camera']['camera_1_1']['camera_size_x'] = g_dev['cam'].imagesize_x
        self.config['camera']['camera_1_1']['camera_size_y'] = g_dev['cam'].imagesize_y
        #breakpoint()

        retryapi=True
        while retryapi:
            try:
                response = authenticated_request("PUT", uri, self.config)
                retryapi=False
            except:
                plog ("connection glitch in update config. Waiting 5 seconds.")
                time.sleep(5)
        if 'message' in response:
            if response['message'] == "Missing Authentication Token":
                plog("Missing Authentication Token. Config unable to be uploaded. Please fix this now.")
                sys.exit()
            else:
                plog("There may be a problem in the config upload? Here is the response.")
                plog(response)
        elif 'ResponseMetadata' in response:
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                plog("Config uploaded successfully.")
                #breakpoint()
                #g_dev['seq'].nightly_reset_script()

            else:
                plog("Response to obsid config upload unclear. Here is the response")
                plog(response)

        else:
            plog("Response to obsid config upload unclear. Here is the response")
            plog(response)

    def cancel_all_activity(self):

        g_dev["obs"].stop_all_activity = True
        g_dev["obs"].stop_all_activity_timer = time.time()
        plog("Stop_all_activity is now set True.")
        self.send_to_user(
            "Cancel/Stop received. Exposure stopped, camera may begin readout, then will discard image."
        )
        self.send_to_user(
            "Pending reductions and transfers to the PTR Archive are not affected."
        )
        # Now we need to cancel possibly a pending camera cycle or a
        # script running in the sequencer.  NOTE a stop or cancel empties outgoing queue at AWS side and
        # only a Cancel/Stop action is sent.  But we need to save any subsequent commands.

        plog("Emptying Command Queue")
        with self.cmd_queue.mutex:
            self.cmd_queue.queue.clear()

        plog("Stopping Exposure")

        try:
            g_dev["cam"]._stop_expose()
            g_dev["cam"].exposure_busy = False
            expresult = {}
            expresult["stopped"] = True

        except Exception as e:
            plog("Camera is not busy.", e)
            plog(traceback.format_exc())
            self.exposure_busy = False

        g_dev["obs"].exposure_halted_indicator = True
        g_dev["obs"].exposure_halted_indicator_timer = time.time()

    def scan_requests(self, cancel_check=False):
        """Gets commands from AWS, and post a STOP/Cancel flag.

        We limit the polling to once every 4 seconds because AWS does not
        appear to respond any faster. When we poll, we parse
        the action keyword for 'stop' or 'cancel' and post the
        existence of the timestamp of that command to the
        respective device attribute <self>.cancel_at. Then we
        enqueue the incoming command as well.

        NB at this time we are preserving one command queue
        for all devices at a site. This may need to change when we
        have parallel mountings or independently controlled cameras.
        """

        # To stop the scan requests getting hammered unnecessarily.
        # Which is has sometimes on net disconnections.
        if (time.time() - self.scan_request_timer) > 1.0:
            self.scan_request_timer = time.time()
            url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
            body = {"site": self.name}
            cmd = {}
            # Get a list of new jobs to complete (this request
            # marks the commands as "RECEIVED")
            try:
                unread_commands = reqs.request(
                    "POST", url_job, data=json.dumps(body), timeout=20
                ).json()
            except:
                plog("problem gathering scan requests. Likely just a connection glitch.")
                unread_commands=[]
        else:
            unread_commands=[]

        # Make sure the list is sorted in the order the jobs were issued
        # Note: the ulid for a job is a unique lexicographically-sortable id.
        if len(unread_commands) > 0:
            try:
                unread_commands.sort(key=lambda x: x["timestamp_ms"])
                # Process each job one at a time
                for cmd in unread_commands:
                    if (self.admin_owner_commands_only and (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles']))) or (not self.admin_owner_commands_only):


                        if cmd["action"] in ["cancel_all_commands", "stop"] or cmd["action"].lower() in ["stop", "cancel"] or (cmd["action"] == "run" and cmd["required_params"]["script"] == "stopScript"):

                            # A stop script command flags to the running scripts that it is time to stop
                            # activity and return. This period runs for about 30 seconds.
                            g_dev["obs"].send_to_user(
                                "A Cancel/Stop has been called. Cancelling out of running scripts over 30 seconds.")
                            g_dev['seq'].stop_script_called = True
                            g_dev['seq'].stop_script_called_time = time.time()
                            # Cancel out of all running exposures.
                            g_dev['obs'].cancel_all_activity()
                        else:
                            try:
                                action = cmd['action']
                            except:
                                action = None

                            try:
                                script = cmd['required_params']['script']
                            except:
                                script = None

                            if cmd["deviceType"]=='obs':
                                plog ('OBS COMMAND: received a system wide command')

                                if cmd['action']=='configure_pointing_reference_off':
                                    self.mount_reference_model_off = True
                                    plog ('mount_reference_model_off')
                                    g_dev["obs"].send_to_user("mount_reference_model_off.")

                                elif cmd['action']=='configure_pointing_reference_on':
                                    self.mount_reference_model_off = False
                                    plog ('mount_reference_model_on')
                                    g_dev["obs"].send_to_user("mount_reference_model_on.")

                                elif cmd['action']=='configure_telescope_mode':

                                    if cmd['required_params']['mode'] == 'manual':
                                        self.scope_in_manual_mode = True
                                        plog ('Manual Mode Engaged.')
                                        g_dev["obs"].send_to_user('Manual Mode Engaged.')
                                    else:
                                        self.scope_in_manual_mode = False
                                        plog ('Manual Mode Turned Off.')
                                        g_dev["obs"].send_to_user('Manual Mode Turned Off.')

                                elif cmd['action']=='configure_moon_safety':

                                    if cmd['required_params']['mode'] == 'on':
                                        self.moon_checks_on = True
                                        plog ('Moon Safety On')
                                        g_dev["obs"].send_to_user('Moon Safety On')
                                    else:
                                        self.moon_checks_on = False
                                        plog ('Moon Safety Off')
                                        g_dev["obs"].send_to_user('Moon Safety Off')

                                elif cmd['action']=='configure_sun_safety':

                                    if cmd['required_params']['mode'] =='on':
                                        self.sun_checks_on = True
                                        plog ('Sun Safety On')
                                        g_dev["obs"].send_to_user('Sun Safety On')
                                    else:
                                        self.sun_checks_on = False
                                        plog ('Sun Safety Off')
                                        g_dev["obs"].send_to_user('Sun Safety Off')

                                elif cmd['action']=='configure_altitude_safety':

                                    if cmd['required_params']['mode'] == 'on':
                                        self.altitude_checks_on = True
                                        plog ('Altitude Safety On')
                                        g_dev["obs"].send_to_user('Altitude Safety On')
                                    else:
                                        self.altitude_checks_on = False
                                        plog ('Altitude Safety Off')
                                        g_dev["obs"].send_to_user('Altitude Safety Off')

                                elif cmd['action']=='configure_daytime_exposure_safety':

                                    if cmd['required_params']['mode'] == 'on':
                                        self.daytime_exposure_time_safety_on = True
                                        plog ('Daytime Exposure Safety On')
                                        g_dev["obs"].send_to_user('Daytime Exposure Safety On')
                                    else:
                                        self.daytime_exposure_time_safety_on = False
                                        plog ('Daytime Exposure Safety Off')
                                        g_dev["obs"].send_to_user('Daytime Exposure Safety Off')

                                elif cmd['action']=='start_simulating_open_roof':
                                    self.assume_roof_open = True
                                    self.open_and_enabled_to_observe=True
                                    g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()
                                    self.enclosure_status_timer = datetime.datetime.now()
                                    plog ('Roof is now assumed to be open. WEMA shutter status is ignored.')
                                    g_dev["obs"].send_to_user('Roof is now assumed to be open. WEMA shutter status is ignored.')

                                elif cmd['action']=='stop_simulating_open_roof':
                                    self.assume_roof_open = False
                                    g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()
                                    self.enclosure_status_timer = datetime.datetime.now()
                                    plog ('Roof is now NOT assumed to be open. Reading WEMA shutter status.')
                                    g_dev["obs"].send_to_user('Roof is now NOT assumed to be open. Reading WEMA shutter status.')


                                elif cmd['action']=='configure_who_can_send_commands':
                                    if cmd['required_params']['only_accept_admin_or_owner_commands'] == True:
                                        self.admin_owner_commands_only = True
                                        plog ('Scope set to only accept admin or owner commands')
                                        g_dev["obs"].send_to_user('Scope set to only accept admin or owner commands')
                                    else:
                                        self.admin_owner_commands_only = False
                                        plog ('Scope now open to all user commands, not just admin or owner.')
                                        g_dev["obs"].send_to_user('Scope now open to all user commands, not just admin or owner.')
                                elif cmd['action']=='obs_configure_auto_center_on':
                                    self.auto_centering_off = False
                                    plog ('Scope set to automatically center.')
                                    g_dev["obs"].send_to_user('Scope set to automatically center.')
                                elif cmd['action']=='obs_configure_auto_center_off':
                                    self.auto_centering_off = True
                                    plog ('Scope set to not automatically center.')
                                    g_dev["obs"].send_to_user('Scope set to not automatically center.')
                                else:
                                    print ("Unknown command: " + str(cmd))


                                self.obs_settings_upload_timer = time.time() - 2*self.obs_settings_upload_period

                                self.request_update_status() #self.update_status(dont_wait=True)

                            # Check here for admin/owner only functions
                            elif action == "run" and script == 'collectScreenFlats' and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                plog("Request rejected as flats can only be commanded by admin user.")
                                g_dev['obs'].send_to_user(
                                    "Request rejected as flats can only be commanded by admin user.")
                            elif action == "run" and script == 'collectSkyFlats' and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                plog("Request rejected as flats can only be commanded by admin user.")
                                g_dev['obs'].send_to_user(
                                    "Request rejected as flats can only be commanded by admin user.")

                            elif action == "run" and script in ['pointingRun'] and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                plog("Request rejected as pointing runs can only be commanded by admin user.")
                                g_dev['obs'].send_to_user(
                                    "Request rejected as pointing runs can only be commanded by admin user.")
                            elif action == "run" and script in ("collectBiasesAndDarks") and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                plog("Request rejected as bias and darks can only be commanded by admin user.")
                                g_dev['obs'].send_to_user(
                                    "Request rejected as bias and darks can only be commanded by admin user.")

                            # Check here for irrelevant commands
                            elif cmd['deviceType'] == 'screen' and self.config['screen']['screen1']['driver'] == None:
                                plog("Refusing command as there is no screen")
                                g_dev['obs'].send_to_user("Request rejected as site has no flat screen.")
                            elif cmd['deviceType'] == 'rotator' and self.config['rotator']['rotator1']['driver'] == None:
                                plog("Refusing command as there is no rotator")
                                g_dev['obs'].send_to_user("Request rejected as site has no rotator.")

                            # If not irrelevant, queue the command
                            else:
                                g_dev["obs"].stop_all_activity = False
                                self.cmd_queue.put(cmd)


                        if cancel_check:
                            return  # Note we do not process any commands.
                    else:
                        plog("Request rejected as obs in admin or owner mode.")
                        g_dev['obs'].send_to_user("Request rejected as obs in admin or owner mode.")
            except:
                if 'Internal server error' in str(unread_commands):
                    plog ("AWS server glitch reading unread_commands")
                else:
                    plog(traceback.format_exc())
                    plog("unread commands")
                    plog (unread_commands)
                    plog ("MF trying to find whats happening with this relatively rare bug!")


        # NEED TO WAIT UNTIL CURRENT COMMAND IS FINISHED UNTIL MOVING ONTO THE NEXT ONE!
        # THAT IS WHAT CAUSES THE "CAMERA BUSY" ISSUE. We don't need to wait for the
        # rotator as the exposure routine in camera.py already waits for that.
        if (not g_dev["cam"].exposure_busy) and (not self.stop_processing_command_requests):
            while self.cmd_queue.qsize() > 0:
                if not self.stop_processing_command_requests and not g_dev["cam"].exposure_busy and not g_dev['seq'].block_guard:  # This is to stop multiple commands running over the top of each other.
                    self.stop_processing_command_requests = True
                    cmd = self.cmd_queue.get()

                    device_instance = cmd["deviceInstance"]
                    plog("obs.scan_request: ", cmd)
                    device_type = cmd["deviceType"]



                    if device_type=='enclosure':
                        plog ('An OBS has mistakenly received an enclosure command! Ignoring.')
                    else:
                        device = self.all_devices[device_type][device_instance]
                        try:
                            device.parse_command(cmd)
                        except Exception as e:
                            plog(traceback.format_exc())
                            plog("Exception in obs.scan_requests:  ", e, 'cmd:  ', cmd)

                    self.stop_processing_command_requests = False
                else:
                    time.sleep(0.2)

        return


    def update_status(self, cancel_check=False, mount_only=False, dont_wait=False):
        """Collects status from all devices and sends an update to AWS.

        Each device class is responsible for implementing the method
        `get_status`, which returns a dictionary.
        """

        if self.currently_updating_status==True:
            return

        self.currently_updating_status=True
        #g_dev["mnt"].get_mount_coordinates()
        # try:
        #     g_dev['mnt'].rapid_park_indicator=g_dev['mnt'].mount.AtPark
        # except Exception as e:
        #     plog (e)
        #     plog ("Getting intermittent errors with astrophysics mount.  MTF hunting this bug.")



        # if not g_dev['mnt'].rapid_park_indicator:
        #     try:
        #         g_dev['mnt'].rapid_pier_indicator=g_dev['mnt'].mount.sideOfPier
        #     except Exception as e:
        #         plog (e)
        #         plog ("astrophysics doesn't report side of pier at park? MTF hunting this bug.")


        g_dev['foc'].update_focuser_temperature

        # Wait a bit between status updates otherwise
        # status updates bank up in the queue
        if dont_wait == True:
            self.status_interval = self.status_upload_time + 0.25
        while time.time() < self.time_last_status + self.status_interval:
            self.currently_updating_status=False
            return  # Note we are just not sending status, too soon.

        #print ("update_status")

        # Keep an eye on the stop-script and exposure halt time to reset those timers.
        if g_dev['seq'].stop_script_called and ((time.time() - g_dev['seq'].stop_script_called_time) > 35):
            g_dev["obs"].send_to_user("Stop Script Complete.")
            g_dev['seq'].stop_script_called = False
            g_dev['seq'].stop_script_called_time = time.time()

        if g_dev["obs"].exposure_halted_indicator == True:
            if g_dev["obs"].exposure_halted_indicator_timer - time.time() > 12:
                g_dev["obs"].exposure_halted_indicator = False
                g_dev["obs"].exposure_halted_indicator_timer = time.time()

        if g_dev["obs"].stop_all_activity and ((time.time() - g_dev["obs"].stop_all_activity_timer) > 35):
            g_dev["obs"].stop_all_activity = False

        # Good spot to check if we need to nudge the telescope as long as we aren't exposing.
        if not g_dev["cam"].exposure_busy and not g_dev['seq'].block_guard:
            self.check_platesolve_and_nudge()

        # Meridian 'pulse'. A lot of mounts will not do a meridian flip unless a
        # specific slew command is sent. So this tracks how long it has been since
        # a slew and sends a slew command to the exact coordinates it is already pointing on
        # at least a 5 minute basis.
        if (time.time() - g_dev['obs'].time_of_last_slew) > 300:
            # Check no other commands or exposures are happening
            if g_dev['obs'].cmd_queue.empty() and not g_dev["cam"].exposure_busy and not g_dev['cam'].currently_in_smartstack_loop and not g_dev["seq"].focussing:
                if not g_dev['mnt'].rapid_park_indicator and not g_dev['mnt'].mount.Slewing and g_dev['mnt'].mount.Tracking :
                    # Don't do it if the roof isn't open etc.
                    if (g_dev['obs'].open_and_enabled_to_observe==True ) or g_dev['obs'].scope_in_manual_mode:
                        ra = g_dev['mnt'].mount.RightAscension
                        dec = g_dev['mnt'].mount.Declination
                        temppointing=SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
                        temppointingaltaz=temppointing.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
                        alt = temppointingaltaz.alt.degree
                        if alt > 25:
                            wait_for_slew()
                            meridianra=g_dev['mnt'].mount.RightAscension
                            meridiandec=g_dev['mnt'].mount.Declination
                            g_dev['obs'].time_of_last_slew=time.time()
                            #g_dev['mnt'].mount.SlewToCoordinatesAsync(meridianra, meridiandec)
                            g_dev['mnt'].slew_async_directly(ra=meridianra, dec=meridiandec)
                            wait_for_slew()
                            self.time_of_last_slew=time.time()

        # Send up the obs settings status - basically the current safety settings
        if (
            (datetime.datetime.now() - self.observing_status_timer)
        ) > datetime.timedelta(minutes=self.observing_check_period):
            g_dev['obs'].ocn_status = g_dev['obs'].get_weather_status_from_aws()
            self.observing_status_timer = datetime.datetime.now()


        if (
            (datetime.datetime.now() - self.enclosure_status_timer)
        ) > datetime.timedelta(minutes=self.enclosure_check_period):

            g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()
            self.enclosure_status_timer = datetime.datetime.now()

        if (time.time() - self.obs_settings_upload_timer) > self.obs_settings_upload_period:
            self.obs_settings_upload_timer = time.time()
            status = {}
            status['obs_settings']={}
            status['obs_settings']['scope_in_manual_mode']=self.scope_in_manual_mode
            status['obs_settings']['sun_safety_mode']=self.sun_checks_on
            status['obs_settings']['moon_safety_mode']=self.moon_checks_on
            status['obs_settings']['altitude_safety_mode']=self.altitude_checks_on
            status['obs_settings']['lowest_altitude']=-5
            status['obs_settings']['daytime_exposure_safety_mode']=self.daytime_exposure_time_safety_on
            status['obs_settings']['daytime_exposure_time']=0.01

            status['obs_settings']['auto_center_on']= not self.auto_centering_off
            status['obs_settings']['admin_owner_commands_only']=self.admin_owner_commands_only
            status['obs_settings']['simulating_open_roof']=self.assume_roof_open
            status['obs_settings']['pointing_reference_on']= (not self.mount_reference_model_off)

            lane = "obs_settings"
            try:
                send_status(self.name, lane, status)
            except:
                plog('could not send obs_settings status')
                plog(traceback.format_exc())


        # Send main batch of devices status
        obsy = self.name
        if mount_only == True:
            device_list = ['mount', 'telescope']
        else:
            device_list = self.device_types
        status={}
        for dev_type in device_list:
            #  The status that we will send is grouped into lists of
            #  devices by dev_type.
            status[dev_type] = {}
            devices_of_type = self.all_devices.get(dev_type, {})
            device_names = devices_of_type.keys()

            for device_name in device_names:

                # Get the actual device object...
                device = devices_of_type[device_name]
                # Currently the telescope and mount devices are the same... this will change.
                if 'telescope' in device_name:
                    status['telescope'] = status['mount']
                else:
                    result = device.get_status()

                if result is not None:
                    status[dev_type][device_name] = result
        status["timestamp"] = round((time.time()) / 2.0, 3)
        status["send_heartbeat"] = False

        if status is not None:
            lane = "device"
            if self.send_status_queue.qsize() < 7:
                self.send_status_queue.put((obsy, lane, status), block=False)


        # If the roof is open, then it is open and enabled to observe
        if not g_dev['obs'].enc_status == None:
            if 'Open' in g_dev['obs'].enc_status['shutter_status']:
                if (not 'NoObs' in g_dev['obs'].enc_status['shutter_status'] and not self.net_connection_dead) or self.assume_roof_open:
                    self.open_and_enabled_to_observe = True
                else:
                    self.open_and_enabled_to_observe = False

        # Check that the mount hasn't slewed too close to the sun
        # If the roof is open and enabled to observe
        # Don't do sun checks at nightime!
        if not ((g_dev['events']['Observing Begins']  <= ephem.now() < g_dev['events']['Observing Ends'])):
            try:
                if not g_dev['mnt'].mount.Slewing and self.open_and_enabled_to_observe and self.sun_checks_on:

                    sun_coords = get_sun(Time.now())
                    temppointing = SkyCoord((g_dev['mnt'].current_icrs_ra)*u.hour,
                                            (g_dev['mnt'].current_icrs_dec)*u.degree, frame='icrs')
                    sun_dist = sun_coords.separation(temppointing)
                    if sun_dist.degree < self.config['closest_distance_to_the_sun'] and not g_dev['mnt'].rapid_park_indicator:
                        g_dev['obs'].send_to_user("Found telescope pointing too close to the sun: " +
                                                  str(sun_dist.degree) + " degrees.")
                        plog("Found telescope pointing too close to the sun: " + str(sun_dist.degree) + " degrees.")
                        g_dev['obs'].send_to_user("Parking scope and cancelling all activity")
                        plog("Parking scope and cancelling all activity")

                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()
                        if not g_dev['mnt'].rapid_park_indicator:
                            g_dev['mnt'].park_command()

                        self.currently_updating_status=False
                        return
            except Exception as e:
                plog ("Sun check didn't work for some reason")
                if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:

                    plog("The SkyX had an error.")
                    plog("Usually this is because of a broken connection.")
                    plog("Killing then waiting 60 seconds then reconnecting")
                    g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)

        self.time_last_status = time.time()
        self.status_count += 1

        self.currently_updating_status=False


    def update(self):
        """
        This compact little function is the heart of the code in the sense this is repeatedly
        called. It first SENDS status for all devices to AWS, then it checks for any new
        commands from AWS. If certain timers have reached their point, it will undertake
        a variety of safety checks as well.
        """

        if self.currently_updating_FULL:
            return

        self.currently_updating_FULL=True

        #print ("full update")

        if not self.currently_updating_status:
            self.request_update_status()

        if time.time() - self.get_new_job_timer > 3:
            self.get_new_job_timer = time.time()
            try:
                self.scan_requests("mount1")
            except:
                pass


        self.full_update_lock=True
        while self.currently_updating_status:
            print ('w')
            time.sleep(0.5)

        if self.status_count > 1:  # Give time for status to form
            g_dev["seq"].manager()  # Go see if there is something new to do.





        # An important check to make sure equatorial telescopes are pointed appropriately
        # above the horizon. SRO and ECO have shown that it is possible to get entirely
        # confuzzled and take images of the dirt. This should save them from this fate.
        # Also it should generically save any telescope from pointing weirdly down
        # or just tracking forever after being left tracking for far too long.
        #
        # Also an area to put things to irregularly check if things are still connected, e.g. cooler
        #
        # We don't want to run these checks EVERY status update, just every 5 minutes
        if time.time() - self.time_since_safety_checks > self.safety_check_period:
            self.time_since_safety_checks = time.time()

            # Adjust focus on a not-too-frequent period for temperature
            if not g_dev["cam"].exposure_busy and not g_dev["seq"].focussing and self.open_and_enabled_to_observe:
                g_dev['foc'].adjust_focus()

            # Check nightly_reset is all good
            if ((g_dev['events']['Cool Down, Open']  <= ephem.now() < g_dev['events']['Observing Ends'])):
                g_dev['seq'].nightly_reset_complete = False

            # Don't do sun checks at nightime!
            if not ((g_dev['events']['Observing Begins']  <= ephem.now() < g_dev['events']['Observing Ends'])):
                if not g_dev['mnt'].rapid_park_indicator and self.open_and_enabled_to_observe and self.sun_checks_on: # Only do the sun check if scope isn't parked
                    # Check that the mount hasn't slewed too close to the sun
                    sun_coords = get_sun(Time.now())

                    temppointing = SkyCoord((g_dev['mnt'].current_icrs_ra)*u.hour,
                                            (g_dev['mnt'].current_icrs_dec)*u.degree, frame='icrs')

                    sun_dist = sun_coords.separation(temppointing)
                    if sun_dist.degree < self.config['closest_distance_to_the_sun'] and not g_dev['mnt'].rapid_park_indicator:
                        g_dev['obs'].send_to_user("Found telescope pointing too close to the sun: " +
                                                  str(sun_dist.degree) + " degrees.")
                        plog("Found telescope pointing too close to the sun: " + str(sun_dist.degree) + " degrees.")
                        g_dev['obs'].send_to_user("Parking scope and cancelling all activity")
                        plog("Parking scope and cancelling all activity")
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()
                        if not g_dev['mnt'].rapid_park_indicator:
                            g_dev['mnt'].park_command()

                        self.currently_updating_FULL=False
                        return

            # Roof Checks only if not in debug mode
            # And only check if the scope thinks everything is open and hunky dory
            if self.open_and_enabled_to_observe and not self.scope_in_manual_mode and not self.assume_roof_open:
                if g_dev['obs'].enc_status is not None :
                    if  'Software Fault' in g_dev['obs'].enc_status['shutter_status']:
                        plog("Software Fault Detected.") #  " Will alert the authorities!")
                        plog("Parking Scope in the meantime.")
                        self.open_and_enabled_to_observe = False
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()
                        if not g_dev['mnt'].rapid_park_indicator:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()

                    if 'Closing' in g_dev['obs'].enc_status['shutter_status'] or 'Opening' in g_dev['obs'].enc_status['shutter_status']:
                            plog("Detected Roof Movement.")
                            self.open_and_enabled_to_observe = False
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()
                            if not g_dev['mnt'].rapid_park_indicator:
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()

                    if 'Error' in g_dev['obs'].enc_status['shutter_status']:
                        plog("Detected an Error in the Roof Status. Packing up for safety.")
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()    #NB Kills bias dark
                        self.open_and_enabled_to_observe = False
                        if not g_dev['mnt'].rapid_park_indicator:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()

                else:
                    plog("Enclosure roof status probably not reporting correctly. WEMA down?")

                roof_should_be_shut = False

                if not self.scope_in_manual_mode and not g_dev['seq'].flats_being_collected and not self.assume_roof_open:
                    if (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                        roof_should_be_shut = True
                        self.open_and_enabled_to_observe = False
                    if not self.config['auto_morn_sky_flat']:
                        if (g_dev['events']['Observing Ends'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                            roof_should_be_shut = True
                            self.open_and_enabled_to_observe = False
                        if (g_dev['events']['Naut Dawn'] < ephem.now() < g_dev['events']['Morn Bias Dark']):
                            roof_should_be_shut = True
                            self.open_and_enabled_to_observe = False
                    if not (g_dev['events']['Cool Down, Open'] < ephem.now() < g_dev['events']['Close and Park']):
                        roof_should_be_shut = True
                        self.open_and_enabled_to_observe = False

                if 'Open' in g_dev['obs'].enc_status['shutter_status']:
                    if roof_should_be_shut == True:
                        plog("Safety check notices that the roof was open outside of the normal observing period")


                if not self.scope_in_manual_mode and not g_dev['seq'].flats_being_collected and not self.assume_roof_open:
                    # If the roof should be shut, then the telescope should be parked.
                    if roof_should_be_shut == True:
                        if not g_dev['mnt'].rapid_park_indicator:
                            plog('Parking telescope as it is during the period that the roof is meant to be shut.')
                            self.open_and_enabled_to_observe = False
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()  #NB Kills bias dark
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()

                    if g_dev['obs'].enc_status is not None:
                    # If the roof IS shut, then the telescope should be shutdown and parked.
                        if 'Closed' in g_dev['obs'].enc_status['shutter_status']:

                            if not g_dev['mnt'].rapid_park_indicator:
                                plog("Telescope found not parked when the observatory roof is shut. Parking scope.")
                                self.open_and_enabled_to_observe = False
                                if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                    self.cancel_all_activity()  #NB Kills bias dark
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()


                        # But after all that if everything is ok, then all is ok, it is safe to observe
                        if 'Open' in g_dev['obs'].enc_status['shutter_status'] and roof_should_be_shut == False:
                            if not 'NoObs' in g_dev['obs'].enc_status['shutter_status'] and not self.net_connection_dead:
                                self.open_and_enabled_to_observe = True
                            elif self.assume_roof_open:
                                self.open_and_enabled_to_observe = True
                            else:
                                self.open_and_enabled_to_observe = False


                    else:
                        plog("g_dev['obs'].enc_status not reporting correctly")

            # Check the mount is still connected
            #g_dev['mnt'].check_connect()
            # if got here, mount is connected. NB Plumb in PW startup code

            # Check that the mount hasn't tracked too low or an odd slew hasn't sent it pointing to the ground.
            if self.altitude_checks_on:
                try:

                    mount_altitude = float(g_dev['mnt'].previous_status['altitude'])

                    lowest_acceptable_altitude = self.config['lowest_requestable_altitude']
                    if mount_altitude < lowest_acceptable_altitude:
                        plog("Altitude too low! " + str(mount_altitude) + ". Parking scope for safety!")
                        if not g_dev['mnt'].rapid_park_indicator:
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                except Exception as e:
                    plog(traceback.format_exc())
                    plog(e)

                    if g_dev['mnt'].theskyx:

                        plog("The SkyX had an error.")
                        plog("Usually this is because of a broken connection.")
                        plog("Killing then waiting 60 seconds then reconnecting")
                        g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                    else:
                       # breakpoint()
                       pass

            # If no activity for an hour, park the scope
            if not self.scope_in_manual_mode:
                if time.time() - self.time_of_last_slew > self.config['mount']['mount1']['time_inactive_until_park'] and time.time() - self.time_of_last_exposure > self.config['mount']['mount1']['time_inactive_until_park']:
                    if not g_dev['mnt'].rapid_park_indicator:
                        plog("Parking scope due to inactivity")
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                    self.time_of_last_slew = time.time()
                    self.time_of_last_exposure = time.time()

            # Check that cooler is alive
            if g_dev['cam']._cooler_on():
                current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                current_camera_temperature = float(current_camera_temperature)

                if abs(float(current_camera_temperature) - float(g_dev['cam'].setpoint)) > 1.5:
                    self.camera_sufficiently_cooled_for_calibrations = False
                    self.last_time_camera_was_warm=time.time()
                elif (time.time()-self.last_time_camera_was_warm) < 1200:
                    self.camera_sufficiently_cooled_for_calibrations = False
                else:
                    self.camera_sufficiently_cooled_for_calibrations = True
            else:
                try:
                    probe = g_dev['cam']._cooler_on()
                    if not probe:
                        g_dev['cam']._set_cooler_on()
                        plog("Found cooler off.")
                        try:
                            g_dev['cam']._connect(False)
                            g_dev['cam']._connect(True)
                            g_dev['cam']._set_cooler_on()
                        except:
                            plog("Camera cooler reconnect failed.")
                except Exception as e:
                    plog("\n\nCamera was not connected @ expose entry:  ", e, "\n\n")
                    try:
                        g_dev['cam']._connect(False)
                        g_dev['cam']._connect(True)
                        g_dev['cam']._set_cooler_on()
                    except:
                        plog("Camera cooler reconnect failed 2nd time.")

            # Things that only rarely have to be reported go in this block.
            if (time.time() - self.last_time_report_to_console) > 600:
                plog (ephem.now())
                if self.camera_sufficiently_cooled_for_calibrations == False:
                    if (time.time() - self.last_time_camera_was_warm) < 1200:
                        plog ("Camera was recently too warm for calibrations")
                        plog ("Waiting for a 20 minute period where camera has been cooled")
                        plog ("Before continuing calibrations to ensure cooler is evenly cooled")
                        plog ( str(int(1200 - (time.time() - self.last_time_camera_was_warm))) + " seconds to go.")
                        plog ("Camera current temperature ("+ str(current_camera_temperature)+").")
                        plog ("Difference from setpoint: " + str( (current_camera_temperature - g_dev['cam'].setpoint)))
                    else:
                        plog ("Camera currently too warm ("+ str(current_camera_temperature)+") for calibrations.")
                        plog ("Difference from setpoint: " + str( (current_camera_temperature - g_dev['cam'].setpoint)))
                self.last_time_report_to_console = time.time()



            if (time.time() - g_dev['seq'].time_roof_last_opened < 10 ):
                plog ("Roof opened only recently: " + str(round((time.time() - g_dev['seq'].time_roof_last_opened)/60,1)) +" minutes ago.")
                plog ("Some functions, particularly flats, won't start until 10 seconds after the roof has opened.")



            # After the observatory and camera have had time to settle....
            if (time.time() - self.camera_time_initialised) > 1200:
                # Check that the camera is not overheating.
                # If it isn't overheating check that it is at the correct temperature
                if self.camera_overheat_safety_warm_on:

                    plog(time.time() - self.camera_overheat_safety_timer)
                    if (time.time() - self.camera_overheat_safety_timer) > 1201:
                        print("Camera OverHeating Safety Warm Cycle Complete. Resetting to normal temperature.")
                        g_dev['cam']._set_setpoint(g_dev['cam'].setpoint)
                        # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                        g_dev['cam']._set_cooler_on()
                        self.camera_overheat_safety_warm_on = False
                    else:
                        print("Camera Overheating Safety Warm Cycle on.")

                elif g_dev['cam'].protect_camera_from_overheating and (float(current_camera_temperature) - g_dev['cam'].current_setpoint) > (2 * g_dev['cam'].day_warm_degrees):
                    plog("Found cooler on, but warm.")
                    plog("Keeping it slightly warm ( " + str(2 * g_dev['cam'].day_warm_degrees) +
                          " degrees warmer ) for about 20 minutes just in case the camera overheated.")
                    plog("Then will reset to normal.")
                    self.camera_overheat_safety_warm_on = True
                    self.camera_overheat_safety_timer = time.time()
                    self.last_time_camera_was_warm=time.time()
                    #print (float(g_dev['cam'].setpoint +20.0))
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + (2 * g_dev['cam'].day_warm_degrees)))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()

            if not self.camera_overheat_safety_warm_on and (time.time() - self.warm_report_timer > 300):
                # Daytime... a bit tricky! Two periods... just after biases but before nightly reset OR ... just before eve bias dark
                # As nightly reset resets the calendar
                self.warm_report_timer = time.time()
                self.too_hot_in_observatory = False
                focstatus=g_dev['foc'].get_status()
                self.temperature_in_observatory_from_focuser=focstatus["focus_temperature"]

                if self.temperature_in_observatory_from_focuser > self.too_hot_temperature:  #This should be a per obsy config item
                    self.too_hot_in_observatory=True

                if g_dev['cam'].day_warm  and (ephem.now() < g_dev['events']['Eve Bias Dark'] - ephem.hour) or \
                        (g_dev['events']['End Morn Bias Dark'] + ephem.hour < ephem.now() < g_dev['events']['Nightly Reset']):
                    plog("In Daytime: Camera set at warmer temperature")
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + g_dev['cam'].day_warm_degrees))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    self.last_time_camera_was_warm=time.time()


                elif g_dev['cam'].day_warm  and (self.too_hot_in_observatory) and (ephem.now() < g_dev['events']['Clock & Auto Focus'] - ephem.hour):
                    plog("Currently too hot: "+str(self.temperature_in_observatory_from_focuser)+"C for excess cooling. Keeping it at day_warm until a cool hour long ramping towards clock & autofocus")
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + g_dev['cam'].day_warm_degrees))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    self.last_time_camera_was_warm=time.time()

                # Ramp heat temperature
                # Beginning after "End Morn Bias Dark" and taking an hour to ramp
                elif g_dev['cam'].day_warm and (g_dev['events']['End Morn Bias Dark'] < ephem.now() < g_dev['events']['End Morn Bias Dark'] + ephem.hour):
                    plog("In Camera Warming Ramping cycle of the day")
                    frac_through_warming = 1-((g_dev['events']['End Morn Bias Dark'] +
                                               ephem.hour) - ephem.now()) / ephem.hour
                    plog("Fraction through warming cycle: " + str(frac_through_warming))
                    g_dev['cam']._set_setpoint(
                        float(g_dev['cam'].setpoint + (frac_through_warming) * g_dev['cam'].day_warm_degrees))
                    g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    self.last_time_camera_was_warm=time.time()

                # Ramp cool temperature
                # Defined as beginning an hour before "Eve Bias Dark" to ramp to the setpoint.
                # If the observatory is not too hot, set up cooling for biases
                elif g_dev['cam'].day_warm and (not self.too_hot_in_observatory) and (g_dev['events']['Eve Bias Dark'] - ephem.hour < ephem.now() < g_dev['events']['Eve Bias Dark']):
                    plog("In Camera Cooling Ramping cycle of the day")
                    frac_through_warming = 1 - (((g_dev['events']['Eve Bias Dark']) - ephem.now()) / ephem.hour)
                    plog("Fraction through cooling cycle: " + str(frac_through_warming))
                    if frac_through_warming > 0.66:
                        g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                        g_dev['cam']._set_cooler_on()
                        self.last_time_camera_was_warm=time.time()
                    else:
                        g_dev['cam']._set_setpoint(
                            float(g_dev['cam'].setpoint + (1 - (frac_through_warming * 1.5)) * g_dev['cam'].day_warm_degrees))
                        g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))

                # Don't bother trying to cool for biases if too hot in observatory.
                # Don't even bother for flats, it just won't get there.
                # Just aim for clock & auto focus
                elif g_dev['cam'].day_warm and (self.too_hot_in_observatory) and (g_dev['events']['Clock & Auto Focus'] - ephem.hour < ephem.now() < g_dev['events']['Clock & Auto Focus']):
                    plog("In Camera Cooling Ramping cycle aiming for Clock & Auto Focus")
                    frac_through_warming = 1 - (((g_dev['events']['Clock & Auto Focus']) - ephem.now()) / ephem.hour)
                    print("Fraction through cooling cycle: " + str(frac_through_warming))
                    if frac_through_warming > 0.8:
                        g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                        g_dev['cam']._set_cooler_on()
                    else:
                        g_dev['cam']._set_setpoint(
                            float(g_dev['cam'].setpoint + (1 - frac_through_warming) * g_dev['cam'].day_warm_degrees))
                        g_dev['cam']._set_cooler_on()
                        self.last_time_camera_was_warm=time.time()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))

                # Nighttime temperature
                elif g_dev['cam'].day_warm and not (self.too_hot_in_observatory) and (g_dev['events']['Eve Bias Dark'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                    g_dev['cam']._set_cooler_on()

                elif g_dev['cam'].day_warm and (self.too_hot_in_observatory) and self.open_and_enabled_to_observe and (g_dev['events']['Clock & Auto Focus'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                    g_dev['cam']._set_cooler_on()

                elif g_dev['cam'].day_warm and (self.too_hot_in_observatory) and not self.open_and_enabled_to_observe and (g_dev['events']['Clock & Auto Focus'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    plog ("Focusser reporting too high a temperature in the observatory")
                    plog ("The roof is also shut, so keeping camera at the day_warm temperature")

                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + g_dev['cam'].day_warm_degrees))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()
                    self.last_time_camera_was_warm=time.time()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))

                elif (g_dev['events']['Eve Bias Dark'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                    g_dev['cam']._set_cooler_on()

            # Check that the site is still connected to the net.
            if test_connect():
                self.time_of_last_live_net_connection = time.time()
                self.net_connection_dead = False
            if (time.time() - self.time_of_last_live_net_connection) > 600:
                plog("Warning, last live net connection was over ten minutes ago")
            if (time.time() - self.time_of_last_live_net_connection) > 1200:
                plog("Last connection was over twenty minutes ago. Running a further test or two")
                if test_connect(host='http://dev.photonranch.org'):
                    plog("Connected to photonranch.org, so it must be that Google is down. Connection is live.")
                    self.time_of_last_live_net_connection = time.time()
                elif test_connect(host='http://aws.amazon.com'):
                    plog("Connected to aws.amazon.com. Can't connect to Google or photonranch.org though.")
                    self.time_of_last_live_net_connection = time.time()
                else:
                    plog("Looks like the net is down, closing up and parking the observatory")
                    self.open_and_enabled_to_observe = False
                    self.net_connection_dead = True
                    if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                        self.cancel_all_activity()
                    if not g_dev['mnt'].rapid_park_indicator:
                        plog("Parking scope due to inactivity")
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                        self.time_of_last_slew = time.time()

        self.full_update_lock=False
        self.currently_updating_FULL=False
        # END of safety checks.

    def run(self):
        try:
            # Keep the main thread alive, otherwise signals are ignored
            while True:
                if self.currently_updating_FULL==False:
                    if (time.time() - self.last_update_complete) > 1.0:
                        self.update()
                        self.last_update_complete=time.time()
                else:
                    time.sleep(0.05)
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            plog("Finishing loops and exiting...")
            self.stopped = True
            return


    def ptrarchive_uploader(self, pri_image):

        upload_timer=time.time()
        if pri_image is None:
            plog("Got an empty entry in ptrarchive_queue.")
            #one_at_a_time = 0
            #self.ptrarchive_queue.task_done()

        else:
            # Here we parse the file, set up and send to AWS
            filename = pri_image[1][1]
            filepath = pri_image[1][0] + filename  # Full path to file on disk

            # Only ingest new large fits.fz files to the PTR archive.
            try:
                broken = 0
                with open(filepath, "rb") as fileobj:

                    if filepath.split('.')[-1] == 'token':
                        files = {"file": (filepath, fileobj)}
                        aws_resp = authenticated_request("POST", "/upload/", {"object_name": filename})
                        while True:
                            try:
                                reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=45)
                                try:
                                    os.remove(filepath)
                                except:
                                    self.laterdelete_queue.put(filepath, block=False)
                                break
                            except:
                                plog("Non-fatal connection glitch for a file posted.")
                                plog(files)

                                time.sleep(5)


                    elif self.env_exists == True and (not frame_exists(fileobj)):
                        try:
                            # Get header explicitly out to send up
                            # This seems to be necessary
                            tempheader=fits.open(filepath)
                            tempheader=tempheader[1].header
                            headerdict = {}
                            for entry in tempheader.keys():
                                headerdict[entry] = tempheader[entry]
                            #plog("****************************************************** \
                            #      This is a one-time non-fatal error that regularly reccurs having to do with injesting \
                            #      into the archive. Line 1541 in obs.py", fileobj, file_metadata=headerdict)
                            upload_file_and_ingest_to_archive(fileobj, file_metadata=headerdict)
                            #plog("******************************************************")
                            # Only remove file if successfully uploaded
                            if ('calibmasters' not in filepath) or ('ARCHIVE_' in filepath):
                                try:
                                    os.remove(filepath)
                                except:
                                    self.laterdelete_queue.put(filepath, block=False)


                        except ocs_ingester.exceptions.DoNotRetryError:
                            plog ("Couldn't upload to PTR archive: " + str(filepath))
                            broken=1
                        except Exception as e:
                            if 'list index out of range' in str(e):
                                # This error is thrown when there is a corrupt file
                                broken=1

                            elif 'timed out.' in str(e) or 'TimeoutError' in str(e):
                                # Not broken, just bung it back in the queue for later
                                plog("Timeout glitch, trying again later: ", e)
                                time.sleep(10)
                                self.ptrarchive_queue.put(pri_image, block=False)
                                # And give it a little sleep
                                return str(filepath.split('/')[-1]) + " timed out."

                            elif 'credential_provider' in str(e) or 'endpoint_resolver' in str(e):
                                #plog((traceback.format_exc()))
                                plog ("Credential provider error for the ptrarchive, bunging a file back in the queue.")
                                time.sleep(10)
                                self.ptrarchive_queue.put(pri_image, block=False)

                                return str(filepath.split('/')[-1]) + " got an odd error, but retrying."

                            else:
                                plog("couldn't send to PTR archive for some reason: ", e)

                                #plog((traceback.format_exc()))

                                # And give it a little sleep
                                time.sleep(10)

                                broken =1
                                # return str(filepath.split('/')[-1]) + " failed."


                if broken == 1:
                    try:
                        shutil.move(filepath, self.broken_path + filename)
                    except:
                        plog ("Couldn't move " + str(filepath) + " to broken folder.")

                        self.laterdelete_queue.put(filepath, block=False)
                    return str(filepath.split('/')[-1]) + " broken."
            except Exception as e:
                plog ("something strange in the ptrarchive uploader", e)
                return 'something strange in the ptrarchive uploader'


            upload_timer=time.time() - upload_timer
            hours_to_go = (self.ptrarchive_queue.qsize() * upload_timer/60/60) / int(self.config['number_of_simultaneous_ptrarchive_streams'])
            return ( str(filepath.split('/')[-1]) + " sent to archive. Queue Size: " + str(self.ptrarchive_queue.qsize())+ ". " + str(round(hours_to_go,1)) +" hours to go.")

    def pipearchive_copier(self, fileinfo):

        upload_timer=time.time()

        (filename,dayobs,instrume) = fileinfo


        # Check folder exists

        pipefolder = self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs)
        if not os.path.exists(self.config['pipe_archive_folder_path'] + str(instrume)):
            os.makedirs(self.config['pipe_archive_folder_path'] + str(instrume))

        if not os.path.exists(self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs)):
            os.makedirs(self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs))


        if filename is None:
            plog("Got an empty entry in pipearchive_queue.")
            #one_at_a_time = 0
            #self.ptrarchive_queue.task_done()

        else:
            # Here we parse the file, set up and send to AWS
            #filename = pri_image[1][1]
            #filepath = pri_image[1][0] + filename  # Full path to file on disk

            # Only ingest new large fits.fz files to the PTR archive.
            try:
                broken = 0
                try:
                    shutil.copy(filename, pipefolder +'/'+ filename.split('/')[-1])
                except:
                    plog ("Couldn't copy " + str(filename) + ". Broken.")
                    broken =1

                try:
                    os.remove(filename)
                except:
                    self.laterdelete_queue.put(filename, block=False)


                if broken == 1:
                    try:
                        shutil.move(filename, self.broken_path + filename.split('/')[-1])
                    except:
                        plog ("Couldn't move " + str(filename) + " to broken folder.")

                        self.laterdelete_queue.put(filename, block=False)
                    return str(filename) + " broken."
            except Exception as e:
                plog(traceback.format_exc())
                plog ("something strange in the pipearchive copier", e)
                return 'something strange in the pipearchive copier'


            upload_timer=time.time() - upload_timer
            hours_to_go = (self.pipearchive_queue.qsize() * upload_timer/60/60) / int(self.config['number_of_simultaneous_pipearchive_streams'])
            return ( str(filename.split('/')[-1]) + " sent to local pipe archive. Queue Size: " + str(self.pipearchive_queue.qsize())+ ". " + str(round(hours_to_go,1)) +" hours to go.")

    def altarchive_copier(self, fileinfo):

        upload_timer=time.time()

        (fromfile,tofile) = fileinfo


        # Check folder exists

        # pipefolder = self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs)
        # if not os.path.exists(self.config['pipe_archive_folder_path'] + str(instrume)):
        #     os.makedirs(self.config['pipe_archive_folder_path'] + str(instrume))

        # if not os.path.exists(self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs)):
        #     os.makedirs(self.config['pipe_archive_folder_path'] + str(instrume) +'/'+ str(dayobs))


        # if filename is None:
        #     plog("Got an empty entry in pipearchive_queue.")
        #     #one_at_a_time = 0
        #     #self.ptrarchive_queue.task_done()

        # else:
        # Here we parse the file, set up and send to AWS
        #filename = pri_image[1][1]
        #filepath = pri_image[1][0] + filename  # Full path to file on disk

        # Only ingest new large fits.fz files to the PTR archive.
        try:
            broken = 0
            try:
                shutil.copy(fromfile,tofile)
            except:
                plog ("Couldn't copy " + str(fromfile) + ". Broken.")
                broken =1

            try:
                os.remove(fromfile)
            except:
                self.laterdelete_queue.put(fromfile, block=False)


            if broken == 1:
                try:
                    shutil.move(fromfile, self.broken_path + fromfile.split('/')[-1])
                except:
                    plog ("Couldn't move " + str(fromfile) + " to broken folder.")

                    self.laterdelete_queue.put(fromfile, block=False)
                return str(fromfile) + " broken."
        except Exception as e:
            plog(traceback.format_exc())
            plog ("something strange in the pipearchive copier", e)
            return 'something strange in the pipearchive copier'


        upload_timer=time.time() - upload_timer
        hours_to_go = (self.pipearchive_queue.qsize() * upload_timer/60/60) / int(self.config['number_of_simultaneous_altarchive_streams'])
        return ( str(fromfile.split('/')[-1]) + " sent to altpath archive. Queue Size: " + str(self.altarchive_queue.qsize())+ ". " + str(round(hours_to_go,1)) +" hours to go.")



    # Note this is a thread!
    def copy_to_altarchive(self):
        """Sends queued files to AWS.

        Large fpacked fits are uploaded using the ocs-ingester, which
        adds the image to the PTR archive database.

        This is intended to transfer slower files not needed for UI responsiveness

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0

        number_of_simultaneous_uploads= self.config['number_of_simultaneous_altarchive_streams']

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.altarchive_queue.empty()) and one_at_a_time == 0:


                one_at_a_time = 1

                items=[]
                for q in range(min(number_of_simultaneous_uploads,self.altarchive_queue.qsize()) ):
                    items.append(self.altarchive_queue.get(block=False))

                with ThreadPool(processes=number_of_simultaneous_uploads) as pool:
                    for result in pool.map(self.altarchive_copier, items):
                        self.altarchive_queue.task_done()
                        #plog (result)

                one_at_a_time = 0


            else:
                time.sleep(0.2)


    # Note this is a thread!
    def copy_to_pipearchive(self):
        """Sends queued files to AWS.

        Large fpacked fits are uploaded using the ocs-ingester, which
        adds the image to the PTR archive database.

        This is intended to transfer slower files not needed for UI responsiveness

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0

        number_of_simultaneous_uploads= self.config['number_of_simultaneous_pipearchive_streams']

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.pipearchive_queue.empty()) and one_at_a_time == 0:


                one_at_a_time = 1

                items=[]
                for q in range(min(number_of_simultaneous_uploads,self.pipearchive_queue.qsize()) ):
                    items.append(self.pipearchive_queue.get(block=False))

                with ThreadPool(processes=number_of_simultaneous_uploads) as pool:
                    for result in pool.map(self.pipearchive_copier, items):
                        self.pipearchive_queue.task_done()
                        plog (result)

                one_at_a_time = 0


            else:
                time.sleep(0.2)




    # Note this is a thread!
    def update_status_thread(self):


        one_at_a_time = 0

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if not self.full_update_lock and (not self.update_status_queue.empty()) and one_at_a_time == 0:


                one_at_a_time = 1
                request = self.update_status_queue.get(block=False)
                if request == 'mountonly':
                    print ("mount only")
                    self.update_status(mount_only=True)
                else:
                    self.update_status()
                self.update_status_queue.task_done()
                one_at_a_time = 0


            else:
                time.sleep(0.05)

    # Note this is a thread!
    def full_update_thread(self):


        one_at_a_time = 0

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.FULL_update_thread_queue.empty()) and one_at_a_time == 0:


                one_at_a_time = 1
                self.FULL_update_thread_queue.get(block=False)
                self.update()
                self.FULL_update_thread_queue.task_done()
                one_at_a_time = 0


            else:
                time.sleep(0.05)


    # Note this is a thread!
    def send_to_ptrarchive(self):
        """Sends queued files to AWS.

        Large fpacked fits are uploaded using the ocs-ingester, which
        adds the image to the PTR archive database.

        This is intended to transfer slower files not needed for UI responsiveness

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0

        number_of_simultaneous_uploads= self.config['number_of_simultaneous_ptrarchive_streams']

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.ptrarchive_queue.empty()) and one_at_a_time == 0:


                one_at_a_time = 1

                items=[]
                for q in range(min(number_of_simultaneous_uploads,self.ptrarchive_queue.qsize()) ):
                    items.append(self.ptrarchive_queue.get(block=False))

                with ThreadPool(processes=number_of_simultaneous_uploads) as pool:
                    for result in pool.map(self.ptrarchive_uploader, items):
                        self.ptrarchive_queue.task_done()
                        plog (result)

                one_at_a_time = 0


            else:
                time.sleep(0.2)


    def send_status_process(self):
        """

        This sends statuses through one at a time.

        """

        one_at_a_time = 0
        while True:
            if (not self.send_status_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pre_upload = time.time()
                received_status = self.send_status_queue.get(block=False)
                send_status(received_status[0], received_status[1], received_status[2])
                self.send_status_queue.task_done()
                upload_time = time.time() - pre_upload
                self.status_interval = 2 * upload_time
                if self.status_interval < 10:
                    self.status_interval = 10
                self.status_upload_time = upload_time
                one_at_a_time = 0
            else:
                time.sleep(0.1)

    def laterdelete_process(self):
        """This is a thread where things that fail to get
        deleted from the filesystem go to get deleted later on.
        Usually due to slow or network I/O
        """

        while True:
            if (not self.laterdelete_queue.empty()):
                (deletefilename) = self.laterdelete_queue.get(block=False)
                self.laterdelete_queue.task_done()
                try:
                    os.remove(deletefilename)
                except:
                    self.laterdelete_queue.put(deletefilename, block=False)

            else:
                time.sleep(0.1)

    def sendtouser_process(self):
        """This is a thread where things that fail to get
        deleted from the filesystem go to get deleted later on.
        Usually due to slow or network I/O
        """

        while True:
            if (not self.sendtouser_queue.empty()):

                (p_log, p_level) = self.sendtouser_queue.get(block=False)
                url_log = "https://logs.photonranch.org/logs/newlog"
                body = json.dumps(
                    {
                        "site": self.config["obs_id"],
                        "log_message": str(p_log),
                        "log_level": str(p_level),
                        "timestamp": time.time(),
                    }
                )

                try:
                    reqs.post(url_log, body, timeout=5)
                except:
                    plog("Log did not send, usually not fatal.")

                self.sendtouser_queue.task_done()
                time.sleep(0.1)

            else:
                time.sleep(0.1)

    def mainjpeg_process(self):
        """
        This is the main subprocess where jpegs are created for the UI.
        """

        while True:
            if (not self.mainjpeg_queue.empty()):
                osc_jpeg_timer_start = time.time()
                (hdusmalldata, smartstackid, paths, pier_side) = self.mainjpeg_queue.get(block=False)
                is_osc = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]
                osc_bayer= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"]
                if is_osc:
                    osc_background_cut=self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut']
                    osc_brightness_enhance= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance']
                    osc_contrast_enhance=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance']
                    osc_colour_enhance=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance']
                    osc_saturation_enhance=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_saturation_enhance']
                    osc_sharpness_enhance=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance']
                else:
                    osc_background_cut=0
                    osc_brightness_enhance= 0
                    osc_contrast_enhance=0
                    osc_colour_enhance=0
                    osc_saturation_enhance=0
                    osc_sharpness_enhance=0
                # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                transpose_jpeg= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]
                flipx_jpeg= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']
                flipy_jpeg= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']
                rotate180_jpeg= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']
                rotate90_jpeg = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']
                rotate270_jpeg= g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']
                crop_preview=self.config["camera"][g_dev['cam'].name]["settings"]["crop_preview"]
                yb = self.config["camera"][g_dev['cam'].name]["settings"][
                     "crop_preview_ybottom"
                 ]
                yt = self.config["camera"][g_dev['cam'].name]["settings"][
                     "crop_preview_ytop"
                 ]
                xl = self.config["camera"][g_dev['cam'].name]["settings"][
                     "crop_preview_xleft"
                 ]
                xr = self.config["camera"][g_dev['cam'].name]["settings"][
                     "crop_preview_xright"
                 ]
                squash_on_x_axis=self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]

                ##  Here WER adds Zoom prototype code:
                zoom_factor = 'full'   #This still needs to be passed in as a parameter.


                jpeg_subprocess=subprocess.Popen(['python','subprocesses/mainjpeg.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)



                if True:
                    pickle.dump([hdusmalldata, smartstackid, paths, pier_side, is_osc, osc_bayer, osc_background_cut,osc_brightness_enhance, osc_contrast_enhance,\
                          osc_colour_enhance, osc_saturation_enhance, osc_sharpness_enhance, transpose_jpeg, flipx_jpeg, flipy_jpeg, rotate180_jpeg,rotate90_jpeg, \
                              rotate270_jpeg, crop_preview, yb, yt, xl, xr, squash_on_x_axis, zoom_factor], jpeg_subprocess.stdin)

                # Here is a manual debug area which makes a pickle for debug purposes. Default is False, but can be manually set to True for code debugging
                else:
                    # breakpoint()
                    pickle.dump([hdusmalldata, smartstackid, paths, pier_side, is_osc, osc_bayer, osc_background_cut,osc_brightness_enhance, osc_contrast_enhance,\
                        osc_colour_enhance, osc_saturation_enhance, osc_sharpness_enhance, transpose_jpeg, flipx_jpeg, flipy_jpeg, rotate180_jpeg,rotate90_jpeg, \
                            rotate270_jpeg, crop_preview, yb, yt, xl, xr, squash_on_x_axis, zoom_factor], open('testjpegpickle','wb'))




                del hdusmalldata # Get big file out of memory

                # Essentially wait until the subprocess is complete
                jpeg_subprocess.communicate()

                # Try saving the jpeg to disk and quickly send up to AWS to present for the user
                if smartstackid == 'no':
                    try:
                        self.enqueue_for_fastUI(
                            100, paths["im_path"], paths["jpeg_name10"]
                        )
                        self.enqueue_for_mediumUI(
                            1000, paths["im_path"], paths["jpeg_name10"].replace('EX10', 'EX20')
                        )
                        plog("JPEG constructed and sent: " +str(time.time() - osc_jpeg_timer_start)+ "s")
                    except:
                        plog(
                            "there was an issue saving the preview jpg. Pushing on though"
                        )

                self.mainjpeg_queue.task_done()

            else:
                time.sleep(0.1)

    def sep_process(self):
        """This is the sep queue that happens in a different process
        than the main camera thread. SEPs can take 5-10, up to 30 seconds sometimes
        to run, so it is an overhead we can't have hanging around.
        """

        one_at_a_time = 0
        while True:
            if (not self.sep_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1


                (hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position, nativebin) = self.sep_queue.get(block=False)

                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']) :
                    #plog ("Too bright to consider photometry!")
                    do_sep=False
                else:
                    do_sep=True



                is_osc= self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]
                interpolate_for_focus= self.config["camera"][g_dev['cam'].name]["settings"]['interpolate_for_focus']
                bin_for_focus= self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_focus']
                focus_bin_value= self.config["camera"][g_dev['cam'].name]["settings"]['focus_bin_value']
                interpolate_for_sep=self.config["camera"][g_dev['cam'].name]["settings"]['interpolate_for_sep']
                bin_for_sep= self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_sep']
                sep_bin_value= self.config["camera"][g_dev['cam'].name]["settings"]['sep_bin_value']
                focus_jpeg_size= self.config["camera"][g_dev['cam'].name]["settings"]['focus_jpeg_size']
                saturate=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                minimum_realistic_seeing=self.config['minimum_realistic_seeing']
                sep_subprocess=subprocess.Popen(['python','subprocesses/SEPprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)



                pickle.dump([hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position, g_dev['events'],ephem.now(),self.config["camera"][g_dev['cam']
                                                         .name]["settings"]['focus_image_crop_width'], self.config["camera"][g_dev['cam']
                                                          .name]["settings"]['focus_image_crop_height'], is_osc,interpolate_for_focus,bin_for_focus,focus_bin_value,interpolate_for_sep,bin_for_sep,sep_bin_value,focus_jpeg_size,saturate,minimum_realistic_seeing,nativebin,do_sep
                                                           ], sep_subprocess.stdin)

                # Here is a manual debug area which makes a pickle for debug purposes. Default is False, but can be manually set to True for code debugging
                if False:
                    pickle.dump([hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position, g_dev['events'],ephem.now(),self.config["camera"][g_dev['cam']
                                                              .name]["settings"]['focus_image_crop_width'], self.config["camera"][g_dev['cam']
                                                                                                        .name]["settings"]['focus_image_crop_height'], is_osc,interpolate_for_focus,bin_for_focus,focus_bin_value,interpolate_for_sep,bin_for_sep,sep_bin_value,focus_jpeg_size,saturate,minimum_realistic_seeing,nativebin,do_sep
                                                                                                                                                                               ], open('subprocesses/testSEPpickle','wb'))



                # Essentially wait until the subprocess is complete
                sep_subprocess.communicate()

                # LOADING UP THE SEP FILE HERE AGAIN
                if os.path.exists(im_path + text_name.replace('.txt', '.sep')):
                    try:
                        sources = Table.read(im_path + text_name.replace('.txt', '.sep'), format='csv')

                        try:
                            self.enqueue_for_mediumUI(200, im_path, text_name.replace('.txt', '.sep'))
                        except:
                            plog("Failed to send SEP up for some reason")

                        # DONUT IMAGE DETECTOR.
                        # The brightest pixel and the centre of flux must be within a few pixels of each other
                        # If not, it is highly likely to be a donut and hence, FWHM doesn't make sense to calculate
                        binfocus=1
                        if frame_type == 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_focus']:
                            binfocus=self.config["camera"][g_dev['cam'].name]["settings"]['focus_bin_value']

                        if frame_type != 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_sep']:
                            binfocus=self.config["camera"][g_dev['cam'].name]["settings"]['sep_bin_value']

                        xdonut=np.median(pow(pow(sources['x'] - sources['xpeak'],2),0.5))*pixscale*binfocus
                        ydonut=np.median(pow(pow(sources['y'] - sources['ypeak'],2),0.5))*pixscale*binfocus
                        if xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut):
                            plog ("Possible donut image detected.")
                            plog('x ' + str(xdonut))
                            plog('y ' + str(ydonut))


                        if (len(sources) < 2) or ( frame_type == 'focus' and (len(sources) < 10 or len(sources) == np.nan or str(len(sources)) =='nan' or xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut))):
                            plog ("Did not find an acceptable FWHM for this image.")
                            self.fwhmresult={}
                            self.fwhmresult["error"] = True
                            self.fwhmresult['FWHM'] = np.nan
                            self.fwhmresult["mean_focus"] = avg_foc
                            self.fwhmresult['No_of_sources'] = np.nan
                            sources['FWHM'] = [np.nan] * len(sources)
                            rfp = np.nan
                            rfr = np.nan
                            rfs = np.nan
                            sources = sources
                        else:
                            # Get halflight radii
                            fwhmcalc = sources['FWHM']
                            fwhmcalc = fwhmcalc[fwhmcalc != 0]  # Remove 0 entries

                            # sigma clipping iterator to reject large variations
                            templen = len(fwhmcalc)
                            while True:
                                fwhmcalc = fwhmcalc[fwhmcalc < np.median(fwhmcalc) + 3 * np.std(fwhmcalc)]
                                if len(fwhmcalc) == templen:
                                    break
                                else:
                                    templen = len(fwhmcalc)

                            fwhmcalc = fwhmcalc[fwhmcalc > np.median(fwhmcalc) - 3 * np.std(fwhmcalc)]
                            rfp = round(np.median(fwhmcalc), 3)
                            rfr = round(np.median(fwhmcalc) * pixscale * g_dev['cam'].native_bin, 3)
                            rfs = round(np.std(fwhmcalc) * pixscale * g_dev['cam'].native_bin, 3)
                            plog("\nImage FWHM:  " + str(rfr) + "+/-" + str(rfs) + " arcsecs, " + str(rfp)
                                 + " pixels.")
                            self.fwhmresult={}
                            self.fwhmresult["FWHM"] = rfr
                            self.fwhmresult["mean_focus"] = avg_foc
                            self.fwhmresult['No_of_sources'] = len(sources)


                        if focus_image != True:
                            # Focus tracker code. This keeps track of the focus and if it drifts
                            # Then it triggers an autofocus.
                            g_dev["foc"].focus_tracker.pop(0)
                            g_dev["foc"].focus_tracker.append(round(rfr, 3))
                            plog("Last ten FWHM: " + str(g_dev["foc"].focus_tracker) + " Median: " + str(np.nanmedian(g_dev["foc"].focus_tracker)) + " Last Solved: " + str(g_dev["foc"].last_focus_fwhm))

                            # If there hasn't been a focus yet, then it can't check it,
                            # so make this image the last solved focus.
                            if g_dev["foc"].last_focus_fwhm == None:
                                g_dev["foc"].last_focus_fwhm = rfr
                            else:
                                # Very dumb focus slip deteector
                                if (
                                    np.nanmedian(g_dev["foc"].focus_tracker)
                                    > g_dev["foc"].last_focus_fwhm
                                    + self.config["focus_trigger"]
                                ):
                                    g_dev["foc"].focus_needed = True
                                    g_dev["obs"].send_to_user(
                                        "Focus has drifted to "
                                        + str(np.nanmedian(g_dev["foc"].focus_tracker))
                                        + " from "
                                        + str(g_dev["foc"].last_focus_fwhm)
                                        + ".",
                                        p_level="INFO",
                                    )
                    except Exception as e:
                        plog ("something odd occured in the reinterpretation of the SEP file", e)
                        plog(traceback.format_exc())

                else:
                    #plog ("Did not find a source list from SEP for this image.")
                    self.fwhmresult={}
                    self.fwhmresult['FWHM'] = np.nan
                    self.fwhmresult['No_of_sources'] = np.nan


                if os.path.exists(im_path + text_name.replace('.txt', '.rad')):
                    try:
                        self.enqueue_for_mediumUI(250, im_path, text_name.replace('.txt', '.rad'))
                    except:
                        plog("Failed to send RAD up for some reason")

                if frame_type == 'focus':
                    self.enqueue_for_fastUI(100, im_path, text_name.replace('EX00.txt', 'EX10.jpg'))

                try:
                    self.enqueue_for_mediumUI(180, im_path, text_name.replace('.txt', '.his'))
                except:
                    plog("Failed to send HIS up for some reason")
                if os.path.exists(im_path + text_name.replace('.txt', '.box')):
                    try:
                        self.enqueue_for_mediumUI(180, im_path, text_name.replace('.txt', '.box'))
                    except:
                        plog("Failed to send BOX up for some reason")

                if self.config['keep_focus_images_on_disk']:
                    g_dev['obs'].to_slow_process(1000, ('focus', cal_path + cal_name, hdufocusdata, hduheader,
                                                        frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    if self.config["save_to_alt_path"] == "yes":
                        g_dev['obs'].to_slow_process(1000, ('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocusdata, hduheader,
                                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                self.enqueue_for_fastUI(10, im_path, text_name)

                del hdufocusdata

                self.sep_processing = False
                self.sep_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.1)

    def platesolve_process(self):
        """This is the platesolve queue that happens in a different process
        than the main thread. Platesolves can take 5-10, up to 30 seconds sometimes
        to run, so it is an overhead we can't have hanging around. This thread attempts
        a platesolve and uses the solution and requests a telescope nudge/center
        if the telescope has not slewed in the intervening time between beginning
        the platesolving process and completing it.

        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if (not self.platesolve_queue.empty()) and one_at_a_time == 0:

                one_at_a_time = 1
                self.platesolve_is_processing = True

                (hdufocusdata, hduheader, cal_path, cal_name, frame_type, time_platesolve_requested,
                 pixscale, pointing_ra, pointing_dec) = self.platesolve_queue.get(block=False)

                # Do not bother platesolving unless it is dark enough!!
                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                    plog("Too bright to consider platesolving!")
                else:

                    platesolve_subprocess=subprocess.Popen(['python','subprocesses/Platesolveprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)

                    platesolve_crop = self.config["camera"][g_dev['cam'].name]["settings"]['platesolve_image_crop']
                    bin_for_platesolve= self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_platesolve']
                    platesolve_bin_factor=self.config["camera"][g_dev['cam'].name]["settings"]['platesolve_bin_value']

                    pickle.dump([hdufocusdata, hduheader, self.local_calibration_path, cal_name, frame_type, time_platesolve_requested,
                     pixscale, pointing_ra, pointing_dec, platesolve_crop, bin_for_platesolve, platesolve_bin_factor, g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"], g_dev['cam'].camera_known_readnoise, self.config['minimum_realistic_seeing']], platesolve_subprocess.stdin)

                    # yet another pickle debugger.
                    if False:
                        pickle.dump([hdufocusdata, hduheader, self.local_calibration_path, cal_name, frame_type, time_platesolve_requested,
                         pixscale, pointing_ra, pointing_dec, platesolve_crop, bin_for_platesolve, platesolve_bin_factor, g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"], g_dev['cam'].camera_known_readnoise, self.config['minimum_realistic_seeing']], open('subprocesses/testplatesolvepickle','wb'))

                    del hdufocusdata

                    # Essentially wait until the subprocess is complete
                    platesolve_subprocess.communicate()

                    if os.path.exists(self.local_calibration_path + 'platesolve.pickle'):
                        solve= pickle.load(open(self.local_calibration_path + 'platesolve.pickle', 'rb'))
                    else:
                        solve= 'error'
                    try:
                        os.remove(self.local_calibration_path + 'platesolve.pickle')
                    except:
                        plog ("Could not remove platesolve pickle. ")

                    if solve == 'error':
                        plog ("Planewave solve came back as error")
                        self.last_platesolved_ra = np.nan
                        self.last_platesolved_dec = np.nan
                        self.last_platesolved_ra_err = np.nan
                        self.last_platesolved_dec_err = np.nan
                        self.platesolve_errors_in_a_row=self.platesolve_errors_in_a_row+1
                    else:
                        plog(
                            "PW Solves: ",
                            solve["ra_j2000_hours"],
                            solve["dec_j2000_degrees"],
                        )

                        target_ra = g_dev["mnt"].last_ra_requested
                        target_dec = g_dev["mnt"].last_dec_requested
                        solved_ra = solve["ra_j2000_hours"]
                        solved_dec = solve["dec_j2000_degrees"]
                        solved_arcsecperpixel = solve["arcsec_per_pixel"]
                        plog("1x1 pixelscale solved: " + str(float(solved_arcsecperpixel / platesolve_bin_factor / g_dev['cam'].native_bin)))

                        self.pixelscale_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].name + str(g_dev['obs'].name))
                        try:
                            pixelscale_list=self.pixelscale_shelf['pixelscale_list']
                        except:
                            pixelscale_list=[]

                        pixelscale_list.append(float(solved_arcsecperpixel / platesolve_bin_factor / g_dev['cam'].native_bin))

                        too_long=True
                        while too_long:
                            if len(pixelscale_list) > 100:
                                pixelscale_list.pop(0)
                            else:
                                too_long = False

                        self.pixelscale_shelf['pixelscale_list'] = pixelscale_list
                        self.pixelscale_shelf.close()



                        err_ha = target_ra - solved_ra
                        err_dec = target_dec - solved_dec

                        # Check that the RA doesn't cross over zero, if so, bring it back around
                        if err_ha > 12:
                            plog ("BIG CHANGE ERR_HA")
                            plog(err_ha)
                            err_ha = err_ha - 24
                            plog(err_ha)
                        elif err_ha < -12:
                            plog ("BIG CHANGE ERR_HA")
                            plog(err_ha)
                            err_ha = err_ha + 24
                            plog(err_ha)

                        plog("Deviation from plate solution in ra: " + str(round(err_ha * 15 * 3600, 2)) + " & dec: " + str (round(err_dec * 3600, 2)) + " asec")

                        self.last_platesolved_ra = solve["ra_j2000_hours"]
                        self.last_platesolved_dec = solve["dec_j2000_degrees"]
                        self.last_platesolved_ra_err = target_ra - solved_ra
                        self.last_platesolved_dec_err = target_dec - solved_dec
                        self.platesolve_errors_in_a_row=0

                        # Reset Solve timers
                        g_dev['obs'].last_solve_time = datetime.datetime.now()
                        g_dev['obs'].images_since_last_solve = 0




                        # Test here that there has not been a slew, if there has been a slew, cancel out!


                        # If we are WAY out of range, then reset the mount reference and attempt moving back there.
                        if not self.auto_centering_off:
                            if (abs(err_ha * 15 * 3600) > 5400) or (abs(err_dec * 3600) > 5400):
                                err_ha = 0
                                err_dec = 0
                                plog("Platesolve has found that the current suggested pointing is way off!")
                                plog("This may be a poor pointing estimate.")
                                plog("This is more than a simple nudge, so not nudging the scope.")
                                g_dev["mnt"].reset_mount_reference()
                                plog("I've  reset the mount_reference.")

                                plog ("reattempting to get back on target on next attempt")
                                #self.pointing_correction_requested_by_platesolve_thread = True
                                self.pointing_recentering_requested_by_platesolve_thread = True
                                self.pointing_correction_request_time = time.time()
                                self.pointing_correction_request_ra = target_ra
                                self.pointing_correction_request_dec = target_dec
                                self.pointing_correction_request_ra_err = err_ha
                                self.pointing_correction_request_dec_err = err_dec

                            elif self.time_of_last_slew > time_platesolve_requested:
                                plog("detected a slew since beginning platesolve... bailing out of platesolve.")

                            else:

                                 self.pointing_correction_requested_by_platesolve_thread = True
                                 self.pointing_correction_request_time = time.time()
                                 self.pointing_correction_request_ra = pointing_ra + err_ha
                                 self.pointing_correction_request_dec = pointing_dec + err_dec
                                 self.pointing_correction_request_ra_err = err_ha
                                 self.pointing_correction_request_dec_err = err_dec

                                 if not g_dev['obs'].mount_reference_model_off:
                                     if target_dec > -85 and target_dec < 85 and g_dev['mnt'].last_slew_was_pointing_slew:
                                         try:
                                             plog ("updating mount reference")
                                             g_dev['mnt'].last_slew_was_pointing_slew = False

                                             plog ("adjustment: " + str(err_ha) +' ' +str(err_dec))
                                             if g_dev["mnt"].pier_side == 0:
                                                 try:
                                                     plog ("current references: " + str ( g_dev['mnt'].get_mount_reference()))
                                                     g_dev["mnt"].adjust_mount_reference(
                                                         err_ha, err_dec
                                                     )
                                                 except Exception as e:
                                                     plog("Something is up in the mount reference adjustment code ", e)
                                             else:
                                                 try:
                                                     plog ("current references: " + str ( g_dev['mnt'].get_flip_reference()))
                                                     g_dev["mnt"].adjust_flip_reference(
                                                         err_ha, err_dec
                                                     )
                                                 except Exception as e:
                                                     plog("Something is up in the mount reference adjustment code ", e)
                                             plog ("final references: " + str ( g_dev['mnt'].get_mount_reference()))

                                         except:
                                             plog("This mount doesn't report pierside")
                                             plog(traceback.format_exc())


                        self.platesolve_is_processing = False


                self.platesolve_is_processing = False
                self.platesolve_queue.task_done()

                g_dev['mnt'].last_slew_was_pointing_slew = False

                one_at_a_time = 0

            else:
                time.sleep(0.1)

    def slow_camera_process(self):
        """
        A place to process non-process dependant images from the camera pile.
        Usually long-term saves to disk and such things
        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if (not self.slow_camera_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                slow_process = self.slow_camera_queue.get(block=False)
                slow_process = slow_process[1]

                # Set up RA and DEC headers
                # needs to be done AFTER text file is sent up.
                # Text file RA and Dec and PTRarchive RA and Dec are formatted different

                temphduheader = slow_process[3]

                if slow_process[0] == 'focus':
                    hdufocus = fits.PrimaryHDU()
                    hdufocus.data = slow_process[2]
                    hdufocus.header = temphduheader
                    hdufocus.header["NAXIS1"] = hdufocus.data.shape[0]
                    hdufocus.header["NAXIS2"] = hdufocus.data.shape[1]
                    hdufocus.header["DATE"] = (
                        datetime.date.strftime(
                            datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
                        ),
                        "Date FITS file was written",
                    )
                    hdufocus.writeto(slow_process[1], overwrite=True, output_verify='silentfix')

                    try:
                        hdufocus.close()
                    except:
                        pass
                    del hdufocus

                if slow_process[0] == 'localcalibration':

                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:

                            # Figure out which folder to send the calibration file to
                            # and delete any old files over the maximum amount to store
                            if slow_process[4] == 'bias':
                                tempfilename = self.local_bias_folder + slow_process[1].replace('.fits', '.npy')
                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_bias_to_store']
                                n_files = len(glob.glob(self.local_bias_folder + '*.n*'))
                                while n_files > max_files:
                                    list_of_files = glob.glob(self.local_bias_folder + '*.n*')
                                    n_files = len(list_of_files)
                                    oldest_file = min(list_of_files, key=os.path.getctime)
                                    os.remove(oldest_file)

                            elif slow_process[4] == 'dark':
                                tempexposure = temphduheader['EXPTIME']
                                tempfilename = self.local_dark_folder + \
                                    slow_process[1].replace('.fits', '_' + str(tempexposure) + '_.npy')
                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_dark_to_store']
                                n_files = len(glob.glob(self.local_dark_folder + '*.n*'))
                                while n_files > max_files:
                                    list_of_files = glob.glob(self.local_dark_folder + '*.n*')
                                    n_files = len(list_of_files)
                                    oldest_file = min(list_of_files, key=os.path.getctime)
                                    os.remove(oldest_file)

                            elif slow_process[4] == 'flat' or slow_process[4] == 'skyflat' or slow_process[4] == 'screenflat':
                                tempfilter = temphduheader['FILTER']
                                tempexposure = temphduheader['EXPTIME']
                                if not os.path.exists(self.local_flat_folder + tempfilter):
                                    os.makedirs(self.local_flat_folder + tempfilter)
                                tempfilename = self.local_flat_folder + tempfilter + '/' + \
                                    slow_process[1].replace('.fits', '_' + str(tempexposure) + '_.npy')

                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_flat_to_store']
                                n_files = len(glob.glob(self.local_flat_folder + tempfilter + '/' + '*.n*'))
                                while n_files > max_files:
                                    list_of_files = glob.glob(self.local_flat_folder + tempfilter + '/' + '*.n*')
                                    n_files = len(list_of_files)
                                    oldest_file = min(list_of_files, key=os.path.getctime)
                                    os.remove(oldest_file)

                            # Save the file as an uncompressed numpy binary
                            np.save(
                                tempfilename,
                                np.array(slow_process[2], dtype=np.float32)
                            )

                            saver = 1

                        except Exception as e:
                            plog("Failed to write raw file: ", e)
                            if "requested" in e and "written" in e:
                                plog(check_download_cache())
                            plog(traceback.format_exc())
                            time.sleep(10)
                            saverretries = saverretries + 1

                if slow_process[0] == 'raw' or slow_process[0] == 'raw_alt_path' or slow_process[0] == 'reduced_alt_path':

                    # Make  sure the alt paths exist
                    if self.config["save_to_alt_path"] == "yes":
                        if slow_process[0] == 'raw_alt_path' or slow_process[0] == 'reduced_alt_path':
                            os.makedirs(
                                self.alt_path + g_dev["day"], exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/raw/", exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/reduced/", exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/calib/", exist_ok=True)

                    altfolder = self.config['temporary_local_alt_archive_to_hold_files_while_copying']
                    if not os.path.exists(self.config['temporary_local_alt_archive_to_hold_files_while_copying']):
                        os.makedirs(self.config['temporary_local_alt_archive_to_hold_files_while_copying'] )


                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:
                            hdu = fits.PrimaryHDU()
                            hdu.data = slow_process[2]
                            hdu.header = temphduheader
                            hdu.header["DATE"] = (
                                datetime.date.strftime(
                                    datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
                                ),
                                "Date FITS file was written",
                            )
                            if 'alt_path' in slow_process[0]:
                                #breakpoint()
                                hdu.writeto( altfolder +'/' + slow_process[1].split('/')[-1].replace('EX00','EX00-'+temphduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
                                )  # Save full raw file locally
                                self.altarchive_queue.put((copy.deepcopy(altfolder +'/' + slow_process[1].split('/')[-1].replace('EX00','EX00-'+temphduheader['OBSTYPE'])),copy.deepcopy(slow_process[1])), block=False)
                            else:
                                hdu.writeto(
                                    slow_process[1].replace('EX00','EX00-'+temphduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
                                )  # Save full raw file locally
                            try:
                                hdu.close()
                            except:
                                pass
                            del hdu
                            saver = 1

                        except Exception as e:
                            plog("Failed to write raw file: ", e)
                            if "requested" in e and "written" in e:
                                plog(check_download_cache())
                            plog(traceback.format_exc())
                            time.sleep(10)
                            saverretries = saverretries + 1

                if slow_process[0] == 'fz_and_send':

                    # Create the fz file ready for PTR Archive
                    # Note that even though the raw file is int16,
                    # The compression and a few pieces of software require float32
                    # BUT it actually compresses to the same size either way

                    temphduheader["BZERO"] = 0  # Make sure there is no integer scaling left over
                    temphduheader["BSCALE"] = 1  # Make sure there is no integer scaling left over
                    if self.config['save_raws_to_pipe_folder_for_nightly_processing']:


                        pipefolder = self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME'])
                        if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying']+'/'+ str(temphduheader['DAY-OBS'])):
                            os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']))

                        if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME'])):
                            os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME']))



                    if not self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:


                        # This routine saves the file ready for uploading to AWS
                        # It usually works perfectly 99.9999% of the time except
                        # when there is an astropy cache error. It is likely that
                        # the cache will need to be cleared when it fails, but
                        # I am still waiting for it to fail again (rare)
                        saver = 0
                        saverretries = 0
                        while saver == 0 and saverretries < 10:
                            try:
                                if self.config['ingest_raws_directly_to_archive']:
                                    hdufz = fits.CompImageHDU(
                                        np.array(slow_process[2], dtype=np.float32), temphduheader
                                    )
                                    hdufz.writeto(
                                        slow_process[1], overwrite=True
                                    )  # Save full fz file locally
                                    #print (slow_process[1])
                                    try:
                                        hdufz.close()
                                    except:
                                        pass
                                    del hdufz  # remove file from memory now that we are doing with it

                                if self.config['save_raws_to_pipe_folder_for_nightly_processing']:

                                    hdu = fits.PrimaryHDU(np.array(slow_process[2], dtype=np.float32), temphduheader)


                                    #plog ("gonna pipe folder")
                                    #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                    hdu.writeto(
                                        pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.fits'), overwrite=True
                                    )
                                    try:
                                        hdu.close()
                                    except:
                                        pass
                                    del hdu  # remove file from memory now that we are doing with it

                                    #(filename,dayobs,instrume) = fileinfo
                                    self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.fits')),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
                                    #hdufz.writeto(
                                    #    slow_process[1], overwrite=True
                                    #)  # Save full fz file locally
                                saver = 1
                            except Exception as e:
                                plog("Failed to write raw fz file: ", e)
                                if "requested" in e and "written" in e:
                                    plog(check_download_cache())
                                plog(traceback.format_exc())
                                time.sleep(10)
                                saverretries = saverretries + 1


                        # Send this file up to ptrarchive
                        if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                            self.enqueue_for_PTRarchive(
                                26000000, '', slow_process[1]
                            )

                    else:  # Is an OSC

                        if self.config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':

                            newhdured = slow_process[2][::2, ::2]
                            GTRonly = slow_process[2][::2, 1::2]
                            GBLonly = slow_process[2][1::2, ::2]
                            newhdublue = slow_process[2][1::2, 1::2]
                            clearV = (block_reduce(slow_process[2],2))

                            oscmatchcode = (datetime.datetime.now().strftime("%d%m%y%H%M%S"))

                            temphduheader["OSCMATCH"] = oscmatchcode
                            temphduheader['OSCSEP'] = 'yes'
                            temphduheader['NAXIS1'] = float(temphduheader['NAXIS1'])/2
                            temphduheader['NAXIS2'] = float(temphduheader['NAXIS2'])/2
                            temphduheader['CRPIX1'] = float(temphduheader['CRPIX1'])/2
                            temphduheader['CRPIX2'] = float(temphduheader['CRPIX2'])/2
                            temphduheader['PIXSCALE'] = float(temphduheader['PIXSCALE'])*2
                            temphduheader['CDELT1'] = float(temphduheader['CDELT1'])*2
                            temphduheader['CDELT2'] = float(temphduheader['CDELT2'])*2
                            tempfilter = temphduheader['FILTER']
                            tempfilename = slow_process[1]



                            # Save and send R1
                            temphduheader['FILTER'] = tempfilter + '_R1'
                            temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'R1-EX')



                            if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                                hdufz = fits.CompImageHDU(
                                    np.array(newhdured, dtype=np.float32), temphduheader
                                )
                                hdufz.writeto(
                                    tempfilename.replace('-EX', 'R1-EX'), overwrite=True#, output_verify='silentfix'
                                )  # Save full fz file locally
                                self.enqueue_for_PTRarchive(
                                    26000000, '', tempfilename.replace('-EX', 'R1-EX')
                                )

                            if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
                                hdu = fits.PrimaryHDU(np.array(newhdured, dtype=np.float32), temphduheader)
                                temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')
                                #plog ("gonna pipe folder")
                                #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                hdu.writeto(
                                    pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
                                )
                                self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)

                            del newhdured

                            # Save and send G1
                            temphduheader['FILTER'] = tempfilter + '_G1'
                            temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'G1-EX')



                            if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                                hdufz = fits.CompImageHDU(
                                    np.array(GTRonly, dtype=np.float32), temphduheader
                                )
                                hdufz.writeto(
                                    tempfilename.replace('-EX', 'G1-EX'), overwrite=True#, output_verify='silentfix'
                                )  # Save full fz file locally
                                self.enqueue_for_PTRarchive(
                                    26000000, '', tempfilename.replace('-EX', 'G1-EX')
                                )
                            if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
                                hdu = fits.PrimaryHDU(np.array(GTRonly, dtype=np.float32), temphduheader)
                                temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

                                #plog ("gonna pipe folder")
                                #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                hdu.writeto(
                                    pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
                                )
                                self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
                            del GTRonly

                            # Save and send G2
                            temphduheader['FILTER'] = tempfilter + '_G2'
                            temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'G2-EX')




                            if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                                hdufz = fits.CompImageHDU(
                                    np.array(GBLonly, dtype=np.float32), temphduheader
                                )
                                hdufz.writeto(
                                    tempfilename.replace('-EX', 'G2-EX'), overwrite=True#, output_verify='silentfix'
                                )  # Save full fz file locally
                                self.enqueue_for_PTRarchive(
                                    26000000, '', tempfilename.replace('-EX', 'G2-EX')
                                )
                            if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
                                hdu = fits.PrimaryHDU(np.array(GBLonly, dtype=np.float32), temphduheader)
                                temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

                                #plog ("gonna pipe folder")
                                #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                hdu.writeto(
                                    pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
                                )
                                self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)

                            del GBLonly

                            # Save and send B1
                            temphduheader['FILTER'] = tempfilter + '_B1'
                            temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'B1-EX')




                            if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                                hdufz = fits.CompImageHDU(
                                    np.array(newhdublue, dtype=np.float32), temphduheader
                                )
                                hdufz.writeto(
                                    tempfilename.replace('-EX', 'B1-EX'), overwrite=True#, output_verify='silentfix'
                                )  # Save full fz file locally
                                self.enqueue_for_PTRarchive(
                                    26000000, '', tempfilename.replace('-EX', 'B1-EX')
                                )
                            if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
                                hdu = fits.PrimaryHDU(np.array(newhdublue, dtype=np.float32), temphduheader)
                                temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

                                #plog ("gonna pipe folder")
                                #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                hdu.writeto(
                                    pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
                                )
                                self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
                            del newhdublue

                            # Save and send clearV
                            temphduheader['FILTER'] = tempfilter + '_clearV'
                            temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'CV-EX')

                            temphduheader['SATURATE']=float(temphduheader['SATURATE']) * 4
                            temphduheader['FULLWELL']=float(temphduheader['FULLWELL']) * 4
                            temphduheader['MAXLIN']=float(temphduheader['MAXLIN']) * 4





                            if self.config['send_files_at_end_of_night'] == 'no' and self.config['ingest_raws_directly_to_archive']:
                                hdufz = fits.CompImageHDU(
                                    np.array(clearV, dtype=np.float32), temphduheader
                                )
                                hdufz.writeto(
                                    tempfilename.replace('-EX', 'CV-EX'), overwrite=True#, output_verify='silentfix'
                                )
                                self.enqueue_for_PTRarchive(
                                    26000000, '', tempfilename.replace('-EX', 'CV-EX')
                                )
                            if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
                                hdu = fits.PrimaryHDU(np.array(clearV, dtype=np.float32), temphduheader)
                                temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

                                #plog ("gonna pipe folder")
                                #plog (pipefolder + '/' + str(temphduheader['ORIGNAME']))
                                hdu.writeto(
                                    pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
                                )
                                self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
                            del clearV


                        else:
                            plog("this bayer grid not implemented yet")

                if slow_process[0] == 'reduced':
                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:
                            hdureduced = fits.PrimaryHDU()
                            hdureduced.data = slow_process[2]
                            hdureduced.header = temphduheader
                            hdureduced.header["NAXIS1"] = hdureduced.data.shape[0]
                            hdureduced.header["NAXIS2"] = hdureduced.data.shape[1]
                            hdureduced.header["DATE"] = (
                                datetime.date.strftime(
                                    datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
                                ),
                                "Date FITS file was written",
                            )
                            hdureduced.data = hdureduced.data.astype("float32")
                            hdureduced.writeto(
                                slow_process[1], overwrite=True, output_verify='silentfix'
                            )  # Save flash reduced file locally
                            saver = 1
                        except Exception as e:
                            plog("Failed to write raw file: ", e)
                            if "requested" in e and "written" in e:

                                plog(check_download_cache())
                            plog(traceback.format_exc())
                            time.sleep(10)
                            saverretries = saverretries + 1

                self.slow_camera_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.5)

    # Note this is a thread!
    def fast_to_ui(self):
        """Sends small files specifically focussed on UI responsiveness to AWS.

        This is primarily a queue for files that need to get to the UI FAST.
        This allows small files to be uploaded simultaneously
        with bigger files being processed by the ordinary queue.

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0
        while True:

            if (not self.fast_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.fast_queue.get(block=False)
                if pri_image is None:
                    plog("Got an empty entry in fast_queue.")
                    self.fast_queue.task_done()
                    one_at_a_time = 0
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = authenticated_request("POST", "/upload/", {"object_name": filename})
                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    #while True:
                    try:
                        reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=10)
                        #plog("SUCCESS FOR:" + filename)
                    except Exception as e:
                        if 'timeout' in str(e).lower() or 'SSLWantWriteError' or 'RemoteDisconnected' in str(e):
                            plog("Seems to have been a timeout on the file posted: " + str(e) + "Putting it back in the queue.")
                            plog(filename)
                            #breakpoint()
                            self.fast_queue.put((100, pri_image[1]), block=False)
                        else:
                            plog("Fatal connection glitch for a file posted: " + str(e))
                            plog(files)
                            plog((traceback.format_exc()))
                            #breakpoint()
                        #time.sleep(5)
                self.fast_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.05)

    # Note this is a thread!
    def calibration_to_ui(self):
        """Sends large calibrations files to AWS.

        This is primarily a queue for calibration masters to the UI so
        they don't slow down the other UI queues.

        This allows small files to be uploaded simultaneously
        with bigger files being processed by the ordinary queue.

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0
        while True:

            if (not self.calibrationui_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.calibrationui_queue.get(block=False)
                if pri_image is None:
                    plog("Got an empty entry in fast_queue.")
                    self.calibrationui_queue.task_done()
                    one_at_a_time = 0
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = authenticated_request("POST", "/upload/", {"object_name": filename})
                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    #while True:
                    try:
                        # Different timeouts for different filesizes.
                        # Large filesizes are usually calibration files during the daytime
                        # So need and can have longer timeouts to get it up the pipe.
                        # However small UI files need to get up in some reasonable amount of time
                        # and have a reasonable timeout so the UI doesn't glitch out.
                        reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=1800)

                        #plog("SUCCESS FOR:" + filename)
                    except Exception as e:
                        if 'timeout' in str(e).lower() or 'SSLWantWriteError' or 'RemoteDisconnected' in str(e):
                            plog("Seems to have been a timeout on the file posted: " + str(e) + "Putting it back in the queue.")
                            plog(filename)
                            #breakpoint()
                            self.calibrationui_queue.put((100, pri_image[1]), block=False)
                        else:
                            plog("Fatal connection glitch for a file posted: " + str(e))
                            plog(files)
                            plog((traceback.format_exc()))
                            #breakpoint()
                        #time.sleep(5)
                self.calibrationui_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.05)

    # Note this is a thread!
    def medium_to_ui(self):
        """Sends medium files needed for the inspection tab to the UI.

        This is primarily a queue for files that need to get to the UI fairly quickly
        but not as rapidly needed as the fast queue.

        This allows small files to be uploaded simultaneously
        with bigger files being processed by the ordinary queue.

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0
        while True:

            if (not self.mediumui_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.mediumui_queue.get(block=False)
                if pri_image is None:
                    plog("Got an empty entry in mediumui_queue.")
                    self.mediumui_queue.task_done()
                    one_at_a_time = 0
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = authenticated_request("POST", "/upload/", {"object_name": filename})
                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    #while True:
                    try:
                        reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=300)
                        #plog("SUCCESS FOR:" + filename)
                    except Exception as e:
                        if 'timeout' in str(e).lower() or 'SSLWantWriteError' or 'RemoteDisconnected' in str(e):
                            plog("Seems to have been a timeout on the file posted: " + str(e) + "Putting it back in the queue.")
                            plog(filename)
                            #breakpoint()
                            self.mediumui_queue.put((100, pri_image[1]), block=False)
                        else:
                            plog("Fatal connection glitch for a file posted: " + str(e))
                            plog(files)
                            plog((traceback.format_exc()))
                            #breakpoint()
                        #time.sleep(5)
                self.mediumui_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.05)


    def send_to_user(self, p_log, p_level="INFO"):

        # This is now a queue--- it was actually slowing
        # everything down each time this was called!

        self.sendtouser_queue.put((p_log, p_level),block=False)
        # url_log = "https://logs.photonranch.org/logs/newlog"
        # body = json.dumps(
        #     {
        #         "site": self.config["obs_id"],
        #         "log_message": str(p_log),
        #         "log_level": str(p_level),
        #         "timestamp": time.time(),
        #     }
        # )

        # try:
        #     reqs.post(url_log, body, timeout=5)
        # except:
        #     plog("Log did not send, usually not fatal.")

    # Note this is another thread!

    def smartstack_image(self):

        while True:

            if not self.smartstack_queue.empty():
                (
                    paths,
                    pixscale,
                    smartstackid,
                    sskcounter,
                    Nsmartstack, pier_side
                ) = self.smartstack_queue.get(block=False)

                if paths is None:
                    continue

                # SmartStack Section
                if smartstackid != "no":
                    sstack_timer = time.time()

                    if self.config['keep_reduced_on_disk']:
                        img = fits.open(
                            paths["red_path"] + paths["red_name01"].replace('.fits','.head'),
                            ignore_missing_end=True,
                        )
                        imgdata = np.load(paths["red_path"] + paths["red_name01"].replace('.fits','.npy'))

                        g_dev['obs'].to_slow_process(1000,('reduced', paths["red_path"] + paths["red_name01"], imgdata, img[0].header, \
                                               'EXPOSE', g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                        picklepayload=[
                            paths,
                            smartstackid,
                            self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"],
                            self.local_calibration_path,
                            pixscale,
                            self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"],
                            self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg'],
                            pier_side,
                            self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"],
                            self.config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"],
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"],
                            g_dev['cam'].native_bin,
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["read_noise"],
                            self.config['minimum_realistic_seeing'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'] ,
                            self.config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance'] ,
                            self.config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance'] ,
                            self.config["camera"][g_dev['cam'].name]["settings"]['osc_saturation_enhance'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance'],
                            self.config["camera"][g_dev['cam'].name]["settings"]["crop_preview"],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_ybottom"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_ytop"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_xleft"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_xright"
                            ]
                            ]
                    else:
                        picklepayload=[
                            paths,
                            smartstackid,
                            False,
                            self.obsid_path,
                            pixscale,
                            self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"],
                            self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg'],
                            self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg'],
                            pier_side,
                            self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"],
                            None,
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"],
                            g_dev['cam'].native_bin,
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["read_noise"],
                            self.config['minimum_realistic_seeing'],
                            0,0,0,0,0,
                            self.config["camera"][g_dev['cam'].name]["settings"]["crop_preview"],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_ybottom"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_ytop"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_xleft"
                            ],
                            self.config["camera"][g_dev['cam'].name]["settings"][
                                "crop_preview_xright"
                            ]
                            ]


                    smartstack_subprocess=subprocess.Popen(['python','subprocesses/SmartStackprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)

                    pickle.dump(picklepayload, smartstack_subprocess.stdin)

                    # Another pickle debugger
                    if False:
                        pickle.dump(picklepayload, open('subprocesses/testsmartstackpickle','wb'))

                    # Essentially wait until the subprocess is complete
                    smartstack_subprocess.communicate()


                    self.fast_queue.put((15, (paths["im_path"], paths["jpeg_name10"])), block=False)
                    self.fast_queue.put(
                        (150, (paths["im_path"], paths["jpeg_name10"].replace('EX10', 'EX20'))), block=False)

                    reprojection_failed=pickle.load(open(paths["im_path"] + 'smartstack.pickle', 'rb'))
                    try:
                        os.remove(paths["im_path"] + 'smartstack.pickle')
                    except:
                        pass

                    if reprojection_failed == True:
                        g_dev["obs"].send_to_user(
                            "A smartstack failed to stack, the single image has been sent to the GUI.",
                            p_level="INFO",
                        )

                    else:
                        g_dev["obs"].send_to_user(
                            "A preview SmartStack, "
                            + str(sskcounter + 1)
                            + " out of "
                            + str(Nsmartstack)
                            + ", has been sent to the GUI.",
                            p_level="INFO",
                        )
                    plog(datetime.datetime.now())

                plog("Smartstack round complete. Time taken: " + str(time.time() - sstack_timer))

                self.smartstack_queue.task_done()
            else:
                time.sleep(0.1)

    def check_platesolve_and_nudge(self):

        """
        A function periodically called to check if there is a telescope nudge to re-center to undertake.
        """
        if not g_dev['obs'].auto_centering_off:
            # Sometimes the pointing is so far off platesolve requests a new slew and recenter
            if self.pointing_recentering_requested_by_platesolve_thread:
                self.pointing_recentering_requested_by_platesolve_thread = False
                self.pointing_correction_requested_by_platesolve_thread = False
                g_dev['mnt'].go_command(ra=self.pointing_correction_request_ra, dec=self.pointing_correction_request_dec)
                g_dev['seq'].centering_exposure(no_confirmation=True, try_hard=True, try_forever=True)
                if g_dev['seq'].currently_mosaicing:
                    # Slew to new mosaic pane location.
                    new_ra = g_dev['seq'].mosaic_center_ra + g_dev['seq'].current_mosaic_displacement_ra
                    new_dec= g_dev['seq'].mosaic_center_dec + g_dev['seq'].current_mosaic_displacement_dec
                    new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)
                    wait_for_slew()
                    #g_dev['mnt'].mount.SlewToCoordinatesAsync(new_ra, new_dec)
                    g_dev['mnt'].slew_async_directly(ra=new_ra, dec=new_dec)
                    wait_for_slew()

                    self.time_of_last_slew=time.time()



            # This block repeats itself in various locations to try and nudge the scope
            # If the platesolve requests such a thing.
            if self.pointing_correction_requested_by_platesolve_thread and not g_dev['cam'].currently_in_smartstack_loop:

                if self.pointing_correction_request_time > self.time_of_last_slew:  # Check it hasn't slewed since request

                    plog("Re-centering Telescope Slightly.")
                    self.send_to_user("Re-centering Telescope Slightly.")
                    wait_for_slew()
                    g_dev['mnt'].previous_pier_side=g_dev['mnt'].mount.sideOfPier
                    ranudge= g_dev['mnt'].mount.RightAscension + g_dev['obs'].pointing_correction_request_ra_err
                    decnudge= g_dev['mnt'].mount.Declination + g_dev['obs'].pointing_correction_request_dec_err
                    if ranudge < 0:
                        ranudge=ranudge+24
                    if ranudge > 24:
                        ranudge=ranudge-24
                    self.time_of_last_slew=time.time()
                    try:
                        wait_for_slew()
                        #g_dev['mnt'].mount.SlewToCoordinatesAsync(ranudge, decnudge)
                        g_dev['mnt'].slew_async_directly(ra=ranudge, dec=decnudge)
                        wait_for_slew()
                    except:
                        plog (traceback.format_exc())
                    if not g_dev['mnt'].previous_pier_side==g_dev['mnt'].mount.sideOfPier:
                        self.send_to_user("Detected pier flip in re-centering. Re-centering telescope again.")
                        g_dev['mnt'].go_command(ra=self.pointing_correction_request_ra, dec=self.pointing_correction_request_dec)
                        g_dev['seq'].centering_exposure(no_confirmation=True, try_hard=True, try_forever=True)
                    g_dev['obs'].time_of_last_slew = time.time()
                    wait_for_slew()

                self.pointing_correction_requested_by_platesolve_thread = False

    def get_enclosure_status_from_aws(self):

        """
        Requests the current enclosure status from the related WEMA.
        """


        wema = self.wema_name
        uri_status = f"https://status.photonranch.org/status/{wema}/enclosure/"


        try:
            aws_enclosure_status=reqs.get(uri_status, timeout=20)

            aws_enclosure_status=aws_enclosure_status.json()

            aws_enclosure_status['site']=self.name

            for enclosurekey in aws_enclosure_status['status']['enclosure']['enclosure1'].keys():
                aws_enclosure_status['status']['enclosure']['enclosure1'][enclosurekey]=aws_enclosure_status['status']['enclosure']['enclosure1'][enclosurekey]['val']

            if self.assume_roof_open:
                aws_enclosure_status['status']['enclosure']['enclosure1']["shutter_status"] = 'Sim. Open'
                aws_enclosure_status['status']['enclosure']['enclosure1']["enclosure_mode"] = "Simulated"



            try:
                # To stop status's filling up the queue under poor connection conditions
                # There is a size limit to the queue
                if self.send_status_queue.qsize() < 7:
                    self.send_status_queue.put((self.name, 'enclosure', aws_enclosure_status['status']), block=False)

            except Exception as e:
                plog ("aws enclosure send failed ", e)

            aws_enclosure_status=aws_enclosure_status['status']['enclosure']['enclosure1']

        except Exception as e:
            plog("Failed to get aws enclosure status. Usually not fatal:  ", e)

        try:
            if g_dev['seq'].last_roof_status == 'Closed' and aws_enclosure_status["shutter_status"] in ['Open','open']:
                g_dev['seq'].time_roof_last_opened=time.time()
                # reset blocks so it can restart a caelndar event
                g_dev['seq'].reset_completes()
                g_dev['seq'].last_roof_status = 'Open'

            if g_dev['seq'].last_roof_status == 'Open' and aws_enclosure_status["shutter_status"] in ['Closed','closed']:
                g_dev['seq'].last_roof_status = 'Closed'
        except:
            plog("Glitch on getting shutter status in aws call.")





        try:

            status = {'shutter_status': aws_enclosure_status["shutter_status"],
                      'enclosure_synchronized': aws_enclosure_status["enclosure_synchronized"],  # self.following, 20220103_0135 WER
                      'dome_azimuth': aws_enclosure_status["dome_azimuth"],
                      'dome_slewing': aws_enclosure_status["dome_slewing"],
                      'enclosure_mode': aws_enclosure_status["enclosure_mode"]}

        except:
            try:
                status = {'shutter_status': aws_enclosure_status["shutter_status"]}
            except:
                plog ('failed enclosure status!')
                status = {'shutter_status': 'Unknown'}

        if self.assume_roof_open:


            status = {'shutter_status': 'Sim. Open',
            "enclosure_mode": "Simulated"}

        return status

    def get_weather_status_from_aws(self):

        """
        Requests the current enclosure status from the related WEMA.
        """

        wema = self.wema_name
        uri_status = f"https://status.photonranch.org/status/{wema}/weather/"

        try:
            aws_weather_status=reqs.get(uri_status, timeout=20)
            aws_weather_status=aws_weather_status.json()

            aws_weather_status['site']=self.name
        except Exception as e:
            plog("Failed to get aws weather status. Usually not fatal:  ", e)
            aws_weather_status={}
            aws_weather_status['status']={}
            aws_weather_status['status']['observing_conditions']={}
            aws_weather_status['status']['observing_conditions']['observing_conditions1'] = None

        try:
            if aws_weather_status['status']['observing_conditions']['observing_conditions1'] == None:
                aws_weather_status['status']['observing_conditions']['observing_conditions1'] = {'wx_ok': 'Unknown'}
            else:
                for weatherkey in aws_weather_status['status']['observing_conditions']['observing_conditions1'].keys():
                    aws_weather_status['status']['observing_conditions']['observing_conditions1'][weatherkey]=aws_weather_status['status']['observing_conditions']['observing_conditions1'][weatherkey]['val']
        except:
            plog ("bit of a glitch in weather status")
            aws_weather_status={}
            aws_weather_status['status']={}
            aws_weather_status['status']['observing_conditions']={}
            aws_weather_status['status']['observing_conditions']['observing_conditions1'] = {'wx_ok': 'Unknown'}

        try:
            # To stop status's filling up the queue under poor connection conditions
            # There is a size limit to the queue
            if self.send_status_queue.qsize() < 7:
                self.send_status_queue.put((self.name, 'weather', aws_weather_status['status']), block=False)

        except Exception as e:
            plog ("aws enclosure send failed ", e)

        aws_weather_status=aws_weather_status['status']['observing_conditions']['observing_conditions1']

        return aws_weather_status

    def enqueue_for_PTRarchive(self, priority, im_path, name):
        image = (im_path, name)
        self.ptrarchive_queue.put((priority, image), block=False)

    def enqueue_for_fastUI(self, priority, im_path, name):
        image = (im_path, name)
        self.fast_queue.put((priority, image), block=False)

    def enqueue_for_mediumUI(self, priority, im_path, name):
        image = (im_path, name)
        self.mediumui_queue.put((priority, image), block=False)

    def enqueue_for_calibrationUI(self, priority, im_path, name):
        image = (im_path, name)
        self.calibrationui_queue.put((priority, image), block=False)

    def to_smartstack(self, to_red):
        self.smartstack_queue.put(to_red, block=False)

    def to_slow_process(self, priority, to_slow):
        self.slow_camera_queue.put((priority, to_slow), block=False)

    def to_platesolve(self, to_platesolve):
        self.platesolve_queue.put( to_platesolve, block=False)

    def to_sep(self, to_sep):
        self.sep_queue.put( to_sep, block=False)

    def to_mainjpeg(self, to_sep):
        self.mainjpeg_queue.put( to_sep, block=False)

    def request_update_status(self, mount_only=False):
        if not self.currently_updating_status and not mount_only:
            self.update_status_queue.put( 'normal', block=False)
        elif not self.currently_updating_status and mount_only:
            self.update_status_queue.put( 'mountonly', block=False)

    def request_full_update(self):
        if not g_dev["obs"].currently_updating_FULL:
            self.FULL_update_thread_queue.put( 'dummy', block=False)

def wait_for_slew():

    """
    A function called when the code needs to wait for the telescope to stop slewing before undertaking a task.
    """

    try:
        if not g_dev['mnt'].rapid_park_indicator:
            movement_reporting_timer = time.time()
            while g_dev['mnt'].mount.Slewing:
                if time.time() - movement_reporting_timer > 2.0:
                    plog('m>')
                    movement_reporting_timer = time.time()
                if not g_dev['obs'].currently_updating_status and g_dev['obs'].update_status_queue.empty():
                    g_dev['obs'].request_update_status(mount_only=True, dont_wait=True)

    except Exception as e:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        if 'pywintypes.com_error' in str(e):
            plog("Mount disconnected. Recovering.....")
            time.sleep(30)
            g_dev['mnt'].mount.Connected = True
        else:
            # breakpoint()
            pass
    return

if __name__ == "__main__":



    #DO NOT RUN CODE until we sort the blocking of the HA filter.
    o = Observatory(ptr_config.obs_id, ptr_config.site_config)
    o.run()  # This is meant to be a never ending loop.