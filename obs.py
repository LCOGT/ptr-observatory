
# obs.py
# concurrency via threading


"""
IMPORTANT TODOs:
    
This body of code needs to be refactored, particularly the camera module which is too convoluted.

Flash calibrate from LNG  - Hot and cold pixel repair

Gather screen flats   #For these ideally we need to figure out when screen saturates, then develop a curve which
linearizes the screen -- and adu/bright for each filter.  Screen bright is the independent variable.  What we want
is the longest possible exposure to get to some exposure level, to minimize shutter effects, then gather 2E7 electrons.

Shutter compensation?


Autofocus

Gather Sky Flats  First need to set up to track SkyFlat spot from approx time where exposures can start through the
finish, avoiding a zenith event.    However a zenith event really does not affect things very much.  We have the field
roation issue to contend with though.   A different problem is exposure calculation.  In principle we should be able to predict
sky bright at midpoint of upcoming exposure since the transformation is only moderately quadratic.  So what we need is 
adu/lux for each filter.


Events
Map Hz to sky mags
Read IR cam values
Source Lists
Astro Solves, EN pointer
Self guiding 
Time to complete, Estimated time to complete.
Dome management
Enclosure light management   
Robust start up of devices.
ASCOM camera not Maxim.
Event/Calendar
ACP Operation
Throttle traffic when closed, Sun up
Screen support    
Enqueue specific device commands and then dispatch them when device is not busy.


NBNBNB Possibly a better way to build this is use Remote ascom to interface to each device. 1st that permits multiple
control computers.  2nd it isolates the devices while the code is being debugged.  This mostly seems to affect
MaximDL and filter wheel interactions.
    
    
"""

import time, json, sys, threading, queue     #17 to 1 Brightness

from api_calls import API_calls
import ptr_events
import api_calls
import requests
import config_east as config
import os

# import device classes
from devices.camera import Camera
from devices.camera_maxim import MaximCamera
from devices.enclosure import Enclosure 
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
from devices.mount import Mount
from devices.telescope import Telescope
from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
from devices.switch import Switch
from devices.screen import Screen
from devices.sequencer import Sequencer
from global_yard import g_dev
import ptr_bz2
import httplib2


#A monkey patch to speed up outgoing large files.   Does this help?

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

    time_between_status_update = 5 #seconds
    time_between_command_check = 3

#    device_types = [
#        'observing_conditions',
#        'enclosure',
#        'mount',
#        'telescope',
#        'rotator',
#        'focuser', 
#        'filter_wheel',
#        'camera',
#        'switch'
#
#    ]

    def __init__(self, name, config): 

        # This is the class through which we can make authenticated api calls.
        self.api = API_calls()

        # The site name (str) and configuration (dict) are given by the user. 
        self.name = name
        self.config = config
        self.update_config()
        self.device_types =[
        'observing_conditions',
#        'enclosure',
        'mount',
        'telescope',
        'rotator',
        'focuser',
#        'screen',
        'camera',
        'sequencer',
        'filter_wheel']
        
        # Use the configuration to instantiate objects for all devices.
        self.create_devices(config)

        # Run observatory loops as long as the `stopped` is not set to True.
        self.stopped = False
        self.cycles = 1000000
        self.loud_status = False
        g_dev['obs'] = self
        self.g_dev = g_dev
        #Build the to-AWS Queue
        self.aws_queue = queue.PriorityQueue()
        self.aws_queue_thread = threading.Thread(target=self.send_to_AWS, args=())
        self.aws_queue_thread.start()

        #self.run()

    def create_devices(self, config: dict):

        # This dict will store all created devices, subcategorized by dev_type.
        self.all_devices = {} 

        # Create device objects by type, going through the config by type.
        for dev_type in self.device_types:

            self.all_devices[dev_type] = {}

            # Get the names of all the devices from each dev_type.
            devices_of_type = config.get(dev_type, {})
            
            device_names = devices_of_type.keys()
            #print(devices_of_type, device_names)

            # Instantiate each device object from based on its type
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                settings = devices_of_type[name].get("settings", {})
                #print('looking for dev-types:  ', dev_type)
                if dev_type == "observing_conditions":
                    device = ObservingConditions(driver, name)
