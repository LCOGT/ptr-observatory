
# obs.py
# concurrency via threading

import time, json, sys, threading

from api_calls import API_calls

# import device classes
from devices.camera import Camera
from devices.enclosure import Enclosure 
from devices.filter import Filter
from devices.focuser import Focuser
from devices.mount import Mount
from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
from devices.switch import Switch


class Observatory:

    time_between_status_update = 3 #seconds
    time_between_command_check = 3

    device_types = [ 
        'camera',
        'enclosure',
        'filter',
        'focuser', 
        'mount',
        'rotator',
        'switch',

    ]

    def __init__(self, name, config): 

        # This is the class through which we can make authenticated api calls.
        self.api = API_calls()

        # The site name (str) and configuration (dict) are given by the user. 
        self.name = name
        self.config = config
        self.update_config()

        # Use the configuration to instantiate objects for all devices.
        self.create_devices(config)

        # Run observatory loops as long as the `stopped` is not set to True.
        self.stopped = False
        self.run()

    def run(self):
        ''' Continuously scan for commands and send status updates.

        Scanning and updating are run in independent threads.
        The run loop can be terminated by sending a KeyboardInterrupt signal.
        '''
        try:
            self.scan_thread = threading.Thread(target=self.scan_requests).start()
            self.update_thread = threading.Thread(target=self.update_status).start()
            #self.update_config = threading.Thread(target=self.update_config).start()

            # Keep the main thread alive, otherwise signals are ignored
            while True:
                time.sleep(0.5)

        # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True 
            return

    def create_devices(self, config: dict):

        # This dict will store all created devices, subcategorized by type.
        self.all_devices = {} 

        # Create device objects by type, going through the config by type.
        for type in self.device_types:

            self.all_devices[type] = {}
            print(type)
            # Get the names of all the devices from each type.
            devices_of_type = config.get(type, {})
            device_names = devices_of_type.keys()

            # Instantiate each device object from based on its type
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                if type == "camera":
                    device = Camera(driver, name)
                elif type == "mount":
                    device = Mount(driver, name)
                elif type == "filter":
                    device = Filter(driver, name)
                elif type == "focuser":
                    device = Focuser(driver, name)
                elif type == "rotator":
                    device = Rotator(driver, name)
                else:
                    print(f"Unknown device: {name}")

                # Add the instantiated device to the collection of all devices.
                self.all_devices[type][name] = device

        print("Device creation finished.")
        
    def update_config(self):
        ''' Send the config to aws. Used in UI creation too. 

        NOTE: currently, the config must include:
                config["site"] = `site name`
                config["mounts"] = <list>
            This is due to code in the flask api, in the `sites.py` file
            during initializing aws resources from the config 
            (function init_from_config)
        '''
            
        print("Sending updated site configuration...")
        uri = f"{self.name}/config/"
        response = self.api.authenticated_request("PUT", uri, self.config)
        print(response)

    def scan_requests(self):

        # Loop forever unless stopped 
        while not self.stopped:
            time.sleep(self.time_between_command_check)
            start = time.time()
            uri = f"{self.name}/mount1/command/"
            cmd = json.loads(self.api.authenticated_request("GET", uri))

            if cmd == {'Body': 'empty'}:
                print(f"finished empty scan in {time.time()-start:.2f} seconds")
                continue

            # If a non-empty command arrives, it will print to the terminal.
            print(cmd)

            cmd_type = cmd['type']
            device_name = cmd['device']

            # Get the device based on it's type and name, then parse the cmd.
            device = self.all_devices[cmd_type][device_name]
            device.parse_command(cmd)

            print(f"scan finished in {time.time()-start:.2f} seconds")

    def update_status(self):
        ''' Collect status from all devics and send an update to aws.

        Each device class is responsible for implementing the method 
        `get_status` which returns a dictionary. 
        '''

        while not self.stopped:

            # Only send an update every few seconds.
            time.sleep(self.time_between_status_update)

            start = time.time()

            ### Get status of all devices
            ###

            status = {}

            # Loop through all types of devices.
            # For each type, we get and save the status of each device.
            for type in self.device_types:

                # The status that we will send is grouped into lists of 
                # devices by type.
                status[type] = {}
                
                # Names of all devices of the current type.
                # Recall that self.all_devices[type] is a dictionary of all 
                # `type` devices, with key=name and val=device object itself.
                devices_of_type = self.all_devices.get(type, {})
                device_names = devices_of_type.keys()

                for device_name in device_names:
                    # Get the actual device object...
                    device = devices_of_type[device_name]
                    # ...and add it to main status dict.
                    status[type][device_name] = device.get_status()
            
            # Include the time that the status was assembled and sent.
            status["timestamp"] = str(int(time.time()))

            ### Put this status online
            ###

            uri = f"{self.name}/status/"
            response = self.api.authenticated_request("PUT", uri, status)

            print(f"update finished in {time.time()-start:.2f} seconds")



if __name__=="__main__":

    simple_config = {
        "site": "sim_site",
        "mount": {
            "mount1": {
                "name": "mount1",
                "driver": 'ASCOM.Simulator.Telescope',
            },
        },
        "camera": {
            "cam1": {
                "name": "cam1",
                "driver": 'ASCOM.Simulator.Camera',
            },
            "cam2": {
                "name": "cam2",
                "driver": 'ASCOM.Simulator.Camera',
            },
        },
        "filter": {
            "filter1": {
                "name": "filter1",
                "driver": "ASCOM.Simulator.FilterWheel",
            }
        },
        "telescope": {
            "telescope1": {
                "name": "telescope1",
                "driver": "ASCOM.Simulator.Telescope"
            }
        },
        "focuser": {
            "focuser1": {
                "name": "focuser1",
                "driver": "ASCOM.Simulator.Focuser"
            }
        },
        "rotator": {
            "rotator1": {
                "name": "rotator1",
                "driver": "ASCOM.Simulator.Rotator"
            }
        },
    }

    o = Observatory("sim_site", simple_config)

