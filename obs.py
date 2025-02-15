# -*- coding: utf-8 -*-
"""
obs.py  obs.py  obs.py  obs.py  obs.py  obs.py  obs.py  obs.py  obs.py  obs.py
Observatory is the central organising part of a given observatory system.

It deals with connecting all the devices together and deals with decisions that
involve multiple devices and fundamental operations of the OBS.

It also organises the various queues that process, send, slice and dice data.
"""
# The ingester should only be imported after environment variables are loaded in.
from dotenv import load_dotenv
load_dotenv(".env")
import ocs_ingester.exceptions

from ocs_ingester.ingester import upload_file_and_ingest_to_archive

from requests.adapters import HTTPAdapter, Retry
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
import math
import shutil
import glob
import subprocess
import pickle

from astropy.io import fits
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord, get_sun, AltAz
from astropy.time import Time
from astropy import units as u

import bottleneck as bn
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
from devices.rotator import Rotator
#from devices.selector import Selector
#from devices.screen import Screen
from devices.sequencer import Sequencer
from ptr_events import Events

from ptr_utility import plog
from astropy.utils.exceptions import AstropyUserWarning
import warnings

warnings.simplefilter("ignore", category=AstropyUserWarning)

reqs = requests.Session()
retries = Retry(total=3, backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount("http://", HTTPAdapter(max_retries=retries))



def test_connect(host="http://google.com"):
    # This just tests the net connection
    # for certain safety checks
    # If it cannot connect to the internet for an extended period of time.
    # It will park
    try:
        urllib.request.urlopen(host)  # Python 3.x
        return True
    except:
        return False


def ra_dec_fix_hd(ra, dec):
    # Get RA and Dec into the proper domain
    # RA in hours, Dec in degrees
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
    """
    Get a list of all the PIDs of a all the running process whose name contains
    the given string processName
    """
    listOfProcessObjects = []
    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=["pid", "name", "create_time"])
            # Check if process name contains the given name string.
            if processName.lower() in pinfo["name"].lower():
                listOfProcessObjects.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return listOfProcessObjects


