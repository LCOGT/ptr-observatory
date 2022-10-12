""""
IMPORTANT TODOs:

WER 20211211

Simplify. No site specific if statements in main code if possible.
Sort out when rotator is not installed and focus temp when no probe
is in the Gemini.

Abstract away Redis, Memurai, and local shares for IPC.
"""

import bz2
import json
import math
import os
import threading
import time
import queue
import shelve
import socket

from astropy.io import fits
import numpy as np
import redis  # Client, can work with Memurai
import requests
import sep
from skimage.io import imsave
from skimage.transform import resize

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
from processing.calibration import calibrate
import ptr_events


# TODO: move this and the next function to a better location and add to fz
def to_bz2(filename, delete=False):
    """Compresses a FITS file to bz2."""

    try:
        uncomp = open(filename, "rb")
        comp = bz2.compress(uncomp.read())
        uncomp.close()
        if delete:
            os.remove(filename)
        target = open(filename + ".bz2", "wb")
        target.write(comp)
        target.close()
        return True
    except OSError:
        print("to_bz2 failed.")
        return False


# Move this function to a better location
def from_bz2(filename, delete=False):
    """Decompresses a bz2 file."""

    try:
        comp = open(filename, "rb")
        uncomp = bz2.decompress(comp.read())
        comp.close()
        if delete:
            os.remove(filename)
        target = open(filename[0:-4], "wb")
        target.write(uncomp)
        target.close()
        return True
    except OSError:
        print("from_bz2 failed.")
        return False


def send_status(obsy, column, status_to_send):
    """Sends an update to the status endpoint."""

    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}
    data = json.dumps(payload)
    response = requests.post(uri_status, data=data)

    if response.ok:
        print("Status sent successfully.")
    else:
        print(
            'self.api.authenticated_request("PUT", uri, status):  Failed! ',
            response.status_code,
        )


