
"""
WER 20200307

IMPORTANT TODOs:

- Figure out how to fix jams with Maxium. Debug interrupts can cause
  it to disconnect.

- Design the program to terminate cleanly with Ctrl-C.

THINGS TO FIX:
    20200316

    fully test flash calibration
    generate local masters
    create and send sources file created by sep
    verify operation with FLI16200 camera

    screen flats
    autofocus, and with grid of known stars
    sky flats
    much better weather station approach

"""

import time
import threading
import queue
import requests
import os
import sys
import argparse
import json
import importlib
import numpy as np
from api_calls import API_calls
from skimage import data, io, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure
from skimage.io import imsave
import matplotlib.pyplot as plt

from PIL import Image
import ptr_events

# import device classes
from devices.camera import Camera
from devices.filter_wheel import FilterWheel
from devices.focuser import Focuser
from devices.enclosure import Enclosure
from devices.mount import Mount
from devices.telescope import Telescope
from devices.observing_conditions import ObservingConditions
from devices.rotator import Rotator
from devices.switch import Switch    #Nothing implemented yet 20200511
from devices.screen import Screen
from devices.sequencer import Sequencer
import processing.calibration
from global_yard import g_dev
import bz2
import httplib2


# TODO: move this function to a better location
def to_bz2(filename, delete=False):
    try:
        uncomp = open(filename, 'rb')
        comp = bz2.compress(uncomp.read())
        uncomp.close()
        if delete:
            os.remove(filename)
        target = open(filename + '.bz2', 'wb')
        target.write(comp)
        target.close()
        return True
    except:
        pass
        print('to_bz2 failed.')
        return False


# TODO: move this function to a better location
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


