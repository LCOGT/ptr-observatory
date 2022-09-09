
"""
WER 20210624

First attempt at having a parallel dedicated agent for weather and enclosure.
This code should be as simple and reliable as possible, no hanging variables, 
etc.

This would be a good place to log the weather data and any enclosure history,
once this code is stable enough to run as a service.

We need to resolve the 'redis' solution for each site. 20120826

Note this is derived from OBS but is WEMA so we shoudl not need to build
things from a config file, but rather by implicatin just pick the correct
data from the config file.  All config files for a cluster of mounts/teleescops
under one WEMA should start with common data for the WEMA.  Not the wema
has no knowledge of how many mnt/tels there may be in any given enclosure.
"""


import json
import redis
import requests
import time
import shelve
import socket
from api_calls import API_calls
import ptr_events
from devices.observing_conditions import ObservingConditions
from devices.enclosure import Enclosure
from pprint import pprint

from global_yard import g_dev


import os, signal, subprocess


               
def terminate_restart_observer(site_path, no_restart=False):
    if no_restart is False or  True:
        return
    else:
        camShelf = shelve.open(site_path + 'ptr_night_shelf/' + 'pid_obs')
        #camShelf['pid_obs'] = self.obs_pid
        #camShelf['pid_time'] = time.time()
        pid = camShelf['pid_obs']     # a 9 character string
        camShelf.close()
        
        try:
            print("Terminating:  ", pid)
            os.kill(pid, signal.SIGTERM)
        except:
            print("No observer process was found, starting a new one.")

        #subprocess.call('C:/Users/obs/Documents/GitHub/ptr-observatory/restart_obs.bat')
        #The above routine does not return but does start a process.
        os.system('cmd /c C:\\Users\\obs\\Documents\\GitHub\\ptr-observatory\\restart_obs.bat')
        #  worked with /k, try /c Which should terminate
        return
    
#  NB NB For now a different class, so max code is eliminated, but ideally
#  this should be a strict subset of the observer's code NB NB note we can eventually fold this back into obs.
    
def send_status(obsy, column, status_to_send):
    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # NB None of the strings can be empty.  Otherwise this put faults.
    try:    # 20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
        #print("AWS uri:  ", uri)
        #print('Status to be sent:  \n', status, '\n')
        payload ={
            "statusType": str(column),
            "status":  status_to_send
            }
        #print("Payload:  ", payload)
        data = json.dumps(payload)
        response = requests.post(uri_status, data=data)
        #self.api.authenticated_request("PUT", uri_status, status)   # response = is not  used
        #print("AWS Response:  ",response)
        # NB should qualify acceptance and type '.' at that point.

    except:
        print('self.api.authenticated_request("PUT", uri, status):   Failed!')
        
