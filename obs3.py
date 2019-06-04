
# obs.py
# try with gevent

import time, json
import sys
import gevent

from api_calls import API_calls
from devices.camera import Camera
from devices.mount import Mount

running = True

class Observatory:

    update_status_period = 2 #seconds
    scan_for_tasks_period = 2
    running = True

    device_types = [ 
        'mount',
        'camera',
        'filter',
        'focuser', 
        'rotator',
    ]

    def __init__(self, name, config): 
        self.api = API_calls()
        self.name = name
        self.config = config

        self.create_devices(config)

        self.run()

    def run(self):
        try:
            gevent.joinall([ 
                gevent.spawn(self.scan_requests),
                gevent.spawn(self.update_status),
            ])
        except Exception as e:
            print(e)


    def stop(self):
        self.running = False
        sys.exit()

    def create_devices(self, config: dict):

        # This dict will store all created devices, subcategorized by type.
        self.all_devices = {} 

        # Create device objects by type, going through the config by type.
        for type in self.device_types:

            self.all_devices[type] = {}

            # Get the names of all the devices from each type.
            devices_of_type = config.get(type, {})
            device_names = devices_of_type.keys()

            # Instantiate each device object from based on its type
            for name in device_names:
                driver = devices_of_type[name]["driver"]
                if type == "camera":
                    device = Camera(driver)
                elif type == "mount":
                    device = Mount(driver)
                elif type == "filter":
                    device = Filter(driver)
                elif type == "focuser":
                    device = Focuser(driver)
                elif type == "rotator":
                    device = Rotator(driver)

                # Add the instantiated device to the collection of all devices.
                self.all_devices[type][name] = device

        print("Device creation finished.")
        

    def scan_requests(self):

        while True:
            start = time.time()
            gevent.sleep(self.scan_for_tasks_period)
            print("scanning")
            uri = f"{self.name}/mount1/command/"
            cmd = json.loads(self.api.get(uri))

            if cmd == {'Body': 'empty'}:
                #return
                print(f"empty scan took {time.time()-start} seconds")
                continue

            print(cmd)

            cmd_type = cmd['type']
            device_name = cmd['device']

            # Get the device based on it's type and name, then parse the cmd.
            device = self.all_devices[cmd_type][device_name]
            device.parse_command(cmd)

            print("scan complete")

    def update_status(self):
        
        while True:
            start = time.time()
            print("updating")
            ### Get status of all devices
            ###

            status = {}

            # Loop through all types of devices.
            # For each type, we get and save the status of each device.
            for type in self.device_types:

                # The status is grouped into lists of devices by type.
                status[type] = {}
                
                # Names of all devices of the current type.
                # Recall that self.all_devices[type] is a dictionary of all `type` 
                # devices, with key=name and val=device object itself.
                devices_of_type = self.all_devices.get(type, {})
                device_names = devices_of_type.keys()

                for device_name in device_names:
                    # The actual device object
                    device = devices_of_type[device_name]
                    # Add to main status dict.
                    status[type][device_name] = device.get_status()
            
            status["timestamp"] = str(int(time.time()))

            ### Push this status online
            ###

            uri = f"{self.name}/status/"
            res = self.api.put(uri, status)

            print(f"update finished in {time.time()-start} seconds")
            gevent.sleep(self.update_status_period)



if __name__=="__main__":


    import signal
    import os

    simple_config = {
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
    }

    def signal_handler(signal, frame):
        print('You pressed Ctrl+C')
        running = False
        sys.exit()
    signal.signal(signal.SIGINT, signal_handler)
    print('Press Ctrl+C')

    o = Observatory("site4", simple_config)
