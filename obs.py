
""""
IMPORTANT TODOs:

WER 20211211

Simplify. No site specific if statements in main code if possible.
Sort out when rotator is not installed and focus temp when no probe
is in the Gemini.

Abstract away Redis, Memurai, and local shares for IPC.
"""

import ephem
import datetime
import json
#import math
import os
import queue
import shelve
import socket
import threading
import time
import sys
import shutil
import sep
sep.set_sub_object_limit(16384)
#import signal
import glob

import astroalign as aa
from astropy.io import fits
from astropy.nddata import block_reduce
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord, FK5, ICRS,  \
    EarthLocation, AltAz, get_sun, get_moon
from astropy.time import Time
from astropy import units as u
from astropy.table import Table
from astropy.stats import median_absolute_deviation

# For fast photutils source detection
#from astropy.stats import sigma_clipped_stats
#from photutils.detection import DAOStarFinder

from dotenv import load_dotenv
import numpy as np
import numpy.ma as ma
import redis  # Client, can work with Memurai

import requests
import urllib.request
#import sep
#from skimage.io import imsave
#from skimage.transform import resize
import func_timeout
import traceback
import psutil

from api_calls import API_calls
from auto_stretch.stretch import Stretch
import ptr_config

from devices.camera import Camera
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
from devices.enclosure import Enclosure
from devices.mount import Mount
from devices.telescope import Telescope
from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
from devices.selector import Selector
from devices.screen import Screen
from devices.sequencer import Sequencer
from global_yard import g_dev
from planewave import platesolve
import ptr_events
from ptr_utility import plog
from scipy import stats
from PIL import Image, ImageEnhance, ImageFont, ImageDraw

#import colour
from colour_demosaicing import (
    demosaicing_CFA_Bayer_bilinear,  # )#,
    # demosaicing_CFA_Bayer_Malvar2004,
    demosaicing_CFA_Bayer_Menon2007)
# mosaicing_CFA_Bayer)

# Incorporate better request retry strategy
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=50,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))
#reqs.mount('https://', HTTPAdapter(max_retries=retries))

# The ingester should only be imported after environment variables are loaded in.
load_dotenv(".env")
from ocs_ingester.ingester import frame_exists, upload_file_and_ingest_to_archive

def test_connect(host='http://google.com'):
    try:
        urllib.request.urlopen(host)  # Python 3.x
        return True
    except:
        return False


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


listOfProcessIds = findProcessIdByName('maxim_dl')
for pid in listOfProcessIds:
    pid_num = pid['pid']
    plog("Terminating existing Maxim process:  ", pid_num)
    p2k = psutil.Process(pid_num)
    p2k.terminate()


def send_status(obsy, column, status_to_send):
    """Sends an update to the status endpoint."""
    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}

    try:

        data = json.dumps(payload)
    except Exception as e:
        plog("Failed to create status payload. Usually not fatal:  ", e)

    try:
        reqs.post(uri_status, data=data)
    except Exception as e:
        plog("Failed to send_status. Usually not fatal:  ", e)


debug_flag = None
debug_lapse_time = None