class Observatory:
    """Docstring here"""

    def __init__(self, name, config):
        # This is the ayneclass through which we can make authenticated api calls.
        self.api = API_calls()

        self.command_interval = 3  # Seconds between polls for new commands
        self.status_interval = 4  # NOTE THESE ARE IMPLEMENTED AS A DELTA NOT A RATE.

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
        self.device_types = config["device_types"]
        self.wema_types = config["wema_types"]
        self.enc_types = None  # config['enc_types']
        self.short_status_devices = None  # May not be needed for no wema obsy

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

        # Check directory system has been constructed
        # for new sites or changed directories in configs.
        if not os.path.exists(g_dev["cam"].site_path + "ptr_night_shelf"):
            os.makedirs(g_dev["cam"].site_path + "ptr_night_shelf")
        if not os.path.exists(g_dev["cam"].site_path + "archive"):
            os.makedirs(g_dev["cam"].site_path + "archive")

        self.time_last_status = time.time() - 3
        # Build the to-AWS Try again, reboot, verify dome and tel and start a thread.
        self.aws_queue = queue.PriorityQueue()
        self.aws_queue_thread = threading.Thread(target=self.send_to_AWS, args=())
        self.aws_queue_thread.start()

        # =============================================================================
        # Here we set up the reduction Queue and Thread:
        # =============================================================================

        # Don't set a maximum size or we will lose files.
        self.reduce_queue = queue.Queue()
        self.reduce_queue_thread = threading.Thread(target=self.reduce_image, args=())
        self.reduce_queue_thread.start()
        self.blocks = None
        self.projects = None
        self.events_new = None
        self.reset_last_reference()

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
                print(name)
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
                    print(f"Unknown device: {name}")
                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device
        print("Finished creating devices.")

    def update_config(self):
        """Sends the config to AWS."""

        uri = f"https://api.photonranch.org/dev/{self.name}/config/"
        self.config["events"] = g_dev["events"]
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response.ok:
            print("Config uploaded successfully.")

    def scan_requests(self):
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
            # Wait a bit before polling for new commands
            time.sleep(self.command_interval)

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
                    unread_commands.sort(key=lambda x: x["ulid"])
                    # Process each job one at a time
                    print("# of incomming commands:  ", len(unread_commands))
                    for cmd in unread_commands:
                        if self.config["selector"]["selector1"]["driver"] is None:
                            port = cmd["optional_params"][
                                "instrument_selector_position"
                            ]
                            g_dev["mnt"].instrument_port = port
                            cam_name = self.config["selector"]["selector1"]["cameras"][
                                port
                            ]
                            if cmd["deviceType"][:6] == "camera":
                                # Note camelCase is the format of command keys
                                cmd["required_params"]["deviceInstance"] = cam_name
                                cmd["deviceInstance"] = cam_name
                                device_instance = cam_name
                            else:
                                try:
                                    device_instance = cmd["deviceInstance"]
                                except:
                                    device_instance = cmd["required_params"][
                                        "deviceInstance"
                                    ]
                        else:
                            device_instance = cmd["deviceInstance"]

                        print("obs.scan_request: ", cmd)
                        device_type = cmd["deviceType"]
                        device = self.all_devices[device_type][device_instance]
                        try:
                            device.parse_command(cmd)
                        except Exception as e:
                            print("Exception in obs.scan_requests:  ", e)

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
                print("Sequencer Hold asserted.")
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
                if device_name in self.config["wema_types"] and (
                    self.is_wema or self.site_is_specific
                ):
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
            print("\n\nStatus Sent:  \n", status)  # from Update:  ', status))
        else:
            print(".")  # We print this to stay informed of process on the console.

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
        # self.redis_server.set('obs_time', self.time_last_status, ex=120 )
        self.status_count += 1

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
        if self.status_count > 2:  # Give time for status to form
            g_dev["seq"].manager()  # Go see if there is something new to do.

    def run(self):  # run is a poor name for this function.
        try:
            # Keep the main thread alive, otherwise signals are ignored
            while True:
                self.update()
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return

    # Note this is a thread!
    def send_to_AWS(self):  # pri_image is a tuple, smaller first item has priority.
        # second item is also a tuple containing im_path and name.

        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if not self.aws_queue.empty():
                pri_image = self.aws_queue.get(block=False)
                if pri_image is None:
                    print("got an empty entry in aws_queue???")
                    self.aws_queue.task_done()
                    time.sleep(0.2)
                    continue
                # Here we parse the file, set up and send to AWS
                im_path = pri_image[1][0]
                name = pri_image[1][1]
                if not (
                    name[-3:] == "jpg"
                    or name[-3:] == "txt"
                    or name[-3:] == "token"
                    or ".fits.fz" in name
                ):
                    # compress first
                    to_bz2(im_path + name)
                    name = name + ".bz2"
                aws_req = {"object_name": name}
                aws_resp = g_dev["obs"].api.authenticated_request(
                    "POST", "/upload/", aws_req
                )
                with open(im_path + name, "rb") as f:
                    files = {"file": (im_path + name, f)}
                    # if name[-3:] == 'jpg':
                    print("--> To AWS -->", str(im_path + name))
                    requests.post(aws_resp["url"], data=aws_resp["fields"], files=files)

                if (
                    name[-3:] == "bz2"
                    or name[-3:] == "jpg"
                    or name[-3:] == "txt"
                    or ".fits.fz" in name
                ):
                    os.remove(im_path + name)

                self.aws_queue.task_done()
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
        response = requests.post(url_log, body)
        if not response.ok:
            print("Log did not send, usually not fatal.")

    # Note this is another thread!
    def reduce_image(self):
        """

        The incoming object is typically a large fits HDU.
        Found in its header will be both standard image parameters
        and destination filenames.

        Before saving reduced or generating postage,
        we flip the images so East is left and North is up.
        The header keyword PIERSIDE defines the orientation.
        """
        while True:
            if not self.reduce_queue.empty():
                pri_image = self.reduce_queue.get(block=False)

                if pri_image is None:
                    time.sleep(0.5)
                    continue

                # Here we parse the input and calibrate it.
                paths = pri_image[0]
                hdu = pri_image[1]
                backup = pri_image[0].copy()  # NB NB Should this be a deepcopy?

                lng_path = g_dev["cam"].lng_path
                # NB Important decision here, do we flash calibrate screen and sky flats? For now, Yes.

                calibrate(hdu, lng_path, paths["frame_type"], quick=False)

                # Note the raw ibmage is not flipped/

                # NB NB NB I do not think we should be flipping ALt_Az images.
                # NB NB NB I think ever raw images should be flipped so that at
                # PA = 0.0. that N is up and East is to the left. Since LCO only
                # has fork telescopes all LCO instruments have the same native alignment
                # in the archive. WER 20220703

                wpath = (
                    paths["red_path"] + paths["red_name01_lcl"]
                )  # This name is convienent for local sorting

                hdu.writeto(wpath, overwrite=True)  # Bigfit reduced
                # This was in camera after reduce and it had a race condition.

                if hdu.header["OBSTYPE"].lower() in (
                    "bias",
                    "dark",
                    "screenflat",
                    "skyflat",
                ):
                    hdu.writeto(paths["cal_path"] + paths["cal_name"], overwrite=True)

                # Will try here to solve
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
                    try:
                        # NB NB The following needs better bin management
                        solve = platesolve.platesolve(
                            wpath, float(hdu.header["PIXSCALE"])
                        )
                        print(
                            "PW Solves: ",
                            solve["ra_j2000_hours"],
                            solve["dec_j2000_degrees"],
                        )

                        # Update the NEW header for a "Reduced" fits. The Raw fits has not been changed.
                        hdu.header["RA-J20PW"] = solve["ra_j2000_hours"]
                        hdu.header["DECJ20PW"] = solve["dec_j2000_degrees"]
                        hdu.header["RAHRS"] = float(solve["ra_j2000_hours"])
                        hdu.header["RA"] = float(solve["ra_j2000_hours"] * 15)
                        hdu.header["DEC"] = float(solve["dec_j2000_degrees"])
                        hdu.header["MEAS-SPW"] = solve["arcsec_per_pixel"]
                        hdu.header["MEAS-RPW"] = solve["rot_angle_degs"]

                        # This updates the RA and Dec in the raw file header if a solution is found
                        with fits.open(
                            paths["raw_path"] + paths["raw_name00"], "update"
                        ) as f:
                            for hdbf in f:
                                hdbf.header["RA-J20PW"] = solve["ra_j2000_hours"]
                                hdbf.header["DECJ20PW"] = solve["dec_j2000_degrees"]
                                hdbf.header["RAHRS"] = float(solve["ra_j2000_hours"])
                                hdbf.header["RA"] = float(solve["ra_j2000_hours"] * 15)
                                hdbf.header["DEC"] = float(solve["dec_j2000_degrees"])
                                hdbf.header["MEAS-SPW"] = solve["arcsec_per_pixel"]
                                hdbf.header["MEAS-RPW"] = solve["rot_angle_degs"]

                        target_ra = g_dev["mnt"].current_icrs_ra
                        target_dec = g_dev["mnt"].current_icrs_dec
                        solved_ra = solve["ra_j2000_hours"]
                        solved_dec = solve["dec_j2000_degrees"]
                        err_ha = target_ra - solved_ra
                        err_dec = target_dec - solved_dec
                        print("err ra, dec:  ", err_ha, err_dec)
                        # NB NB NB Need to add Pierside as a parameter to this cacc 20220214 WER

                        if g_dev["mnt"].pier_side_str == "Looking West":
                            g_dev["mnt"].adjust_mount_reference(err_ha, err_dec)
                        else:
                            g_dev["mnt"].adjust_flip_reference(
                                err_ha, err_dec
                            )  # Need to verify signs
                    except:
                        print(
                            "Image:  ",
                            wpath[-24:-5],
                            " did not solve; this is usually OK.",
                        )
                        hdu.header["RA-J20PW"] = False
                        hdu.header["DECJ20PW"] = False
                        hdu.header["MEAS-SPW"] = False
                        hdu.header["MEAS-RPW"] = False
                # Return to classic processing

                # Here we need to consider just what local reductions and calibrations really make sense to
                # process in-line vs doing them in another process. For all practical purposes everything
                # below can be done in a different process, the exception perhaps has to do with autofocus
                # processing.

                # Note we may be using different files if calibrate is null.
                # NB We should only write this if calibrate actually succeeded to return a result ??
                # This might want to be yet another thread queue, esp if we want to do Aperture Photometry.
                no_AWS = False
                quick = False
                do_sep = False
                spot = None
                # Note this was turned off because very rarely it hangs internally.
                if (
                    do_sep
                ):  # We have already ran this code when focusing, but we should not ever get here when doing that.
                    try:
                        img = hdu.data.copy().astype("float")
                        bkg = sep.Background(img)
                        img = img - bkg
                        sources = sep.extract(img, 4.5, err=bkg.globalrms, minarea=9)
                        sources.sort(order="cflux")
                        sep_result = []
                        spots = []
                        for source in sources:
                            a0 = source["a"]
                            b0 = source["b"]
                            r0 = 2 * round(math.sqrt(a0**2 + b0**2), 2)
                            sep_result.append(
                                (
                                    round((source["x"]), 2),
                                    round((source["y"]), 2),
                                    round((source["cflux"]), 2),
                                    round(r0),
                                    3,
                                )
                            )
                            spots.append(round((r0), 2))
                        spot = np.array(spots)
                        try:
                            spot = np.median(spot[-9:-2])  #  This grabs seven spots.
                            if len(sep_result) < 5:
                                spot = None
                        except:
                            spot = None
                    except:
                        spot = None

                # =============================================================================
                # x = 2      From Numpy: a way to quickly embed an array in a larger one
                # y = 3
                # wall[x:x+block.shape[0], y:y+block.shape[1]] = block
                # =============================================================================

                hdu.data = hdu.data.astype("uint16")
                iy, ix = hdu.data.shape
                if iy == ix:
                    resized_a = resize(hdu.data, (1280, 1280), preserve_range=True)
                else:
                    resized_a = resize(
                        hdu.data, (int(1536 * iy / ix), 1536), preserve_range=True
                    )  # We should trim chips so ratio is exact.
                hdu.data = resized_a.astype("uint16")

                i768sq_data_size = hdu.data.size

                hdu.writeto(paths["im_path"] + paths["i768sq_name10"], overwrite=True)
                hdu.data = resized_a.astype("float")

                # New contrast scaling code:
                stretched_data_float = Stretch().stretch(hdu.data)
                stretched_256 = 255 * stretched_data_float
                hot = np.where(stretched_256 > 255)
                cold = np.where(stretched_256 < 0)
                stretched_256[hot] = 255
                stretched_256[cold] = 0
                stretched_data_uint8 = stretched_256.astype(
                    "uint8"
                )  # Eliminates a user warning
                hot = np.where(stretched_data_uint8 > 255)
                cold = np.where(stretched_data_uint8 < 0)
                stretched_data_uint8[hot] = 255
                stretched_data_uint8[cold] = 0
                imsave(paths["im_path"] + paths["jpeg_name10"], stretched_data_uint8)

                jpeg_data_size = abs(
                    stretched_data_uint8.size - 1024
                )  # istd = np.std(hdu.data)

                if (
                    not no_AWS
                ):  # In the no_AWS case should we skip more of the above processing?
                    g_dev["cam"].enqueue_for_AWS(
                        jpeg_data_size, paths["im_path"], paths["jpeg_name10"]
                    )
                    g_dev["cam"].enqueue_for_AWS(
                        i768sq_data_size, paths["im_path"], paths["i768sq_name10"]
                    )
                    g_dev["cam"].enqueue_for_AWS(
                        13000000, paths["raw_path"], paths["raw_name00"]
                    )  # NB need to chunkify 25% larger then small fits.
                    g_dev["cam"].enqueue_for_AWS(
                        26000000, paths["raw_path"], paths["raw_name00"] + ".fz"
                    )

                time.sleep(0.5)
                img = None  # Clean up all big objects.
                try:
                    hdu = None
                except:
                    pass
                g_dev["obs"].send_to_user(
                    "An image reduction has completed.", p_level="INFO"
                )
                self.reduce_queue.task_done()
            else:
                time.sleep(0.5)


if __name__ == "__main__":

    # # Define a command line argument to specify the config file to use
    # parser = argparse.ArgumentParser()
    # parser.add_argument('--config', type=str, default="default")
    # options = parser.parse_args()
    # # Import the specified config file
    # print(options.config)
    # if options.config == "default":
    #     config_file_name = "config"
    # else:
    #     config_file_name = f"config_files.config_{options.config}"
    # config = importlib.import_module(config_file_name)
    # print(f"Starting up {config.site_name}.")

    # Start up the observatory
    o = Observatory(config.site_name, config.site_config)
    o.run()
