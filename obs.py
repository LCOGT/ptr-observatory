
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
import os, sys
import argparse
import json

from api_calls import API_calls
import ptr_events

# NB: The main config file should be named simply 'config.py'.
# Specific site configs should not be tracked in version control.
import config_saf as config
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
import bz2
import httplib2



def to_bz2(filename, delete=False):
    try:
        uncomp = open(filename, 'rb')
        comp = bz2.compress(uncomp.read())
        uncomp.close()
        if delete:
            os.remove(filename)
        target = open(filename +'.bz2', 'wb')
        target.write(comp)
        target.close()
        return True
    except:
        print('to_bz2 failed.')
        return False

def from_bz2(filename, delete=False):
    try:
        comp = open(filename, 'rb')
        uncomp = bz2.decompress(comp.read())
        comp.close()
        if delete:
            os.remove(filename)
        target=open(filename[0:-4], 'wb')
        target.write(uncomp)
        target.close()
        return True
    except:
        print('from_bz2 failed.')
        return False

#The following function is a monkey patch to speed up outgoing large files.
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
        self.status_interval  = 2 # seconds between sending status to aws  #nOTE THESE IMPLENTED AS A DELA NOT A RATE.

        # The site name (str) and configuration (dict) are given by the user.
        self.name = name
        self.config = config
        self.update_config()
        self.last_request = None
        self.stopped = False
        self.device_types = [
            'observing_conditions',
            'enclosure',
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
        self.loud_status = False
        g_dev['obs'] = self
        self.g_dev = g_dev
        self.time_last_status = time.time() - 3  #initializes for what will be a rate limiter
        #Build the to-AWS Queue and start a thread.
        self.aws_queue = queue.PriorityQueue()
        self.aws_queue_thread = threading.Thread(target=self.send_to_AWS, args=())
        self.aws_queue_thread.start()
        #Build the site (from-AWS) Queue and start a thread.
        # self.site_queue = queue.SimpleQueue()
        # self.site_queue_thread = threading.Thread(target=self.get_from_AWS, args=())
        # self.site_queue_thread.start()



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
                    device = ObservingConditions(driver, name, self.config)
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
                    device = Camera(driver, name, self.config)   #THIS NEEDS TO BE STARTED PRIOR TO FILTER WHEEL!!!
                elif dev_type == "sequencer":
                    device = Sequencer(driver, name)
                elif dev_type == "filter_wheel":
                    device = FilterWheel(driver, name, self.config)
                else:
                    print(f"Unknown device: {name}")
                # Add the instantiated device to the collection of all devices.
                self.all_devices[dev_type][name] = device


    def update_config(self):
        '''
        Send the config to aws.
        '''
        uri = f"{self.name}/config/"
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("Config uploaded successfully.")

    def scan_requests(self, mount):
        '''
        Outline of change 20200323 WER
        Get commands from AWS, and post a STOP/Cancel flag
        This function will be a Thread. we will limit the polling to once every 2.5 - 3 seconds because AWS does not
        appear to respond any faster.  When we do poll we parse the action keyword for 'stop' or 'cancel' and post the
        existence of the timestamp of that command to the respective device attribute   <self>.cancel_at.  Then we
        also enqueue the incoming command as well.

        when a device is status scanned, if .cancel_at is not None, the device takes appropriate action and sets
        cancel_at back to None.

        NB at this time we are preserving one command queue for all devices at a site.  This may need to change when we
        have parallel mountings or independently controlled cameras.
        '''


        # This stopping mechanism allows for threads to close cleanly.
        while not self.stopped:

            # Wait a bit before polling for new commands
            time.sleep(self.command_interval)
            t1 = time.time()
            if not  g_dev['seq'].sequencer_hold:
                url = f"https://jobs.photonranch.org/jobs/getnewjobs"
                body = {"site": self.name}
                #uri = f"{self.name}/{mount}/command/"
                cmd = {}

                # Get a list of new jobs to complete (this request marks the commands as "RECEIVED")
                unread_commands = requests.request('POST', url, data=json.dumps(body)).json()

                # Make sure the list is sorted in the order the jobs were issued
                # Note: the ulid for a job is a unique lexicographically-sortable id
                unread_commands.sort(key=lambda x: x["ulid"])

                # Process each job one at a time
                for cmd in unread_commands:
                    print(cmd)
                    deviceInstance = cmd['deviceInstance']
                    deviceType = cmd['deviceType']
                    device = self.all_devices[deviceType][deviceInstance]
                    try:
                        device.parse_command(cmd)
                    except Exception as e:
                        print(e)

               # print('scan_requests finished in:  ', round(time.time() - t1, 3), '  seconds')
                return   #Contine   #This creates an infinite loop
            else:
                print('Sequencer Hold asserted.')    #What we really want here is looking for a Cancel/Stop.
                continue


    def update_status(self):
        ''' Collect status from all devics and send an update to aws.
        Each device class is responsible for implementing the method
        `get_status` which returns a dictionary.
        '''

        # This stopping mechanism allows for threads to close cleanly.
        loud = False
        # Wait a bit between status updates
        while time.time() < self.time_last_status + self.status_interval:
            #time.sleep(self.st)atus_interval  #This was prior code
            #print("Staus send skipped.")
            return   #Note we are just not sending status, too soon.

        t1 = time.time()
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
        status["timestamp"] = str(round((time.time() + t1)/2. , 3))
        status['send_heartbeat'] = 'false'
        if loud:
            print('Status Sent:  \n', status)#from Update:  ', status))
        else:
            pass
            #print('.')#   #We print this to stay informed of process on the console.
        uri = f"{self.name}/status/"
        #NBNBNB None of the strings can be empty.  Otherwise this put faults.
        #if loud: print('pre-AWS phase of update_status took :  ', round(time.time() - t1, 9), sys.getsizeof(status))
        #NB is it possible we might want to gueue this phase of sending the status back? 20200322
        try:    #20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
            self.api.authenticated_request("PUT", uri, status)   #response = is not  used
            self.time_last_status = time.time()
        except:
            print('self.api.authenticated_request("PUT", uri, status):   Failed!')
        #if loud: print("update_status finished in:  ", round(time.time() - t1, 2), "  seconds")

    def update(self):
        #t2 = time.time()
        self.update_status()
        #print('update_status took :  ', round(time.time() - t2, 3))
        #t1 = time.time()
        self.scan_requests('mount1')
       #print('scan_requests took :  ', round(time.time() - t1, 3))


# =============================================================================
#     This thread is basically the sequencer.  When a device, such as a camera causes a block, it is the responsibility
#     of that device to call self.update on a regular basis so AWS can receive status and to monitor is AWS is sending
#     other commands or a STOP.
#
#     Seeks, rotations and exposures are the typical example of observing related delays.
#
#     We will follow the convention that a command is in the form of a dictionary and the first entry is a command
#     type.  These command dictionaries can be nested to an arbitrary level and this thread is the master point where
#     the command is parsed and dispatched.   This wqas changed early from Tim;s original design becuase of conflicts
#     with some ASCOM instances.   My comment above about having status be its own thread refers to this area of the
#     code.  WER 20200307
# =============================================================================

    def run(self):   #run is a poor name for this function.
        try:
            #self.update_thread = threading.Thread(target=self.update_status).start()
            # Each mount operates async and has its own command queue to scan.
            # TODO: is it better to use just one command queue per site?
            # for mount in self.all_devices['mount'].keys():
            #     self.scan_thread = threading.Thread(
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

    #Note this is a thread!
    def send_to_AWS(self):  #pri_image is a tuple, smaller first item has priority. second item is alsa tuple
                            #containing #im_path and name.

        # This stopping mechanism allows for threads to close cleanly.
        while True:
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
                    to_bz2(im_path + name)
                    name = name + '.bz2'
                aws_req = {"object_name": "raw_data/2019/" + name}
                site_str = config.site_config['site']
                aws_resp = g_dev['obs'].api.authenticated_request('POST', site_str +'/upload/', aws_req)
                with open(im_path + name , 'rb') as f:
                    files = {'file': (im_path + name, f)}
                    print('--> To AWS -->', str(im_path + name))
                    requests.post(aws_resp['url'], data=aws_resp['fields'], files=files)
                if name[-3:] == 'bz2' or name[-3:] == 'jpg' or name[-3:] =='txt':
                    #os.remove(im_path + name)   #We do not need to keep locally
                    pass
                self.aws_queue.task_done()
                time.sleep(0.1)
            else:
                time.sleep(0.2)
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


    o = Observatory(config.site_name, config.site_config)
    #print('\n', o.all_devices)
    o.run()

def run_simulator():
    conf = config_simulator
    o = Observatory(conf.site_name, conf.site_config)
    o.run()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    # command line arg to use simulated ascom devices
    parser.add_argument('-sim', action='store_true')
    options = parser.parse_args()
    options.sim = False

    if options.sim:
        print('Starting up with ASCOM simulators.')
        run_simulator()
    else:
        print('Starting up default configuration file.')
        run_wmd()





