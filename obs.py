\
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
import math
import os
import queue
import shelve
import socket
import threading
import time
import sys
import shutil

import astroalign as aa
from astropy.io import fits
from astropy.nddata import block_reduce
from astropy.utils.data import check_download_cache
from dotenv import load_dotenv
import numpy as np
import redis  # Client, can work with Memurai

import requests

#import sep
from skimage.io import imsave
from skimage.transform import resize
import func_timeout
import traceback

from api_calls import API_calls
from auto_stretch.stretch import Stretch
import config
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

from PIL import Image, ImageEnhance

# The ingester should only be imported after environment variables are loaded in.
load_dotenv(".env")
from ocs_ingester.ingester import frame_exists, upload_file_and_ingest_to_archive


def send_status(obsy, column, status_to_send):
    """Sends an update to the status endpoint."""

    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}
    
    try:
        
        data = json.dumps(payload)
    except Exception as e:
        plog("Failed to send_status. usually not fatal:  ", e)
    
    try:
        requests.post(uri_status, data=data)
    except Exception as e:
        plog("Failed to send_status. usually not fatal:  ", e)


class Observatory:
    """Docstring here"""

    def __init__(self, name, config):
        # This is the ayneclass through which we can make authenticated api calls.
        self.api = API_calls()

        self.command_interval = 0 # seconds between polls for new commands
        self.status_interval = 0  # NOTE THESE IMPLEMENTED AS A DELTA NOT A RATE.

        self.name = name  # NB NB NB Names needs a once-over.
        self.site_name = name
        self.config = config
        self.site = config["site"]
   
        if self.config["wema_is_active"]:
            self.hostname = socket.gethostname()
            if self.hostname in self.config["wema_hostname"]:
                self.is_wema = True
                g_dev["wema_share_path"] = config["wema_write_share_path"]
                self.wema_path = g_dev["wema_share_path"]
            else:
                # This host is a client
                self.is_wema = False  # This is a client.
                self.site_path = config["client_path"]
                g_dev["site_path"] = self.site_path
                g_dev["wema_share_path"] = config[
                    "client_write_share_path"
                ]  # Just to be safe.
                self.wema_path = g_dev["wema_share_path"]
        else:
            self.is_wema = False  # This is a client.
            self.site_path = config["client_path"]
            g_dev["site_path"] = self.site_path
            g_dev["wema_share_path"] = self.site_path  # Just to be safe.
            self.wema_path = g_dev["wema_share_path"]

        if self.config["site_is_specific"]:
            self.site_is_specific = True
        else:
            self.site_is_specific = False



        self.last_request = None
        self.stopped = False
        self.status_count = 0
        self.stop_all_activity = False
        self.site_message = "-"
        self.all_device_types = config["device_types"]  # May not be needed
        self.device_types = config["device_types"]  # config['short_status_devices']
        self.wema_types = config["wema_types"]
        self.enc_types = None  # config['enc_types']
        self.short_status_devices = (
             config['short_status_devices']  # May not be needed for no wema obsy
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

        # Instantiate the helper class for astronomical events
        # Soon the primary event / time values can come from AWS.
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()

        self.astro_events.display_events()

        # Define a redis server if needed.
        redis_ip = config["redis_ip"]
        if redis_ip is not None:
            self.redis_server = redis.StrictRedis(
                host=redis_ip, port=6379, db=0, decode_responses=True
            )
            self.redis_wx_enabled = True
            g_dev["redis"] = self.redis_server  # I think IPC needs to be a class.
        else:
            self.redis_wx_enabled = False
            g_dev["redis"] = None  # a placeholder.

        

        # Use the configuration to instantiate objects for all devices.
        self.create_devices()
        self.loud_status = False
        g_dev["obs"] = self
        site_str = config["site"]
        g_dev["site"]: site_str
        self.g_dev = g_dev

        # Clear out smartstacks directory
        #print ("removing and reconstituting smartstacks directory")
        try:
            shutil.rmtree(g_dev["cam"].site_path + "smartstacks")
        except:
            print ("problems with removing the smartstacks directory... usually a file is open elsewhere")
        time.sleep(3)
        if not os.path.exists(g_dev["cam"].site_path + "smartstacks"):
            os.makedirs(g_dev["cam"].site_path + "smartstacks")

        # Check directory system has been constructed
        # for new sites or changed directories in configs.
        if not os.path.exists(g_dev["cam"].site_path + "ptr_night_shelf"):
            os.makedirs(g_dev["cam"].site_path + "ptr_night_shelf")
        if not os.path.exists(g_dev["cam"].site_path + "archive"):
            os.makedirs(g_dev["cam"].site_path + "archive")
        if not os.path.exists(g_dev["cam"].site_path + "tokens"):
            os.makedirs(g_dev["cam"].site_path + "tokens")
        if not os.path.exists(g_dev["cam"].site_path + "astropycache"):
            os.makedirs(g_dev["cam"].site_path + "astropycache")
        if not os.path.exists(g_dev["cam"].site_path + "smartstacks"):
            os.makedirs(g_dev["cam"].site_path + "smartstacks")
        if not os.path.exists(g_dev["cam"].site_path + "calibmasters"):
            os.makedirs(g_dev["cam"].site_path + "calibmasters")

        self.last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        self.images_since_last_solve = 10000

        self.time_last_status = time.time() - 3
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

        # Set up command_queue for incoming jobs
        self.cmd_queue = queue.Queue(
            maxsize=0
        )  # Note this is not a thread but a FIFO buffer
        self.stop_all_activity = False  # This is used to stop the camera or sequencer

        # =============================================================================
        # Here we set up the reduction Queue and Thread:
        # =============================================================================
        self.reduce_queue = queue.Queue(
            maxsize=0
        )  # Why do we want a maximum size and lose files?
        self.reduce_queue_thread = threading.Thread(target=self.reduce_image, args=())
        self.reduce_queue_thread.start()
        self.blocks = None
        self.projects = None
        self.events_new = None
        self.reset_last_reference()
        self.env_exists = os.path.exists(os.getcwd() + '\.env')  # Boolean, check if .env present


        # If mount is permissively set, reset mount reference
        # This is necessary for SRO and it seems for ECO
        # I actually think it may be necessary for all telescopes
        # Not all who wander are lost.... but those that point below altitude -10 probably are.
        #if self.config["mount"]["mount1"]["permissive_mount_reset"] == "yes":
        g_dev["mnt"].reset_mount_reference()

        # Keep track of how long it has been since the last activity
        self.time_since_last_slew_or_exposure = time.time()

        # Only poll the broad safety checks (altitude and inactivity) every 5 minutes
        self.time_since_safety_checks=time.time()

        # Need to set this for the night log
        #g_dev['foc'].set_focal_ref_reset_log(self.config["focuser"]["focuser1"]["reference"])
        # Send the config to AWS. TODO This has faulted.
        self.update_config()   #This is the never-ending control loop



    def set_last_reference(self, delta_ra, delta_dec, last_time):
        mnt_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + "last")
        mnt_shelf["ra_cal_offset"] = delta_ra
        mnt_shelf["dec_cal_offset"] = delta_dec
        mnt_shelf["time_offset"] = last_time
        mnt_shelf.close()
        return

    def get_last_reference(self):
        mnt_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + "last")
        delta_ra = mnt_shelf["ra_cal_offset"]
        delta_dec = mnt_shelf["dec_cal_offset"]
        last_time = mnt_shelf["time_offset"]
        mnt_shelf.close()
        return delta_ra, delta_dec, last_time

    def reset_last_reference(self):
        mnt_shelf = shelve.open(self.site_path + "ptr_night_shelf/" + "last")
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

        uri = f"{self.name}/config/"
        self.config["events"] = g_dev["events"]
        response = g_dev["obs"].api.authenticated_request("PUT", uri, self.config)
        if 'message' in response:
            if response['message'] == "Missing Authentication Token":
                print ("Missing Authentication Token. Config unable to be uploaded. Please fix this now.")
                sys.exit()
            else:
                print ("There may be a problem in the config upload? Here is the response.")
                print (response)
        elif 'ResponseMetadata' in response:
            #print(response['ResponseMetadata']['HTTPStatusCode'])
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                plog("Config uploaded successfully.")

            else:
                print ("Response to site config upload unclear. Here is the response")
                print (response)
        else:
            print ("Response to site config upload unclear. Here is the response")
            print (response)

    def scan_requests(self, cancel_check=False):
        """Gets commands from AWS, and post a STOP/Cancel flag.

        This function will be a Thread. We limit the
        polling to once every 2.5 - 3 seconds because AWS does not
        appear to respond any faster. When we poll, we parse
        the action keyword for 'stop' or 'cancel' and post the
        existence of the timestamp of that command to the
        respective device attribute <self>.cancel_at. Then we
        enqueue the incoming command as well.

        When a device is status scanned, if .cancel_at is not
        None, the device takes appropriate action and sets
        cancel_at back to None.

        NB at this time we are preserving one command queue
        for all devices at a site. This may need to change when we
        have parallel mountings or independently controlled cameras.
        """

        # This stopping mechanism allows for threads to close cleanly.

        while not self.stopped:    #This variable is not used.

            if  True:  #not g_dev["seq"].sequencer_hold:  THis causes an infinte loope witht he above while
                url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
                body = {"site": self.name}
                cmd = {}
                # Get a list of new jobs to complete (this request
                # marks the commands as "RECEIVED")
                unread_commands = requests.request(
                    "POST", url_job, data=json.dumps(body)
                ).json()
                # Make sure the list is sorted in the order the jobs were issued
                # Note: the ulid for a job is a unique lexicographically-sortable id.
                if len(unread_commands) > 0:
                    unread_commands.sort(key=lambda x: x["timestamp_ms"])
                    # Process each job one at a time
                    plog(
                        "# of incomming commands:  ",
                        len(unread_commands),
                        unread_commands,
                    )

                    for cmd in unread_commands:
                        if cmd["action"] in ["cancel_all_commands", "stop"]:
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
                            # only a Cancel/Stop action is sent.  But we need to same any subsequent commands.
                            try:
                                if g_dev["cam"].exposure_busy:
                                    
                                    g_dev["cam"]._stop_expose()
                                    # Should we try to flush the image array?
                                    g_dev["obs"].stop_all_activity = True
                                    g_dev["cam"].exposure_busy = False
                                else:
                                    plog("Camera is not busy.")
                            except:
                                plog("Camera stop faulted.")
                            while self.cmd_queue.qsize() > 0:
                                plog("Deleting Job:  ", self.cmd_queue.get())
                            
                            #return  # Note we basically do nothing and let camera, etc settle down.
                        else:
                            self.cmd_queue.put(cmd)  # SAVE THE COMMAND FOR LATER
                            g_dev["obs"].stop_all_activity = False
                            self.send_to_user(
                                "Queueing up a new command... Hint:  " + cmd["action"]
                            )

                        if cancel_check:
                            result={'stopped': True}
                            return  # Note we do not process any commands.

                # NEED TO WAIT UNTIL CURRENT COMMAND IS FINISHED UNTIL MOVING ONTO THE NEXT ONE!
                # THAT IS WHAT CAUSES THE "CAMERA BUSY" ISSUE. We don't need to wait for the
                # rotator as the exposure routine in camera.py already waits for that.                
                #if (not g_dev["cam"].exposure_busy) and (not g_dev['mnt'].mount.Slewing):
                if (not g_dev["cam"].exposure_busy):
                    while self.cmd_queue.qsize() > 0:
                        self.send_to_user(
                            "Number of queued commands:  " + str(self.cmd_queue.qsize())
                        )
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
                            
                 
                # TO KEEP THE REAL-TIME USE A BIT SNAPPIER, POLL FOR NEW PROJECTS ON A MUCH SLOWER TIMESCALE
                # TO REMOVE UNNECESSARY CALLS FOR PROJECTS.
                if time.time() - self.project_call_timer > 30: 
                    self.project_call_timer = time.time()
                    plog(".")  # We print this to stay informed of process on the console.
                    url_blk = "https://calendar.photonranch.org/dev/siteevents"
                    # UTC VERSION
                    start_aperture = str(g_dev['events']['Eve Sky Flats']).split()
                    close_aperture = str(g_dev['events']['End Morn Sky Flats']).split()
                    
    
                    # Reformat ephem.Date into format required by the UI
                    startapyear=start_aperture[0].split('/')[0]
                    startapmonth=start_aperture[0].split('/')[1]
                    startapday=start_aperture[0].split('/')[2]
                    closeapyear=close_aperture[0].split('/')[0]
                    closeapmonth=close_aperture[0].split('/')[1]
                    closeapday=close_aperture[0].split('/')[2]                
                    
                    if len(str(startapmonth)) == 1:
                        startapmonth='0' + startapmonth
                    if len(str(startapday)) == 1:
                        startapday='0' + str(startapday)
                    if len(str(closeapmonth)) == 1:
                        closeapmonth='0' + closeapmonth
                    if len(str(closeapday)) == 1:
                        closeapday='0' + str(closeapday)
    
                    start_aperture_date = startapyear + '-' + startapmonth + '-' + startapday
                    close_aperture_date = closeapyear + '-' + closeapmonth + '-' + closeapday
    
                    start_aperture[0] =start_aperture_date 
                    close_aperture[0] =close_aperture_date 
    
    
                    
                    body = json.dumps(
                        {
                            "site": self.config["site"],
                            "start": start_aperture[0].replace('/','-') +'T' + start_aperture[1] +'Z',
                            "end": close_aperture[0].replace('/','-') +'T' + close_aperture[1] +'Z',
                            "full_project_details:": False,
                        }
                    )
    
                    if (
                        True
                    ):  # self.blocks is None: # This currently prevents pick up of calendar changes.
                        blocks = requests.post(url_blk, body).json()
                        if len(blocks) > 0:
                            self.blocks = blocks
    
                    url_proj = "https://projects.photonranch.org/dev/get-all-projects"
                    if True:
                        all_projects = requests.post(url_proj).json()
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
                            + self.site_name.upper()
                        )
                        self.events_new = requests.get(url).json()
                return  # This creates an infinite loop

            else:
                
                continue

    def update_status(self, bpt=False, cancel_check=False):
        """Collects status from all devices and sends an update to AWS.

        Each device class is responsible for implementing the method
        `get_status`, which returns a dictionary.
        """
        
        
        
        
        loud = False
        if bpt:
            print('UpdateStatus bpt was invoked.')
            #breakpoint()
        
        
        
        # Wait a bit between status updates
        while time.time() < self.time_last_status + self.status_interval:
            return  # Note we are just not sending status, too soon.

        #print ("Time between status updates: " + str(time.time() - self.time_last_status))

        t1 = time.time()
        status = {}

        # Loop through all types of devices.
        # For each type, we get and save the status of each device.

        if not self.config["wema_is_active"]:
            #device_list = self.short_status_devices()
            device_list = self.device_types
            remove_enc = False
        if self.config["wema_is_active"]:
            device_list = self.short_status_devices  #  used when wema is sending ocn and enc status via a different stream.
            remove_enc = False   

        else:
            device_list = self.device_types  #  used when one computer is doing everything for a site.
            remove_enc = True
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
                if (
                    "enclosure" in device_name
                    and device_name in self.config["wema_types"]
                    and (self.is_wema or self.site_is_specific)
                ):
                    if (
                        datetime.datetime.now() - self.enclosure_status_timer
                    ) < datetime.timedelta(minutes=self.enclosure_check_period):
                        result = None
                        send_enc = False
                    else:
                        plog("Running enclosure status check")
                        self.enclosure_status_timer = datetime.datetime.now()
                        send_enc = True

                        result = device.get_status()

                elif (
                    "observing_conditions" in device_name
                    and device_name in self.config["wema_types"]
                    and (self.is_wema or self.site_is_specific)
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
                        if self.site_is_specific:
                            remove_enc = False

                else:
                    result = device.get_status()
                if result is not None:
                    status[dev_type][device_name] = result

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
        #print ("Status update length: " + str(time.time() - beginning_update_status))
        loud = False
        # Consider inhibiting unless status rate is low
        obsy = self.name
        

        if status is not None:
            lane = "device"
            #send_status(obsy, lane, status)
            self.send_status_queue.put((obsy, lane, status), block=False)
        if ocn_status is not None:
            lane = "weather"
            #send_status(obsy, lane, ocn_status)  # NB Do not remove this send for SAF!
            if send_ocn == True:
                self.send_status_queue.put((obsy, lane, ocn_status), block=False)
        if enc_status is not None:
            lane = "enclosure"
            #send_status(obsy, lane, enc_status)
            if send_enc == True:
                self.send_status_queue.put((obsy, lane, enc_status), block=False)
        #if loud:
        #    plog("\n\nStatus Sent:  \n", status)
        #else:
            
        # NB should qualify acceptance and type '.' at that point.
        self.time_last_status = time.time()
        self.status_count += 1
    
        
        

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
        if time.time() - self.time_since_safety_checks > 300:
            self.time_since_safety_checks=time.time()
            
            # Check the mount is still connected
            g_dev['mnt'].check_connect()
            
            # Check that the mount hasn't tracked too low or an odd slew hasn't sent it pointing to the ground.
            try:
                mount_altitude=g_dev['mnt'].mount.Altitude
                lowest_acceptable_altitude= self.config['mount']['mount1']['lowest_acceptable_altitude'] 
                if mount_altitude < lowest_acceptable_altitude:
                    print ("Altitude too low! " + str(mount_altitude) + ". Parking scope for safety!")
                    if not g_dev['mnt'].mount.AtPark:  
                        g_dev['mnt'].home_command()
                        g_dev['mnt'].park_command()  
                        # Reset mount reference because thats how it probably got pointing at the dirt in the first place!
                        if self.config["mount"]["mount1"]["permissive_mount_reset"] == "yes":
                            g_dev["mnt"].reset_mount_reference()
            except Exception as e:
                print (traceback.format_exc())
                print (e)
                breakpoint()
                if 'GetAltAz' in str(e) and 'ASCOM.SoftwareBisque.Telescope' in str(e):
                    print ("The SkyX Altitude detection had an error.")
                    print ("Usually this is because of a broken connection.")
                    print ("Waiting 60 seconds then reconnecting")
                    
                    time.sleep(60)
                    
                    self.mount.Connected = True
                    #g_dev['mnt'].home_command()
                
    
            # If no activity for an hour, park the scope               
            if time.time() - self.time_since_last_slew_or_exposure > self.config['mount']['mount1']\
                                                                                ['time_inactive_until_park']:
                if not g_dev['mnt'].mount.AtPark:  
                    print ("Parking scope due to inactivity")
                    g_dev['mnt'].home_command()
                    g_dev['mnt'].park_command()
                    self.time_since_last_slew_or_exposure = time.time()
                    
            # Check that cooler is alive
            #print ("Cooler check")
            probe = g_dev['cam']._cooler_on()
            if probe == True:
                print ("Cooler is still on at " + str(g_dev['cam']._temperature()))            
            
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
                    #time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk

                #  NB NB NB This looks like a redundant send
                tt = time.time()
                #aws_resp = g_dev["obs"].api.authenticated_request(
                #    "POST", "/upload/", {"object_name": filename})
                #plog('The setup phase took:  ', round(time.time() - tt, 1), ' sec.')


                # Only ingest new large fits.fz files to the PTR archive.
                #print (self.env_exists)
                if filename.endswith("-EX00.fits.fz"):
                    with open(filepath, "rb") as fileobj:
                        #print (frame_exists(fileobj))
                        tempPTR=0
                        if self.env_exists == True and (not frame_exists(fileobj)):
                            #print ("attempting ingester")
                            try:
                                #tt = time.time()
                                print ("attempting ingest to aws@  ", tt)
                                upload_file_and_ingest_to_archive(fileobj)
                                #print ("did ingester")
                                plog(f"--> To PTR ARCHIVE --> {str(filepath)}")
                                plog('*.fz ingestion took:  ', round(time.time() - tt, 1), ' sec.')
                                self.aws_queue.task_done()
                                #os.remove(filepath)
                                
                                tempPTR=1
                            except Exception as e:
                                print ("couldn't send to PTR archive for some reason")
                                print (e)
                                print ((traceback.format_exc()))
                                tempPTR=0
                        # If ingester fails, send to default S3 bucket.
                        if tempPTR ==0:
                            files = {"file": (filepath, fileobj)}
                            try:
                                aws_resp = g_dev["obs"].api.authenticated_request(
                                    "POST", "/upload/", {"object_name": filename})
                                #requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                #break

                                #tt = time.time()
                                print ("attempting aws@  ", tt)
                                req_resp = requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                print ("did aws", req_resp)
                                plog(f"--> To AWS --> {str(filepath)}")
                                plog('*.fz transfer took:  ', round(time.time() - tt, 1), ' sec.')
                                self.aws_queue.task_done()
                                #os.remove(filepath)
                                
                                #break

                            except:
                                print ("Connection glitch for the request post, waiting a moment and trying again")
                                time.sleep(5)
                            
                # Send all other files to S3.
                else:
                    with open(filepath, "rb") as fileobj:
                        files = {"file": (filepath, fileobj)}
                        try:
                            aws_resp = g_dev["obs"].api.authenticated_request(
                                "POST", "/upload/", {"object_name": filename})
                            requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                            plog(f"--> To AWS --> {str(filepath)}")
                            self.aws_queue.task_done()
                            #os.remove(filepath)
                            
                            #break
                        except:
                            print ("Connection glitch for the request post, waiting a moment and trying again")
                            time.sleep(5)

                try:   
                    os.remove(filepath)
                except:
                    pass
                
                if (
                    filename[-3:] == "jpg"
                    or filename[-3:] == "txt"
                    or ".fits.fz" in filename
                    or ".token" in filename
                ):
                    try:
                        os.remove(filepath)
                    except:
                        pass


                one_at_a_time = 0
                #3time.sleep(0.1)
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
                pre_upload=time.time()
                received_status = self.send_status_queue.get(block=False)
                #print ("****************")
                #print (received_status)                
                send_status(received_status[0], received_status[1], received_status[2])
                self.send_status_queue.task_done()
                upload_time=time.time() - pre_upload                
                self.status_interval = 2 * upload_time
                #print ("New status interval: " + str(self.status_interval))
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
                #print (slow_process[0])
                #print (slow_process[1][0])
                slow_process=slow_process[1]
                #print ("********** slow queue : " + str(slow_process[0]) )
                if slow_process[0] == 'focus':
                    hdufocus=fits.PrimaryHDU()
                    hdufocus.data=slow_process[2]                            
                    hdufocus.header=slow_process[3]
                    hdufocus.header["NAXIS1"] = hdufocus.data.shape[0]
                    hdufocus.header["NAXIS2"] = hdufocus.data.shape[1]
                    hdufocus.writeto(slow_process[1], overwrite=True, output_verify='silentfix')

                    try:
                        hdufocus.close()
                    except:
                        pass                    
                    del hdufocus
                
                if slow_process[0] == 'raw' or slow_process[0] =='raw_alt_path' or slow_process[0] == 'reduced_alt_path':
                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:
                            hdu=fits.PrimaryHDU()
                            hdu.data=slow_process[2]                            
                            hdu.header=slow_process[3]
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
                        np.array(slow_process[2], dtype=np.float32), slow_process[3]
                    )
                    hdufz.verify("fix")
                    hdufz.header[
                        "BZERO"
                    ] = 0  # Make sure there is no integer scaling left over
                    hdufz.header[
                        "BSCALE"
                    ] = 1  # Make sure there is no integer scaling left over

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
                            26000000, '',slow_process[1]
                        )
                        g_dev["obs"].send_to_user(
                            "An image has been readout from the camera and queued for transfer to the cloud.",
                            p_level="INFO",
                        )
                    #print ("fz done.")
                
                if slow_process[0] == 'reduced':
                    saver = 0
                    saverretries = 0
                    while saver == 0 and saverretries < 10:
                        try:
                            hdureduced=fits.PrimaryHDU()
                            hdureduced.data=slow_process[2]                            
                            hdureduced.header=slow_process[3]
                            hdureduced.header["NAXIS1"] = hdureduced.data.shape[0]
                            hdureduced.header["NAXIS2"] = hdureduced.data.shape[1]
                            hdureduced.data=hdureduced.data.astype("float32")
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
                #breakpoint()
                



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
                    #time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = g_dev["obs"].api.authenticated_request(
                    "POST", "/upload/", {"object_name": filename})
                # Only ingest new large fits.fz files to the PTR archive.
                
                # Send all other files to S3.
                
                with open(filepath, "rb") as fileobj:
                    files = {"file": (filepath, fileobj)}
                    while True:
                        try:
                            requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                            break
                        except:
                            print ("Connection glitch for the request post, waiting a moment and trying again")
                            time.sleep(5)
                    plog(f"--> To AWS --> {str(filepath)}")

                # if (
                #     filename[-3:] == "jpg"
                #     or filename[-3:] == "txt"
                #     or ".fits.fz" in filename
                #     or ".token" in filename
                # ):
                #     os.remove(filepath)

                self.fast_queue.task_done()
                one_at_a_time = 0
                #time.sleep(0.1)
            else:
                time.sleep(0.05)

    def send_to_user(self, p_log, p_level="INFO"):
        url_log = "https://logs.photonranch.org/logs/newlog"
        body = json.dumps(
            {
                "site": self.config["site"],
                "log_message": str(p_log),
                "log_level": str(p_level),
                "timestamp": time.time(),
            }
        )

        try:
            requests.post(url_log, body)
        #if not response.ok:
        except:
            print("Log did not send, usually not fatal.")


    # Note this is another thread!
    def reduce_image(self):

        while True:

            if not self.reduce_queue.empty():
                (
                    paths,
                    pixscale,
                    smartstackid,
                    sskcounter,
                    Nsmartstack,
                    sources,
                ) = self.reduce_queue.get(block=False)

                if paths is None:
                    #time.sleep(0.5)
                    continue

                                  

                # SmartStack Section
                if smartstackid != "no" :
                    
                    if not paths["frame_type"] in [
                        "bias",
                        "dark",
                        "flat",
                        "solar",
                        "lunar",
                        "skyflat",
                        "screen",
                        "spectrum",
                        "auto_focus",
                    ]:
                        img = fits.open(
                            paths["red_path"] + paths["red_name01"],
                            ignore_missing_end=True,
                        )
                        imgdata=img[0].data.copy()
                        # Pick up some header items for smartstacking later
                        ssfilter = str(img[0].header["FILTER"])
                        ssobject = str(img[0].header["OBJECT"])
                        ssexptime = str(img[0].header["EXPTIME"])
                        ssframenumber = str(img[0].header["FRAMENUM"])
                        img.close()
                        del img
                        sstackimghold=np.array(imgdata)  

                    print ("Number of sources just prior to smartstacks: " + str(len(sources)))
                    if len(sources) < 5:
                        print ("skipping stacking as there are not enough sources " + str(len(sources)) +" in this image")

                    # No need to open the same image twice, just using the same one as SEP.
                    img = sstackimghold.copy()
                    del sstackimghold
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
                        if sys.byteorder=='little':
                            img=img.newbyteorder('little').byteswap()
                        else:
                            img=img.newbyteorder('big').byteswap()
    
    
                        # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
                        reprojection_failed=False
                        if not os.path.exists(
                            g_dev["cam"].site_path + "smartstacks/" + smartStackFilename
                        ):
                            if len(sources) >= 5:
                                # Store original image
                                plog("Storing First smartstack image")
                                np.save(
                                    g_dev["cam"].site_path
                                    + "smartstacks/"
                                    + smartStackFilename,
                                    img,
                                )
    
                            else:
                                print ("Not storing first smartstack image as not enough sources")
                                reprojection_failed=True
                            storedsStack = img
                        else:
                            # Collect stored SmartStack
                            storedsStack = np.load(
                                g_dev["cam"].site_path + "smartstacks/" + smartStackFilename
                            )
                            #print (storedsStack.dtype.byteorder)
                            # Prep new image
                            plog("Pasting Next smartstack image")
                            # img=np.nan_to_num(img)
                            # backgroundLevel =(np.nanmedian(sep.Background(img.byteswap().newbyteorder())))
                            # print (" Background Level : " + str(backgroundLevel))
                            # img= img - backgroundLevel
                            # Reproject new image onto footprint of old image.
                            #plog(datetime.datetime.now())
                            if len(sources) > 5:
                                try:
                                    reprojectedimage, _ = func_timeout.func_timeout (60, aa.register, args=(img, storedsStack),\
                                                                                     kwargs={"detection_sigma":3, "min_area":9})
                                    # scalingFactor= np.nanmedian(reprojectedimage / storedsStack)
                                    # print (" Scaling Factor : " +str(scalingFactor))
                                    # reprojectedimage=(scalingFactor) * reprojectedimage # Insert a scaling factor
                                    storedsStack = np.array((reprojectedimage + storedsStack))
                                    # Save new stack to disk
                                    np.save(
                                        g_dev["cam"].site_path
                                        + "smartstacks/"
                                        + smartStackFilename,
                                        storedsStack,
                                    )
                                    reprojection_failed=False
                                except func_timeout.FunctionTimedOut:
                                    print ("astroalign timed out")
                                    reprojection_failed=True
                                except aa.MaxIterError:
                                    print ("astroalign could not find a solution in this image")
                                    reprojection_failed=True
                                except Exception:
                                    print ("astroalign failed")
                                    print (traceback.format_exc())
                                    reprojection_failed=True
                            else:
                                reprojection_failed=True
    
    
                        if reprojection_failed == True: # If we couldn't make a stack send a jpeg of the original image.
                            storedsStack=img
                        
                        
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
                        stretched_data_uint8 = Image.fromarray(stretched_data_uint8)
        
                        if iy == ix:

                            stretched_data_uint8 = stretched_data_uint8.resize(
                                         (900, 900)
                                    )
                        else:

                            stretched_data_uint8 = stretched_data_uint8.resize(
                                        
                                        (int(900 * iy / ix), 900)
                                        
                                    ) 
           
                        stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
                        stretched_data_uint8.save(
                            paths["im_path"] + paths["jpeg_name10"]
                        )
                            

                        
                    # This is where the OSC smartstack stuff is. 
                    else:   
                        
                        # img is the image coming in
                        
                        
                                                
    
                        if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                            
                            if self.config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':                           
                                
                                # Checkerboard collapse for other colours for temporary jpeg                            
                                # Create indexes for B, G, G, R images                            
                                xshape=img.shape[0]
                                yshape=img.shape[1]
    
                                # B pixels
                                list_0_1 = np.array([ [0,0], [0,1] ])
                                checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                #checkerboard=np.array(checkerboard)
                                newhdublue=(block_reduce(img * checkerboard ,2))
                                
                                # R Pixels
                                list_0_1 = np.array([ [1,0], [0,0] ])
                                checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                #checkerboard=np.array(checkerboard)
                                newhdured=(block_reduce(img * checkerboard ,2))
                                
                                # G top right Pixels
                                list_0_1 = np.array([ [0,1], [0,0] ])
                                checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                #checkerboard=np.array(checkerboard)
                                newhdugreen=(block_reduce(img * checkerboard ,2))
                                
                                # G bottom left Pixels
                                #list_0_1 = np.array([ [0,0], [1,0] ])
                                #checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                #checkerboard=np.array(checkerboard)
                                #GBLonly=(block_reduce(storedsStack * checkerboard ,2))                                
                                
                                # Sum two Gs together and half them to be vaguely on the same scale
                                #hdugreen = np.array(GTRonly + GBLonly) / 2
                                #del GTRonly
                                #del GBLonly
                                del checkerboard
    
                            else:
                                print ("this bayer grid not implemented yet")
                            
                            
                            # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
                            reprojection_failed=False
                            for colstack in ['blue','green','red']:
                                if not os.path.exists(
                                    g_dev["cam"].site_path + "smartstacks/" + smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                                ):
                                    if len(sources) >= 5:
                                        # Store original image
                                        plog("Storing First smartstack image")
                                        if colstack == 'blue':
                                            np.save(
                                                g_dev["cam"].site_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid, smartstackid + str(colstack)),
                                                newhdublue,
                                            )
                                        if colstack == 'green':
                                            np.save(
                                                g_dev["cam"].site_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid, smartstackid + str(colstack)),
                                                newhdugreen,
                                            )
                                        if colstack == 'red':
                                            np.save(
                                                g_dev["cam"].site_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid, smartstackid + str(colstack)),
                                                newhdured,
                                            )
            
                                    else:
                                        print ("Not storing first smartstack image as not enough sources")
                                        reprojection_failed=True
                                    # if colstack == 'blue':
                                    #     bluestoredsStack = newhdublue
                                    # if colstack == 'green':
                                    #     greenstoredsStack = newhdugreen
                                    # if colstack == 'red':
                                    #     redstoredsStack = newhdured
                                else:
                                    # Collect stored SmartStack
                                    storedsStack = np.load(
                                        g_dev["cam"].site_path + "smartstacks/" + smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                                    )
                                    #print (storedsStack.dtype.byteorder)
                                    # Prep new image
                                    plog("Pasting Next smartstack image")
                                    # img=np.nan_to_num(img)
                                    # backgroundLevel =(np.nanmedian(sep.Background(img.byteswap().newbyteorder())))
                                    # print (" Background Level : " + str(backgroundLevel))
                                    # img= img - backgroundLevel
                                    # Reproject new image onto footprint of old image.
                                    #plog(datetime.datetime.now())
                                    if len(sources) > 5:
                                        try:
                                            if colstack == 'red':
                                                reprojectedimage, _ = func_timeout.func_timeout (60, aa.register, args=(newhdured, storedsStack),\
                                                                                                 kwargs={"detection_sigma":3, "min_area":9})
                                                
                                            if colstack == 'blue':
                                                reprojectedimage, _ = func_timeout.func_timeout (60, aa.register, args=(newhdublue, storedsStack),\
                                                                                                 kwargs={"detection_sigma":3, "min_area":9})
                                            if colstack == 'green':
                                                reprojectedimage, _ = func_timeout.func_timeout (60, aa.register, args=(newhdugreen, storedsStack),\
                                                                                                 kwargs={"detection_sigma":3, "min_area":9})
                                                # scalingFactor= np.nanmedian(reprojectedimage / storedsStack)
                                            # print (" Scaling Factor : " +str(scalingFactor))
                                            # reprojectedimage=(scalingFactor) * reprojectedimage # Insert a scaling factor
                                            storedsStack = np.array((reprojectedimage + storedsStack))
                                            # Save new stack to disk
                                            np.save(
                                                g_dev["cam"].site_path
                                                + "smartstacks/"
                                                + smartStackFilename.replace(smartstackid, smartstackid + str(colstack)),
                                                storedsStack,
                                            )
                                            if colstack == 'green':
                                                newhdugreen=np.array(storedsStack)
                                            if colstack == 'red':
                                                newhdured=np.array(storedsStack)
                                            if colstack == 'blue':
                                                newhdublue=np.array(storedsStack)
                                            del storedsStack
                                            reprojection_failed=False
                                        except func_timeout.FunctionTimedOut:
                                            print ("astroalign timed out")
                                            reprojection_failed=True
                                        except aa.MaxIterError:
                                            print ("astroalign could not find a solution in this image")
                                            reprojection_failed=True
                                        except Exception:
                                            print ("astroalign failed")
                                            print (traceback.format_exc())
                                            reprojection_failed=True
                                    else:
                                        reprojection_failed=True
                            
                            # NOW THAT WE HAVE THE INDIVIDUAL IMAGES THEN PUT THEM TOGETHER
                            xshape=newhdugreen.shape[0]
                            yshape=newhdugreen.shape[1]                          
                            
                            newhdublue[newhdublue < 1] = 1
                            newhdugreen[newhdugreen < 1] = 1
                            newhdured[newhdured < 1] = 1
                                                        
                            blue_stretched_data_float = Stretch().stretch(newhdublue)
                            del newhdublue
                            green_stretched_data_float = Stretch().stretch(newhdugreen)
                            red_stretched_data_float = Stretch().stretch(newhdured)
                            del newhdured                                
                            del newhdugreen
                            rgbArray=np.zeros((xshape,yshape,3), 'uint8')
                            rgbArray[..., 0] = red_stretched_data_float*256
                            rgbArray[..., 1] = green_stretched_data_float*256
                            rgbArray[..., 2] = blue_stretched_data_float*256
    
                            del red_stretched_data_float
                            del blue_stretched_data_float
                            del green_stretched_data_float
                            colour_img = Image.fromarray(rgbArray, mode="RGB")
                            
                           # adjust brightness
                            brightness=ImageEnhance.Brightness(colour_img)
                            brightness_image=brightness.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'])
                            del colour_img
                            del brightness
                            
                            # adjust contrast
                            contrast=ImageEnhance.Contrast(brightness_image)
                            contrast_image=contrast.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance'])
                            del brightness_image
                            del contrast
                            
                            # adjust colour
                            colouradj=ImageEnhance.Color(contrast_image)
                            colour_image=colouradj.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance'])
                            del contrast_image
                            del colouradj
                            
                            # adjust saturation
                            satur=ImageEnhance.Color(colour_image)
                            satur_image=satur.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_saturation_enhance'])
                            del colour_image
                            del satur
                            
                            # adjust sharpness
                            sharpness=ImageEnhance.Sharpness(satur_image)
                            final_image=sharpness.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance'])
                            del satur_image
                            del sharpness
                            
                            # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                            if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                                final_image=final_image.transpose(Image.TRANSPOSE)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                                final_image=final_image.transpose(Image.FLIP_LEFT_RIGHT)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                                final_image=final_image.transpose(Image.FLIP_TOP_BOTTOM)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                                final_image=final_image.transpose(Image.ROTATE_180)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                                final_image=final_image.transpose(Image.ROTATE_90)
                            if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                                final_image=final_image.transpose(Image.ROTATE_270)
                            
                            # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                            # to maintain the orientation. whether it is 1 or 0 that is flipped
                            # is sorta arbitrary... you'd use the site-config settings above to 
                            # set it appropriately and leave this alone.
                            if g_dev['mnt'].pier_side == 1:
                                final_image=final_image.transpose(Image.ROTATE_180)
                            
                            
                            ## Resizing the array to an appropriate shape for the jpg and the small fits
                            iy, ix = final_image.size
                            if iy == ix:
                                #final_image.resize((1280, 1280))
                                final_image.resize((900, 900))
                            else:
                                #final_image.resize((int(1536 * iy / ix), 1536))
                                final_image.resize((int(900 * iy / ix), 900))
                            
                            
                                
                            final_image.save(
                                paths["im_path"] + paths["jpeg_name10"]
                            )
                            del final_image
                                    
                
                           



                    self.fast_queue.put((15, (paths["im_path"], paths["jpeg_name10"])), block=False)

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
                        img.close()
                        # Just in case
                    except:
                        pass
                    del img

                # WE CANNOT SOLVE FOR POINTING IN THE REDUCE THREAD! 
                # POINTING SOLUTIONS HAVE TO HAPPEN AND COMPLETE IN BETWEEN EXPOSURES AND SLEWS

                #time.sleep(0.5)
                self.img = None  # Clean up all big objects.
                self.reduce_queue.task_done()
            else:
                time.sleep(0.1)


if __name__ == "__main__":

    o = Observatory(config.site_name, config.site_config)
    o.run()   #This is meant to be a never ending loop.