# TODO: move this function to a better location
# The following function is a monkey patch to speed up outgoing large files.
# NB does not appear to work. 20200408 WER
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
            print("send:", repr(data))
        if hasattr(data, 'read') and not isinstance(data, list):
            if self.debuglevel > 0:
                print("sendIng a read()able")
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

        self.command_interval = 2   # seconds between polls for new commands

        self.status_interval = 3    # NOTE THESE IMPLEMENTED AS A DELTA NOT A RATE.

        self.name = name
        self.config = config
        self.last_request = None
        self.stopped = False
        self.site_message = '-'
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

        # Send the config to aws   # NB NB NB This has faulted.
        self.update_config()

        # Instantiate the helper class for astronomical events

        self.astro_events = ptr_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.display_events()
        # Use the configuration to instantiate objects for all devices.
        self.create_devices(config)
        self.loud_status = False
        g_dev['obs'] = self
        self.g_dev = g_dev
        self.time_last_status = time.time() - 3

        # Build the to-AWS Queue and start a thread.
        self.aws_queue = queue.PriorityQueue()
        self.aws_queue_thread = threading.Thread(target=self.send_to_AWS, args=())
        self.aws_queue_thread.start()

        # =============================================================================
        # Here we set up the reduction Queue and Thread:
        # =============================================================================
        self.reduce_queue = queue.Queue(maxsize=50)
        self.reduce_queue_thread = threading.Thread(target=self.reduce_image, args=())
        self.reduce_queue_thread.start()

        # Build the site (from-AWS) Queue and start a thread.
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
                # print('looking for dev-types:  ', dev_type)
                if dev_type == "observing_conditions":
                    device = ObservingConditions(driver, name, self.config, self.astro_events)
                elif dev_type == 'enclosure':
                    device = Enclosure(driver, name, self.config, self.astro_events)
                elif dev_type == "mount":
                    device = Mount(driver, name, settings, self.config, self.astro_events, tel=False)
                elif dev_type == "telescope":   # order of attaching is sensitive
                    device = Telescope(driver, name, settings, self.config, tel=True)
                elif dev_type == "rotator":
                    device = Rotator(driver, name, self.config)
                elif dev_type == "focuser":
                    device = Focuser(driver, name, self.config)
                elif dev_type == "screen":
                    device = Screen(driver, name)
                elif dev_type == "camera":
                    device = Camera(driver, name, self.config)
                elif dev_type == "sequencer":
                    device = Sequencer(driver, name, self.config, self.astro_events)
                elif dev_type == "filter_wheel":
                    device = FilterWheel(driver, name, self.config)
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
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("Config uploaded successfully.")

    def scan_requests(self, mount):
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
        '''

        # This stopping mechanism allows for threads to close cleanly.
        while not self.stopped:
            # Wait a bit before polling for new commands
            time.sleep(self.command_interval)
           #  t1 = time.time()
            if not g_dev['seq'].sequencer_hold:
                url = f"https://jobs.photonranch.org/jobs/getnewjobs"
                body = {"site": self.name}
                # uri = f"{self.name}/{mount}/command/"
                cmd = {}
                # Get a list of new jobs to complete (this request
                # marks the commands as "RECEIVED")
                unread_commands = requests.request('POST', url, \
                                                   data=json.dumps(body)).json()
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
                ## Test Tim's code
                # url = "https://projects.photonranch.org/dev/get-all-projects"
                # all_projects = requests.post(url).json()
                # if all_projects is not None:
                #     print(all_projects)
                return   # Continue   #This creates an infinite loop
            else:
                print('Sequencer Hold asserted.')    #What we really want here is looking for a Cancel/Stop.
                continue

    def update_status(self):
        ''' Collect status from all devices and send an update to aws.
        Each device class is responsible for implementing the method
        `get_status` which returns a dictionary.
        '''

        # This stopping mechanism allows for threads to close cleanly.
        loud = False
        # Wait a bit between status updates
        while time.time() < self.time_last_status + self.status_interval:
            # time.sleep(self.st)atus_interval  #This was prior code
            # print("Staus send skipped.")
            return   # Note we are just not sending status, too soon.

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
                device = devices_of_type[device_name]
                # ...and add it to main status dict.
                status[dev_type][device_name] = device.get_status()
        # Include the time that the status was assembled and sent.
        status["timestamp"] = str(round((time.time() + t1)/2., 3))
        status['send_heartbeat'] = 'false'
        if loud:
            print('Status Sent:  \n', status)   # from Update:  ', status))
        else:
            print('.')   # We print this to stay informed of process on the console.
            #  Consider inhibity unless status rate is low
        uri = f"{self.name}/status/"
        # NB None of the strings can be empty.  Otherwise this put faults.
        try:    # 20190926  tHIS STARTED THROWING EXCEPTIONS OCCASIONALLY
            #print("AWS uri:  ", uri)
            #print('Status to be sent:  \n', status, '\n')
            response = self.api.authenticated_request("PUT", uri, status)   # response = is not  used
            #print("AWS Response:  ",response)
            self.time_last_status = time.time()
        except:
            print('self.api.authenticated_request("PUT", uri, status):   Failed!')


    def update(self):
        """

        20200411 WER
        This compact little function is the heart of the code in the sense this is repeatedly
        called.  It first SENDS status for all devices to AWS, then it checks for any new
        commands from AWS.  Then it calls sequencer.monitor() were jobs may get launched. A
        flaw here is we do not have a Ulid for the 'Job number.'

        With a Maxim based camera is it possible for the owner to push buttons in parallel
        with commands coming from AWS.  This is useful during the debugging phase.

        Sequences that are self-dispatched primarily relate to Bias darks, screen and sky
        flats, opening and closing.  Status for these jobs is reported via the normal
        sequencer status mechanism. Guard flags to preveent careless interrupts will be
        implemented as well as Cancel of a sequence if emitted by the Cancel botton on
        the AWS Sequence tab.

        Flat acquisition will include auomatic rejection of any image that has a mean
        intensity > cam.saturate.  The camera will return without further processing and
        no image will be returned to AWS or stored locally.  We should log the Unihedron and
        calc_illum values where filter first enter non-saturation.  Once we know those values
        we can spend much less effort taking frames that are saturated. Save The Shutter!

        """

        self.update_status()
        try:
            self.scan_requests('mount1')   #NBNBNB THis has faulted, needs to be Try/Except
        except:
            print("self.scan_requests('mount1') threw an exception.")

        g_dev['seq'].manager()  #  Go see if there is something new to do.

    def run(self):   # run is a poor name for this function.
        try:
            # self.update_thread = threading.Thread(target=self.update_status).start()
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

    # Note this is a thread!
    def send_to_AWS(self):  # pri_image is a tuple, smaller first item has priority.
                            # second item is also a tuple containing im_path and name.

        # This stopping mechanism allows for threads to close cleanly.
        while True:
            if not self.aws_queue.empty():
                pri_image = self.aws_queue.get(block=False)
                if pri_image is None:
                    time.sleep(0.2)
                    continue
                # Here we parse the file, set up and send to AWS
                im_path = pri_image[1][0]
                name = pri_image[1][1]
                if not (name[-3:] == 'jpg' or name[-3:] == 'txt'):
                    # compress first
                    to_bz2(im_path + name)
                    name = name + '.bz2'
                aws_req = {"object_name": name}
                aws_resp = g_dev['obs'].api.authenticated_request('POST', '/upload/', aws_req)
                with open(im_path + name, 'rb') as f:
                    files = {'file': (im_path + name, f)}
                    print('--> To AWS -->', str(im_path + name))
                    requests.post(aws_resp['url'], data=aws_resp['fields'],
                                  files=files)
                if name[-3:] == 'bz2' or name[-3:] == 'jpg' or \
                        name[-3:] == 'txt':
                    # os.remove(im_path + name)
                    pass
                self.aws_queue.task_done()
                time.sleep(0.1)
            else:
                time.sleep(0.2)

    # Note this is another thread!
    def reduce_image(self):
        '''
        The incoming object is typically a large fits HDU. Found in its
        header will be both standard image parameters but destination filenames

        '''
        while True:
            if not self.reduce_queue.empty():
                # print(self)
                # print(self.reduce_queue)
                # print(self.reduce_queue.empty)
                pri_image = self.reduce_queue.get(block=False)
                #print(pri_image)
                if pri_image is None:
                    breakpoint
                    time.sleep(.5)
                    continue
                # Here we parse the input and calibrate it.

                paths = pri_image[0]
                hdu = pri_image[1]
                print('Name:  ', paths, '   Hdu.data.shape:', hdu.data.shape)
                print("SIMULATED REDUCTIONS COMPLETED!")

                # paths = {'raw_path':  raw_path,
                #          'cal_path':  cal_path,
                #          'red_path':  red_path,
                #          'cal_name':  cal_name,
                #          'raw_nam00': raw_name00,
                #          'red_nam01': red_name01,
                #          'i768sq_name00': i768sq_name,
                #          'i768sq_name10': i768sq_name,
                #          'jpeg_name10': jpeg_name,
                #          'jpeg_name11': jpeg_name,
                #          'text_name00': text_name,
                #          'text_name10': text_name
                #          }
                #
                # try:    #NB relocate this to Expose entry area.  Fill out except.
                im_path_r = g_dev['cam'].camera_path
                lng_path =  g_dev['cam'].lng_path
                #     # os.makedirs(im_path_r + g_dev['day'] + '/to_AWS/', exist_ok=True)
                #     # os.makedirs(im_path_r + g_dev['day'] + '/raw/', exist_ok=True)
                #     # os.makedirs(im_path_r + g_dev['day'] + '/calib/', exist_ok=True)
                #     # os.makedirs(im_path_r + g_dev['day'] + '/reduced/', exist_ok=True)
                #     #print('Created:  ',im_path + g_dev['day'] + '\\to_AWS\\' )
                #     im_path = im_path_r + g_dev['day'] + '/to_AWS/'
                #     raw_path = im_path_r + g_dev['day'] + '/raw/'
                #     cal_path = im_path_r + g_dev['day'] + '/calib/'
                #     red_path = im_path_r + g_dev['day'] + '/reduced/'
                # except:
                #     print('Path creation in Reductions failed.', lng_path)
               #NB Important decision here, do we flash calibrate screen and sky flats?  For now, Yes.

                #cal_result = calibrate(hdu, lng_path, frame_type, start_x=start_x, start_y=start_y, quick=quick)

                hdu.writeto(paths['red_path'] + paths['red_name01'], overwrite=True)
                # print(hdu.data)
                # print('WROTE TO: ', paths['red_path'] + paths['red_name01'])
                # if g_dev['cam'].toss:
                #     print('lng_path:  ', lng_path)
                #     hdu =  fits.open(lng_path + 'test/M8-0019ha')
                #     print(hdu.data)


                '''
                Here we need to consider just what local reductions and calibrations really make sense to
                process in-line vs doing them in another process.  For all practical purposes everything
                below can be done in a different process, the exception perhaps has to do with autofocus
                processing.


                '''
                # Note we may be using different files if calibrate is null.
                # NB  We should only write this if calibrate actually succeeded to return a result ??

                #  if frame_type == 'sky flat':
                #      hdu.header['SKYSENSE'] = int(g_dev['scr'].bright_setting)
                #
                # if not quick:
                #     hdu1.writeto(im_path + raw_name01, overwrite=True)
                # raw_data_size = hdu1[0].data.size



                #  NB Should this step be part of calibrate?  Second should we form and send a
                #  CSV file to AWS and possibly overlay key star detections?
                #  Possibly even astro solve and align a series or dither batch?
                no_AWS = False
                quick = False
                do_sep = False
                spot = None
                if do_sep:
                    try:
                        img = hdu.data.copy().astype('float')
                        bkg = sep.Background(img)
                        #bkg_rms = bkg.rms()
                        img -= bkg
                        sources = sep.extract(img_sub, 4.5, err=bkg.globalrms, minarea=9)#, filter_kernel=kern)
                        sources.sort(order = 'cflux')
                        print('No. of detections:  ', len(sources))
                        sep_result = []
                        spots = []
                        for source in sources:
                            a0 = source['a']
                            b0 =  source['b']
                            r0 = 2*round(math.sqrt(a0**2 + b0**2), 2)
                            sep_result.append((round((source['x']), 2), round((source['y']), 2), round((source['cflux']), 2), \
                                           round(r0), 3))
                            spots.append(round((r0), 2))
                        spot = np.array(spots)
                        try:
                            spot = np.median(spot[-9:-2])   #  This grabs seven spots.
                            print(sep_result, '\n', 'Spot and flux:  ', spot, source['cflux'], len(sources), avg_foc[1], '\n')
                            if len(sep_result) < 5:
                                spot = None
                        except:
                            spot = None
                    except:
                        spot = None

                raw_data_size = hdu.data.size
                #g_dev['obs'].update_status()
                #Here we need to process images which upon input, may not be square.  The way we will do that
                #is find which dimension is largest.  We then pad the opposite dimension with 1/2 of the difference,
                #and add vertical or horizontal lines filled with img(min)-2 but >=0.  The immediate last or first line
                #of fill adjacent to the image is set to 80% of img(max) so any subsequent subframing selections by the
                #user is informed. If the incoming image dimensions are odd, they will be decreased by one.  In essence
                #we wre embedding a non-rectanglular image in a "square" and scaling it to 768^2.  We will impose a
                #minimum subframe reporting of 32 x 32

                in_shape = hdu.data.shape
                in_shape = [in_shape[0], in_shape[1]]   #Have to convert to a list, cannot manipulate a tuple,
                if in_shape[0]%2 == 1:
                    in_shape[0] -= 1
                if in_shape[0] < 32:
                    in_shape[0] = 32
                if in_shape[1]%2 == 1:
                    in_shape[1] -= 1
                if in_shape[1] < 32:
                    in_shape[1] = 32
                #Ok, we have an even array and a minimum 32x32 array.

                # =============================================================================
                # x = 2      From Numpy: a way to quickly embed an array in a larger one
                # y = 3
                # wall[x:x+block.shape[0], y:y+block.shape[1]] = block
                # =============================================================================

                if in_shape[0] < in_shape[1]:
                    diff = int(abs(in_shape[1] - in_shape[0])/2)
                    in_max = int(hdu.data.max()*0.8)
                    in_min = int(hdu.data.min() - 2)
                    if in_min < 0:
                        in_min = 0
                    new_img = np. zeros((in_shape[1], in_shape[1]))    #new square array
                    new_img[0:diff - 1, :] = in_min
                    new_img[diff-1, :] = in_max
                    new_img[diff:(diff + in_shape[0]), :] = hdu.data
                    new_img[(diff + in_shape[0]), :] = in_max
                    new_img[(diff + in_shape[0] + 1):(2*diff + in_shape[0]), :] = in_min
                    hdu.data = new_img
                elif in_shape[0] > in_shape[1]:
                    #Same scheme as above, but expands second axis.
                    diff = int((in_shape[0] - in_shape[1])/2)
                    in_max = int(hdu.data.max()*0.8)
                    in_min = int(hdu.data.min() - 2)
                    if in_min < 0:
                        in_min = 0
                    new_img = np. zeros((in_shape[0], in_shape[0]))    #new square array
                    new_img[:, 0:diff - 1] = in_min
                    new_img[:, diff-1] = in_max
                    new_img[:, diff:(diff + in_shape[1])] = hdu.data
                    new_img[:, (diff + in_shape[1])] = in_max
                    new_img[:, (diff + in_shape[1] + 1):(2*diff + in_shape[1])] = in_min
                    hdu.data = new_img
                else:
                    #nothing to do, the array is already square
                    pass


                if quick:
                    pass
                hdu.data = hdu.data.astype('uint16')
                resized_a = resize(hdu.data, (768, 768), preserve_range=True)
                #print(resized_a.shape, resized_a.astype('uint16'))
                hdu.data = resized_a.astype('uint16')

                i768sq_data_size = hdu.data.size
                print('ABOUT to print paths.')
                print('Sending to:  ', paths['im_path'])
                print('Also to:     ', paths['i768sq_name10'])
                print("DID IT!")
                hdu.writeto(paths['im_path'] + paths['i768sq_name10'], overwrite=True)
                hdu.data = resized_a.astype('float')
                #The following does a very lame contrast scaling.  A beer for best improvement on this code!!!
                istd = np.std(hdu.data)
                imean = np.mean(hdu.data)
                img3 = hdu.data/(imean + 3*istd)
                fix = np.where(img3 >= 0.999)
                fiz = np.where(img3 < 0)
                img3[fix] = .999
                img3[fiz] = 0
                #img3[:, 384] = 0.995
                #img3[384, :] = 0.995
                print(istd, img3.max(), img3.mean(), img3.min())
                imsave(paths['im_path'] + paths['jpeg_name10'], img3)  #NB File extension triggers JPEG conversion.
                jpeg_data_size = img3.size - 1024
                if not no_AWS:  #IN the no+AWS case should we skip more of the above processing?
                    #g_dev['cam'].enqueue_for_AWS(text_data_size, paths['im_path'], paths['text_name'])
                    g_dev['cam'].enqueue_for_AWS(jpeg_data_size, paths['im_path'], paths['jpeg_name10'])
                    if not quick:
                        g_dev['cam'].enqueue_for_AWS(i768sq_data_size, paths['im_path'], paths['i768sq_name10'])
                        g_dev['cam'].enqueue_for_AWS(raw_data_size, paths['raw_path'], paths['raw_name00'])
                    print('Sent to AWS Queue.')
                time.sleep(0.5)
                self.img = None   #Clean up all big objects.
                try:
                    hdu = None
                except:
                    pass
                try:
                    hdu1 = None
                except:
                    pass

                self.reduce_queue.task_done()
            else:
                time.sleep(.5)

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
    # patch_httplib()     # NB at some point we should check this improves performance, I think it does.  WER
    import config
    o = Observatory(config.site_name, config.site_config)
    o.run()



def OLD_CODE():
    '''
    This is a place for code that is not currently used but saved for reference later.
    If there is code in here that you know is no longer needed, please delete it!

    '''
