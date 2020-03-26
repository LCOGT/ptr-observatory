
"""
WER 20200307

IMPORTANT TODOs:
    
Figure out how to fix jams with Maxium. Debug interrupts can cause it to disconnect.

Test all this code with ASCOM simulators as the instruments so we have a stable reference
to start from.

Remove WMD specifics, and add constructors for shelved objects.

THINGS TO FIX:
    20200316
    filter wheel code is broken  -blocked until FLI gets us new library.
    fully test flash calibration
    genereate local masters
    create and send sources file created by sep
    verify operation with FLI16200 camera
    Get Neyle a webcam we will be happy to reccommend
    screen flats
    autofocus, and with grid of known stars
    sky flats
    much better weather station approach
    
    
      
"""

import time,  threading, queue
import requests
import os
import argparse
import json

from api_calls import API_calls
#import ptr_events

# NB: The main config file should be named simply 'config.py'. 
# Specific site configs should not be tracked in version control. 
# Recommended practices: https://stackoverflow.com/questions/4743770/how-to-manage-configuration-files-when-collaborating
import config_east as config    
import config_simulator as config_simulator

# import device classes
from devices.camera import Camera
from devices.enclosure import Enclosure 
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
from devices.mount import Mount
from devices.telescope import Telescope
from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
#from devices.switch import Switch    #Nothing implemneted yet 20200307
from devices.screen import Screen
from devices.sequencer import Sequencer
from global_yard import g_dev
import ptr_bz2
import httplib2

last_req = None

#The following function is a monkey patch to speed up outgoing large files.   Does this help?  Does not appear to be used.

def patch_httplib(bsize=400000):
    """ Update httplib block size for faster upload (Default if bsize=None) """
    if bsize is None:
        bsize = 8192
    def send(self, data, sblocks=bsize):
        """Send `data' to the server."""
        if self.sock is None:
            if self.auto_open:
                self.connect()
            else:
                raise httplib2.NotConnected()
        if self.debuglevel > 0:
            print( "send:", repr(data))
        if hasattr(data, 'read') and not isinstance(data, list):
            if self.debuglevel > 0: print( "sendIng a read()able")
            datablock = data.read(sblocks)
            while datablock:
                self.sock.sendall(datablock)
                datablock = data.read(sblocks)
        else:
            self.sock.sendall(data)
    httplib2.httplib.HTTPConnection.send = send