def authenticated_request(method: str, uri: str, payload: dict = None) -> str:
    # Populate the request parameters. Include data only if it was sent.
    base_url = "https://api.photonranch.org/api"
    request_kwargs = {
        "method": method,
        "timeout": 10,
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
    # if column == 'weather':
    #     print("Did not send spurious weathr report.")
    #     return
    try:
        data = json.dumps(payload)
        #print(data)
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
        g_dev["name"] = name

        self.config = ptr_config
        self.wema_name = self.config["wema_name"]
        self.wema_config = self.get_wema_config() # fetch the wema config from AWS

        # Used to tell whether the obs is currently rebooting theskyx
        self.rebooting_theskyx = False

        # Creation of directory structures if they do not exist already
        self.obsid_path = str(
            ptr_config["archive_path"] + "/" + self.name + "/"
        ).replace("//", "/")
        g_dev["obsid_path"] = self.obsid_path
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path, mode=0o777)
        self.local_calibration_path = (
            ptr_config["local_calibration_path"] + self.config["obs_id"] + "/"
        )
        if not os.path.exists(ptr_config["local_calibration_path"]):
            os.makedirs(ptr_config["local_calibration_path"], mode=0o777)
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path, mode=0o777)

        if self.config["save_to_alt_path"] == "yes":
            self.alt_path = ptr_config["alt_path"] + \
                self.config["obs_id"] + "/"
            if not os.path.exists(ptr_config["alt_path"]):
                os.makedirs(ptr_config["alt_path"], mode=0o777)
            if not os.path.exists(self.alt_path):
                os.makedirs(self.alt_path, mode=0o777)

        if not os.path.exists(self.obsid_path + "ptr_night_shelf"):
            os.makedirs(self.obsid_path + "ptr_night_shelf", mode=0o777)
        if not os.path.exists(self.obsid_path + "archive"):
            os.makedirs(self.obsid_path + "archive", mode=0o777)
        if not os.path.exists(self.obsid_path + "tokens"):
            os.makedirs(self.obsid_path + "tokens", mode=0o777)
        if not os.path.exists(self.obsid_path + "astropycache"):
            os.makedirs(self.obsid_path + "astropycache", mode=0o777)

        # Local Calibration Paths
        main_camera_device_name = self.config["device_roles"]["main_cam"]
        camera_name_for_directories = self.config["camera"][main_camera_device_name]["name"]

        # Base path and camera name
        base_path = self.local_calibration_path

        def create_directories(base_path, camera_name, subdirectories):
            """
            Create directories if they do not already exist.
            """
            for subdir in subdirectories:
                path = os.path.join(base_path, "archive", camera_name, subdir)
                if not os.path.exists(path):
                    os.makedirs(path, mode=0o777)

        # Subdirectories to create
        subdirectories = [
            "calibmasters",
            "localcalibrations",
            "localcalibrations/darks",
            "localcalibrations/darks/narrowbanddarks",
            "localcalibrations/darks/broadbanddarks",
            "localcalibrations/darks/fortymicroseconddarks",
            "localcalibrations/darks/fourhundredmicroseconddarks",
            "localcalibrations/darks/pointzerozerofourfivedarks",
            "localcalibrations/darks/onepointfivepercentdarks",
            "localcalibrations/darks/fivepercentdarks",
            "localcalibrations/darks/tenpercentdarks",
            "localcalibrations/darks/quartersecdarks",
            "localcalibrations/darks/halfsecdarks",
            "localcalibrations/darks/sevenfivepercentdarks",
            "localcalibrations/darks/onesecdarks",
            "localcalibrations/darks/oneandahalfsecdarks",
            "localcalibrations/darks/twosecdarks",
            "localcalibrations/darks/threepointfivesecdarks",
            "localcalibrations/darks/fivesecdarks",
            "localcalibrations/darks/sevenpointfivesecdarks",
            "localcalibrations/darks/tensecdarks",
            "localcalibrations/darks/fifteensecdarks",
            "localcalibrations/darks/twentysecdarks",
            "localcalibrations/darks/thirtysecdarks",
            "localcalibrations/biases",
            "localcalibrations/flats",
        ]

        # Create the directories
        create_directories(base_path, camera_name_for_directories, subdirectories)

        # Set calib masters folder
        self.calib_masters_folder = os.path.join(base_path, "archive", camera_name_for_directories, "calibmasters") + "/"

        self.local_dark_folder = (
            self.local_calibration_path
            + "archive/"
            + camera_name_for_directories
            + "/localcalibrations/darks"
            + "/"
        )
        self.local_bias_folder = (
            self.local_calibration_path
            + "archive/"
            + camera_name_for_directories
            + "/localcalibrations/biases"
            + "/"
        )
        self.local_flat_folder = (
            self.local_calibration_path
            + "archive/"
            + camera_name_for_directories
            + "/localcalibrations/flats"
            + "/"
        )

        # Directories for broken and orphaned upload files
        self.orphan_path = (
            self.config["archive_path"] + "/" + self.name + "/" + "orphans/"
        )
        if not os.path.exists(self.orphan_path):
            os.makedirs(self.orphan_path, mode=0o777)
        self.broken_path = (
            self.config["archive_path"] + "/" + self.name + "/" + "broken/"
        )
        if not os.path.exists(self.broken_path):
            os.makedirs(self.broken_path, mode=0o777)

        # Clear out smartstacks directory
        try:
            shutil.rmtree(self.local_calibration_path + "smartstacks")
        except:
            pass
        if not os.path.exists(self.local_calibration_path + "smartstacks"):
            os.makedirs(self.local_calibration_path + "smartstacks", mode=0o777)

        # Copy in the latest fz_archive subprocess file to the smartstacks folder
        shutil.copy(
            "subprocesses/fz_archive_file.py",
            self.local_calibration_path + "smartstacks/fz_archive_file.py",
        )
        shutil.copy(
            "subprocesses/local_reduce_file_subprocess.py",
            self.local_calibration_path + "smartstacks/local_reduce_file_subprocess.py",
        )

        # # Clear out substacks directory     #This is redundant
        # try:
        #     shutil.rmtree(self.local_calibration_path + "substacks")
        # except:
        #     pass
        # if not os.path.exists(self.local_calibration_path + "substacks"):
        #     os.makedirs(self.local_calibration_path + "substacks")

        # # Orphan and Broken paths
        # self.orphan_path = (
        #     self.config["archive_path"] + "/" + self.name + "/" + "orphans/"
        # )
        # if not os.path.exists(self.orphan_path):
        #     os.makedirs(self.orphan_path)

        # self.broken_path = (
        #     self.config["archive_path"] + "/" + self.name + "/" + "broken/"
        # )
        # if not os.path.exists(self.broken_path):
        #     os.makedirs(self.broken_path)

        # Software Kills.
        # There are some software that really benefits from being restarted from
        # scratch on Windows, so on bootup of obs.py, the system closes them down
        # Reconnecting the devices reboots the softwares later on.
        processes = [
            "Gemini Software.exe",
            "OptecGHCommander.exe",
            "AltAzDSConfig.exe",
            "ASCOM.AltAzDS.exe",
            "AstroPhysicsV2 Driver.exe",
            "AstroPhysicsCommandCenter.exe",
            "TheSkyX.exe",
            "TheSky64.exe",
            "PWI4.exe",
            "PWI3.exe",
            "FitsLiberator.exe"
        ]

        if name != "tbo2": # saves a few seconds for the simulator site.
            for process in processes:
                try:
                    os.system(f'taskkill /IM "{process}" /F')
                except Exception:
                    pass


        listOfProcessIds = findProcessIdByName("maxim_dl")
        for pid in listOfProcessIds:
            pid_num = pid["pid"]
            plog("Terminating existing Maxim process:  ", pid_num)
            p2k = psutil.Process(pid_num)
            p2k.terminate()

        # Initialisation of variables best explained elsewhere
        self.status_interval = 0
        self.status_count = 0
        self.status_upload_time = 0.5
        self.time_last_status = time.time() - 3000
        self.pulse_timer=time.time()

        self.check_lightning = self.config.get("has_lightning_detector", False)

        # Timers to only update status at regular specified intervals.
        self.observing_status_timer = datetime.datetime.now() - datetime.timedelta(days=1)
        self.observing_check_period = self.config["observing_check_period"]
        self.enclosure_status_timer = datetime.datetime.now() - datetime.timedelta(days=1)
        self.enclosure_check_period = self.config["enclosure_check_period"]
        self.obs_settings_upload_timer = time.time() - 20
        self.obs_settings_upload_period = 60

        self.last_time_report_to_console = time.time() - 180  #NB changed fro

        self.last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        self.images_since_last_solve = 10000

        self.project_call_timer = time.time()
        self.get_new_job_timer = time.time()
        self.scan_request_timer = time.time()

        # ANd one for scan requests
        self.cmd_queue = queue.Queue(maxsize=0)
        self.currently_scan_requesting = True
        self.scan_request_queue = queue.Queue(maxsize=0)
        self.scan_request_thread = threading.Thread(
            target=self.scan_request_thread)
        self.scan_request_thread.daemon = True
        self.scan_request_thread.start()

        # And one for updating calendar blocks
        self.currently_updating_calendar_blocks = False
        self.calendar_block_queue = queue.Queue(maxsize=0)
        self.calendar_block_thread = threading.Thread(
            target=self.calendar_block_thread)
        self.calendar_block_thread.daemon = True
        self.calendar_block_thread.start()

        self.too_hot_temperature = self.config[
            "temperature_at_which_obs_too_hot_for_camera_cooling"
        ]
        self.warm_report_timer = time.time() - 600

        # Keep track of how long it has been since the last activity of slew or exposure
        # This is useful for various functions... e.g. if telescope idle for an hour, park.
        self.time_of_last_exposure = time.time()
        self.time_of_last_slew = time.time()
        self.time_of_last_pulse = time.time()

        # Keep track of how long it has been since the last live connection to the internet
        self.time_of_last_live_net_connection = time.time()

        # Initialising various flags best explained elsewhere
        self.env_exists = os.path.exists(
            os.getcwd() + "\.env"
        )  # Boolean, check if .env present
        self.stop_processing_command_requests = False
        self.platesolve_is_processing = False
        self.stop_all_activity = False  # This is used to stop the camera or sequencer
        self.exposure_halted_indicator = False
        self.camera_sufficiently_cooled_for_calibrations = True
        self.last_slew_was_pointing_slew = False
        self.open_and_enabled_to_observe = False
        self.net_connection_dead = False

        # Set default obs safety settings at bootup
        self.scope_in_manual_mode = self.config["scope_in_manual_mode"]
        self.moon_checks_on = self.config["moon_checks_on"]
        self.sun_checks_on = self.config["sun_checks_on"]
        self.altitude_checks_on = self.config["altitude_checks_on"]
        self.daytime_exposure_time_safety_on = self.config["daytime_exposure_time_safety_on"]
        self.mount_reference_model_off = self.config["mount_reference_model_off"]

        self.admin_owner_commands_only = self.config.get("owner_only_commands", False)
        self.assume_roof_open = self.config.get("simulate_open_roof", False)
        self.auto_centering_off = self.config.get("auto_centering_off", False)


        # Instantiate the helper class for astronomical events
        # Soon the primary event / time values can come from AWS.  NB NB   I send them there! Why do we want to put that code in AWS???
        self.astro_events = Events(self.config, self.wema_config)
        self.astro_events.calculate_events()
        self.astro_events.display_events()

        # If the camera is detected as substantially (20 degrees) warmer than the setpoint
        # during safety checks, it will keep it warmer for about 20 minutes to make sure
        # the camera isn't overheating, then return it to its usual temperature.
        self.camera_overheat_safety_warm_on = False
        # self.camera_overheat_safety_warm_on = self.config['warm_camera_during_daytime_if_too_hot']
        self.camera_overheat_safety_timer = time.time()
        # Some things you don't want to check until the camera has been cooling for a while.
        self.camera_time_initialised = time.time()
        # You want to make sure that the camera has been cooling for a while at the setpoint
        # Before taking calibrations to ensure the sensor is evenly cooled
        self.last_time_camera_was_warm = time.time() - 60

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
        self.last_platesolved_dec = np.nan
        self.last_platesolved_ra_err = np.nan
        self.last_platesolved_dec_err = np.nan
        self.platesolve_errors_in_a_row = 0

        self.sync_after_platesolving = False

        self.worst_potential_pointing_in_arcseconds = 30000

        # Rotator vs mount vs camera sync stuff
        self.rotator_has_been_checked_since_last_slew = False

        g_dev["obs"] = self
        g_dev["obsid"] = ptr_config["obs_id"]

        self.currently_updating_status = False

        # Use the configuration to instantiate objects for all devices.
        # Also configure device roles in here.
        self.create_devices()

        self.last_update_complete = time.time() - 5

        self.mountless_operation = False
        if self.devices["mount"] == None:
            plog("Engaging mountless operations. Telescope set in manual mode")
            self.mountless_operation = True
            self.scope_in_manual_mode = True

        self.ptrarchive_queue = queue.PriorityQueue(maxsize=0)
        self.ptrarchive_queue_thread = threading.Thread(
            target=self.send_to_ptrarchive, args=()
        )
        self.ptrarchive_queue_thread.daemon = True
        self.ptrarchive_queue_thread.start()

        self.fast_queue = queue.Queue(maxsize=0)
        self.fast_queue_thread = threading.Thread(
            target=self.fast_to_ui, args=())
        self.fast_queue_thread.daemon = True
        self.fast_queue_thread.start()

        self.file_wait_and_act_queue = queue.Queue(maxsize=0)
        self.file_wait_and_act_queue_thread = threading.Thread(
            target=self.file_wait_and_act, args=()
        )
        self.file_wait_and_act_queue_thread.daemon = True
        self.file_wait_and_act_queue_thread.start()

        self.mediumui_queue = queue.PriorityQueue(maxsize=0)
        self.mediumui_thread = threading.Thread(
            target=self.medium_to_ui, args=())
        self.mediumui_thread.daemon = True
        self.mediumui_thread.start()

        self.calibrationui_queue = queue.PriorityQueue(maxsize=0)
        self.calibrationui_thread = threading.Thread(
            target=self.calibration_to_ui, args=()
        )
        self.calibrationui_thread.daemon = True
        self.calibrationui_thread.start()

        self.slow_camera_queue = queue.PriorityQueue(maxsize=0)
        self.slow_camera_queue_thread = threading.Thread(
            target=self.slow_camera_process, args=()
        )
        self.slow_camera_queue_thread.daemon = True
        self.slow_camera_queue_thread.start()

        self.send_status_queue = queue.Queue(maxsize=0)
        self.send_status_queue_thread = threading.Thread(
            target=self.send_status_process, args=()
        )
        self.send_status_queue_thread.daemon = True
        self.send_status_queue_thread.start()

        self.platesolve_queue = queue.Queue(maxsize=0)
        self.platesolve_queue_thread = threading.Thread(
            target=self.platesolve_process, args=()
        )
        self.platesolve_queue_thread.daemon = True
        self.platesolve_queue_thread.start()

        self.laterdelete_queue = queue.Queue(maxsize=0)
        self.laterdelete_queue_thread = threading.Thread(
            target=self.laterdelete_process, args=()
        )
        self.laterdelete_queue_thread.daemon = True
        self.laterdelete_queue_thread.start()

        self.sendtouser_queue = queue.Queue(maxsize=0)
        self.sendtouser_queue_thread = threading.Thread(
            target=self.sendtouser_process, args=()
        )
        self.sendtouser_queue_thread.daemon = True
        self.sendtouser_queue_thread.start()


        self.queue_reporting_period = 60
        self.queue_reporting_timer = time.time() - (2 * self.queue_reporting_period)

        # send up obs status immediately
        self.obs_settings_upload_timer = (
            time.time() - 2 * self.obs_settings_upload_period
        )

        # A dictionary that holds focus results for the SEP queue.
        self.fwhmresult = {}
        self.fwhmresult["error"] = True
        self.fwhmresult["FWHM"] = np.nan
        self.fwhmresult["mean_focus"] = np.nan
        self.fwhmresult["No_of_sources"] = np.nan

        # On initialisation, there should be no commands heading towards the site
        # So this command reads the commands waiting and just ... ignores them
        # essentially wiping the command queue coming from AWS.
        # This prevents commands from previous nights/runs suddenly running
        # when obs.py is booted (has happened a bit in the past!)
        try:
            reqs.request(
                "POST",
                "https://jobs.photonranch.org/jobs/getnewjobs",
                data=json.dumps({"site": self.name}),
                timeout=30,
            ).json()

        except:
            plog ("getnewjobs connection glitch on startup")

        # On startup, collect orphaned fits files that may have been dropped from the queue
        # when the site crashed or was rebooted.
        if self.config["ingest_raws_directly_to_archive"]:
            self.devices["sequencer"].collect_and_queue_neglected_fits()

        # Inform UI of reboot
        self.send_to_user(
            "Observatory code has been rebooted. Manually queued commands have been flushed."
        )

        # Upload the config to the UI
        self.update_config()

        # Report previously calculated Camera Gains as part of bootup
        textfilename = (
            self.obsid_path
            + "ptr_night_shelf/"
            + "cameragain"
            + self.devices["main_cam"].alias
            + str(self.name)
            + ".txt"
        )
        if os.path.exists(textfilename):
            try:
                with open(textfilename, "r") as f:
                    lines = f.readlines()
                    for line in lines:
                        plog(line.replace("\n", ""))
            except:
                plog("something wrong with opening camera gain text file")
                pass

        # Report filter throughputs as part of bootup
        filter_throughput_shelf = shelve.open(
            self.obsid_path
            + "ptr_night_shelf/"
            + "filterthroughput"
            + self.devices["main_cam"].alias
            + str(self.name)
        )

        if len(filter_throughput_shelf) == 0:
            plog("Looks like there is no filter throughput shelf.")
        else:
            #First lts sort this shelf for lowest to highest throughput.
            #breakpoint()
            #filter_throughput_shelf = dict(sorted(filter_throughput_shelf.items(), key=lambda item: item[1], reverse=False)
            plog("Stored filter throughputs")
            for filtertempgain in list(filter_throughput_shelf.keys()):
                plog(
                    str(filtertempgain)
                    + " "
                    + str(filter_throughput_shelf[filtertempgain])
                )
        filter_throughput_shelf.close()

        # Boot up filter offsets
        filteroffset_shelf = shelve.open(
            self.obsid_path
            + "ptr_night_shelf/"
            + "filteroffsets_"
            + self.devices["main_cam"].alias
            + str(self.name)
        )
        plog("Filter Offsets")
        for filtername in filteroffset_shelf:
            plog(str(filtername) + " " + str(filteroffset_shelf[filtername]))
            self.devices["main_fw"].filter_offsets[filtername.lower()] = filteroffset_shelf[
                filtername
            ]
        filteroffset_shelf.close()

        # On bootup, detect the roof status and set the obs to observe or not.
        try:
            self.enc_status = self.get_enclosure_status_from_aws()
            # If the roof is open, then it is open and enabled to observe
            if not self.enc_status == None:
                if "Open" in self.enc_status["shutter_status"]:
                    if (
                        not "NoObs" in self.enc_status["shutter_status"]
                        and not self.net_connection_dead
                    ) or self.assume_roof_open:
                        self.open_and_enabled_to_observe = True
                    else:
                        self.open_and_enabled_to_observe = False
        except:
            plog("FAIL ON OPENING ROOF CHECK")
            self.open_and_enabled_to_observe = False

        # AND one for safety checks
        # Only poll the broad safety checks (altitude and inactivity) every 5 minutes
        self.safety_check_period = self.config["safety_check_period"]
        self.time_since_safety_checks = time.time() - (2 * self.safety_check_period)
        self.safety_and_monitoring_checks_loop_thread = threading.Thread(
            target=self.safety_and_monitoring_checks_loop
        )
        self.safety_and_monitoring_checks_loop_thread.daemon = True
        self.safety_and_monitoring_checks_loop_thread.start()

        self.drift_tracker_timer = time.time()
        self.drift_tracker_counter = 0

        self.currently_scan_requesting = False

        # Sometimes we update the status in a thread. This variable prevents multiple status updates occuring simultaneously
        self.currently_updating_status = False
        # Create this actual thread
        self.update_status_queue = queue.Queue(maxsize=0)
        self.update_status_thread = threading.Thread(
            target=self.update_status_thread)
        self.update_status_thread.daemon = True
        self.update_status_thread.start()

        # Initialisation complete!


    def create_devices(self):
        """Create and store device objects by type, including role assignments.

        This function creates several ways to access devices:
        1. By type and name: self.all_devices['camera']['QHY600m'] = camera object
        2. By name only: self.device_by_name['QHY600m'] = camera object
        3. By role: self.devices['main_cam'] = camera object

        """

        print("\n--- Initializing Devices ---")
        self.all_device_types = self.config["device_types"]
        self.all_devices = {}  # Store devices by type then name. So all_devices['camera']['QHY600m'] = camera object
        self.device_by_name = {} # Store devices by name only. So device_by_name['QHY600m'] = camera object

        # Make a dict for accessing devices by role
        # This must match the config! But it's duplicated here so human programmers can easily see what the supported roles are.
        self.devices = {
            "mount": None,
            "main_focuser": None,
            "main_fw": None,
            "main_rotator": None,
            "main_cam": None,
            "guide_cam": None,
            "widefield_cam": None,
            "allsky_cam": None
        }
        # Validate to make sure that the roles in the config match the roles defined here
        if set(self.devices.keys()) != set(self.config["device_roles"].keys()):
            plog("ERROR: Device roles in Observatory class do not match device roles in config.")
            plog(f"Config roles: {set(self.config['device_roles'].keys())}")
            plog(f"Roles in obs.py Observatory.create_devices: {set(self.devices.keys())}")
            plog("Please update config.device_roles so that they match the roles in Observatory.devices.")
            plog('Fatal error, exiting...')
            sys.exit()

        # Make a dict we can use to lookup the roles for a device
        # Use like: device_roles['QHY600m'] = ['main_cam'] (or whatever roles are assigned to that device)
        # Support multiple roles per device, though this isn't used currently (2025/11/01).
        device_roles = dict()
        for role, device_name in self.config.get("device_roles", {}).items():
            if device_name not in device_roles:
                device_roles[device_name] = []
            device_roles[device_name].append(role)

        # Now we can create the device objects. Group by type, with type order defined by config.device_types
        for dev_type in self.all_device_types:

            # Get all the names of devices of this type
            self.all_devices[dev_type] = {}
            devices_of_type = self.config.get(dev_type, {})
            device_names = devices_of_type.keys()

            # For each of this device type, create the device object and save it in the appropriate lookup dicts
            for device_name in device_names:

                plog(f"Initializing {dev_type} device: {device_name}")
                driver = devices_of_type[device_name].get("driver")
                settings = devices_of_type[device_name].get("settings", {})

                # Instantiate the device object based on its type
                if dev_type == "mount":
                    if "PWI4" in driver:
                        subprocess.Popen('"C:\Program Files (x86)\PlaneWave Instruments\PlaneWave Interface 4\PWI4.exe"', shell=True)
                        time.sleep(10)
                        urllib.request.urlopen("http://localhost:8220/mount/connect")
                        time.sleep(5)
                    device = Mount(driver, device_name, self.config, self, tel=True)
                elif dev_type == "rotator":
                    device = Rotator(driver, device_name, self.config, self)
                elif dev_type == "focuser":
                    device = Focuser(driver, device_name, self.config, self)
                elif dev_type == "filter_wheel":
                    device = FilterWheel(driver, device_name, self.config, self)
                elif dev_type == "camera":
                    device = Camera(driver, device_name, self.config, self)
                elif dev_type == "sequencer":
                    device = Sequencer(self)
                    self.devices["sequencer"] = device # seq doesn't have a role, but add it to self.devices for easy access
                else:
                    continue

                # Store the device for name-based lookup
                self.all_devices[dev_type][device_name] = device
                self.device_by_name[device_name] = device

                # Store the device for role-based lookup
                if device_name in device_roles:
                    for role in device_roles[device_name]:
                        self.devices[role] = device

        # Assign roles
        for role, device_name in self.config.get("device_roles", {}).items():
            if device_name and device_name not in self.device_by_name.keys():
                print("\n")
                print(f"\tWARNING: the device role <{role}> should be assigned to device {device_name}, but that device was never initialized.")
                print(f"This will result in errors if the observatory tries to access <{role}>. Please check the device roles in the config.")
                print(f"This error is probably because the device name in config.device_roles doesn't match any device in the config.")
                print(f"It might also be because the role is for a type of device that is not included in config.device_types.")
                print("\n")

        print("--- Finished Initializing Devices ---\n")

    def get_wema_config(self):
        """ Fetch the WEMA config from AWS """
        wema_config = None
        url = f"https://api.photonranch.org/api/{self.wema_name}/config/"
        try:
            response = requests.get(url, timeout=20)
            wema_config = response.json()['configuration']
            wema_last_recorded_day_dir = wema_config['events'].get('day_directory', '<missing>')
            plog(f"Retrieved wema config, lastest version is from day_directory {wema_last_recorded_day_dir}")
        except Exception as e:
            plog("WARNING: failed to get wema config!", e)
        return wema_config


    def update_config(self):
        """Sends the config to AWS."""

        uri = f"{self.config['obs_id']}/config/"
        self.config["events"] = g_dev["events"]

        # Insert camera size into config
        for name, camera in self.all_devices["camera"].items():
            self.config["camera"][name]["camera_size_x"] = camera.imagesize_x
            self.config["camera"][name]["camera_size_y"] = camera.imagesize_y

        retryapi = True
        while retryapi:
            try:
                response = authenticated_request("PUT", uri, self.config)
                retryapi = False
            except:
                plog("connection glitch in update config. Waiting 5 seconds.")
                time.sleep(5)
        if "message" in response:
            if response["message"] == "Missing Authentication Token":
                plog(
                    "Missing Authentication Token. Config unable to be uploaded. Please fix this now."
                )
                sys.exit()
            else:
                plog(
                    "There may be a problem in the config upload? Here is the response."
                )
                plog(response)
        elif "ResponseMetadata" in response:
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                plog("Config uploaded successfully.")
            else:
                plog("Response to obsid config upload unclear. Here is the response")
                plog(response)
        else:
            plog("Response to obsid config upload unclear. Here is the response")
            plog(response)

    def cancel_all_activity(self):
        self.stop_all_activity = True
        self.stop_all_activity_timer = time.time()
        plog("Stop_all_activity is now set True.")
        self.send_to_user(
            "Cancel/Stop received. Exposure stopped, camera may begin readout, then will discard image."
        )
        self.send_to_user(
            "Pending reductions and transfers to the PTR Archive are not affected."
        )

        plog("Emptying Command Queue")
        with self.cmd_queue.mutex:
            self.cmd_queue.queue.clear()

        plog("Stopping Exposure")

        try:
            self.devices["main_cam"]._stop_expose()
            self.devices["main_cam"].running_an_exposure_set = False

        except Exception as e:
            plog("Camera is not busy.", e)
            plog(traceback.format_exc())
            self.devices["main_cam"].running_an_exposure_set = False

        self.exposure_halted_indicator = True
        self.exposure_halted_indicator_timer = time.time()

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
            unread_commands = []

        # Make sure the list is sorted in the order the jobs were issued
        # Note: the ulid for a job is a unique lexicographically-sortable id.
        if len(unread_commands) > 0:
            try:
                unread_commands.sort(key=lambda x: x["timestamp_ms"])
                # Process each job one at a time
                for cmd in unread_commands:
                    if (
                        self.admin_owner_commands_only
                        and (
                            ("admin" in cmd["user_roles"])
                            or ("owner" in cmd["user_roles"])
                        )
                    ) or (not self.admin_owner_commands_only):

                        # Check for a stop or cancel command
                        if (
                            cmd["action"] in ["cancel_all_commands", "stop"]
                            or cmd["action"].lower() in ["stop", "cancel"]
                            or (
                                cmd["action"] == "run"
                                and cmd["required_params"]["script"] == "stopScript"
                            )
                        ):
                            # A stop script command flags to the running scripts that it is time to stop
                            # activity and return. This period runs for about 30 seconds.
                            self.send_to_user(
                                "A Cancel/Stop has been called. Cancelling out of running scripts over 30 seconds."
                            )
                            self.devices["sequencer"].stop_script_called = True
                            self.devices["sequencer"].stop_script_called_time = time.time()
                            # Cancel out of all running exposures.
                            self.cancel_all_activity()

                        # Anything that is not a stop or cancel command
                        else:
                            action = cmd.get('action')
                            script = cmd["required_params"].get("script")

                            if cmd["deviceType"] == "obs":
                                plog("OBS COMMAND: received a system wide command")

                                if cmd["action"] == "configure_pointing_reference_off":
                                    self.mount_reference_model_off = True
                                    plog("mount_reference_model_off")
                                    self.send_to_user(
                                        "mount_reference_model_off."
                                    )

                                elif cmd["action"] == "configure_pointing_reference_on":
                                    self.mount_reference_model_off = False
                                    plog("mount_reference_model_on")
                                    self.send_to_user(
                                        "mount_reference_model_on."
                                    )

                                elif cmd["action"] == "configure_telescope_mode":
                                    if cmd["required_params"]["mode"] == "manual":
                                        self.scope_in_manual_mode = True
                                        plog("Manual Mode Engaged.")
                                        self.send_to_user(
                                            "Manual Mode Engaged."
                                        )
                                    else:
                                        self.scope_in_manual_mode = False
                                        plog("Manual Mode Turned Off.")
                                        self.send_to_user(
                                            "Manual Mode Turned Off."
                                        )

                                elif cmd["action"] == "configure_moon_safety":
                                    if cmd["required_params"]["mode"] == "on":
                                        self.moon_checks_on = True
                                        plog("Moon Safety On")
                                        self.send_to_user(
                                            "Moon Safety On")
                                    else:
                                        self.moon_checks_on = False
                                        plog("Moon Safety Off")
                                        self.send_to_user(
                                            "Moon Safety Off")

                                elif cmd["action"] == "configure_sun_safety":
                                    if cmd["required_params"]["mode"] == "on":
                                        self.sun_checks_on = True
                                        plog("Sun Safety On")
                                        self.send_to_user(
                                            "Sun Safety On")
                                    else:
                                        self.sun_checks_on = False
                                        plog("Sun Safety Off")
                                        self.send_to_user(
                                            "Sun Safety Off")

                                elif cmd["action"] == "configure_altitude_safety":
                                    if cmd["required_params"]["mode"] == "on":
                                        self.altitude_checks_on = True
                                        plog("Altitude Safety On")
                                        self.send_to_user(
                                            "Altitude Safety On")
                                    else:
                                        self.altitude_checks_on = False
                                        plog("Altitude Safety Off")
                                        self.send_to_user(
                                            "Altitude Safety Off")

                                elif (
                                    cmd["action"] == "configure_daytime_exposure_safety"
                                ):
                                    if cmd["required_params"]["mode"] == "on":
                                        self.daytime_exposure_time_safety_on = True
                                        plog("Daytime Exposure Safety On")
                                        self.send_to_user(
                                            "Daytime Exposure Safety On"
                                        )
                                    else:
                                        self.daytime_exposure_time_safety_on = False
                                        plog("Daytime Exposure Safety Off")
                                        self.send_to_user(
                                            "Daytime Exposure Safety Off"
                                        )

                                elif cmd["action"] == "start_simulating_open_roof":
                                    self.assume_roof_open = True
                                    self.open_and_enabled_to_observe = True
                                    self.enc_status = g_dev[
                                        "obs"
                                    ].get_enclosure_status_from_aws()
                                    self.enclosure_status_timer = (
                                        datetime.datetime.now()
                                    )
                                    plog(
                                        "Roof is now assumed to be open. WEMA shutter status is ignored."
                                    )
                                    self.send_to_user(
                                        "Roof is now assumed to be open. WEMA shutter status is ignored."
                                    )

                                elif cmd["action"] == "stop_simulating_open_roof":
                                    self.assume_roof_open = False
                                    self.enc_status = g_dev[
                                        "obs"
                                    ].get_enclosure_status_from_aws()
                                    self.enclosure_status_timer = (
                                        datetime.datetime.now()
                                    )
                                    plog(
                                        "Roof is now NOT assumed to be open. Reading WEMA shutter status."
                                    )
                                    self.send_to_user(
                                        "Roof is now NOT assumed to be open. Reading WEMA shutter status."
                                    )

                                elif cmd["action"] == "configure_who_can_send_commands":
                                    if (
                                        cmd["required_params"][
                                            "only_accept_admin_or_owner_commands"
                                        ]
                                        == True
                                    ):
                                        self.admin_owner_commands_only = True
                                        plog(
                                            "Scope set to only accept admin or owner commands"
                                        )
                                        self.send_to_user(
                                            "Scope set to only accept admin or owner commands"
                                        )
                                    else:
                                        self.admin_owner_commands_only = False
                                        plog(
                                            "Scope now open to all user commands, not just admin or owner."
                                        )
                                        self.send_to_user(
                                            "Scope now open to all user commands, not just admin or owner."
                                        )

                                elif cmd["action"] == "obs_configure_auto_center_on":
                                    self.auto_centering_off = False
                                    plog("Scope set to automatically center.")
                                    self.send_to_user(
                                        "Scope set to automatically center."
                                    )

                                elif cmd["action"] == "obs_configure_auto_center_off":
                                    self.auto_centering_off = True
                                    plog("Scope set to not automatically center.")
                                    self.send_to_user(
                                        "Scope set to not automatically center."
                                    )

                                else:
                                    plog("Unknown command: " + str(cmd))

                                self.obs_settings_upload_timer = (
                                    time.time() - 2 * self.obs_settings_upload_period
                                )

                                self.request_update_status()

                            # Check here for admin/owner only functions
                            elif (
                                action == "run"
                                and script == "collectScreenFlats"
                                and not (
                                    ("admin" in cmd["user_roles"])
                                    or ("owner" in cmd["user_roles"])
                                )
                            ):
                                plog(
                                    "Request rejected as flats can only be commanded by admin user."
                                )
                                self.send_to_user(
                                    "Request rejected as flats can only be commanded by admin user."
                                )
                            elif (
                                action == "run"
                                and script == "collectSkyFlats"
                                and not (
                                    ("admin" in cmd["user_roles"])
                                    or ("owner" in cmd["user_roles"])
                                )
                            ):
                                plog(
                                    "Request rejected as flats can only be commanded by admin user."
                                )
                                self.send_to_user(
                                    "Request rejected as flats can only be commanded by admin user."
                                )
                            elif (
                                action == "run"
                                and script in ["pointingRun"]
                                and not (
                                    ("admin" in cmd["user_roles"])
                                    or ("owner" in cmd["user_roles"])
                                )
                            ):
                                plog(
                                    "Request rejected as pointing runs can only be commanded by admin user."
                                )
                                self.send_to_user(
                                    "Request rejected as pointing runs can only be commanded by admin user."
                                )
                            elif (
                                action == "run"
                                and script in ("collectBiasesAndDarks")
                                and not (
                                    ("admin" in cmd["user_roles"])
                                    or ("owner" in cmd["user_roles"])
                                )
                            ):
                                plog(
                                    "Request rejected as bias and darks can only be commanded by admin user."
                                )
                                self.send_to_user(
                                    "Request rejected as bias and darks can only be commanded by admin user."
                                )
                            elif (
                                action == "run"
                                and script in ("estimateFocusOffset")
                                and not (
                                    ("admin" in cmd["user_roles"])
                                    or ("owner" in cmd["user_roles"])
                                )
                            ):
                                plog(
                                    "Request rejected as focus offset estimation can only be commanded by admin user."
                                )
                                self.send_to_user(
                                    "Request rejected as focus offset estimation can only be commanded by admin user."
                                )
                            # Check here for irrelevant commands
                            elif (
                                cmd["deviceType"] == "screen"
                                and len(self.all_devices.get("screen", {}) == 0) # check that no screens were initialized
                            ):
                                plog("Refusing command as there is no screen")
                                self.send_to_user(
                                    "Request rejected as site has no flat screen."
                                )
                            elif (
                                cmd["deviceType"] == "rotator"
                                and not self.devices['main_rotator']
                            ):
                                plog("Refusing command as there is no rotator")
                                self.send_to_user(
                                    "Request rejected as site has no rotator."
                                )
                            # If not irrelevant, queue the command
                            else:
                                self.stop_all_activity = False
                                self.cmd_queue.put(cmd)
                        if cancel_check:
                            return  # Note we do not process any commands.

                    else:
                        plog("Request rejected as obs in admin or owner mode.")
                        self.send_to_user(
                            "Request rejected as obs in admin or owner mode."
                        )
            except:
                if "Internal server error" in str(unread_commands):
                    plog("AWS server glitch reading unread_commands")
                else:
                    plog(traceback.format_exc())
                    plog("unread commands")
                    plog(unread_commands)
                    plog(
                        "MF trying to find whats happening with this relatively rare bug!"
                    )
        return

    def update_status(self, cancel_check=False, mount_only=False, dont_wait=False):
        """Collects status from all devices and sends an update to AWS.

        Each device class is responsible for implementing the method
        `get_status`, which returns a dictionary.
        """

        if self.currently_updating_status == True and mount_only == False:
            return

        self.currently_updating_status = True

        not_slewing = False
        if self.mountless_operation:
            not_slewing = True
        elif not self.devices["mount"].return_slewing():
            not_slewing = True

        # Wait a bit between status updates otherwise
        # status updates bank up in the queue
        if not_slewing:  # Don't wait while slewing.
            if not dont_wait:
                self.status_interval = self.status_upload_time + 0.25
                while time.time() < (self.time_last_status + self.status_interval):
                    time.sleep(0.001)

        # Don't make a new status during a slew unless the queue is empty, otherwise the green crosshairs on the UI lags.
        if (not not_slewing and self.send_status_queue.qsize() == 0) or not_slewing:
            # Send main batch of devices status
            obsy = self.name
            if mount_only == True:
                device_list = ["mount"]
            else:
                device_list = self.all_device_types
            status = {}
            for dev_type in device_list:
                #  The status that we will send is grouped into lists of
                #  devices by dev_type.
                status[dev_type] = {}
                devices_of_type = self.all_devices.get(dev_type, {})
                device_names = devices_of_type.keys()

                for device_name in device_names:
                    device = devices_of_type[device_name]
                    result = device.get_status()
                    if result is not None:
                        status[dev_type][device_name] = result
                #breakpoint()

            status["timestamp"] = round((time.time()) / 2.0, 3)
            status["send_heartbeat"] = False

            if status is not None:
                lane = "device"
                if self.send_status_queue.qsize() < 7:
                    self.send_status_queue.put(
                        (obsy, lane, status), block=False)

        """
        Here we update lightning system.
        Check if file exists and is not stale
        If ok open file and look for instances of distance < specified
        if there are any then assemble a file to write to transfer disk.


        """

        # NB NB this needs to be conditoned on the site having lightning detection!
        try:
            if self.config['has_lightning_detector']:

                try:
                    with open("C:/Astrogenic/NexStorm/reports/TRACReport.txt", 'r') as light_rec:
                        r_date, r_time = light_rec.readline().split()[-2:]
                        #plog(r_date, r_time)
                        d_string = r_date + 'T' +r_time
                        d_time = datetime.datetime.fromisoformat(d_string)+datetime.timedelta(minutes=7.5)
                        distance = 10.001
                        if datetime.datetime.now() < d_time:   #  Here validate if not stale before doing next line.
                            for lin in light_rec.readlines():
                                if 'distance' in lin:
                                    s_range = float(lin.split()[-2])
                                    if s_range < distance:
                                        distance = s_range
                        else:
                            #plog("Lightning report is stale.")
                            pass
                    if distance <=  10.0:
                        plog("Lightning distance is:   ", distance, ' km away.')
                    else:
                        pass
                        #plog('Lighting is > 10 km away,')
                except:
                    plog('Lightning distance test did not work')

        except:
            pass

        self.time_last_status = time.time()
        self.status_count += 1

        self.currently_updating_status = False

    def safety_and_monitoring_checks_loop(self):
        while True:
            self.time_since_safety_checks = time.time()

            if False and (
                (time.time() - self.queue_reporting_timer) > self.queue_reporting_period
            ):
                self.queue_reporting_timer = time.time()
                plog("Queue Reports - hunting for ram leak")
                if self.config["ingest_raws_directly_to_archive"]:
                    plog("PTR Archive Queue: " +
                         str(self.ptrarchive_queue.qsize()))
                plog("Fast UI Queue: " + str(self.fast_queue.qsize()))
                plog("Medium UI Queue: " + str(self.mediumui_queue.qsize()))
                plog("Calibration UI Queue: " +
                     str(self.calibrationui_queue.qsize()))
                plog("Slow Camera Queue: " + str(self.slow_camera_queue.qsize()))
                plog("Platesolve Queue: " + str(self.platesolve_queue.qsize()))
                plog("SEP Queue: " + str(self.sep_queue.qsize()))
                plog("JPEG Queue: " + str(self.mainjpeg_queue.qsize()))

            if not self.mountless_operation:
                try:
                    # If the roof is open, then it is open and enabled to observe
                    if not self.enc_status == None:
                        if "Open" in self.enc_status["shutter_status"]:
                            if (
                                not "NoObs" in self.enc_status["shutter_status"]
                                and not self.net_connection_dead
                            ) or self.assume_roof_open:
                                self.open_and_enabled_to_observe = True
                            else:
                                self.open_and_enabled_to_observe = False

                    # Check that the mount hasn't slewed too close to the sun
                    # If the roof is open and enabled to observe
                    # Don't do sun checks at nightime!
                    if (
                        not (
                            (
                                g_dev["events"]["Observing Begins"]
                                <= ephem.now()
                                < g_dev["events"]["Observing Ends"]
                            )
                        )
                        and not self.devices["mount"].currently_slewing
                    ):
                        try:
                            if (
                                not self.devices["mount"].return_slewing()
                                and not self.devices["mount"].parking_or_homing
                                and self.open_and_enabled_to_observe
                                and self.sun_checks_on
                            ):
                                sun_coords = get_sun(Time.now())
                                temppointing = SkyCoord(
                                    (self.devices["mount"].current_icrs_ra) * u.hour,
                                    (self.devices["mount"].current_icrs_dec) * u.degree,
                                    frame="icrs",
                                )
                                sun_dist = sun_coords.separation(temppointing)
                                if (
                                    sun_dist.degree
                                    < self.config["closest_distance_to_the_sun"]
                                    and not self.devices["mount"].rapid_park_indicator
                                ):
                                    self.send_to_user(
                                        "Found telescope pointing too close to the sun: "
                                        + str(sun_dist.degree)
                                        + " degrees."
                                    )
                                    plog(
                                        "Found telescope pointing too close to the sun: "
                                        + str(sun_dist.degree)
                                        + " degrees."
                                    )
                                    self.send_to_user(
                                        "Parking scope and cancelling all activity"
                                    )
                                    plog(
                                        "Parking scope and cancelling all activity")

                                    if (
                                        not self.devices["sequencer"].morn_bias_dark_latch
                                        and not self.devices["sequencer"].bias_dark_latch
                                    ):
                                        self.cancel_all_activity()
                                    if not self.devices["mount"].rapid_park_indicator:
                                        self.devices["mount"].park_command()

                                    self.currently_updating_status = False
                                    return
                        except Exception as e:
                            plog(traceback.format_exc())
                            plog("Sun check didn't work for some reason")
                            if (
                                "Object reference not set" in str(e)
                                and self.devices["mount"].theskyx
                            ):
                                plog("The SkyX had an error.")
                                plog(
                                    "Usually this is because of a broken connection.")
                                plog(
                                    "Killing then waiting 60 seconds then reconnecting"
                                )
                                self.kill_and_reboot_theskyx(
                                    self.devices["mount"].current_icrs_ra,
                                    self.devices["mount"].current_icrs_dec,
                                )
                except:
                    plog("pigjfsdoighdfg")

            try:
                # Keep an eye on the stop-script and exposure halt time to reset those timers.
                if self.devices["sequencer"].stop_script_called and (
                    (time.time() - self.devices["sequencer"].stop_script_called_time) > 35
                ):
                    self.send_to_user("Stop Script Complete.")
                    self.devices["sequencer"].stop_script_called = False
                    self.devices["sequencer"].stop_script_called_time = time.time()

                if self.exposure_halted_indicator == True:
                    if self.exposure_halted_indicator_timer - time.time() > 12:
                        self.exposure_halted_indicator = False
                        self.exposure_halted_indicator_timer = time.time()

                if self.stop_all_activity and (
                    (time.time() - self.stop_all_activity_timer) > 35
                ):
                    self.stop_all_activity = False

                # If theskyx is rebooting wait
                while self.rebooting_theskyx:
                    plog("waiting for theskyx to reboot")
                    time.sleep(5)

                # If camera is rebooting, the.running_an_exposure_set term can fall out
                # If it is rebooting then return to the start of the loop.
                not_rebooting = True
                try:
                    if self.devices["main_cam"].theskyx:
                        while True:
                            try:
                                self.devices["main_cam"].running_an_exposure_set
                                # plog ("theskyx camera check")
                                if not not_rebooting:
                                    continue
                                else:
                                    break
                            except:
                                plog("pausing while camera reboots")
                                not_rebooting = False
                                time.sleep(1)
                except:
                    while True:
                        try:
                            self.devices["main_cam"].running_an_exposure_set
                            # plog ("theskyx camera check")
                            if not not_rebooting:
                                continue
                            else:
                                break
                        except:
                            plog("pausing while camera reboots")
                            not_rebooting = False
                            time.sleep(1)

                # Good spot to check if we need to nudge the telescope as long as we aren't exposing.
                if not self.mountless_operation:
                    if (
                        not self.devices["main_cam"].running_an_exposure_set
                        and not self.devices["sequencer"].block_guard
                        and not self.devices["sequencer"].total_sequencer_control
                    ):
                        self.check_platesolve_and_nudge()
                    # Meridian 'pulse'. A lot of mounts will not do a meridian flip unless a
                    # specific slew command is sent. So this tracks how long it has been since
                    # a slew and sends a slew command to the exact coordinates it is already pointing on
                    # at least a 5 minute basis.
                    self.time_of_last_pulse = max(
                        self.time_of_last_slew, self.time_of_last_pulse
                    )
                    try:
                        if (time.time() - self.time_of_last_pulse) > 300 and not g_dev[
                            "mnt"
                        ].currently_slewing:
                            # Check no other commands or exposures are happening
                            if (
                                self.cmd_queue.empty()
                                and not self.devices["main_cam"].running_an_exposure_set
                                and not self.devices["main_cam"].currently_in_smartstack_loop
                                and not self.devices["sequencer"].focussing
                            ):
                                if (
                                    not self.devices["mount"].rapid_park_indicator
                                    and not self.devices["mount"].return_slewing()
                                    and self.devices["mount"].return_tracking()
                                ):
                                    # Don't do it if the roof isn't open etc.
                                    if (
                                        self.open_and_enabled_to_observe == True
                                    ) or self.scope_in_manual_mode:
                                        ra = self.devices["mount"].return_right_ascension()
                                        dec = self.devices["mount"].return_declination()
                                        temppointing = SkyCoord(
                                            ra * u.hour, dec * u.degree, frame="icrs"
                                        )
                                        temppointingaltaz = temppointing.transform_to(
                                            AltAz(
                                                location=self.devices["mount"].site_coordinates,
                                                obstime=Time.now(),
                                            )
                                        )
                                        alt = temppointingaltaz.alt.degree
                                        if alt > 25:
                                            self.devices["mount"].wait_for_slew(wait_after_slew=False)
                                            meridianra = g_dev[
                                                "mnt"
                                            ].return_right_ascension()
                                            meridiandec = g_dev[
                                                "mnt"
                                            ].return_declination()
                                            self.devices["mount"].slew_async_directly(
                                                ra=meridianra, dec=meridiandec
                                            )
                                            plog("Meridian Probe")
                                            self.devices["mount"].wait_for_slew(wait_after_slew=False)
                                            self.time_of_last_pulse = time.time()
                    except:
                        plog("perhaps theskyx is restarting????")
                        plog(traceback.format_exc())

                # Send up the obs settings status - basically the current safety settings
                if (
                    (datetime.datetime.now() - self.observing_status_timer)
                ) > datetime.timedelta(minutes=self.observing_check_period):
                    self.ocn_status = self.get_weather_status_from_aws()
                    # These two lines are meant to update the parameters for refraction correction in the mount class
                    try:
                        self.pressure = self.ocn_status["pressure_mbar"]
                    except:
                        self.pressure = 1013.0
                    try:
                        self.temperature = self.ocn_status[
                            "temperature_C"
                        ]
                    except:
                        self.temperature = g_dev[
                            "foc"
                        ].current_focus_temperature
                    self.observing_status_timer = datetime.datetime.now()

                if (
                    (datetime.datetime.now() - self.enclosure_status_timer)
                ) > datetime.timedelta(minutes=self.enclosure_check_period):
                    self.enc_status = g_dev[
                        "obs"
                    ].get_enclosure_status_from_aws()
                    self.enclosure_status_timer = datetime.datetime.now()

                if (
                    time.time() - self.obs_settings_upload_timer
                ) > self.obs_settings_upload_period:
                    self.obs_settings_upload_timer = time.time()
                    status = {}
                    status["obs_settings"] = {}
                    status["obs_settings"][
                        "scope_in_manual_mode"
                    ] = self.scope_in_manual_mode
                    status["obs_settings"]["sun_safety_mode"] = self.sun_checks_on
                    status["obs_settings"]["moon_safety_mode"] = self.moon_checks_on
                    status["obs_settings"][
                        "altitude_safety_mode"
                    ] = self.altitude_checks_on
                    status["obs_settings"]["lowest_altitude"] = -5
                    status["obs_settings"][
                        "daytime_exposure_safety_mode"
                    ] = self.daytime_exposure_time_safety_on
                    status["obs_settings"]["daytime_exposure_time"] = 0.01
                    status["obs_settings"]["auto_center_on"] = not self.auto_centering_off
                    status["obs_settings"][
                        "admin_owner_commands_only"
                    ] = self.admin_owner_commands_only
                    status["obs_settings"][
                        "simulating_open_roof"
                    ] = self.assume_roof_open
                    status["obs_settings"][
                        "pointing_reference_on"
                    ] = not self.mount_reference_model_off
                    status["obs_settings"]["morning_flats_done"] = g_dev[
                        "seq"
                    ].morn_flats_done
                    status["obs_settings"]["timedottime_of_last_upload"] = time.time()
                    lane = "obs_settings"
                    try:
                        send_status(self.name, lane, status)
                    except:
                        plog("could not send obs_settings status")
                        plog(traceback.format_exc())

                # An important check to make sure equatorial telescopes are pointed appropriately
                # above the horizon. SRO and ECO have shown that it is possible to get entirely
                # confuzzled and take images of the dirt. This should save them from this fate.
                # Also it should generically save any telescope from pointing weirdly down
                # or just tracking forever after being left tracking for far too long.
                #
                # Also an area to put things to irregularly check if things are still connected, e.g. cooler

                # Adjust focus on a not-too-frequent period for temperature
                if not self.mountless_operation:
                    if (
                        not self.devices["main_cam"].running_an_exposure_set
                        and not self.devices["sequencer"].focussing
                        and self.open_and_enabled_to_observe
                        and not self.devices["mount"].currently_slewing
                        and not self.devices["main_focuser"].focuser_is_moving
                    ):
                        self.devices["main_focuser"].adjust_focus()

                # Check nightly_reset is all good
                if (
                    g_dev["events"]["Cool Down, Open"]
                    <= ephem.now()
                    < g_dev["events"]["Observing Ends"]
                ):
                    self.devices["sequencer"].nightly_reset_complete = False

                if not self.mountless_operation:
                    # Don't do sun checks at nightime!
                    if (
                        not (
                            (
                                g_dev["events"]["Observing Begins"]
                                <= ephem.now()
                                < g_dev["events"]["Observing Ends"]
                            )
                        )
                        and not self.devices["mount"].currently_slewing
                    ):
                        if (
                            not self.devices["mount"].rapid_park_indicator
                            and self.open_and_enabled_to_observe
                            and self.sun_checks_on
                        ):  # Only do the sun check if scope isn't parked
                            # Check that the mount hasn't slewed too close to the sun
                            sun_coords = get_sun(Time.now())
                            temppointing = SkyCoord(
                                (self.devices["mount"].current_icrs_ra) * u.hour,
                                (self.devices["mount"].current_icrs_dec) * u.degree,
                                frame="icrs",
                            )

                            sun_dist = sun_coords.separation(temppointing)
                            if (
                                sun_dist.degree
                                < self.config["closest_distance_to_the_sun"]
                                and not self.devices["mount"].rapid_park_indicator
                            ):
                                self.send_to_user(
                                    "Found telescope pointing too close to the sun: "
                                    + str(sun_dist.degree)
                                    + " degrees."
                                )
                                plog(
                                    "Found telescope pointing too close to the sun: "
                                    + str(sun_dist.degree)
                                    + " degrees."
                                )
                                self.send_to_user(
                                    "Parking scope and cancelling all activity"
                                )
                                plog("Parking scope and cancelling all activity")
                                if (
                                    not self.devices["sequencer"].morn_bias_dark_latch
                                    and not self.devices["sequencer"].bias_dark_latch
                                ):
                                    self.cancel_all_activity()
                                if not self.devices["mount"].rapid_park_indicator:
                                    self.devices["mount"].park_command()

                                self.currently_updating_FULL = False
                                return

                    # Roof Checks only if not in debug mode
                    # And only check if the scope thinks everything is open and hunky dory
                    if (
                        self.open_and_enabled_to_observe
                        and not self.scope_in_manual_mode
                        and not self.assume_roof_open
                    ):
                        if self.enc_status is not None:
                            if (
                                "Software Fault"
                                in self.enc_status["shutter_status"]
                            ):
                                plog(
                                    "Software Fault Detected."
                                )  # " Will alert the authorities!")
                                plog("Parking Scope in the meantime.")

                                self.open_and_enabled_to_observe = False
                                if (
                                    not self.devices["sequencer"].morn_bias_dark_latch
                                    and not self.devices["sequencer"].bias_dark_latch
                                ):
                                    self.cancel_all_activity()

                                if not self.devices["mount"].rapid_park_indicator:
                                    if self.devices["mount"].home_before_park:
                                        self.devices["mount"].home_command()
                                    self.devices["mount"].park_command()

                            if (
                                "Closing" in self.enc_status["shutter_status"]
                                or "Opening"
                                in self.enc_status["shutter_status"]
                            ):
                                plog("Detected Roof Movement.")
                                self.open_and_enabled_to_observe = False
                                if (
                                    not self.devices["sequencer"].morn_bias_dark_latch
                                    and not self.devices["sequencer"].bias_dark_latch
                                ):
                                    self.cancel_all_activity()
                                if not self.devices["mount"].rapid_park_indicator:
                                    if self.devices["mount"].home_before_park:
                                        self.devices["mount"].home_command()
                                    self.devices["mount"].park_command()

                            if "Error" in self.enc_status["shutter_status"]:
                                plog(
                                    "Detected an Error in the Roof Status. Packing up for safety."
                                )
                                if (
                                    not self.devices["sequencer"].morn_bias_dark_latch
                                    and not self.devices["sequencer"].bias_dark_latch
                                ):
                                    self.cancel_all_activity()  # NB Kills bias dark
                                self.open_and_enabled_to_observe = False
                                if not self.devices["mount"].rapid_park_indicator:
                                    if self.devices["mount"].home_before_park:
                                        self.devices["mount"].home_command()
                                    self.devices["mount"].park_command()

                        else:
                            plog(
                                "Enclosure roof status probably not reporting correctly. WEMA down?"
                            )

                        roof_should_be_shut = False

                        if (
                            not self.scope_in_manual_mode
                            and not self.devices["sequencer"].flats_being_collected
                            and not self.assume_roof_open
                        ):
                            if (
                                g_dev["events"]["End Morn Sky Flats"]
                                < ephem.now()
                                < g_dev["events"]["End Morn Bias Dark"]
                            ):
                                roof_should_be_shut = True
                                self.open_and_enabled_to_observe = False
                            if not self.config["auto_morn_sky_flat"]:
                                if (
                                    g_dev["events"]["Observing Ends"]
                                    < ephem.now()
                                    < g_dev["events"]["End Morn Bias Dark"]
                                ):
                                    roof_should_be_shut = True
                                    self.open_and_enabled_to_observe = False
                                if (
                                    g_dev["events"]["Naut Dawn"]
                                    < ephem.now()
                                    < g_dev["events"]["Morn Bias Dark"]
                                ):
                                    roof_should_be_shut = True
                                    self.open_and_enabled_to_observe = False
                            if not (
                                g_dev["events"]["Cool Down, Open"]
                                < ephem.now()
                                < g_dev["events"]["Close and Park"]
                            ):
                                roof_should_be_shut = True
                                self.open_and_enabled_to_observe = False

                        if "Open" in self.enc_status["shutter_status"]:
                            if roof_should_be_shut == True:
                                plog(
                                    "Safety check notices that the roof was open outside of the normal observing period"
                                )

                        if (
                            not self.scope_in_manual_mode
                            and not self.devices["sequencer"].flats_being_collected
                            and not self.assume_roof_open
                        ):
                            # If the roof should be shut, then the telescope should be parked.
                            if roof_should_be_shut == True:
                                if not self.devices["mount"].rapid_park_indicator:
                                    plog(
                                        "Parking telescope as it is during the period that the roof is meant to be shut."
                                    )
                                    self.open_and_enabled_to_observe = False
                                    if (
                                        not self.devices["sequencer"].morn_bias_dark_latch
                                        and not self.devices["sequencer"].bias_dark_latch
                                    ):
                                        self.cancel_all_activity()  # NB Kills bias dark
                                    if self.devices["mount"].home_before_park:
                                        self.devices["mount"].home_command()
                                    self.devices["mount"].park_command()

                            if self.enc_status is not None:
                                # If the roof IS shut, then the telescope should be shutdown and parked.
                                if (
                                    "Closed"
                                    in self.enc_status["shutter_status"]
                                ):
                                    if not self.devices["mount"].rapid_park_indicator:
                                        plog(
                                            "Telescope found not parked when the observatory roof is shut. Parking scope."
                                        )
                                        self.open_and_enabled_to_observe = False
                                        if (
                                            not self.devices["sequencer"].morn_bias_dark_latch
                                            and not self.devices["sequencer"].bias_dark_latch
                                        ):
                                            self.cancel_all_activity()  # NB Kills bias dark
                                        if self.devices["mount"].home_before_park:
                                            self.devices["mount"].home_command()
                                        self.devices["mount"].park_command()

                                # But after all that if everything is ok, then all is ok, it is safe to observe
                                if (
                                    "Open" in self.enc_status["shutter_status"]
                                    and roof_should_be_shut == False
                                ):
                                    if (
                                        not "NoObs"
                                        in self.enc_status["shutter_status"]
                                        and not self.net_connection_dead
                                    ):
                                        self.open_and_enabled_to_observe = True
                                    elif self.assume_roof_open:
                                        self.open_and_enabled_to_observe = True
                                    else:
                                        self.open_and_enabled_to_observe = False
                                else:
                                    self.open_and_enabled_to_observe = False

                            else:
                                plog(
                                    "self.enc_status not reporting correctly")

                if not self.mountless_operation:
                    # Check that the mount hasn't tracked too low or an odd slew hasn't sent it pointing to the ground.
                    if self.altitude_checks_on and not self.devices["mount"].currently_slewing:
                        try:
                            mount_altitude = float(
                                self.devices["mount"].previous_status["altitude"]
                            )

                            lowest_acceptable_altitude = self.config[
                                "lowest_acceptable_altitude"
                            ]
                            if mount_altitude < lowest_acceptable_altitude:
                                plog(
                                    "Altitude too low! "
                                    + str(mount_altitude)
                                    + ". Parking scope for safety!"
                                )
                                if not self.devices["mount"].rapid_park_indicator:
                                    if (
                                        not self.devices["sequencer"].morn_bias_dark_latch
                                        and not self.devices["sequencer"].bias_dark_latch
                                    ):
                                        self.cancel_all_activity()
                                    if self.devices["mount"].home_before_park:
                                        self.devices["mount"].home_command()
                                    self.devices["mount"].park_command()
                        except Exception as e:
                            plog(traceback.format_exc())
                            plog(e)

                            if self.devices["mount"].theskyx:
                                plog("The SkyX had an error.")
                                plog(
                                    "Usually this is because of a broken connection.")
                                plog(
                                    "Killing then waiting 60 seconds then reconnecting"
                                )
                                self.kill_and_reboot_theskyx(-1, -1)
                            else:
                                pass

                    # If no activity for an hour, park the scope
                    if (
                        not self.scope_in_manual_mode
                        and not self.devices["mount"].currently_slewing
                    ):
                        if (
                            time.time() - self.time_of_last_slew
                            > self.devices['mount'].config['time_inactive_until_park']
                            and time.time() - self.time_of_last_exposure
                            > self.devices['mount'].config['time_inactive_until_park']
                        ):
                            if not self.devices["mount"].rapid_park_indicator:
                                plog("Parking scope due to inactivity")
                                if self.devices["mount"].home_before_park:
                                    self.devices["mount"].home_command()
                                self.devices["mount"].park_command()
                            self.time_of_last_slew = time.time()
                            self.time_of_last_exposure = time.time()

                # Check that cooler is alive
                if self.devices["main_cam"]._cooler_on():
                    current_camera_temperature, cur_humidity, cur_pressure, cur_pwm = g_dev[
                        "cam"
                    ]._temperature()
                    current_camera_temperature = round(
                        current_camera_temperature, 1)
                    if (
                        abs(
                            float(current_camera_temperature)
                            - float(self.devices["main_cam"].setpoint)
                        )
                        > self.devices['main_cam'].settings['temp_setpoint_tolerance']
                    ):

                        self.camera_sufficiently_cooled_for_calibrations = False
                        self.last_time_camera_was_warm = time.time()
                    elif (time.time() - self.last_time_camera_was_warm) < 120:  #NB NB THis should be a config item and in confict wth code below
                        self.camera_sufficiently_cooled_for_calibrations = False
                    else:
                        self.camera_sufficiently_cooled_for_calibrations = True
                else:
                    try:
                        probe = self.devices["main_cam"]._cooler_on()
                        if not probe:
                            self.devices["main_cam"]._set_cooler_on()
                            plog("Found cooler off.")
                            try:
                                self.devices["main_cam"]._connect(False)
                                self.devices["main_cam"]._connect(True)
                                self.devices["main_cam"]._set_cooler_on()
                            except:
                                plog("Camera cooler reconnect failed.")
                    except Exception as e:
                        plog(
                            "\n\nCamera was not connected @ expose entry:  ", e, "\n\n"
                        )
                        try:
                            self.devices["main_cam"]._connect(False)
                            self.devices["main_cam"]._connect(True)
                            self.devices["main_cam"]._set_cooler_on()
                        except:
                            plog("Camera cooler reconnect failed 2nd time.")

                # Things that only rarely have to be reported go in this block.
                if (time.time() - self.last_time_report_to_console) > 180:   #NB NB This should be a config item WER
                    #plog(ephem.now())
                    if self.camera_sufficiently_cooled_for_calibrations == False:
                        if (time.time() - self.last_time_camera_was_warm) < 180:  # Temporary NB WER 2024_04-13
                            plog(
                                "Camera was recently out of the temperature range for calibrations"
                            )
                            plog(
                                "Waiting for a 3 minute period where camera has been cooled to the right temperature"
                            )
                            plog(
                                "Before continuing calibrations to ensure cooler is evenly cooled"
                            )
                            plog(
                                str(
                                    int(
                                        180
                                        - (time.time() -
                                           self.last_time_camera_was_warm)
                                    )
                                )
                                + " seconds to go."
                            )
                            plog(
                                "Camera current temperature ("
                                + str(current_camera_temperature)
                                + ")."
                            )
                            plog(
                                "Camera current PWM% ("
                                + str(cur_pwm)
                                + ")."
                            )

                            plog(
                                "Difference from setpoint: "
                                + str(
                                    round((current_camera_temperature -
                                     self.devices["main_cam"].setpoint),2)
                                )
                            )
                        else:
                            plog(
                                "Camera currently too warm ("
                                + str(current_camera_temperature)
                                + ") for calibrations."
                            )
                            breakpoint()
                            plog(
                                "Difference from setpoint: "
                                + str(
                                    round((current_camera_temperature -
                                     self.devices["main_cam"].setpoint), 2)
                                )
                            )
                        self.last_time_camera_was_warm = time.time()

                    self.last_time_report_to_console = time.time()

                if time.time() - self.devices["sequencer"].time_roof_last_opened < 10:
                    plog(
                        "Roof opened only recently: "
                        + str(
                            round(
                                (time.time() -
                                 self.devices["sequencer"].time_roof_last_opened) / 60,
                                1,
                            )
                        )
                        + " minutes ago."
                    )
                    plog(
                        "Some functions, particularly flats, won't start until 10 seconds after the roof has opened."
                    )

                # After the observatory and camera have had time to settle....
                if (time.time() - self.camera_time_initialised) > 600:
                    # Check that the camera is not overheating.
                    # If it isn't overheating check that it is at the correct temperature
                    if self.camera_overheat_safety_warm_on:
                        #plog(time.time() - self.camera_overheat_safety_timer)
                        if (time.time() - self.camera_overheat_safety_timer) > 1201:
                            plog(
                                "Camera OverHeating Safety Warm Cycle Complete. Resetting to normal temperature."
                            )
                            self.devices["main_cam"]._set_setpoint(self.devices["main_cam"].setpoint)
                            # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                            self.devices["main_cam"]._set_cooler_on()
                            self.camera_overheat_safety_warm_on = False
                        else:
                            plog("Camera Overheating Safety Warm Cycle on.")

                    elif self.devices["main_cam"].protect_camera_from_overheating and (
                        float(current_camera_temperature)
                        - self.devices["main_cam"].current_setpoint
                    ) > (2 * self.devices["main_cam"].day_warm_degrees):
                        plog("Found cooler on, but warm.")
                        plog(
                            "Keeping it slightly warm ( "
                            + str(2 * self.devices["main_cam"].day_warm_degrees)
                            + " degrees warmer ) for about 20 minutes just in case the camera overheated."
                        )
                        plog("Then will reset to normal.")
                        self.camera_overheat_safety_warm_on = True
                        self.camera_overheat_safety_timer = time.time()
                        self.last_time_camera_was_warm = time.time()
                        self.devices["main_cam"]._set_setpoint(
                            float(
                                self.devices["main_cam"].setpoint
                                + (2 * self.devices["main_cam"].day_warm_degrees)
                            )
                        )
                        # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                        self.devices["main_cam"]._set_cooler_on()

                if not self.camera_overheat_safety_warm_on and (
                    time.time() - self.warm_report_timer > 300
                ):
                    # Daytime... a bit tricky! Two periods... just after biases but before nightly reset OR ... just before eve bias dark
                    # As nightly reset resets the calendar
                    self.warm_report_timer = time.time()
                    self.too_hot_in_observatory = False
                    try:
                        focstatus = self.devices["main_focuser"].get_status()
                        self.temperature_in_observatory_from_focuser = focstatus[
                            "focus_temperature"
                        ]
                    except:
                        self.temperature_in_observatory_from_focuser = 20.0
                        pass

                    try:
                        if (
                            self.temperature_in_observatory_from_focuser
                            > self.too_hot_temperature
                        ):  # This should be a per obsy config item
                            self.too_hot_in_observatory = True
                    except:
                        plog("observatory temperature probe failed.")

                    if (
                        self.devices["main_cam"].day_warm
                        and (
                            ephem.now(
                            ) < g_dev["events"]["Eve Bias Dark"] - ephem.hour
                        )
                        or (
                            g_dev["events"]["End Morn Bias Dark"] + ephem.hour
                            < ephem.now()
                            < g_dev["events"]["Nightly Reset"]
                        )
                    ):
                        plog("In Daytime: Camera set at warmer temperature")
                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint +
                                  self.devices["main_cam"].day_warm_degrees)
                        )

                        # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                        self.devices["main_cam"]._set_cooler_on()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))
                        self.last_time_camera_was_warm = time.time()

                    elif (
                        self.devices["main_cam"].day_warm
                        and (self.too_hot_in_observatory)
                        and (
                            ephem.now()
                            < g_dev["events"]["Clock & Auto Focus"] - ephem.hour
                        )
                    ):
                        plog(
                            "Currently too hot: "
                            + str(self.temperature_in_observatory_from_focuser)
                            + "C for excess cooling. Keeping it at day_warm until a cool hour long ramping towards clock & autofocus"
                        )
                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint +
                                  self.devices["main_cam"].day_warm_degrees)
                        )
                        # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                        self.devices["main_cam"]._set_cooler_on()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))
                        self.last_time_camera_was_warm = time.time()

                    # Ramp heat temperature
                    # Beginning after "End Morn Bias Dark" and taking an hour to ramp
                    elif self.devices["main_cam"].day_warm and (
                        g_dev["events"]["End Morn Bias Dark"]
                        < ephem.now()
                        < g_dev["events"]["End Morn Bias Dark"] + ephem.hour
                    ):
                        plog("In Camera Warming Ramping cycle of the day")
                        frac_through_warming = (
                            1
                            - (
                                (g_dev["events"]
                                 ["End Morn Bias Dark"] + ephem.hour)
                                - ephem.now()
                            )
                            / ephem.hour
                        )
                        plog(
                            "Fraction through warming cycle: "
                            + str(frac_through_warming)
                        )
                        self.devices["main_cam"]._set_setpoint(
                            float(
                                self.devices["main_cam"].setpoint
                                + (frac_through_warming) *
                                self.devices["main_cam"].day_warm_degrees
                            )
                        )
                        self.devices["main_cam"]._set_cooler_on()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))
                        self.last_time_camera_was_warm = time.time()

                    # Ramp cool temperature
                    # Defined as beginning an hour before "Eve Bias Dark" to ramp to the setpoint.
                    # If the observatory is not too hot, set up cooling for biases
                    elif (
                        self.devices["main_cam"].day_warm
                        and (not self.too_hot_in_observatory)
                        and (
                            g_dev["events"]["Eve Bias Dark"] - ephem.hour
                            < ephem.now()
                            < g_dev["events"]["Eve Bias Dark"]
                        )
                    ):
                        plog("In Camera Cooling Ramping cycle of the day")
                        frac_through_warming = 1 - (
                            ((g_dev["events"]["Eve Bias Dark"]) - ephem.now())
                            / ephem.hour
                        )
                        plog(
                            "Fraction through cooling cycle: "
                            + str(frac_through_warming)
                        )
                        if frac_through_warming > 0.66:
                            self.devices["main_cam"]._set_setpoint(
                                float(self.devices["main_cam"].setpoint))
                            self.devices["main_cam"]._set_cooler_on()
                            self.last_time_camera_was_warm = time.time()
                        else:
                            self.devices["main_cam"]._set_setpoint(
                                float(
                                    self.devices["main_cam"].setpoint
                                    + (1 - (frac_through_warming * 1.5))
                                    * self.devices["main_cam"].day_warm_degrees
                                )
                            )
                            self.devices["main_cam"]._set_cooler_on()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))

                    # Don't bother trying to cool for biases if too hot in observatory.
                    # Don't even bother for flats, it just won't get there.
                    # Just aim for clock & auto focus
                    elif (
                        self.devices["main_cam"].day_warm
                        and (self.too_hot_in_observatory)
                        and (
                            g_dev["events"]["Clock & Auto Focus"] - ephem.hour
                            < ephem.now()
                            < g_dev["events"]["Clock & Auto Focus"]
                        )
                    ):
                        plog(
                            "In Camera Cooling Ramping cycle aiming for Clock & Auto Focus"
                        )
                        frac_through_warming = 1 - (
                            ((g_dev["events"]["Clock & Auto Focus"]) - ephem.now())
                            / ephem.hour
                        )
                        plog(
                            "Fraction through cooling cycle: "
                            + str(frac_through_warming)
                        )
                        if frac_through_warming > 0.8:
                            self.devices["main_cam"]._set_setpoint(
                                float(self.devices["main_cam"].setpoint))
                            self.devices["main_cam"]._set_cooler_on()
                        else:
                            self.devices["main_cam"]._set_setpoint(
                                float(
                                    self.devices["main_cam"].setpoint
                                    + (1 - frac_through_warming)
                                    * self.devices["main_cam"].day_warm_degrees
                                )
                            )
                            self.devices["main_cam"]._set_cooler_on()
                            self.last_time_camera_was_warm = time.time()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))

                    # Nighttime temperature
                    elif (
                        self.devices["main_cam"].day_warm
                        and not (self.too_hot_in_observatory)
                        and (
                            g_dev["events"]["Eve Bias Dark"]
                            < ephem.now()
                            < g_dev["events"]["End Morn Bias Dark"]
                        )
                    ):
                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint))
                        self.devices["main_cam"]._set_cooler_on()

                    elif (
                        self.devices["main_cam"].day_warm
                        and (self.too_hot_in_observatory)
                        and self.open_and_enabled_to_observe
                        and (
                            g_dev["events"]["Clock & Auto Focus"]
                            < ephem.now()
                            < g_dev["events"]["End Morn Bias Dark"]
                        )
                    ):
                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint))
                        self.devices["main_cam"]._set_cooler_on()

                    elif (
                        self.devices["main_cam"].day_warm
                        and (self.too_hot_in_observatory)
                        and not self.open_and_enabled_to_observe
                        and (
                            g_dev["events"]["Clock & Auto Focus"]
                            < ephem.now()
                            < g_dev["events"]["End Morn Bias Dark"]
                        )
                    ):
                        plog(
                            "Focusser reporting too high a temperature in the observatory"
                        )
                        plog(
                            "The roof is also shut, so keeping camera at the day_warm temperature"
                        )

                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint +
                                  self.devices["main_cam"].day_warm_degrees)
                        )
                        # Some cameras need to be sent this to change the temperature also.. e.g. TheSkyX
                        self.devices["main_cam"]._set_cooler_on()
                        self.last_time_camera_was_warm = time.time()
                        plog("Temp set to " +
                             str(self.devices["main_cam"].current_setpoint))

                    elif (
                        g_dev["events"]["Eve Bias Dark"]
                        < ephem.now()
                        < g_dev["events"]["End Morn Bias Dark"]
                    ):
                        self.devices["main_cam"]._set_setpoint(
                            float(self.devices["main_cam"].setpoint))
                        self.devices["main_cam"]._set_cooler_on()

                if not self.mountless_operation:
                    # Check that the site is still connected to the net.
                    if test_connect():
                        self.time_of_last_live_net_connection = time.time()
                        self.net_connection_dead = False
                    if (time.time() - self.time_of_last_live_net_connection) > 600:
                        plog(
                            "Warning, last live net connection was over ten minutes ago"
                        )
                    if (time.time() - self.time_of_last_live_net_connection) > 1200:
                        plog(
                            "Last connection was over twenty minutes ago. Running a further test or two"
                        )
                        if test_connect(host="http://dev.photonranch.org"):
                            plog(
                                "Connected to photonranch.org, so it must be that Google is down. Connection is live."
                            )
                            self.time_of_last_live_net_connection = time.time()
                        elif test_connect(host="http://aws.amazon.com"):
                            plog(
                                "Connected to aws.amazon.com. Can't connect to Google or photonranch.org though."
                            )
                            self.time_of_last_live_net_connection = time.time()
                        else:
                            plog(
                                "Looks like the net is down, closing up and parking the observatory"
                            )
                            self.open_and_enabled_to_observe = False
                            self.net_connection_dead = True
                            if (
                                not self.devices["sequencer"].morn_bias_dark_latch
                                and not self.devices["sequencer"].bias_dark_latch
                            ):
                                self.cancel_all_activity()
                            if not self.devices["mount"].rapid_park_indicator:
                                plog("Parking scope due to inactivity")
                                if self.devices["mount"].home_before_park:
                                    self.devices["mount"].home_command()
                                self.devices["mount"].park_command()
                                self.time_of_last_slew = time.time()
                # wait for safety_check_period
                time.sleep(self.safety_check_period)

            except:
                plog(
                    "Something went wrong in safety check loop. It is ok.... it is a try/except"
                )
                plog("But we should prevent any crashes.")
                plog(traceback.format_exc())

                # If theskyx is rebooting wait
                while self.rebooting_theskyx:
                    plog("waiting for theskyx to reboot in the except function")
                    time.sleep(5)

    def core_command_and_sequencer_loop(self):
        """
        This compact little function is the heart of the code in the sense this is repeatedly
        called. It checks for any new commands from AWS and runs them.
        """
        not_slewing = False
        if self.mountless_operation:
            not_slewing = True
        elif not self.devices["mount"].return_slewing():
            not_slewing = True

        # Check that there isn't individual commands to be run
        if (
            (not self.devices["main_cam"].running_an_exposure_set)
            and not self.devices["sequencer"].total_sequencer_control
            and (not self.stop_processing_command_requests)
            and not_slewing
            and not self.pointing_recentering_requested_by_platesolve_thread
            and not self.pointing_correction_requested_by_platesolve_thread
        ):
            while self.cmd_queue.qsize() > 0:
                if (
                    not self.stop_processing_command_requests
                    and not self.devices["main_cam"].running_an_exposure_set
                    and not self.devices["sequencer"].block_guard
                    and not self.devices["sequencer"].total_sequencer_control
                    and not_slewing
                    and not self.pointing_recentering_requested_by_platesolve_thread
                    and not self.pointing_correction_requested_by_platesolve_thread
                ):  # This is to stop multiple commands running over the top of each other.
                    self.stop_processing_command_requests = True
                    cmd = self.cmd_queue.get()
                    device_instance = cmd["deviceInstance"]
                    plog("obs.scan_request: ", cmd)
                    device_type = cmd["deviceType"]

                    if device_type == "enclosure":
                        plog(
                            "An OBS has mistakenly received an enclosure command! Ignoring."
                        )
                    else:
                        device = self.all_devices[device_type][device_instance]
                        try:
                            device.parse_command(cmd)
                        except Exception as e:
                            plog(traceback.format_exc())
                            plog("Exception in obs.scan_requests:  ",
                                 e, "cmd:  ", cmd)

                    self.stop_processing_command_requests = False
                    time.sleep(1)
                else:
                    time.sleep(1)
        # Check there isn't sequencer commands to run.
        if self.status_count > 1:  # Give time for status to form
            self.devices["sequencer"].manager()  # Go see if there is something new to do.

    def run(self):
        try:
            # Keep the main thread alive, otherwise signals are ignored
            while True:
                self.core_command_and_sequencer_loop()
                time.sleep(2.5)
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            plog("Finishing loops and exiting...")
            self.stopped = True
            return

    def ptrarchive_uploader(self, pri_image):
        upload_timer = time.time()
        if pri_image is None:
            plog("Got an empty entry in ptrarchive_queue.")
        else:
            # Here we parse the file, set up and send to AWS
            filename = pri_image[1][1]
            filepath = pri_image[1][0] + filename  # Full path to file on disk

            time_put_in_queue = pri_image[1][2]

            if filepath == "":
                print("blank entry in ptrarchive uploader")

            # Check it is there
            if not os.path.exists(filepath):
                if (time.time() - time_put_in_queue) < 43200:
                    if (time.time() - time_put_in_queue) > 600:
                        plog(
                            filepath + " not there yet, chucking it back in the queue."
                        )
                    self.enqueue_for_PTRarchive(26000000, "", filepath)
                else:
                    plog("WAITED TOO LONG! " + filepath + " never turned up!")
                return ""

            # Check it is no small
            if "token" not in filepath and os.stat(filepath).st_size < 100:
                if (time.time() - time_put_in_queue) < 43200:
                    if (time.time() - time_put_in_queue) > 600:
                        plog(
                            filepath
                            + " is there but still small - likely still writing out, chucking it back in the queue."
                        )
                    self.enqueue_for_PTRarchive(26000000, "", filepath)
                else:
                    plog("WAITED TOO LONG! " + filepath + " never turned up!")
                return ""

            # Only ingest fits.fz files to the PTR archive.
            try:
                broken = 0
                with open(filepath, "rb") as fileobj:
                    if filepath.split(".")[-1] == "token":
                        files = {"file": (filepath, fileobj)}
                        aws_resp = authenticated_request(
                            "POST", "/upload/", {"object_name": filename}
                        )
                        retry = 0
                        while retry < 10:
                            retry = retry + 1
                            try:
                                plog("Attempting upload of token")
                                plog(str(files))
                                token_output = reqs.post(
                                    aws_resp["url"],
                                    data=aws_resp["fields"],
                                    files=files,
                                    timeout=45,
                                )
                                plog(token_output)
                                if "204" in str(token_output):
                                    try:
                                        os.remove(filepath)
                                    except:
                                        self.laterdelete_queue.put(
                                            filepath, block=False
                                        )
                                    return "Nightly token uploaded."
                                else:
                                    plog("Not successful, attempting token again.")
                            except:
                                plog("Non-fatal connection glitch for a file posted.")
                                plog(files)
                                plog(traceback.format_exc())
                                time.sleep(5)

                    # and (not frame_exists(fileobj)):
                    elif self.env_exists == True:
                        try:
                            # Get header explicitly out to send up
                            # This seems to be necessary
                            tempheader = fits.open(filepath)
                            try:
                                tempheader = tempheader[1].header
                            except:
                                # Calibrations are not fz'ed so have the header elsewhere.
                                tempheader = tempheader[0].header

                            headerdict = {}
                            for entry in tempheader.keys():
                                headerdict[entry] = tempheader[entry]
                            #20250112  Deleting below.   WER
                            #plog("obs line 2563, header;  ", headerdict)   #NB try to debug missing value
                            # 'frame_basename,size,DATE-OBS,DAY-OBS,INSTRUME,SITEID,TELID')  20250112 WER
                            upload_file_and_ingest_to_archive(
                                fileobj, file_metadata=headerdict
                            )

                            # Only remove file if successfully uploaded
                            if ("calibmasters" not in filepath) or (
                                "ARCHIVE_" in filepath
                            ):
                                try:
                                    os.remove(filepath)
                                except:
                                    self.laterdelete_queue.put(
                                        filepath, block=False)

                        except ocs_ingester.exceptions.NonFatalDoNotRetryError:
                            plog(
                                "Apprently this file already exists in the archive: "
                                + str(filepath)
                            )
                            broken = 1

                        except ocs_ingester.exceptions.DoNotRetryError:
                            plog("Couldn't upload to PTR archive: " + str(filepath))
                            plog(traceback.format_exc())
                            #breakpoint()
                            broken = 1
                        except Exception as e:
                            if "urllib3.exceptions.ConnectTimeoutError" in str(
                                traceback.format_exc()
                            ):
                                plog("timeout in ingester")

                            elif "requests.exceptions.ConnectTimeout" in str(
                                traceback.format_exc()
                            ):
                                plog("timeout in ingester")

                            elif "TimeoutError" in str(traceback.format_exc()):
                                plog("timeout in ingester")

                            elif "list index out of range" in str(e):
                                # This error is thrown when there is a corrupt file
                                broken = 1

                            elif "timed out." in str(e) or "TimeoutError" in str(e):
                                # Not broken, just bung it back in the queue for later
                                plog("Timeout glitch, trying again later: ", e)
                                time.sleep(10)
                                self.ptrarchive_queue.put(
                                    pri_image, block=False)
                                # And give it a little sleep
                                return str(filepath.split("/")[-1]) + " timed out."

                            elif "credential_provider" in str(
                                e
                            ) or "endpoint_resolver" in str(e):
                                plog(
                                    "Credential provider error for the ptrarchive, bunging a file back in the queue."
                                )
                                time.sleep(10)
                                self.ptrarchive_queue.put(
                                    pri_image, block=False)
                                return (
                                    str(filepath.split("/")[-1])
                                    + " got an odd error, but retrying."
                                )

                            else:
                                plog(filepath)
                                plog(
                                    "couldn't send to PTR archive for some reason: ", e
                                )
                                plog(traceback.format_exc())
                                # And give it a little sleep
                                time.sleep(10)
                                broken = 1

                if broken == 1:
                    try:
                        shutil.move(filepath, self.broken_path + filename)
                    except:
                        plog("Couldn't move " + str(filepath) +
                             " to broken folder.")
                        self.laterdelete_queue.put(filepath, block=False)
                    return str(filepath.split("/")[-1]) + " broken."

            except Exception as e:
                plog("something strange in the ptrarchive uploader", e)
                return "something strange in the ptrarchive uploader"

            upload_timer = time.time() - upload_timer
            hours_to_go = (
                self.ptrarchive_queue.qsize() * upload_timer / 60 / 60
            ) / int(self.config["number_of_simultaneous_ptrarchive_streams"])

            return (
                str(filepath.split("/")[-1])
                + " sent to archive. Queue Size: "
                + str(self.ptrarchive_queue.qsize())
                + ". "
                + str(round(hours_to_go, 1))
                + " hours to go."
            )

    # Note this is a thread!
    def scan_request_thread(self):
        while True:
            if (
                not self.scan_request_queue.empty()
            ) and not self.currently_scan_requesting:
                self.scan_request_queue.get(block=False)
                self.currently_scan_requesting = True
                self.scan_requests()
                self.currently_scan_requesting = False
                self.scan_request_queue.task_done()
                # We don't want multiple requests straight after one another, so clear the queue.
                with self.scan_request_queue.mutex:
                    self.scan_request_queue.queue.clear()
                time.sleep(3)

            # Check at least every 10 seconds even if not requested
            elif (
                time.time() - self.get_new_job_timer > 10
                and not self.currently_scan_requesting
            ):
                self.get_new_job_timer = time.time()
                self.currently_scan_requesting = True
                self.scan_requests()
                self.currently_scan_requesting = False
                time.sleep(3)
            else:
                # Need this to be as LONG as possible.  Essentially this sets the rate of checking scan requests.
                time.sleep(3)

    # Note this is a thread!
    def calendar_block_thread(self):
        while True:
            if not self.calendar_block_queue.empty():
                #one_at_a_time = 1
                self.calendar_block_queue.get(block=False)
                self.currently_updating_calendar_blocks = True
                self.devices["sequencer"].update_calendar_blocks()
                self.currently_updating_calendar_blocks = False
                self.calendar_block_queue.task_done()
                time.sleep(3)
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(5)

    # Note this is a thread!
    # It also produces the '.' heartbeat to let you know it is running.
    def update_status_thread(self):
        while True:
            not_slewing = False
            if self.mountless_operation:
                not_slewing = True
            elif not self.devices["mount"].return_slewing():
                not_slewing = True

            if time.time()-self.pulse_timer >30:
                self.pulse_timer=time.time()
                plog('.')

            if (
                not_slewing
            ):  # Stop automatic status update while slewing to allow mount full status throughput
                if not self.update_status_queue.empty():
                    request = self.update_status_queue.get(block=False)
                    if request == "mountonly":
                        self.update_status(mount_only=True, dont_wait=True)
                    else:
                        self.update_status()
                    self.update_status_queue.task_done()
                    if not request == "mountonly":
                        time.sleep(2)

                # Update status on at lest a 30s period if not requested
                elif (time.time() - self.time_last_status) > 30:
                    self.update_status()
                    self.time_last_status = time.time()
                    time.sleep(2)

                else:
                    # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                    time.sleep(0.2)
            else:
                time.sleep(0.5)

    # Note this is a thread!
    def send_to_ptrarchive(self):
        """Sends queued files to AWS.

        Large fpacked fits are uploaded using the ocs-ingester, which
        adds the image to the PTR archive database.

        This is intended to transfer slower files not needed for UI responsiveness

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        number_of_simultaneous_uploads = self.config[
            "number_of_simultaneous_ptrarchive_streams"
        ]

        while True:
            if not self.ptrarchive_queue.empty():
                items = []
                for q in range(
                    min(number_of_simultaneous_uploads,
                        self.ptrarchive_queue.qsize())
                ):
                    items.append(self.ptrarchive_queue.get(block=False))

                with ThreadPool(processes=number_of_simultaneous_uploads) as pool:
                    for result in pool.map(self.ptrarchive_uploader, items):
                        self.ptrarchive_queue.task_done()
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(2)

    def send_status_process(self):
        """

        This sends statuses through one at a time.

        """

        while True:
            if not self.send_status_queue.empty():
                pre_upload = time.time()
                received_status = self.send_status_queue.get(block=False)

                #print(received_status[0], received_status[1], received_status[2])
                send_status(
                    received_status[0], received_status[1], received_status[2])
                self.send_status_queue.task_done()
                upload_time = time.time() - pre_upload
                self.status_interval = 2 * upload_time
                if self.status_interval > 10:
                    self.status_interval = 10
                self.status_upload_time = upload_time

                not_slewing = False
                if self.mountless_operation:
                    not_slewing = True
                elif not self.devices["mount"].return_slewing():
                    not_slewing = True

                if not_slewing:  # Don't wait while slewing.
                    time.sleep(max(2, self.status_interval))
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                if not self.mountless_operation:
                    # Don't wait while slewing.
                    if not self.devices["mount"].return_slewing():
                        time.sleep(max(2, self.status_interval))

    def laterdelete_process(self):
        """This is a thread where things that fail to get
        deleted from the filesystem go to get deleted later on.
        Usually due to slow or network I/O
        """

        while True:
            if not self.laterdelete_queue.empty():
                (deletefilename) = self.laterdelete_queue.get(block=False)
                self.laterdelete_queue.task_done()
                try:
                    os.remove(deletefilename)
                except:
                    self.laterdelete_queue.put(deletefilename, block=False)
                time.sleep(2)
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(2)

    def sendtouser_process(self):
        """This is a thread where things that fail to get
        deleted from the filesystem go to get deleted later on.
        Usually due to slow or network I/O
        """

        while True:
            if not self.sendtouser_queue.empty():
                while not self.sendtouser_queue.empty():
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
                        # plog(traceback.format_exc())
                    self.sendtouser_queue.task_done()
            else:
                time.sleep(0.25)


    def platesolve_process(self):
        """This is the platesolve queue that happens in a different process
        than the main thread. Platesolves can take 5-10, up to 30 seconds sometimes
        to run, so it is an overhead we can't have hanging around. This thread attempts
        a platesolve and uses the solution and requests a telescope nudge/i
        if the telescope has not slewed in the intervening time between beginning
        the platesolving process and completing it.

        """

        while True:
            if not self.platesolve_queue.empty():
                self.platesolve_is_processing = True

                (
                    platesolve_token,
                    hduheader,
                    cal_path,
                    cal_name,
                    frame_type,
                    time_platesolve_requested,
                    pixscale,
                    pointing_ra,
                    pointing_dec,
                    firstframesmartstack,
                    useastronometrynet,
                    pointing_exposure,
                    jpeg_filename,
                    path_to_jpeg, # not including filename
                    image_or_reference,
                    exposure_time,
                ) = self.platesolve_queue.get(block=False)

                # Initial blind plate solve can take a long time, so an appropriate wait for the first one is appropriate
                if  pixscale == None: #np.isnan(pixscale) or
                    timeout_time = 800# + exposure_time + \
                        #self.devices["main_cam"].readout_time
                else:
                    timeout_time = 180# + exposure_time + \
                        #self.devices["main_cam"].readout_time

                platesolve_timeout_timer = time.time()
                if image_or_reference == "reference":

                    while (
                        not os.path.exists(platesolve_token)
                        and (time.time() - platesolve_timeout_timer) < timeout_time
                    ):
                        time.sleep(0.5)

                if (time.time() - platesolve_timeout_timer) > timeout_time:
                    plog("waiting for platesolve token timed out")
                    solve = "error"

                    # try:
                    #     os.system("taskkill /IM ps3cli.exe /F")
                    # except:
                    #     pass
                else:
                    if image_or_reference == "reference":
                        (imagefilename, imageMode) = pickle.load(
                            open(platesolve_token, "rb")
                        )
                        # Need to raise the background to fit into uint16
                        raised_array=np.load(imagefilename)
                        raised_array=raised_array - np.nanmin(raised_array)
                        hdufocusdata = np.maximum(raised_array,0).astype(np.uint16)
                        del raised_array
                        hduheader = fits.open(imagefilename.replace(".npy", ".head"))[
                            0
                        ].header

                    else:
                        # Need to raise the background to fit into uint16
                        raised_array=platesolve_token - np.nanmin(platesolve_token)
                        hdufocusdata = np.maximum(raised_array,0).astype(np.uint16)
                        del raised_array
                        del platesolve_token

                    is_osc = self.devices["main_cam"].settings["is_osc"]

                    # Do not bother platesolving unless it is dark enough!!
                    if not (
                        g_dev["events"]["Civil Dusk"]
                        < ephem.now()
                        < g_dev["events"]["Civil Dawn"]
                    ):
                        plog("Too bright to consider platesolving!")
                    else:
                        try:
                            try:
                                os.remove(
                                    self.local_calibration_path + "platesolve.pickle"
                                )
                                os.remove(
                                    self.local_calibration_path
                                    + "platesolve.temppickle"
                                )
                            except:
                                pass

                            target_ra = self.devices["mount"].last_ra_requested
                            target_dec = self.devices["mount"].last_dec_requested

                            if self.devices["sequencer"].block_guard and not self.devices["sequencer"].focussing:
                                target_ra = self.devices["sequencer"].block_ra
                                target_dec = self.devices["sequencer"].block_dec

                            platesolve_crop = 0.0

                            # yet another pickle debugger.
                            if True:
                                pickle.dump(
                                    [
                                        hdufocusdata,
                                        hduheader,
                                        self.local_calibration_path,
                                        cal_name,
                                        frame_type,
                                        time_platesolve_requested,
                                        pixscale,
                                        pointing_ra,
                                        pointing_dec,
                                        platesolve_crop,
                                        False,
                                        1,
                                        self.devices["main_cam"].settings["saturate"],
                                        self.devices["main_cam"].camera_known_readnoise,
                                        self.config['minimum_realistic_seeing'],
                                        is_osc,
                                        useastronometrynet,
                                        pointing_exposure,
                                        f'{path_to_jpeg}{jpeg_filename}',
                                        target_ra,
                                        target_dec
                                    ],
                                    open('subprocesses/testplatesolvepickle','wb')
                                )


                            #breakpoint()

                            try:
                                platesolve_subprocess = subprocess.Popen(
                                    ["python", "subprocesses/Platesolveprocess.py"],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    bufsize=0,
                                )
                            except OSError:
                                plog(traceback.format_exc())
                                pass

                            try:
                                pickle.dump(
                                    [
                                        hdufocusdata,
                                        hduheader,
                                        self.local_calibration_path,
                                        cal_name,
                                        frame_type,
                                        time_platesolve_requested,
                                        pixscale,
                                        pointing_ra,
                                        pointing_dec,
                                        platesolve_crop,
                                        False,
                                        1,
                                        self.devices["main_cam"].settings["saturate"],
                                        self.devices["main_cam"].camera_known_readnoise,
                                        self.config["minimum_realistic_seeing"],
                                        is_osc,
                                        useastronometrynet,
                                        pointing_exposure,
                                        f'{path_to_jpeg}{jpeg_filename}',
                                        target_ra,
                                        target_dec,
                                    ],
                                    platesolve_subprocess.stdin,
                                )
                            except:
                                plog("Problem in the platesolve pickle dump")
                                plog(traceback.format_exc())

                            del hdufocusdata

                            platesolve_timeout_timer=time.time()
                            while not os.path.exists(self.local_calibration_path + 'platesolve.pickle') and (time.time() - platesolve_timeout_timer) < timeout_time:
                                time.sleep(0.5)

                            if (time.time() - platesolve_timeout_timer) > timeout_time:
                                plog("platesolve timed out")
                                solve = "error"
                                platesolve_subprocess.kill()

                                # try:
                                #     os.system("taskkill /IM ps3cli.exe /F")
                                # except:
                                #     pass

                            elif os.path.exists(
                                self.local_calibration_path + "platesolve.pickle"
                            ):
                                solve = pickle.load(
                                    open(
                                        self.local_calibration_path
                                        + "platesolve.pickle",
                                        "rb",
                                    )
                                )
                            else:
                                solve = "error"

                            try:
                                os.remove(
                                    self.local_calibration_path + "platesolve.pickle"
                                )
                            except:
                                plog("Could not remove platesolve pickle. ")

                            if solve == "error":
                                # send up the platesolve image
                                info_image_channel = 1 # send as an info image to this channel
                                self.enqueue_for_fastUI(
                                    path_to_jpeg, jpeg_filename, exposure_time, info_image_channel
                                )

                                plog("Planewave solve came back as error")
                                self.last_platesolved_ra = np.nan
                                self.last_platesolved_dec = np.nan
                                self.last_platesolved_ra_err = np.nan
                                self.last_platesolved_dec_err = np.nan
                                self.platesolve_errors_in_a_row = (
                                    self.platesolve_errors_in_a_row + 1
                                )
                                self.platesolve_is_processing = False

                            else:
                                # send up the platesolve image
                                info_image_channel = 1 # send as an info image to this channel
                                self.enqueue_for_fastUI(
                                    path_to_jpeg, jpeg_filename, exposure_time, info_image_channel
                                )

                                try:
                                    plog(
                                        "PW Solves: ",
                                        round(solve["ra_j2000_hours"], 5),
                                        round(solve["dec_j2000_degrees"], 4),
                                    )
                                except:
                                    plog("couldn't print PW solves.... why?")
                                    plog(solve)

                                solved_ra = solve["ra_j2000_hours"]
                                solved_dec = solve["dec_j2000_degrees"]
                                solved_arcsecperpixel = abs(solve["arcsec_per_pixel"])
                                plog(
                                    "1x1 pixelscale solved: "
                                    + str(solved_arcsecperpixel)
                                )

                                # If this is the first pixelscale gotten, then it is the pixelscale!
                                if self.devices["main_cam"].pixscale == None:
                                    self.devices["main_cam"].pixscale = abs(
                                        solved_arcsecperpixel)

                                if (
                                    (self.devices["main_cam"].pixscale * 0.9)
                                    < float(abs(solved_arcsecperpixel))
                                    < (self.devices["main_cam"].pixscale * 1.1)
                                ):
                                    self.pixelscale_shelf = shelve.open(
                                        self.obsid_path
                                        + "ptr_night_shelf/"
                                        + "pixelscale"
                                        + self.devices["main_cam"].alias
                                        + str(self.name)
                                    )
                                    try:
                                        pixelscale_list = self.pixelscale_shelf[
                                            "pixelscale_list"
                                        ]
                                    except:
                                        pixelscale_list = []
                                    pixelscale_list.append(
                                        float(abs(solved_arcsecperpixel))
                                    )
                                    too_long = True
                                    while too_long:
                                        if len(pixelscale_list) > 100:
                                            pixelscale_list.pop(0)
                                        else:
                                            too_long = False
                                    self.pixelscale_shelf[
                                        "pixelscale_list"
                                    ] = pixelscale_list
                                    self.pixelscale_shelf.close()

                                err_ha = target_ra - solved_ra
                                err_dec = target_dec - solved_dec

                                if not self.devices["mount"].model_on:
                                    mount_deviation_ha = pointing_ra - solved_ra
                                    mount_deviation_dec = pointing_dec - solved_dec
                                else:
                                    (
                                        corrected_pointing_ra,
                                        corrected_pointing_dec,
                                        _,
                                        _,
                                    ) = self.devices["mount"].transform_mechanical_to_icrs(
                                        pointing_ra,
                                        pointing_dec,
                                        self.devices["mount"].rapid_pier_indicator,
                                    )

                                    mount_deviation_ha = (
                                        corrected_pointing_ra - solved_ra
                                    )
                                    mount_deviation_dec = (
                                        corrected_pointing_dec - solved_dec
                                    )

                                    if abs(mount_deviation_ha) > 10:
                                        plog(
                                            "BIG deviation in HA... whats going on?")
                                        plog(mount_deviation_ha)
                                        plog(corrected_pointing_ra)
                                        plog(solved_ra)
                                        plog(pointing_ra)
                                    else:
                                        plog("Reasonable ha deviation")

                                # Check that the RA doesn't cross over zero, if so, bring it back around
                                if err_ha > 12:
                                    plog("BIG CHANGE ERR_HA")
                                    plog(err_ha)
                                    err_ha = err_ha - 24
                                    plog(err_ha)
                                elif err_ha < -12:
                                    plog("BIG CHANGE ERR_HA")
                                    plog(err_ha)
                                    err_ha = err_ha + 24
                                    plog(err_ha)

                                radial_distance = pow(
                                    pow(
                                        err_ha
                                        * math.cos(math.radians(pointing_dec))
                                        * 15
                                        * 3600,
                                        2,
                                    )
                                    + pow(err_dec * 3600, 2),
                                    0.5,
                                )

                                plog(
                                    "Radial Deviation, Ra, Dec  (asec): ",
                                    str(round(radial_distance, 1))
                                    + ",  "
                                    + str(round(err_ha * 15 * 3600, 1))
                                    + ",  "
                                    + str(round(err_dec * 3600, 1)),
                                )

                                self.last_platesolved_ra = solve["ra_j2000_hours"]
                                self.last_platesolved_dec = solve["dec_j2000_degrees"]
                                self.last_platesolved_ra_err = target_ra - solved_ra
                                self.last_platesolved_dec_err = target_dec - solved_dec
                                self.platesolve_errors_in_a_row = 0

                                # Reset Solve timers
                                self.last_solve_time = datetime.datetime.now()
                                self.images_since_last_solve = 0


                                self.drift_tracker_counter = (
                                    self.drift_tracker_counter + 1
                                )


                                if self.sync_after_platesolving:
                                    plog("Syncing mount after this solve")

                                    self.devices["mount"].sync_to_pointing(
                                        solved_ra, solved_dec)
                                    self.pointing_correction_requested_by_platesolve_thread = (
                                        False
                                    )
                                    self.sync_after_platesolving = False

                                # If we are WAY out of range, then reset the mount reference and attempt moving back there.
                                elif not self.auto_centering_off:


                                    # Used for calculating relative offset compared to image size
                                    dec_field_asec = (
                                        self.devices["main_cam"].pixscale *
                                        self.devices["main_cam"].imagesize_x
                                    )
                                    ra_field_asec = (
                                        self.devices["main_cam"].pixscale *
                                        self.devices["main_cam"].imagesize_y
                                    )

                                    if (
                                        abs(err_ha * 15 * 3600)
                                        > self.worst_potential_pointing_in_arcseconds
                                    ) or (
                                        abs(err_dec * 3600)
                                        > self.worst_potential_pointing_in_arcseconds
                                    ):
                                        err_ha = 0
                                        err_dec = 0
                                        plog(
                                            "Platesolve has found that the current suggested pointing is way off!"
                                        )
                                        plog(
                                            "This may be a poor pointing estimate.")
                                        plog(
                                            "This is more than a simple nudge, so not nudging the scope."
                                        )
                                        # self.send_to_user(
                                        #     "Platesolve detects pointing far out, RA: "
                                        #     + str(round(err_ha * 15 * 3600, 2))
                                        #     + " DEC: "
                                        #     + str(round(err_dec * 3600, 2))
                                        # )

                                    elif (
                                        self.time_of_last_slew
                                        > time_platesolve_requested
                                    ):
                                        plog(
                                            "detected a slew since beginning platesolve... bailing out of platesolve."
                                        )


                                    # Only recenter if out by more than 1%
                                    elif (
                                        abs(err_ha * 15 * 3600) > 0.01 *
                                            ra_field_asec
                                    ) or (abs(err_dec * 3600) > 0.01 * dec_field_asec):
                                        self.pointing_correction_requested_by_platesolve_thread = (
                                            True
                                        )
                                        self.pointing_correction_request_time = (
                                            time.time()
                                        )
                                        self.pointing_correction_request_ra = (
                                            pointing_ra + err_ha
                                        )
                                        self.pointing_correction_request_dec = (
                                            pointing_dec + err_dec
                                        )
                                        self.pointing_correction_request_ra_err = err_ha
                                        self.pointing_correction_request_dec_err = (
                                            err_dec
                                        )


                                        drift_timespan = (
                                            time.time() - self.drift_tracker_timer
                                        )

                                        if drift_timespan > 180:
                                            self.drift_arcsec_ra_arcsecperhour = (
                                                err_ha * 15 * 3600
                                            ) / (drift_timespan / 3600)
                                            self.drift_arcsec_dec_arcsecperhour = (
                                                err_dec * 3600
                                            ) / (drift_timespan / 3600)
                                            plog(
                                                "Drift calculations in arcsecs per hour, RA: "
                                                + str(
                                                    round(
                                                        self.drift_arcsec_ra_arcsecperhour,
                                                        6,
                                                    )
                                                )
                                                + " DEC: "
                                                + str(
                                                    round(
                                                        self.drift_arcsec_dec_arcsecperhour,
                                                        6,
                                                    )
                                                )
                                            )

                                        if not self.mount_reference_model_off:
                                            if (
                                                target_dec > -85
                                                and target_dec < 85
                                                and g_dev[
                                                    "mnt"
                                                ].last_slew_was_pointing_slew
                                            ):
                                                # The mount reference should only be updated if it is less than a third of the worst potential pointing in arcseconds.....
                                                if (
                                                    abs(err_ha * 15 * 3600)
                                                    < (
                                                        self.worst_potential_pointing_in_arcseconds
                                                        / 3
                                                    )
                                                ) or (
                                                    abs(err_dec * 3600)
                                                    < (
                                                        self.worst_potential_pointing_in_arcseconds
                                                        / 3
                                                    )
                                                ):
                                                    try:
                                                        g_dev[
                                                            "mnt"
                                                        ].last_slew_was_pointing_slew = (
                                                            False
                                                        )
                                                        if self.devices["mount"].pier_side == 0:
                                                            try:
                                                                print(
                                                                    "HA going in "
                                                                    + str(
                                                                        mount_deviation_ha
                                                                    )
                                                                )
                                                                g_dev[
                                                                    "mnt"
                                                                ].record_mount_reference(
                                                                    mount_deviation_ha,
                                                                    mount_deviation_dec,
                                                                    pointing_ra,
                                                                    pointing_dec,
                                                                )

                                                            except Exception as e:
                                                                plog(
                                                                    "Something is up in the mount reference adjustment code ",
                                                                    e,
                                                                )
                                                        else:
                                                            try:
                                                                print(
                                                                    "HA going in "
                                                                    + str(
                                                                        mount_deviation_ha
                                                                    )
                                                                )
                                                                g_dev[
                                                                    "mnt"
                                                                ].record_flip_reference(
                                                                    mount_deviation_ha,
                                                                    mount_deviation_dec,
                                                                    pointing_ra,
                                                                    pointing_dec,
                                                                )
                                                            except Exception as e:
                                                                plog(
                                                                    "Something is up in the mount reference adjustment code ",
                                                                    e,
                                                                )

                                                    except:
                                                        plog(
                                                            "This mount doesn't report pierside"
                                                        )
                                                        plog(
                                                            traceback.format_exc())

                                self.platesolve_is_processing = False
                        except:
                            plog("glitch in the platesolving dimension")
                            plog(traceback.format_exc())

                self.platesolve_is_processing = False
                self.platesolve_queue.task_done()

                if not self.mountless_operation:
                    self.devices["mount"].last_slew_was_pointing_slew = False

                time.sleep(1)

            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(1)

    #   Note this is a thread
    def slow_camera_process(self):
        """
        A place to process non-process dependent images from the camera pile.
        Usually long-term saves to disk and such things
        """

        while True:
            if not self.slow_camera_queue.empty():
                #one_at_a_time = 1
                slow_process = self.slow_camera_queue.get(block=False)
                slow_process = slow_process[1]
                try:
                    # Set up RA and DEC headers
                    # needs to be done AFTER text file is sent up.
                    # Text file RA and Dec and PTRarchive RA and Dec are formatted different
                    try:
                        temphduheader = slow_process[3]
                    except:
                        temphduheader = None

                    if slow_process[0] == "focus":
                        hdufocus = fits.PrimaryHDU()
                        hdufocus.data = slow_process[2]
                        hdufocus.header = temphduheader
                        hdufocus.header["NAXIS1"] = hdufocus.data.shape[0]
                        hdufocus.header["NAXIS2"] = hdufocus.data.shape[1]
                        hdufocus.header["DATE"] = (
                            datetime.date.strftime(
                                datetime.datetime.utcfromtimestamp(
                                    time.time()),
                                "%Y-%m-%d",
                            ),
                            "Date FITS file was written",
                        )
                        hdufocus.writeto(
                            slow_process[1], overwrite=True, output_verify="silentfix"
                        )

                        try:
                            hdufocus.close()
                        except:
                            pass
                        del hdufocus

                    if slow_process[0] == "numpy_array_save":
                        try:
                            np.save(slow_process[1], slow_process[2])
                        except:
                            plog ("numpy file save issue")
                            plog(traceback.format_exc())

                    if slow_process[0] == "fits_file_save":
                        fits.writeto(
                            slow_process[1],
                            slow_process[2],
                            temphduheader,
                            overwrite=True,
                        )

                    if slow_process[0] == "fits_file_save_and_UIqueue":
                        fits.writeto(
                            slow_process[1],
                            slow_process[2],
                            temphduheader,
                            overwrite=True,
                        )
                        filepathaws = slow_process[4]
                        filenameaws = slow_process[5]
                        if "ARCHIVE_" in filenameaws:
                        #     self.enqueue_for_PTRarchive(
                        #         100000000000000, filepathaws, filenameaws
                        #     )
                            pass # skipping ingesting archive calibrations. Won't need the later one either eventually
                        else:
                            self.enqueue_for_calibrationUI(
                                50, filepathaws, filenameaws
                            )

                    if slow_process[0] == "localcalibration":
                        saver = 0
                        saverretries = 0
                        while saver == 0 and saverretries < 10:
                            try:
                                if not os.path.exists(
                                    self.local_dark_folder + "/localcalibrations"
                                ):
                                    os.makedirs(
                                        self.local_dark_folder + "/localcalibrations", mode=0o777
                                    )

                                if "dark" in slow_process[4]:
                                    # Define the base path and subdirectories
                                    base_path = self.local_dark_folder
                                    subdirectories = [
                                        "",
                                        "/localcalibrations/darks/narrowbanddarks",
                                        "/localcalibrations/darks/broadbanddarks",
                                        "/localcalibrations/darks/fortymicroseconddarks",
                                        "/localcalibrations/darks/fourhundredmicroseconddarks",
                                        "/localcalibrations/darks/pointzerozerofourfivedarks",
                                        "/localcalibrations/darks/onepointfivepercentdarks",
                                        "/localcalibrations/darks/fivepercentdarks",
                                        "/localcalibrations/darks/tenpercentdarks",
                                        "/localcalibrations/darks/quartersecdarks",
                                        "/localcalibrations/darks/halfsecdarks",
                                        "/localcalibrations/darks/sevenfivepercentdarks",
                                        "/localcalibrations/darks/onesecdarks",
                                        "/localcalibrations/darks/oneandahalfsecdarks",
                                        "/localcalibrations/darks/twosecdarks",
                                        "/localcalibrations/darks/threepointfivesecdarks",
                                        "/localcalibrations/darks/fivesecdarks",
                                        "/localcalibrations/darks/sevenpointfivesecdarks",
                                        "/localcalibrations/darks/tensecdarks",
                                        "/localcalibrations/darks/fifteensecdarks",
                                        "/localcalibrations/darks/twentysecdarks",
                                        "/localcalibrations/darks/thirtysecdarks",
                                    ]

                                    # Create directories if they do not exist
                                    for subdir in subdirectories:
                                        path = base_path + subdir
                                        if not os.path.exists(path):
                                            os.makedirs(path, mode=0o777)

                                if "flat" in slow_process[4]:
                                    if not os.path.exists(self.local_flat_folder):
                                        os.makedirs(self.local_flat_folder, mode=0o777)

                                # Figure out which folder to send the calibration file to
                                # and delete any old files over the maximum amount to store
                                def manage_files(folder_path, max_files, exclude_pattern=None):
                                    """
                                    Manages files in a directory by ensuring the number of files does not exceed the maximum allowed.
                                    Deletes the oldest files if necessary.
                                    """
                                    files = glob.glob(f"{folder_path}/*.n*")
                                    if exclude_pattern:
                                        files = [f for f in files if exclude_pattern not in f]
                                    while len(files) > max_files:
                                        oldest_file = min(files, key=os.path.getctime)
                                        try:
                                            os.remove(oldest_file)
                                        except:
                                            self.laterdelete_queue.put(oldest_file, block=False)
                                        files = glob.glob(f"{folder_path}/*.n*")


                                def process_file(slow_process, temphduheader, config):
                                    """
                                    Processes a single file based on its type and manages storage for the corresponding folder.
                                    """
                                    base_folder_mapping = {
                                        "bias": self.local_bias_folder,
                                        "dark": self.local_dark_folder,
                                        "broadband_ss_biasdark": os.path.join(self.local_dark_folder, "broadbanddarks"),
                                        "narrowband_ss_biasdark": os.path.join(self.local_dark_folder, "narrowbanddarks"),
                                        "fortymicrosecond_exposure_dark": os.path.join(self.local_dark_folder, "fortymicroseconddarks"),
                                        "fourhundredmicrosecond_exposure_dark": os.path.join(self.local_dark_folder, "fourhundredmicroseconddarks"),
                                        "pointzerozerofourfive_exposure_dark": os.path.join(self.local_dark_folder, "pointzerozerofourfivedarks"),
                                        "onepointfivepercent_exposure_dark": os.path.join(self.local_dark_folder, "onepointfivepercentdarks"),
                                        "fivepercent_exposure_dark": os.path.join(self.local_dark_folder, "fivepercentdarks"),
                                        "tenpercent_exposure_dark": os.path.join(self.local_dark_folder, "tenpercentdarks"),
                                        "quartersec_exposure_dark": os.path.join(self.local_dark_folder, "quartersecdarks"),
                                        "halfsec_exposure_dark": os.path.join(self.local_dark_folder, "halfsecdarks"),
                                        "threequartersec_exposure_dark": os.path.join(self.local_dark_folder, "sevenfivepercentdarks"),
                                        "onesec_exposure_dark": os.path.join(self.local_dark_folder, "onesecdarks"),
                                        "oneandahalfsec_exposure_dark": os.path.join(self.local_dark_folder, "oneandahalfsecdarks"),
                                        "twosec_exposure_dark": os.path.join(self.local_dark_folder, "twosecdarks"),
                                        "threepointfivesec_exposure_dark": os.path.join(self.local_dark_folder, "threepointfivesecdarks"),
                                        "fivesec_exposure_dark": os.path.join(self.local_dark_folder, "fivesecdarks"),
                                        "sevenpointfivesec_exposure_dark": os.path.join(self.local_dark_folder, "sevenpointfivesecdarks"),
                                        "tensec_exposure_dark": os.path.join(self.local_dark_folder, "tensecdarks"),
                                        "fifteensec_exposure_dark": os.path.join(self.local_dark_folder, "fifteensecdarks"),
                                        "twentysec_exposure_dark": os.path.join(self.local_dark_folder, "twentysecdarks"),
                                        "thirtysec_exposure_dark": os.path.join(self.local_dark_folder, "thirtysecdarks"),
                                        "flat": self.local_flat_folder,
                                        "skyflat": self.local_flat_folder,
                                        "screenflat": self.local_flat_folder,
                                    }

                                    file_type = slow_process[4]
                                    folder_path = base_folder_mapping.get(file_type)
                                    if not folder_path:
                                        return  # Skip unsupported file types

                                    tempexposure = temphduheader.get("EXPTIME", "")
                                    tempfilter = temphduheader.get("FILTER", "")

                                    #breakpoint()
                                    # if it is a flat observation, it needs to go in a filtered directory
                                    #
                                    if 'flat' in str(file_type):
                                        if not os.path.exists(self.local_flat_folder):
                                            os.makedirs(self.local_flat_folder, mode=0o777, exist_ok=True)
                                        folder_path=folder_path+ str(tempfilter) + '/'

                                    if not os.path.exists(folder_path):
                                        os.makedirs(folder_path, mode=0o777, exist_ok=True)


                                    file_suffix = f"_{slow_process[7]}_{tempexposure}_.npy" if "flat" not in file_type else f"_{slow_process[7]}_{tempfilter}_{tempexposure}_.npy"
                                    tempfilename = os.path.join(folder_path, slow_process[1].replace(".fits", file_suffix))

                                    # Manage files based on type
                                    max_files = self.devices['main_cam'].settings.get(f"number_of_{file_type}_to_store", 10)
                                    exclude_pattern = "tempbiasdark" if "dark" in file_type else "tempcali" if "flat" in file_type else None
                                    manage_files(folder_path, max_files, exclude_pattern)

                                    return tempfilename


                                # Example usage
                                tempfilename=process_file(slow_process, temphduheader, self.config)



                                # Save the file as an uncompressed numpy binary
                                temparray = np.array(
                                    slow_process[2], dtype=np.uint16)
                                tempmedian = bn.nanmedian(temparray)
                                if tempmedian > 30 and tempmedian < 58000:
                                    np.save(
                                        tempfilename,
                                        np.array(
                                            slow_process[2], dtype=np.uint16),
                                    )
                                else:
                                    plog("Odd median: " + str(tempmedian))
                                    plog(
                                        "Not saving this calibration file: "
                                        + str(tempfilename)
                                    )

                                saver = 1

                            except Exception as e:
                                plog("Failed to write raw file: ", e)
                                if "requested" in str(e) and "written" in str(e):
                                    plog(check_download_cache())
                                plog(traceback.format_exc())
                                time.sleep(10)
                                saverretries = saverretries + 1
                except:
                    plog("Something up in the slow process")
                    plog(traceback.format_exc())
                self.slow_camera_queue.task_done()
                time.sleep(1)

            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(1)

    # Note this is a thread!
    def file_wait_and_act(self):
        """A general purpose wait for file and act thread"""

        while True:
            if not self.file_wait_and_act_queue.empty():
                (filename, timesubmitted, packet) = self.file_wait_and_act_queue.get(
                    block=False
                )

                # Here we parse the file, set up and send to AWS
                try:
                    # If the file is there now
                    if os.path.exists(filename):
                        # To the extent it has a size
                        if os.stat(filename).st_size > 0:
                            if ".fwhm" in filename:
                                try:
                                    with open(filename, "r") as f:
                                        fwhm_info = json.load(f)

                                    self.fwhmresult = {}
                                    self.fwhmresult["FWHM"] = float(
                                        fwhm_info["rfr"])
                                    rfr = float(fwhm_info["rfr"])
                                    self.fwhmresult["mean_focus"] = packet[0]
                                    self.fwhmresult["No_of_sources"] = float(
                                        fwhm_info["sources"]
                                    )
                                    self.fwhmresult["exp_time"] = packet[1]

                                    self.fwhmresult["filter"] = packet[2]
                                    self.fwhmresult["airmass"] = packet[3]
                                except:
                                    plog("something funky in the fwhm area ")
                                    plog(traceback.format_exc())

                                if not np.isnan(self.fwhmresult["FWHM"]):
                                    # Focus tracker code. This keeps track of the focus and if it drifts
                                    # Then it triggers an autofocus.

                                    self.devices["main_focuser"].focus_tracker.pop(0)
                                    self.devices["main_focuser"].focus_tracker.append(
                                        (
                                            self.fwhmresult["mean_focus"],
                                            self.devices["main_focuser"].current_focus_temperature,
                                            self.fwhmresult["exp_time"],
                                            self.fwhmresult["filter"],
                                            self.fwhmresult["airmass"],
                                            round(rfr, 3),
                                        )
                                    )
                                    plog(
                                        "Last ten FWHM (pixels): "
                                        + str(self.devices["main_focuser"].focus_tracker)
                                    )
                                    # If there hasn't been a focus yet, then it can't check it,
                                    # so make this image the last solved focus.
                                    if self.devices["main_focuser"].last_focus_fwhm == None:
                                        self.devices["main_focuser"].last_focus_fwhm = rfr
                                    else:
                                        # Very dumb focus slip deteector
                                        # if (
                                        #     bn.nanmedian(self.devices["main_focuser"].focus_tracker)
                                        #     > self.devices["main_focuser"].last_focus_fwhm
                                        #     + self.config["focus_trigger"]
                                        # ):
                                        #     self.devices["main_focuser"].focus_needed = True
                                        #     self.send_to_user(
                                        #         "FWHM has drifted to:  "
                                        #         + str(round(bn.nanmedian(self.devices["main_focuser"].focus_tracker),2))
                                        #         + " from "
                                        #         + str(self.devices["main_focuser"].last_focus_fwhm)
                                        #         + ".",
                                        #         p_level="INFO")
                                        pass
                                        #print("TEMPORARILY DISABLED 1234")

                        else:
                            self.file_wait_and_act_queue.put(
                                (filename, timesubmitted, packet), block=False
                            )
                    # If it has been less than 3 minutes put it back in
                    elif time.time() - timesubmitted < (
                        300 + packet[1] + self.devices["main_cam"].readout_time
                    ):
                        self.file_wait_and_act_queue.put(
                            (filename, timesubmitted, packet), block=False
                        )
                    else:
                        plog(
                            str(filename)
                            + " seemed to never turn up... not putting back in the queue"
                        )

                except:
                    plog("something strange in the UI uploader")
                    plog((traceback.format_exc()))
                self.file_wait_and_act_queue.task_done()
                time.sleep(1)

            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(5)

    # Note this is a thread!
    def fast_to_ui(self):
        """Sends small files specifically focussed on UI responsiveness to AWS.

        This is primarily a queue for files that need to get to the UI FAST.
        This allows small files to be uploaded simultaneously
        with bigger files being processed by the ordinary queue.

        The pri_image is a tuple, smaller first item has priority.
        The second item is also a tuple containing im_path and name.
        """

        while True:
            if not self.fast_queue.empty():
                pri_image = self.fast_queue.get(block=False)

                # Parse the inputs in the tuple sent to fast_queue
                try:
                    (
                        path_to_file_directory, # doesn't include file itself
                        filename,
                        time_submitted,
                        exposure_time,
                        info_image_channel
                    ) = pri_image

                    filepath = f"{path_to_file_directory}{filename}" # Full path to the file on disk
                except Exception as e:
                    plog("Error in fast_to_ui: problem parsing the arguments")
                    plog(e)
                    plog("This is what was recieved: ", pri_image)
                    plog("fast_to_ui did not upload an image.")
                    continue


                # Here we parse the file, set up and send to AWS
                try:
                    if filepath == "":
                        plog("The fast_queue contained an entry with no path to the image. ") #? Why? MTF finding out.
                        continue

                    # If the file is there now
                    if os.path.exists(filepath) and not "EX20" in filename:
                        # To the extent it has a size
                        if os.stat(filepath).st_size > 0:

                            request_body = {
                                "object_name": filename,
                                "s3_directory": "data" # default to sending as a regular image
                            }
                            if info_image_channel is not None:
                                request_body["s3_directory"] = "info-images"
                                request_body["info_channel"] = info_image_channel

                            aws_resp = authenticated_request("POST", "/upload/", request_body) # this gets the presigned s3 upload url
                            with open(filepath, "rb") as fileobj:
                                files = {"file": (filepath, fileobj)}
                                try:
                                    reqs.post(
                                        aws_resp["url"],
                                        data=aws_resp["fields"],
                                        files=files,
                                        timeout=10,
                                    )
                                except Exception as e:
                                    if (
                                        "timeout" in str(e).lower()
                                        or "SSLWantWriteError"
                                        or "RemoteDisconnected" in str(e)
                                    ):
                                        plog(
                                            "Seems to have been a timeout on the file posted: "
                                            + str(e)
                                            + "Putting it back in the queue."
                                        )
                                        plog(filename)
                                        self.fast_queue.put(pri_image, block=False)
                                    else:
                                        plog(
                                            "Fatal connection glitch for a file posted: "
                                            + str(e)
                                        )
                                        plog(files)
                                        plog((traceback.format_exc()))
                        else:
                            plog(
                                str(filepath)
                                + " is there but has a zero file size so is probably still being written to, putting back in queue."
                            )
                            self.fast_queue.put(pri_image, block=False)
                    # If it has been less than 3 minutes put it back in
                    elif time.time() - time_submitted < 1200 + float(exposure_time):
                        self.fast_queue.put(pri_image, block=False)
                    else:
                        plog(
                            str(filepath)
                            + " seemed to never turn up... not putting back in the queue"
                        )
                except:
                    plog("something strange in the UI uploader")
                    plog((traceback.format_exc()))
                self.fast_queue.task_done()
                time.sleep(0.5)
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(1)

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

        while True:
            if not self.calibrationui_queue.empty():
                pri_image = self.calibrationui_queue.get(block=False)

                try:
                    # Here we parse the file, set up and send to AWS
                    filename = pri_image[1][1]
                    # Full path to file on disk
                    filepath = pri_image[1][0] + filename
                    aws_resp = authenticated_request(
                        "POST", "/upload/", {"object_name": filename}
                    )
                    with open(filepath, "rb") as fileobj:
                        files = {"file": (filepath, fileobj)}
                        try:
                            # Different timeouts for different filesizes.
                            # Large filesizes are usually calibration files during the daytime
                            # So need and can have longer timeouts to get it up the pipe.
                            # However small UI files need to get up in some reasonable amount of time
                            # and have a reasonable timeout so the UI doesn't glitch out.
                            reqs.post(
                                aws_resp["url"],
                                data=aws_resp["fields"],
                                files=files,
                                timeout=1800,
                            )

                        except Exception as e:
                            if (
                                "timeout" in str(e).lower()
                                or "SSLWantWriteError"
                                or "RemoteDisconnected" in str(e)
                            ):
                                plog(
                                    "Seems to have been a timeout on the file posted: "
                                    + str(e)
                                    + "Putting it back in the queue."
                                )
                                plog(filename)
                                self.calibrationui_queue.put(
                                    (100, pri_image[1]), block=False
                                )
                            else:
                                plog(
                                    "Fatal connection glitch for a file posted: "
                                    + str(e)
                                )
                                plog(files)
                                plog((traceback.format_exc()))
                except:
                    plog("something strange in the calibration uploader")
                    plog((traceback.format_exc()))
                self.calibrationui_queue.task_done()
                time.sleep(10)
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(10)

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

        while True:
            if not self.mediumui_queue.empty():
                pri_image = self.mediumui_queue.get(block=False)

                try:
                    # Here we parse the file, set up and send to AWS
                    filename = pri_image[1][1]
                    # Full path to file on disk
                    filepath = pri_image[1][0] + filename
                    timesubmitted = pri_image[1][2]

                    if filepath == "":
                        plog(
                            "found an empty thing in the medium_queue."  #"? Why? MTF finding out."
                        )
                    else:
                        # If the file is there now
                        if os.path.exists(filepath):
                            # To the extent it has a size
                            if os.stat(filepath).st_size > 0:
                                aws_resp = authenticated_request(
                                    "POST", "/upload/", {"object_name": filename}
                                )
                                with open(filepath, "rb") as fileobj:
                                    files = {"file": (filepath, fileobj)}
                                    try:
                                        reqs.post(
                                            aws_resp["url"],
                                            data=aws_resp["fields"],
                                            files=files,
                                            timeout=300,
                                        )
                                    except Exception as e:
                                        if (
                                            "timeout" in str(e).lower()
                                            or "SSLWantWriteError"
                                            or "RemoteDisconnected" in str(e)
                                        ):
                                            plog(
                                                "Seems to have been a timeout on the file posted: "
                                                + str(e)
                                                + "Putting it back in the queue."
                                            )
                                            plog(filename)
                                            self.mediumui_queue.put(
                                                (100, pri_image[1]), block=False
                                            )
                                        else:
                                            plog(
                                                "Fatal connection glitch for a file posted: "
                                                + str(e)
                                            )
                                            plog(files)
                                            plog((traceback.format_exc()))
                            else:
                                plog(
                                    str(filepath)
                                    + " is there but has a zero file size so is probably still being written to, putting back in queue."
                                )
                                self.mediumui_queue.put(
                                    (100, pri_image[1]), block=False
                                )
                        # If it has been less than 3 minutes put it back in
                        elif time.time() - timesubmitted < 300:
                            self.mediumui_queue.put(
                                (100, pri_image[1]), block=False)
                        else:
                            plog(
                                str(filepath)
                                + " seemed to never turn up... not putting back in the queue"
                            )

                except:
                    plog("something strange in the medium-UI uploader")
                    plog((traceback.format_exc()))
                self.mediumui_queue.task_done()
                time.sleep(0.5)
            else:
                # Need this to be as LONG as possible to allow large gaps in the GIL. Lower priority tasks should have longer sleeps.
                time.sleep(3)

    def send_to_user(self, p_log, p_level="INFO"):
        # This is now a queue--- it was actually slowing
        # everything down each time this was called!
        self.sendtouser_queue.put((p_log, p_level), block=False)

    def check_platesolve_and_nudge(self, no_confirmation=True):
        """
        A function periodically called to check if there is a telescope nudge to re-center to undertake.
        """
        if not self.auto_centering_off:
            # Sometimes the pointing is so far off platesolve requests a new slew and recenter

            if self.pointing_recentering_requested_by_platesolve_thread:
                self.pointing_recentering_requested_by_platesolve_thread = False
                self.pointing_correction_requested_by_platesolve_thread = False
                self.devices["mount"].go_command(
                    ra=self.pointing_correction_request_ra,
                    dec=self.pointing_correction_request_dec,
                )
                self.devices["sequencer"].centering_exposure(
                    no_confirmation=no_confirmation, try_hard=True, try_forever=True
                )

                self.drift_tracker_timer = time.time()
                self.drift_tracker_counter = 0
                if self.devices["sequencer"].currently_mosaicing:
                    # Slew to new mosaic pane location.
                    new_ra = (
                        self.devices["sequencer"].mosaic_center_ra
                        + self.devices["sequencer"].current_mosaic_displacement_ra
                    )
                    new_dec = (
                        self.devices["sequencer"].mosaic_center_dec
                        + self.devices["sequencer"].current_mosaic_displacement_dec
                    )
                    new_ra, new_dec = ra_dec_fix_hd(new_ra, new_dec)   #This probably has to do with taking a mosaic near the poles.
                    self.devices["mount"].wait_for_slew(wait_after_slew=False)
                    self.devices["mount"].slew_async_directly(ra=new_ra, dec=new_dec)
                    self.devices["mount"].wait_for_slew(wait_after_slew=False)
                    self.time_of_last_slew = time.time()

            # This block repeats itself in various locations to try and nudge the scope
            # If the platesolve requests such a thing.
            if (
                self.pointing_correction_requested_by_platesolve_thread
            ):
                # Check it hasn't slewed since request, although ignore this check if in smartstack_loop due to dithering.
                if (
                    self.pointing_correction_request_time > self.time_of_last_slew
                ) or self.devices["main_cam"].currently_in_smartstack_loop:
                    plog("Re-centering Telescope.")
                    # Don't always need to be reporting every small recenter.
                    if not self.devices["main_cam"].currently_in_smartstack_loop and not (
                        (
                            abs(self.pointing_correction_request_ra_err)
                            + abs(self.pointing_correction_request_dec_err)
                        )
                        < 0.25
                    ):
                        self.send_to_user("Re-centering Telescope.")
                    self.devices["mount"].wait_for_slew(wait_after_slew=False)
                    self.devices["mount"].previous_pier_side = self.devices["mount"].return_side_of_pier()

                    ranudge = self.pointing_correction_request_ra
                    decnudge = self.pointing_correction_request_dec

                    self.devices["main_cam"].initial_smartstack_ra = copy.deepcopy(ranudge)
                    self.devices["main_cam"].initial_smartstack_dec = copy.deepcopy(
                        decnudge)

                    if ranudge < 0:
                        ranudge = ranudge + 24
                    if ranudge > 24:
                        ranudge = ranudge - 24
                    self.time_of_last_slew = time.time()
                    try:
                        self.devices["mount"].wait_for_slew(wait_after_slew=False)
                        self.devices["mount"].slew_async_directly(
                            ra=ranudge, dec=decnudge)
                        self.devices["mount"].wait_for_slew(wait_after_slew=False)
                    except:
                        plog(traceback.format_exc())
                    if (
                        not self.devices["mount"].previous_pier_side
                        == self.devices["mount"].return_side_of_pier()
                    ):
                        self.send_to_user(
                            "Detected pier flip in re-centering. Re-centering telescope again."
                        )
                        self.devices["mount"].go_command(
                            ra=self.pointing_correction_request_ra,
                            dec=self.pointing_correction_request_dec,
                        )
                        self.devices["sequencer"].centering_exposure(
                            no_confirmation=no_confirmation,
                            try_hard=True,
                            try_forever=True,
                        )
                    self.time_of_last_slew = time.time()
                    self.devices["mount"].wait_for_slew(wait_after_slew=False)

                    self.drift_tracker_timer = time.time()
                    self.drift_tracker_counter = 0

                self.pointing_correction_requested_by_platesolve_thread = False

    def get_enclosure_status_from_aws(self):
        """
        Requests the current enclosure status from the related WEMA.
        """
        uri_status = f"https://status.photonranch.org/status/{self.wema_name}/enclosure/"
        try:
            aws_enclosure_status = reqs.get(uri_status, timeout=20)
            aws_enclosure_status = aws_enclosure_status.json()
            aws_enclosure_status["site"] = self.name

            for enclosurekey in aws_enclosure_status["status"]["enclosure"][
                "enclosure1"
            ].keys():
                aws_enclosure_status["status"]["enclosure"]["enclosure1"][
                    enclosurekey
                ] = aws_enclosure_status["status"]["enclosure"]["enclosure1"][
                    enclosurekey
                ][
                    "val"
                ]

            if self.assume_roof_open:
                aws_enclosure_status["status"]["enclosure"]["enclosure1"][
                    "shutter_status"
                ] = "Sim. Open"
                aws_enclosure_status["status"]["enclosure"]["enclosure1"][
                    "enclosure_mode"
                ] = "Simulated"

            try:
                # To stop status's filling up the queue under poor connection conditions
                # There is a size limit to the queue
                if self.send_status_queue.qsize() < 7:
                    self.send_status_queue.put(
                        (self.name, "enclosure",
                         aws_enclosure_status["status"]),
                        block=False,
                    )

            except Exception as e:
                plog("aws enclosure send failed ", e)

            aws_enclosure_status = aws_enclosure_status["status"]["enclosure"][
                "enclosure1"
            ]

        except Exception as e:
            plog("Failed to get aws enclosure status. Usually not fatal:  ", e)

        try:
            if self.devices["sequencer"].last_roof_status == "Closed" and aws_enclosure_status[
                "shutter_status"
            ] in ["Open", "open"]:
                self.devices["sequencer"].time_roof_last_opened = time.time()
                # reset blocks so it can restart a calendar event
                self.devices["sequencer"].reset_completes()
                self.devices["sequencer"].last_roof_status = "Open"

            if self.devices["sequencer"].last_roof_status == "Open" and aws_enclosure_status[
                "shutter_status"
            ] in ["Closed", "closed"]:
                self.devices["sequencer"].last_roof_status = "Closed"
        except:
            plog("Glitch on getting shutter status in aws call.")

        try:
            status = {
                "shutter_status": aws_enclosure_status["shutter_status"],
                "enclosure_synchronized": aws_enclosure_status[
                    "enclosure_synchronized"
                ],  # self.following, 20220103_0135 WER
                "dome_azimuth": aws_enclosure_status["dome_azimuth"],
                "dome_slewing": aws_enclosure_status["dome_slewing"],
                "enclosure_mode": aws_enclosure_status["enclosure_mode"],
            }
        except:
            try:
                status = {
                    "shutter_status": aws_enclosure_status["shutter_status"]}
            except:
                plog("failed enclosure status!")
                status = {"shutter_status": "Unknown"}

        if self.assume_roof_open:
            status = {"shutter_status": "Sim. Open",
                      "enclosure_mode": "Simulated"}

        return status

    def get_weather_status_from_aws(self):
        """
        Requests the current enclosure status from the related WEMA.
        """

        uri_status = f"https://status.photonranch.org/status/{self.wema_name}/weather/"

        try:
            aws_weather_status = reqs.get(uri_status, timeout=20)
            aws_weather_status = aws_weather_status.json()

            aws_weather_status["site"] = self.name
        except Exception as e:
            plog("Failed to get aws weather status. Usually not fatal:  ", e)
            aws_weather_status = {}
            aws_weather_status["status"] = {}
            aws_weather_status["status"]["observing_conditions"] = {}
            aws_weather_status["status"]["observing_conditions"][
                "observing_conditions1"
            ] = None

        try:
            if (
                aws_weather_status["status"]["observing_conditions"][
                    "observing_conditions1"
                ]
                == None
            ):
                aws_weather_status["status"]["observing_conditions"][
                    "observing_conditions1"
                ] = {"wx_ok": "Unknown"}
            else:
                for weatherkey in aws_weather_status["status"]["observing_conditions"][
                    "observing_conditions1"
                ].keys():
                    aws_weather_status["status"]["observing_conditions"][
                        "observing_conditions1"
                    ][weatherkey] = aws_weather_status["status"][
                        "observing_conditions"
                    ][
                        "observing_conditions1"
                    ][
                        weatherkey
                    ][
                        "val"
                    ]
        except:
            plog("bit of a glitch in weather status")
            aws_weather_status = {}
            aws_weather_status["status"] = {}
            aws_weather_status["status"]["observing_conditions"] = {}
            aws_weather_status["status"]["observing_conditions"][
                "observing_conditions1"
            ] = {"wx_ok": "Unknown"}

        try:
            # To stop status's filling up the queue under poor connection conditions
            # There is a size limit to the queue
            if self.send_status_queue.qsize() < 7:
                self.send_status_queue.put(
                    (self.name, "weather", aws_weather_status["status"]), block=False
                )

        except Exception as e:
            plog("aws enclosure send failed ", e)

        aws_weather_status = aws_weather_status["status"]["observing_conditions"][
            "observing_conditions1"
        ]

        return aws_weather_status

    def enqueue_for_PTRarchive(self, priority, im_path, name):
        image = (im_path, name, time.time())
        self.ptrarchive_queue.put((priority, image), block=False)

    def enqueue_for_fastUI(self, im_path, filename, exposure_time, info_image_channel=None):
        """ Add an entry to the queue (self.fast_queue) that feeds the quick image upload thread.
        Entries are added before the file is created. The queue is monitored by the
        fast_to_ui method which is run as a separate thread. It checks for existence of
        the files in the queue, and once they exist, it uploads them and removes
        the corresponding entry from the queue.

        im_path:            string path to the directory where the file to upload is located
        filename:               filename of the file to upload
        exposure_time:      exposure duration in seconds (used to know if the exposure has completed yet)
        info_image-channel: int in [1,2,3] indicating to send to this info image channel
                            if None, send the image normally (not as an info image)
        """
        # Validate the info image channel: must be an int of 1, 2, or 3
        # If validation fails, try uploading as a regular image
        if info_image_channel is not None:
            try:
                info_image_channel = int(info_image_channel)
                if not info_image_channel in {1, 2, 3}:
                    raise Exception()
            except:
                plog(f"Error while attempting to upload {filename} as an info image")
                plog(f"enqueue_for_fatsUI recieved a misformed value for the info image channel")
                plog(f"Info image channel must be 1, 2, or 3. Recieved <{info_image_channel}> instead.")
                plog("Falling back to sending as a normal image.")
                info_image_channel = None

        payload = (
            im_path,
            filename,
            time.time(),
            exposure_time,
            info_image_channel
        )
        self.fast_queue.put(payload, block=False)

    def enqueue_for_mediumUI(self, priority, im_path, name):
        image = (im_path, name)
        self.mediumui_queue.put(
            (priority, (image[0], image[1], time.time())), block=False
        )

    def enqueue_for_calibrationUI(self, priority, im_path, name):
        image = (im_path, name)
        self.calibrationui_queue.put((priority, image), block=False)

    def to_slow_process(self, priority, to_slow):
        self.slow_camera_queue.put((priority, to_slow), block=False)

    def to_platesolve(self, to_platesolve):
        self.platesolve_queue.put(to_platesolve, block=False)

    def request_update_status(self, mount_only=False):
        not_slewing = False
        if self.mountless_operation:
            not_slewing = True
        elif not self.devices["mount"].return_slewing():
            not_slewing = True

        if not_slewing:  # Don't glog the update pipes while slewing.
            if not self.currently_updating_status and not mount_only:
                self.update_status_queue.put("normal", block=False)
            elif not self.currently_updating_status and mount_only:
                self.update_status_queue.put("mountonly", block=False)

    def request_scan_requests(self):
        self.scan_request_queue.put("normal", block=False)

    def request_update_calendar_blocks(self):
        if not self.currently_updating_calendar_blocks:
            self.calendar_block_queue.put("normal", block=False)

    def flush_command_queue(self):
        # So this command reads the commands waiting and just ... ignores them
        # essentially wiping the command queue coming from AWS.
        # This prevents commands from previous nights/runs suddenly running
        # when obs.py is booted (has happened a bit in the past!)
        # Also the sequencer can call this at the end of long sequences to make sure backed up
        # jobs don't send the scope go wildly.
        reqs.request(
            "POST",
            "https://jobs.photonranch.org/jobs/getnewjobs",
            data=json.dumps({"site": self.name}),
            timeout=30,
        ).json()

    def kill_and_reboot_theskyx(self, returnra, returndec): # Return to a given ra and dec or send -1,-1 to remain at park
        self.devices['mount'].mount_update_paused=True

        self.rebooting_theskyx=True

        if self.devices["main_cam"].theskyx:
            self.devices["main_cam"].updates_paused=True

        os.system("taskkill /IM TheSkyX.exe /F")
        os.system("taskkill /IM TheSky64.exe /F")
        time.sleep(5)
        retries=0

        while retries <5:
            try:
                # Recreate the mount
                rebooted_mount = Mount(self.devices['mount'].config['driver'],
                        self.name,
                        self.config,
                        self,
                        tel=True)
                self.all_devices['mount'][self.devices['mount'].name] = rebooted_mount
                self.devices['mount'] = rebooted_mount # update the 'mount' role to point to the new mount

                # If theskyx is controlling the camera and filter wheel, reconnect the camera and filter wheel
                for camera in self.all_devices['camera']:
                    if camera.theskyx:
                        new_camera = Camera(camera.driver, camera.name, self.config, self)
                        # Update references from the previous camera object to the rebooted one
                        self.all_devices['camera'][camera.name] = new_camera
                        if camera.role:
                            self.devices[camera.role] = new_camera

                        time.sleep(5)
                        new_camera.camera_update_reboot=True
                        time.sleep(5)
                        new_camera.theskyx_set_cooler_on=True
                        new_camera.theskyx_cooleron=True
                        new_camera.theskyx_set_setpoint_trigger=True
                        new_camera.theskyx_set_setpoint_value= self.devices["main_cam"].setpoint
                        new_camera.theskyx_temperature=self.devices["main_cam"].setpoint, 999.9, 999.9
                        new_camera.shutter_open=False
                        new_camera.theskyxIsExposureComplete=True
                        new_camera.theskyx=True
                        new_camera.updates_paused=False


                        # If the cam is connected to theskyx, reboot the filter wheel and focuser.
                        # Since there's currently no clear way to determine which filter wheel and focuser are connected to the camera,
                        # we'll just reboot all filter wheels and focusers.
                        for filter_wheel in self.all_devices['filter_wheel']:
                            if filter_wheel.config['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                                new_fw = FilterWheel('CCDSoft2XAdaptor.ccdsoft5Camera', filter_wheel.name, self.config, self)
                                if filter_wheel.role:
                                    self.devices[filter_wheel.role] = new_fw
                                time.sleep(5)
                        for focuser in self.all_devices['focuser']:
                            if focuser.config['driver'] == 'CCDSoft2XAdaptor.ccdsoft5Camera':
                                new_focuser = Focuser('CCDSoft2XAdaptor.ccdsoft5Camera', focuser.name, self.config, self)
                                if focuser.role:
                                    self.devices[focuser.role] = new_focuser
                                time.sleep(5)

                time.sleep(5)
                retries=6
            except:
                retries=retries+1
                time.sleep(60)
                if retries == 4:
                    plog(traceback.format_exc())

        self.devices['mount'].mount_update_reboot=True
        self.devices['mount'].wait_for_mount_update()
        self.devices['mount'].mount_update_paused=False

        self.rebooting_theskyx=False

        self.devices['mount'].park_command({}, {})
        if not (returnra == -1 or returndec == -1):
            self.devices['mount'].go_command(ra=returnra, dec=returndec)

        return



if __name__ == "__main__":
    o = Observatory(ptr_config.obs_id, ptr_config.site_config)
    o.run()  # This is meant to be a never ending loop.
