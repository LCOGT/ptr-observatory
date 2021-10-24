
"""
WER 20210624

First attempt at having a parallel dedicated agent for weather and enclosure.
This code should be as simple and reliable as possible, no hanging variables, 
etc.

This would be a good place to log the weather data and any enclosure history,
once this code is stable enough to run as a service.

We need to resolve the 'redis' solution for each site. 20120826
"""


import json
import redis
import requests
import time

from api_calls import API_calls
import ptr_events
from devices.wms_enclosure_agent import Enclosure
from devices.wms_observing_agent import ObservingConditions
from global_yard import g_dev

class Observatory:

    def __init__(self, name, config):
        self.api = API_calls()
        self.command_interval = 3
        self.status_interval = 3
        self.name = name
        self.site_name = name
        self.config = config
        self.site_path = config['site_path']
        g_dev['obs'] = self 
        g_dev['site']=  config['site']
        self.last_request = None
        self.stopped = False
        self.site_message = '-'
        self.device_types = [
            'observing_conditions',
            'enclosure'] 
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.display_events()
        redis_ip = config['redis_ip']
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379,\
                                db=0, decode_responses=True)
            self.redis_wx_enabled = True
        else:
            self.redis_wx_enabled = False
        for key in self.redis_server.keys(): self.redis_server.delete(key)   #Flush old state.
        g_dev['redis_server'] = self.redis_server   #Use this instance.
        g_dev['redis_server']['wema_loaded'] = True
        self.update_config()
        self.create_devices(config)
        self.time_last_status = time.time()
        self.loud_status = False
        self.blocks = None
        self.projects = None
        self.events_new = None


        
        
    def create_devices(self, config: dict):
        self.all_devices = {}
        for dev_type in self.device_types:
            self.all_devices[dev_type] = {}
            devices_of_type = config.get(dev_type, {})
            device_names = devices_of_type.keys()
            if dev_type == 'camera':
                pass
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                #settings = devices_of_type[name].get("settings", {})

                if dev_type == "observing_conditions":
                    device = ObservingConditions(driver, name, self.config,\
                                                 self.astro_events)
                elif dev_type == 'enclosure':
                    device = Enclosure(driver, name, self.config,\
                                       self.astro_events)
                else:
                    print(f"Unknown device: {name}")
                self.all_devices[dev_type][name] = device
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
        This should be changed to look into the site command que to pick up
        any commands directed at the Wx station, or if the agent is going to 
        always exist lets develop a seperate command queue for it.
        '''

    def update_status(self):
        ''' Collect status from all devices and send an update to aws.
        Each device class is responsible for implementing the method
        `get_status` which returns a dictionary.
        '''
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
        status["timestamp"] = round((time.time() + t1)/2., 3)
        status['send_heartbeat'] = False
        loud = False
        if loud:
            print('\n\n > Status Sent:  \n', status)
        else:
            print('>', )
        uri_status = f"https://status.photonranch.org/status/{self.name}/status/"
        try:    # 20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
            payload ={
                "statusType": "wxEncStatus",
                "status":  status
                }
            data = json.dumps(payload)
            #print(data)
            requests.post(uri_status, data=data)
            self.redis_server.set('wema_heart_time', self.time_last_status, ex=120)
            if self.name in ['mrc', 'mrc1']:
                uri_status_2 = "https://status.photonranch.org/status/mrc2/status/"
                payload ={
                "statusType": "wxEncStatus",
                "status":  status
                }
                #data = json.dumps(payload)
                requests.post(uri_status_2, data=data)
            self.time_last_status = time.time()
        except:
            print('self.api.authenticated_request "PUT":  Failed!')

    def update(self):

        self.update_status()
        time.sleep(5)

    def run(self):   # run is a poor name for this function.
        try:
           while True:
                self.update()
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return

if __name__ == "__main__":

    import config
    o = Observatory(config.site_name, config.site_config)
    
    o.run()
