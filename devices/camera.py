import win32com.client
import time

import os
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.utils.data import get_pkg_data_filename

from os.path import join, dirname, abspath

class Camera:

    """ 
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """

    def __init__(self, driver: str, name: str):
        self.name = name
        # Define the camera driver, then connect to it.
        self.camera = win32com.client.Dispatch(driver)
        self.camera.Connected = True

        self.save_directory = abspath(join(dirname(__file__), '..', 'images'))

        print("Connected to camera.")
        print(self.camera.Description)
    
    def get_status(self):
        status = {"type":"camera"}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "expose":
            self.expose_command(req, opt)
        elif action == "stop":
            self.stop_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")

    ###############################
    #       Camera Commands       #
    ###############################

    def expose_command(self, required_params, optional_params):
        ''' Apply settings and start an exposure. '''
        c = self.camera
        bin = int(optional_params.get('bin', 1))
        gain = optional_params.get('gain', 1)
        count = int(optional_params.get('count', 1))
        exposure_time = required_params.get('time', 5)
        
        # Setting binning requires also setting NumX and NumY: number of pixels per side.
        c.NumX = c.NumX / bin
        c.NumY = c.NumY / bin
        c.BinX = bin
        c.BinY = bin

        try:
            print("starting exposure")
            c.StartExposure(exposure_time, False)
        except Exception as e:
            print("failed exposure")
            print(e)

        for i in range(20):
            pc = c.PercentCompleted
            print(f"{pc}%")
            if pc >= 100: 
                self.save_image()
                break
            time.sleep(1)

    def stop_command(self, required_params, optional_params):
        ''' Stop the current exposure and return the camera to Idle state. '''

        self.camera.AbortExposure()

        # Alternative: self.camera.StopExposure() will stop the exposure and 
        # initiate the readout process. 
        


    ###############################
    #       Helper Methods        #
    ###############################


    def save_image(self):
        print(f"Image ready: {self.camera.ImageReady}.")

        # Wait until image is ready for retrieval.
        while not self.camera.ImageReady:
            time.sleep(0.1)

        # Array of pixel values from the camera.
        image_array = np.array(self.camera.ImageArray)

        # Create a PrimaryHDU object to encapsulate the data.
        hdu = fits.PrimaryHDU(image_array)

        # Add header
        hdu.header['C_HEAD'] = ('CUSTOMVAL', 'Custom comment')

        # Write file.
        try: 
            print(self.save_directory)
            filename = f'image_{int(time.time())}.fits'
            hdu.writeto(join(self.save_directory, filename))
        except Exception as e:
            print(f"Problem saving file. {e}")






        






if __name__ == '__main__':
    c = Camera('ASCOM.Simulator.Camera')
    print(c.get_ascom_description())

        