class WxEncAgent:

    def __init__(self, name, config):

        self.api = API_calls()

        self.command_interval = 5   #Not relevent for SAF... No commads to Wx are sent by AWS.
        self.status_interval = 5
        self.name = name
        self.site_name = name
        self.config = config
        g_dev['obs'] = self     # NB NB We need to work through site vs mnt/tel
                                # and sub-site distinction.distinction.

        self.site = config['site']

        if self.config['wema_is_active']:
            self.hostname = self.hostname = socket.gethostname()
            if self.hostname in self.config['wema_hostname']:
                self.is_wema = True
                g_dev['wema_write_share_path'] = config['wema_write_share_path']
                self.wema_path = g_dev['wema_write_share_path']
                self.site_path = self.wema_path
            else:  
                #This host is a client
                self.is_wema = False  #This is a client.
                self.site_path = config['client_write_share_path']
                g_dev['site_path'] = self.site_path
                g_dev['wema_write_share_path']  = self.site_path  # Just to be safe.
                self.wema_path = g_dev['wema_write_share_path'] 
        else:
            self.is_wema = False  #This is a client.
            self.site_path = config['client_write_share_path']
            g_dev['site_path'] = self.site_path
            g_dev['wema_write_share_path']  = self.site_path  # Just to be safe.
            self.wema_path = g_dev['wema_write_share_path'] 
        if self.config['site_is_specific']:
             self.site_is_specific = True
        else:
            self.site_is_specific = False
            

        self.last_request = None
        self.stopped = False
        self.site_message = '-'
        self.site_mode = config['site_in_automatic_default']
        self.device_types = config['wema_types']
        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.display_events()

        self.wema_pid = os.getpid()
        print('WEMA_PID:  ', self.wema_pid)

        if config['redis_ip'] is not None:           
            self.redis_server = redis.StrictRedis(host=config['redis_ip'], port=6379, db=0, decode_responses=True)
            self.redis_wx_enabled = True
            g_dev['redis'] = self.redis_server  #Enable wide easy access to this object.
            for key in self.redis_server.keys():
                self.redis_server.delete(key)   #Flush old state.
            self.redis_server.set('wema_pid', self.wema_pid)
        else:
            self.redis_wx_enabled = False
            g_dev['redis'] = None
        ##  g_dev['redis_server']['wema_loaded'] = True

        
        # #Here we clean up any older processes
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
        print('Fresh WEMA_PID:  ', self.wema_pid)
        #self.redis_server.set('wema_pid', self.wema_pid)

        #Redundant store of wema_pid
        camShelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'pid_wema')
        camShelf['pid_wema'] = self.wema_pid
        camShelf['pid_time'] = time.time()
        #pid = camShelf['pid_obs']      # a 9 character string
        camShelf.close()
        self.update_config()
        self.create_devices(config)
        self.time_last_status = time.time()
        self.loud_status = False
        self.blocks = None
        self.projects = None
        self.events_new = None
        immed_time = time.time()
        self.obs_time = immed_time
        self.wema_start_time = immed_time
        #self.redis_server.set('obs_time', immed_time, ex=360)


        #subprocess.call('obs.py')  This is clearly wrong.
        #time.sleep(5)

        #print("Starting observer, may have to terminate a stale observer first.")

        #terminate_restart_observer(g_dev['obs']['site_path'], no_restart=True)
       
    



        
        
    def create_devices(self, config: dict):
        self.all_devices = {}
        for dev_type in self.device_types:  #This has been set up for wema to be ocn and enc.
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
        breakpoint()
        if response:
            print(self.config, "\n\nConfig uploaded successfully.")

    def scan_requests(self, mount):
        return
        '''
        
        For a wema this can be used to capture commands to the wema once the
        AWS side knows how to redirect from any mount/telescope to the common
        Wema.
        This should be changed to look into the site command que to pick up
        any commands directed at the Wx station, or if the agent is going to 
        always exist lets develop a seperate command queue for it.
        '''

    def update_status(self):
        ''' Collect status from weather and enclosure devices and send an 
        update to aws,  Each device class is responsible for implementing the 
        method 'get_status()' which returns a dictionary.
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
                #print(device)
                status[dev_type][device_name] = device.get_status()
        # Include the time that the status was assembled and sent.
        status["timestamp"] = round((time.time() + t1)/2., 3)
        status['send_heartbeat'] = False
        enc_status = None
        ocn_status = None
        device_status = None
        try:
            ocn_status = {'observing_conditions': status.pop('observing_conditions')}
            enc_status = {'enclosure':  status.pop('enclosure')}
            device_status = status
        except:
            pass

        obsy = self.name
        if ocn_status is not None:
            lane = 'weather'
            send_status(obsy, lane, ocn_status)  #NB NB Do not remove this sed for SAF!
        if enc_status is not None:
            lane = 'enclosure'
            send_status(obsy, lane, enc_status)
        if  device_status is not None:
            lane = 'device'
            final_send  = status
            send_status(obsy, lane, device_status)
        loud = False
        if loud:
            print('\n\n > Status Sent:  \n', status)
        else:
            try:
                obs_time = float(self.redis_server.get('obs_time'))
                #print("Obs time received:  ", obs_time)
                delta= time.time() - obs_time
            except:
                delta= 999.99  #"NB NB NB Temporily flags someing really wrong."
            if delta > 1800:
                print(">The observer's time is stale > 300 seconds:  ", round(delta, 2))
                #Here is where we terminate the obs.exe and restart it.
            if delta > 3600:
                #terminate_restart_observer(g_dev['obs'}['site_path'], no_restart=True)
                pass

            else:
                print('>')

        # except:
        #     print('self.api.authenticated_request "PUT":  Failed!')

    def update(self):

        self.update_status()
        time.sleep(1)

    def run(self):   # run is a poor name for this function.
        try:
           while True:
                self.update()
                # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return
        
    def send_to_user(self, p_log, p_level='INFO'):
        url_log = "https://logs.photonranch.org/logs/newlog"
        body = json.dumps({
            'site': self.config['site'],
            'log_message':  str(p_log),
            'log_level': str(p_level),
            'timestamp':  time.time()
            })
        try:
            resp = requests.post(url_log, body)
        except:
            print("Log did not send, usually not fatal.")
if __name__ == "__main__":

    import config
    wema = WxEncAgent(config.site_name, config.site_config)
    
    wema.run()
