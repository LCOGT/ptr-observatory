
"""
WER 20210624

First attempt at having a parallel dedicated agent for weather and enclosure.

"""

import time
import threading
import queue
import requests
import os
import redis
import json
import numpy as np
import math
import shelve
from pprint import pprint
from api_calls import API_calls
import matplotlib.pyplot as plt
import ptr_events
from devices.wms_enclosure_agent import Enclosure
from devices.wms_observing_agent import ObservingConditions
from global_yard import g_dev
import bz2
import httplib2

# move this function to a better location
def to_bz2(filename, delete=False):
    try:
        uncomp = open(filename, 'rb')
        comp = bz2.compress(uncomp.read())
        uncomp.close()
        if delete:
            try:
                os.remove(filename)
            except:
                pass
        target = open(filename + '.bz2', 'wb')
        target.write(comp)
        target.close()
        return True
    except:
        pass
        print('to_bz2 failed.')
        return False


# move this function to a better location
def from_bz2(filename, delete=False):
    try:
        comp = open(filename, 'rb')
        uncomp = bz2.decompress(comp.read())
        comp.close()
        if delete:
            os.remove(filename)
        target = open(filename[0:-4], 'wb')
        target.write(uncomp)
        target.close()
        return True
    except:
        print('from_bz2 failed.')
        return False


# move this function to a better location
# The following function is a monkey patch to speed up outgoing large files.
# NB does not appear to work. 20200408 WER
def patch_httplib(bsize=400000):
    """ Update httplib block size for faster upload (Default if bsize=None) """
    if bsize is None:
        bsize = 8192

    def send(self, p_data, sblocks=bsize):
        """Send `p_data' to the server."""
        if self.sock is None:
            if self.auto_open:
                self.connect()
            else:
                raise httplib2.NotConnected()
        if self.debuglevel > 0:
            print("send:", repr(p_data))
        if hasattr(p_data, 'read') and not isinstance(p_data, list):
            if self.debuglevel > 0:
                print("sendIng a read()able")
            datablock = p_data.read(sblocks)
            while datablock:
                self.sock.sendall(datablock)
                datablock = p_data.read(sblocks)
        else:
            self.sock.sendall(p_data)
    httplib2.httplib.HTTPConnection.send = send
    
    
