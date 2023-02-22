"""
WER 20210624

First attempt at having a parallel dedicated agent for weather and enclosure.
This code should be as simple and reliable as possible, no hanging variables,
etc.

This would be a good place to log the weather data and any enclosure history,
once this code is stable enough to run as a service.

We need to resolve the 'redis' solution for each site. 20210826

Note this is derived from OBS but is WEMA so we should not need to build
things from a config file, but rather by implication just pick the correct
data from the config file. All config files for a cluster of mounts/telescopes
under one WEMA should start with common data for the WEMA. Note the WEMA
has no knowledge of how many mnt/tels there may be in any given enclosure.
"""


import os
import signal
import json
import shelve
import time
import socket
from pathlib import Path

import requests
import redis

import config
from api_calls import API_calls
import ptr_events
from devices.observing_conditions import ObservingConditions
from devices.enclosure import Enclosure
from global_yard import g_dev
from ptr_utility import plog


# FIXME: This needs attention once we figure out the restart_obs script.
def terminate_restart_observer(site_path, no_restart=False):
    """Terminates observatory code if running and restarts obs."""
    if no_restart is False:
        return

    camShelf = shelve.open(site_path + "ptr_night_shelf/" + "pid_obs")
    pid = camShelf["pid_obs"]  # a 9 character string
    camShelf.close()
    try:
        print("Terminating:  ", pid)
        os.kill(pid, signal.SIGTERM)
    except:
        print("No observer process was found, starting a new one.")
    # The above routine does not return but does start a process.
    parentPath = Path.cwd()
    os.system("cmd /c " + str(parentPath) + "\restart_obs.bat")

    return


def send_status(obsy, column, status_to_send):
    """Sends a status update to AWS."""

    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # NB None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}
    data = json.dumps(payload)
    try:
        response = requests.post(uri_status, data=data)

    #if response.ok:
       # pass
        print("Status sent successfully.")
    except:
        print(
            'self.api.authenticated_request("PUT", uri, status):  Failed! ',
            response.status_code,
        )