#                elif dev_type == "enclosure":
#                    print("enc:  ", driver, name)
#                    device = Enclosure(driver, name)
                elif dev_type == "mount":
                    device = Mount(driver, name, settings, tel=False)
                elif dev_type == "telescope":
                    device = Telescope(driver, name, settings, tel=True)
                elif dev_type == "focuser":
                    device = Focuser(driver, name, self.config)
                elif dev_type == "rotator":
                    device = Rotator(driver, name)
#                elif dev_type == "screen":
#                    device = Screen('EastAlnitak', 'COM22')
                elif dev_type == "camera":                      
                    device = Camera(driver, name, self.config)   #APPARENTLY THIS NEEDS TO BE STARTED PRIOR TO FILTER WHEEL!!!
                    time.sleep(2)
                elif dev_type == "sequencer":
                     device = Sequencer(driver, name)
                elif dev_type == "filter_wheel":
                     #pass
                     #device = FilterWheel(driver, name, self.config)
                     print('Filter wheel bypassed')

                #elif dev_type == "camera_maxim":                    
                #device = MaximCamera(driver, name)
                else:
                    print(f"Unknown device: {name}")

                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device
        #print(g_dev)
        print("Device creation finished.", )
        
    def update_config(self):
        ''' Send the config to aws. Used in UI creation too. '''
            
        print("Sending updated site configuration...")
        uri = f"{self.name}/config/"
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("Config uploaded successfully.")
            print(response)

    def scan_requests(self, mount):

        # Loop forever unless stopped 
        #kwhile not self.stopped:
            #time.sleep(self.time_between_command_check)
            #start = time.time()
        uri = f"{self.name}/{mount}/command/"
        try:
            
            cmd = json.loads(self.api.authenticated_request("GET", uri))   #This needs work
        except:
            cmd = {'Body': 'empty'}
            print('self.api.authenticated_request("GET", uri)  -- FAILED')

        if cmd == {'Body': 'empty'}:
            #print('Command Queue: ', cmd)
            return  #Nothing to do, co command in the FIFO
            # If a non-empty command arrives, it will print to the terminal.
            print(cmd)

        cmd_instance = cmd['instance']
        device_name = cmd['device']

        #Get the device based on it's type and name, then parse the cmd.
        print(device_name, cmd_instance)
        device = self.all_devices[device_name][cmd_instance]
        device.parse_command(cmd)

            #print(f"{mount} finished scan in {time.time()-start:.2f} seconds")

    def update_status(self):
        ''' Collect status from all devics and send an update to aws.

        Each device class is responsible for implementing the method 
        `get_status` which returns a dictionary. 
        '''
#
#        while not self.stopped:

            # Only send an update every few seconds.
            #time.sleep(self.time_between_status_update)

        start = time.time()

            ### Get status of all devices
            ###

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
#                if dev_type == "camera":
#                    continue
            for device_name in device_names:
                # Get the actual device object...
                if device_name =='filter_wheel' or device_name == 'filter_wheel1':
#                    continue
                    pass
                device = devices_of_type[device_name]
                # ...and add it to main status dict.
                status[dev_type][device_name] = device.get_status()
        
        # Include the time that the status was assembled and sent.
        status["timestamp"] = str(round((time.time() + start)/2. , 3))

        ### Put this status online
        ###bbbb
     
        if self.loud_status:
            print('Status Sent:  \n', status)#from Update:  ', status))
        else:
            print('.')#Status Sent:  \n', status)#from Update:  ', status)

        uri = f"{self.name}/status/"
        #NBNBNB None of the strings can be empty.  Otherwise this put faults.
        try:    #20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
            response = self.api.authenticated_request("PUT", uri, status)
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
#     is parsed and dispatched.          
# =============================================================================
    
    def run(self, n_cycles=None, loud=False):
        self.loud_status = loud
        if n_cycles is not None:
            self.cycles = n_cycles
        try:
            while self.cycles >= 0:
                self.update()