class Observatory:
    """Docstring here"""

    def __init__(self, name, ptr_config):
        # This is the main class through which we can make authenticated api calls.
        self.api = API_calls()



        self.command_interval = 0  # seconds between polls for new commands
        self.status_interval = 0  # NOTE THESE IMPLEMENTED AS A DELTA NOT A RATE.

        self.name = name  # NB NB NB Names needs a once-over.
        self.obs_id = name

        g_dev['name'] = name
        self.config = ptr_config
        self.observatory_location = ptr_config["observatory_location"]
        self.debug_flag = self.config['debug_mode']
        self.admin_only_flag = self.config['admin_owner_commands_only']

        # Default path
        self.obsid_path = ptr_config["client_path"] + '/' + self.name + '/'
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)

        if self.debug_flag:
            self.debug_lapse_time = time.time() + self.config['debug_duration_sec']
            g_dev['debug'] = True
            self.camera_temperature_in_range_for_calibrations = True
            #g_dev['obs'].open_and_enabled_to_observe = True
        else:
            self.debug_lapse_time = 0.0
            g_dev['debug'] = False
            #g_dev['obs'].open_and_enabled_to_observe = False

        if self.config["wema_is_active"]:
            self.hostname = socket.gethostname()
            if self.hostname in self.config["wema_hostname"]:
                self.is_wema = True
                g_dev["wema_share_path"] = ptr_config["wema_write_share_path"]
                self.wema_path = g_dev["wema_share_path"]
            else:
                # This host is a client
                self.is_wema = False  # This is a client.
                self.obsid_path = ptr_config["client_path"] + '/' + self.name + '/'
                if not os.path.exists(self.obsid_path):
                    os.makedirs(self.obsid_path)

                g_dev["obsid_path"] = self.obsid_path
                g_dev["wema_share_path"] = ptr_config[
                    "client_write_share_path"
                ]  # Just to be safe.
                self.wema_path = g_dev["wema_share_path"]
        else:
            self.is_wema = False  # This is a client.
            self.obsid_path = ptr_config["client_path"] + self.config['obs_id'] + '/'
            g_dev["obsid_path"] = self.obsid_path
            g_dev["wema_share_path"] = self.obsid_path  # Just to be safe.
            self.wema_path = g_dev["wema_share_path"]

        if self.config["obsid_is_specific"]:
            self.obsid_is_specific = True
        else:
            self.obsid_is_specific = False

        self.last_request = None
        self.stopped = False
        self.status_count = 0
        self.first_pass= True
        self.stop_all_activity = False
        self.obsid_message = "-"
        self.all_device_types = ptr_config["device_types"]  # May not be needed
        self.device_types = ptr_config["device_types"]  # ptr_config['short_status_devices']
        self.wema_types = ptr_config["wema_types"]
        self.enc_types = None  # config['enc_types']
        self.short_status_devices = (
            ptr_config['short_status_devices']  # May not be needed for no wema obsy
        )
        self.observing_status_timer = datetime.datetime.now() - datetime.timedelta(
            days=1
        )
        self.observing_check_period = self.config[
            "observing_check_period"
        ]  # How many minutes between observing conditions check
        self.enclosure_status_timer = datetime.datetime.now() - datetime.timedelta(
            days=1
        )
        self.enclosure_check_period = self.config[
            "enclosure_check_period"
        ]  # How many minutes between enclosure check

        self.project_call_timer = time.time()
        self.get_new_job_timer = time.time()
        self.status_upload_time = 0.5
        self.command_busy = False
        # Instantiate the helper class for astronomical events
        # Soon the primary event / time values can come from AWS.
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()

        self.astro_events.calculate_events()
        self.astro_events.display_events()

        # Define a redis server if needed.
        redis_ip = ptr_config["redis_ip"]
        if redis_ip is not None:
            self.redis_server = redis.StrictRedis(
                host=redis_ip, port=6379, db=0, decode_responses=True
            )
            self.redis_wx_enabled = True
            g_dev["redis"] = self.redis_server  # I think IPC needs to be a class.
        else:
            self.redis_wx_enabled = False
            g_dev["redis"] = None  # a placeholder.

        g_dev["obs"] = self
        obsid_str = ptr_config["obs_id"]
        g_dev["obsid"]: obsid_str
        self.g_dev = g_dev

        # Use the configuration to instantiate objects for all devices.
        self.create_devices()
        self.loud_status = False

        # Clear out smartstacks directory
        #plog ("removing and reconstituting smartstacks directory")
        try:
            shutil.rmtree(self.obsid_path + "smartstacks")
        except:
            plog("problems with removing the smartstacks directory... usually a file is open elsewhere")
        time.sleep(3)
        if not os.path.exists(self.obsid_path + "smartstacks"):
            os.makedirs(self.obsid_path + "smartstacks")

        # Check directory system has been constructed
        # for new sites or changed directories in configs.
        # NB NB be careful if we have a site with multiple cameras, etc,
        # some of these directores seem up a level or two. WER

        if not os.path.exists(self.obsid_path + "ptr_night_shelf"):
            os.makedirs(self.obsid_path + "ptr_night_shelf")
        if not os.path.exists(self.obsid_path + "archive"):
            os.makedirs(self.obsid_path + "archive")
        if not os.path.exists(self.obsid_path + "tokens"):
            os.makedirs(self.obsid_path + "tokens")
        if not os.path.exists(self.obsid_path + "astropycache"):
            os.makedirs(self.obsid_path + "astropycache")
        if not os.path.exists(self.obsid_path + "smartstacks"):
            os.makedirs(self.obsid_path + "smartstacks")
        if not os.path.exists(self.obsid_path + "calibmasters"):  # retaining for backward compatibility
            os.makedirs(self.obsid_path + "calibmasters")
        camera_name = self.config['camera']['camera_1_1']['name']
        if not os.path.exists(self.obsid_path + "archive/" + camera_name + "/calibmasters"):
            os.makedirs(self.obsid_path + "archive/" + camera_name + "/calibmasters")
        if not os.path.exists(self.obsid_path + "archive/" + camera_name + "/localcalibrations"):
            os.makedirs(self.obsid_path + "archive/" + camera_name + "/localcalibrations")

        if not os.path.exists(self.obsid_path + "archive/" + camera_name + "/localcalibrations/darks"):
            os.makedirs(self.obsid_path + "archive/" + camera_name + "/localcalibrations/darks")
        if not os.path.exists(self.obsid_path + "archive/" + camera_name + "/localcalibrations/biases"):
            os.makedirs(self.obsid_path + "archive/" + camera_name + "/localcalibrations/biases")
        if not os.path.exists(self.obsid_path + "archive/" + camera_name + "/localcalibrations/flats"):
            os.makedirs(self.obsid_path + "archive/" + camera_name + "/localcalibrations/flats")

        self.calib_masters_folder = self.obsid_path + "archive/" + camera_name + "/calibmasters" + '/'
        self.local_dark_folder = self.obsid_path + "archive/" + camera_name + "/localcalibrations/darks" + '/'
        self.local_bias_folder = self.obsid_path + "archive/" + camera_name + "/localcalibrations/biases" + '/'
        self.local_flat_folder = self.obsid_path + "archive/" + camera_name + "/localcalibrations/flats" + '/'

        self.last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        self.images_since_last_solve = 10000

        self.time_last_status = time.time() - 3

        self.platesolve_is_processing = False

        # Build the to-AWS Try again, reboot, verify dome nad tel and start a thread.

        self.aws_queue = queue.PriorityQueue(maxsize=0)
        self.aws_queue_thread = threading.Thread(target=self.send_to_aws, args=())
        self.aws_queue_thread.start()

        self.fast_queue = queue.PriorityQueue(maxsize=0)
        self.fast_queue_thread = threading.Thread(target=self.fast_to_aws, args=())
        self.fast_queue_thread.start()

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

        # Set up command_queue for incoming jobs
        self.cmd_queue = queue.Queue(
            maxsize=0
        )  # Note this is not a thread but a FIFO buffer
        self.stop_all_activity = False  # This is used to stop the camera or sequencer
        self.exposure_halted_indicator = False
        # =============================================================================
        # Here we set up the reduction Queue and Thread:
        # =============================================================================
        self.smartstack_queue = queue.Queue(
            maxsize=0
        )  # Why do we want a maximum size and lose files?
        self.smartstack_queue_thread = threading.Thread(target=self.smartstack_image, args=())
        self.smartstack_queue_thread.start()
        self.blocks = None
        self.projects = None
        self.events_new = None
        self.reset_last_reference()
        self.env_exists = os.path.exists(os.getcwd() + '\.env')  # Boolean, check if .env present

        # Get initial coordinates into the global system
        g_dev['mnt'].get_mount_coordinates()

        # If mount is permissively set, reset mount reference
        # This is necessary for SRO and it seems for ECO
        # I actually think it may be necessary for all telescopes
        # Not all who wander are lost.... but those that point below altitude -10 probably are.
        # if self.config["mount"]["mount1"]["permissive_mount_reset"] == "yes":
        g_dev["mnt"].reset_mount_reference()

        # Keep track of how long it has been since the last activity
        self.time_of_last_exposure = time.time()
        self.time_of_last_slew = time.time()

        # Only poll the broad safety checks (altitude and inactivity) every 5 minutes
        self.time_since_safety_checks = time.time() - 310.0

        # Keep track of how long it has been since the last live connection to the internet
        self.time_of_last_live_net_connection = time.time()

        # If the camera is detected as substantially (20 degrees) warmer than the setpoint
        # during safety checks, it will keep it warmer for about 20 minutes to make sure
        # the camera isn't overheating, then return it to its usual temperature.
        self.camera_overheat_safety_warm_on = False
        self.camera_overheat_safety_timer = time.time()
        # Some things you don't want to check until the camera has been cooling for a while.
        self.camera_time_initialised = time.time()

        # If there is a pointing correction needed, then it is REQUESTED
        # by the platesolve thread and then the code will interject
        # a pointing correction at an appropriate stage.
        # But if the telescope moves in the meantime, this is cancelled.
        # A telescope move itself should already correct for this pointing in the process of moving.
        # This is sort of a more elaborate and time-efficient version of the previous "re-seek"
        self.pointing_correction_requested_by_platesolve_thread = False
        self.pointing_correction_request_time = time.time()
        self.pointing_correction_request_ra = 0.0
        self.pointing_correction_request_dec = 0.0

        # This variable is simply.... is it open and enabled to observe!
        # This is set when the roof is open and everything is safe
        # This allows sites without roof control or only able to shut
        # the roof to know it is safe to observe but also ... useful
        # to observe.... if the roof isn't open, don't get flats!
        # Off at bootup, but that would quickly change to true after the code
        # checks the roof status etc. self.weather_report_is_acceptable_to_observe=False
        if self.debug_flag:
            self.open_and_enabled_to_observe = True
        else:
            self.open_and_enabled_to_observe = False

        # On initialisation, there should be no commands heading towards the site
        # So this command reads the commands waiting and just ... ignores them
        # essentially wiping the command queue coming from AWS.
        # This prevents commands from previous nights/runs suddenly running
        # when obs.py is booted (has happened a bit!)
        url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
        body = {"site": self.name}
        #cmd = {}
        # Get a list of new jobs to complete (this request
        # marks the commands as "RECEIVED")
        unread_commands = reqs.request(
            "POST", url_job, data=json.dumps(body)
        ).json()

        # On startup, collect orphaned fits files that may have been dropped from the queue
        # when the site crashed
        g_dev['seq'].collect_and_queue_neglected_fits()

        # Inform UI of reboot
        self.send_to_user("Observatory code has been rebooted. Manually queued commands have been flushed.")

        # Need to set this for the night log
        # g_dev['foc'].set_focal_ref_reset_log(self.config["focuser"]["focuser1"]["reference"])
        # Send the config to AWS. TODO This has faulted.
        self.update_config()  # This is the never-ending control loop

        # g_dev['obs'].open_and_enabled_to_observe=True

        # breakpoint()
        #req2 = {'target': 'near_tycho_star', 'area': 150}
        #opt = {}
        #g_dev['seq'].sky_flat_script({}, {}, morn=True)
        # g_dev['seq'].extensive_focus_script(req2,opt)
        # req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 63, \
        #        'numOfDark': 31, 'darkTime': 75, 'numOfDark2': 31, 'dark2Time': 75, \
        #        'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  #This specificatin is obsolete
        #opt = {}
        # No action needed on  the enclosure at this level
        # self.park_and_close(enc_status)
        # NB The above put dome closed and telescope at Park, Which is where it should have been upon entry.
        #g_dev['seq'].bias_dark_script(req, opt, morn=True)

         
        
        # Pointing
        #req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
        #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
        #opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
        #result = g_dev['cam'].expose_command(req, opt, no_AWS=False, solve_it=True)

        #g_dev['seq'].regenerate_local_masters()

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
                plog(name)
                driver = devices_of_type[name]["driver"]
                settings = devices_of_type[name].get("settings", {})
                if dev_type == "observing_conditions":
                    device = ObservingConditions(
                        driver, name, self.config, self.astro_events
                    )
                elif dev_type == "enclosure":
                    device = Enclosure(driver, name, self.config, self.astro_events)
                elif dev_type == "mount":
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

        response = g_dev["obs"].api.authenticated_request("PUT", uri, self.config)
        if 'message' in response:
            if response['message'] == "Missing Authentication Token":
                plog("Missing Authentication Token. Config unable to be uploaded. Please fix this now.")
                sys.exit()
            else:
                plog("There may be a problem in the config upload? Here is the response.")
                plog(response)
        elif 'ResponseMetadata' in response:
            # plog(response['ResponseMetadata']['HTTPStatusCode'])
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                plog("Config uploaded successfully.")

            else:
                plog("Response to obsid config upload unclear. Here is the response")
                plog(response)
        else:
            plog("Response to obsid config upload unclear. Here is the response")
            plog(response)

    def cancel_all_activity(self):

        g_dev["obs"].stop_all_activity = True
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
        # try:
        plog("Emptying Command Queue")
        with self.cmd_queue.mutex:
            self.cmd_queue.queue.clear()

        plog("Stopping Exposure")
        try:
            # if g_dev["cam"].exposure_busy:
            g_dev["cam"]._stop_expose()                # Should we try to flush the image array?
            g_dev["cam"].exposure_busy = False
        except Exception as e:
            plog("Camera is not busy.", e)
            self.exposure_busy = False

        g_dev["obs"].exposure_halted_indicator = True

        # except:
        #    plog("Camera stop faulted.")
        #self.exposure_busy = False

        # while self.cmd_queue.qsize() > 0:
        #    plog("Deleting Job:  ", self.cmd_queue.get())

        # return  # Note we basically do nothing and let camera, etc settle down.

    def scan_requests(self, cancel_check=False):
        """Gets commands from AWS, and post a STOP/Cancel flag.

        This function will be a Thread. We limit the
        polling to once every 2.5 - 3 seconds because AWS does not
        appear to respond any faster. When we poll, we parse
        the action keyword for 'stop' or 'cancel' and post the
        existence of the timestamp of that command to the
        respective device attribute <self>.cancel_at. Then we
        enqueue the incoming command as well.
sel
        When a device is status scanned, if .cancel_at is not
        None, the device takes appropriate action and sets
        cancel_at back to None.

        NB at this time we are preserving one command queue
        for all devices at a site. This may need to change when we
        have parallel mountings or independently controlled cameras.
        """

        # This stopping mechanism allows for threads to close cleanly.
        try:
            if self.debug_flag and time.time() > self.debug_lapse_time:
                self.debug_flag = False
                plog("Debug_flag time has lapsed, so disabled. ")
        except:
            breakpoint()
            pass

        while not self.stopped:  # This variable is not used.

            if True:  # not g_dev["seq"].sequencer_hold:  THis causes an infinte loope witht he above while

                url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
                body = {"site": self.name}
                cmd = {}
                # Get a list of new jobs to complete (this request
                # marks the commands as "RECEIVED")
                unread_commands = reqs.request(
                    "POST", url_job, data=json.dumps(body)
                ).json()
                # Make sure the list is sorted in the order the jobs were issued
                # Note: the ulid for a job is a unique lexicographically-sortable id.
                if len(unread_commands) > 0:
                    unread_commands.sort(key=lambda x: x["timestamp_ms"])
                    # Process each job one at a time
                    #plog(
                    #    "# of incoming commands:  ",
                    #    len(unread_commands),
                    #    unread_commands,
                    #)

                    for cmd in unread_commands:

                        if not (self.admin_only_flag and (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles']) or (not self.admin_only_flag))):

                            # breakpoint()

                            if cmd["action"] in ["cancel_all_commands", "stop"] or cmd["action"].lower() in ["stop", "cancel"] or (cmd["action"] == "run" and cmd["required_params"]["script"] == "stopScript"):
                                # self.cancel_all_activity() # Hi Wayne, I have to cancel all acitivity with some roof stuff
                                # So I've moved the cancelling to it's own function just above so it can be called from multiple locations.

                                # elif cmd["action"].lower() in ["stop", "cancel"] or ( cmd["action"]  == "run" and cmd["script"]  == "stopScript"):
                                #self.stop_command(req, opt)
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

                                # Check here for admin/owner only functions
                                if action == "run" and script == 'collectScreenFlats' and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                    plog("Request rejected as flats can only be commanded by admin user.")
                                    g_dev['obs'].send_to_user(
                                        "Request rejected as flats can only be commanded by admin user.")
                                elif action == "run" and script == 'collectSkyFlats' and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
                                    plog("Request rejected as flats can only be commanded by admin user.")
                                    g_dev['obs'].send_to_user(
                                        "Request rejected as flats can only be commanded by admin user.")

                                elif action == "run" and script in ['32TargetPointingRun', 'pointingRun', 'makeModel'] and not (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles'])):
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
                                elif cmd['deviceType'] == 'enclosure' and not ("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles']):
                                    plog("Refusing command - only admin or owners can send enclosure commands")
                                    g_dev['obs'].send_to_user(
                                        "Refusing command - only admin or owners can send enclosure commands")
                                else:

                                    self.cmd_queue.put(cmd)  # SAVE THE COMMAND FOR LATER
                                    g_dev["obs"].stop_all_activity = False
                                    #plog(
                                    #    "Queueing up a new command... Hint:  " + cmd["action"]
                                    #)

                            if cancel_check:
                                result = {'stopped': True}
                                return  # Note we do not process any commands.
                        else:
                            plog("Request rejected as site in admin or owner mode.")
                            g_dev['obs'].send_to_user("Request rejected as site in admin or owner mode.")

                # NEED TO WAIT UNTIL CURRENT COMMAND IS FINISHED UNTIL MOVING ONTO THE NEXT ONE!
                # THAT IS WHAT CAUSES THE "CAMERA BUSY" ISSUE. We don't need to wait for the
                # rotator as the exposure routine in camera.py already waits for that.
                # if (not g_dev["cam"].exposure_busy) and (not g_dev['mnt'].mount.Slewing):
                if (not g_dev["cam"].exposure_busy):
                    while self.cmd_queue.qsize() > 0:
                        if not self.command_busy:  # This is to stop multiple commands running over the top of each other.
                            self.command_busy = True
                            #plog(
                            #    "Number of queued commands:  " + str(self.cmd_queue.qsize())
                            #)
                            cmd = self.cmd_queue.get()
                            # This code is redundant
                            if self.config["selector"]["selector1"]["driver"] is None:
                                port = cmd["optional_params"]["instrument_selector_position"]
                                g_dev["mnt"].instrument_port = port
                                cam_name = self.config["selector"]["selector1"]["cameras"][port]
                                if cmd["deviceType"][:6] == "camera":
                                    # Note camelCase is the format of command keys
                                    cmd["required_params"]["deviceInstance"] = cam_name
                                    cmd["deviceInstance"] = cam_name
                                    device_instance = cam_name
                                else:
                                    try:
                                        try:
                                            device_instance = cmd["deviceInstance"]
                                        except:
                                            device_instance = cmd["required_params"][
                                                "deviceInstance"
                                            ]
                                    except:
                                        pass
                            else:
                                device_instance = cmd["deviceInstance"]
                            plog("obs.scan_request: ", cmd)

                            device_type = cmd["deviceType"]
                            device = self.all_devices[device_type][device_instance]
                            try:
                                #plog("Trying to parse:  ", cmd)

                                device.parse_command(cmd)
                            except Exception as e:

                                plog(traceback.format_exc())

                                plog("Exception in obs.scan_requests:  ", e, 'cmd:  ', cmd)
                            self.command_busy = False

                # TO KEEP THE REAL-TIME USE A BIT SNAPPIER, POLL FOR NEW PROJECTS ON A MUCH SLOWER TIMESCALE
                # TO REMOVE UNNECESSARY CALLS FOR PROJECTS.
                if time.time() - self.project_call_timer > 30:
                    self.project_call_timer = time.time()
                    if self.debug_flag:
                        plog("~")
                    else:
                        plog('.')
                        # We print this to stay informed of process on the console.
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
                            "site": self.config["site"],
                            "start": start_aperture[0].replace('/', '-') + 'T' + start_aperture[1] + 'Z',
                            "end": close_aperture[0].replace('/', '-') + 'T' + close_aperture[1] + 'Z',
                            "full_project_details:": False,
                        }
                    )

                    # if (
                    #    True
                    # ):  # self.blocks is None: # This currently prevents pick up of calendar changes.
                    blocks = reqs.post(url_blk, body).json()
                    # if len(blocks) > 0:
                    self.blocks = blocks

                    url_proj = "https://projects.photonranch.org/projects/get-all-projects"
                    if True:
                        all_projects = reqs.post(url_proj).json()
                        self.projects = []
                        if len(all_projects) > 0 and len(blocks) > 0:
                            self.projects = all_projects  # NOTE creating a list with a dict entry as item 0
                        # Note the above does not load projects if there are no blocks scheduled.
                        # A sched block may or may not havean associated project.

                    # Design Note. Blocks relate to scheduled time at a site so we expect AWS to mediate block
                    # assignments. Priority of blocks is determined by the owner and a 'equipment match' for
                    # background projects.

                    # Projects on the other hand can be a very large pool so how to manage becomes an issue.
                    # To the extent a project is not visible at a site, aws should not present it. If it is
                    # visible and passes the owners priority it should then be presented to the site.

                    if self.events_new is None:
                        url = (
                            "https://api.photonranch.org/api/events?site="
                            + self.obs_id.upper()
                        )
                        self.events_new = reqs.get(url).json()
                return  # This creates an infinite loop

            else:

                continue

    def update_status(self, bpt=False, cancel_check=False, mount_only=False, dont_wait=False):
        """Collects status from all devices and sends an update to AWS.

        Each device class is responsible for implementing the method
        `get_status`, which returns a dictionary.
        """

        loud = False
        if bpt:
            plog('UpdateStatus bpt was invoked.')
            # breakpoint()
        send_enc = False
        send_ocn = False

        # Wait a bit between status updates
        if dont_wait == True:
            self.status_interval = self.status_upload_time + 0.25
        while time.time() < self.time_last_status + self.status_interval:
            return  # Note we are just not sending status, too soon.

        # Keep an eye on the stop-script time
        if g_dev['seq'].stop_script_called and ((time.time() - g_dev['seq'].stop_script_called_time) > 35):
            g_dev["obs"].send_to_user("Stop Script Complete.")
            g_dev['seq'].stop_script_called = False
            g_dev['seq'].stop_script_called_time = time.time()

        # Good spot to check if we need to nudge the telescope as long as we aren't exposing.
        if not g_dev["cam"].exposure_busy:
            self.check_platesolve_and_nudge()

        #plog ("Time between status updates: " + str(time.time() - self.time_last_status))

        t1 = time.time()
        status = {}

        # Loop through all types of devices.
        # For each type, we get and save the status of each device.

        if not self.config["wema_is_active"]:
            #device_list = self.short_status_devices()
            device_list = self.device_types
            remove_enc = False
        if self.config["wema_is_active"]:
            # used when wema is sending ocn and enc status via a different stream.
            device_list = self.short_status_devices
            remove_enc = False

        else:
            device_list = self.device_types  # used when one computer is doing everything for a site.
            remove_enc = True

        if mount_only == True:
            device_list = ['mount', 'telescope']

        for dev_type in device_list:
            #  The status that we will send is grouped into lists of
            #  devices by dev_type.
            status[dev_type] = {}
            # Names of all devices of the current type.
            # Recall that self.all_devices[type] is a dictionary of all
            # `type` devices, with key=name and val=device object itself.
            devices_of_type = self.all_devices.get(dev_type, {})
            device_names = devices_of_type.keys()

            for device_name in device_names:

                # Get the actual device object...
                device = devices_of_type[device_name]
                # ...and add it to main status dict.
                # breakpoint()

                if (
                    "enclosure" in device_name
                    # and device_name in self.config["wema_types"]
                    # and (self.is_wema or self.obsid_is_specific)
                ):

                    if self.config['enclosure']['enclosure1']['driver'] == None and not self.obsid_is_specific:
                        # Even if no connection send a satus
                        status = {'shutter_status': "No enclosure.",
                                  'enclosure_synchronized': False,  # self.following, 20220103_0135 WER
                                  'dome_azimuth': 0,
                                  'dome_slewing': False,
                                  'enclosure_mode': "No Enclosure",
                                  'enclosure_message': "No message"},  # self.state}#self.following, 20220103_0135 WER

                    elif (
                        datetime.datetime.now() - self.enclosure_status_timer
                    ) < datetime.timedelta(minutes=self.enclosure_check_period):
                        result = None
                        send_enc = False
                    else:
                        #plog("Running enclosure status check")
                        self.enclosure_status_timer = datetime.datetime.now()
                        send_enc = True

                        result = device.get_status()

                elif ("observing_conditions" in device_name
                      and self.config['observing_conditions']['observing_conditions1']['driver'] == None):
                    # Here is where the weather config gets updated.
                    if (
                        datetime.datetime.now() - self.observing_status_timer
                    ) < datetime.timedelta(minutes=self.observing_check_period):
                        result = None
                        send_ocn = False
                    else:
                        #plog("Running weather status check.")
                        self.observing_status_timer = datetime.datetime.now()
                        result = device.get_noocndevice_status()
                        send_ocn = True
                        if self.obsid_is_specific:
                            remove_enc = False

                elif (
                    "observing_conditions" in device_name
                    and device_name in self.config["wema_types"]
                    and (self.is_wema or self.obsid_is_specific)
                ):
                    # Here is where the weather config gets updated.
                    if (
                        datetime.datetime.now() - self.observing_status_timer
                    ) < datetime.timedelta(minutes=self.observing_check_period):
                        result = None
                        send_ocn = False
                    else:
                        plog("Running weather status check.")
                        self.observing_status_timer = datetime.datetime.now()
                        result = device.get_status(g_dev=g_dev)
                        send_ocn = True
                        if self.obsid_is_specific:
                            remove_enc = False

                else:
                    if 'telescope' in device_name:
                        status['telescope'] = status['mount']
                    else:
                        result = device.get_status()
                if result is not None:
                    status[dev_type][device_name] = result

        # If the roof is open, then it is open and enabled to observe
        try:
            if g_dev['enc'].status['shutter_status'] == 'Open':
                self.open_and_enabled_to_observe = True
        except:
            pass

        # Check that the mount hasn't slewed too close to the sun
        try:
            if not g_dev['mnt'].mount.Slewing:
                sun_coords = get_sun(Time.now())
                temppointing = SkyCoord((g_dev['mnt'].current_icrs_ra)*u.hour,
                                        (g_dev['mnt'].current_icrs_dec)*u.degree, frame='icrs')
    
                sun_dist = sun_coords.separation(temppointing)
                #plog ("sun distance: " + str(sun_dist.degree))
                if sun_dist.degree < self.config['closest_distance_to_the_sun'] and not g_dev['mnt'].mount.AtPark:
                    g_dev['obs'].send_to_user("Found telescope pointing too close to the sun: " +
                                              str(sun_dist.degree) + " degrees.")
                    plog("Found telescope pointing too close to the sun: " + str(sun_dist.degree) + " degrees.")
                    g_dev['obs'].send_to_user("Parking scope and cancelling all activity")
                    plog("Parking scope and cancelling all activity")
                    self.cancel_all_activity()
                    if not g_dev['mnt'].mount.AtPark:
                        g_dev['mnt'].park_command()
                    return
        except:
            plog ("Sun check didn't work for some reason")

        status["timestamp"] = round((time.time() + t1) / 2.0, 3)
        status["send_heartbeat"] = False
        try:
            ocn_status = None
            enc_status = None
            ocn_status = {"observing_conditions": status.pop("observing_conditions")}
            enc_status = {"enclosure": status.pop("enclosure")}
            device_status = status
        except:
            pass
        #plog ("Status update length: " + str(time.time() - beginning_update_status))
        loud = False
        # Consider inhibiting unless status rate is low
        obsy = self.name

        if status is not None:
            lane = "device"
            #send_status(obsy, lane, status)
            self.send_status_queue.put((obsy, lane, status), block=False)
        if ocn_status is not None:
            lane = "weather"
            # send_status(obsy, lane, ocn_status)  # NB Do not remove this send for SAF!
            if send_ocn == True:
                self.send_status_queue.put((obsy, lane, ocn_status), block=False)
        if enc_status is not None:
            lane = "enclosure"
            #send_status(obsy, lane, enc_status)
            if send_enc == True:
                self.send_status_queue.put((obsy, lane, enc_status), block=False)
        # if loud:
        #    plog("\n\nStatus Sent:  \n", status)
        # else:

        # NB should qualify acceptance and type '.' at that point.
        self.time_last_status = time.time()
        self.status_count += 1
        # breakpoint()

    def update(self):
        """
        This compact little function is the heart of the code in the sense this is repeatedly
        called. It first SENDS status for all devices to AWS, then it checks for any new
        commands from AWS. Then it calls sequencer.monitor() were jobs may get launched. A
        flaw here is we do not have a Ulid for the 'Job number'.

        Sequences that are self-dispatched primarily relate to biases, darks, screen and sky
        flats, opening and closing. Status for these jobs is reported via the normal
        sequencer status mechanism. Guard flags to prevent careless interrupts will be
        implemented as well as Cancel of a sequence if emitted by the Cancel botton on
        the AWS Sequence tab.

        Flat acquisition will include automatic rejection of any image that has a mean
        intensity > camera saturate. The camera will return without further processing and
        no image will be returned to AWS or stored locally. We should log the Unihedron and
        calc_illum values where filters first enter non-saturation. Once we know those values
        we can spend much less effort taking frames that are saturated. Save The Shutter!
        """

        self.update_status()

        if time.time() - self.get_new_job_timer > 3:
            self.get_new_job_timer = time.time()
            try:
                self.scan_requests(
                    "mount1"
                )  # NBNBNB THis has faulted, usually empty input lists.
            except:
                pass
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
        # Probably we don't want to run these checkes EVERY status update, just every 5 minutes
        check_time = self.config['check_time']
        if self.debug_flag:
            check_time *= 4
            self.time_since_safety_checks = time.time() + check_time
        if time.time() - self.time_since_safety_checks > check_time and not self.debug_flag:
            self.time_since_safety_checks = time.time()

            # breakpoint()

            # Check that the mount hasn't slewed too close to the sun
            sun_coords = get_sun(Time.now())
            temppointing = SkyCoord((g_dev['mnt'].current_icrs_ra)*u.hour,
                                    (g_dev['mnt'].current_icrs_dec)*u.degree, frame='icrs')

            sun_dist = sun_coords.separation(temppointing)
            #plog ("sun distance: " + str(sun_dist.degree))
            if sun_dist.degree < self.config['closest_distance_to_the_sun'] and not g_dev['mnt'].mount.AtPark:
                g_dev['obs'].send_to_user("Found telescope pointing too close to the sun: " +
                                          str(sun_dist.degree) + " degrees.")
                plog("Found telescope pointing too close to the sun: " + str(sun_dist.degree) + " degrees.")
                g_dev['obs'].send_to_user("Parking scope and cancelling all activity")
                plog("Parking scope and cancelling all activity")
                self.cancel_all_activity()
                if not g_dev['mnt'].mount.AtPark:
                    g_dev['mnt'].park_command()
                return

            # If the shutter is open, check it is meant to be.
            # This is just a brute force overriding safety check.
            # Opening and Shutting should be done more glamorously through the
            # sequencer, but if all else fails, this routine should save
            # the observatory from rain, wasps and acts of god.
            
            #try:
            #    plog("Roof Status: " + str(g_dev['enc'].status['shutter_status']))
            #except:
            #    plog("Wema is probably not working.")

            # Report on weather report status:
            #try:
            #    plog("Weather Report Acceptable to Open: " + str(g_dev['seq'].weather_report_is_acceptable_to_observe))
            #except:
            #    plog("Enc status not reporting, Wema may be OTL.")

            # Roof Checks only if not in Manual mode and not debug mode
            if g_dev['enc'].mode != 'Manual' or not self.debug_flag:
                if g_dev['enc'].status is not None:
                    if g_dev['enc'].status['shutter_status'] == 'Software Fault':
                        plog("Software Fault Detected. Will alert the authorities!")
                        plog("Parking Scope in the meantime")
                        if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            self.open_and_enabled_to_observe = False
                            # self.cancel_all_activity()   #NB THis kills bias-dark
                            if not g_dev['mnt'].mount.AtPark:
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()
                            # will send a Close call out into the blue just in case it catches
                            g_dev['enc'].enclosure.CloseShutter()
                            g_dev['seq'].enclosure_next_open_time = time.time(
                            ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening

                    if g_dev['enc'].status['shutter_status'] == 'Closing':
                        if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            plog(
                                "Detected Roof Closing. Sending another close command just in case the roof got stuck on this status (this happens!)")
                            self.open_and_enabled_to_observe = False
                            # self.cancel_all_activity()    #NB Kills bias dark
                            g_dev['enc'].enclosure.CloseShutter()
                            g_dev['seq'].enclosure_next_open_time = time.time(
                            ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening

                    if g_dev['enc'].status['shutter_status'] == 'Error':
                        if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            plog("Detected an Error in the Roof Status. Closing up for safety.")
                            plog("This is usually because the weather system forced the roof to shut.")
                            plog("By closing it again, it resets the switch to closed.")
                            # self.cancel_all_activity()    #NB Kills bias dark
                            self.open_and_enabled_to_observe = False
                            g_dev['enc'].enclosure.CloseShutter()
                            g_dev['seq'].enclosure_next_open_time = time.time(
                            ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
                            # while g_dev['enc'].enclosure.ShutterStatus == 3:
                            #plog ("closing")
                            plog("Also Parking the Scope")
                            if not g_dev['mnt'].mount.AtPark:
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()

                    roof_should_be_shut = False
                else:
                    plog("Enclosure roof status probably not reporting correctly. WEMA down?")
                try:
                    if g_dev['enc'].status['shutter_status'] == 'Closing':
                        if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            plog(
                                "Detected Roof Closing. Sending another close command just in case the roof got stuck on this status (this happens!)")
                            self.open_and_enabled_to_observe = False
                            # self.cancel_all_activity()    #NB Kills bias dark
                            g_dev['enc'].enclosure.CloseShutter()
                            g_dev['seq'].enclosure_next_open_time = time.time(
                            ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
    
                    if g_dev['enc'].status['shutter_status'] == 'Error':
                        if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            plog("Detected an Error in the Roof Status. Closing up for safety.")
                            plog("This is usually because the weather system forced the roof to shut.")
                            plog("By closing it again, it resets the switch to closed.")
                            # self.cancel_all_activity()    #NB Kills bias dark
                            self.open_and_enabled_to_observe = False
                            g_dev['enc'].enclosure.CloseShutter()
                            g_dev['seq'].enclosure_next_open_time = time.time(
                            ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
                            # while g_dev['enc'].enclosure.ShutterStatus == 3:
                            #plog ("closing")
                            plog("Also Parking the Scope")
                            if not g_dev['mnt'].mount.AtPark:
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()
                except:
                    plog("shutter status enclosure tests did not work. Usually shutter status is None")
                roof_should_be_shut = False

                # breakpoint()
                if (g_dev['events']['End Morn Sky Flats'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    roof_should_be_shut = True
                    self.open_and_enabled_to_observe = False
                if not self.config['auto_morn_sky_flat'] and self.config['only_scope_that_controls_the_roof']:
                    if (g_dev['events']['Observing Ends'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                        roof_should_be_shut = True
                        self.open_and_enabled_to_observe = False
                    if (g_dev['events']['Naut Dawn'] < ephem.now() < g_dev['events']['Morn Bias Dark']):
                        roof_should_be_shut = True
                        self.open_and_enabled_to_observe = False
                if not (g_dev['events']['Cool Down, Open'] < ephem.now() < g_dev['events']['Close and Park']):
                    roof_should_be_shut = True
                    self.open_and_enabled_to_observe = False

                try:
                    if g_dev['enc'].status['shutter_status'] == 'Open':
                        if roof_should_be_shut == True:
                            plog("Safety check found that the roof was open outside of the normal observing period")
                            if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                                plog("Shutting the roof out of an abundance of caution. This may also be normal functioning")

                                # self.cancel_all_activity()  #NB Kills bias dark
                                g_dev['enc'].enclosure.CloseShutter()
                                while g_dev['enc'].enclosure.ShutterStatus == 3:
                                    plog("closing")
                                    time.sleep(3)
                            else:
                                plog("This scope does not have control of the roof though.")
                except:
                    plog('Line 1192 Roof shutter status faulted.')

                # If the roof should be shut, then the telescope should be parked.
                if roof_should_be_shut == True and g_dev['enc'].mode == 'Automatic':
                    if not g_dev['mnt'].mount.AtPark:
                        plog('Parking telescope.')
                        self.open_and_enabled_to_observe = False
                        # self.cancel_all_activity()   #NB Kills bias dark
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        # PWI must receive a park() in order to report being parked.  Annoying problem when debugging, because I want tel to stay where it is.
                        g_dev['mnt'].park_command()
                if g_dev['enc'].status['shutter_status'] is not None:
                    # If the roof IS shut, then the telescope should be shutdown and parked.
                    if g_dev['enc'].status['shutter_status'] == 'Closed':

                        if not g_dev['mnt'].mount.AtPark:
                            plog("Telescope found not parked when the observatory roof is shut. Parking scope.")
                            self.open_and_enabled_to_observe = False
                            # self.cancel_all_activity()  #NB Kills bias dark
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()

                    # if g_dev['enc'].status['shutter_status'] == 'Open':
                    #     self.config['mount']'auto_morn_sky_flat': False,
                    #     if (g_dev['events']['Close and Park'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    #         plog ("Safety check found that it is in the period where the observatory should be closing up")
                    #         plog ("Checking on the dome being closed and the telescope at park.")
                    #         g_dev['enc'].enclosure.CloseShutter()
                    #         while g_dev['enc'].enclosure.ShutterStatus == 3:
                    #             plog ("closing")
                    #         if not g_dev['mnt'].mount.AtPark:
                    #             g_dev['mnt'].home_command()
                    #             g_dev['mnt'].park_command()

                    # But after all that if everything is ok, then all is ok, it is safe to observe
                    if g_dev['enc'].status['shutter_status'] == 'Open' and roof_should_be_shut == False:
                        self.open_and_enabled_to_observe = True
                else:
                    plog('Shutter status not reporting correctly')
            #plog("Current Open and Enabled to Observe Status: " + str(self.open_and_enabled_to_observe))

            # Check the mount is still connected
            g_dev['mnt'].check_connect()
            # if got here, mount is connected. NB Plumb in PW startup code

            # Check that the mount hasn't tracked too low or an odd slew hasn't sent it pointing to the ground.
            try:
                mount_altitude = g_dev['mnt'].mount.Altitude
                lowest_acceptable_altitude = self.config['mount']['mount1']['lowest_acceptable_altitude']
                if mount_altitude < lowest_acceptable_altitude:
                    plog("Altitude too low! " + str(mount_altitude) + ". Parking scope for safety!")
                    if not g_dev['mnt'].mount.AtPark:
                        # self.cancel_all_activity()  #NB Kills bias dark
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                        # Reset mount reference because thats how it probably got pointing at the dirt in the first place!
                        if self.config["mount"]["mount1"]["permissive_mount_reset"] == "yes":
                            g_dev["mnt"].reset_mount_reference()
            except Exception as e:
                plog(traceback.format_exc())
                plog(e)
                breakpoint()
                if 'GetAltAz' in str(e) and 'ASCOM.SoftwareBisque.Telescope' in str(e):
                    plog("The SkyX Altitude detection had an error.")
                    plog("Usually this is because of a broken connection.")
                    plog("Waiting 60 seconds then reconnecting")

                    time.sleep(60)

                    g_dev['mnt'].mount.Connected = True
                    # g_dev['mnt'].home_command()

            # If no activity for an hour, park the scope
            if time.time() - self.time_of_last_slew > self.config['mount']['mount1']['time_inactive_until_park'] and time.time() - self.time_of_last_exposure > self.config['mount']['mount1']['time_inactive_until_park']:
                if not g_dev['mnt'].mount.AtPark:
                    plog("Parking scope due to inactivity")
                    if g_dev['mnt'].home_before_park:
                        g_dev['mnt'].home_command()
                    g_dev['mnt'].park_command()
                self.time_of_last_slew = time.time()
                self.time_of_last_exposure = time.time()

            # Check that rotator is rotating
            if g_dev['rot'] != None:
                try:
                    g_dev['rot'].check_rotator_is_rotating() 
                except:
                    plog("occasionally rotator skips a beat when homing.")
                
            # Check that cooler is alive
            #plog ("Cooler check")
            #probe = g_dev['cam']._cooler_on()
            if g_dev['cam']._cooler_on():

                current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                current_camera_temperature = float(current_camera_temperature)   # NB NB Probably redundantWER
                #plog("Cooler is still on at " + str(current_camera_temperature))

                if current_camera_temperature - g_dev['cam'].setpoint > 1.5 or current_camera_temperature - g_dev['cam'].setpoint < -1.5:


                
                    #print (current_camera_temperature - g_dev['cam'].setpoint)

                    self.camera_temperature_in_range_for_calibrations = False
                    #plog("Temperature out of range to undertake calibrations")
                else:
                    self.camera_temperature_in_range_for_calibrations = True

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

                elif (float(current_camera_temperature) - g_dev['cam'].current_setpoint) > (2 * g_dev['cam'].day_warm_degrees):
                    plog("Found cooler on, but warm.")
                    plog("Keeping it slightly warm ( " + str(2 * g_dev['cam'].day_warm_degrees) +
                          " degrees warmer ) for about 20 minutes just in case the camera overheated.")
                    plog("Then will reset to normal.")
                    self.camera_overheat_safety_warm_on = True
                    self.camera_overheat_safety_timer = time.time()
                    #print (float(g_dev['cam'].setpoint +20.0))
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + (2 * g_dev['cam'].day_warm_degrees)))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()

            # breakpoint()
            if not self.camera_overheat_safety_warm_on:
                # Daytime temperature
                # if g_dev['cam'].day_warm and (g_dev['events']['End Morn Bias Dark'] + ephem.hour < ephem.now() < g_dev['events']['Eve Bias Dark'] - ephem.hour):

                # Daytime... a bit tricky! Two periods... just after biases but before nightly reset OR ... just before eve bias dark
                # As nightly reset resets the calendar
                if g_dev['cam'].day_warm and (ephem.now() < g_dev['events']['Eve Bias Dark'] - ephem.hour) or \
                        (g_dev['events']['End Morn Bias Dark'] + ephem.hour < ephem.now() < g_dev['events']['Nightly Reset']):
                    plog("In Daytime: Camera set at warmer temperature")
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint + g_dev['cam'].day_warm_degrees))
                    # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                    g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    # pass

                # Ramp heat temperature
                # Beginning after "End Morn Bias Dark" and taking an hour to ramp
                elif g_dev['cam'].day_warm and (g_dev['events']['End Morn Bias Dark'] < ephem.now() < g_dev['events']['End Morn Bias Dark'] + ephem.hour):
                    plog("In Camera Warming Ramping cycle of the day")
                    frac_through_warming = 1-((g_dev['events']['End Morn Bias Dark'] +
                                               ephem.hour) - ephem.now()) / ephem.hour
                    print("Fraction through warming cycle: " + str(frac_through_warming))
                    # if frac_through_warming > 0.8:
                    #     g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                    #     g_dev['cam']._set_cooler_on()
                    # else:
                    g_dev['cam']._set_setpoint(
                        float(g_dev['cam'].setpoint + (frac_through_warming) * g_dev['cam'].day_warm_degrees))
                    g_dev['cam']._set_cooler_on()
                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    # pass

                # Ramp cool temperature
                # Defined as beginning an hour before "Eve Bias Dark" to ramp to the setpoint.
                elif g_dev['cam'].day_warm and (g_dev['events']['Eve Bias Dark'] - ephem.hour < ephem.now() < g_dev['events']['Eve Bias Dark']):
                    plog("In Camera Cooling Ramping cycle of the day")
                    frac_through_warming = 1 - (((g_dev['events']['Eve Bias Dark']) - ephem.now()) / ephem.hour)
                    print("Fraction through cooling cycle: " + str(frac_through_warming))
                    if frac_through_warming > 0.8:
                        g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                        g_dev['cam']._set_cooler_on()
                    else:
                        g_dev['cam']._set_setpoint(
                            float(g_dev['cam'].setpoint + (1 - frac_through_warming) * g_dev['cam'].day_warm_degrees))
                        g_dev['cam']._set_cooler_on()

                    plog("Temp set to " + str(g_dev['cam'].current_setpoint))
                    # pass

                # Nighttime temperature
                elif (g_dev['events']['Eve Bias Dark'] < ephem.now() < g_dev['events']['End Morn Bias Dark']):
                    g_dev['cam']._set_setpoint(float(g_dev['cam'].setpoint))
                    g_dev['cam']._set_cooler_on()
                    # pass

            # breakpoint()

            # Check that the site is still connected to the net.
            if test_connect():
                self.time_of_last_live_net_connection = time.time()

            #plog("Last live connection to Google was " + str(time.time() -
            #                                                 self.time_of_last_live_net_connection) + " seconds ago.")
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
                    self.cancel_all_activity()
                    if not g_dev['mnt'].mount.AtPark:
                        plog("Parking scope due to inactivity")
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                        self.time_of_last_slew = time.time()

                    g_dev['enc'].enclosure.CloseShutter()
            #plog ("temporary reporting: MTF")
            if (g_dev['seq'].enclosure_next_open_time - time.time()) > 0:
                plog("opens this eve: " + str(g_dev['seq'].opens_this_evening))

                plog("minutes until next open attempt ALLOWED: " +
                     str((g_dev['seq'].enclosure_next_open_time - time.time()) / 60))

            # Report on when the observatory might close up if it intends to
            #if g_dev['seq'].weather_report_close_during_evening == True:
            #    plog("Observatory closing early in " +
            #         str((g_dev['seq'].weather_report_close_during_evening_time - ephem.now()) * 24) + " hours due to weather.")

            #if g_dev['seq'].weather_report_wait_until_open == True:
            #    plog("Observatory opening in " +
            #         str((g_dev['seq'].weather_report_wait_until_open_time - ephem.now()) * 24) + " hours due to poor weather.")

                # breakpoint()
                #plog ("Time Now")
                #plog (ephem.now())
                #plog ("Time Observatory Closing up Early")
                #plog (g_dev['seq'].weather_report_close_during_evening_time)
                #plog ("Difference in time")
                #plog (ephem.now() - g_dev['seq'].weather_report_close_during_evening_time)

        # END of safety checks.

    def run(self):  # run is a poor name for this function.
        try:
            # Keep the main thread alive, otherwise signals are ignored
            while True:
                self.update()
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            plog("Finishing loops and exiting...")
            self.stopped = True
            return

    # Note this is a thread!
    def send_to_aws(self):
        """Sends queued files to AWS.

        Large fpacked fits are uploaded using the ocs-ingester, which
        adds the image to a dedicated S3 bucket along with a record in
        the PTR archive database. All other files, including large fpacked
        fits if archive ingestion fails, will upload to a second S3 bucket.

        This is intended to transfer slower files not needed for UI responsiveness

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.aws_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.aws_queue.get(block=False)
                if pri_image is None:
                    plog("Got an empty entry in aws_queue.")
                    self.aws_queue.task_done()
                    one_at_a_time = 0
                    # time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk

                #  NB NB NB This looks like a redundant send
                tt = time.time()
                # aws_resp = g_dev["obs"].api.authenticated_request(
                #    "POST", "/upload/", {"object_name": filename})
                #plog('The setup phase took:  ', round(time.time() - tt, 1), ' sec.')

                # Only ingest new large fits.fz files to the PTR archive.
                #plog (self.env_exists)
                if filename.endswith("-EX00.fits.fz"):
                    with open(filepath, "rb") as fileobj:
                        #plog (frame_exists(fileobj))
                        tempPTR = 0
                        if self.env_exists == True and (not frame_exists(fileobj)):

                            #plog ("\nstarting ingester")
                            retryarchive = 0
                            while retryarchive < 10:
                                try:
                                    #tt = time.time()
                                    #plog ("attempting ingest to aws@  ", tt)
                                    upload_file_and_ingest_to_archive(fileobj)
                                    #plog ("did ingester")
                                    #plog(f"--> To PTR ARCHIVE --> {str(filepath)}")
                                    #plog('*.fz ingestion took:  ', round(time.time() - tt, 1), ' sec.')
                                    self.aws_queue.task_done()
                                    # os.remove(filepath)

                                    tempPTR = 1
                                    retryarchive = 11
                                except Exception as e:

                                    plog("couldn't send to PTR archive for some reason")
                                    plog("Retry " + str(retryarchive))
                                    plog(e)
                                    plog((traceback.format_exc()))
                                    time.sleep(pow(retryarchive, 2) + 1)
                                    if retryarchive < 10:
                                        retryarchive = retryarchive+1
                                    tempPTR = 0

                        # If ingester fails, send to default S3 bucket.
                        if tempPTR == 0:
                            files = {"file": (filepath, fileobj)}
                            try:
                                aws_resp = g_dev["obs"].api.authenticated_request(
                                    "POST", "/upload/", {"object_name": filename})
                                #reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                # break

                                #tt = time.time()
                               # plog("attempting aws@  ", tt)
                                req_resp = reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                #plog("did aws", req_resp)
                               # plog(f"--> To AWS --> {str(filepath)}")
                                #plog('*.fz transfer took:  ', round(time.time() - tt, 1), ' sec.')
                                self.aws_queue.task_done()
                                one_at_a_time = 0
                                # os.remove(filepath)

                                # break

                            except:
                                plog("Connection glitch for the request post, waiting a moment and trying again")
                                time.sleep(5)

                # Send all other files to S3.
                else:
                    with open(filepath, "rb") as fileobj:
                        files = {"file": (filepath, fileobj)}
                        try:
                            aws_resp = g_dev["obs"].api.authenticated_request(
                                "POST", "/upload/", {"object_name": filename})
                            reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                            # plog(resullll)
                            #plog(f"--> To AWS --> {str(filepath)}")
                            self.aws_queue.task_done()
                            # os.remove(filepath)

                            # break
                        except:
                            plog("Connection glitch for the request post, waiting a moment and trying again")
                            time.sleep(5)

                one_at_a_time = 0

                # Don't remove local calibrations after uploading but remove the others
                #print(filepath)
                if ('calibmasters' not in filepath):
                    try:
                        os.remove(filepath)
                    except:
                        plog("Couldn't remove " + str(filepath) + "file after transfer")
                        # pass

                # if (
                #     filename[-3:] == "jpg"
                #     or filename[-3:] == "txt"
                #     or ".fits.fz" in filename
                #     or ".token" in filename
                # ):
                #     try:
                #         os.remove(filepath)
                #     except:
                #         plog ("Couldn't remove " +str(filepath) + "file after transfer")
                #         pass

            else:
                time.sleep(0.5)

    def send_status_process(self):
        """A place to process non-process dependant images from the camera pile

        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if (not self.send_status_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pre_upload = time.time()
                received_status = self.send_status_queue.get(block=False)
                #plog ("****************")
                #plog (received_status)
                send_status(received_status[0], received_status[1], received_status[2])
                self.send_status_queue.task_done()
                upload_time = time.time() - pre_upload
                self.status_interval = 2 * upload_time
                if self.status_interval < 10:
                    self.status_interval = 10
                self.status_upload_time = upload_time
                #plog ("New status interval: " + str(self.status_interval))
                one_at_a_time = 0
            else:
                time.sleep(0.1)

    def mainjpeg_process(self):
        """This is the sep queue that happens in a different process
        than the main camera thread. SEPs can take 5-10, up to 30 seconds sometimes
        to run, so it is an overhead we can't have hanging around. This thread undertakes
        the SEP routine while the main camera thread is processing the jpeg image.
        The camera thread will wait for SEP to finish before moving on.         
        """

        # This stopping mechanism allows for threads to close cleanly.
        # one_at_a_time=0
        while True:
            if (not self.mainjpeg_queue.empty()):  # and one_at_a_time==0
                # one_at_a_time=1
                osc_jpeg_timer_start = time.time()
                (hdusmalldata, smartstackid, paths, pier_side) = self.mainjpeg_queue.get(block=False)

                # If this a bayer image, then we need to make an appropriate image that is monochrome
                # That gives the best chance of finding a focus AND for pointing while maintaining resolution.
                # This is best done by taking the two "real" g pixels and interpolating in-between
                # binfocus=1
                
                if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                    #plog ("interpolating bayer grid for focusing purposes.")
                    if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':
                        # Only separate colours if needed for colour jpeg
                        if smartstackid == 'no':
                            # # Checkerboard collapse for other colours for temporary jpeg
                            # # Create indexes for B, G, G, R images
                            # xshape = hdusmalldata.shape[0]
                            # yshape = hdusmalldata.shape[1]

                            # # B pixels
                            # #list_0_1 = np.array([ [0,0], [0,1] ])
                            # list_0_1 = np.asarray([[0, 0], [0, 1]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # hdublue = (block_reduce(hdusmalldata * checkerboard, 2))

                            # # R Pixels
                            # list_0_1 = np.asarray([[1, 0], [0, 0]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # hdured = (block_reduce(hdusmalldata * checkerboard, 2))

                            # # G top right Pixels
                            # list_0_1 = np.asarray([[0, 1], [0, 0]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # #GTRonly=(block_reduce(hdufocusdata * checkerboard ,2))
                            # hdugreen = (block_reduce(hdusmalldata * checkerboard, 2))

                            # # G bottom left Pixels
                            # #list_0_1 = np.asarray([ [0,0], [1,0] ])
                            # #checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # #GBLonly=(block_reduce(hdusmalldata * checkerboard ,2))

                            # # Sum two Gs together and half them to be vaguely on the same scale
                            # #hdugreen = np.array((GTRonly + GBLonly) / 2)
                            # #del GTRonly
                            # #del GBLonly

                            # del checkerboard
                            
                            hdured = hdusmalldata[::2, ::2]
                            hdugreen = hdusmalldata[::2, 1::2]
                            #g2 = hdusmalldata[1::2, ::2]
                            hdublue = hdusmalldata[1::2, 1::2]

                    else:
                        plog("this bayer grid not implemented yet")

                

                # This is holding the flash reduced fits file waiting to be saved
                # AFTER the jpeg has been sent up to AWS.
                #hdureduceddata = np.array(hdusmalldata)

                # Code to stretch the image to fit into the 256 levels of grey for a jpeg
                # But only if it isn't a smartstack, if so wait for the reduce queue
                if smartstackid == 'no':

                    if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                        xshape = hdugreen.shape[0]
                        yshape = hdugreen.shape[1]

                        # histogram matching

                        #plog (np.median(hdublue))
                        #plog (np.median(hdugreen))
                        #plog (np.median(hdured))

                        # breakpoint()
                        osc_timer=time.time()
                        # The integer mode of an image is typically the sky value, so squish anything below that
                        #bluemode = stats.mode((hdublue.astype('int16').flatten()), keepdims=True)[0] - 25
                        #redmode = stats.mode((hdured.astype('int16').flatten()), keepdims=True)[0] - 25
                        #greenmode = stats.mode((hdugreen.astype('int16').flatten()), keepdims=True)[0] - 25
                        #hdublue[hdublue < bluemode] = bluemode
                        #hdugreen[hdugreen < greenmode] = greenmode
                        #hdured[hdured < redmode] = redmode

                        # Then bring the background level up a little from there
                        # blueperc=np.nanpercentile(hdublue,0.75)
                        # greenperc=np.nanpercentile(hdugreen,0.75)
                        # redperc=np.nanpercentile(hdured,0.75)
                        # hdublue[hdublue < blueperc] = blueperc
                        # hdugreen[hdugreen < greenperc] = greenperc
                        # hdured[hdured < redperc] = redperc

                        #hdublue = hdublue * (np.median(hdugreen) / np.median(hdublue))
                        #hdured = hdured * (np.median(hdugreen) / np.median(hdured))

                        blue_stretched_data_float = Stretch().stretch(hdublue)*256
                        ceil = np.percentile(blue_stretched_data_float, 100)  # 5% of pixels will be white
                        # 5% of pixels will be black
                        floor = np.percentile(blue_stretched_data_float,
                                              self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut'])
                        #a = 255/(ceil-floor)
                        #b = floor*255/(floor-ceil)
                        blue_stretched_data_float[blue_stretched_data_float < floor] = floor
                        blue_stretched_data_float = blue_stretched_data_float-floor
                        blue_stretched_data_float = blue_stretched_data_float * (255/np.max(blue_stretched_data_float))

                        #blue_stretched_data_float = np.maximum(0,np.minimum(255,blue_stretched_data_float*a+b)).astype(np.uint8)
                        #blue_stretched_data_float[blue_stretched_data_float < floor] = floor
                        del hdublue

                        green_stretched_data_float = Stretch().stretch(hdugreen)*256
                        ceil = np.percentile(green_stretched_data_float, 100)  # 5% of pixels will be white
                        # 5% of pixels will be black
                        floor = np.percentile(green_stretched_data_float,
                                              self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut'])
                        #a = 255/(ceil-floor)
                        green_stretched_data_float[green_stretched_data_float < floor] = floor
                        green_stretched_data_float = green_stretched_data_float-floor
                        green_stretched_data_float = green_stretched_data_float * \
                            (255/np.max(green_stretched_data_float))

                        #b = floor*255/(floor-ceil)

                        #green_stretched_data_float[green_stretched_data_float < floor] = floor
                        #green_stretched_data_float = np.maximum(0,np.minimum(255,green_stretched_data_float*a+b)).astype(np.uint8)
                        del hdugreen

                        red_stretched_data_float = Stretch().stretch(hdured)*256
                        ceil = np.percentile(red_stretched_data_float, 100)  # 5% of pixels will be white
                        # 5% of pixels will be black
                        floor = np.percentile(red_stretched_data_float,
                                              self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut'])
                        #a = 255/(ceil-floor)
                        #b = floor*255/(floor-ceil)
                        # breakpoint()

                        red_stretched_data_float[red_stretched_data_float < floor] = floor
                        red_stretched_data_float = red_stretched_data_float-floor
                        red_stretched_data_float = red_stretched_data_float * (255/np.max(red_stretched_data_float))

                        #red_stretched_data_float[red_stretched_data_float < floor] = floor
                        #red_stretched_data_float = np.maximum(0,np.minimum(255,red_stretched_data_float*a+b)).astype(np.uint8)
                        del hdured

                       

                        rgbArray = np.empty((xshape, yshape, 3), 'uint8')
                        rgbArray[..., 0] = red_stretched_data_float  # *256
                        rgbArray[..., 1] = green_stretched_data_float  # *256
                        rgbArray[..., 2] = blue_stretched_data_float  # *256

                        del red_stretched_data_float
                        del blue_stretched_data_float
                        del green_stretched_data_float
                        colour_img = Image.fromarray(rgbArray, mode="RGB")

                        
                        
                        # adjust brightness
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'] != 1.0:
                            brightness = ImageEnhance.Brightness(colour_img)
                            brightness_image = brightness.enhance(
                                g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'])
                            del colour_img
                            del brightness
                        else:
                            brightness_image = colour_img
                            del colour_img

                        # adjust contrast
                        contrast = ImageEnhance.Contrast(brightness_image)
                        contrast_image = contrast.enhance(
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance'])
                        del brightness_image
                        del contrast

                        # adjust colour
                        colouradj = ImageEnhance.Color(contrast_image)
                        colour_image = colouradj.enhance(
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance'])
                        del contrast_image
                        del colouradj

                        # adjust saturation
                        satur = ImageEnhance.Color(colour_image)
                        satur_image = satur.enhance(g_dev['cam'].config["camera"]
                                                    [g_dev['cam'].name]["settings"]['osc_saturation_enhance'])
                        del colour_image
                        del satur

                        # adjust sharpness
                        sharpness = ImageEnhance.Sharpness(satur_image)
                        final_image = sharpness.enhance(
                            g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance'])
                        del satur_image
                        del sharpness

                        

                        # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                            final_image = final_image.transpose(Image.Transpose.TRANSPOSE)
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_180)
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_90)
                        if g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_270)

                        # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                        # to maintain the orientation. whether it is 1 or 0 that is flipped
                        # is sorta arbitrary... you'd use the site-config settings above to
                        # set it appropriately and leave this alone.
                        if pier_side == 1:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_180)


                        # if (
                        #     self.config["camera"][self.name]["settings"]["crop_preview"]
                        #     == True
                        # ):
                        #     yb = self.config["camera"][self.name]["settings"][
                        #         "crop_preview_ybottom"
                        #     ]
                        #     yt = self.config["camera"][self.name]["settings"][
                        #         "crop_preview_ytop"
                        #     ]
                        #     xl = self.config["camera"][self.name]["settings"][
                        #         "crop_preview_xleft"
                        #     ]
                        #     xr = self.config["camera"][self.name]["settings"][
                        #         "crop_preview_xright"
                        #     ]
                        #     hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]

                        # breakpoint()
                        # Save BIG version of JPEG.
                        final_image.save(
                            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
                        )

                        # Resizing the array to an appropriate shape for the small jpg
                        iy, ix = final_image.size
                        if (
                            self.config["camera"][g_dev['cam'].name]["settings"]["crop_preview"]
                            == True
                        ):
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
                            #hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]
                            final_image=final_image.crop((xl,yt,xr,yb))
                            iy, ix = final_image.size
                        
                        if iy == ix:
                            #final_image.resize((1280, 1280))
                            final_image = final_image.resize((900, 900))
                        else:
                            #final_image.resize((int(1536 * iy / ix), 1536))
                            if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                final_image = final_image.resize((int(900 * iy / ix), 900))
                            else:
                                final_image = final_image.resize((900, int(900 * iy / ix)))

                        final_image.save(
                            paths["im_path"] + paths["jpeg_name10"]
                        )
                        del final_image

                    else:
                        # Making cosmetic adjustments to the image array ready for jpg stretching
                        # breakpoint()

                        #hdusmalldata = np.asarray(hdusmalldata)

                        # breakpoint()
                        # hdusmalldata[
                        #     hdusmalldata
                        #     > image_saturation_level
                        # ] = image_saturation_level
                        # #hdusmalldata[hdusmalldata < -100] = -100
                        hdusmalldata = hdusmalldata - np.min(hdusmalldata)

                        stretched_data_float = Stretch().stretch(hdusmalldata+1000)
                        stretched_256 = 255 * stretched_data_float
                        hot = np.where(stretched_256 > 255)
                        cold = np.where(stretched_256 < 0)
                        stretched_256[hot] = 255
                        stretched_256[cold] = 0
                        stretched_data_uint8 = stretched_256.astype("uint8")
                        hot = np.where(stretched_data_uint8 > 255)
                        cold = np.where(stretched_data_uint8 < 0)
                        stretched_data_uint8[hot] = 255
                        stretched_data_uint8[cold] = 0

                        iy, ix = stretched_data_uint8.shape
                        #stretched_data_uint8 = Image.fromarray(stretched_data_uint8)
                        final_image = Image.fromarray(stretched_data_uint8)
                        # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                        if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                            final_image = final_image.transpose(Image.TRANSPOSE)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                            final_image = final_image.transpose(Image.FLIP_LEFT_RIGHT)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                            final_image = final_image.transpose(Image.FLIP_TOP_BOTTOM)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                            final_image = final_image.transpose(Image.ROTATE_180)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                            final_image = final_image.transpose(Image.ROTATE_90)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                            final_image = final_image.transpose(Image.ROTATE_270)

                        # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                        # to maintain the orientation. whether it is 1 or 0 that is flipped
                        # is sorta arbitrary... you'd use the site-config settings above to
                        # set it appropriately and leave this alone.
                        if pier_side == 1:
                            final_image = final_image.transpose(Image.ROTATE_180)

                        # Save BIG version of JPEG.
                        final_image.save(
                            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
                        )

                        # Resizing the array to an appropriate shape for the jpg and the small fits

                        if iy == ix:
                            # hdusmalldata = resize(
                            #     hdusmalldata, (1280, 1280), preserve_range=True
                            # )
                            final_image = final_image.resize(
                                (900, 900)
                            )
                        else:
                            # stretched_data_uint8 = resize(
                            #     stretched_data_uint8,
                            #     (int(1536 * iy / ix), 1536),
                            #     preserve_range=True,
                            # )
                            # stretched_data_uint8 = resize(
                            #     stretched_data_uint8,
                            #     (int(900 * iy / ix), 900),
                            #     preserve_range=True,
                            # )
                            if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                final_image = final_image.resize(

                                    (int(900 * iy / ix), 900)

                                )
                            else:
                                final_image = final_image.resize(

                                    (900, int(900 * iy / ix))

                                )
                        # stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
                        final_image.save(
                            paths["im_path"] + paths["jpeg_name10"]
                        )
                        del final_image

                del hdusmalldata

                # Try saving the jpeg to disk and quickly send up to AWS to present for the user
                # GUI
                if smartstackid == 'no':
                    try:

                        # if not no_AWS:
                        g_dev["cam"].enqueue_for_fastAWS(
                            100, paths["im_path"], paths["jpeg_name10"]
                        )
                        g_dev["cam"].enqueue_for_fastAWS(
                            1000, paths["im_path"], paths["jpeg_name10"].replace('EX10', 'EX20')
                        )
                        # g_dev["obs"].send_to_user(
                        #    "A preview image of the single image has been sent to the GUI.",
                        #    p_level="INFO",
                        # )
                    except:
                        plog(
                            "there was an issue saving the preview jpg. Pushing on though"
                        )

                    plog("JPEG constructed and sent: " +str(time.time() - osc_jpeg_timer_start)+ "s")
                self.mainjpeg_queue.task_done()
                # one_at_a_time=0
            else:
                time.sleep(0.1)

    def sep_process(self):
        """This is the sep queue that happens in a different process
        than the main camera thread. SEPs can take 5-10, up to 30 seconds sometimes
        to run, so it is an overhead we can't have hanging around.       
        """

        # This stopping mechanism allows for threads to close cleanly.
        one_at_a_time = 0
        while True:
            if (not self.sep_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                #print ("In the queue.....")

                sep_timer_begin=time.time()
                
                (hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position) = self.sep_queue.get(block=False)
                
                #breakpoint()
                # Background clip the focus image
                ## Estimate Method 1: This routine tests the number of pixels to the negative side of the distribution until it hits 0 three pixels in a row. This (+3) becomes the lower threshold.
                imageMode = (float(stats.mode(hdufocusdata.flatten(), nan_policy='omit', keepdims=False)[0]))
                
                breaker=1
                counter=0
                zerocount=0
                while (breaker != 0):
                    counter=counter+1
                    currentValue= np.count_nonzero(hdufocusdata == imageMode-counter)
            
                    if (currentValue < 20):
                        zerocount=zerocount+1
                    else:
                        zerocount=0
                    if (zerocount == 3):
                        zeroValue=(imageMode-counter)+3
                        breaker =0
                        
                masker = ma.masked_less(hdufocusdata, (zeroValue))
                hdufocusdata= masker.filled(imageMode)
                #print ("Minimum Value in Array")
                #print (zeroValue)
    
                # Report number of nans in array
                #print ("Number of nan pixels in image array: " + str(numpy.count_nonzero(numpy.isnan(imagedata))))
                
                
                # Background clipped
                hduheader["IMGMIN"] = ( np.nanmin(hdufocusdata), "Minimum Value of Image Array" )
                hduheader["IMGMAX"] = ( np.nanmax(hdufocusdata), "Maximum Value of Image Array" )
                hduheader["IMGMEAN"] = ( np.nanmean(hdufocusdata), "Mean Value of Image Array" )
                hduheader["IMGMED"] = ( np.nanmedian(hdufocusdata), "Median Value of Image Array" )
                
                hduheader["IMGMODE"] = ( imageMode, "Mode Value of Image Array" )
                hduheader["IMGSTDEV"] = ( np.nanstd(hdufocusdata), "Median Value of Image Array" )
                hduheader["IMGMAD"] = ( median_absolute_deviation(hdufocusdata, ignore_nan=True), "Median Absolute Deviation of Image Array" )
                
                
                
                # Get out raw histogram construction data
                # Get a flattened array with all nans removed
                int_array_flattened=np.rint(hdufocusdata.flatten())
                flat_no_nan_array=(int_array_flattened[~np.isnan(int_array_flattened)])
                del int_array_flattened
                # Collect unique values and counts
                unique,counts=np.unique(flat_no_nan_array, return_counts=True)
                del flat_no_nan_array
                histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                np.savetxt(
                    im_path + text_name.replace('.txt', '.his'),
                    histogramdata, delimiter=','
                )
                
                
                try:
                    g_dev['cam'].enqueue_for_fastAWS(180, im_path, text_name.replace('.txt', '.his'))
                    #plog("Sent SEP up")
                except:
                    plog("Failed to send HIS up for some reason")
                
                
                
                
                
                
                
                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']) :
                    plog ("Too bright to consider photometry!")


                    rfp = np.nan
                    rfr = np.nan
                    rfs = np.nan
                    sepsky = np.nan
                else:

                    if frame_type == 'focus':
                        focus_crop_width = self.config["camera"][g_dev['cam']
                                                                 .name]["settings"]['focus_image_crop_width']
                        focus_crop_height = self.config["camera"][g_dev['cam']
                                                                  .name]["settings"]['focus_image_crop_height']
                        # breakpoint()

                        fx, fy = hdufocusdata.shape

                        crop_width = (fx * focus_crop_width) / 2
                        crop_height = (fy * focus_crop_height) / 2

                        # Make sure it is an even number for OSCs
                        if (crop_width % 2) != 0:
                            crop_width = crop_width+1
                        if (crop_height % 2) != 0:
                            crop_height = crop_height+1

                        crop_width = int(crop_width)
                        crop_height = int(crop_height)
                        # breakpoint()

                        if crop_width > 0 or crop_height > 0:
                            hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]
                            #plog("Focus image cropped to " + str(hdufocusdata.shape))

                    # focdate=time.time()
                    binfocus = 1
                    if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:

                        if frame_type == 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['interpolate_for_focus']:
                            hdufocusdata=demosaicing_CFA_Bayer_Menon2007(hdufocusdata, 'RGGB')[:,:,1]
                            hdufocusdata=hdufocusdata.astype("float32")
                            binfocus=1
                        if frame_type == 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_focus']: 
                            focus_bin_factor=self.config["camera"][g_dev['cam'].name]["settings"]['focus_bin_value']
                            hdufocusdata=block_reduce(hdufocusdata,focus_bin_factor)
                            binfocus=focus_bin_factor
                        
                        
                        if frame_type != 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['interpolate_for_sep']: 
                            hdufocusdata=demosaicing_CFA_Bayer_Menon2007(hdufocusdata, 'RGGB')[:,:,1]
                            hdufocusdata=hdufocusdata.astype("float32")
                            binfocus=1
                        if frame_type != 'focus' and self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_sep']:
                            sep_bin_factor=self.config["camera"][g_dev['cam'].name]["settings"]['sep_bin_value']
                            hdufocusdata=block_reduce(hdufocusdata,sep_bin_factor)
                            binfocus=sep_bin_factor
                            

                    # If it is a focus image then it will get sent in a different manner to the UI for a jpeg
                    if frame_type == 'focus':

                        hdusmalldata = np.array(hdufocusdata)

                        fx, fy = hdusmalldata.shape

                        focus_jpeg_size=self.config["camera"][g_dev['cam'].name]["settings"]['focus_jpeg_size']
                        crop_width = (fx - focus_jpeg_size) / 2
                        crop_height = (fy - focus_jpeg_size) / 2

       

                        # Make sure it is an even number for OSCs
                        if (crop_width % 2) != 0:
                            crop_width = crop_width+1
                        if (crop_height % 2) != 0:
                            crop_height = crop_height+1

                        crop_width = int(crop_width)
                        crop_height = int(crop_height)
                        # breakpoint()

                        if crop_width > 0 or crop_height > 0:
                            hdusmalldata = hdusmalldata[crop_width:-crop_width, crop_height:-crop_height]

                        hdusmalldata = hdusmalldata - np.min(hdusmalldata)

                        stretched_data_float = Stretch().stretch(hdusmalldata+1000)
                        stretched_256 = 255 * stretched_data_float
                        hot = np.where(stretched_256 > 255)
                        cold = np.where(stretched_256 < 0)
                        stretched_256[hot] = 255
                        stretched_256[cold] = 0
                        stretched_data_uint8 = stretched_256.astype("uint8")
                        hot = np.where(stretched_data_uint8 > 255)
                        cold = np.where(stretched_data_uint8 < 0)
                        stretched_data_uint8[hot] = 255
                        stretched_data_uint8[cold] = 0

                        iy, ix = stretched_data_uint8.shape
                        #stretched_data_uint8 = Image.fromarray(stretched_data_uint8)
                        final_image = Image.fromarray(stretched_data_uint8)
                        # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                        # if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                        #     final_image=final_image.transpose(Image.TRANSPOSE)
                        # if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                        #     final_image=final_image.transpose(Image.FLIP_LEFT_RIGHT)
                        # if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                        #     final_image=final_image.transpose(Image.FLIP_TOP_BOTTOM)
                        # if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                        #     final_image=final_image.transpose(Image.ROTATE_180)
                        # if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                        #     final_image=final_image.transpose(Image.ROTATE_90)
                        # if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                        #     final_image=final_image.transpose(Image.ROTATE_270)

                        #plog ("Focus image cropped to " + str(hdufocusdata.shape))

                        #
                        # stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
                        draw = ImageDraw.Draw(final_image)
                        # breakpoint()
                        #font=ImageFont.truetype("C:\Windows\Fonts\sans-serif.ttf", 16)

                        draw.text((0, 0), str(focus_position), (255))

                        #draw.text((0, 0),str(focus_position),(255,255,255),font=font)

                        final_image.save(im_path + text_name.replace('EX00.txt', 'EX10.jpg'))

                        g_dev["cam"].enqueue_for_fastAWS(100, im_path, text_name.replace('EX00.txt', 'EX10.jpg'))

                    #plog("focus construction time")
                    #plog(time.time() -focdate)

                    actseptime = time.time()
                    focusimg = np.array(
                        hdufocusdata, order="C"
                    )

                    try:
                        # Some of these are liberated from BANZAI
                        bkg = sep.Background(focusimg)

                        sepsky = (np.nanmedian(bkg), "Sky background estimated by SEP")

                        focusimg -= bkg
                        ix, iy = focusimg.shape
                        border_x = int(ix * 0.05)
                        border_y = int(iy * 0.05)
                        sep.set_extract_pixstack(int(ix*iy - 1))
                        # minarea is set as roughly how big we think a 0.7 arcsecond seeing star
                        # would be at this pixelscale and binning. Different for different cameras/telescopes.
                        #minarea = int(pow(0.7*1.5 / (pixscale*binfocus), 2) * 3.14)
                        
                        
                        #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
                        # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
                        # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
                        minarea= -9.2421 * pixscale + 16.553
                        if minarea < 5:  # There has to be a min minarea though!
                            minarea = 5

                        #sep.set_sub_object_limit(10000)
                        sources = sep.extract(
                            focusimg, 5.0, err=bkg.globalrms, minarea=minarea
                        )
                        #plog("Actual SEP time: " + str(time.time()-actseptime))

                        #plog ("min_area: " + str(minarea))
                        sources = Table(sources)
                        sources = sources[sources['flag'] < 8]
                        image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                        sources = sources[sources["peak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
                        sources = sources[sources["cpeak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
                        #sources = sources[sources["peak"] > 150 * pow(binfocus,2)]
                        #sources = sources[sources["cpeak"] > 150 * pow(binfocus,2)]
                        sources = sources[sources["flux"] > 2000]
                        sources = sources[sources["x"] < ix - border_x]
                        sources = sources[sources["x"] > border_x]
                        sources = sources[sources["y"] < iy - border_y]
                        sources = sources[sources["y"] > border_y]

                        # BANZAI prune nans from table
                        nan_in_row = np.zeros(len(sources), dtype=bool)
                        for col in sources.colnames:
                            nan_in_row |= np.isnan(sources[col])
                        sources = sources[~nan_in_row]

                        # Calculate the ellipticity (Thanks BANZAI)
                        sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])

                        sources = sources[sources['ellipticity'] < 0.1]  # Remove things that are not circular stars

                        # Calculate the kron radius (Thanks BANZAI)
                        kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
                                                          sources['a'], sources['b'],
                                                          sources['theta'], 6.0)
                        sources['flag'] |= krflag
                        sources['kronrad'] = kronrad

                        # Calculate uncertainty of image (thanks BANZAI)
                        #uncertainty = float(readnoise) * np.ones(hdufocusdata.shape,
                        #                                         dtype=hdufocusdata.dtype) / float(readnoise)

                        uncertainty = float(readnoise) * np.ones(focusimg.shape,
                                                                 dtype=focusimg.dtype) / float(readnoise)


                        # DONUT IMAGE DETECTOR.
                        #plog ("The Fitzgerald Magical Donut detector")
                        
                        xdonut=np.median(pow(pow(sources['x'] - sources['xpeak'],2),0.5))*pixscale*binfocus
                        ydonut=np.median(pow(pow(sources['y'] - sources['ypeak'],2),0.5))*pixscale*binfocus
                        if xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut):
                            plog ("Possible donut image detected.")    
                            plog('x ' + str(xdonut))
                            plog('y ' + str(ydonut))                        
                        #breakpoint()

                        # Calcuate the equivilent of flux_auto (Thanks BANZAI)
                        # This is the preferred best photometry SEP can do.
                        try:
                            flux, fluxerr, flag = sep.sum_ellipse(focusimg, sources['x'], sources['y'],
                                                              sources['a'], sources['b'],
                                                              np.pi / 2.0, 2.5 * kronrad,
                                                              subpix=1, err=uncertainty)
                        except:
                            plog(traceback.format_exc())
                            
                        sources['flux'] = flux
                        sources['fluxerr'] = fluxerr
                        sources['flag'] |= flag
                        sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
                                                             subpix=5)
                        # If image has been binned for focus we need to multiply some of these things by the binning
                        # To represent the original image
                        sources['FWHM'] = (sources['FWHM'] * 2) * binfocus
                        sources['x'] = (sources['x']) * binfocus
                        sources['y'] = (sources['y']) * binfocus

                        #

                        sources['a'] = (sources['a']) * binfocus
                        sources['b'] = (sources['b']) * binfocus
                        sources['kronrad'] = (sources['kronrad']) * binfocus
                        sources['peak'] = (sources['peak']) / pow(binfocus, 2)
                        sources['cpeak'] = (sources['cpeak']) / pow(binfocus, 2)




                        # Need to reject any stars that have FWHM that are less than a extremely
                        # perfect night as artifacts
                        sources = sources[sources['FWHM'] > (0.6 / (pixscale))]
                        sources = sources[sources['FWHM'] > (self.config['minimum_realistic_seeing'] / pixscale)]
                        sources = sources[sources['FWHM'] != 0]

                        # BANZAI prune nans from table
                        nan_in_row = np.zeros(len(sources), dtype=bool)
                        for col in sources.colnames:
                            nan_in_row |= np.isnan(sources[col])
                        sources = sources[~nan_in_row]

                        #plog("No. of detections:  ", len(sources))

                            

                        if (len(sources) < 2) or ( frame_type == 'focus' and (len(sources) < 10 or len(sources) == np.nan or str(len(sources)) =='nan' or xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut))):
                            #plog ("not enough sources to estimate a reliable focus")
                            plog ("Did not find an acceptable FWHM for this image.")    
                            g_dev['cam'].expresult["error"] = True
                            g_dev['cam'].expresult['FWHM'] = np.nan
                            g_dev['cam'].expresult['No_of_sources'] = np.nan
                            sources['FWHM'] = [np.nan] * len(sources)
                            rfp = np.nan
                            rfr = np.nan
                            rfs = np.nan
                            sources = sources

                        else:
                            # Get halflight radii
                            # breakpoint()
                            # fwhmcalc=(np.array(sources['FWHM']))
                            fwhmcalc = sources['FWHM']
                            #fwhmcalc=fwhmcalc[fwhmcalc > 1.0]
                            fwhmcalc = fwhmcalc[fwhmcalc != 0]  # Remove 0 entries
                            # fwhmcalc=fwhmcalc[fwhmcalc < 75] # remove stupidly large entries

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
                            rfr = round(np.median(fwhmcalc) * pixscale, 3)
                            rfs = round(np.std(fwhmcalc) * pixscale, 3)
                            plog("\nImage FWHM:  " + str(rfr) + "+/-" + str(rfs) + " arcsecs, " + str(rfp)
                                 + " pixels.")
                            # breakpoint()
                            g_dev['cam'].expresult["FWHM"] = rfr
                            g_dev['cam'].expresult["mean_focus"] = avg_foc
                            g_dev['cam'].expresult['No_of_sources'] = len(sources)

                            # rfp = rfp
                            # g_dev['cam'].rfr = rfr
                            # g_dev['cam'].rfs = rfs
                            # g_dev['cam'].sources = sources

                            # try:
                            #     valid = (
                            #         0.0 <= result["FWHM"] <= 20.0
                            #         and 100 < result["mean_focus"] < 12600
                            #     )
                            #     result["error"] = False

                            # except:
                            #     result[
                            #         "error"

                            #     ] = True
                            #     result["FWHM"] = np.nan
                            #     result["mean_focus"] = np.nan

                            if focus_image != True:
                                # Focus tracker code. This keeps track of the focus and if it drifts
                                # Then it triggers an autofocus.
                                g_dev["foc"].focus_tracker.pop(0)
                                g_dev["foc"].focus_tracker.append(round(rfr, 3))
                                plog("Last ten FWHM: " + str(g_dev["foc"].focus_tracker) + " Median: " + str(np.nanmedian(g_dev["foc"].focus_tracker)) + " Last Solved: " + "Last solved focus FWHM: " + str(g_dev["foc"].last_focus_fwhm))
                                #plog()
                                #plog("Median last ten FWHM")
                                #plog(np.nanmedian(g_dev["foc"].focus_tracker))
                                #plog("Last solved focus FWHM: " + str(g_dev["foc"].last_focus_fwhm))
                                #plog(g_dev["foc"].last_focus_fwhm)

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
                                            + ". Autofocus triggered for next exposures.",
                                            p_level="INFO",
                                        )

                        source_delete = ['thresh', 'npix', 'tnpix', 'xmin', 'xmax', 'ymin', 'ymax', 'x2', 'y2', 'xy', 'errx2',
                                         'erry2', 'errxy', 'a', 'b', 'theta', 'cxx', 'cyy', 'cxy', 'cflux', 'cpeak', 'xcpeak', 'ycpeak']
                        # for sourcedel in source_delete:
                        #    breakpoint()
                        sources.remove_columns(source_delete)

                        sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)

                        try:
                            g_dev['cam'].enqueue_for_fastAWS(200, im_path, text_name.replace('.txt', '.sep'))
                            #plog("Sent SEP up")
                        except:
                            plog("Failed to send SEP up for some reason")

                            
                        
                        # # Identify the brightest star in the image set
                        
                        # # Make a cutout around this star - 10 times rfp
                        
                        # brightest_array = None
                        
                        # # Send this array up
                        
                        
                        
                        
                        # # Identify the brightest non-saturated star in the image set
                        
                        # # Make a cutout around this star - 10 times rfp
                        
                        # unsaturated_array = None
                        
                        # # Send this array up
                        # #import json
                        # data = {'brightest': brightest_array, 'unsaturated': unsaturated_array}
                        # # To write to a file:
                        # with open(im_path + text_name.replace('.txt', '.rad'), "w") as f:
                        #     json.dump(data, f)
                        
                        
                        # try:
                        #     g_dev['cam'].enqueue_for_fastAWS(2000, im_path, text_name.replace('.txt', '.rad'))
                        #     #plog("Sent SEP up")
                        # except:
                        #     plog("Failed to send RAD up for some reason")
                        
                        # To print out the JSON string (which you could then hardcode into the JS)
                        #json.dumps(data)
                        

                    except:
                        plog("something failed in SEP calculations for exposure. This could be an overexposed image")
                        plog(traceback.format_exc())
                        sources = [0]
                        rfp = np.nan
                        rfr = np.nan
                        rfs = np.nan
                        sepsky = np.nan

                    #plog("Sep time to process: " + str(time.time() - sep_timer_begin))

                
                
                # Value-added header items for the UI 
                

                try:
                    #hduheader["SEPSKY"] = str(sepsky)
                    hduheader["SEPSKY"] = sepsky
                except:
                    hduheader["SEPSKY"] = -9999
                try:
                    hduheader["FWHM"] = (str(rfp), 'FWHM in pixels')
                    hduheader["FWHMpix"] = (str(rfp), 'FWHM in pixels')
                except:
                    hduheader["FWHM"] = (-99, 'FWHM in pixels')
                    hduheader["FWHMpix"] = (-99, 'FWHM in pixels')

                try:
                    hduheader["FWHMasec"] = (str(rfr), 'FWHM in arcseconds')
                except:
                    hduheader["FWHMasec"] = (-99, 'FWHM in arcseconds')
                try:
                    hduheader["FWHMstd"] = (str(rfs), 'FWHM standard deviation in arcseconds')
                except:

                    hduheader["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')

                try:
                    hduheader["NSTARS"] = ( len(sources), 'Number of star-like sources in image')
                except:
                    hduheader["NSTARS"] = ( -99, 'Number of star-like sources in image')
                



                # if focus_image == False:
                text = open(
                    im_path + text_name, "w"
                )  # This is needed by AWS to set up database.
                #breakpoint()
                text.write(str(hduheader))
                text.close()
                g_dev['cam'].enqueue_for_fastAWS(10, im_path, text_name)

                if self.config['keep_focus_images_on_disk']:
                    # hdufocus=fits.PrimaryHDU()
                    # hdufocus.data=g_dev['cam'].hdufocusdatahold
                    # hdufocus.header=hdu.header
                    # hdufocus.header["NAXIS1"] = g_dev['cam'].hdufocusdatahold.shape[0]
                    # hdufocus.header["NAXIS2"] = g_dev['cam'].hdufocusdatahold.shape[1]
                    # hdufocus.writeto(cal_path + cal_name, overwrite=True, output_verify='silentfix')
                    # pixscale=hdufocus.header['PIXSCALE']

                    g_dev['cam'].to_slow_process(1000, ('focus', cal_path + cal_name, hdufocusdata, hduheader,
                                                        frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    if self.config["save_to_alt_path"] == "yes":
                        g_dev['cam'].to_slow_process(1000, ('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocusdata, hduheader,
                                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    # try:
                    #     g_dev['cam'].hdufocusdatahold.close()
                    # except:
                    #     pass
                    # del g_dev['cam'].hdufocusdatahold
                    # del hdufocus

                g_dev['cam'].sep_processing = False
                self.sep_queue.task_done()
                one_at_a_time = 0

            else:
                time.sleep(0.1)

    def platesolve_process(self):
        """This is the platesolve queue that happens in a different process
        than the main camera thread. Platesolves can take 5-10, up to 30 seconds sometimes
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
                psolve_timer_begin = time.time()
                (hdufocusdata, hduheader, cal_path, cal_name, frame_type, time_platesolve_requested,
                 pixscale, pointing_ra, pointing_dec) = self.platesolve_queue.get(block=False)

                # Do not bother platesolving unless it is dark enough!!
                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                    plog("Too bright to consider platesolving!")
                else:
                    # focdate=time.time()

                    # Crop the image for platesolving
                    platesolve_crop = self.config["camera"][g_dev['cam'].name]["settings"]['platesolve_image_crop']
                    # breakpoint()

                    fx, fy = hdufocusdata.shape

                    crop_width = (fx * platesolve_crop) / 2
                    crop_height = (fy * platesolve_crop) / 2

                    # Make sure it is an even number for OSCs
                    if (crop_width % 2) != 0:
                        crop_width = crop_width+1
                    if (crop_height % 2) != 0:
                        crop_height = crop_height+1

                    crop_width = int(crop_width)
                    crop_height = int(crop_height)

                    # breakpoint()
                    if crop_width > 0 or crop_height > 0:
                        hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]
                    #plog("Platesolve image cropped to " + str(hdufocusdata.shape))

                    binfocus = 1
                    #if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                    if self.config["camera"][g_dev['cam'].name]["settings"]['bin_for_platesolve']:
                        platesolve_bin_factor=self.config["camera"][g_dev['cam'].name]["settings"]['platesolve_bin_value']
                        hdufocusdata=block_reduce(hdufocusdata,platesolve_bin_factor)
                        binfocus=platesolve_bin_factor                    

                    #plog("platesolve construction time")
                    #plog(time.time() -focdate)

                    # actseptime=time.time()
                    focusimg = np.array(
                        hdufocusdata, order="C"
                    )

                    try:
                        # Some of these are liberated from BANZAI
                        bkg = sep.Background(focusimg)

                        #sepsky = ( np.nanmedian(bkg), "Sky background estimated by SEP" )

                        focusimg -= bkg
                        ix, iy = focusimg.shape
                        border_x = int(ix * 0.05)
                        border_y = int(iy * 0.05)
                        sep.set_extract_pixstack(int(ix*iy - 1))
                        #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
                        # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
                        # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
                        minarea= -9.2421 * pixscale + 16.553
                        if minarea < 5:  # There has to be a min minarea though!
                            minarea = 5

                        sources = sep.extract(
                            focusimg, 5.0, err=bkg.globalrms, minarea=minarea
                        )
                        #plog ("min_area: " + str(minarea))
                        sources = Table(sources)
                        sources = sources[sources['flag'] < 8]
                        image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                        sources = sources[sources["peak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
                        sources = sources[sources["cpeak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
                        #sources = sources[sources["peak"] > 150 * pow(binfocus,2)]
                        #sources = sources[sources["cpeak"] > 150 * pow(binfocus,2)]
                        sources = sources[sources["flux"] > 2000]
                        sources = sources[sources["x"] < ix - border_x]
                        sources = sources[sources["x"] > border_x]
                        sources = sources[sources["y"] < iy - border_y]
                        sources = sources[sources["y"] > border_y]

                        # BANZAI prune nans from table
                        nan_in_row = np.zeros(len(sources), dtype=bool)
                        for col in sources.colnames:
                            nan_in_row |= np.isnan(sources[col])
                        sources = sources[~nan_in_row]
                        #plog("Actual Platesolve SEP time: " + str(time.time()-actseptime))
                    except:
                        plog("Something went wrong with platesolve SEP")

                    # # Fast checking of the NUMBER of sources
                    # # No reason to run a computationally intensive
                    # # SEP routine for that, just photutils will do.
                    # psource_timer_begin=time.time()
                    # plog ("quick image stats from photutils")
                    # tempmean, tempmedian, tempstd = sigma_clipped_stats(hdufocusdata, sigma=3.0)
                    # plog((tempmean, tempmedian, tempstd))
                    # #daofind = DAOStarFinder(fwhm=(2.2 / pixscale), threshold=5.*tempstd)  #estimate fwhm in pixels by reasonable focus level.

                    # if g_dev['foc'].last_focus_fwhm == None:
                    #     tempfwhm=2.2/(pixscale*binfocus)
                    # else:
                    #     tempfwhm=g_dev['foc'].last_focus_fwhm/(pixscale*binfocus)
                    # daofind = DAOStarFinder(fwhm=tempfwhm , threshold=5.*tempstd)

                    # plog ("Used fwhm is " + str(tempfwhm) + " pixels")
                    # sources = daofind(hdufocusdata - tempmedian)
                    # plog (sources)
                    # plog("Photutils time to process: " + str(time.time() -psource_timer_begin ))

                    # We only need to save the focus image immediately if there is enough sources to
                    #  rationalise that.  It only needs to be on the disk immediately now if platesolve
                    #  is going to attempt to pick it up.  Otherwise it goes to the slow queue.
                    # Also, too many sources and it will take an unuseful amount of time to solve
                    # Too many sources mean a globular or a crowded field where we aren't going to be
                    # able to solve too well easily OR it is such a wide field of view that who cares
                    # if we are off by 10 arcseconds?
                    plog("Number of sources for Platesolve: " + str(len(sources)))

                    if len(sources) >= 15:
                        hdufocus = fits.PrimaryHDU()
                        hdufocus.data = hdufocusdata
                        hdufocus.header = hduheader
                        hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
                        hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
                        hdufocus.writeto(cal_path + 'platesolvetemp.fits', overwrite=True, output_verify='silentfix')
                        pixscale = hdufocus.header['PIXSCALE']
                        # if self.config["save_to_alt_path"] == "yes":
                        #    self.to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocus.data, hdufocus.header, \
                        #                                   frame_type))

                        try:
                            hdufocus.close()
                        except:
                            pass
                        del hdufocusdata
                        del hdufocus

                        # Test here that there has not been a slew, if there has been a slew, cancel out!
                        if self.time_of_last_slew > time_platesolve_requested:
                            plog("detected a slew since beginning platesolve... bailing out of platesolve.")
                            # if not self.config['keep_focus_images_on_disk']:
                            #    os.remove(cal_path + cal_name)
                            #one_at_a_time = 0
                            # self.platesolve_queue.task_done()
                            # break
                        else:

                            try:
                                # time.sleep(1) # A simple wait to make sure file is saved
                                solve = platesolve.platesolve(
                                    cal_path + 'platesolvetemp.fits', pixscale
                                )
                                #plog("Platesolve time to process: " + str(time.time() - psolve_timer_begin))

                                plog(
                                    "PW Solves: ",
                                    solve["ra_j2000_hours"],
                                    solve["dec_j2000_degrees"],
                                )
                                # breakpoint()
                                #pointing_ra = g_dev['mnt'].mount.RightAscension
                                #pointing_dec = g_dev['mnt'].mount.Declination
                                #icrs_ra, icrs_dec = g_dev['mnt'].get_mount_coordinates()
                                #target_ra = g_dev["mnt"].current_icrs_ra
                                #target_dec = g_dev["mnt"].current_icrs_dec
                                target_ra = g_dev["mnt"].last_ra
                                target_dec = g_dev["mnt"].last_dec
                                solved_ra = solve["ra_j2000_hours"]
                                solved_dec = solve["dec_j2000_degrees"]
                                solved_arcsecperpixel = solve["arcsec_per_pixel"]
                                solved_rotangledegs = solve["rot_angle_degs"]
                                err_ha = target_ra - solved_ra
                                err_dec = target_dec - solved_dec
                                solved_arcsecperpixel = solve["arcsec_per_pixel"]
                                solved_rotangledegs = solve["rot_angle_degs"]
                                plog("Deviation from plate solution in ra: " + str(round(err_ha * 15 * 3600, 2)) + " & dec: " + str (round(err_dec * 3600, 2)) + " asec")

                                # breakpoint()
                                # Reset Solve timers
                                g_dev['obs'].last_solve_time = datetime.datetime.now()
                                g_dev['obs'].images_since_last_solve = 0

                                # Test here that there has not been a slew, if there has been a slew, cancel out!
                                if self.time_of_last_slew > time_platesolve_requested:
                                    plog("detected a slew since beginning platesolve... bailing out of platesolve.")
                                    # if not self.config['keep_focus_images_on_disk']:
                                    #    os.remove(cal_path + cal_name)
                                   # one_at_a_time = 0
                                    # self.platesolve_queue.task_done()
                                    # break

                                # If we are WAY out of range, then reset the mount reference and attempt moving back there.
                                elif (
                                    err_ha * 15 * 3600 > 1200
                                    or err_dec * 3600 > 1200
                                    or err_ha * 15 * 3600 < -1200
                                    or err_dec * 3600 < -1200
                                ) and self.config["mount"]["mount1"][
                                    "permissive_mount_reset"
                                ] == "yes":
                                    g_dev["mnt"].reset_mount_reference()
                                    plog("I've  reset the mount_reference 1")
                                    g_dev["mnt"].current_icrs_ra = solved_ra
                                    #    "ra_j2000_hours"
                                    # ]
                                    g_dev["mnt"].current_icrs_dec = solved_dec
                                    #    "dec_j2000_hours"
                                    # ]
                                    err_ha = 0
                                    err_dec = 0

                                    plog("Platesolve is requesting to move back on target!")
                                    #g_dev['mnt'].mount.SlewToCoordinatesAsync(target_ra, target_dec)

                                    self.pointing_correction_requested_by_platesolve_thread = True
                                    self.pointing_correction_request_time = time.time()
                                    self.pointing_correction_request_ra = target_ra
                                    self.pointing_correction_request_dec = target_dec

                                    # wait_for_slew()

                                else:

                                    # If the mount has updatable RA and Dec coordinates, then sync that
                                    # But if not, update the mount reference
                                    # try:
                                    #     # If mount has Syncable coordinates
                                    #     g_dev['mnt'].mount.SyncToCoordinates(solved_ra, solved_dec)
                                    #     # Reset the mount reference because if the mount has
                                    #     # syncable coordinates, the mount should already be corrected
                                    #     g_dev["mnt"].reset_mount_reference()

                                    #     if (
                                    #          abs(err_ha * 15 * 3600)
                                    #          > self.config["threshold_mount_update"]
                                    #          or abs(err_dec * 3600)
                                    #          > self.config["threshold_mount_update"]
                                    #      ):
                                    #         #plog ("I am nudging the telescope slightly!")
                                    #         #g_dev['mnt'].mount.SlewToCoordinatesAsync(target_ra, target_dec)
                                    #         #wait_for_slew()
                                    #         plog ("Platesolve is requesting to move back on target!")
                                    #         self.pointing_correction_requested_by_platesolve_thread = True
                                    #         self.pointing_correction_request_time = time.time()
                                    #         self.pointing_correction_request_ra = target_ra
                                    #         self.pointing_correction_request_dec = target_dec

                                    # except:
                                    # If mount doesn't have Syncable coordinates

                                    if (
                                        abs(err_ha * 15 * 3600)
                                        > self.config["threshold_mount_update"]
                                        or abs(err_dec * 3600)
                                        > self.config["threshold_mount_update"]
                                    ):

                                        #plog ("I am nudging the telescope slightly!")
                                        #g_dev['mnt'].mount.SlewToCoordinatesAsync(pointing_ra + err_ha, pointing_dec + err_dec)
                                        # wait_for_slew()
                                        #plog("Platesolve is requesting to move back on target!")
                                        self.pointing_correction_requested_by_platesolve_thread = True
                                        self.pointing_correction_request_time = time.time()
                                        self.pointing_correction_request_ra = pointing_ra + err_ha
                                        self.pointing_correction_request_dec = pointing_dec + err_dec

                                        try:
                                            # if g_dev["mnt"].pier_side_str == "Looking West":
                                            if g_dev["mnt"].pier_side == 0:
                                                try:
                                                    g_dev["mnt"].adjust_mount_reference(
                                                        -err_ha, -err_dec
                                                    )
                                                except Exception as e:
                                                    plog("Something is up in the mount reference adjustment code ", e)
                                            else:
                                                try:
                                                    g_dev["mnt"].adjust_flip_reference(
                                                        -err_ha, -err_dec
                                                    )  # Need to verify signs
                                                except Exception as e:
                                                    plog("Something is up in the mount reference adjustment code ", e)

                                        except:
                                            plog("This mount doesn't report pierside")
                                            plog(traceback.format_exc())
                                self.platesolve_is_processing = False
                            except Exception as e:
                                plog(
                                    "Image: did not platesolve; this is usually OK. ", e
                                )
                                plog(traceback.format_exc())

                try:
                    os.remove(cal_path + 'platesolvetemp.fits')
                except:
                    pass

                self.platesolve_is_processing = False
                self.platesolve_queue.task_done()

                one_at_a_time = 0

            else:
                time.sleep(0.1)

    def slow_camera_process(self):
        """A place to process non-process dependant images from the camera pile

        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if (not self.slow_camera_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                slow_process = self.slow_camera_queue.get(block=False)
                #plog (slow_process[0])
                #plog (slow_process[1][0])
                slow_process = slow_process[1]

                # Set up RA and DEC headers for BANZAI
                # needs to be done AFTER text file is sent up.
                # Text file RA and Dec and BANZAI RA and Dec are gormatted different

                temphduheader = slow_process[3]

                #plog ("********** slow queue : " + str(slow_process[0]) )
                if slow_process[0] == 'focus':
                    hdufocus = fits.PrimaryHDU()
                    hdufocus.data = slow_process[2]
                    hdufocus.header = temphduheader
                    hdufocus.header["NAXIS1"] = hdufocus.data.shape[0]
                    hdufocus.header["NAXIS2"] = hdufocus.data.shape[1]
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
                            # hdu=fits.PrimaryHDU()
                            # hdu=fits.CompImageHDU()

                            # hdu.data=slow_process[2]
                            # hdu.header=temphduheader

                            # Figure out which folder to send the calibration file to
                            # and delete any old files over the maximum amount to store
                            if slow_process[4] == 'bias':
                                #tempfilename=self.local_bias_folder + slow_process[1].replace('.fits','.fits.fz')
                                tempfilename = self.local_bias_folder + slow_process[1].replace('.fits', '.npy')
                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_bias_to_store']
                                n_files = len(glob.glob(self.local_bias_folder + '*.n*'))
                                while n_files > max_files:
                                    list_of_files = glob.glob(self.local_bias_folder + '*.n*')
                                    n_files = len(list_of_files)
                                    oldest_file = min(list_of_files, key=os.path.getctime)
                                    os.remove(oldest_file)
                                    plog("removed old bias. ")# + str(oldest_file))

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
                                    plog("removed old dark. ")# + str(oldest_file))

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
                                    plog("removed old flat. ") # + str(oldest_file))

                            # Save the file as an uncompressed numpy binary

                            np.save(
                                tempfilename,
                                np.array(slow_process[2], dtype=np.float32)
                            )

                            # hdufz = fits.CompImageHDU(
                            #    np.array(slow_process[2] , dtype=np.float32), temphduheader
                            # )
                            # hdufz.verify("fix")
                            # hdufz.header[
                            #    "BZERO"
                            # ] = 0  # Make sure there is no integer scaling left over
                            # hdufz.header[
                            #    "BSCALE"
                            # ] = 1  # Make sure there is no integer scaling left over
                            # hdufz.writeto(
                            #    tempfilename, overwrite=True, output_verify='silentfix'
                            # )

                            # hdu.writeto(
                            #    tempfilename, overwrite=True, output_verify='silentfix'
                            # )  # Save full raw file locally

                            # try:
                            #    hdufz.close()
                            # except:
                            #    pass
                            #del hdufz

                            # try:
                            #    hdu.close()
                            # except:
                            #    pass
                            #del hdu
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

                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:
                            hdu = fits.PrimaryHDU()
                            hdu.data = slow_process[2]
                            hdu.header = temphduheader
                            hdu.writeto(
                                slow_process[1], overwrite=True, output_verify='silentfix'
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

                    # Create the fz file ready for BANZAI and the AWS/UI
                    # Note that even though the raw file is int16,
                    # The compression and a few pieces of software require float32
                    # BUT it actually compresses to the same size either way
                    hdufz = fits.CompImageHDU(
                        np.array(slow_process[2], dtype=np.float32), temphduheader
                    )
                    hdufz.verify("fix")
                    hdufz.header[
                        "BZERO"
                    ] = 0  # Make sure there is no integer scaling left over
                    hdufz.header[
                        "BSCALE"
                    ] = 1  # Make sure there is no integer scaling left over

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
                                hdufz.writeto(
                                    slow_process[1], overwrite=True, output_verify='silentfix'
                                )  # Save full fz file locally
                                saver = 1
                            except Exception as e:
                                plog("Failed to write raw fz file: ", e)
                                if "requested" in e and "written" in e:
                                    plog(check_download_cache())
                                plog(traceback.format_exc())
                                time.sleep(10)
                                saverretries = saverretries + 1

                        try:
                            hdufz.close()
                        except:
                            pass
                        del hdufz  # remove file from memory now that we are doing with it

                        # Send this file up to AWS (THIS WILL BE SENT TO BANZAI INSTEAD, SO THIS IS THE INGESTER POSITION)
                        if self.config['send_files_at_end_of_night'] == 'no':
                            g_dev['cam'].enqueue_for_AWS(
                                26000000, '', slow_process[1]
                            )

                    else:  # Is an OSC
                        if self.config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':

                            # Get the original data out
                            #imgdata = np.array(slow_process[2], dtype=np.float32)

                            # # Checkerboard collapse for other colours for temporary jpeg
                            # # Create indexes for B, G, G, R images
                            # xshape = imgdata.shape[0]
                            # yshape = imgdata.shape[1]

                            # # B pixels
                            # list_0_1 = np.array([[0, 0], [0, 1]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # newhdublue = (block_reduce(imgdata * checkerboard, 2))

                            # # R Pixels
                            # list_0_1 = np.array([[1, 0], [0, 0]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # newhdured = (block_reduce(imgdata * checkerboard, 2))

                            # # G top right Pixels
                            # list_0_1 = np.array([[0, 1], [0, 0]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # GTRonly = (block_reduce(imgdata * checkerboard, 2))

                            # # G bottom left Pixels
                            # list_0_1 = np.array([[0, 0], [1, 0]])
                            # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                            # # checkerboard=np.array(checkerboard)
                            # GBLonly = (block_reduce(imgdata * checkerboard, 2))

                            # # Sum two Gs together and half them to be vaguely on the same scale
                            # #hdugreen = np.array(GTRonly + GBLonly) / 2
                            # #del GTRonly
                            # #del GBLonly
                            # del checkerboard
                            
                            
                            
                            newhdured = slow_process[2][::2, ::2]
                            GTRonly = slow_process[2][::2, 1::2]
                            GBLonly = slow_process[2][1::2, ::2]
                            newhdublue = slow_process[2][1::2, 1::2]
                            
                            #del imgdata

                            oscmatchcode = (datetime.datetime.now().strftime("%d%m%y%H%M%S"))

                            hdufz.header["OSCMATCH"] = oscmatchcode
                            hdufz.header['OSCSEP'] = 'yes'
                            hdufz.header['NAXIS1'] = float(hdufz.header['NAXIS1'])/2
                            hdufz.header['NAXIS2'] = float(hdufz.header['NAXIS2'])/2
                            hdufz.header['CRPIX1'] = float(hdufz.header['CRPIX1'])/2
                            hdufz.header['CRPIX2'] = float(hdufz.header['CRPIX2'])/2
                            hdufz.header['PIXSCALE'] = float(hdufz.header['PIXSCALE'])*2
                            hdufz.header['CDELT1'] = float(hdufz.header['CDELT1'])*2
                            hdufz.header['CDELT2'] = float(hdufz.header['CDELT2'])*2
                            tempfilter = hdufz.header['FILTER']
                            tempfilename = slow_process[1]

                            # Save and send R1
                            hdufz.header['FILTER'] = tempfilter + '_R1'

                            hdufz.data = newhdured
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'R1-EX'), overwrite=True, output_verify='silentfix'
                            )  # Save full fz file locally
                            del newhdured
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'R1-EX')
                                )

                            # Save and send G1
                            hdufz.header['FILTER'] = tempfilter + '_G1'
                            hdufz.data = GTRonly
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'G1-EX'), overwrite=True, output_verify='silentfix'
                            )  # Save full fz file locally
                            del GTRonly
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'G1-EX')
                                )

                            # Save and send G2
                            hdufz.header['FILTER'] = tempfilter + '_G2'
                            hdufz.data = GBLonly
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'G2-EX'), overwrite=True, output_verify='silentfix'
                            )  # Save full fz file locally
                            del GBLonly
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'G2-EX')
                                )

                            # Save and send B1
                            hdufz.header['FILTER'] = tempfilter + '_B1'
                            hdufz.data = newhdublue
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'B1-EX'), overwrite=True, output_verify='silentfix'
                            )  # Save full fz file locally
                            del newhdublue
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'B1-EX')
                                )

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
                # breakpoint()

    # Note this is a thread!

    def fast_to_aws(self):
        """Sends small files specifically focussed on UI responsiveness to AWS.

        This is primarily a queue for files that need to get to the UI fast and
        skip the queue. This allows small files to be uploaded simultaneously
        with bigger files being processed by the ordinary queue.

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        one_at_a_time = 0
        # This stopping mechanism allows for threads to close cleanly.
        while True:

            if (not self.fast_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                pri_image = self.fast_queue.get(block=False)
                if pri_image is None:
                    plog("Got an empty entry in fast_queue.")
                    self.fast_queue.task_done()
                    one_at_a_time = 0
                    # time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                t1 = time.time()
                aws_resp = g_dev["obs"].api.authenticated_request(
                    "POST", "/upload/", {"object_name": filename})
                # Only ingest new large fits.fz files to the PTR archive.
                t2 = time.time()
                #print('\naws_auth_req time:  ', t2 - t1, filename[-8:])
                # Send all other files to S3.

                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    #print('\nfiles;  ', files)
                    while True:
                        try:
                            t3 = time.time()
                            reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                            #print('\nnext... post time:  ', time.time() - t3, filepath[-8:])

                            break
                        except:
                            plog("Non-fatal connection glitch for a file posted.")
                            time.sleep(5)
                    #plog(f"\n--> To AWS --> {str(filepath)}")

                # if (
                #     filename[-3:] == "jpg"
                #     or filename[-3:] == "txt"
                #     or ".fits.fz" in filename
                #     or ".token" in filename
                # ):
                #     os.remove(filepath)

                self.fast_queue.task_done()
                #print('\nfast queue total time:  ', time.time() - t2)
                one_at_a_time = 0
                # time.sleep(0.1)
            else:
                time.sleep(0.05)

    def send_to_user(self, p_log, p_level="INFO"):
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
            reqs.post(url_log, body)
        # if not response.ok:
        except:
            plog("Log did not send, usually not fatal.")

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
                    # sources,
                ) = self.smartstack_queue.get(block=False)

                if paths is None:
                    # time.sleep(0.5)
                    continue

                # SmartStack Section
                if smartstackid != "no":
                    sstack_timer = time.time()
                    # if not paths["frame_type"] in [
                    #     "bias",
                    #     "dark",
                    #     "flat",
                    #     "solar",
                    #     "lunar",
                    #     "skyflat",
                    #     "screen",
                    #     "spectrum",
                    #     "auto_focus",
                    # ]:
                    img = fits.open(
                        paths["red_path"] + paths["red_name01"],
                        ignore_missing_end=True,
                    )
                    imgdata = img[0].data.copy()
                    # Pick up some header items for smartstacking later
                    ssfilter = str(img[0].header["FILTER"])
                    ssobject = str(img[0].header["OBJECT"])
                    ssexptime = str(img[0].header["EXPTIME"])
                    #ssframenumber = str(img[0].header["FRAMENUM"])
                    img.close()
                    del img
                    if not self.config['keep_reduced_on_disk']:
                        try:
                            os.remove(paths["red_path"] + paths["red_name01"])
                        except Exception as e:
                            plog("could not remove temporary reduced file: ", e)

                    # sstackimghold=np.array(imgdata)

                    focusimg = np.array(
                        imgdata, order="C"
                    )

                    try:
                        # Some of these are liberated from BANZAI
                        # breakpoint()
                        try:
                            bkg = sep.Background(focusimg)
                        except:
                            focusimg = focusimg.byteswap().newbyteorder()
                            bkg = sep.Background(focusimg)

                        #sepsky = ( np.nanmedian(bkg), "Sky background estimated by SEP" )

                        focusimg -= bkg
                        ix, iy = focusimg.shape
                        border_x = int(ix * 0.05)
                        border_y = int(iy * 0.05)
                        sep.set_extract_pixstack(int(ix*iy - 1))
                        # minarea is set as roughly how big we think a 0.7 arcsecond seeing star
                        # would be at this pixelscale and binning. Different for different cameras/telescopes.
                        #minarea=int(pow(0.7*1.5 / (pixscale*binfocus),2)* 3.14)
                        #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
                        # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
                        # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
                        minarea= -9.2421 * pixscale + 16.553
                        if minarea < 5:  # There has to be a min minarea though!
                            minarea = 5

                        sources = sep.extract(
                            focusimg, 5.0, err=bkg.globalrms, minarea=minarea
                        )
                        #plog ("min_area: " + str(minarea))\
                        sources = Table(sources)
                        sources = sources[sources['flag'] < 8]
                        image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                        sources = sources[sources["peak"] < 0.8 * image_saturation_level]
                        sources = sources[sources["cpeak"] < 0.8 * image_saturation_level]
                        #sources = sources[sources["peak"] > 150 * pow(binfocus,2)]
                        #sources = sources[sources["cpeak"] > 150 * pow(binfocus,2)]
                        sources = sources[sources["flux"] > 2000]
                        sources = sources[sources["x"] < ix - border_x]
                        sources = sources[sources["x"] > border_x]
                        sources = sources[sources["y"] < iy - border_y]
                        sources = sources[sources["y"] > border_y]

                        # BANZAI prune nans from table
                        nan_in_row = np.zeros(len(sources), dtype=bool)
                        for col in sources.colnames:
                            nan_in_row |= np.isnan(sources[col])
                        sources = sources[~nan_in_row]
                        #plog("Actual Platesolve SEP time: " + str(time.time()-actseptime))
                    except:
                        plog("Something went wrong with platesolve SEP")
                        plog(traceback.format_exc())

                    plog("Number of sources just prior to smartstacks: " + str(len(sources)))
                    if len(sources) < 5:
                        plog("skipping stacking as there are not enough sources " + str(len(sources)) + " in this image")

                    # No need to open the same image twice, just using the same one as SEP.
                    #img = sstackimghold.copy()
                    #del sstackimghold
                    smartStackFilename = (
                        str(ssobject)
                        + "_"
                        + str(ssfilter)
                        + "_"
                        + str(ssexptime)
                        + "_"
                        + str(smartstackid)
                        + ".npy"
                    )

                    # For OSC, we need to smartstack individual frames.
                    if not self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                        # Detect and swap img to the correct endianness - needed for the smartstack jpg
                        if sys.byteorder == 'little':
                            imgdata = imgdata.newbyteorder('little').byteswap()
                        else:
                            imgdata = imgdata.newbyteorder('big').byteswap()

                        # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
                        reprojection_failed = False
                        if not os.path.exists(
                            self.obsid_path + "smartstacks/" + smartStackFilename
                        ):
                            if len(sources) >= 5:
                                # Store original image
                                plog("Storing First smartstack image")
                                np.save(
                                    self.obsid_path
                                    + "smartstacks/"
                                    + smartStackFilename,
                                    imgdata,
                                )

                            else:
                                plog("Not storing first smartstack image as not enough sources")
                                reprojection_failed = True
                            storedsStack = imgdata
                        else:
                            # Collect stored SmartStack
                            storedsStack = np.load(
                                self.obsid_path + "smartstacks/" + smartStackFilename
                            )
                            #plog (storedsStack.dtype.byteorder)
                            # Prep new image
                            plog("Pasting Next smartstack image")
                            # img=np.nan_to_num(img)
                            # backgroundLevel =(np.nanmedian(sep.Background(img.byteswap().newbyteorder())))
                            # plog (" Background Level : " + str(backgroundLevel))
                            # img= img - backgroundLevel
                            # Reproject new image onto footplog of old image.
                            # plog(datetime.datetime.now())

                            #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
                            # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
                            # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
                            minarea= -9.2421 * pixscale + 16.553
                            if minarea < 5:  # There has to be a min minarea though!
                                minarea = 5
                                
                            if len(sources) > 5:
                                try:
                                    reprojectedimage, _ = func_timeout.func_timeout(60, aa.register, args=(imgdata, storedsStack),
                                                                                    kwargs={"detection_sigma": 5, "min_area": minarea})
                                    # scalingFactor= np.nanmedian(reprojectedimage / storedsStack)
                                    # plog (" Scaling Factor : " +str(scalingFactor))
                                    # reprojectedimage=(scalingFactor) * reprojectedimage # Insert a scaling factor
                                    storedsStack = np.array((reprojectedimage + storedsStack))
                                    # Save new stack to disk
                                    np.save(
                                        self.obsid_path
                                        + "smartstacks/"
                                        + smartStackFilename,
                                        storedsStack,
                                    )

                                    hduss = fits.PrimaryHDU()
                                    hduss.data = storedsStack
                                    # hdureduced.header=slow_process[3]
                                    #hdureduced.header["NAXIS1"] = hdureduced.data.shape[0]
                                    #hdureduced.header["NAXIS2"] = hdureduced.data.shape[1]
                                    hduss.data = hduss.data.astype("float32")
                                    try:
                                        hduss.writeto(
                                            self.obsid_path
                                            + "smartstacks/"
                                            + smartStackFilename.replace('.npy', '_' + str(sskcounter) + '_' + str(Nsmartstack) + '.fit'), overwrite=True, output_verify='silentfix'
                                        )  # Save flash reduced file locally
                                    except:
                                        plog("Couldn't save smartstack fits. YOU MAY HAVE THE FITS OPEN IN A VIEWER.")

                                    reprojection_failed = False
                                except func_timeout.FunctionTimedOut:
                                    plog("astroalign timed out")
                                    reprojection_failed = True
                                except aa.MaxIterError:
                                    plog("astroalign could not find a solution in this image")
                                    reprojection_failed = True
                                except Exception:
                                    plog("astroalign failed")
                                    plog(traceback.format_exc())
                                    reprojection_failed = True
                            else:
                                reprojection_failed = True

                        if reprojection_failed == True:  # If we couldn't make a stack send a jpeg of the original image.
                            storedsStack = imgdata

                         # Resizing the array to an appropriate shape for the jpg and the small fits

                        # Code to stretch the image to fit into the 256 levels of grey for a jpeg
                        stretched_data_float = Stretch().stretch(storedsStack + 1000)
                        del storedsStack
                        stretched_256 = 255 * stretched_data_float
                        hot = np.where(stretched_256 > 255)
                        cold = np.where(stretched_256 < 0)
                        stretched_256[hot] = 255
                        stretched_256[cold] = 0
                        stretched_data_uint8 = stretched_256.astype("uint8")
                        hot = np.where(stretched_data_uint8 > 255)
                        cold = np.where(stretched_data_uint8 < 0)
                        stretched_data_uint8[hot] = 255
                        stretched_data_uint8[cold] = 0

                        iy, ix = stretched_data_uint8.shape
                        final_image = Image.fromarray(stretched_data_uint8)
                        # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                        if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                            final_image = final_image.transpose(Image.Transpose.TRANSPOSE)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_180)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_90)
                        if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_270)

                        # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                        # to maintain the orientation. whether it is 1 or 0 that is flipped
                        # is sorta arbitrary... you'd use the site-config settings above to
                        # set it appropriately and leave this alone.
                        if pier_side == 1:
                            final_image = final_image.transpose(Image.Transpose.ROTATE_180)

                        # Save BIG version of JPEG.
                        final_image.save(
                            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
                        )
                        # Resizing the array to an appropriate shape for the jpg and the small fits

                        if iy == ix:
                            # hdusmalldata = resize(
                            #     hdusmalldata, (1280, 1280), preserve_range=True
                            # )
                            final_image = final_image.resize(
                                (900, 900)
                            )
                        else:
                            # stretched_data_uint8 = resize(
                            #     stretched_data_uint8,
                            #     (int(1536 * iy / ix), 1536),
                            #     preserve_range=True,
                            # )
                            # stretched_data_uint8 = resize(
                            #     stretched_data_uint8,
                            #     (int(900 * iy / ix), 900),
                            #     preserve_range=True,
                            # )
                            if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                final_image = final_image.resize(

                                    (int(900 * iy / ix), 900)

                                )
                            else:
                                final_image = final_image.resize(

                                    (900, int(900 * iy / ix))

                                )
                        # stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
                        final_image.save(
                            paths["im_path"] + paths["jpeg_name10"]
                        )
                        del final_image

                    # This is where the OSC smartstack stuff is.
                    else:

                        # img is the image coming in

                        if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:

                            if self.config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':

                                # # Checkerboard collapse for other colours for temporary jpeg
                                # # Create indexes for B, G, G, R images
                                # xshape = imgdata.shape[0]
                                # yshape = imgdata.shape[1]

                                # # B pixels
                                # list_0_1 = np.array([[0, 0], [0, 1]])
                                # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                                # # checkerboard=np.array(checkerboard)
                                # newhdublue = (block_reduce(imgdata * checkerboard, 2))

                                # # R Pixels
                                # list_0_1 = np.array([[1, 0], [0, 0]])
                                # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                                # # checkerboard=np.array(checkerboard)
                                # newhdured = (block_reduce(imgdata * checkerboard, 2))

                                # # G top right Pixels
                                # list_0_1 = np.array([[0, 1], [0, 0]])
                                # checkerboard = np.tile(list_0_1, (xshape//2, yshape//2))
                                # # checkerboard=np.array(checkerboard)
                                # newhdugreen = (block_reduce(imgdata * checkerboard, 2))

                                # # G bottom left Pixels
                                # #list_0_1 = np.array([ [0,0], [1,0] ])
                                # #checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                # # checkerboard=np.array(checkerboard)
                                # #GBLonly=(block_reduce(storedsStack * checkerboard ,2))

                                # # Sum two Gs together and half them to be vaguely on the same scale
                                # #hdugreen = np.array(GTRonly + GBLonly) / 2
                                # #del GTRonly
                                # #del GBLonly
                                # del checkerboard
                                
                                
                                newhdured = imgdata[::2, ::2]
                                newhdugreen = imgdata[::2, 1::2]
                                #g2 = hdusmalldata[1::2, ::2]
                                newhdublue = imgdata[1::2, 1::2]
                                

                            else:
                                plog("this bayer grid not implemented yet")

                            # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
                            reprojection_failed = False
                            for colstack in ['blue', 'green', 'red']:
                                if not os.path.exists(
                                    self.obsid_path + "smartstacks/" +
                                        smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                                ):
                                    if len(sources) >= 5:
                                        # Store original image
                                        plog("Storing First smartstack image")
                                        if colstack == 'blue':
                                            np.save(
                                                self.obsid_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid,
                                                                             smartstackid + str(colstack)),
                                                newhdublue,
                                            )
                                        if colstack == 'green':
                                            np.save(
                                                self.obsid_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid,
                                                                             smartstackid + str(colstack)),
                                                newhdugreen,
                                            )
                                        if colstack == 'red':
                                            np.save(
                                                self.obsid_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid,
                                                                             smartstackid + str(colstack)),
                                                newhdured,
                                            )

                                    else:
                                        plog("Not storing first smartstack image as not enough sources")
                                        reprojection_failed = True
                                    # if colstack == 'blue':
                                    #     bluestoredsStack = newhdublue
                                    # if colstack == 'green':
                                    #     greenstoredsStack = newhdugreen
                                    # if colstack == 'red':
                                    #     redstoredsStack = newhdured
                                else:
                                    # Collect stored SmartStack
                                    storedsStack = np.load(
                                        self.obsid_path + "smartstacks/" +
                                        smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                                    )
                                    #plog (storedsStack.dtype.byteorder)
                                    # Prep new image
                                    plog("Pasting Next smartstack image")
                                    # img=np.nan_to_num(img)
                                    # backgroundLevel =(np.nanmedian(sep.Background(img.byteswap().newbyteorder())))
                                    # plog (" Background Level : " + str(backgroundLevel))
                                    # img= img - backgroundLevel
                                    # Reproject new image onto footplog of old image.
                                    # plog(datetime.datetime.now())

                                    #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
                                    # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
                                    # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
                                    minarea= -9.2421 * pixscale + 16.553
                                    if minarea < 5:  # There has to be a min minarea though!
                                        minarea = 5

                                    if len(sources) > 5:
                                        try:
                                            if colstack == 'red':
                                                reprojectedimage, _ = func_timeout.func_timeout(60, aa.register, args=(newhdured, storedsStack),
                                                                                                kwargs={"detection_sigma": 5, "min_area": minarea})

                                            if colstack == 'blue':
                                                reprojectedimage, _ = func_timeout.func_timeout(60, aa.register, args=(newhdublue, storedsStack),
                                                                                                kwargs={"detection_sigma": 5, "min_area": minarea})
                                            if colstack == 'green':
                                                reprojectedimage, _ = func_timeout.func_timeout(60, aa.register, args=(newhdugreen, storedsStack),
                                                                                                kwargs={"detection_sigma": 5, "min_area": minarea})
                                                # scalingFactor= np.nanmedian(reprojectedimage / storedsStack)
                                            # plog (" Scaling Factor : " +str(scalingFactor))
                                            # reprojectedimage=(scalingFactor) * reprojectedimage # Insert a scaling factor
                                            storedsStack = np.array((reprojectedimage + storedsStack))
                                            # Save new stack to disk
                                            np.save(
                                                self.obsid_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid,
                                                                             smartstackid + str(colstack)),
                                                storedsStack,
                                            )

                                            hduss = fits.PrimaryHDU()
                                            hduss.data = storedsStack
                                            # hdureduced.header=slow_process[3]
                                            #hdureduced.header["NAXIS1"] = hdureduced.data.shape[0]
                                            #hdureduced.header["NAXIS2"] = hdureduced.data.shape[1]
                                            hduss.data = hduss.data.astype("float32")
                                            try:
                                                hduss.writeto(
                                                    self.obsid_path
                                                    + "smartstacks/"
                                                    + smartStackFilename.replace(smartstackid, smartstackid + str(colstack)).replace('.npy', '_' + str(sskcounter) + '_' + str(Nsmartstack) + '.fit'), overwrite=True, output_verify='silentfix'
                                                )  # Save flash reduced file locally
                                            except:
                                                plog("Couldn't save smartstack fits. YOU MAY HAVE THE FITS OPEN IN A VIEWER.")
                                            del hduss
                                            if colstack == 'green':
                                                newhdugreen = np.array(storedsStack)
                                            if colstack == 'red':
                                                newhdured = np.array(storedsStack)
                                            if colstack == 'blue':
                                                newhdublue = np.array(storedsStack)
                                            del storedsStack
                                            reprojection_failed = False
                                        except func_timeout.FunctionTimedOut:
                                            plog("astroalign timed out")
                                            reprojection_failed = True
                                        except aa.MaxIterError:
                                            plog("astroalign could not find a solution in this image")
                                            reprojection_failed = True
                                        except Exception:
                                            plog("astroalign failed")
                                            plog(traceback.format_exc())
                                            reprojection_failed = True
                                    else:
                                        reprojection_failed = True

                            # NOW THAT WE HAVE THE INDIVIDUAL IMAGES THEN PUT THEM TOGETHER
                            xshape = newhdugreen.shape[0]
                            yshape = newhdugreen.shape[1]

                            # The integer mode of an image is typically the sky value, so squish anything below that
                            bluemode = stats.mode((newhdublue.astype('int16').flatten()), keepdims=True)[0] - 25
                            redmode = stats.mode((newhdured.astype('int16').flatten()), keepdims=True)[0] - 25
                            greenmode = stats.mode((newhdugreen.astype('int16').flatten()), keepdims=True)[0] - 25
                            newhdublue[newhdublue < bluemode] = bluemode
                            newhdugreen[newhdugreen < greenmode] = greenmode
                            newhdured[newhdured < redmode] = redmode

                            # Then bring the background level up a little from there
                            # blueperc=np.nanpercentile(newhdublue,0.75)
                            # greenperc=np.nanpercentile(newhdugreen,0.75)
                            # redperc=np.nanpercentile(newhdured,0.75)
                            # newhdublue[newhdublue < blueperc] = blueperc
                            # newhdugreen[newhdugreen < greenperc] = greenperc
                            # newhdured[newhdured < redperc] = redperc

                            #newhdublue = newhdublue * (np.median(newhdugreen) / np.median(newhdublue))
                            #newhdured = newhdured * (np.median(newhdugreen) / np.median(newhdured))

                            blue_stretched_data_float = Stretch().stretch(newhdublue)*256
                            ceil = np.percentile(blue_stretched_data_float, 100)  # 5% of pixels will be white
                            floor = np.percentile(blue_stretched_data_float, 60)  # 5% of pixels will be black
                            #a = 255/(ceil-floor)
                            #b = floor*255/(floor-ceil)
                            blue_stretched_data_float[blue_stretched_data_float < floor] = floor
                            blue_stretched_data_float = blue_stretched_data_float-floor
                            blue_stretched_data_float = blue_stretched_data_float * \
                                (255/np.max(blue_stretched_data_float))

                            #blue_stretched_data_float = np.maximum(0,np.minimum(255,blue_stretched_data_float*a+b)).astype(np.uint8)
                            #blue_stretched_data_float[blue_stretched_data_float < floor] = floor
                            del newhdublue

                            green_stretched_data_float = Stretch().stretch(newhdugreen)*256
                            ceil = np.percentile(green_stretched_data_float, 100)  # 5% of pixels will be white
                            floor = np.percentile(green_stretched_data_float, 60)  # 5% of pixels will be black
                            #a = 255/(ceil-floor)
                            green_stretched_data_float[green_stretched_data_float < floor] = floor
                            green_stretched_data_float = green_stretched_data_float-floor
                            green_stretched_data_float = green_stretched_data_float * \
                                (255/np.max(green_stretched_data_float))

                            #b = floor*255/(floor-ceil)

                            #green_stretched_data_float[green_stretched_data_float < floor] = floor
                            #green_stretched_data_float = np.maximum(0,np.minimum(255,green_stretched_data_float*a+b)).astype(np.uint8)
                            del newhdugreen

                            red_stretched_data_float = Stretch().stretch(newhdured)*256
                            ceil = np.percentile(red_stretched_data_float, 100)  # 5% of pixels will be white
                            floor = np.percentile(red_stretched_data_float, 60)  # 5% of pixels will be black
                            #a = 255/(ceil-floor)
                            #b = floor*255/(floor-ceil)
                            # breakpoint()

                            red_stretched_data_float[red_stretched_data_float < floor] = floor
                            red_stretched_data_float = red_stretched_data_float-floor
                            red_stretched_data_float = red_stretched_data_float * (255/np.max(red_stretched_data_float))

                            #red_stretched_data_float[red_stretched_data_float < floor] = floor
                            #red_stretched_data_float = np.maximum(0,np.minimum(255,red_stretched_data_float*a+b)).astype(np.uint8)
                            del newhdured

                            rgbArray = np.zeros((xshape, yshape, 3), 'uint8')
                            rgbArray[..., 0] = red_stretched_data_float  # *256
                            rgbArray[..., 1] = green_stretched_data_float  # *256
                            rgbArray[..., 2] = blue_stretched_data_float  # *256

                            del red_stretched_data_float
                            del blue_stretched_data_float
                            del green_stretched_data_float
                            colour_img = Image.fromarray(rgbArray, mode="RGB")

                           # adjust brightness
                            brightness = ImageEnhance.Brightness(colour_img)
                            brightness_image = brightness.enhance(
                                self.config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'])
                            del colour_img
                            del brightness

                            # adjust contrast
                            contrast = ImageEnhance.Contrast(brightness_image)
                            contrast_image = contrast.enhance(
                                self.config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance'])
                            del brightness_image
                            del contrast

                            # adjust colour
                            colouradj = ImageEnhance.Color(contrast_image)
                            colour_image = colouradj.enhance(
                                self.config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance'])
                            del contrast_image
                            del colouradj

                            # adjust saturation
                            satur = ImageEnhance.Color(colour_image)
                            satur_image = satur.enhance(
                                self.config["camera"][g_dev['cam'].name]["settings"]['osc_saturation_enhance'])
                            del colour_image
                            del satur

                            # adjust sharpness
                            sharpness = ImageEnhance.Sharpness(satur_image)
                            final_image = sharpness.enhance(
                                self.config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance'])
                            del satur_image
                            del sharpness

                            # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                            if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                                final_image = final_image.transpose(Image.TRANSPOSE)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                                final_image = final_image.transpose(Image.FLIP_LEFT_RIGHT)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                                final_image = final_image.transpose(Image.FLIP_TOP_BOTTOM)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                                final_image = final_image.transpose(Image.ROTATE_180)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                                final_image = final_image.transpose(Image.ROTATE_90)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                                final_image = final_image.transpose(Image.ROTATE_270)

                            # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                            # to maintain the orientation. whether it is 1 or 0 that is flipped
                            # is sorta arbitrary... you'd use the site-config settings above to
                            # set it appropriately and leave this alone.
                            if pier_side == 1:
                                final_image = final_image.transpose(Image.ROTATE_180)

                            # Save BIG version of JPEG.
                            final_image.save(
                                paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
                            )

                            # Resizing the array to an appropriate shape for the jpg and the small fits
                            iy, ix = final_image.size
                            if (
                                self.config["camera"][g_dev['cam'].name]["settings"]["crop_preview"]
                                == True
                            ):
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
                                #hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]
                                final_image=final_image.crop((xl,yt,xr,yb))
                                iy, ix = final_image.size
                                
                            if iy == ix:
                                #final_image.resize((1280, 1280))
                                final_image = final_image.resize((900, 900))
                            else:
                                #final_image.resize((int(1536 * iy / ix), 1536))
                                if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                    final_image = final_image.resize((int(900 * iy / ix), 900))
                                else:
                                    final_image = final_image.resize(900, (int(900 * iy / ix)))

                            final_image.save(
                                paths["im_path"] + paths["jpeg_name10"]
                            )
                            del final_image

                    self.fast_queue.put((15, (paths["im_path"], paths["jpeg_name10"])), block=False)
                    self.fast_queue.put(
                        (150, (paths["im_path"], paths["jpeg_name10"].replace('EX10', 'EX20'))), block=False)

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

                    try:
                        imgdata.close()
                        # Just in case
                    except:
                        pass
                    del imgdata

                # WE CANNOT SOLVE FOR POINTING IN THE REDUCE THREAD!
                # POINTING SOLUTIONS HAVE TO HAPPEN AND COMPLETE IN BETWEEN EXPOSURES AND SLEWS

                # time.sleep(0.5)
                plog("Smartstack time taken: " + str(time.time() - sstack_timer))
                self.img = None  # Clean up all big objects.
                self.smartstack_queue.task_done()
            else:
                time.sleep(0.1)

    def check_platesolve_and_nudge(self):

        # This block repeats itself in various locations to try and nudge the scope
        # If the platesolve requests such a thing.
        if g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
            g_dev['obs'].pointing_correction_requested_by_platesolve_thread = False
            if g_dev['obs'].pointing_correction_request_time > g_dev['obs'].time_of_last_slew:  # Check it hasn't slewed since request
                plog("Re-centering Telescope Slightly.")
                self.send_to_user("Re-centering Telescope Slightly.")
                g_dev['mnt'].mount.SlewToCoordinatesAsync(
                    g_dev['obs'].pointing_correction_request_ra, g_dev['obs'].pointing_correction_request_dec)
                g_dev['obs'].time_of_last_slew = time.time()
                wait_for_slew()


def wait_for_slew():

    try:
        if not g_dev['mnt'].mount.AtPark:
            movement_reporting_timer = time.time()
            while g_dev['mnt'].mount.Slewing:  # or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                #if g_dev['mnt'].mount.Slewing: plog( 'm>')
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if time.time() - movement_reporting_timer > 2.0:
                    plog('m>')
                    movement_reporting_timer = time.time()
                # time.sleep(0.1)
                g_dev['obs'].update_status(mount_only=True, dont_wait=True)

    except Exception as e:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        if 'pywintypes.com_error' in str(e):
            plog("Mount disconnected. Recovering.....")
            time.sleep(30)
            g_dev['mnt'].mount.Connected = True
            # g_dev['mnt'].home_command()
        else:
            breakpoint()
    return


if __name__ == "__main__":

    o = Observatory(ptr_config.obs_id, ptr_config.site_config)
    o.run()  # This is meant to be a never ending loop.
