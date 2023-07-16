
"""
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
import os
import queue
import shelve
import socket
import threading
import time
import sys
import shutil
import glob
import subprocess
import pickle
from astropy.io import fits
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord, get_sun
from astropy.time import Time
from astropy import units as u
from astropy.table import Table
from dotenv import load_dotenv
import numpy as np
import redis  
import requests
import urllib.request
import traceback
import psutil
from api_calls import API_calls
import ptr_config
from devices.camera import Camera
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
#from devices.enclosure import Enclosure
from devices.mount import Mount
from devices.telescope import Telescope
#from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
from devices.selector import Selector
from devices.screen import Screen
from devices.sequencer import Sequencer
from global_yard import g_dev
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
#reqs.mount('https://', HTTPAdapter(max_retries=retries))

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
    
    #if payload['statusType'] == 'weather':
    #   breakpoint()
    
    
    #print (payload)

    try:

        data = json.dumps(payload)
    except Exception as e:
        plog("Failed to create status payload. Usually not fatal:  ", e)

    try:
        reqs.post(uri_status, data=data, timeout=20)
    except Exception as e:
        plog("Failed to send_status. Usually not fatal:  ", e)
        
    #breakpoint()


    
    


debug_flag = None
debug_lapse_time = None


class Observatory:
    """Docstring here"""

    def __init__(self, name, ptr_config):
        # This is the main class through which we can make authenticated api calls.
        self.api = API_calls()
        self.command_interval = 0  # seconds between polls for new commands
        self.status_interval = 0  # NOTE THESE IMPLEMENTED AS A DELTA NOT A RATE.
        self.name = name  
        self.obs_id = name
        g_dev['name'] = name
        
        self.config = ptr_config
        self.wema_name = self.config['wema_name']
        #self.observatory_location = ptr_config["observatory_location"]
        self.debug_flag = self.config['debug_mode']

        self.admin_only_flag = self.config['admin_owner_commands_only']

        # Default path
        self.obsid_path = ptr_config["client_path"] + '/' + self.name + '/'
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)
        self.local_calibration_path = ptr_config['local_calibration_path'] + self.config['obs_id'] + '/'
        if not os.path.exists(ptr_config['local_calibration_path']):
            os.makedirs(ptr_config['local_calibration_path'])
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path)

        # Kill rotator softwares on boot-up to resync.
        try:
            os.system("taskkill /IM AltAzDSConfig.exe /F")
        except:
            pass
        try:
            os.system('taskkill /IM "Gemini Software.exe" /F')
        except:
            pass
        #breakpoint()

        if self.debug_flag:

            self.debug_lapse_time = time.time() + self.config['debug_duration_sec']
            g_dev['debug'] = True
            self.camera_temperature_in_range_for_calibrations = True
            #g_dev['obs'].open_and_enabled_to_observe = True
        else:
            self.debug_lapse_time = 0.0
            g_dev['debug'] = False
            #g_dev['obs'].open_and_enabled_to_observe = False

        #if self.config["wema_is_active"]:
        #    self.hostname = socket.gethostname()
        #    if self.hostname in self.config["wema_hostname"]:
        #        self.is_wema = True
        #        g_dev["wema_share_path"] = ptr_config["wema_write_share_path"]
        #        self.wema_path = g_dev["wema_share_path"]
        #    else:
        # This host is a client
        self.is_wema = False  # This is a client.
        self.obsid_path = ptr_config["client_path"] + '/' + self.name + '/'
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)

        g_dev["obsid_path"] = self.obsid_path
        #g_dev["wema_share_path"] = ptr_config[
        #    "client_write_share_path"
        #]  # Just to be safe.
        #self.wema_path = g_dev["wema_share_path"]
        #else:
        #    self.is_wema = False  # This is a client.
        #    self.obsid_path = ptr_config["client_path"] + self.config['obs_id'] + '/'
        #    g_dev["obsid_path"] = self.obsid_path
        #    g_dev["wema_share_path"] = self.obsid_path  # Just to be safe.
        #    self.wema_path = g_dev["wema_share_path"]

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
        # self.wema_types = ptr_config["wema_types"]    >>>>
        # self.enc_types = None  # config['enc_types']
        # self.short_status_devices = (
        #     ptr_config['short_status_devices']  # May not be needed for no wema obsy
        #)
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

        self.last_time_report_to_console = time.time()

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

        self.auto_centering_off=self.config['turn_auto_centering_off']

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
        
        


        # Local Calibration Paths
        #self.local_calibration_path = ptr_config['local_calibration_path'] + self.config['obs_id'] + '/'
        
        if not os.path.exists(self.local_calibration_path + "calibmasters"):  # retaining for backward compatibility
            os.makedirs(self.local_calibration_path + "calibmasters")
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

        # Clear out smartstacks directory
        #plog ("removing and reconstituting smartstacks directory")
        try:
            shutil.rmtree(self.local_calibration_path + "smartstacks")
        except:
            plog("problems with removing the smartstacks directory... usually a file is open elsewhere")
        time.sleep(3)
        if not os.path.exists(self.local_calibration_path + "smartstacks"):
            os.makedirs(self.local_calibration_path + "smartstacks")
        
        # Orphan and Broken paths
        self.orphan_path=self.config['client_path'] +'/' + g_dev['obs'].name + '/' + 'orphans/'
        if not os.path.exists(self.orphan_path):
            os.makedirs(self.orphan_path)
        
        self.broken_path=self.config['client_path'] +'/' + g_dev['obs'].name + '/' + 'broken/'
        if not os.path.exists(self.broken_path):
            os.makedirs(self.broken_path)


        self.last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        self.images_since_last_solve = 10000

        self.time_last_status = time.time() - 3

        self.platesolve_is_processing = False

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

        self.laterdelete_queue = queue.Queue(maxsize=0)
        self.laterdelete_queue_thread = threading.Thread(target=self.laterdelete_process, args=())
        self.laterdelete_queue_thread.start()

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
        #self.events_new = None
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
        self.warm_report_timer = time.time()

        # set manual mode at startup
        self.scope_in_manual_mode=self.config['scope_in_manual_mode']
        
        self.sun_checks_off=self.config['sun_checks_off']
        self.altitude_checks_off=self.config['altitude_checks_off']
        self.daytime_exposure_time_safety_off=self.config['daytime_exposure_time_safety_off']
        self.mount_reference_model_off= self.config['mount_reference_model_off'],
        
        self.camera_temperature_in_range_for_calibrations=True
        
        self.last_platesolved_ra = np.nan
        self.last_platesolved_dec =np.nan
        self.last_platesolved_ra_err = np.nan
        self.last_platesolved_dec_err =np.nan
        
        # Keep track of how long it has been since the last activity
        self.time_of_last_exposure = time.time()
        self.time_of_last_slew = time.time()

        # Only poll the broad safety checks (altitude and inactivity) every 5 minutes
        self.safety_check_period = self.config['safety_check_period']
        self.time_since_safety_checks = time.time() - (2* self.safety_check_period)

        # Keep track of how long it has been since the last live connection to the internet
        self.time_of_last_live_net_connection = time.time()

        # If the camera is detected as substantially (20 degrees) warmer than the setpoint
        # during safety checks, it will keep it warmer for about 20 minutes to make sure
        # the camera isn't overheating, then return it to its usual temperature.
        self.camera_overheat_safety_warm_on = False   #NB NB should this be initialized from Config? WER
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
        reqs.request(
            "POST", url_job, data=json.dumps(body), timeout=30
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

        if self.debug_flag:
            g_dev['obs'].open_and_enabled_to_observe=True


        # Report Camera Gains as part of bootup
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
                breakpoint()



                
        
        # Report filter Gains as part of bootup
        filter_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtergain' + g_dev['cam'].name + str(g_dev['obs'].name))
        #breakpoint()
        if len(filter_gain_shelf)==0:
            plog ("Looks like there is no filter shelf.")
        else:
            plog ("Stored filter gains")
            for filtertempgain in list(filter_gain_shelf.keys()):
                plog (str(filtertempgain) + " " + str(filter_gain_shelf[filtertempgain]))
        filter_gain_shelf.close()                

        # breakpoint()
        #req2 = {'target': 'near_tycho_star', 'area': 150}
        #opt = {}
        #g_dev['obs'].open_and_enabled_to_observe = True
        #g_dev['seq'].sky_flat_script({}, {}, morn=False)
        # g_dev['seq'].extensive_focus_script(req2,opt)
        
        
        # req = {'bin1': True, 'bin2': False, 'bin3': False, 'bin4': False, 'numOfBias': 63, \
        #         'numOfDark': 31, 'darkTime': 75, 'numOfDark2': 31, 'dark2Time': 75, \
        #         'hotMap': True, 'coldMap': True, 'script': 'genBiasDarkMaster', }  #This specificatin is obsolete
        # opt = {}        
        # g_dev['seq'].bias_dark_script(req, opt, morn=True)
        
        # Pointing
        #req = {'time': self.config['focus_exposure_time'],  'alias':  str(self.config['camera']['camera_1_1']['name']), 'image_type': 'focus'}   #  NB Should pick up filter and constats from config
        #opt = {'area': 150, 'count': 1, 'bin': '2, 2', 'filter': 'focus'}
        #opt = {'area': 150, 'count': 1, 'bin': 1, 'filter': 'focus'}
        #result = g_dev['cam'].expose_command(req, opt, no_AWS=False, solve_it=True)
        # breakpoint()
        #g_dev['seq'].regenerate_local_masters()
        
        #g_dev['seq'].sky_grid_pointing_run(max_pointings=25, alt_minimum=25)
        
        #g_dev['mnt'].slewToSkyFlatAsync(skip_open_test=True) 

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
                #plog(name)
                try:
                    driver = devices_of_type[name]["driver"]
                except:
                    pass
                settings = devices_of_type[name].get("settings", {})
                #if dev_type == "observing_conditions":
                #    device = ObservingConditions(
                 #      driver, name, self.config, self.astro_events
                #    )
                #elif dev_type == "enclosure":
                #    device = Enclosure(driver, name, self.config, self.astro_events)
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

        retryapi=True
        while retryapi:
            try:
                response = g_dev["obs"].api.authenticated_request("PUT", uri, self.config)
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
            g_dev['cam'].expresult["stopped"] = True
        except Exception as e:
            plog("Camera is not busy.", e)
            self.exposure_busy = False

        g_dev["obs"].exposure_halted_indicator = True
        g_dev["obs"].exposure_halted_indicator_timer = time.time()

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
                #breakpoint()
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
                    "POST", url_job, data=json.dumps(body), timeout=20
                ).json()
                # Make sure the list is sorted in the order the jobs were issued
                # Note: the ulid for a job is a unique lexicographically-sortable id.
                if len(unread_commands) > 0:
                    unread_commands.sort(key=lambda x: x["timestamp_ms"])
                    # Process each job one at a time
                    for cmd in unread_commands:

                        if not (self.admin_only_flag and (("admin" in cmd['user_roles']) or ("owner" in cmd['user_roles']) or (not self.admin_only_flag))):

                            # breakpoint()

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
        #send_enc = False
        #send_ocn = False

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

        if g_dev["obs"].exposure_halted_indicator == True:
            if g_dev["obs"].exposure_halted_indicator_timer - time.time() > 12:
                g_dev["obs"].exposure_halted_indicator = False
                g_dev["obs"].exposure_halted_indicator_timer = time.time()

        # Good spot to check if we need to nudge the telescope as long as we aren't exposing.
        if not g_dev["cam"].exposure_busy:
            self.check_platesolve_and_nudge()

        
        t1 = time.time()
        status = {}

        # Loop through all types of devices.
        # For each type, we get and save the status of each device.

        #if not self.config["wema_is_active"]:
            #device_list = self.short_status_devices()
        device_list = self.device_types
        #breakpoint()
            #remove_enc = False
        #if self.config["wema_is_active"]:
            # used when wema is sending ocn and enc status via a different stream.
            #device_list = self.short_status_devices
            #remove_enc = False

        #else:
            #device_list = self.device_types  # used when one computer is doing everything for a site.
            #remove_enc = True

        obsy = self.name
        if mount_only == True:
            device_list = ['mount', 'telescope']

        # Get current enclosure status
        #send_enc=False
        #print ("enc status timer: " + str(datetime.datetime.now() - self.enclosure_status_timer))
        #print (datetime.timedelta(minutes=self.enclosure_check_period))
        #if (
        #    datetime.datetime.now() - self.enclosure_status_timer
        #) > datetime.timedelta(minutes=self.enclosure_check_period):
            
        #    g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()    
        #    lane = "enclosure"                
        #    self.enclosure_status_timer = datetime.datetime.now()
            #self.send_status_queue.put((obsy, lane, g_dev['obs'].enc_status), block=False)
        #    print ("status sendy!")
        #    print (g_dev['obs'].enc_status)
        
        #status['enclosure']['enclosure1'] = g_dev['obs'].enc_status
        
        # Get current weather status  
        #send_ocn=False
        #plog ("Obs")
        #plog (datetime.datetime.now() - self.observing_status_timer)
        #plog (datetime.timedelta(minutes=self.observing_check_period))
        
        if (
            (datetime.datetime.now() - self.observing_status_timer)
        ) > datetime.timedelta(minutes=self.observing_check_period):
            g_dev['obs'].ocn_status = g_dev['obs'].get_weather_status_from_aws()
            #lane = "weather"
            self.observing_status_timer = datetime.datetime.now()
            #self.send_status_queue.put((obsy, lane, g_dev['obs'].ocn_status), block=False)
            #plog (g_dev['obs'].ocn_status)
            #plog ("Ping obs")
            
        #plog ("end")
        #plog (datetime.datetime.now() - self.enclosure_status_timer)
        #plog (datetime.timedelta(minutes=self.enclosure_check_period)) 
        
        if (
            (datetime.datetime.now() - self.enclosure_status_timer)
        ) > datetime.timedelta(minutes=self.enclosure_check_period):
            #lane = "enclosure"
            g_dev['obs'].enc_status = g_dev['obs'].get_enclosure_status_from_aws()
            self.enclosure_status_timer = datetime.datetime.now()
            #plog ("Ping end")


        for dev_type in device_list:
            #  The status that we will send is grouped into lists of
            #  devices by dev_type.
            status[dev_type] = {}
            #status['enclosure'] = {}
            #status['observing_conditions'] = {}
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


                


                # if (
                #    "enclosure" in device_name
                #     # and device_name in self.config["wema_types"]
                #     # and (self.is_wema or self.obsid_is_specific)
                # ):

                #     if self.config['enclosure']['enclosure1']['driver'] == None and not self.obsid_is_specific:
                #         # Even if no connection send a satus
                #         status = {'shutter_status': "No enclosure.",
                #                   'enclosure_synchronized': False,  # self.following, 20220103_0135 WER
                #                   'dome_azimuth': 0,
                #                   'dome_slewing': False,
                #                   'enclosure_mode': "No Enclosure",
                #                   'enclosure_message': "No message"},  # self.state}#self.following, 20220103_0135 WER

                #     elif (
                #         datetime.datetime.now() - self.enclosure_status_timer
                #     ) < datetime.timedelta(minutes=self.enclosure_check_period):
                #         result = None
                #         send_enc = False
                #     else:
                #         #plog("Running enclosure status check")
                #         self.enclosure_status_timer = datetime.datetime.now()
                #         send_enc = True

                #         result = device.get_status()

                # elif ("observing_conditions" in device_name
                #       and self.config['observing_conditions']['observing_conditions1']['driver'] == None):
                #     # Here is where the weather config gets updated.
                #     if (
                #         datetime.datetime.now() - self.observing_status_timer
                #     ) < datetime.timedelta(minutes=self.observing_check_period):
                #         result = None
                #         send_ocn = False
                #     else:
                #         #plog("Running weather status check.")
                #         self.observing_status_timer = datetime.datetime.now()
                #         result = device.get_noocndevice_status()
                #         send_ocn = True
                #         if self.obsid_is_specific:
                #             remove_enc = False

                # elif (
                #     "observing_conditions" in device_name
                #     and device_name in self.config["wema_types"]
                #     and (self.is_wema or self.obsid_is_specific)
                # ):
                #     # Here is where the weather config gets updated.
                #     if (
                #         datetime.datetime.now() - self.observing_status_timer
                #     ) < datetime.timedelta(minutes=self.observing_check_period):
                #         result = None
                #         send_ocn = False
                #     else:
                #         plog("Running weather status check.")
                #         self.observing_status_timer = datetime.datetime.now()
                #         result = device.get_status(g_dev=g_dev)
                #         send_ocn = True
                #         if self.obsid_is_specific:
                #             remove_enc = False

                
                if 'telescope' in device_name:
                    status['telescope'] = status['mount']
                else:
                    result = device.get_status()
                    
                if result is not None:
                    status[dev_type][device_name] = result

        #status['observing_conditions']['observing_conditions1'] = g_dev['obs'].ocn_status
        #status['enclosure']['enclosure1'] = g_dev['obs'].enc_status

        # If the roof is open, then it is open and enabled to observe
        #try:

        if not g_dev['obs'].enc_status == None:
            if g_dev['obs'].enc_status['shutter_status'] == 'Open' or self.debug_flag:
                self.open_and_enabled_to_observe = True
        #except:
        #    pass

        # Check that the mount hasn't slewed too close to the sun
        # If the roof is open and enabled to observe
        try:

            if not g_dev['mnt'].mount.Slewing and self.open_and_enabled_to_observe and not self.sun_checks_off:

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
                    
                    if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                        self.cancel_all_activity()
                    if not g_dev['mnt'].mount.AtPark:
                        g_dev['mnt'].park_command()
                    return
        except:
            plog ("Sun check didn't work for some reason")

        status["timestamp"] = round((time.time() + t1) / 2.0, 3)
        status["send_heartbeat"] = False
        #try:
            #ocn_status = None
            #enc_status = None
            #ocn_status = {"observing_conditions": status.pop("observing_conditions")}
            #enc_status = {"enclosure": status.pop("enclosure")}
            #device_status = status
        #except:
        #    pass
        #plog ("Status update length: " + str(time.time() - beginning_update_status))
        loud = False
        # Consider inhibiting unless status rate is low
        

        if status is not None:
            lane = "device"
            #send_status(obsy, lane, status)
            #print( obsy, lane, status['timestamp'] )
            #plog (status)
            #plog("Status Queue size: "+ str(self.send_status_queue.qsize()))
            # To stop status's filling up the queue under poor connection conditions
            # There is a size limit to the queue
            if self.send_status_queue.qsize() < 7:
                self.send_status_queue.put((obsy, lane, status), block=False)
        
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
        
        #if self.debug_flag:
        #    safety_check_period *= 4
        #    self.time_since_safety_checks = time.time() + safety_check_period
            
        if time.time() - self.time_since_safety_checks > self.safety_check_period and not self.debug_flag:
            self.time_since_safety_checks = time.time()

            # breakpoint()
            if (time.time() - self.last_time_report_to_console) > 600:
                plog (ephem.now())
                self.last_time_report_to_console = time.time()
            #print ("Nightly Reset Complete      : " + str(g_dev['seq'].nightly_reset_complete))
            #plog("Time until Nightly Reset      : " + str(round(( g_dev['events']['Nightly Reset'] - ephem.now()) * 24,2)) + " hours")
            
            
            # Check nightly_reset is all good
            if ((g_dev['events']['Cool Down, Open']  <= ephem.now() < g_dev['events']['Observing Ends'])):
                g_dev['seq'].nightly_reset_complete = False
            
            if not g_dev['mnt'].mount.AtPark and self.open_and_enabled_to_observe and not self.sun_checks_off: # Only do the sun check if scope isn't parked
                # Check that the mount hasn't slewed too close to the sun
                sun_coords = get_sun(Time.now())
                try:
                    temppointing = SkyCoord((g_dev['mnt'].current_icrs_ra)*u.hour,
                                            (g_dev['mnt'].current_icrs_dec)*u.degree, frame='icrs')
                except:
                    breakpoint()
                sun_dist = sun_coords.separation(temppointing)
                #plog ("sun distance: " + str(sun_dist.degree))
                if sun_dist.degree < self.config['closest_distance_to_the_sun'] and not g_dev['mnt'].mount.AtPark:
                    g_dev['obs'].send_to_user("Found telescope pointing too close to the sun: " +
                                              str(sun_dist.degree) + " degrees.")
                    plog("Found telescope pointing too close to the sun: " + str(sun_dist.degree) + " degrees.")
                    g_dev['obs'].send_to_user("Parking scope and cancelling all activity")
                    plog("Parking scope and cancelling all activity")
                    if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
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

            # Roof Checks only if not in debug mode
            # And only check if the scope thinks everything is open and hunky dory
            if not self.debug_flag and self.open_and_enabled_to_observe and not self.scope_in_manual_mode:
                if g_dev['obs'].enc_status is not None:
                    if g_dev['obs'].enc_status['shutter_status'] == 'Software Fault':
                        plog("Software Fault Detected. Will alert the authorities!")
                        plog("Parking Scope in the meantime")
                        #if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                        self.open_and_enabled_to_observe = False
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()   #NB THis kills bias-dark
                        if not g_dev['mnt'].mount.AtPark:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                        # will send a Close call out into the blue just in case it catches
                        #g_dev['enc'].enclosure.CloseShutter()
                        #g_dev['seq'].enclosure_next_open_time = time.time(
                        #) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening

                    if g_dev['obs'].enc_status['shutter_status'] == 'Closing' or g_dev['obs'].enc_status['shutter_status'] == 'Opening':
                        #if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            plog("Detected Roof Movement.")
                            self.open_and_enabled_to_observe = False
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()
                            if not g_dev['mnt'].mount.AtPark:
                                if g_dev['mnt'].home_before_park:
                                    g_dev['mnt'].home_command()
                                g_dev['mnt'].park_command()
                            
                            #g_dev['enc'].enclosure.CloseShutter()
                            #g_dev['seq'].enclosure_next_open_time = time.time(
                            #) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening

                    if g_dev['obs'].enc_status['shutter_status'] == 'Error':
                        
                        plog("Detected an Error in the Roof Status. Packing up for safety.")
                        #plog("This is usually because the weather system forced the roof to shut.")
                        #plog("By closing it again, it resets the switch to closed.")
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            self.cancel_all_activity()    #NB Kills bias dark
                        self.open_and_enabled_to_observe = False
                        #g_dev['enc'].enclosure.CloseShutter()
                        #g_dev['seq'].enclosure_next_open_time = time.time(
                        #) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
                        # while g_dev['enc'].enclosure.ShutterStatus == 3:
                        #plog ("closing")
                        plog("Also Parking the Scope")
                        if not g_dev['mnt'].mount.AtPark:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()

                    #roof_should_be_shut = False
                else:
                    plog("Enclosure roof status probably not reporting correctly. WEMA down?")
                # try:
                #     if g_dev['enc'].status['shutter_status'] == 'Closing':
                #         if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                #             plog(
                #                 "Detected Roof Closing. Sending another close command just in case the roof got stuck on this status (this happens!)")
                #             self.open_and_enabled_to_observe = False
                #             # self.cancel_all_activity()    #NB Kills bias dark
                #             g_dev['enc'].enclosure.CloseShutter()
                #             g_dev['seq'].enclosure_next_open_time = time.time(
                #             ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
    
                #     if g_dev['enc'].status['shutter_status'] == 'Error':
                #         if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                #             plog("Detected an Error in the Roof Status. Closing up for safety.")
                #             plog("This is usually because the weather system forced the roof to shut.")
                #             plog("By closing it again, it resets the switch to closed.")
                #             # self.cancel_all_activity()    #NB Kills bias dark
                #             self.open_and_enabled_to_observe = False
                #             g_dev['enc'].enclosure.CloseShutter()
                #             g_dev['seq'].enclosure_next_open_time = time.time(
                #             ) + self.config['roof_open_safety_base_time'] * g_dev['seq'].opens_this_evening
                #             # while g_dev['enc'].enclosure.ShutterStatus == 3:
                #             #plog ("closing")
                #             plog("Also Parking the Scope")
                #             if not g_dev['mnt'].mount.AtPark:
                #                 if g_dev['mnt'].home_before_park:
                #                     g_dev['mnt'].home_command()
                #                 g_dev['mnt'].park_command()
                # except:
                #     plog("shutter status enclosure tests did not work. Usually shutter status is None")
                roof_should_be_shut = False

                # breakpoint()
                if not self.scope_in_manual_mode and not g_dev['seq'].flats_being_collected:
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

                try:
                    if g_dev['obs'].enc_status['shutter_status'] == 'Open':
                        if roof_should_be_shut == True:
                            plog("Safety check notices that the roof was open outside of the normal observing period")
                            
                            # if self.config['obsid_roof_control'] and g_dev['enc'].mode == 'Automatic':
                            #     plog("Shutting the roof out of an abundance of caution. This may also be normal functioning")

                            #     # self.cancel_all_activity()  #NB Kills bias dark
                            #     g_dev['enc'].enclosure.CloseShutter()
                            #     while g_dev['enc'].enclosure.ShutterStatus == 3:
                            #         plog("closing")
                            #         time.sleep(3)
                            #else:
                            #    plog("This scope does not have control of the roof though.")
                except:
                    plog('Line 1192 Roof shutter status faulted.')

                if not self.scope_in_manual_mode and not g_dev['seq'].flats_being_collected :

                    # If the roof should be shut, then the telescope should be parked.
                    if roof_should_be_shut == True:
                        if not g_dev['mnt'].mount.AtPark:
                            plog('Parking telescope as it is during the period that the roof is meant to be shut.')
                            self.open_and_enabled_to_observe = False
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()  #NB Kills bias dark
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            # PWI must receive a park() in order to report being parked.  Annoying problem when debugging, because I want tel to stay where it is.
                            g_dev['mnt'].park_command()
    
                    if g_dev['obs'].enc_status is not None:
                        # If the roof IS shut, then the telescope should be shutdown and parked.
                        if g_dev['obs'].enc_status['shutter_status'] == 'Closed':
    
                            if not g_dev['mnt'].mount.AtPark:
                                plog("Telescope found not parked when the observatory roof is shut. Parking scope.")
                                self.open_and_enabled_to_observe = False
                                if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                    self.cancel_all_activity()  #NB Kills bias dark
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
                        if g_dev['obs'].enc_status['shutter_status'] == 'Open' and roof_should_be_shut == False:
                            self.open_and_enabled_to_observe = True
    
                    else:
                        plog("g_dev['obs'].enc_status not reporting correctly")
            #plog("Current Open and Enabled to Observe Status: " + str(self.open_and_enabled_to_observe))

            # Check the mount is still connected
            g_dev['mnt'].check_connect()
            # if got here, mount is connected. NB Plumb in PW startup code

            # Check that the mount hasn't tracked too low or an odd slew hasn't sent it pointing to the ground.
            if not self.altitude_checks_off:
                try:
                    mount_altitude = g_dev['mnt'].mount.Altitude
                    lowest_acceptable_altitude = self.config['mount']['mount1']['lowest_acceptable_altitude']
                    if mount_altitude < lowest_acceptable_altitude:
                        plog("Altitude too low! " + str(mount_altitude) + ". Parking scope for safety!")
                        if not g_dev['mnt'].mount.AtPark:
                            if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                                self.cancel_all_activity()
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                            # Reset mount reference because thats how it probably got pointing at the dirt in the first place!
                            if self.config["mount"]["mount1"]["permissive_mount_reset"] == "yes":
                                g_dev["mnt"].reset_mount_reference()
                except Exception as e:
                    plog(traceback.format_exc())
                    plog(e)
                    
                    if g_dev['mnt'].theskyx:
                        
                        plog("The SkyX had an error.")
                        plog("Usually this is because of a broken connection.")
                        plog("Killing then waiting 60 seconds then reconnecting")
                        g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                    else:
                        breakpoint()
                        
                    # g_dev['mnt'].home_command()

            # If no activity for an hour, park the scope
            if not self.scope_in_manual_mode:
                if time.time() - self.time_of_last_slew > self.config['mount']['mount1']['time_inactive_until_park'] and time.time() - self.time_of_last_exposure > self.config['mount']['mount1']['time_inactive_until_park']:
                    if not g_dev['mnt'].mount.AtPark:
                        plog("Parking scope due to inactivity")
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                    self.time_of_last_slew = time.time()
                    self.time_of_last_exposure = time.time()

            # Check that rotator is rotating
            #if g_dev['rot'] != None:
            #    try:
            #        g_dev['rot'].check_rotator_is_rotating() 
            #    except:
            #        plog("occasionally rotator skips a beat when homing.")
                
            # Check that cooler is alive
            if g_dev['cam']._cooler_on():

                current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                current_camera_temperature = float(current_camera_temperature)   
                if current_camera_temperature - g_dev['cam'].setpoint > 1.5 or current_camera_temperature - g_dev['cam'].setpoint < -1.5:
                    self.camera_temperature_in_range_for_calibrations = False
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

                elif g_dev['cam'].protect_camera_from_overheating and (float(current_camera_temperature) - g_dev['cam'].current_setpoint) > (2 * g_dev['cam'].day_warm_degrees):
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

            if not self.camera_overheat_safety_warm_on and (time.time() - self.warm_report_timer > 300):                
                # Daytime... a bit tricky! Two periods... just after biases but before nightly reset OR ... just before eve bias dark
                # As nightly reset resets the calendar
                self.warm_report_timer = time.time()
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
                    if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                        self.cancel_all_activity()
                    if not g_dev['mnt'].mount.AtPark:
                        plog("Parking scope due to inactivity")
                        if g_dev['mnt'].home_before_park:
                            g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()
                        self.time_of_last_slew = time.time()

                    #g_dev['enc'].enclosure.CloseShutter()

            #if (g_dev['seq'].enclosure_next_open_time - time.time()) > 0:
            #    plog("opens this eve: " + str(g_dev['seq'].opens_this_evening))

            #    plog("minutes until next open attempt ALLOWED: " +
            #         str((g_dev['seq'].enclosure_next_open_time - time.time()) / 60))

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

                # Only ingest new large fits.fz files to the PTR archive.
                if filename.endswith("-EX00.fits.fz"):
                    try:
                        broken = 0
                        with open(filepath, "rb") as fileobj:
                            tempPTR = 0

                            if self.env_exists == True and (not frame_exists(fileobj)):
    
                                #plog ("\nstarting ingester")
                                retryarchive = 0
                                while retryarchive < 10:
                                    try:      
                                        # Get header explicitly out to send up
                                        tempheader=fits.open(filepath)
                                        tempheader=tempheader[1].header
                                        headerdict = {}
                                        for entry in tempheader.keys():
                                            headerdict[entry] = tempheader[entry]
                                            #print (entry)
                                            #print ("***********")
                                            
                                        #breakpoint()
                                        
                                        upload_file_and_ingest_to_archive(fileobj, file_metadata=headerdict)                                    
                                        self.aws_queue.task_done()
                                        tempPTR = 1
                                        retryarchive = 11
                                        # Only remove file if successfully uploaded
                                        if ('calibmasters' not in filepath) or ('ARCHIVE_' in filepath):
                                            try:
                                                os.remove(filepath)
                                            except:
                                                #plog("Couldn't remove " + str(filepath) + " file after transfer, sending to delete queue")
                                                self.laterdelete_queue.put(filepath, block=False)
                                    except ocs_ingester.exceptions.DoNotRetryError:
                                        #plog((traceback.format_exc()))
                                        plog ("Couldn't upload to PTR archive: " + str(filepath))

                                        broken=1
                                        
                                        #plog ("Caught filespecification error properly")
                                        #plog((traceback.format_exc()))
                                        #breakpoint()
                                        retryarchive = 11
                                        tempPTR =0
                                    except Exception as e:
                                        if 'list index out of range' in str(e):
                                            #plog((traceback.format_exc()))
                                            # This error is thrown when there is a corrupt file
                                            try:
                                                os.remove(filepath)
                                            except:
                                                #plog("Couldn't remove " + str(filepath) + " file after transfer, sending to delete queue")
                                                self.laterdelete_queue.put(filepath, block=False)
                                            retryarchive=11
                                        else:
                                            plog("couldn't send to PTR archive for some reason: ", e)
                                            #plog("Retry " + str(retryarchive))
                                            #plog(e)
                                            #plog((traceback.format_exc()))
                                            time.sleep(pow(retryarchive, 2) + 1)
                                            if retryarchive < 10:
                                                retryarchive = retryarchive+1
                                            tempPTR = 0
    
                            # If ingester fails, send to default S3 bucket.
                            if tempPTR == 0:
                                files = {"file": (filepath, fileobj)}
                                retryapi=True
                                while retryapi:
                                    try:
                                        aws_resp = g_dev["obs"].api.authenticated_request(
                                            "POST", "/upload/", {"object_name": filename})
                                        req_resp = reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=600)
        
                                        self.aws_queue.task_done()
                                        one_at_a_time = 0
                                        retryapi=False
        
                                    except:
                                        plog(traceback.format_exc())
                                        #breakpoint()
                                        plog("Connection glitch for the request post, waiting a moment and trying again")
                                        time.sleep(5)
                        
                        if broken == 1:
                        
                            #breakpoint()
                            
                            try:
                                shutil.move(filepath, self.broken_path + filename)
                            except:
                                plog ("Couldn't move " + str(filepath) + " to broken folder.")
                    except Exception as e:
                        plog ("something strange in the AWS uploader", e)
                # Send all other files to S3.
                else:
                    with open(filepath, "rb") as fileobj:
                        files = {"file": (filepath, fileobj)}
                        uploaded=False
                        while not uploaded:                            
                            try:
                                aws_resp = g_dev["obs"].api.authenticated_request(
                                    "POST", "/upload/", {"object_name": filename})
                                reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=600)
                                
                                # Only remove file if successfully uploaded
                                if ('calibmasters' not in filepath) or ('ARCHIVE_' in filepath):
                                    try:
                                        os.remove(filepath)
                                        #plog("not deleting")
                                    except:
                                        #plog("Couldn't remove " + str(filepath) + " file after transfer")
                                        self.laterdelete_queue.put(filepath, block=False)
                                
                                self.aws_queue.task_done()
                                uploaded=True
    
                            except:
                                plog(traceback.format_exc())
                                #breakpoint()
                                plog("Connection glitch for the request post, waiting a moment and trying again")
                                time.sleep(5)

                one_at_a_time = 0

                
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

        # This stopping mechanism allows for threads to close cleanly.
        # one_at_a_time=0
        while True:
            if (not self.laterdelete_queue.empty()):  # and one_at_a_time==0
                (deletefilename) = self.laterdelete_queue.get(block=False)
                #notdelete=1
                #while notdelete==1:
                #plog("Deleting: " +str(deletefilename))
                    
                self.laterdelete_queue.task_done()
                
                try:
                    os.remove(deletefilename)
                    #notdelete=0
                except:
                    #plog("failed to remove: " + str(deletefilename) + " trying again soon")
                    self.laterdelete_queue.put(deletefilename, block=False)
                    time.sleep(5)
                
                
                # one_at_a_time=0
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
                
                
                #pickletime=time.time()
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



                #[hdusmalldata, smartstackid, paths, pier_side, is_osc, osc_bayer, osc_background_cut,osc_brightness_enhance, osc_contrast_enhance,\
                #     osc_colour_enhance, osc_saturation_enhance, osc_sharpness_enhance, transpose_jpeg, flipx_jpeg, flipy_jpeg, rotate180_jpeg,rotate90_jpeg, \
                #         rotate270_jpeg, crop_preview, yb, yt, xl, xr, squash_on_x_axis]
                
                #pickletime=time.time()
                
                jpeg_subprocess=subprocess.Popen(['python','subprocesses/mainjpeg.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
                              
                
                
                pickle.dump([hdusmalldata, smartstackid, paths, pier_side, is_osc, osc_bayer, osc_background_cut,osc_brightness_enhance, osc_contrast_enhance,\
                     osc_colour_enhance, osc_saturation_enhance, osc_sharpness_enhance, transpose_jpeg, flipx_jpeg, flipy_jpeg, rotate180_jpeg,rotate90_jpeg, \
                         rotate270_jpeg, crop_preview, yb, yt, xl, xr, squash_on_x_axis], jpeg_subprocess.stdin)
                
                #pickle.dump([hdusmalldata, smartstackid, paths, pier_side, is_osc, osc_bayer, osc_background_cut,osc_brightness_enhance, osc_contrast_enhance,\
                #    osc_colour_enhance, osc_saturation_enhance, osc_sharpness_enhance, transpose_jpeg, flipx_jpeg, flipy_jpeg, rotate180_jpeg,rotate90_jpeg, \
                #        rotate270_jpeg, crop_preview, yb, yt, xl, xr, squash_on_x_axis], open('testjpegpickle','wb'))
                    
                    
                del hdusmalldata
                #plog ("pickling time: " + str(time.time()-pickletime))
                    
                # Essentially wait until the subprocess is complete
                jpeg_subprocess.communicate()
                    
                #plog ("jpeg pickle time" + str(time.time()-pickletime))

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
                        plog("JPEG constructed and sent: " +str(time.time() - osc_jpeg_timer_start)+ "s")
                    except:
                        plog(
                            "there was an issue saving the preview jpg. Pushing on though"
                        )
                        
                    
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

                #sep_timer_begin=time.time()
                
                (hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position, nativebin) = self.sep_queue.get(block=False)

                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']) :
                    plog ("Too bright to consider photometry!")
                    # If it doesn't go through SEP then the fits header text file needs to be dumped here
                    text = open(
                        im_path + text_name, "w"
                    )  # This is needed by AWS to set up database.
                    #breakpoint()
                    text.write(str(hduheader))
                    text.close()
                else:
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
                                                                                                       .name]["settings"]['focus_image_crop_height'], is_osc,interpolate_for_focus,bin_for_focus,focus_bin_value,interpolate_for_sep,bin_for_sep,sep_bin_value,focus_jpeg_size,saturate,minimum_realistic_seeing,nativebin
                                                                                                                                                                               ], sep_subprocess.stdin)
                                                                                                                                 
                                                                                                                                 
                    # pickle.dump([hdufocusdata, pixscale, readnoise, avg_foc, focus_image, im_path, text_name, hduheader, cal_path, cal_name, frame_type, focus_position, g_dev['events'],ephem.now(),self.config["camera"][g_dev['cam']
                    #                                          .name]["settings"]['focus_image_crop_width'], self.config["camera"][g_dev['cam']
                    #                                                                                    .name]["settings"]['focus_image_crop_height'], is_osc,interpolate_for_focus,bin_for_focus,focus_bin_value,interpolate_for_sep,bin_for_sep,sep_bin_value,focus_jpeg_size,saturate,minimum_realistic_seeing
                    #                                                                                                                                                           ], open('subprocesses/testSEPpickle','wb'))
        
                    #
                    #plog ("pickling time: " + str(time.time()-pickletime))
                        
                    # Essentially wait until the subprocess is complete
                    sep_subprocess.communicate()
    
    
                    
    
                    # LOADING UP THE SEP FILE HERE AGAIN
                    
    
                    if os.path.exists(im_path + text_name.replace('.txt', '.sep')):
                        try:
                            sources = Table.read(im_path + text_name.replace('.txt', '.sep'), format='csv')
                            
                            try:
                                g_dev['cam'].enqueue_for_fastAWS(200, im_path, text_name.replace('.txt', '.sep'))
                                #plog("Sent SEP up")
                            except:
                                plog("Failed to send SEP up for some reason")
                            
                            #DONUT IMAGE DETECTOR.
                            #plog ("The Fitzgerald Magical Donut detector")
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
                                rfr = round(np.median(fwhmcalc) * pixscale * g_dev['cam'].native_bin, 3)
                                rfs = round(np.std(fwhmcalc) * pixscale * g_dev['cam'].native_bin, 3)
                                plog("\nImage FWHM:  " + str(rfr) + "+/-" + str(rfs) + " arcsecs, " + str(rfp)
                                     + " pixels.")
                                # breakpoint()
                                g_dev['cam'].expresult["FWHM"] = rfr
                                g_dev['cam'].expresult["mean_focus"] = avg_foc
                                g_dev['cam'].expresult['No_of_sources'] = len(sources)
            
            
                            if focus_image != True:
                                # Focus tracker code. This keeps track of the focus and if it drifts
                                # Then it triggers an autofocus.
                                g_dev["foc"].focus_tracker.pop(0)
                                g_dev["foc"].focus_tracker.append(round(rfr, 3))
                                plog("Last ten FWHM: " + str(g_dev["foc"].focus_tracker) + " Median: " + str(np.nanmedian(g_dev["foc"].focus_tracker)) + " Last Solved: " + str(g_dev["foc"].last_focus_fwhm))
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
                                            + ".",
                                            p_level="INFO",
                                        )
                        except Exception as e:
                            plog ("something odd occured in the reinterpretation of the SEP file")
                            plog(traceback.format_exc())
                            
                    else:
                        plog ("Did not find a source list from SEP for this image.")    
                        #g_dev['cam'].expresult["error"] = True
                        g_dev['cam'].expresult['FWHM'] = np.nan
                        g_dev['cam'].expresult['No_of_sources'] = np.nan
                        
                    
                    if os.path.exists(im_path + text_name.replace('.txt', '.rad')):
                        try:
                            g_dev['cam'].enqueue_for_fastAWS(250, im_path, text_name.replace('.txt', '.rad'))
                            #plog("Sent SEP up")
                        except:
                            plog("Failed to send RAD up for some reason")
                    
                    if frame_type == 'focus':
                        g_dev["cam"].enqueue_for_fastAWS(100, im_path, text_name.replace('EX00.txt', 'EX10.jpg'))
                    
                    try:
                        g_dev['cam'].enqueue_for_fastAWS(180, im_path, text_name.replace('.txt', '.his'))
                        #plog("Sent SEP up")
                    except:
                        plog("Failed to send HIS up for some reason")
                    
                    
    
                    if self.config['keep_focus_images_on_disk']:
                        g_dev['cam'].to_slow_process(1000, ('focus', cal_path + cal_name, hdufocusdata, hduheader,
                                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
    
                        if self.config["save_to_alt_path"] == "yes":
                            g_dev['cam'].to_slow_process(1000, ('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocusdata, hduheader,
                                                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                
                g_dev['cam'].enqueue_for_fastAWS(10, im_path, text_name)

                del hdufocusdata

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
                #psolve_timer_begin = time.time()
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
                     pixscale, pointing_ra, pointing_dec, platesolve_crop, bin_for_platesolve, platesolve_bin_factor, g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]], platesolve_subprocess.stdin)
                                                                                                                                 
                    #pickle.dump([hdufocusdata, hduheader, self.local_calibration_path, cal_name, frame_type, time_platesolve_requested, 
                    # pixscale, pointing_ra, pointing_dec, platesolve_crop, bin_for_platesolve, platesolve_bin_factor, g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]], open('subprocesses/testplatesolvepickle','wb'))                                                                                                             

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
                        
                    else:
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
                        #solved_arcsecperpixel = solve["arcsec_per_pixel"]
                        #solved_rotangledegs = solve["rot_angle_degs"]
                        err_ha = target_ra - solved_ra
                        err_dec = target_dec - solved_dec
                        #solved_arcsecperpixel = solve["arcsec_per_pixel"]
                        #solved_rotangledegs = solve["rot_angle_degs"]
                        plog("Deviation from plate solution in ra: " + str(round(err_ha * 15 * 3600, 2)) + " & dec: " + str (round(err_dec * 3600, 2)) + " asec")
                        
                        #breakpoint()
                        
                        self.last_platesolved_ra = solve["ra_j2000_hours"]
                        self.last_platesolved_dec = solve["dec_j2000_degrees"]
                        self.last_platesolved_ra_err = target_ra - solved_ra
                        self.last_platesolved_dec_err = target_dec - solved_dec
                        
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
                            err_ha * 15 * 3600 > 3600
                            or err_dec * 3600 > 3600
                            or err_ha * 15 * 3600 < -3600
                            or err_dec * 3600 < -3600
                        ) and self.config["mount"]["mount1"][
                            "permissive_mount_reset"
                        ] == "yes":
                            g_dev["mnt"].reset_mount_reference()
                            plog("I've  reset the mount_reference.")
                            g_dev["mnt"].current_icrs_ra = solved_ra
                            #    "ra_j2000_hours"
                            # ]
                            g_dev["mnt"].current_icrs_dec = solved_dec
                            #    "dec_j2000_hours"
                            # ]
                            err_ha = 0
                            err_dec = 0
    
                            plog("Platesolve has found that the current suggested pointing is way off!")
                            plog("This is more than a simple nudge, so not nudging the scope.")
                            
                            
                            #plog("Platesolve is requesting to move back on target!")
                            #g_dev['mnt'].mount.SlewToCoordinatesAsync(target_ra, target_dec)
    
                            #self.pointing_correction_requested_by_platesolve_thread = True
                            #self.pointing_correction_request_time = time.time()
                            #self.pointing_correction_request_ra = target_ra
                            #self.pointing_correction_request_dec = target_dec
    
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
                                #plog(str(g_dev["mnt"].pier_side) + " <-- pierside TEMP MTF reporting")
                                #ra_correction_multiplier= self.config['pointing_correction_ra_multiplier']
                               # dec_correction_multiplier= self.config['pointing_correction_dec_multiplier']
                                self.pointing_correction_requested_by_platesolve_thread = True
                                self.pointing_correction_request_time = time.time()
                                self.pointing_correction_request_ra = pointing_ra + err_ha #* ra_correction_multiplier)
                                self.pointing_correction_request_dec = pointing_dec + err_dec# * dec_correction_multiplier)
                                
                                if not self.config['mount_reference_model_off']:
                                    if target_dec > -85 and target_dec < 85:
                                        try:
                                            #try:
                                            #    g_dev["mnt"].pier_side=g_dev['mnt'].mount.sideOfPier
                                            #except:
                                            #    plog("MTF chase this later")
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
                                #tempfilename=self.local_bias_folder + slow_process[1].replace('.fits','.fits.fz')
                                tempfilename = self.local_bias_folder + slow_process[1].replace('.fits', '.npy')
                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_bias_to_store']
                                n_files = len(glob.glob(self.local_bias_folder + '*.n*'))
                                while n_files > max_files:
                                    list_of_files = glob.glob(self.local_bias_folder + '*.n*')
                                    n_files = len(list_of_files)
                                    oldest_file = min(list_of_files, key=os.path.getctime)
                                    os.remove(oldest_file)
                                    #plog("removed old bias. ")# + str(oldest_file))

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
                                    #plog("removed old dark. ")# + str(oldest_file))

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
                                    #plog("removed old flat. ") # + str(oldest_file))

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
                    
                    temphduheader["BZERO"] = 0  # Make sure there is no integer scaling left over
                    temphduheader["BSCALE"] = 1  # Make sure there is no integer scaling left over
                    
                    
                    #hdufz.verify("fix")
                    
                    #hdufz.header["DATE"] = (
                    #    datetime.date.strftime(
                    #        datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
                    #    ),
                    #    "Date FITS file was written"
                    #)
                    
                    #breakpoint()

                    if not self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:

                        

                        hdufz = fits.CompImageHDU(
                            np.array(slow_process[2], dtype=np.float32), temphduheader
                        )

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
                                    #slow_process[1], overwrite=True, output_verify='silentfix'
                                    slow_process[1], overwrite=True
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
                            
                            newhdured = slow_process[2][::2, ::2]
                            GTRonly = slow_process[2][::2, 1::2]
                            GBLonly = slow_process[2][1::2, ::2]
                            newhdublue = slow_process[2][1::2, 1::2]

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

                            
                            hdufz = fits.CompImageHDU(
                                np.array(newhdured, dtype=np.float32), temphduheader
                            )
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'R1-EX'), overwrite=True#, output_verify='silentfix'
                            )  # Save full fz file locally
                            del newhdured
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'R1-EX')
                                )

                            # Save and send G1
                            temphduheader['FILTER'] = tempfilter + '_G1'
                            
                            hdufz = fits.CompImageHDU(
                                np.array(GTRonly, dtype=np.float32), temphduheader
                            )
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'G1-EX'), overwrite=True#, output_verify='silentfix'
                            )  # Save full fz file locally
                            del GTRonly
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'G1-EX')
                                )

                            # Save and send G2
                            temphduheader['FILTER'] = tempfilter + '_G2'
                           
                            hdufz = fits.CompImageHDU(
                                np.array(GBLonly, dtype=np.float32), temphduheader
                            )
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'G2-EX'), overwrite=True#, output_verify='silentfix'
                            )  # Save full fz file locally
                            del GBLonly
                            if self.config['send_files_at_end_of_night'] == 'no':
                                g_dev['cam'].enqueue_for_AWS(
                                    26000000, '', tempfilename.replace('-EX', 'G2-EX')
                                )

                            # Save and send B1
                            temphduheader['FILTER'] = tempfilter + '_B1'
                            
                            hdufz = fits.CompImageHDU(
                                np.array(newhdublue, dtype=np.float32), temphduheader
                            )
                            hdufz.writeto(
                                tempfilename.replace('-EX', 'B1-EX'), overwrite=True#, output_verify='silentfix'
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
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                retryapi=True
                while retryapi:
                    try:
                        aws_resp = g_dev["obs"].api.authenticated_request(
                            "POST", "/upload/", {"object_name": filename})
                        retryapi=False
                    except:
                        plog ("connection glitch in fast_aws thread. Waiting 5 seconds.")
                        time.sleep(5)
                # Send all other files to S3.               

                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    #print('\nfiles;  ', files)
                    while True:
                        try:
                            reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=45)

                            break
                        except:
                            plog("Non-fatal connection glitch for a file posted.")
                            plog(files)
                            time.sleep(5)
                self.fast_queue.task_done()
                one_at_a_time = 0

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
            reqs.post(url_log, body, timeout=5)
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
                        
                        g_dev['cam'].to_slow_process(1000,('reduced', paths["red_path"] + paths["red_name01"], imgdata, img[0].header, \
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
                    
                    #print ("pierside")
                    #print (pier_side)
                    #print (picklepayload)
                    #pickle.dump(picklepayload, open('subprocesses/testsmartstackpickle','wb')) 
                    #sys.exit()
                    
                                           
                    smartstack_subprocess=subprocess.Popen(['python','subprocesses/SmartStackprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
                                     
                    pickle.dump(picklepayload, smartstack_subprocess.stdin)
                                                                                                                                 
                    #pickle.dump(picklepayload, open('subprocesses/testsmartstackpickle','wb'))                                                                                                             
                        
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
                
                if self.auto_centering_off:
                    plog ("Telescope off-center, but auto-centering turned off")
                else:
                    plog("Re-centering Telescope Slightly.")
                    self.send_to_user("Re-centering Telescope Slightly.")
                    g_dev['mnt'].mount.SlewToCoordinatesAsync(g_dev['obs'].pointing_correction_request_ra, g_dev['obs'].pointing_correction_request_dec)
                    g_dev['obs'].time_of_last_slew = time.time()
                    wait_for_slew()
    
    def get_enclosure_status_from_aws(self):
        
        obsy = self.wema_name
        """Sends an update to the status endpoint."""
        uri_status = f"https://status.photonranch.org/status/{obsy}/enclosure/"
        # None of the strings can be empty. Otherwise this put faults.
        #payload = {"statusType": str(column), "status": status_to_send}

        #try:

        #    data = json.dumps(payload)
        #except Exception as e:
        #    plog("Failed to create status payload. Usually not fatal:  ", e)

        #breakpoint()

        try:
            aws_enclosure_status=reqs.get(uri_status, timeout=20)
            
            aws_enclosure_status=aws_enclosure_status.json()
            
            for enclosurekey in aws_enclosure_status['status']['enclosure']['enclosure1'].keys():
                aws_enclosure_status['status']['enclosure']['enclosure1'][enclosurekey]=aws_enclosure_status['status']['enclosure']['enclosure1'][enclosurekey]['val']
        
            
            # aws_enclosure_status['status']['enclosure']['enclosure1']['enclosure_mode'] = aws_enclosure_status['status']['enclosure']['enclosure1']['enclosure_mode']['val']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['dome_azimuth'] = aws_enclosure_status['status']['enclosure']['enclosure1']['dome_azimuth']['val']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['enclosure_synchronized'] = aws_enclosure_status['status']['enclosure']['enclosure1']['enclosure_synchronized']['val']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['dome_slewing'] = aws_enclosure_status['status']['enclosure']['enclosure1']['dome_slewing']['val']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['shutter_status'] = aws_enclosure_status['status']['enclosure']['enclosure1']['shutter_status']['val']
            
            # #breakpoint()
            # # New Tim Entries
            # if aws_enclosure_status['status']['enclosure']['enclosure1']['shutter_status'] =='Open':
            #     aws_enclosure_status['status']['enclosure']['enclosure1']['observatory_open'] = True
            #     aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_bad_weather'] = False
            #     aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_daytime'] = False
            #     aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_manual_mode'] = False
            # else:
            #     aws_enclosure_status['status']['enclosure']['enclosure1']['observatory_open'] = False
            #     if not aws_enclosure_status['status']['enclosure']['enclosure1']['enclosure_mode'] == 'Automatic':
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_manual_mode'] = True
            #     else:
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_manual_mode'] = False
            #     if g_dev['obs'].ocn_status['wx_ok'] == 'Unknown':
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_bad_weather'] = False
            #     elif g_dev['obs'].ocn_status['wx_ok'] == 'No':
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_bad_weather'] = True
            #     else:
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_bad_weather'] = False
            #         # NEED TO INCLUDE WEATHER REPORT AND FITZ NUMBER HERE
            #     if g_dev['events']['Cool Down, Open'] < ephem.now() or ephem.now() < g_dev['events']['Close and Park'] > ephem.now():
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_daytime'] = True
            #     else:
            #         aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_daytime'] = False
                    
                    
            
            
            # g_dev['obs'].ocn_status 
            
            # aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_bad_weather']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_daytime']
            # aws_enclosure_status['status']['enclosure']['enclosure1']['shut_reason_manual_mode']
            
            #aws_enclosure_status['server_timestamp_ms'] = int(time.time())
            #aws_enclosure_status['site'] = self.obs_id
            #plog(aws_enclosure_status)
            #breakpoint()
            try:
                # To stop status's filling up the queue under poor connection conditions
                # There is a size limit to the queue
                if self.send_status_queue.qsize() < 7:
                    self.send_status_queue.put((self.name, 'enclosure', aws_enclosure_status['status']), block=False)
                #self.send_status_queue.put((self.name, 'enclosure', aws_enclosure_status), block=False)
                
            #breakpoint()
            except Exception as e:
                #breakpoint()
                plog ("aws enclosure send failed ", e)
                #pass
            
            aws_enclosure_status=aws_enclosure_status['status']['enclosure']['enclosure1']
        
        except Exception as e:
            plog("Failed to get aws enclosure status. Usually not fatal:  ", e)
        
        #if aws_enclosure_status["shutter_status"] in ['Closed','closed']:
        #    g_dev['seq'].time_roof_last_shut=time.time()
        
        try:
            if g_dev['seq'].last_roof_status == 'Closed' and aws_enclosure_status["shutter_status"] in ['Open','open']:
                g_dev['seq'].time_roof_last_opened=time.time()  
                g_dev['seq'].last_roof_status == 'Open'
                
            if g_dev['seq'].last_roof_status == 'Open' and aws_enclosure_status["shutter_status"] in ['Closed','closed']:
                g_dev['seq'].last_roof_status == 'Closed'
        except:
            plog("Glitch on getting shutter status in aws call.")
        
        try:
        
            status = {'shutter_status': aws_enclosure_status["shutter_status"],
                      'enclosure_synchronized': aws_enclosure_status["enclosure_synchronized"],  # self.following, 20220103_0135 WER
                      'dome_azimuth': aws_enclosure_status["dome_azimuth"],
                      'dome_slewing': aws_enclosure_status["dome_slewing"],
                      'enclosure_mode': aws_enclosure_status["enclosure_mode"]}#,
                      #'enclosure_message': "No message"}

        except:
            try:
                status = {'shutter_status': aws_enclosure_status["shutter_status"]}
            except:
                plog ('failed enclosure status!')
                status = {'shutter_status': 'Unknown'}

        return status
    
    def get_weather_status_from_aws(self):
        
        obsy = self.wema_name
        """Sends an update to the status endpoint."""
        uri_status = f"https://status.photonranch.org/status/{obsy}/weather/"
        # None of the strings can be empty. Otherwise this put faults.
        #payload = {"statusType": str(column), "status": status_to_send}

        #try:

        #    data = json.dumps(payload)
        #except Exception as e:
        #    plog("Failed to create status payload. Usually not fatal:  ", e)

        #breakpoint()



        try:
            aws_weather_status=reqs.get(uri_status, timeout=20)
            aws_weather_status=aws_weather_status.json()
            #breakpoint()
        except Exception as e:
            plog("Failed to get aws enclosure status. Usually not fatal:  ", e)
            aws_weather_status={} 
            aws_weather_status['status']={}
            aws_weather_status['status']['observing_conditions']={}
            aws_weather_status['status']['observing_conditions']['observing_conditions1'] = None
            
            
        if aws_weather_status['status']['observing_conditions']['observing_conditions1'] == None:
            aws_weather_status['status']['observing_conditions']['observing_conditions1'] = {'wx_ok': 'Unknown'} 
        else:
            #breakpoint()
            for weatherkey in aws_weather_status['status']['observing_conditions']['observing_conditions1'].keys():
                aws_weather_status['status']['observing_conditions']['observing_conditions1'][weatherkey]=aws_weather_status['status']['observing_conditions']['observing_conditions1'][weatherkey]['val']
        
        
        try:
            # To stop status's filling up the queue under poor connection conditions
            # There is a size limit to the queue
            if self.send_status_queue.qsize() < 7:            
                self.send_status_queue.put((self.name, 'weather', aws_weather_status['status']), block=False)
            #self.send_status_queue.put((self.name, 'enclosure', aws_enclosure_status), block=False)
            
        #breakpoint()
        except Exception as e:
            #breakpoint()
            plog ("aws enclosure send failed ", e)
            #pass
        
        aws_weather_status=aws_weather_status['status']['observing_conditions']['observing_conditions1']
                        
        return aws_weather_status

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