#                g_dev['enc'].manager()
                time.sleep(2)
                self.cycles -= 1
                #print('.')
        
        
#        ''' Continuously scan for commands and send status updates.
#
#        Scanning and updating are run in independent threads.
#        The run loop can be terminated by sending a KeyboardInterrupt signal.
#        '''
#        try:
#            self.update_thread = threading.Thread(target=self.update_status).start()
#
#            # Each mount operates async and has its own command queue to scan.
#            # TODO: is it better to use just one command queue per site? 
#            for mount in self.all_devices['mount'].keys():
#                self.scan_thread = threading.Thread(
#                    target=self.scan_requests, 
#                    args=(mount,)
#                ).start()
#
#            # Keep the main thread alive, otherwise signals are ignored
#            while True:
#                time.sleep(0.5)
#
        # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = False 
            self.cycles = 1000000
            return
        
    def send_to_AWS(self):  #pri_image is a tuple, smaller first item has priority. second item is also
                                       #A tuple containing im_path and name.    
        while True:
            
            if not self.aws_queue.empty():
                
                pri_image = self.aws_queue.get(block=False)
                if pri_image is None:
                    time.sleep(0.4)
                    
                    continue
                #Here we parse the item, set up and send to AWS
                #print('sendToAWS:  ', pri_image)
                
                im_path = pri_image[1][0]
                name = pri_image[1][1]
                if not (name[-3:] == 'jpg' or name[-3:] == 'txt'):
                    #compress first
                    ptr_bz2.to_bz2(im_path + name)
                    name = name + '.bz2'
                aws_req = {"object_name": "raw_data/2019/" + name}
                site_str = config.site_config['site']
                aws_resp = g_dev['obs'].api.authenticated_request('GET', site_str +'/upload/', aws_req)
        
                with open(im_path + name , 'rb') as f:
                    files = {'file': (im_path + name, f)}
                    print('.>', str(im_path + name))
                    start_send = time.time()
                    #print('\n\n\nStart send at:  ', start_send, '\n\n\n')
                    http_response = requests.post(aws_resp['url'], data=aws_resp['fields'], files=files)
                    print("\n\nhttp_response:  ", http_response, '\n\n')
                if name[-3:] == 'bz2' or name[-3:] == 'jpg' or name[-3:] =='txt':
                    #os.remove(im_path + name)   #We do not need to keep 
                    pass
                    #print('Deleting:  ', im_path + name)
                self.aws_queue.task_done()
                #print('\n*****AWS Transfer completed in:  ', int(time.time() - start_send), ' sec.  *****\n')
                time.sleep(0.2)
            else:
                time.sleep(0.4)
                continue
        



if __name__ == "__main__":

    from config_east import site_config, site_name
    day_str = ptr_events.compute_day_directory()
    #breakpoint()
    g_dev['day'] = day_str
    next_day = ptr_events.Day_tomorrow
    g_dev['d-a-y'] = day_str[0:4] + '-' + day_str[4:6] +  '-' + day_str[6:]
    g_dev['next_day'] = next_day[0:4] + '-' + next_day[4:6] +  '-' + next_day[6:]
    print('Next Day is:  ', g_dev['next_day'])

    #patch_httplib
    print('\nNow is:  ', ptr_events.ephem.now(), g_dev['d-a-y'])   #Add local Sidereal time at Midnight
    try:
         os.remove('Q:\\archive\\' + 'gf06'+ '\\newest.fits')
    except:
        print("Newest.fits not removed, catuion.")
    o = Observatory(site_name, site_config)
    print(o.all_devices)
    o.run(n_cycles=100000, loud=False)