class Observatory:
    def __init__(self, name, config): 

        # This is the class through which we can make authenticated api calls.
        self.api = API_calls()

        self.command_interval = 2 # seconds between polls for new commands
        self.status_interval  = 2 # seconds between sending status to aws

        # The site name (str) and configuration (dict) are given by the user. 
        self.name = name
        self.config = config
        self.update_config()
        
        self.device_types = [
            'observing_conditions',
            'enclosure',     #Commented out so enclosure does not usually open automatically.  Also it breaks configuation.
            'mount',
            'telescope',
            'rotator',
            'focuser',
            'screen',
            'camera',
            'sequencer',
            'filter_wheel'
            ]
        # Use the configuration to instantiate objects for all devices.
        self.create_devices(config)
        self.stopped = False
        self.cycles = 1000000
        self.loud_status = False
        g_dev['obs'] = self
        self.g_dev = g_dev
        #Build the to-AWS Queue and start a thread. Note we ned a status scan thread, and probably a flash-reduce THread
        #or multiprocess style thread.
        self.aws_queue = queue.PriorityQueue()
        self.aws_queue_thread = threading.Thread(target=self.send_to_AWS, args=())
        self.aws_queue_thread.start()

    def create_devices(self, config: dict):
        # This dict will store all created devices, subcategorized by dev_type.
        self.all_devices = {} 
        # Create device objects by type, going through the config by type.
        for dev_type in self.device_types:
            self.all_devices[dev_type] = {}
            # Get the names of all the devices from each dev_type.
            devices_of_type = config.get(dev_type, {})            
            device_names = devices_of_type.keys()
            # Instantiate each device object from based on its type
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                settings = devices_of_type[name].get("settings", {})
                #print('looking for dev-types:  ', dev_type)
                if dev_type == "observing_conditions":
                    device = ObservingConditions(driver, name)
                elif dev_type == 'enclosure':
                    device = Enclosure(driver, name)
                elif dev_type == "mount":
                    device = Mount(driver, name, settings, tel=False)
                elif dev_type == "telescope":   #order of attaching is sensitive
                    device = Telescope(driver, name, settings, tel=True)
                elif dev_type == "rotator":
                    device = Rotator(driver, name)
                elif dev_type == "focuser":
                    device = Focuser(driver, name, self.config)
                elif dev_type == "screen":
                    device = Screen('EastAlnitak', 'COM6')
                elif dev_type == "camera":                      
                    device = Camera(driver, name, self.config)   #APPARENTLY THIS NEEDS TO BE STARTED PRIOR TO FILTER WHEEL!!!
                elif dev_type == "sequencer":
                    device = Sequencer(driver, name)
                elif dev_type == "filter_wheel":
                    device = FilterWheel(driver, name, self.config)
                else:
                    print(f"Unknown device: {name}")
                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device

        
    def update_config(self):
        ''' Send the config to aws. '''
        uri = f"{self.name}/config/"
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("Config uploaded successfully.")

    def scan_requests(self, mount):
        global last_req             #Intended as a debug aid, may be obsolete
        '''
        This can be improved by looking for a Cancel/Stop from
        AWS and even better, queuing commands to different devices
        and explicitly handling their individual busy states.
        
        I.e., a single command queue can be limiting
        '''

        # This stopping mechanism allows for threads to close cleanly.
        while not self.stopped:

            # Wait a bit before polling for new commands
            time.sleep(self.command_interval)

            if not  g_dev['seq'].sequencer_hold:   
                url = f"https://jobs.photonranch.org/jobs/getnewjobs"
                body = {"site": self.name}
                #uri = f"{self.name}/{mount}/command/"
                cmd = {}

                unread_commands = requests.request('POST', url, data=json.dumps(body)).json()
                for cmd in unread_commands:
                    print(cmd)

                    deviceInstance = cmd['deviceInstance']
                    deviceType = cmd['deviceType']
                    device = self.all_devices[deviceType][deviceInstance]
                    try: 
                        device.parse_command(cmd)
                    except Exception as e:
                        print(e)
                continue
            else:
                print('Sequencer Hold asserted.')    #What we really want here is looking for a Cancel/Stop.
                continue

    def update_status(self):
        ''' Collect status from all devics and send an update to aws.
        Each device class is responsible for implementing the method 
        `get_status` which returns a dictionary. 
        '''

        # This stopping mechanism allows for threads to close cleanly.
        while not self.stopped:

            # Wait a bit between status updates
            time.sleep(self.status_interval)

            start = time.time()
            status = {}

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
                    if device_name =='filter_wheel' or device_name == 'filter_wheel1':
                        pass
                    device = devices_of_type[device_name]
                    # ...and add it to main status dict.
                    status[dev_type][device_name] = device.get_status()        
            # Include the time that the status was assembled and sent.
            status["timestamp"] = str(round((time.time() + start)/2. , 3))
            status['send_heartbeat'] = 'false'
            if self.loud_status:
                print('Status Sent:  \n', status)#from Update:  ', status))
            else:
                print('.')#   #We print this to stay infomred of process on the console.
            uri = f"{self.name}/status/"
            #NBNBNB None of the strings can be empty.  Otherwise this put faults.
            try:    #20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
                self.api.authenticated_request("PUT", uri, status)   #response = is not  used
            except:
                print('self.api.authenticated_request("PUT", uri, status):   Failed!')
            #print(f"update finished in {time.time()-start:.2f} seconds", response)
            
    def update(self):
        self.scan_requests('mount1')
        if not self.stopped:
            self.update_status()
    
# =============================================================================
#     This thread is basically the sequencer.  When a device, such as a camera causes a block, it is the responsibility of 
#     that device to call self.update on a regular basis so AWS can receive status and to monitor is AWS is sending other 
#     commands or a STOP.
#            
#     Seeks, rotations and exposures are the typical example of observing related delays.
#          
#     We will follow the convention that a command is in the form of a dictionary and the first entry is a command type.
#     These command dictionaries can be nested to an arbitrary level and this thread is the master point where the command
#     is parsed and dispatched.   This wqas changed early from Tim;s original design becuase of conflicts with some ASCOM
#     instances.   My comment above about having status be its own thread refers to this area of the code.  WER 20200307
# =============================================================================
    
    def run(self, n_cycles=None, loud=False):   #run is a poor name for this function.
        self.loud_status = loud
        if n_cycles is not None:
            self.cycles = n_cycles
        try:
            #while self.cycles >= 0:
                #self.update()