class Observatory:

    def __init__(self, name, config):

        # This is the class through which we can make authenticated api calls.
        self.api = API_calls()
        self.command_interval = 2.5   # seconds between polls for new commands
        self.status_interval = 2.5    # NOTE THESE IMPLEMENTED AS A DELTA NOT A RATE.
        self.name = name
        self.site_name = name
        self.config = config
        self.site_path = config['site_path']
        self.last_request = None
        self.stopped = False
        self.site_message = '-'
        self.device_types = [
            'observing_conditions',
            'enclosure',
            # 'mount',
            # 'telescope',
            # 'screen',
            # 'rotator',
            # 'focuser',
            # 'selector',
            # 'filter_wheel',
            # 'camera',
            # 'sequencer'          
            ] 
        # Instantiate the helper class for astronomical events
        #Soon the primary event / time values come from AWS>
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.display_events()
        # Send the config to aws   # NB NB NB This has faulted.
        self.update_config()
        # Use the configuration to instantiate objects for all devices.
        self.create_devices(config)
        self.loud_status = False
        #g_dev['obs']: self
        g_dev['obs'] = self 
        site_str = config['site']
        g_dev['site']:  site_str
        self.g_dev = g_dev
        self.time_last_status = time.time() - 3
        self.blocks = None
        self.projects = None
        self.events_new = None
        redis_ip = config['redis_ip']
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
        else:
            self.redis_wx_enabled = False


    def create_devices(self, config: dict):
        # This dict will store all created devices, subcategorized by dev_type.
        self.all_devices = {}
        # Create device objects by type, going through the config by type.
        for dev_type in self.device_types:
            self.all_devices[dev_type] = {}
            # Get the names of all the devices from each dev_type.
            # if dev_type == 'camera':
            #     breakpoint()
            devices_of_type = config.get(dev_type, {})
            device_names = devices_of_type.keys()
            # Instantiate each device object from based on its type
            if dev_type == 'camera':
                pass
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                settings = devices_of_type[name].get("settings", {})
                # print('looking for dev-types:  ', dev_type)
                if dev_type == "observing_conditions":
                    device = ObservingConditions(driver, name, self.config, self.astro_events)
                elif dev_type == 'enclosure':
                    device = Enclosure(driver, name, self.config, self.astro_events)

                else:
                    print(f"Unknown device: {name}")
                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device
                # NB 20200410 This dropped out of the code: self.all_devices[dev_type][name] = [device]
        print("Finished creating devices.")

    def update_config(self):
        '''
        Send the config to aws.
        '''
        uri = f"{self.name}/config/"
        self.config['events'] = g_dev['events']
        #print(self.config)
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("Config uploaded successfully.")

    def scan_requests(self, mount):
        return
        '''
        Outline of change 20200323 WER
        Get commands from AWS, and post a STOP/Cancel flag
        This function will be a Thread. we will limit the
        polling to once every 2.5 - 3 seconds because AWS does not
        appear to respond any faster.  When we do poll we parse
        the action keyword for 'stop' or 'cancel' and post the
        existence of the timestamp of that command to the
        respective device attribute   <self>.cancel_at.  Then we
        also enqueue the incoming command as well.

        when a device is status scanned, if .cancel_at is not
        None, the device takes appropriate action and sets
        cancel_at back to None.

        NB at this time we are preserving one command queue
        for all devices at a site.  This may need to change when we
        have parallel mountings or independently controlled cameras.
        
        NB NB This does nothing now since we have no commands specifically
        directed at this agent.  Open and close, if in manual, are directed
        at the obs based enclosure and passed over via redis.
        '''

        # # This stopping mechanism allows for threads to close cleanly.
        # while not self.stopped:
        #     # Wait a bit before polling for new commands
        #     time.sleep(self.command_interval)
        #    #  t1 = time.time()
        #     if not g_dev['seq'].sequencer_hold:
        #         url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
        #         body = {"site": self.name}
        #         # uri = f"{self.name}/{mount}/command/"
        #         cmd = {}
        #         # Get a list of new jobs to complete (this request
        #         # marks the commands as "RECEIVED")
        #         unread_commands = requests.request('POST', url_job, \
        #                                            data=json.dumps(body)).json()
        #         # Make sure the list is sorted in the order the jobs were issued
        #         # Note: the ulid for a job is a unique lexicographically-sortable id
        #         if len(unread_commands) > 0:
        #             #print(unread_commands)
        #             unread_commands.sort(key=lambda x: x["ulid"])
        #             # Process each job one at a time
        #             for cmd in unread_commands:
        #                 if self.config['selector']['selector1']['driver'] != 'Null':
        #                     port = cmd['optional_params']['instrument_selector_position'] 
        #                     g_dev['mnt'].instrument_port = port
        #                     cam_name = self.config['selector']['selector1']['cameras'][port]
        #                     if cmd['deviceType'][:6] == 'camera':
        #                         cmd['required_params']['device_instance'] = cam_name
        #                         cmd['deviceInstance'] = cam_name
        #                         deviceInstance = cam_name
        #                     else:
        #                         try:
        #                             try:
        #                                 deviceInstance = cmd['deviceInstance']
        #                             except:
        #                                 deviceInstance = cmd['required_params']['device_instance']
        #                         except:
        #                             breakpoint()
        #                             pass
        #                 else:
        #                     deviceInstance = cmd['deviceInstance']
        #                 print('obs.scan_request: ', cmd)
        #                 deviceType = cmd['deviceType']
        #                 device = self.all_devices[deviceType][deviceInstance]
        #                 try:
        #                     device.parse_command(cmd)
        #                 except Exception as e:
        #                     print( 'Exception in obs.scan_requests:  ', e)
        #        # # print('scan_requests finished in:  ', round(time.time() - t1, 3), '  seconds')
        #        #  ## Test Tim's code
        #        #  url_blk = "https://calendar.photonranch.org/dev/siteevents"
        #        #  body = json.dumps({
        #        #      'site':  self.config['site'],
        #        #      'start':  g_dev['d-a-y'] + 'T12:00:00Z',
        #        #      'end':    g_dev['next_day'] + 'T19:59:59Z',
        #        #      'full_project_details:':  False})
        #        #  if True: #self.blocks is None:   #This currently prevents pick up of calendar changes.  OK for the moment.
        #        #      blocks = requests.post(url_blk, body).json()
        #        #      if len(blocks) > 0:   #   is not None:
        #        #          self.blocks = blocks
        #        #  url_proj = "https://projects.photonranch.org/dev/get-all-projects"
        #        #  if True: #self.projects is None:
        #        #      all_projects = requests.post(url_proj).json()
        #        #      self.projects = []
        #        #      if len(all_projects) > 0 and len(blocks)> 0:   #   is not None:
        #        #          self.projects = all_projects   #.append(all_projects)  #NOTE creating a list with a dict entry as item 0
        #        #          #self.projects.append(all_projects[1])
        #         '''
        #         Design Note.  blocks relate to scheduled time at a site so we expect AWS to mediate block 
        #         assignments.  Priority of blocks is determined by the owner and a 'equipment match' for
        #         background projects.
                
        #         Projects on the other hand can be a very large pool so how to manage becomes an issue.
        #         TO the extent a project is not visible at a site, aws should not present it.  If it is
        #         visible and passes the owners priority it should then be presented to the site.
                
        #         '''

        #         if self.events_new is None:
        #             url = 'https://api.photonranch.org/api/events?site=SAF'

        #             self.events_new = requests.get(url).json()

        #         return   # Continue   #This creates an infinite loop
                
        #     else:
        #         print('Sequencer Hold asserted.')    #What we really want here is looking for a Cancel/Stop.
        #         continue

    def update_status(self):
        ''' Collect status from all devices and send an update to aws.
        Each device class is responsible for implementing the method
        `get_status` which returns a dictionary.
        '''

        # This stopping mechanism allows for threads to close cleanly.
        loud = False        
        # if g_dev['cam_retry_doit']:
        #     #breakpoint()   #THis should be obsolete.
        #     del g_dev['cam']
        #     device = Camera(g_dev['cam_retry_driver'], g_dev['cam_retry_name'], g_dev['cam_retry_config'])
        #     print("Deleted and re-created:  ,", device)
        # Wait a bit between status updates
        while time.time() < self.time_last_status + self.status_interval:
            # time.sleep(self.st)atus_interval  #This was prior code
            # print("Staus send skipped.")
            return   # Note we are just not sending status, too soon.

        t1 = time.time()
        status = {}
        # status['sending_site'] = self.config['site']
        # status['sending_agent'] = 'wx_enc_agent'
        # Loop through all types of devices.
        # For each type, we get and save the status of each device.
        for dev_type in self.device_types:

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
                status[dev_type][device_name] = device.get_status()
        # Include the time that the status was assembled and sent.
        status["timestamp"] = round((time.time() + t1)/2., 3)
        status['send_heartbeat'] = False
        loud = False
        if loud:
            print('\n\nStatus Sent:  \n', status)   # from Update:  ', status))
        else:
            print('.') #, status)   # We print this to stay informed of process on the console.
            # breakpoint()
            # self.send_log_to_frontend("WARN cam1 just fell on the floor!")
            # self.send_log_to_frontend("ERROR enc1 dome just collapsed.")
            #  Consider inhibity unless status rate is low
        uri_status = f"https://status.photonranch.org/status/{self.name}/status/"
        # NB None of the strings can be empty.  Otherwise this put faults.
        try:    # 20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
            #print("AWS uri:  ", uri)
            #print('Status to be sent:  \n', status, '\n')
            payload ={
                "statusType": "wxEncStatus",
                "status":  status
                }
            data = json.dumps(payload)
            response = requests.post(uri_status, data=data)
            #self.api.authenticated_request("PUT", uri_status, status)   # response = is not  used
            #print("AWS Response:  ",response)
            self.time_last_status = time.time()
            self.redis_server.set('wema_heart_time', self.time_last_status, ex=120)
        except:
            print('self.api.authenticated_request("PUT", uri, status):   Failed!')


    def update(self):
        """

        20200411 WER
        This compact little function is the heart of the code in the sense this is repeatedly
        called.  It first SENDS status for all devices to AWS.

        """
        self.update_status()
        time.sleep(2)
        try:
            self.scan_requests('mount1')   #NBNBNB THis has faulted, usually empty input lists.
        except:
            pass
            #print("self.scan_requests('mount1') threw an exception, probably empty input queues.")
        #g_dev['seq'].manager()  #  Go see if there is something new to do.

    def run(self):   # run is a poor name for this function.
        try:
            # self.update_thread = threading.Thread(target=self.update_status).start()
            # Each mount operates async and has its own command queue to scan.
            # is it better to use just one command queue per site?
            # for mount in self.all_devices['mount'].keys():
            #     self.scan_thre/ad = threading.Thread(
            #         target=self.scan_requests,
            #         args=(mount,)
            #     ).start()
            # Keep the main thread alive, otherwise signals are ignored
            while True:
                self.update()
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return


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

    import config
    

    o = Observatory(config.site_name, config.site_config)
    
    o.run()
