""""
IMPORTANT TODOs:

WER 20211211

Simplify. No site specific if statements in main code if possible.
Sort out when rotator is not installed and focus temp when no probe
is in the Gemini.

Abstract away Redis, Memurai, and local shares for IPC.
"""

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
from dotenv import load_dotenv
import numpy as np
import redis  # Client, can work with Memurai

import requests
# from requests.adapters import HTTPAdapter
# from requests.packages.urllib3.util.retry import Retry
# retry_strategy = Retry(
#     total=10, backoff_factor=0.1
# )
# adapter = HTTPAdapter(max_retries=retry_strategy)
# requests = requests.Session()



import sep
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

# The ingester should only be imported after environment variables are loaded in.
load_dotenv(".env")
from ocs_ingester.ingester import frame_exists, upload_file_and_ingest_to_archive


def send_status(obsy, column, status_to_send):
    """Sends an update to the status endpoint."""

    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}
    data = json.dumps(payload)
    try:
        requests.post(uri_status, data=data)
    except Exception as e:
        plog("Failed to send_status. usually not fatal:  ", e)


class Observatory:
    """Docstring here"""

    def __init__(self, name, config):
        # This is the ayneclass through which we can make authenticated api calls.
        self.api = API_calls()

        self.command_interval = 0  # seconds between polls for new commands
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
            None  # config['short_status_devices']  # May not be needed for no wema obsy
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

        # Send the config to AWS. TODO This has faulted.
        self.update_config()

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
        time.sleep(20)
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


        # Set up command_queue for incoming jobs
        self.cmd_queue = queue.Queue(
            maxsize=30
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

        # Need to set this for the night log
        #g_dev['foc'].set_focal_ref_reset_log(self.config["focuser"]["focuser1"]["reference"])


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

        uri = f"https://api.photonranch.org/dev/{self.name}/config/"
        self.config["events"] = g_dev["events"]
        self.api.authenticated_request("PUT", uri, self.config)
        plog("Config uploaded successfully.")

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
        while not self.stopped:

            if not g_dev["seq"].sequencer_hold:
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
                            self.send_to_user(
                                "Cancel/Stop received. Exposure stopped, will begin readout then discard image."
                            )
                            self.send_to_user(
                                "Pending reductions and transfers to the PTR Archive are not affected."
                            )
                            # Empty the queue
                            try:
                                if g_dev["cam"].exposure_busy:
                                    g_dev["cam"]._stop_expose()
                                    g_dev["obs"].stop_all_activity = True
                                else:
                                    plog("Camera is not busy.")
                            except:
                                plog("Camera stop faulted.")
                            while self.cmd_queue.qsize() > 0:
                                plog("Deleting Job:  ", self.cmd_queue.get())
                            return  # Note we basically do nothing and let camera, etc settle down.
                        else:
                            self.cmd_queue.put(cmd)  # SAVE THE COMMAND FOR LATER
                            self.send_to_user(
                                "Queueing up a new command... Hint:  " + cmd["action"]
                            )

                    if cancel_check:
                        return  # Note we do not process any commands.

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
                        plog("Exception in obs.scan_requests:  ", e)
                url_blk = "https://calendar.photonranch.org/dev/siteevents"
                body = json.dumps(
                    {
                        "site": self.config["site"],
                        "start": g_dev["d-a-y"] + "T00:00:00Z",
                        "end": g_dev["next_day"] + "T23:59:59Z",
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
                # What we really want here is looking for a Cancel/Stop.
                continue

    def update_status(self):
        """Collects status from all devices and sends an update to AWS.

        Each device class is responsible for implementing the method
        `get_status`, which returns a dictionary.
        """

        # This stopping mechanism allows for threads to close cleanly.
        loud = False

        # Wait a bit between status updates
        while time.time() < self.time_last_status + self.status_interval:
            return  # Note we are just not sending status, too soon.

        t1 = time.time()
        status = {}
        # Loop through all types of devices.
        # For each type, we get and save the status of each device.

        if not self.config["wema_is_active"]:
            device_list = self.device_types
            remove_enc = False
        else:
            device_list = self.device_types
            remove_enc = True
        for dev_type in device_list:
            # The status that we will send is grouped into lists of
            # devices by dev_type.
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
                    else:
                        plog("Running enclosure status check")
                        self.enclosure_status_timer = datetime.datetime.now()
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
                    else:
                        plog("Running weather status check.")
                        self.observing_status_timer = datetime.datetime.now()
                        result = device.get_status(g_dev=g_dev)
                        if self.site_is_specific:
                            remove_enc = False

                else:
                    result = device.get_status()
                if result is not None:
                    status[dev_type][device_name] = result

        status["timestamp"] = round((time.time() + t1) / 2.0, 3)
        status["send_heartbeat"] = False
        try:
            ocn_status = {"observing_conditions": status.pop("observing_conditions")}
            enc_status = {"enclosure": status.pop("enclosure")}
            device_status = status
        except:
            pass
        loud = False
        if loud:
            plog("\n\nStatus Sent:  \n", status)
        else:
            plog(".")  # We print this to stay informed of process on the console.

        # Consider inhibity unless status rate is low
        obsy = self.name
        if ocn_status is not None:
            lane = "weather"
            send_status(obsy, lane, ocn_status)  # NB Do not remove this send for SAF!
        if enc_status is not None:
            lane = "enclosure"
            send_status(obsy, lane, enc_status)
        if device_status is not None:
            lane = "device"
            send_status(obsy, lane, device_status)

        # NB should qualify acceptance and type '.' at that point.
        self.time_last_status = time.time()
        self.status_count += 1
        try:
            self.scan_requests(
                "mount1", cancel_check=True
            )  # NB THis has faulted, usually empty input lists.
        except:
            pass

    def update(self):
        """
        This compact little function is the heart of the code in the sense this is repeatedly
        called. It first SENDS status for all devices to AWS, then it checks for any new
        commands from AWS. Then it calls sequencer.monitor() were jobs may get launched. A
        flaw here is we do not have a Ulid for the 'Job number'.

        With a Maxim based camera, is it possible for the owner to push buttons in parallel
        with commands coming from AWS. This is useful during the debugging phase.

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
        if self.status_count > 2:  # Give time for status to form
            g_dev["seq"].manager()  # Go see if there is something new to do.

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
                    time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = g_dev["obs"].api.authenticated_request(
                    "POST", "/upload/", {"object_name": filename})
                # Only ingest new large fits.fz files to the PTR archive.
                if self.env_exists == True and filename.endswith("-EX00.fits.fz"):
                    with open(filepath, "rb") as fileobj:
                        try:
                            if not frame_exists(fileobj):
                                upload_file_and_ingest_to_archive(fileobj)
                                plog(f"--> To PTR ARCHIVE --> {str(filepath)}")
                            # If ingester fails, send to default S3 bucket.
                        except:
                            files = {"file": (filepath, fileobj)}
                            try:
                                requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                break
                            except:
                                print ("Connection glitch for the request post, waiting a moment and trying again")
                                time.sleep(5)
                            plog(f"--> To AWS --> {str(filepath)}")
                # Send all other files to S3.
                else:
                    with open(filepath, "rb") as fileobj:
                        files = {"file": (filepath, fileobj)}
                        try:
                            requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                            break
                        except:
                            print ("Connection glitch for the request post, waiting a moment and trying again")
                            time.sleep(5)
                        plog(f"--> To AWS --> {str(filepath)}")

                if (
                    filename[-3:] == "jpg"
                    or filename[-3:] == "txt"
                    or ".fits.fz" in filename
                    or ".token" in filename
                ):
                    os.remove(filepath)

                self.aws_queue.task_done()
                one_at_a_time = 0
                time.sleep(0.1)
            else:
                time.sleep(0.2)

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
                    time.sleep(0.2)
                    continue

                # Here we parse the file, set up and send to AWS
                filename = pri_image[1][1]
                filepath = pri_image[1][0] + filename  # Full path to file on disk
                aws_resp = g_dev["obs"].api.authenticated_request(
                    "POST", "/upload/", {"object_name": filename})
                # Only ingest new large fits.fz files to the PTR archive.
                if self.env_exists == True and filename.endswith("-EX00.fits.fz"):
                    with open(filepath, "rb") as fileobj:
                        try:
                            if not frame_exists(fileobj):
                                upload_file_and_ingest_to_archive(fileobj)
                                plog(f"--> To PTR ARCHIVE --> {str(filepath)}")
                            # If ingester fails, send to default S3 bucket.
                        except:
                            files = {"file": (filepath, fileobj)}
                            try:
                                requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)
                                break
                            except:
                                print ("Connection glitch for the request post, waiting a moment and trying again")
                                time.sleep(5)
                            plog(f"--> To AWS --> {str(filepath)}")
                # Send all other files to S3.
                else:
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

                if (
                    filename[-3:] == "jpg"
                    or filename[-3:] == "txt"
                    or ".fits.fz" in filename
                    or ".token" in filename
                ):
                    os.remove(filepath)

                self.fast_queue.task_done()
                one_at_a_time = 0
                time.sleep(0.1)
            else:
                time.sleep(0.2)

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
                    time.sleep(0.5)
                    continue


                # Each image that is not a calibration frame gets it's focus examined and
                # Recorded. In the future this is intended to trigger an auto_focus if the
                # Focus gets wildly worse..
                # Also the number of sources indicates whether astroalign should run.
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
                    img=np.asarray(imgdata)
                    del imgdata
                    # imgdata = (
                    #     imgdata - np.min(imgdata)
                    # ) + 100  # Add an artifical pedestal to background.
                    # imgdata = imgdata.astype("float")

                    # imgdata = imgdata.copy(
                    #     order="C"
                    # )  # NB Should we move this up to where we read the array?
                    # bkg = sep.Background(imgdata)
                    # imgdata -= bkg

                    # try:
                    #     sep.set_extract_pixstack(1000000)
                    #     sources = sep.extract(
                    #         imgdata, 4.5, err=bkg.globalrms, minarea=15
                    #     )  # Minarea should deal with hot pixels.
                    #     ix, iy = imgdata.shape

                    #     sources.sort(order="cflux")
                    #     plog("No. of detections:  ", len(sources))


                    #     if len(sources) < 20:
                    #         print ("skipping focus estimate as not enough sources in this image")
                    #         del imgdata
                    #     else:

                    #         #r0 = 0

                    #         border_x = int(ix * 0.05)
                    #         border_y = int(iy * 0.05)
                    #         r0 = []
                    #         xcoords=[]
                    #         ycoords=[]
                    #         acoords=[]
                    #         for sourcef in sources:
                    #             if (
                    #                 border_x < sourcef["x"] < ix - border_x
                    #                 and border_y < sourcef["y"] < iy - border_y
                    #                 and 1000 < sourcef["peak"] < 35000
                    #                 and 1000 < sourcef["cpeak"] < 35000
                    #             ):  # Consider a lower bound
                    #                 a0 = sourcef["a"]
                    #                 b0 = sourcef["b"]
                    #                 r0.append(round(math.sqrt(a0 * a0 + b0 * b0)*2, 2))
                    #                 xcoords.append(sourcef["x"])
                    #                 ycoords.append(sourcef["y"])
                    #                 acoords.append(sourcef["a"])

                    #         rfr, _ = sep.flux_radius(imgdata, xcoords, ycoords, acoords, 0.5, subpix=5)
                    #         rfr = np.median(rfr * 2) * pixscale
                    #         #print ("flux radius = " + sep.flux_radius(imgdata, xcoords, ycoords, acoords, 0.5, subpix=5))
                    #         del imgdata
                    #         FWHM = round(
                    #             np.median(r0) * pixscale, 3
                    #         )  # was 2x larger but a and b are diameters not radii
                    #         #print("This image has a FWHM of " + str(FWHM))
                    #         print("This image has a FWHM of " + str(rfr))
                    #         g_dev["foc"].focus_tracker.pop(0)
                    #         g_dev["foc"].focus_tracker.append(rfr)
                    #         print("Last ten FWHM : ")
                    #         print(g_dev["foc"].focus_tracker)
                    #         print("Median last ten FWHM")
                    #         print(np.nanmedian(g_dev["foc"].focus_tracker))
                    #         print("Last solved focus FWHM")
                    #         print(g_dev["foc"].last_focus_fwhm)

                    #         # If there hasn't been a focus yet, then it can't check it, so make this image the last solved focus.
                    #         if g_dev["foc"].last_focus_fwhm == None:
                    #             g_dev["foc"].last_focus_fwhm = rfr
                    #         else:
                    #             # Very dumb focus slip deteector
                    #             if (
                    #                 np.nanmedian(g_dev["foc"].focus_tracker)
                    #                 > g_dev["foc"].last_focus_fwhm
                    #                 + self.config["focus_trigger"]
                    #             ):
                    #                 g_dev["foc"].focus_needed = True
                    #                 g_dev["obs"].send_to_user(
                    #                     "Focus has drifted to "
                    #                     + str(np.nanmedian(g_dev["foc"].focus_tracker))
                    #                     + " from "
                    #                     + str(g_dev["foc"].last_focus_fwhm)
                    #                     + ". Autofocus triggered for next exposures.",
                    #                     p_level="INFO",
                    #                 )
                    # except:
                    #     print ("something failed in the SEP calculations for exposure. This could be an overexposed image")
                    #     print (traceback.format_exc())
                    #     sources = [0]

                # SmartStack Section
                if smartstackid != "no" :

                    print ("Number of sources just prior to smartstacks: " + str(len(sources)))
                    if len(sources) < 12:
                        print ("skipping stacking as there are not enough sources " + str(len(sources)) +" in this image")


                    #img = fits.open(
                    #    paths["red_path"] + paths["red_name01"]
                    #)  # Pick up reduced fits file
                    # No need to open the same image twice, just using the same one as SEP.
                    #img = sstackimghold.copy()
                    #del sstackimghold

                    #plog(img[0].header["FILTER"])

                    #stackHoldheader = img[0].header
                    #plog(g_dev["cam"].site_path + "smartstacks")

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

                    #cleanhdu=fits.PrimaryHDU()
                    #cleanhdu.data=img

                    #cleanhdr=cleanhdu.header
                    #cleanhdu.writeto(g_dev["cam"].site_path + "smartstacks/" + smartStackFilename.replace('.npy','.fit'))

                    #plog(smartStackFilename)
                    #img = np.asarray(img[0].data)
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
                        if len(sources) >= 30:
                            # Store original image
                            plog("Storing First smartstack image")
                            # storedsStack=np.nan_to_num(img)
                            # backgroundLevel =(np.nanmedian(sep.Background(storedsStack.byteswap().newbyteorder())))
                            # print (backgroundLevel)
                            # storedsStack= storedsStack - backgroundLevel

                            np.save(
                                g_dev["cam"].site_path
                                + "smartstacks/"
                                + smartStackFilename,
                                img,
                            )

                            #cleanhdu=fits.PrimaryHDU()
                            #cleanhdu.data=img

                            #cleanhdr=cleanhdu.header
                            #cleanhdu.writeto(g_dev["cam"].site_path + "smartstacks/" + smartStackFilename.replace('.npy','.fit'))

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
                        plog(datetime.datetime.now())
                        if len(sources) > 30:
                            try:
                                reprojectedimage, _ = func_timeout.func_timeout (60, aa.register, args=(img, storedsStack), kwargs={"detection_sigma":3, "min_area":9})
                                #(20, aa.register, args=(img, storedsStack, detection_sigma=3, min_area=9)

                                # scalingFactor= np.nanmedian(reprojectedimage / storedsStack)
                                # print (" Scaling Factor : " +str(scalingFactor))
                                # reprojectedimage=(scalingFactor) * reprojectedimage # Insert a scaling factor
                                storedsStack = np.asarray((reprojectedimage + storedsStack))
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


                            #except func_timeout.FunctionTimedOut:
                            #    print ("astroalign Timed Out")
                        else:
                            reprojection_failed=True


                    if reprojection_failed == True: # If we couldn't make a stack send a jpeg of the original image.
                        storedsStack=img


                    # Resizing the array to an appropriate shape for the jpg and the small fits
                    iy, ix = storedsStack.shape
                    if iy == ix:
                        storedsStack = resize(
                            storedsStack, (1280, 1280), preserve_range=True
                        )
                    else:
                        storedsStack = resize(
                            storedsStack,
                            (int(1536 * iy / ix), 1536),
                            preserve_range=True,
                        )  #  We should trim chips so ratio is exact.

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

                    imsave(
                        g_dev["cam"].site_path
                        + "smartstacks/"
                        + smartStackFilename.replace(
                            ".npy", "_" + str(ssframenumber) + ".jpg"
                        ),
                        stretched_data_uint8,
                    )

                    imsave(
                        paths["im_path"] + paths["jpeg_name10"],
                        stretched_data_uint8,
                    )

                    #g_dev["cam"].enqueue_for_fastAWS(
                    #    100, paths["im_path"], paths["jpeg_name10"]
                    #)

                    #image = (paths["im_path"], paths["jpeg_name10"])
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
                    #    )

                    plog(datetime.datetime.now())

                    del img


                    # # Save out a fits for testing purposes only
                    # firstimage = fits.PrimaryHDU()
                    # firstimage.scale("float32")
                    # firstimage.data = np.asarray(storedsStack).astype(np.float32)
                    # firstimage.header = stackHoldheader
                    # firstimage.writeto(
                    #     g_dev["cam"].site_path
                    #     + "smartstacks/"
                    #     + smartStackFilename.replace(
                    #         ".npy", str(ssframenumber) + ".fits"
                    #     ),
                    #     overwrite=True,
                    # )
                    # del firstimage



                # Solve for pointing. Note: as the raw and reduced file are already saved and an fz file
                # has already been sent up, this is purely for pointing purposes.
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

                    # check that both enough time and images have past between last solve
                    if self.images_since_last_solve > self.config[
                        "solve_nth_image"
                    ] and (
                        datetime.datetime.now() - self.last_solve_time
                    ) > datetime.timedelta(
                        minutes=self.config["solve_timer"]
                    ):
                        if smartstackid == "no" and len(sources) > 30:
                            try:
                                time.sleep(1) # A simple wait to make sure file is saved
                                solve = platesolve.platesolve(
                                    paths["red_path"] + paths["red_name01"], pixscale
                                )  # 0.5478)
                                plog(
                                    "PW Solves: ",
                                    solve["ra_j2000_hours"],
                                    solve["dec_j2000_degrees"],
                                )
                                target_ra = g_dev["mnt"].current_icrs_ra
                                target_dec = g_dev["mnt"].current_icrs_dec
                                solved_ra = solve["ra_j2000_hours"]
                                solved_dec = solve["dec_j2000_degrees"]
                                solved_arcsecperpixel = solve["arcsec_per_pixel"]
                                solved_rotangledegs = solve["rot_angle_degs"]
                                err_ha = target_ra - solved_ra
                                err_dec = target_dec - solved_dec
                                solved_arcsecperpixel = solve["arcsec_per_pixel"]
                                solved_rotangledegs = solve["rot_angle_degs"]
                                plog(
                                    " coordinate error in ra, dec:  (asec) ",
                                    round(err_ha * 15 * 3600, 2),
                                    round(err_dec * 3600, 2),
                                )  # NB WER changed units 20221012

                                # We do not want to reset solve timers during a smartStack
                                self.last_solve_time = datetime.datetime.now()
                                self.images_since_last_solve = 0

                                # IF IMAGE IS PART OF A SMARTSTACK
                                # THEN OPEN THE REDUCED FILE AND PROVIDE A WCS READY FOR STACKING
                                # if smartStack == 70000080: # This is currently a silly value... we may not be using WCS for smartstacks
                                #     img = fits.open(
                                #         paths["red_path"] + paths["red_name01"],
                                #         mode="update",
                                #         ignore_missing_end=True,
                                #     )
                                #     img[0].header["CTYPE1"] = "RA---TAN"
                                #     img[0].header["CTYPE2"] = "DEC--TAN"
                                #     img[0].header["CRVAL1"] = solved_ra * 15
                                #     img[0].header["CRVAL2"] = solved_dec
                                #     img[0].header["CRPIX1"] = float(
                                #         img[0].header["NAXIS1"] / 2
                                #     )
                                #     img[0].header["CRPIX2"] = float(
                                #         img[0].header["NAXIS2"] / 2
                                #     )
                                #     img[0].header["CUNIT1"] = "deg"
                                #     img[0].header["CUNIT2"] = "deg"
                                #     img[0].header["CROTA2"] = 180 - solved_rotangledegs
                                #     img[0].header["CDELT1"] = solved_arcsecperpixel / 3600
                                #     img[0].header["CDELT2"] = solved_arcsecperpixel / 3600
                                #     img.writeto(
                                #         paths["red_path"] + "SOLVED_" + paths["red_name01"]
                                #     )

                                # IF IMAGE IS PART OF A SMARTSTACK
                                # DO NOT UPDATE THE POINTING!

                                # NB NB NB this needs rethinking, the incoming units are hours in HA or degrees of dec
                                if (
                                    err_ha * 15 * 3600 > 1200
                                    or err_dec * 3600 > 1200
                                    or err_ha * 15 * 3600 < -1200
                                    or err_dec * 3600 < -1200
                                ) and self.config["mount"]["mount1"][
                                    "permissive_mount_reset"
                                ] == "yes":
                                    g_dev["mnt"].reset_mount_reference()
                                    plog("I've  reset the mount_reference 1")
                                    g_dev["mnt"].current_icrs_ra = solve[
                                        "ra_j2000_hours"
                                    ]
                                    g_dev["mnt"].current_icrs_dec = solve[
                                        "dec_j2000_hours"
                                    ]
                                    err_ha = 0
                                    err_dec = 0

                                if (
                                    err_ha * 15 * 3600
                                    > self.config["threshold_mount_update"]
                                    or err_dec * 3600
                                    > self.config["threshold_mount_update"]
                                ):
                                    try:
                                        if g_dev["mnt"].pier_side_str == "Looking West":
                                            g_dev["mnt"].adjust_mount_reference(
                                                err_ha, err_dec
                                            )
                                        else:
                                            g_dev["mnt"].adjust_flip_reference(
                                                err_ha, err_dec
                                            )  # Need to verify signs
                                    except:
                                        plog("This mount doesn't report pierside")

                            except Exception as e:
                                plog(
                                    "Image: did not platesolve; this is usually OK. ", e
                                )

                    else:
                        plog("skipping solve as not enough time or images have passed")
                        self.images_since_last_solve = self.images_since_last_solve + 1


                time.sleep(0.5)
                self.img = None  # Clean up all big objects.
                self.reduce_queue.task_done()
            else:
                time.sleep(0.5)


if __name__ == "__main__":
    o = Observatory(config.site_name, config.site_config)
    o.run()