class WxEncAgent:
    """A class for weather enclosure functionality."""

    def __init__(self, name, config):

        self.api = API_calls()

        # Not relevent for SAF... No commands to Wx are sent by AWS.
        self.command_interval = 20

        self.status_interval = 45
        self.name = name

        self.site_name = name
        self.config = config
        g_dev["obs"] = self
        # TODO: Work through site vs mnt/tel and sub-site distinction.

        self.site = config["site"]

        if self.config["wema_is_active"]:
            self.hostname = self.hostname = socket.gethostname()
            if self.hostname in self.config["wema_hostname"]:
                self.is_wema = True
                g_dev["wema_write_share_path"] = config["wema_write_share_path"]
                self.wema_path = g_dev["wema_write_share_path"]
                self.site_path = self.wema_path
            else:
                # This host is a client
                self.is_wema = False  # This is a client.
                self.site_path = config["client_write_share_path"]
                g_dev["site_path"] = self.site_path
                g_dev["wema_write_share_path"] = self.site_path  # Just to be safe.
                self.wema_path = g_dev["wema_write_share_path"]
        else:
            self.is_wema = False  # This is a client.
            self.site_path = config["client_write_share_path"]
            g_dev["site_path"] = self.site_path
            g_dev["wema_write_share_path"] = self.site_path  # Just to be safe.
            self.wema_path = g_dev["wema_write_share_path"]
        if self.config["site_is_specific"]:
            self.site_is_specific = True
        else:
            self.site_is_specific = False

        self.last_request = None
        self.stopped = False
        self.site_message = "-"
        self.site_mode = config["site_in_automatic_default"]
        self.device_types = config["wema_types"]
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.display_events()

        self.wema_pid = os.getpid()
        print("WEMA_PID:  ", self.wema_pid)

        if config["redis_ip"] is not None:
            self.redis_server = redis.StrictRedis(
                host=config["redis_ip"], port=6379, db=0, decode_responses=True
            )
            self.redis_wx_enabled = True
            # Enable wide easy access to this object with redis.
            g_dev["redis"] = self.redis_server
            for key in self.redis_server.keys():
                self.redis_server.delete(key)  # Flush old state.
            self.redis_server.set("wema_pid", self.wema_pid)
        else:
            self.redis_wx_enabled = False
            g_dev["redis"] = None
        #  g_dev['redis_server']['wema_loaded'] = True

        # Here we clean up any older processes
        # prior_wema = self.redis_server.get("wema_pid")
        # prior_obs = self.redis_server.get("obs_pid")

        # if prior_wema is not None:
        #     pid = int( prior_wema)
        #     try:
        #         print("Terminating Wema:  ", pid)
        #         os.kill(pid, signal.SIGTERM)
        #     except:
        #         print("No wema process was found, starting a new one.")
        # if prior_obs is not None:
        #     pid = int( prior_obs)
        #     try:
        #         print("Terminating Obs:  ", pid)
        #         os.kill(pid, signal.SIGTERM)
        #     except:
        #         print("No observer process was found, starting a new one.")

        self.wema_pid = os.getpid()
        print("Fresh WEMA_PID:  ", self.wema_pid)
        # self.redis_server.set('wema_pid', self.wema_pid)

        # Redundant store of wema_pid
        camShelf = shelve.open(self.site_path + "ptr_night_shelf/" + "pid_wema")
        camShelf["pid_wema"] = self.wema_pid
        camShelf["pid_time"] = time.time()
        camShelf.close()
        self.update_config()
        self.create_devices(config)
        self.time_last_status = time.time() - 60  #forces early status on startup.
        self.loud_status = False
        self.blocks = None
        self.projects = None
        self.events_new = None
        immed_time = time.time()
        self.obs_time = immed_time
        self.wema_start_time = immed_time
        # self.redis_server.set('obs_time', immed_time, ex=360)
        # terminate_restart_observer(g_dev['obs']['site_path'], no_restart=True)

    def create_devices(self, config: dict):
        self.all_devices = {}
        for (
            dev_type
        ) in self.device_types:  # This has been set up for wema to be ocn and enc.
            self.all_devices[dev_type] = {}
            devices_of_type = config.get(dev_type, {})
            device_names = devices_of_type.keys()
            if dev_type == "camera":
                pass
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                # settings = devices_of_type[name].get("settings", {})

                if dev_type == "observing_conditions":

                    device = ObservingConditions(
                        driver, name, self.config, self.astro_events
                    )
                elif dev_type == "enclosure":
                    device = Enclosure(driver, name, self.config, self.astro_events)
                else:
                    print(f"Unknown device: {name}")
                self.all_devices[dev_type][name] = device
        print("Finished creating devices.")

    def update_config(self):
        """Sends the config to AWS."""

        uri = f"{self.config['site']}/config/"
        self.config["events"] = g_dev["events"]
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("\n\nConfig uploaded successfully.")

    def scan_requests(self, mount):
        """

        For a wema this can be used to capture commands to the wema once the
        AWS side knows how to redirect from any mount/telescope to the common
        Wema.
        This should be changed to look into the site command queue to pick up
        any commands directed at the Wx station, or if the agent is going to
        always exist lets develop a seperate command queue for it.
        """
        return

    def update_status(self):
        """
        Collect status from weather and enclosure devices and sends an
        update to AWS. Each device class is responsible for implementing the
        method 'get_status()', which returns a dictionary.
        """

        loud = False
        while time.time() < self.time_last_status + self.status_interval:
            return
        t1 = time.time()
        status = {}

        for dev_type in self.device_types:
            status[dev_type] = {}
            devices_of_type = self.all_devices.get(dev_type, {})
            device_names = devices_of_type.keys()
            for device_name in device_names:
                device = devices_of_type[device_name]
                status[dev_type][device_name] = device.get_status()

        # Include the time that the status was assembled and sent.
        status["timestamp"] = round((time.time() + t1) / 2.0, 3)
        status["send_heartbeat"] = False
        enc_status = None
        ocn_status = None
        device_status = None

        try:
            ocn_status = {"observing_conditions": status.pop("observing_conditions")}
            enc_status = {"enclosure": status.pop("enclosure")}
            device_status = status
        except:
            pass

        obsy = self.name
        if ocn_status is not None:
            lane = "weather"
            #send_status(obsy, lane, ocn_status)  # Do not remove this send for SAF!
            if ocn_status is not None:
                lane = "weather"
                
                try:
                    send_status(obsy, lane, ocn_status)
                except:
                    time.sleep(10)
                    try:
                        send_status(obsy, lane, ocn_status)
                    except:
                        time.sleep(10)
                        try:
                            send_status(obsy, lane, ocn_status)
                        except:
                            plog("Three Tries to send Wx status for MRC failed.")
        if enc_status is not None:
            lane = "enclosure"
            #send_status(obsy, lane, enc_status)
            try:
                time.sleep(2)
                send_status(obsy, lane, enc_status)
            except:
                time.sleep(10)
                try:
                    send_status(obsy, lane, enc_status)
                except:
                    time.sleep(10)
                    try:
                        send_status(obsy, lane, enc_status)
                    except:
                        plog("Three Tries to send Enc status for MRC2 failed.")
            if self.name == "mrc":   #NB  This does not scale, Wema config should has a list of sub-sites.
                obsy = 'mrc2'        #  or have AWS pick up status from the wema only.
            if ocn_status is not None:
                lane = "weather"
                
                try:
                    time.sleep(2)
                    send_status(obsy, lane, ocn_status)
                except:
                    time.sleep(10)
                    try:
                        send_status(obsy, lane, ocn_status)
                    except:
                        time.sleep(10)
                        try:
                            send_status(obsy, lane, ocn_status)
                        except:
                            plog("Three Tries to send Wx status for MRC2 failed.")
                    

            if enc_status is not None:
                lane = "enclosure"
                try:
                    time.sleep(2)
                    send_status(obsy, lane, enc_status)
                except:
                    time.sleep(10)
                    try:
                        send_status(obsy, lane, enc_status)
                    except:
                        time.sleep(10)
                        try:
                            send_status(obsy, lane, enc_status)
                        except:
                            plog("Three Tries to send Enc status for MRC2 failed.")

        loud = False
        if loud:
            print("\n\n > Status Sent:  \n", status)
        else:
            try:
                obs_time = float(self.redis_server.get("obs_time"))
                delta = time.time() - obs_time
            except:
                delta = 999.99  # NB Temporarily flags something really wrong.
            if delta > 1800:
                print(">The observer's time is stale > 300 seconds:  ", round(delta, 2))
            # Here is where we terminate the obs.exe and restart it.
            if delta > 3600:
                # terminate_restart_observer(g_dev['obs'}['site_path'], no_restart=True)
                pass
            else:
                print(">")

    def update(self):
        self.update_status()
        time.sleep(15)

    def run(self):  # run is a poor name for this function.
        """Runs the continuous WEMA process.

        Loop ends with keyboard interrupt."""
        try:
            while True:
                self.update()  # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return

    def send_to_user(self, p_log, p_level="INFO"):
        """ """
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
            response = requests.post(url_log, body)
        except Exception:
            print("Log did not send, usually not fatal.")


if __name__ == "__main__":
    wema = WxEncAgent(config.site_name, config.site_config)
    wema.run()