##                g_dev['enc'].manager()
                #time.sleep(1)
                #self.cycles -= 1

            self.update_thread = threading.Thread(target=self.update_status).start()

            # Each mount operates async and has its own command queue to scan.
            # TODO: is it better to use just one command queue per site? 
            for mount in self.all_devices['mount'].keys():
                self.scan_thread = threading.Thread(
                    target=self.scan_requests, 
                    args=(mount,)
                ).start()

            # Keep the main thread alive, otherwise signals are ignored
            while True:
                time.sleep(1)


        # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            #self.cycles = 1000000
            return
        
    #Note this is a thread!       
    def send_to_AWS(self):  #pri_image is a tuple, smaller first item has priority. second item is alsa tuple containing 
                            #im_path and name.    

        # This stopping mechanism allows for threads to close cleanly.
        while not self.stopped:            
            if not self.aws_queue.empty(): 
                pri_image = self.aws_queue.get(block=False)
                if pri_image is None:
                    time.sleep(0.2)
                    continue
                #Here we parse the file, set up and send to AWS                
                im_path = pri_image[1][0]
                name = pri_image[1][1]
                if not (name[-3:] == 'jpg' or name[-3:] == 'txt'):
                    #compress first
                    ptr_bz2.to_bz2(im_path + name)
                    name = name + '.bz2'
                aws_req = {"object_name": "raw_data/2019/" + name}
                site_str = config.site_config['site']
                aws_resp = g_dev['obs'].api.authenticated_request('POST', site_str +'/upload/', aws_req)       
                with open(im_path + name , 'rb') as f:
                    files = {'file': (im_path + name, f)}
                    print('--> To AWS -->', str(im_path + name))
                    requests.post(aws_resp['url'], data=aws_resp['fields'], files=files)  #http_response =   was never used.
                if name[-3:] == 'bz2' or name[-3:] == 'jpg' or name[-3:] =='txt':
                    #os.remove(im_path + name)   #We do not need to keep locally
                    pass
                self.aws_queue.task_done()
                time.sleep(0.1)
            else:
                time.sleep(0.2)
                continue
def run_wmd():
    '''
    Construct the environment if it has not already been established. E.g shelve spaces.
    This is specific to site WMD and should be used for testing purpose only.
    '''
    #This is a bit of ugliness occcasioned by bad file naming in the FLI Kepler driver. 
    day_str = ptr_events.compute_day_directory()
    g_dev['day'] = day_str
    next_day = ptr_events.Day_tomorrow
    g_dev['d-a-y'] = day_str[0:4] + '-' + day_str[4:6] +  '-' + day_str[6:]
    g_dev['next_day'] = next_day[0:4] + '-' + next_day[4:6] +  '-' + next_day[6:]
    print('\nNext Day is:  ', g_dev['next_day'])
    print('Now is:  ', ptr_events.ephem.now(), g_dev['d-a-y'])   #Add local Sidereal time at Midnight
    patch_httplib
# =============================================================================
#     #This is specific to a camera and should be in camera __init.
# =============================================================================
    try:
        os.remove('Q:\\archive\\' + 'df01'+ '\\newest.fits')
    except:
        print("newest file not removed.")

    o = Observatory(config.site_name,config. site_config)
    print('\n', o.all_devices)
    o.run(n_cycles=100000, loud=False)

def run_simulator():
    conf = config_simulator
    o = Observatory(conf.site_name, conf.site_config)
    o.run()

            
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()

    # command line arg to use simulated ascom devices
    parser.add_argument('-sim', action='store_true')
    options = parser.parse_args()

    if options.sim:
        print('Starting up with ASCOM simulators.')
        run_simulator()
    else:
        print('Starting up default configuration file.')
        run_wmd()


    
    

