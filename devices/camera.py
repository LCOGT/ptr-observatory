
"""
Created on Tue Apr 20 22:19:25 2021

@author: obs, wer, dhunt

"""

import win32com.client
#import pythoncom
#import redis
import time
import datetime
import os
import math
import numpy as np
from astropy.io import fits
#from astropy.table import Table
#from astropy.utils.data import get_pkg_data_filename
import sep
from astropy.time import Time
import glob
import shelve
from pprint import pprint
import matplotlib.pyplot as plt

import traceback

from auto_stretch.stretch import Stretch
from skimage.io import imsave
from skimage.transform import resize


#from devices.sequencer import Sequencer
from devices.darkslide import Darkslide
import ptr_utility
from planewave import platesolve
from global_yard import g_dev
from processing.calibration import calibrate
import copy
from os import getcwd
from pathlib import Path



#string  = \\HOUSE-COMPUTER\saf_archive_2\archive

"""
Camera note 20210131.  IF the QHY ASCOM driver is reloaded or updated use ASCOM
Diagnostics to reesablish the camera binding.
Camera note 20200427.
The goal is refactor this module so we use class attributes more and do not carry them
as parameters in various calls.  Try to use keywords as 'instructions' for processing steps
downstream.  When returning from calls use a dictionary to report results.  Support
synchronous and async reductions.  If the ccd has overscan, incorporate that step into
the immediate processing with trim
Camera Note 20200510.
Beating on camera waiting for long exposures causes Maxim to disconnect.  So instead we
will not look for ImageReady until 'exptime + nominal readout delay - 1 second.'
However every 30 seconds during that wait we will check the camera is connected. if it
drops out we setup the wait and report a failed exposure.
Next add an exposure retry loop: for now retry three times then fail up the call chain.
Reporting camera status should NOT normally provoke the camera when it is exposing. Instead
just report the % complete or estimated time to completion.
The camera operates in  Phase_1:  Setup Exposure, then Phase 2 Take the exposure, then Phase 3
fill out fits headers and save the exposure.  Phase 2, and maybe  Phase 3, are wrapped in the retry-three-
times framework. Next is Phase 4 -- local calibrate and analyze, then Phase 5 -- send to AWS.
Hwere is a Maxim Header with the telescope attached. Note the various keywords which
need to be there  to use Maxim Pinpoint or Visual Pinpoint efficiently.
SIMPLE  	= T
BITPIX  	= -32 /8 unsigned int, 16 & 32 int, -32 & -64 real
NAXIS   	= 2 /number of axes
NAXIS1  	= 4800 /fastest changing axis
NAXIS2  	= 3211 /next to fastest changing axis
BSCALE  	= 1.0000000000000000 /physical = BZERO + BSCALE*array_value
BZERO   	= 0.00000000000000000 /physical = BZERO + BSCALE*array_value
DATE-OBS	= '2021-03-27T18:38:08' /YYYY-MM-DDThh:mm:ss observation, UT
EXPTIME 	= 1.0000000000000000 /Exposure time in seconds
EXPOSURE	= 1.0000000000000000 /Exposure time in seconds
SET-TEMP	= -10.000000000000000 /CCD temperature setpoint in C
CCD-TEMP	= -10.100000000000000 /CCD temperature at start of exposure in C
XPIXSZ  	= 7.5199999999999996 /Pixel Width in microns (after binning)
YPIXSZ  	= 7.5199999999999996 /Pixel Height in microns (after binning)
XBINNING	= 2 /Binning factor in width
YBINNING	= 2 /Binning factor in height
XORGSUBF	= 0 /Subframe X position in binned pixels
YORGSUBF	= 0 /Subframe Y position in binned pixels
READOUTM	= 'Normal  ' /          Readout mode of image
FILTER  	= 'w       ' /          Filter used when taking image
IMAGETYP	= 'Light Frame' /       Type of image
FOCALLEN	= 2700.0000000000000 /Focal length of telescope in mm
APTDIA  	= 300.00000000000000 /Aperture diameter of telescope in mm
APTAREA 	= 59376.102805137634 /Aperture area of telescope in mm^2
EGAIN   	= 1.0000000000000000 /Electronic gain in e-/ADU
SBSTDVER	= 'SBFITSEXT Version 1.0' /Version of SBFITSEXT standard in effect
SWCREATE	= 'MaxIm DL Version 6.24 200613 23VP3' /Name of software
SWSERIAL	= '23VP3-SPE3X-YT5E3-3MX1C-3FVM0-CM' /Software serial number
OBJCTRA 	= '23 55 15' /          Nominal Right Ascension of center of image
OBJCTDEC	= '-54 34 51' /         Nominal Declination of center of image
OBJCTALT	= ' -0.0003' /          Nominal altitude of center of image
OBJCTAZ 	= '180.0056' /          Nominal azimuth of center of image
OBJCTHA 	= '  0.0006' /          Nominal hour angle of center of image
PIERSIDE	= 'EAST    ' /          Side of pier telescope is on
SITELAT 	= '35 32 16' /          Latitude of the imaging location
SITELONG	= '-105 52 13' /        Longitude of the imaging location
JD      	= 2459301.2764814813 /Julian Date at start of exposure
JD-HELIO	= 2459301.2734088539 /Heliocentric Julian Date at exposure midpoint
AIRMASS 	= 31.739008469971399 /Relative optical path length through atmosphere
OBJECT  	= '        '
TELESCOP	= '        ' /          telescope used to acquire this image
INSTRUME	= 'QHYCCD-Cameras-Capture'
OBSERVER	= '        '
NOTES   	= '        '
ROWORDER	= 'TOP-DOWN' /          Image write order, BOTTOM-UP or TOP-DOWN
FLIPSTAT	= '        '
"""

#These should eventually be in a utility module
def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + pCamera)
    #print('Shelf:  ', camShelf)
    sKey = 'Sequence'
    #print(type(sKey), sKey)
    seq = camShelf[sKey]      #get an 8 character string
    seqInt = int(seq)
    seqInt += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    #print(pCamera,seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

def test_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + pCamera)
    #print('Shelf:  ', camShelf)
    sKey = 'Sequence'
    #print(type(sKey), sKey)
    seq = camShelf[sKey]      #get an 8 character string
    camShelf.close()
    SEQ_Counter = seq
    return seq

def reset_sequence(pCamera):
    #breakpoint()
    try:
        camShelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + str(pCamera))
        seqInt = int(-1)
        seqInt  += 1
        seq = ('0000000000'+str(seqInt))[-8:]
        print('Making new seq: ' , pCamera, seq)
        camShelf['Sequence'] = seq
        camShelf.close()
        return seq
    except:
        print ("Nothing on the cam shelf in reset_sequence")
        return None
    #seq = camShelf['Sequence']      # a 9 character string



# Default filter needs to be pulled from site camera or filter config

def camera_factory(driver: str, name: str, config: dict):
    pass

class Camera:

    """
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """

    ###filter, focuser, rotator must be set up prior to camera.
    #Since this is a class definition we need to pre-enter with a list of classes
    #to be created by a camera factory.

    def __init__(self, driver: str, name: str, config: dict):

        """
        Added monkey patches to make ASCOM/Maxim differences
        go away from the bulk of the in-line code.
        Try to be more consistent about use of filter names rather than
        numbers.
        """
        '''

        Outline: if there is a selector then iterate over it for cameras
        and ag's to create.  Name instances cam or ag_<tel>_<sel-port>'.
        Once this is done g_dev['cam'] refers to the selected instance.

        '''
        self.name = name
        g_dev[name + '_cam_retry_driver'] = driver
        g_dev[name + '_cam_retry_name'] = name
        g_dev[name + '_cam_retry_config'] = config
        g_dev[name + '_cam_retry_doit'] = False
        g_dev[name] = self

        if name == 'camera_1_1':     #NBDefaults sets up Selected 'cam'
            g_dev['cam'] = self
        self.config = config
        self.alias = config['camera'][self.name]['name']
        win32com.client.pythoncom.CoInitialize()
        print(driver, name)
        self.camera = win32com.client.Dispatch(driver)


        print ("loading flash dark frame and bias frame if available")

        #parentPath = Path(getcwd())
        #print ("Current Working Directory is: " + str(parentPath))
        #print (str(parentPath) + "\support_info\\tycho_mag_7.dat")
        try:
            self.biasframe = fits.open(self.config['archive_path'] + 'calibmasters/' + self.alias +'/BIAS_master.fits')
            self.biasframe = np.asarray(self.biasframe[0].data, dtype=np.int16)
        except:
            print ("Bias frame not available")
            self.biasframe = [0]
        #    print ("Bias")
        try:
            self.darkframe = fits.open(self.config['archive_path'] + 'calibmasters/' + self.alias +'/DARK_master.fits')
            self.darkframe = np.asarray(self.darkframe[0].data, dtype=np.float32)
        except:
            print ("Dark frame not available")
            self.darkframe = [0]

        #self.camera = win32com.client.Dispatch('ASCOM.FLI.Kepler.Camera')
        #Need logic here if camera denies connection.
        print("Connecting to:  ", driver)


        if driver[:5].lower() == 'ascom':
            print('ASCOM camera is initializing.')
            #Monkey patch in ASCOM specific methods.
            self._connected = self._ascom_connected
            self._connect = self._ascom_connect
            self._set_setpoint = self._ascom_set_setpoint
            self._setpoint = self._ascom_setpoint
            self._temperature = self._ascom_temperature
            self._cooler_on = self._ascom_cooler_on
            self._set_cooler_on = self._ascom_set_cooler_on
            self._expose = self._ascom_expose
            self._stop_expose = self._ascom_stop_expose
            self._imageavailable = self._ascom_imageavailable
            self._getImageArray = self._ascom_getImageArray
            self.description = "ASCOM"
            self.maxim = False
            self.ascom = True
            self.theskyx = False
            print('ASCOM is connected:  ', self._connect(True))
            print('Control is ASCOM camera driver.')

            try:
                actions = self.camera.SupportedActions
                if 'EnableFullSensor' in actions:
                    self.camera.Action("EnableFullSensor", 'enable')
                    print("Chip size expanded to 4132 x 4117")
            except:
                print("Chip size not expanded.")
        elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
            print ("Connecting to the Sky")
            self._connected = self._theskyx_connected
            self._connect = self._theskyx_connect
            self._set_setpoint = self._theskyx_set_setpoint
            self._setpoint = self._theskyx_setpoint
            self._temperature = self._theskyx_temperature
            self._cooler_on = self._theskyx_cooler_on
            self._set_cooler_on = self._theskyx_set_cooler_on
            self._expose = self._theskyx_expose
            self._stop_expose = self._theskyx_stop_expose
            self._imageavailable = self._theskyx_imageavailable
            self._getImageArray = self._theskyx_getImageArray
            self.camera.Connect()
            self.camera.AutoSaveOn =1
            self.description = 'TheSkyX'
            self.maxim = False
            self.ascom = False
            self.theskyx = True
            print('TheSkyX is connected:  ')
            self.app = win32com.client.Dispatch("CCDSoft2XAdaptor.ccdsoft5Camera")

        else:
            print('Maxim camera is initializing.')
            #Monkey patch in Maxim specific methods.
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            self._set_setpoint = self._maxim_set_setpoint
            self._setpoint = self._maxim_setpoint
            self._temperature = self._maxim_temperature
            self._cooler_on = self._maxim_cooler_on
            self._set_cooler_on = self._maxim_set_cooler_on
            self._expose = self._maxim_expose
            self._stop_expose = self._maxim_stop_expose
            self._imageavailable = self._maxim_imageavailable
            self._getImageArray = self._maxim_getImageArray

            self.description = 'MAXIM'
            self.maxim = True
            self.ascom = False
            self.theskyx = False
            print('Maxim is connected:  ', self._connect(True))
            self.app = win32com.client.Dispatch("Maxim.Application")
            print (self.camera)
            self.camera.SetFullFrame()
            self.camera.SetFullFrame


            #self.app.TelescopeConnected = True
            #print("Maxim Telescope Connected: ", self.app.TelescopeConnected)
            print('Control is via Maxim camera interface, not ASCOM.')
            print('Please note telescope is NOT connected to Maxim.')
        ##  NB NB Consider starting at low end of cooling and then gradually increasing it
        print('Cooler started @:  ', self._setpoint())
        setpoint =(float(self.config['camera'][self.name]['settings']['temp_setpoint']))
        self._set_setpoint(setpoint)
        print('Cooler setpoint is now:  ', setpoint)
        if self.config['camera'][self.name]['settings']['cooler_on']:    #NB NB why this logic, do we mean if not cooler found on, then turn it on and take the delay?
            self._set_cooler_on()
        print('Cooler Cooling beginning @:  ', self._temperature())
        time.sleep(5)
        if self.maxim == True:
            print("TEC  % load:  ",  self._maxim_cooler_power())
        self.use_file_mode = False  #self.config['camera'][self.name]['use_file_mode']    #NB NB NB this is obsolte, clear nout file mode from code
        self.current_filter = 0    #W in Apache Ridge case. #This should come from config, filter section
        self.exposure_busy = False
        self.cmd_in = None
        self.t7 = None
        self.camera_message = '-'
        #self.alias = self.config['camera'][self.name]#
        self.site_path = self.config['client_path']
        self.archive_path = self.config['archive_path'] +'archive/'
        self.camera_path = self.archive_path  + self.alias + "/"
        self.alt_path = self.config['alt_path']    #NB NB this should come from config file, it is site dependent.
        self.autosave_path = self.camera_path +'autosave/'
        self.lng_path = self.camera_path + "lng/"
        self.seq_path = self.camera_path + "seq/"
        self.file_mode_path =  self.config['camera'][self.name]['file_mode_path']
        if self.config['camera']['camera_1_1']['driver'] == "CCDSoft2XAdaptor.ccdsoft5Camera":
            self.camera.AutoSavePath = self.config['archive_path'] +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d')
            try:
                os.mkdir(self.config['archive_path'] +'archive/' + datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d'))
            except:
                print ("Couldn't make autosave directory")

        try:
            for file_path in glob.glob(self.file_mode_path + '*.f*t*'):
                os.remove(file_path)
        except:
            print ("Temporary *.fits files not found, this is normally OK.")
        if self.config['camera'][self.name]['settings']['is_cmos']  == True:
            self.is_cmos = True
        else:
            self.is_cmos = False
        self.camera_model = self.config['camera'][self.name]['desc']
        #NB We are reading from the actual camera or setting as the case may be.  For initial setup,
        #   we pull from config for some of the various settings.
        #NB NB There is a differenc between normal cameras and the QHY when it is set to Bin2.
        try:
            self.camera.BinX = int(self.config['camera'][self.name]['settings']['default_bin'][0]) # = 1
            self.camera.BinY = int(self.config['camera'][self.name]['settings']['default_bin'][-1]) # = 1
            #NB we need to be sure AWS picks up this default.config.site_config['camera'][self.name]['settings']['default_bin'])
        except:
            print('Camera only accepts Bins = 1.')
            self.camera.BinX = 1
            self.camera.BinY = 1
        self.overscan_x =  int(self.config['camera'][self.name]['settings']['overscan_x'])
        self.overscan_y =  int(self.config['camera'][self.name]['settings']['overscan_y'])
        # MUCH HERE NEEDS TO BE PUT IN THE CONFIG
        #self.camera_x_size = self.camera.CameraXSize  #unbinned values. QHY returns 2
        #self.camera_y_size = self.camera.CameraYSize  #unbinned
        #self.camera_max_x_bin = self.camera.MaxBinX
        #self.camera_max_y_bin = self.camera.MaxBinX   #NB NB Overriding 511 for FLI cam
        #self.camera_start_x = self.camera.StartX
        #self.camera_start_y = self.camera.StartY
        #self.camera.NumX = int(self.camera_x_size/self.camera.BinX)
        #self.camera.NumY = int(self.camera_y_size/self.camera.BinY)
        #self.camera_num_x = self.camera.NumX    #These are affected binned values.
        #self.camera_num_y = self.camera.NumY
        self.camera_x_size = self.config['camera'][self.name]['settings']['CameraXSize']  #unbinned values. QHY returns 2
        self.camera_y_size = self.config['camera'][self.name]['settings']['CameraYSize']  #unbinned
        self.camera_max_x_bin = self.config['camera'][self.name]['settings']['MaxBinX']
        self.camera_max_y_bin = self.config['camera'][self.name]['settings']['MaxBinY']   #NB NB Overriding 511 for FLI cam
        self.camera_start_x = self.config['camera'][self.name]['settings']['StartX']
        self.camera_start_y = self.config['camera'][self.name]['settings']['StartY']
        try:
            self.camera.NumX = int(self.camera_x_size/self.camera.BinX)
            self.camera.NumY = int(self.camera_y_size/self.camera.BinY)
        except:
            print ("cannot set NumX with this camera")
        self.camera_num_x = int(self.camera_x_size/self.camera.BinX)    #These are affected binned values.
        self.camera_num_y = int(self.camera_y_size/self.camera.BinY)
        self.previous_start_fraction_x = 0.   #These are the subframe **fraction** values for the previous exposure.
        self.previous_start_fraction_y = 0.
        self.previous_num_fraction_x = 1.
        self.previous_num_fraction_y = 1.
        self.previous_start_x = 0.   #These are the subframe **pixel** values for the previous exposure.
        self.previous_start_y = 0.
        self.previous_num_x = 1.
        self.previous_num_y = 1.
        self.previous_image_name = ''
        self.previous_area = 100
        self.af_mode = False
        self.af_step = -1
        self.f_spot_dia = []
        self.f_positions = []
        self.overscan_bin_1 = None   #Remember last overscan if we take a subframe
        self.overscan_bin_2 = None
        self.hint = None
        self.focus_cache = None
        self.darkslide = False
        if self.config['camera'][self.name]['settings']['has_darkslide']:
            self.darkslide = True
            com_port = self.config['camera'][self.name]['settings']['darkslide_com']
            self.darkslide_instance = Darkslide(com_port)     #  NB eventually default after reboot should be closed.
            #self.darkslide_instance.closeDarkslide()   #  Consider turing off IR Obsy light at same time..
            #self.darkslide_open = False
            print("Darkslide unknown on camera startup.")
        self.last_user_name = "Tobor"
        self.last_user_id ="Tobor"
        try:
            seq = test_sequence(self.alias)
        except:
            reset_sequence(self.alias)


        #  NB  Shouldset up default filter @ default focus.


    #Patchable methods   NB These could be default ASCOM
    def _connected(self):
        print("This is un-patched _connected method")
        return False

    def _connect(self, p_connect):
        print("This is un-patched _connect method:  ", p_connect)
        return False

    def _setpoint(self):
        print("This is un-patched cooler _setpoint method")
        return

    #The patches.   Note these are essentially  getter-setter/property constructs.

    def _theskyx_set_setpoint(self, p_temp):
        print ("NOT SURE HOW TO SET TEMP POINT IN THE SKY YET")
        self.camera.TemperatureSetPoint  = float(p_temp)
        return self.camera.TemperatureSetPoint

    def _theskyx_connected(self):
        return self.camera.LinkEnabled

    def _theskyx_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _theskyx_temperature(self):
        return self.camera.Temperature

    def _theskyx_cooler_power(self):
        return self.camera.CoolerPower

    def _theskyx_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _theskyx_cooler_on(self):
        print ("I am not sure what this function is asking for")
        return True   # NB NB NB This would be a good place to put a warming protector

    def _theskyx_set_cooler_on(self):
        self.camera.RegulateTemperature = True
        print("3s wait for cooler to start up.")
        time.sleep(3)
        return self.camera.RegulateTemperature   # NB NB NB This would be a good place to put a warming protector

    def _theskyx_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        return self.camera.TemperatureSetpoint

    def _theskyx_setpoint(self):
        return self.camera.TemperatureSetpoint

    def _theskyx_expose(self, exposure_time, imtypeb):
        self.camera.ExposureTime = exposure_time
        self.camera.TakeImage()

    def _theskyx_stop_expose(self):
        self.camera.AbortExposure()

    def _theskyx_imageavailable(self):
        print (self.camera.IsExposureComplete)
        return (self.camera.IsExposureComplete)

    def _theskyx_getImageArray(self):
        return (fits.open(self.camera.LastImageFileName)[0].data)




    def _maxim_connected(self):
        return self.camera.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _maxim_temperature(self):
        return self.camera.Temperature

    def _maxim_cooler_power(self):
        return self.camera.CoolerPower

    def _maxim_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _maxim_cooler_on(self):
        return self.camera.CoolerOn   # NB NB NB This would be a good place to put a warming protector

    def _maxim_set_cooler_on(self):
        self.camera.CoolerOn = True
        print("3s wait for cooler to start up.")
        time.sleep(3)
        return self.camera.CoolerOn   # NB NB NB This would be a good place to put a warming protector

    def _maxim_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        return self.camera.TemperatureSetpoint

    def _maxim_setpoint(self):
        return self.camera.TemperatureSetpoint

    def _maxim_expose(self, exposure_time, imtypeb):
        self.camera.Expose(exposure_time, imtypeb)

    def _maxim_stop_expose(self):
        self.camera.AbortExposure()

    def _maxim_imageavailable(self):
        return (self.camera.ImageReady)

    def _maxim_getImageArray(self):
        return (self.camera.ImageArray)



    def _ascom_connected(self):
        return self.camera.Connected

    def _ascom_imageavailable(self):
        return (self.camera.ImageReady)



    def _ascom_connect(self, p_connect):
        self.camera.Connected = p_connect
        return self.camera.Connected

    def _ascom_temperature(self):
        return self.camera.CCDTemperature

    def _ascom_cooler_on(self):
        return self.camera.CoolerOn   # NB NB NB This would be a good place to put a warming protector

    def _ascom_set_cooler_on(self):
        self.camera.CoolerOn = True
        return self.camera.CoolerOn

    def _ascom_set_setpoint(self, p_temp):
        if self.camera.CanSetCCDTemperature:
            self.camera.SetCCDTemperature = float(p_temp)
            return self.camera.SetCCDTemperature
        else:
            print ("Camera cannot set cooling temperature.")
            return p_temp

    def _ascom_setpoint(self):
        if self.camera.CanSetCCDTemperature:
            return self.camera.SetCCDTemperature
        else:
            print ("Camera cannot set cooling temperature: Using 10.0C")
            return 10.0

    def _ascom_expose(self, exposure_time, imtypeb):
            self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
            self.camera.StopExposure()   #ASCOM also has an AbortExposure method.

    def _ascom_getImageArray(self):
        return (self.camera.ImageArray)


    def create_simple_autosave(self, exp_time=0, img_type=0, speed=0, suffix='', \
                               repeat=1, readout_mode="Normal", filter_name='W', \
                               enabled=1, binning=1, binmode=0, column=1):
        '''
        Creates a valid Maxium Autosaave file.
        '''
        exp_time = round(abs(float(exp_time)), 3)
        if img_type > 3:
            img_type = 0
        repeat = abs(int(repeat))
        if repeat < 1:
            repeat = 1
        binning = abs(int(binning))
        if binning > 24:
            binning = 2
        if filter_name == "":
            filter_name = 'w'
        proto_file = open(self.camera_path +'seq/ptr_proto.seq')
        proto = proto_file.readlines()
        proto_file.close()
        #print(proto, '\n\n')
        if column == 1:
            proto[51] = proto[51][:9]  + str(img_type) + proto[51][10:]
            proto[50] = proto[50][:9]  + str(exp_time) + proto[50][12:]
            proto[48] = proto[48][:12] + str(suffix)   + proto[48][12:]
            proto[47] = proto[47][:10] + str(speed)    + proto[47][11:]
            proto[31] = proto[31][:11] + str(repeat)   + proto[31][12:]
            proto[29] = proto[29][:17] + readout_mode  + proto[29][23:]
            proto[13] = proto[13][:12] + filter_name   + proto[13][13:]
            proto[10] = proto[10][:12] + str(enabled)  + proto[10][13:]
            proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
        seq_file = open(self.camera_path +'seq/ptr_mrc.seq', 'w')
        for item in range(len(proto)):
            seq_file.write(proto[item])
        seq_file.close()
       # print(proto)                binning=3, filter_name='air')


    def get_status(self):
        #status = {"type":"camera"}
        status = {}
        status['active_camera'] = self.name
        if self.config['camera'][self.name]['settings']['has_darkslide']:
            #ds = self.darkslide_instance.slideStatus
            status['darkslide'] = g_dev['drk'].slideStatus
        else:
            status['darkslide']    = 'unknown'
        if self.exposure_busy:
            status['busy_lock'] = True
        else:
            status['busy_lock'] = False
        if self.maxim:
            cam_stat = 'Not implemented yet' #
            #print('AutoSave:  ', self.camera.SequenceRunning)
        if self.ascom:
            cam_stat = 'ASCOM camera not implemented yet' #self.camera.CameraState
        if self.theskyx:
            cam_stat = 'TheSkyX camera not implemented yet' #self.camera.CameraState
        status['status'] = cam_stat  #The state could be expanded to be more meaningful.
        return status
#        if self.maxim:
#            status['ccd_temperature'] = str(round(self.camera.Temperature , 3))
#        if self.ascom:
#            status['ccd_temperature'] = str(round(self.camera.CCDTemperature , 3))




    def parse_command(self, command):
        #print("Camera Command incoming:  ", command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        self.user_id = command['user_id']
        if self.user_id != self.last_user_id:
            self.last_user_id = self.user_id
        self.user_name = command['user_name']

        #if self.object_name != '':
        #    self.object_name = opt['object_name']
        #else:
        #    self.object_name = False
        print (opt)
        if 'object_name' in opt:            # this is the worlds laziest bit of code... it is just until some javascript is updated. remove try except >Oct22
            if opt['object_name'] == '':
                opt['object_name']= 'Unspecified'
            print (opt['object_name'])
        else:
            opt['object_name']= 'Unspecified'
            print (opt['object_name'])
        if self.user_name != self.last_user_name:
            self.last_user_name = self.user_name
        if action == "expose" and not self.exposure_busy:
            self.expose_command(req, opt, do_sep=True, quick=False)
            self.exposure_busy = False     #Hangup needs to be guarded with a timeout.
            self.active_script = None

        elif action == "expose" and self.exposure_busy:
            print("Cannot expose, camera is currently busy")
#            self.screen_flat_script(req, opt)
#            self.exposure_busy = False
#            self.active_script = 'make_superscreenflats'
        elif action == "darkslide_close":
           # self.stop_command(req, opt)
           # self.exposure_busy = False
           g_dev['drk'].closeDarkslide()
           print("Closing the darkslide.")
        elif action == "darkslide_open":
           # self.stop_command(req, opt)
           # self.exposure_busy = False
           g_dev['drk'].openDarkslide()
           print("Opening the darkslide.")
        elif action == "stop":
            self.stop_command(req, opt)
            self.exposure_busy = False
            print("STOP  STOP  STOP received.")
        else:

            print(f"Command <{action}> not recognized.")

    ###############################
    #       Camera Commands       #
    ###############################

    ''''
    Each time an expose is entered we need to look and see if the filter
    and or focus is different.  If  filter change is required, do it and look up
    the new filter offet.  Apply that as well.  Possibly this step also includes
    a temperature compensation cycle.
    Do we let focus 'float' or do we pin to a reference?  I think the latter.
    ref = actual - offset(filter): ref + offset(f) = setpoint.  At end of AF
    cycle the reference is updated logging in the filter used and the temperature.
    The old value is appended to a list which can be analysed to find the temp
    comp parameter.  It is assumed we ignore the diffuser condition when saving
    or autofocusing.  Basically use a MAD regression and expect a correlation
    value > 0.6 or so.  Store the primary temp via PWI3 and use the Wx temp
    for ambient.  We need a way to log the truss temp until we can find which
    temp best drives the compensation.
    We will assume that the default filter is a wide or lum with a nominal offset
    of 0.000  All other filter offsets are with respect to the default value.
    I.e., an autofocus of the reference filter results in the new focal position
    becoming the reference.
    The system boots up and selects the reference filter and reference focus.
    '''


    def expose_command(self, required_params, optional_params,  \
                       gather_status = True, do_sep=True, no_AWS=False, quick=False, solve_it=False):
        '''
        This is Phase 1:  Setup the camera.
        Apply settings and start an exposure.
        Quick=True is meant to be fast.  We assume the ASCOM/Maxim imageBuffer is the source of data in that mode,
        not the slower File Path.  THe mode used for focusing or other operations where we do not want to save any
        image data.
        '''
        #print('Expose Entered.  req:  ', required_params, 'opt:  ', optional_params)
        #print("Checking if Maxim is still connected!")
        #  self.t7 is last time camera was read out
        #if self.t7 is not None and (time.time() - self.t7 > 30) and self.maxim:

        try:
            self.user_name
        except:
            self.user_name = "kilroy_was_here"
        self.t0 = time.time()
        #Force a reseek //eventually dither//
        try:
            if g_dev['mnt'].last_seek_time < self.t0 - 180:   #NB Consider upping this to 300 to 600 sec.
                print('re_seeking')
                g_dev['mnt'].re_seek(0)  #) is a placeholder for a dither value being passed.
        except:
            pass
              #print('Re_seek skipped; usualy becuase no prior seek this session.')
        try:

            probe = self._cooler_on()
            if not probe:
                self._set_cooler_on()
                print('Found cooler off.')
                try:
                    self._connect(False)
                    self._connect(True)
                    self._set_cooler_on()
                except:
                    print('Camera reconnect failed @ expose entry.')
        except Exception as e:
            print("\n\nCamera was not connected @ expose entry:  ", e, '\n\n')
            try:
                self._connect(False)
                self._connect(True)
                self._set_cooler_on()
            except:
                print('Camera reconnect failed 2nd time @ expose entry.')
        opt = optional_params
        self.hint = optional_params.get('hint', '')
        self.script = required_params.get('script', 'None')
        self.pane = optional_params.get('pane', None)
        bin_x = optional_params.get('bin', self.config['camera'][self.name] \
                                                      ['settings']['default_bin'])  #NB this should pick up config default.

        try:
            bin_x = eval(bin_x)[:2]   #This is meant to strip off the Pixel size when it comes in from aws.
        except:
            print('Bin eval did not work, no harm usually.')
        if bin_x in ['4 4', 4, '4, 4', '4,4', [4, 4], (4, 4)]:     # For now this is the highest level of binning supported.
            bin_x = 4
            self.ccd_sum = '4 4'
        elif bin_x in ['3 3', 3, '3, 3', '3,3', [3, 3], (3, 3)]:   # replace with in and various formats or strip spaces.
            bin_x = 3
            self.ccd_sum = '3 3'
        elif bin_x in ['2 2', 2, '2, 2', '2,2', [2, 2], (2, 2)]:   #The bin spec is too convoluted. This needs a deep clean.
            bin_x = 2
            self.ccd_sum = '2 2'
        elif bin_x in ['0 0', 0, '0, 0', '0,0', [0, 0], (0, 0)]:   # 0,0 is an indicator for selecting the default binning
            bin_x = self.config['camera'][self.name]['settings']['default_bin'][0]
            self.ccd_sum = str(bin_x) + ' ' + str(bin_x)
        else:
            bin_x = 1
            self.ccd_sum = '1 1'

        bin_y = bin_x   #NB This needs fixing someday!
        self.bin = bin_x
        self.camera.BinX = bin_x
        self.camera.BinY = bin_y
        try:
            self.camera.NumX = int(self.camera_x_size/self.camera.BinX)
            self.camera.NumY = int(self.camera_y_size/self.camera.BinY)
        except:
            print ("this camera cannot set NumX")
        #gain = float(optional_params.get('gain', self.config['camera'][name] \
        #                                              ['settings']['reference_gain'][bin_x - 1]))
        readout_time = float(self.config['camera'][self.name]['settings']['cycle_time'][bin_x - 1])
        exposure_time = float(required_params.get('time', 0.0001))   #  0.0 may be the best default.  Use QHY min spec?  Config item?
        exposure_time = min(exposure_time, 1440.)
        self.estimated_readtime = (exposure_time + readout_time)   #  3 is the outer retry loop maximum.
        #exposure_time = max(0.2, exposure_time)  #Saves the shutter, this needs qualify with imtype.
        imtype= required_params.get('image_type', 'light')
        if imtype.lower() in ['experimental']:
            g_dev['enc'].wx_test = not g_dev['enc'].wx_test   #NB NB NB What is this for?
            return
        count = int(optional_params.get('count', 1))   #  For now Repeats are external to full expose command.
        lcl_repeat = 1
        if count < 1:
            count = 1   #Hence frame does not repeat unless count > 1
        #breakpoint()
        #  Here we set up the filter, and later on possibly rotational composition.
        try:    #20200716   FW throwing error (-4)
            #requested_filter_name = str(optional_params.get('filter', 'w'))   #Default should come from config.
            requested_filter_name = str(optional_params.get('filter', self.config['filter_wheel']['filter_wheel1']['settings']['default_filter']))   #Default DOES come from config.

            self.current_filter = requested_filter_name
            self.current_filter = g_dev['fil'].set_name_command({'filter': requested_filter_name}, {})
            if self.current_filter == 'none':
                print ("skipping exposure as no adequate filter match found")
                return
        except Exception as e:
            print("Camera filter setup:  ", e)
            #breakpoint()
        #  NBNB Changing filter may cause a need to shift focus
        self.current_offset = g_dev['fil'].filter_offset  #TEMP   NBNBNB This needs fixing
        # Here we adjust for focus temp and filter offset
        if not imtype.lower() in ['auto_focus', 'focus', 'autofocus probe']:
            g_dev['foc'].adjust_focus(loud=True)
        sub_frame_fraction = optional_params.get('subframe', None)

        #  The following bit of code is convoluted.  Presumably when we get Autofocus working this will get cleaned up.
        # self.toss = False
        # self.do_sep = False

        # if imtype.lower() in ('light', 'light frame', 'experimental', 'screen flat', 'sky flat', \
        #                       'test image', 'auto_focus', 'focus', 'autofocus probe'):
        #                         #here we might eventually turn on spectrograph lamps as needed for the imtype.
        #     imtypeb = True      #imtypeb will passed to open the shutter.
        #     frame_type = imtype.lower()
        #     do_sep = True
        #     self.do_sep = True
        #     if imtype.lower() in ('screen flat', 'sky flat', 'quick'):
        #         do_sep = False
        #         self.do_sep = False
        #     if imtype.lower() == 'test image':
        #         self.toss = True
        # elif imtype.lower() == 'bias':
        #     exposure_time = 0.00001    #Can QHY take 0.0??
        #     imtypeb = False
        #     frame_type = 'BIAS'
        #     no_AWS = False
        #     do_sep = False
        #     self.do_sep = False
        #     # Consider forcing filter to dark if such a filter exists.
        # elif imtype.lower() == 'dark':
        #     imtypeb = False
        #     frame_type = 'DARK'
        #     no_AWS = False
        #     do_sep = False
        #     self.do_sep = False
        #     # Consider forcing filter to dark if such a filter exists.
        # elif imtype.lower() == 'screen flat':
        #     frame_type = 'screen flat'
        # elif imtype.lower() == 'sky flat':
        #     frame_type = 'SKYFLAT'
        #     self.do_sep = False
        # elif imtype.lower() == 'quick':
        #     quick = True
        #     no_AWS = False   # Send only an informational JPEG??
        #     do_sep = False
        #     imtypeb = True
        #     frame_type = 'EXPOSE'
        # elif imtype.lower() == 'lamp flat':
        #     no_AWS = False
        #     do_sep = False
        #     frame_type = 'LAMPFLAT'
        # elif imtype.lower() in ('NeAr flat', 'ThAr flat', 'arc flat'):
        #     no_AWS = False
        #     do_sep = False
        #     frame_type = 'ARC'
        # else:
        #     imtypeb = True
        #     do_sep = True
        # NBNB This area still needs work to cleanly define shutter, calibration, sep and AWS actions.

        # ---- DEH changes to frame_type for banzai compliance and clarity ----
        # send everything except test images to AWS.

        no_AWS, self.toss = True if imtype.lower() == 'test image' else False, False
        quick = True if imtype.lower() == 'quick' else False
        # clearly define which frames do not do_sep, the rest default to do_sep.  NBNB this is obsolete and needs rework 20221002 WER
        if imtype.lower() in ('quick', 'bias', 'dark', 'screen flat', 'sky flat', 'near flat', 'thor flat', \
                                'arc flat', 'lamp flat', 'solar flat'):
            do_sep = False
        else:
            do_sep = True
        # shutter open/close status, turn on lamps, frames: ARC, BIAS, BPM, DARK, DOUBLE(2 lit fib.),
        # EXPERIMENTAL(autofocus), EXPOSE(obj), GUIDE, LAMPFLAT, SKYFLAT, STANDARD, TARGET(Obj+ThAr)
        if imtype.lower() in ('bias', 'dark', 'lamp flat'):
            if imtype.lower() == 'bias':
                exposure_time = 0.0
            # else:
            #     exposure_time = self.config['camera'][self.name]['settings']['min_exposure']
            imtypeb = False  # don't open the shutter.
            lamps = 'turn on led+tungsten lamps here, if lampflat'
            frame_type = imtype.replace(' ', '')
        elif imtype.lower() in ('near flat', 'thor flat', 'arc flat'):
            imtypeb = False
            lamps = 'turn on ThAr or NeAr lamps here'
            frame_type = 'arc'
        elif imtype.lower() in ('sky flat', 'screen flat','solar flat'):
            imtypeb = True  # open the shutter.
            lamps = 'screen lamp or none'
            frame_type = imtype.replace(' ', '')  # note banzai doesn't appear to include screen or solar flat keywords.
        elif imtype.lower() == 'focus':
            frame_type = 'focus'
            imtypeb = True
            lamps = None
        else:  # 'light', 'experimental', 'autofocus probe', 'quick', 'test image', or any other image type
            imtypeb = True
            lamps = None
            if imtype.lower() in ('experimental', 'autofocus probe', 'auto_focus'):
                frame_type = 'experimental'
            else: frame_type = 'expose'

        area = optional_params.get('area', 150)
        # if area is None or area in['Full', 'full', 'chip', 'Chip']:   #  Temporary patch to deal with 'chip'
        #     area = 150
        sub_frame_fraction = optional_params.get('subframe', None)
        # Need to put in support for chip mode once we have implmented in-line bias correct and trim.
        try:
            if type(area) == str and area[-1] == '%':  #NB NB NB Re-use of variable is crappy coding
                #The whole area implementation needs rework for anything specified larger that the full chip.
                #Subframes are more logical to specify as fractionals of the base chip.
                area = int(area[0:-1])
            elif area in ('Sqr', 'sqr', '100%', 100):
                area = 100
            elif area in ('Full', 'full', '150%', 'Chip', 'chip', 150):
                area = 150
        except:
            area = 150     #was 100 in ancient times.

        if bin_y == 0 or self.camera_max_x_bin != self.camera_max_y_bin:
            self.bin_x = min(bin_x, self.camera_max_x_bin)
            self.cameraBinY = self.bin_y
        else:
            self.bin_x = min(bin_x, self.camera_max_x_bin)
            self.camera.BinX = self.bin_x
            self.bin_y = min(bin_y, self.camera_max_y_bin)
            self.camera.BinY = self.bin_y

        self.len_x = self.camera_x_size//self.bin_x
        self.len_y = self.camera_y_size//self.bin_y    #Unit is binned pixels.
        self.len_xs = 0  # THIS IS A HACK, indicating no overscan.
        # print(self.len_x, self.len_y)
        #  NB Area is just a series of subframes centered on the chip.
        # "area": ['100%', '71%', '50%',  '35%', '25%', '12%']

        if 72 < area <= 100:  #  This is completely incorrect, this section needs a total re-think 20201021 WER
            self.camera_num_x = self.len_x
            self.camera_start_x = 0
            self.camera_num_y = self.len_y
            self.camera_start_y = 0
            self.area = 100
        elif 70 <= area <= 72:  # This needs complete rework.
            self.camera_num_x = int(self.len_xs/1.4142)
            self.camera_start_x = int(self.len_xs/6.827)
            self.camera_num_y = int(self.len_y/1.4142)
            self.camera_start_y = int(self.len_y/6.827)
            self.area = 71
        elif area == 50:
            self.camera_num_x = self.len_x//2
            self.camera_start_x = self.len_x//4
            self.camera_num_y = self.len_y//2
            self.camera_start_y = self.len_y//4
            self.area = 50
        elif 33 <= area <= 37:
            self.camera_num_x = int(self.len_/2.829)
            self.camera_start_x = int(self.len_xx/3.093)
            self.camera_num_y = int(self.len_y/2.829)
            self.camera_start_y = int(self.len_y/3.093)
            self.area = 35
        elif area == 25:
            self.camera_num_x = self.len_xs//4
            self.camera_start_x = int(self.len_xs/2.667)
            self.camera_num_y = self.len_y//4
            self.camera_start_y = int(self.len_y/2.667)
            self.area = 25
        elif 11 <= area <= 13:
            self.camera_num_x = self.len_xs//4
            self.camera_start_x = int(self.len_xs/2.667)
            self.camera_num_y = self.len_y//4
            self.camera_start_y = int(self.len_y/2.667)
            self.area = 12
        else:
            self.camera_num_x = self.len_x
            self.camera_start_x = 0
            self.camera_num_y = self.len_y
            self.camera_start_y = 0
            self.area = 150
           #print("Default area used = 100%, ie. the full chip:  ", self.len_x,self.len_y )

        #Next apply any subframe setting here.  Be very careful to keep fractional specs and pixel values disinguished.
        if self.area == self.previous_area and sub_frame_fraction is not None and \
                        (sub_frame_fraction != self.previous_image_name):
            sub_frame_fraction_xw = abs(float(sub_frame_fraction['x1']) -float( sub_frame_fraction['x0']))
            if sub_frame_fraction_xw < 1/32.:
                sub_frame_fraction_xw = 1/32.
            else:
                pass   #Adjust to center position of sub-size frame
            sub_frame_fraction_yw = abs(float(sub_frame_fraction['y1']) - float(sub_frame_fraction['y0']))
            if sub_frame_fraction_yw < 1/32.:
                sub_frame_fraction_yw = 1/32.
            else:
                pass
            sub_frame_fraction_x = min(sub_frame_fraction['x0'], sub_frame_fraction['x1'])
            sub_frame_fraction_y = min(sub_frame_fraction['y0'], sub_frame_fraction['y1'])
            num_x = int(self.previous_num_fraction_x*sub_frame_fraction_xw*self.previous_num_x)
            num_y = int(self.previous_num_fraction_y*sub_frame_fraction_yw*self.previous_num_y)
            #Clamp subframes to a minimum size
            if num_x < 32:
                num_x = 32
            if num_y < 32:
                num_y = 32
            dist_x = int(self.previous_start_x + self.previous_num_x*float(sub_frame_fraction_x))
            dist_y = int(self.previous_start_y +self.previous_num_y*float(sub_frame_fraction_y))
            self.camera_start_x= dist_x
            self.camera_start_y= dist_y
            self.camera_num_x= num_x
            self.camera_num_y= num_y
            self.previous_image_name = sub_frame_fraction['definedOnThisFile']
            self.previous_start_x = dist_x
            self.previous_start_y = dist_y
            self.previous_num_x = num_x
            self.previous_num_y = num_y
            self.bpt_flag = False
        elif self.area == self.previous_area and sub_frame_fraction is not None and \
                          (sub_frame_fraction['definedOnThisFile'] == self.previous_image_name):
            #Here we repeat the previous subframe and do not re-enter and make smaller
            self.camera_start_x = self.previous_start_x
            self.camera_start_y = self.previous_start_y
            dist_x = self.previous_start_x
            dist_y = self.previous_start_y
            self.camera_num_x= self.previous_num_x
            self.cameraNumY= self.previous_num_y
            self.bpt_flag  = True

        elif sub_frame_fraction is None:
            self.previous_start_x = self.camera_start_x  #These are the subframe values for the new area exposure.
            self.previous_start_y = self.camera_start_y
            dist_x = self.previous_start_x
            dist_y = self.previous_start_y
            self.previous_num_x = self.camera_num_x
            self.previous_num_y = self.camera_num_y
            self.previous_num_fraction_x = 1.0
            self.previous_num_fraction_y = 1.0
            self.previous_area = self.area
            self.bpt_flag = False
        #  NB Important: None of above code talks to the camera!
        result = {}  #  This is a default return just in case
        num_retries = 0
        for seq in range(count):
            #  SEQ is the outer repeat loop and takes count images; those individual exposures are wrapped in a
            #  retry-3-times framework with an additional timeout included in it.
            if seq > 0:
                g_dev['obs'].update_status()

            self.pre_mnt = []
            self.pre_rot = []
            self.pre_foc = []
            self.pre_ocn = []
            #time_out = time.time()

            try:
                #Check here for filter, guider, still moving  THIS IS A CLASSIC
                #case where a timeout is a smart idea.
                #Wait for external motion to cease before exposing.  Note this precludes satellite tracking.
                st = ""

                if g_dev['enc'].is_dome:
                    try:
                        enc_slewing = g_dev['enc'].status['dome_slewing']
                    except:
                        print("enclosure SLEWING threw an exception.")
                else:
                     enc_slewing = False

                while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                      g_dev['mnt'].mount.Slewing: #or enc_slewing:   #Filter is moving??
                    if g_dev['foc'].focuser.IsMoving: st += 'f>'
                    if g_dev['rot'].rotator.IsMoving: st += 'r>'
                    if g_dev['mnt'].mount.Slewing:
                        st += 'm>  ' + str(round(time.time() - g_dev['mnt'].move_time, 1))
                    #if enc_slewing:
                        #st += 'd>' + str(round(time.time() - g_dev['mnt'].move_time, 1))
                    print(st)
                    if round(time.time() - g_dev['mnt'].move_time, 1) >=75:
                       print("|n\n DOME OR MOUNT HAS TIMED OUT!|n|n")
                       break

                    st = ""
                    time.sleep(0.2)
                    if seq > 0:
                        g_dev['obs'].update_status()
                    #Refresh the probe of the dome status
                    if g_dev['enc'].is_dome:
                        try:
                            enc_slewing = g_dev['enc'].status['dome_slewing']
                        except:
                            print("enclosure SLEWING threw an exception.")
                    else:
                         enc_slewing = False

            except:
                pass
               # print("Motion check faulted.")
            if seq > 0:
                g_dev['obs'].update_status()   # NB Make sure this routine has a fault guard.
            self.retry_camera = 3
            self.retry_camera_start_time = time.time()

            while self.retry_camera > 0:

                #NB Here we enter Phase 2
                try:
                    self.t1 = time.time()
                    self.exposure_busy = True
                    #print('First Entry to inner Camera loop:  ')  #  Do not reference camera, self.camera.StartX, self.camera.StartY, self.camera.NumX, self.camera.NumY, exposure_time)
                    #First lets verify we are connected or try to reconnect.   #Consider uniform ests in a routine, start with reading CoolerOn
                    try:
                        probe = self._cooler_on()
                        if not probe:
                            print('Found cooler off.')
                            try:
                                self._connect(False)
                                self._connect(True)
                                self._set_cooler_on()
                            except:
                                print('Camera reconnect failed @ expose camera entry.')

                                g_dev['cam_retry_doit'] = True
                    except Exception as e:
                        print("\n\nCamera was not connected @ expose camera retry:  ", e, '\n\n')

                        try:
                            self._connect(False)
                            self._connect(True)
                            self._set_cooler_on()
                        except:
                            print('Camera reconnect failed @ expose camera retry.')

                            g_dev['cam_retry_doit'] = True
                    #  At this point we really should be connected!!

                    if self.maxim or self.ascom or self.theskyx:
                        #print('Link Enable check:  ', self._connected())
                        try:
                            g_dev['ocn'].get_quick_status(self.pre_ocn)
                        except:
                            print ("ECO enclosure on exposure fail, line 1020")
                        g_dev['foc'].get_quick_status(self.pre_foc)
                        try:
                            g_dev['rot'].get_quick_status(self.pre_rot)
                        except:
                            print ("ECO Don't have no rotator 1025")
                        try:
                            g_dev['mnt'].get_quick_status(self.pre_mnt)
                        except:
                            print ("ra_cal_offset is an issue")
                        ldr_handle_time = None
                        # try:
                        #     os.remove(self.camera_path + 'newest.fits')
                        # except:
                        #     pass   #  print ("File newest.fits not found, this is probably OK")                        self.t2 = time.time()
                        ldr_handle_high_time = None  #  This is not maxim-specific

                        #print('Filter number is:  ', self.camera.Filter)
                        #try:
                        #    for file_path in glob.glob('D:*.fit'):
                        #        #os.remove(file_path)
                        #        pass
                        #except:
                        #    pass
                        if self.darkslide and imtypeb:
                            self.darkslide_instance.openDarkslide()
                            self.darkslide_open = True
                            time.sleep(0.1)
                        elif self.darkslide and not imtypeb:
                            self.darkslide_instance.closeDarkslide()
                            self.darkslide_open = False
                            time.sleep(0.1)
                        else:
                            pass
                        if self.use_file_mode:
                            if imtypeb:
                                img_type = 0
                            if frame_type == 'bias':
                                img_type = 1
                            if frame_type == 'dark':
                                img_type = 2
                            if frame_type in ('flat', 'screenflat', 'skyflat'):
                                img_type = 3
                            #  This is a Maxim-only technique. Does not work with ASCOM Camera driver
                            #self.create_simple_autosave(exp_time=exposure_time, img_type=img_type, \
                            #                       filter_name=self.current_filter, binning=bin_x, \
                            #                       repeat=lcl_repeat)
                            self.camera.SetFullFrame()
                            self.create_simple_autosave(exp_time=exposure_time, img_type=img_type, \
                                                   filter_name=self.current_filter, enabled=1, binning=bin_x, \
                                                   repeat=lcl_repeat)
                            for file_path in glob.glob(self.file_mode_path + '*.f*t*'):
                                os.remove(file_path)
                            self.t2 = time.time()
                            self.camera.StartSequence(self.camera_path + 'seq/ptr_mrc.seq')
                            print("Starting autosave  at:  ", self.t2)
                        else:
                            #This is the standard call to Maxim
                            self.pre_mnt = []
                            self.pre_rot = []
                            self.pre_foc = []
                            self.pre_ocn = []
                            if frame_type in ('flat', 'screenflat', 'skyflat', 'dark', 'bias'):
                                g_dev['obs'].send_to_user("Starting " + str(exposure_time) + "s " + str(frame_type) + " calibration exposure.", p_level='INFO')
                            elif frame_type in ('focus', 'auto_focus'):
                                g_dev['obs'].send_to_user("Starting " + str(exposure_time) + "s "+ str(frame_type) + " exposure.", p_level='INFO')
                            else:
                                if 'object_name' in opt:
                                    g_dev['obs'].send_to_user("Starting " + str(exposure_time) + "s exposure of "+ str(opt['object_name']) + " by user: " + str(self.user_name), p_level='INFO')
                                else:
                                    g_dev['obs'].send_to_user("Starting an unnamed frame by user: " + str(self.user_name), p_level='INFO')
                            try:
                                g_dev['ocn'].get_quick_status(self.pre_ocn)   #NB NB WEMA must be running or this may fault.
                            except:
                                print ("ECO aint got ocn line 1087")
                            g_dev['foc'].get_quick_status(self.pre_foc)
                            try:
                                g_dev['rot'].get_quick_status(self.pre_rot)
                            except:
                                print ("ECO ain't got not rotator")
                            #try:
                            g_dev['mnt'].get_quick_status(self.pre_mnt)  #Should do this close to the exposure
                            #except:
                            #    print ("j,,,,hfgd")
                            if imtypeb:
                                imtypeb = 1
                            else:
                                imtypeb = 0
                            self.t2 = time.time()



                            self._expose (exposure_time, imtypeb)
                    else :
                        print("Something terribly wrong, driver not recognized.!")
                        result = {}
                        result['error': True]
                        return result
                    self.t9 = time.time()
                    #We go here to keep this subroutine a reasonable length, Basically still in Phase 2

                    result = self.finish_exposure(exposure_time,  frame_type, count - seq, \
                                         gather_status, do_sep, no_AWS, dist_x, dist_y, \
                                         quick=quick, low=ldr_handle_time, \
                                         high=ldr_handle_high_time, \
                                         script=self.script, opt=opt, solve_it=solve_it)  #  NB all these parameters are crazy!
                    self.exposure_busy = False
                    self.t10 = time.time()
                    #  self._stop_expose()
                    #print("\nInner expose of a group took:  ", round(self.t10 - self.t0 , 2), ' returned:  ', result)
                    self.retry_camera = 0
                    break
                except Exception as e:
                    print('Exception in camera retry loop:  ', e)
                    print(traceback.format_exc())
                    self.retry_camera -= 1
                    num_retries += 1
                    self.exposure_busy = False
                    continue
        #  This is the loop point for the seq count loop
        self.t11 = time.time()
        #print("\nFull expose of a group took:  ", round(self.t11 - self.t0 , 2), ' Retries;  ', num_retries, 'Average: ', round((self.t11 - self.t0)/count, 2),  ' Returning:  ', result, '\n\n')
        try:
            #print(' 0 sec cycle time:  ', round((self.t11 - self.t0)/count - exposure_time , 2) )
            pass
        except:
            pass
        return result

    def stop_command(self, required_params, optional_params):
        ''' Stop the current exposure and return the camera to Idle state. '''
        #  NB NB This routine needs work!
        self.exposure_busy = False
        self.exposure_halted = True

    def finish_exposure(self, exposure_time, frame_type, counter, seq, \
                        gather_status=True, do_sep=False, no_AWS=False, start_x=None, start_y=None, quick=False, \
                        low=0, high=0, script='False', opt=None, solve_it=False):
        print("Finish exposure Entered:  " + str(exposure_time) + 'sec.;   # of ', frame_type, 'to go: ', counter)
        g_dev['obs'].send_to_user("Starting Exposure: "+ str(exposure_time) + ' sec.;   # of ' + frame_type + ' frames. Remaining: ' + str(counter), p_level='INFO')
        #, gather_status, do_sep, no_AWS, start_x, start_y, opt['area'])
        self.status_time = time.time() + 10
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0
        if self.bin == 1:
            cycle_time = exposure_time + 15
        else:
            cycle_time = exposure_time + 12
        self.completion_time = self.t2 + cycle_time + 12
        result = {'error': False}
        notifyReadOutOnlyOnce=0
        quartileExposureReport=0
        while True:    #This loop really needs a timeout.
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []
            try:
                g_dev['mnt'].get_quick_status(self.post_mnt)   #Need to pick which pass was closest to image completion
            except:
                print ("need to get this mount status done")
            try:
                g_dev['rot'].get_quick_status(self.post_rot)
            except:
                print ("ECO has no rotator")
            g_dev['foc'].get_quick_status(self.post_foc)
            try:
                g_dev['ocn'].get_quick_status(self.post_ocn)
            except:
                print ("ECO has no ocn yet")
            if time.time() > self.status_time:
                g_dev['obs'].update_status()
                self.status_time = time.time() + 10
            if time.time() < self.completion_time:   #  NB Testing here if glob too early is delaying readout.
                time.sleep(2)
                self.t7b = time.time()
                remaining = round(self.completion_time - self.t7b, 1)
                if remaining > 0:
                    print (str(round(remaining, 1))+'sec.', str(round(100*remaining/cycle_time, 1))+'%')
                    if quartileExposureReport==0:    # Silly daft but workable exposure time reporting by MTF
                        initialRemaining=remaining
                        quartileExposureReport=quartileExposureReport+1
                    if quartileExposureReport==1 and remaining < initialRemaining*.75 and initialRemaining > 30:
                        quartileExposureReport=quartileExposureReport+1
                        g_dev['obs'].send_to_user("Exposure 25% complete. Remaining: " + str(remaining) + ' sec.', p_level='INFO')
                    if quartileExposureReport==2 and remaining < initialRemaining*.50 and initialRemaining > 30:
                        quartileExposureReport=quartileExposureReport+1
                        g_dev['obs'].send_to_user("Exposure 50% complete. Remaining: " + str(remaining) + ' sec.', p_level='INFO')
                    if quartileExposureReport==3 and remaining < initialRemaining*.25 and initialRemaining > 30:
                        quartileExposureReport=quartileExposureReport+1
                        g_dev['obs'].send_to_user("Exposure 75% complete. Remaining: " + str(remaining) + ' sec.', p_level='INFO')


                continue
            incoming_image_list = []   #glob.glob(self.file_mode_path + '*.f*t*')
            self.t4 = time.time()
            try:
                pier_side = g_dev['mnt'].mount.sideOfPier
            except:
                print ("Mount doesn't use pierside")

            if (not self.use_file_mode and self._imageavailable) or (self.use_file_mode and len(incoming_image_list) >= 1):   #   self.camera.ImageReady:
                #print("reading out camera, takes ~6 seconds.")

                time.sleep(0.1)   #  This delay appears to be necessary. 20200804 WER
                self.t4p4 = time.time()
                ####self.img_safe = self.camera.ImageArray
                #NB NB Do not try to print ImageArray!!!!
                #breakpoint()
                #print (self.camera.LastImageFileName())
                #print (self.camera.AutoSavePath())
                #print (self._getImageArray())
                #breakpoint()
                self.img = np.array(self._getImageArray()).astype('uint16')
                self.t4p5 = time.time()#As read, this is a Windows Safe Array of Longs
                if frame_type in ['bias', 'dark']:
                    print("Median of full area bias or dark  image:  ", np.median(self.img),)
                #self.img = self.img.transpose()  #Need to Transpose so MIRA shows correct orientation, 0,0 lower left.
                #NB DO not do this, pass image through to AWS with as little touch as possible.

                pedastal = 0
                self.overscan = 0

                # if self.use_file_mode:
                #     time.sleep(3)
                #     tries = 0
                #     delay = 1
                #     while True and tries <10:
                #         try:
                #             new_image = fits.open(incoming_image_list[-1])  #  Sometimes glob picks up a file not yet fully formed.
                #             print("Read new image no exception thrown.")
                #             time.sleep(delay)
                #         except Exception as e:
                #             tries += 1
                #             print('In except: ', e)
                #             time.sleep(delay)
                #             new_image.close()
                #             continue
                #         self.img = new_image[0].data   #  NB We could pick up Maxim header info here
                #         #self.img = np.array(self.img).transpose()
                #         iy, ix = self.img.shape        #FITS open fixes C ordering to Fortran
                #         new_image.close()
                #         if len(self.img)*len(self.img[0]) != iy*ix:
                #             continue
                #         break
                #     print ('Grab took :  ', tries*delay, ' sec')
                # else:
                #time.sleep(0.1)   #  This delay appears to be necessary. 20200804 WER
                self.t4p4 = time.time()
                ####self.img_safe = self.camera.ImageArray
                #NB NB Do not try to print ImageArray!!!!
                #self.img = np.array(self.camera.ImageArray)
                #self.img = self.img.astype('int32')
                self.t4p5 = time.time()#As read, this is a Windows Safe Array of Longs
                #print("\n\nMedian of incoming image:  ", np.median(self.img), '\n\n')

                ###self.img = np.array(self.img_safe) # _untransposed   incoming is (4800,3211) for QHY600Pro 2:2 Bin
                #print(self.img_untransposed.shape)
                #self.img = self.img_untransposed    #   .transpose()  Only use this if Maxim has changed orientation.
                #  print('incoming shape:  ', self.img.shape)
                self.t5 = time.time()
                try:
                    pier_side = g_dev['mnt'].mount.sideOfPier    #0 == Tel Looking West, is flipped.
                except:
                    print ("This mount doesn't report sideofpier")
                # print('setup took:  ', round(self.t2 - self.t0))
                # print('time to first readout try: ', round(self.t4 - self.t2, 2), ' sec,')
                # print('to get safearray: ', round(self.t4p5 - self.t2, 2), ' sec,')
                # print('readout took: ', round(self.t5 - self.t4, 2), ' sec,')
                # print('it all took: ', round(self.t5 - self.t2, 2), ' sec,')

                #  NB NB  Be very careful this is the exact code used in build_master and calibration  modules.
                #  NB Note this is QHY600 specific code.  Needs to be supplied in camera config as sliced regions.
                pedastal = 0.0   #No Pedastal for a raw image.  SEP may need one though..
                ix, iy = self.img.shape
                #breakpoint()

                trimmed = self.img
                #This may need a re-think:   Maybe kill neg and anything really hot if there are only a few.
                #smin = np.where(square < 0)    # finds negative pixels  NB <0 where pedastal is 200. Useless!

                self.t77 = time.time()
               # print('readout, transpose & Trim took:  ', round(self.t77 - self.t4, 1), ' sec,')# marks them as 0

                # NB NB this funcion could be part of a night log usign the looger module.
                # g_dev['obs'].send_to_user("Camera has read-out image.", p_level='INFO')  # MTF - seeing if this is irrelevant info - If you know that the raw image is saved, then you also know the camera read out the image and the messages are always within seconds of each other

# =============================================================================
#                 neg_pix = np.where(trimmed < 0)
#                 print("negative pixel count:  ", len(neg_pix[0]))
#
#                 trimmed[neg_pix] = 0
#                 self.img = trimmed.astype('uint16')
#
#                 print('\n\nMedian of raw image, neg pixels removed:  ', np.median(self.img) , '\n\n')
# =============================================================================
                neg_pix = np.where(self.img < 0)
                if len(neg_pix[0]) >0: print("No. of negative pixels fixed:  ", len(neg_pix[0]))
                self.img[neg_pix] = 0
                pos_pix = np.where(self.img > 65535)
                if len(pos_pix[0]) > 0: print("No. of overflow pixels fixed:  ", len(pos_pix[0]))
                self.img[pos_pix] = 65535
                test_saturated = np.array(self.img[ix//3:ix*2//3, iy//3:iy*2//3])  # 1/9th the chip area, but central.
                bi_mean = round((test_saturated.mean() + np.median(test_saturated))/2, 1)
                if frame_type[-4:] == 'flat':   #NB use in operator
                    if bi_mean >= self.config['camera'][self.name]['settings']['saturate']:
                        print("Flat rejected, center is too bright:  ", bi_mean)
                        g_dev['obs'].send_to_user("Flat rejected, too bright.", p_level='INFO')
                        result['error'] = True
                        result['patch'] = bi_mean
                        return result   # signals to flat routine image was rejected, prompt return
                g_dev['obs'].update_status()
                counter = 0
                #Not self.post... was captured just before readout so it is accurate through the end of the exposure
                # try:
                #     avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                # except:
                #     print ("Mountymcmountmount")
                avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                try:
                    avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                except:
                    print ("No Rotator")
                try:
                    avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                except:
                    print ("no ocn")

                if frame_type[-5:] in ['focus', 'probe', "ental"]:

                    self.img = self.img #+ 100   #maintain a + pedestal for sep  THIS SHOULD not be needed for a raw input file.
                    self.img = self.img.astype("float")
                    #print(self.img.flags)
                    self.img = self.img.copy(order='C')   #  NB Should we move this up to where we read the array?
                    bkg = sep.Background(self.img)
                    self.img -= bkg
                    sources = sep.extract(self.img, 4.5, err=bkg.globalrms, minarea=15)  # Minarea should deal with hot pixels.
                    sources.sort(order = 'cflux')
                    print('No. of detections:  ', len(sources))

                    ix, iy = self.img.shape
                    r0 = 0
                    """
                    ToDo here:  1) do not deal with a source nearer than 5% to an edge.
                    2) do not pick any saturated sources.
                    3) form a histogram and then pick the median winner
                    4) generate data for a report.
                    5) save data and image for engineering runs.
                    """
                    border_x = int(ix*0.05)
                    border_y = int(iy*0.05)
                    r0 = []
                    for sourcef in sources:
                        if border_x < sourcef['x'] < ix - border_x and \
                            border_y < sourcef['y'] < iy - border_y and \
                            sourcef['peak']  < 35000 and sourcef['cpeak'] < 35000:  #Consider a lower bound
                            a0 = sourcef['a']
                            b0 = sourcef['b']
                            r0.append(round(math.sqrt(a0*a0 + b0*b0), 2))

                    scale = self.config['camera'][self.name]['settings']['pix_scale'][self.camera.BinX -1]
                    result['FWHM'] = round(np.median(r0)*scale, 3)   #@0210524 was 2x larger but a and b are diameters not radii
                    result['mean_focus'] =  avg_foc[1]
                    try:
                        valid =  0.0 <= result['FWHM']<= 20. and 100 < result['mean_focus'] < 12600
                        result['error'] = False
                    except:
                        result['error'] = True    # NB NB NB These are quick placeholders and need to be changed
                        result['FWHM']  = 3.456
                        result['mean_focus'] =  6543

                    focus_image = True
                else:
                    focus_image = False

                    #return result   #Used if focus not saved in calibs.

                try:
                    #breakpoint()
                    hdu = fits.PrimaryHDU(self.img.transpose())   #THis needs to be done to keep fits "traditional." 0,0 upper left.
                    self.img = None    #  Does this free up any resource?
                    # assign the keyword values and comment of the keyword as a tuple to write both to header.

                    hdu.header['BUNIT']    = ('adu', 'Unit of array values')
                    hdu.header['CCDXPIXE'] = (self.config['camera'][self.name]['settings']['x_pixel'], '[um] Size of unbinned pixel, in X')  # DEH maybe change config units to meters or convert to m?
                    hdu.header['CCDYPIXE'] = (self.config['camera'][self.name]['settings']['y_pixel'], '[um] Size of unbinned pixel, in Y')
                    hdu.header['XPIXSZ']   = (round(float(hdu.header['CCDXPIXE']*self.camera.BinX), 3), '[um] Size of binned pixel')
                    hdu.header['YPIXSZ']   = (round(float(hdu.header['CCDYPIXE']*self.camera.BinY), 3), '[um] Size of binned pixel')
                    try:
                        hdu.header['XBINING'] = (self.camera.BinX, 'Pixel binning in x direction')
                        hdu.header['YBINING'] = (self.camera.BinY, 'Pixel binning in y direction')
                    except:
                        hdu.header['XBINING'] = (1, 'Pixel binning in x direction')
                        hdu.header['YBINING'] = (1, 'Pixel binning in y direction')
                    hdu.header['CCDSUM']   = (self.ccd_sum, 'Sum of chip binning')
                    # DEH pulls from config; master config will need to include keyword, or this line will need to change

                    hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
                    hdu.header['RDOUTM'] = (self.config['camera'][self.name]['settings']['readout_mode'], 'Camera readout mode')
                    hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
                    if self.maxim:

                        hdu.header['CCDSTEMP'] = (round(self.camera.TemperatureSetpoint, 3), '[C] CCD set temperature')
                        hdu.header['CCDATEMP'] = (round(self.camera.Temperature, 3), '[C] CCD actual temperature')

                    if self.ascom:
                        hdu.header['CCDSTEMP'] = (round(self.camera.SetCCDTemperature, 3), '[C] CCD set temperature')
                        hdu.header['CCDATEMP'] = (round(self.camera.CCDTemperature, 3), '[C] CCD actual temperature')
                    hdu.header['COOLERON'] = self._cooler_on()
                    hdu.header['SITEID'] = self.config['site_id'].replace('-','').replace('_','')
                    hdu.header['TELID'] = self.config['telescope']['telescope1']['telescop'][:4]
                    hdu.header['PTRTEL'] = self.config['telescope']['telescope1']['ptrtel']
                    #breakpoint()
                    hdu.header['TELESCOP'] = (self.config['telescope']['telescope1']['desc'], 'Name of the telescope')  #20220901 Deleted ['desc'] WER
                    hdu.header['PROPID'] = 'ptr-' + self.config['site_id'] + '-001-0001'
                    hdu.header['BLKUID']   = ('1234567890', 'Just a placeholder right now. WER')
                    hdu.header['INSTRUME'] = (self.alias, 'Name of camera')
                    hdu.header['CAMNAME']  = (self.camera_model, 'Instrument used')
                    hdu.header['DETECTOR'] = (self.config['camera'][self.name]['detector'], 'Name of camera detector')
                    hdu.header['CAMMANUF'] = (self.config['camera'][self.name]['manufacturer'], 'Name of camera manufacturer')
                    hdu.header['GAIN']     = (self.config['camera'][self.name]['settings']['reference_gain'][self.camera.BinX - 1], '[e-/ADU] Pixel gain')
                    hdu.header['RDNOISE']  = (self.config['camera'][self.name]['settings']['reference_noise'][self.camera.BinX - 1], '[e-/pixel] Read noise')
                    hdu.header['CMOSCAM']  = (self.is_cmos, 'Is CMOS camera')
                    hdu.header['FULLWELL'] = (self.config['camera'][self.name]['settings']['fullwell_capacity'][self.camera.BinX - 1], 'Full well capacity')
                    hdu.header['CMOSGAIN']  = (0, 'CMOS Camera System Gain')
                    hdu.header['CMOSOFFS']  = (10, 'CMOS Camera offset')
                    hdu.header['CAMOFFS']  = (10, 'Camera offset')
                    hdu.header['CAMGAIN']  = (0, 'Camera gain')
                    hdu.header['CAMUSBT']  = (60, 'Camera USB traffic')
                    hdu.header['TIMESYS']  = ('UTC', 'Time system used')
                    hdu.header['DATE'] = (datetime.date.strftime(datetime.datetime.utcfromtimestamp(self.t2),'%Y-%m-%d'), 'Date FITS file was written')
                    hdu.header['DATE-OBS'] = (datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2)), \
                                              'Start date and time of observation')
                    hdu.header['DAY-OBS'] = (g_dev['day'], 'Date at start of observing night')
                    hdu.header['MJD-OBS'] = (Time(self.t2, format='unix').mjd, '[UTC days] Modified Julian Date start date/time')    #NB NB NB Needs to be fixed, mid-exposure dates as well.
                    yesterday= datetime.datetime.now() - datetime.timedelta(1)
                    hdu.header['L1PUBDAT'] = datetime.datetime.strftime(yesterday, '%Y-%m-%dT%H:%M:%S.%fZ') # IF THIS DOESN"T WORK, subtract the extra datetime ...
                    hdu.header['JD-START'] = (Time(self.t2 , format='unix').jd, '[UTC days] Julian Date at start of exposure')
                    #hdu.header['JD-HELIO'] = 'bogus'       # Heliocentric Julian Date at exposure midpoint
                    hdu.header['OBSTYPE'] = (frame_type.upper(), 'Observation type')   #This report is fixed and it should vary...NEEDS FIXING!
                    hdu.header['IMAGETYP'] = (frame_type.upper(), 'Observation type')
                    hdu.header['EXPTIME']  = (exposure_time, '[s] Requested exposure length')   # This is the exposure in seconds specified by the user
                    hdu.header['BUNIT']    = 'adu'
                    hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                    hdu.header['EXPTIME']  = exposure_time   #This is the exposure in seconds specified by the user
                    hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times
                    #hdu.header['FILTER ']  = self.current_filter  # NB this should read from the wheel!
                    #hdu.header['FILTEROF'] = self.current_offset
                    #hdu.header['EXPOSURE'] = (self.t?-self.t2, '[s] Actual exposure length')   # Calculated from actual times
                    hdu.header['FILTER']  = (self.current_filter, 'Filter type')  # NB this should read from the wheel!

                    hdu.header['FILTEROF'] = (self.current_offset, 'Filer offset')
                    hdu.header['FILTRNUM'] = ('PTR_ADON_HA_0023',  'An index into a DB')  #Get a number from the hardware or via Maxim.  NB NB why not cwl and BW instead, plus P
                    if g_dev['scr'] is not None and frame_type == 'screenflat':
                        hdu.header['SCREEN']   = (int(g_dev['scr'].bright_setting), 'Screen brightness setting')

# =============================================================================
#                     #WER:  Darren these values are nominal with respect to a raw chip and then delineate which
#                     #zones of the chip are what.  In our case we are only entering this region with Trimmed
#                     #Data  The Biassec and Trimsec are essentially zero and detsec = datasec.  This is not
#                     #always the case.  This all needs re-thinking if we are going to Run BANSAI at site.
#
#                     # DEH finish these keywords, for BANZAI. all of these should be a string of format '[x1:x2,y1:y2]'
#                     # biassec needs to change, the overscan can be a region larger than 1-pixel-wide column.
#
# =============================================================================
                    if self.bin == 1:
                        hdu.header['DATASEC'] = self.config['camera'][self.name]['settings']['data_sec'][0]
                        hdu.header['DETSEC']  = self.config['camera'][self.name]['settings']['det_sec' ][0]
                        hdu.header['BIASSEC'] = self.config['camera'][self.name]['settings']['bias_sec'][0]
                        hdu.header['TRIMSEC'] = self.config['camera'][self.name]['settings']['trim_sec'][0]
                    elif self.bin == 2:
                        hdu.header['DATASEC'] = self.config['camera'][self.name]['settings']['data_sec'][1]
                        hdu.header['DETSEC']  = self.config['camera'][self.name]['settings']['det_sec' ][1]
                        hdu.header['BIASSEC'] = self.config['camera'][self.name]['settings']['bias_sec'][1]
                        hdu.header['TRIMSEC'] = self.config['camera'][self.name]['settings']['trim_sec'][1]
                    elif self.bin == 3:
                        hdu.header['DATASEC'] = self.config['camera'][self.name]['settings']['data_sec'][2]
                        hdu.header['DETSEC']  = self.config['camera'][self.name]['settings']['det_sec' ][2]
                        hdu.header['BIASSEC'] = self.config['camera'][self.name]['settings']['bias_sec'][2]
                        hdu.header['TRIMSEC'] = self.config['camera'][self.name]['settings']['trim_sec'][2]
                    else:   # self.bin == 4:
                        hdu.header['DATASEC'] = self.config['camera'][self.name]['settings']['data_sec'][3]
                        hdu.header['DETSEC']  = self.config['camera'][self.name]['settings']['det_sec' ][3]
                        hdu.header['BIASSEC'] = self.config['camera'][self.name]['settings']['bias_sec'][3]
                        hdu.header['TRIMSEC'] = self.config['camera'][self.name]['settings']['trim_sec'][3]

                    #The above code sets up a proper, 0,0 lower left MIRA view of the raw image.  NB NB Should index by binning setting
                    hdu.header['SATURATE'] = (float(self.config['camera'][self.name]['settings']['saturate']), '[ADU] Saturation level')  # will come from config(?)
                    hdu.header['MAXLIN'] = (float(self.config['camera'][self.name]['settings']['max_linearity']), '[ADU] Non-linearity level')
                    if self.pane is not None:
                        hdu.header['MOSAIC'] = (True, 'Is mosaic')
                        hdu.header['PANE'] = self.pane


                    hdu.header['FOCAL']    = (round(float(self.config['telescope']['telescope1']['focal_length']), 2), \
                                              '[mm] Telescope focal length')
                    hdu.header['APR-DIA']  = (round(float(self.config['telescope']['telescope1']['aperture']), 2), \
                                              '[mm] Telescope aperture')
                    hdu.header['APR-AREA'] = (round(float(self.config['telescope']['telescope1']['collecting_area']), 1), \
                                              '[mm^2] Telescope collecting area')
                    hdu.header['LATITUDE']  = (round(float(self.config['latitude']), 6), '[Deg N] Telescope Latitude')
                    hdu.header['LONGITUD'] = (round(float(self.config['longitude']), 6), '[Deg E] Telescope Longitude')
                    hdu.header['HEIGHT'] = (round(float(self.config['elevation']), 2), '[m] Altitude of Telescope above sea level')
                    hdu.header['MPC-CODE'] = (self.config['mpc_code'], 'Site code')       # This is made up for now.


                    if 'object_name' in opt:
                        if opt['object_name'] != "Unspecified" and opt['object_name'] != '':
                            hdu.header['OBJECT'] = opt['object_name']
                            hdu.header['OBJSPECF']= "yes"
                    elif g_dev['mnt'].object != "Unspecified" or g_dev['mnt'].object != "empty" :
                        hdu.header['OBJECT']   = (g_dev['mnt'].object, 'Object name')
                        hdu.header['OBJSPECF']= "yes"
                    else:
                        RAtemp = g_dev['mnt'].current_icrs_ra
                        DECtemp = g_dev['mnt'].current_icrs_dec
                        RAstring = f'{RAtemp:.1f}'.replace('.','h')
                        DECstring = f'{DECtemp:.1f}'.replace('-','n').replace('.','d')
                        hdu.header['OBJECT'] = RAstring + "ra" + DECstring + "dec"
                        hdu.header['OBJSPECF']= "no"

                    if frame_type in ('bias', 'dark', 'lampflat', 'skyflat', 'screenflat', 'solarflat', 'arc'):
                        hdu.header['OBJECT'] = frame_type
                    if not any("OBJECT" in s for s in hdu.header.keys()):
                        RAtemp = g_dev['mnt'].current_icrs_ra
                        DECtemp = g_dev['mnt'].current_icrs_dec
                        RAstring = f'{RAtemp:.1f}'.replace('.','h')
                        DECstring = f'{DECtemp:.1f}'.replace('-','n').replace('.','d')
                        hdu.header['OBJECT'] = RAstring + "ra" + DECstring + "dec"
                        hdu.header['OBJSPECF']= "no"

                    ## 16 August 22: MTF - LCO (and many others) currently use decimal degrees for basically everything, so I've updated the fits header for that.
                    ## ALSO you reported that RA is in degrees, but provided it in hours anyway! I multiplied that by 15
                    hdu.header['RA']  = (float(g_dev['mnt'].current_icrs_ra) * 15, '[deg] Telescope right ascension')
                    hdu.header['DEC'] = (g_dev['mnt'].current_icrs_dec, '[deg] Telescope declination')

                    hdu.header['ORIGRA'] = hdu.header['RA']
                    hdu.header['ORIGDEC'] = hdu.header['DEC']

                    hdu.header['RAhrs']  = (g_dev['mnt'].current_icrs_ra, '[hrs] Telescope right ascension')
                    hdu.header['RA-HMS'] = (ptr_utility.hToH_MS(g_dev['mnt'].current_icrs_ra), '[HH MM SS sss] Telescope right ascension')
                    hdu.header['DEC-DMS'] = (ptr_utility.dToD_MS(g_dev['mnt'].current_icrs_dec), '[sDD MM SS ss] Telescope declination')


                    hdu.header['TARG-CHK'] = ((g_dev['mnt'].current_icrs_ra * 15) + g_dev['mnt'].current_icrs_dec, '[deg] Sum of RA and dec')
                    hdu.header['CATNAME']  = (g_dev['mnt'].object, 'Catalog object name')
                    hdu.header['CAT-RA']   = (float(g_dev['mnt'].current_icrs_ra) * 15, '[deg] Catalog RA of object')
                    hdu.header['CAT-DEC']  = (g_dev['mnt'].current_icrs_dec, '[deg] Catalog Dec of object')
                    hdu.header['TARGRA']  = float(g_dev['mnt'].current_icrs_ra) * 15
                    hdu.header['TARGDEC'] = g_dev['mnt'].current_icrs_dec
                    try:
                        hdu.header['SID-TIME'] = (self.pre_mnt[3], '[deg] Sidereal time')
                        hdu.header['OBJCTRA']  = (float(self.pre_mnt[1])*15, '[deg] Object RA')
                        hdu.header['OBJCTDEC'] = (self.pre_mnt[2], '[deg] Object dec')
                    except:
                        print ("problem with the premount?")
                    #hdu.header['OBJCTRA2'] = (self.pre_mnt[1], '[deg] Object RA 2')
                    #hdu.header['OBJCDEC2'] = (self.pre_mnt[2], '[deg] Object dec 2')
                    #hdu.header['OBRARATE'] = self.pre_mnt[4]
                    #hdu.header['OBDECRAT'] = self.pre_mnt[5]
                    try:
                        hdu.header['OBSERVER'] = (self.user_name, 'Observer name')  # userid
                    except:
                        hdu.header['OBSERVER'] = ("kilroy visited", 'Observer name')  # userid
                    hdu.header['OBSNOTE']  = self.hint[0:54]            #Needs to be truncated.
                    if self.maxim:
                        hdu.header['FLIPSTAT'] = 'None'   # This is a maxim camera setup, not a flip status



                    #hdu.header['SEQCOUNT'] = (int(counter), 'Image sequence counter')
                    hdu.header['DITHER']   = (0, '[] Dither')
                    hdu.header['OPERATOR'] = ("WER", 'Site operator')
                    hdu.header['ENCLOSUR'] = (self.config['enclosure']['enclosure1']['name'], 'Enclosure description')   # "Clamshell"   #Need to document shutter status, azimuth, internal light.
                    #NB NB NB Need to add other dome status reports
                    if g_dev['enc'].is_dome:
                        hdu.header['DOMEAZ'] = (g_dev['enc'].status['dome_azimuth'], 'Dome azimuth')
                    #else:
                    #     hdu.header['ENCAZ']    = ("", '[deg] Enclosure azimuth')   #Need to document shutter status, azimuth, internal light.
                    hdu.header['ENCLIGHT'] = ("Off/White/Red/NIR", 'Enclosure lights')
                    hdu.header['ENCRLIGT'] = ("", 'Enclosure red lights state')
                    hdu.header['ENCWLIGT'] = ("", 'Enclosure white lights state')
                    if g_dev['enc'] is not None:
                        try:

                            hdu.header['ENC1STAT'] = g_dev['enc'].status['shutter_status']  #['shutter_status'], 'Shutter status')   #"Open/Closed" enclosure 1 status
                        except:
                            pass

                    #  if gather_status:
                    hdu.header['MNT-SIDT'] = (avg_mnt['sidereal_time'], '[hrs] Mount sidereal time')
                    hdu.header['MNT-RA']   = (float(avg_mnt['right_ascension'])*15, '[deg] Mount RA')
                    ha = avg_mnt['sidereal_time'] - avg_mnt['right_ascension']
                    while ha >= 12:
                        ha -= 24.
                    while ha < -12:
                        ha += 24.
                    hdu.header['MNT-HA']   = (round(ha, 5), '[hrs] Average mount hour angle')  #Note these are average mount observed values.
                    g_dev['ha'] = round(ha, 5)
                    hdu.header['MNT-DEC']  = (avg_mnt['declination'], '[deg] Average mount declination')
                    hdu.header['MNT-RAV']  = (avg_mnt['tracking_right_ascension_rate'], '[] Mount tracking RA rate')
                    hdu.header['MNT-DECV'] = (avg_mnt['tracking_declination_rate'], '[] Mount tracking dec rate')
                    hdu.header['AZIMUTH '] = (avg_mnt['azimuth'], '[deg] Azimuth axis positions')
                    hdu.header['ALTITUDE'] = (avg_mnt['altitude'], '[deg] Altitude axis position')
                    hdu.header['ZENITH'] = (avg_mnt['zenith_distance'], '[deg] Zenith')
                    hdu.header['AIRMASS'] = (avg_mnt['airmass'], 'Effective mean airmass')
                    g_dev['airmass'] = float(avg_mnt['airmass'])
                    hdu.header['REFRACT'] = (round(g_dev['mnt'].refraction_rev, 3),'asec')
                    hdu.header['MNTRDSYS'] = (avg_mnt['coordinate_system'], 'Mount coordinate system')
                    hdu.header['POINTINS'] = (avg_mnt['instrument'], '')
                    hdu.header['MNT-PARK'] = (avg_mnt['is_parked'], 'Mount is parked')
                    hdu.header['MNT-SLEW'] = (avg_mnt['is_slewing'], 'Mount is slewing')
                    hdu.header['MNT-TRAK'] = (avg_mnt['is_tracking'], 'Mount is tracking')
                    #if self.config['site'] == 'mrc':
                    try:
                        if pier_side == 0:
                            hdu.header['PIERSIDE'] = ('Look West', 'Pier on  East side')
                            hdu.header['IMGFLIP'] = (True, 'Is flipped')
                            pier_string = 'lw-'
                        elif pier_side == 1:
                            hdu.header['PIERSIDE'] = ('Look East', 'Pier on West side')
                            hdu.header['IMGFLIP'] = (False, 'Is flipped')
                            pier_string = 'le-'
                    except:
                        hdu.header['PIERSIDE'] = 'Undefined'
                        pier_string = ''
                    hdu.header['HACORR'] = (g_dev['mnt'].ha_corr, '[deg] Hour angle correction')    #Should these be averaged?
                    hdu.header['DECCORR'] = (g_dev['mnt'].dec_corr, '[deg] Declination correction')

                    hdu.header['OTA'] = "Main"
                    hdu.header['SELECTEL'] = ("tel1", "Nominted OTA for pointing")
                    try:
                        hdu.header['ROTATOR']  = (self.config['rotator']['rotator1']['name'], 'Rotator name')
                        hdu.header['ROTANGLE'] = (avg_rot[1], '[deg] Rotator angle')
                        hdu.header['ROTMOVNG'] = (avg_rot[2], 'Rotator is moving')
                    except:
                        print ("have to have no rotator header itesm when no rotator")

                    try:
                        hdu.header['FOCUS'] = (self.config['focuser']['focuser1']['name'], 'Focuser name')
                        hdu.header['FOCUSPOS'] = (avg_foc[1], '[um] Focuser position')
                        hdu.header['FOCUSTMP'] = (avg_foc[2], '[C] Focuser temperature')
                        hdu.header['FOCUSMOV'] = (avg_foc[3], 'Focuser is moving')
                    except:
                        print ("There is something fishy in the focuser routine")


                    try:
                        hdu.header['WXSTATE'] = (g_dev['ocn'].wx_is_ok, 'Weather system state')
                        hdu.header['SKY-TEMP'] = (avg_ocn[1], '[C] Sky temperature')
                        hdu.header['AIR-TEMP'] = (avg_ocn[2], '[C] External temperature')
                        hdu.header['HUMIDITY'] = (avg_ocn[3], '[%] Percentage humidity')
                        hdu.header['DEWPOINT'] = (avg_ocn[4], '[C] Dew point')
                        hdu.header['WINDSPEE'] = (avg_ocn[5], '[km/h] Wind speed')
                        hdu.header['PRESSURE'] = (avg_ocn[6], '[mbar] Atmospheric pressure')
                        hdu.header['CALC-LUX'] = (avg_ocn[7], '[mag/arcsec^2] Expected sky brightness')
                        hdu.header['SKYMAG']  = (avg_ocn[8], '[mag/arcsec^2] Measured sky brightness')
                    except:
                        print ("have to not have ocn header items when no ocn")

                    self.pix_ang = (self.config['camera'][self.name]['settings']['x_pixel']*self.camera.BinX/(float(self.config['telescope'] \
                                              ['telescope1']['focal_length'])*1000.))
                    hdu.header['PIXSCALE'] = (round(math.degrees(math.atan(self.pix_ang))*3600., 4), '[arcsec/pixel] Nominal pixel scale on sky')
                    hdu.header['REQNUM']   = ('00000001', 'Request number')
                    hdu.header['ISMASTER'] = (False, 'Is master image')

                    current_camera_name = self.alias
                    next_seq = next_sequence(current_camera_name)
                    hdu.header['FRAMENUM'] = (int(next_seq), 'Running frame number')
                    # DEH I need to understand these keywords better before writing header comments.
                    if pedastal is not None:
                        hdu.header['PEDESTAL'] = (-pedastal,  'adu, add this for zero based image.')
                        hdu.header['PATCH']    = bi_mean - pedastal    #  A crude value for the central exposure - pedastal    #  A crude value for the central exposure
                    else:
                        hdu.header['PEDESTAL'] = (0.0, 'Dummy value for a raw image')
                        hdu.header['PATCH']    = bi_mean    #  A crude value for the central exposure
                    hdu.header['ERRORVAL'] = 0
                    hdu.header['IMGAREA' ] = opt['area']
                    hdu.header['XORGSUBF'] = self.camera_start_x    #This makes little sense to fix...  NB ALL NEEDS TO COME FROM CONFIG!!
                    hdu.header['YORGSUBF'] = self.camera_start_y


                    #hdu.header['BLKSDATE'] = ('None', 'Group unique ID

                    try:
                        hdu.header['USERNAME'] = self.user_name
                        hdu.header ['USERID']  = self.user_id
                    except:

                        hdu.header['USERNAME'] = self.last_user_name
                        hdu.header ['USERID']  = self.last_user_id
                        #print("User_name or id not found, using prior.")  #Insert last user nameand ID here if they are not supplied.

                    # NB This needs more development
                    im_type = 'EX'   #or EN for engineering....
                    f_ext = ""

                    if frame_type in ('bias', 'dark', 'lampflat', 'skyflat', 'screenflat', 'solarflat', 'arc'):
                        f_ext = "-"
                        if opt['area'] == 150:
                            f_ext += 'f'
                        if frame_type[0:4] in ('bias', 'dark'):
                            f_ext += frame_type[0] + "_" + str(self.camera.BinX)
                        if frame_type in ('lampflat', 'skyflat',' screenflat',  'solarflat', 'arc', 'expose'):
                            f_ext += frame_type[:2] + "_" + str(self.camera.BinX) + '_' + str(self.current_filter)
                    # if frame_type[-4:] == 'flat':
                    #     f_ext = '-' + str(self.current_filter)    #Append flat string to local image name
                    cal_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                                                next_seq  + f_ext + '-'  + im_type + '00.fits'
                    raw_name00 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '00.fits'
                    #fzraw_name00 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                    #    next_seq  + '-' + im_type + '00.fits.fz'
                    red_name01 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '01.fits'
                    red_name01_lcl = red_name01[:-9]+ pier_string + self.current_filter +"-" + red_name01[-9:]
                    if self.pane is not None:
                        red_name01_lcl = red_name01_lcl[:-9] + pier_string + 'p' + str(abs(self.pane)) + "-" + red_name01_lcl[-9:]
                    #Cal_ and raw_ names are confusing
                    i768sq_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '10.fits'
                    jpeg_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '10.jpg'
                    text_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' +  im_type + '00.txt'
                    im_path_r = self.camera_path

                    #lng_path = self.lng_path

                    hdu.header['FILEPATH'] = str(im_path_r) +'to_AWS/'
                    hdu.header['FILENAME'] = str(raw_name00 + '.fz')

                    try: #  NB relocate this to Expose entry area.  Fill out except.  Might want to check on available space.
                        im_path_r = self.camera_path
                        os.makedirs(im_path_r + g_dev['day'] + '/to_AWS/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/raw/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/calib/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/reduced/', exist_ok=True)
                        im_path   = im_path_r + g_dev['day'] + '/to_AWS/'
                        raw_path  = im_path_r + g_dev['day'] + '/raw/'
                        cal_path  = im_path_r +  g_dev['day'] +'/calib/'
                        red_path  = im_path_r + g_dev['day'] + '/reduced/'

                    except:
                        pass

                    text = open(im_path + text_name, 'w')  #This is needed by AWS to set up database.
                    text.write(str(hdu.header))
                    text.close()
                    text_data_size = min(len(str(hdu.header)) - 4096, 2048)
                    paths = {'im_path':  im_path,
                             'raw_path':  raw_path,
                             'cal_path':  cal_path,
                             'red_path':  red_path,
                             'red_path_aux':  None,
                             'cal_name':  cal_name,
                             'raw_name00': raw_name00,
                             #'fzraw_name00': fzraw_name00,
                             'red_name01': red_name01,
                             'red_name01_lcl': red_name01_lcl,
                             'i768sq_name10': i768sq_name,
                             'i768sq_name11': i768sq_name,
                             'jpeg_name10': jpeg_name,
                             'jpeg_name11': jpeg_name,
                             'text_name00': text_name,
                             'text_name10': text_name,
                             'text_name11': text_name,
                             'frame_type':  frame_type
                             }
                    if  False and self.config['site'] == 'saf':    #ADD an owner specified request to do this save
                        os.makedirs(self.alt_path +  g_dev['day'] + '/reduced/', exist_ok=True)
                        red_path_aux = self.alt_path +  g_dev['day'] + '/reduced/'
                        paths['red_path_aux'] = red_path_aux
                    #script = None
                    '''
                    self.enqueue_image(text_data_size, im_path, text_name)
                    self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                    if not quick:
                        self.enqueue_image(db_data_size, im_path, db_name)
                        self.enqueue_image(raw_data_size, im_path, raw_name01)
                    '''


                    if focus_image:
                        if len(self.biasframe) > 10:
                            hdu.data=hdu.data-self.biasframe
                        #if self.darkframe == None:
                        #    print ("Skipping Bias Frame")
                        #else:
                            # Dark frame quick flash
                        if len(self.darkframe) > 10:
                            hdu.data=hdu.data-(self.darkframe*exposure_time)

                    if focus_image and not solve_it:
                        #Note we do not reduce focus images, except above in focus processing.
                        cal_name = cal_name[:-9] + 'F012' + cal_name[-7:]  # remove 'EX' add 'FO'   Could add seq to this

                        hdu.data=hdu.data.astype('float32')
                        hdu.writeto(cal_path + cal_name, overwrite=True)
                        focus_image = False
                        return result
                    if focus_image and solve_it :

                        cal_name = cal_name[:-9] + 'FS' + cal_name[-7:]  # remove 'EX' add 'FO'   Could add seq to this
                        hdu.data=hdu.data.astype('float32')
                        hdu.writeto(cal_path + cal_name, overwrite=True)
                        focus_image = False
                        try:
                            #wpath = 'C:/000ptr_saf/archive/sq01/20210528/reduced/saf-sq01-20210528-00019785-le-w-EX01.fits'
                            time_now = time.time()
                            solve = platesolve.platesolve(cal_path + cal_name, 1.10) #hdu.header['PIXSCALE'])
                            print (solve)
                            print("PW Solves: " +str(solve['ra_j2000_hours']) +str(solve['dec_j2000_degrees']))
                            TARGRA  = g_dev['mnt'].current_icrs_ra
                            TARGDEC = g_dev['mnt'].current_icrs_dec
                            RAJ2000 = solve['ra_j2000_hours']
                            DECJ2000 = solve['dec_j2000_degrees']
                            err_ha = round((TARGRA - RAJ2000)*15*3600, 1)
                            err_dec = round((TARGDEC - DECJ2000)*3600, 1)
                            print("Focus images error in ra, dec, asec:  ", err_ha, err_dec)
                            #g_dev['mnt'].set_last_reference(err_ha, err_dec, time_now)
                            if (err_ha > 100 or err_dec > 100 or err_ha < -100 or err_dec < -100) and self.config['mount']['mount1']['permissive_mount_reset'] == 'yes':
                                g_dev['mnt'].reset_mount_reference()
                                print ("I've reset the mount_reference")
                                g_dev['mnt'].current_icrs_ra = solve['ra_j2000_hours']
                                g_dev['mnt'].current_icrs_dec = solve['dec_j2000_hours']
                            elif g_dev['mnt'].pier_side_str == 'Looking West':
                                g_dev['mnt'].adjust_mount_reference(err_ha, err_dec)
                            else:
                                g_dev['mnt'].adjust_flip_reference(err_ha, err_dec)
                            #return result
                        except:
                            print(cal_path + cal_name, "  was not solved, sorry!")
                        ##    #g_dev['mnt'].reset_last_reference()
                            #return result
                           #Return to classic processing



                    # if  not script in ('True', 'true', 'On', 'on'):   #  not quick and    #Was moved 20201022 for grid
                    #     if not quick:
                    self.enqueue_for_AWS(text_data_size, im_path, text_name)
                    #### MTF - moving jpeg right up here so it gets sent as soon as humanly possible.

                    #


                    #if self.biasframe == None :
                    #    print ("Skipping Bias Frame")
                    #else:
                        # Bias frame quick flash
                    if not frame_type.lower() in ('bias', 'dark', 'flat', 'screenflat', 'skyflat'): # Don't process jpgs or small fits for biases and darks
                        hdusmall=copy.deepcopy(hdu)
                        hdusmall.data = hdusmall.data.astype('float32')

                        if len(self.biasframe) > 10:
                            hdusmall.data=hdusmall.data-self.biasframe
                        #if self.darkframe == None:
                        #    print ("Skipping Bias Frame")
                        #else:
                            # Dark frame quick flash
                        if len(self.darkframe) > 10:
                            hdusmall.data=hdusmall.data-(self.darkframe*exposure_time)
                        inputData=np.asarray(hdusmall.data)

                        inputData[inputData > self.config['camera'][self.name]['settings']['saturate']] = self.config['camera'][self.name]['settings']['saturate']
                        inputData[inputData < -100] = -100
                        inputData=inputData-np.min(inputData)
                        #inputData=np.nan_to_num(inputData)
                        hdusmall.data=inputData
                        # Getting the mode of the image.
                        #modeData =np.rint(inputData) # To do the mode properly it needs to be in integer steps - a float has too many potential values
                        #modeElement = np.argmax(mode(modeData[~np.isnan(modeData)])[1])
                        #imageMode = mode(modeData)[0][modeElement]


                        hdusmall.data = hdusmall.data.astype('int16')
                        iy, ix = hdusmall.data.shape
                        if iy == ix:
                            resized_a = resize(hdusmall.data, (1280, 1280), preserve_range=True)
                        else:
                            resized_a = resize(hdusmall.data, (int(1536*iy/ix), 1536), preserve_range=True)  #  We should trim chips so ratio is exact.
                        #print('New small fits size:  ', resized_a.shape)
                        hdusmall.data = resized_a.astype('int16')

                        # JPEG CODE
                        # New contrast scaling code:
                        stretched_data_float = Stretch().stretch(hdusmall.data)
                        stretched_256 = 255*stretched_data_float
                        hot = np.where(stretched_256 > 255)
                        cold = np.where(stretched_256 < 0)
                        stretched_256[hot] = 255
                        stretched_256[cold] = 0
                        #print("pre-unit8< hot, cold:  ", len(hot[0]), len(cold[0]))
                        stretched_data_uint8 = stretched_256.astype('uint8')  # Eliminates a user warning
                        hot = np.where(stretched_data_uint8 > 255)
                        cold = np.where(stretched_data_uint8 < 0)
                        stretched_data_uint8[hot] = 255
                        stretched_data_uint8[cold] = 0
                        #print("post-unit8< hot, cold:  ", len(hot[0]), len(cold[0]))
                        imsave(paths['im_path'] + paths['jpeg_name10'], stretched_data_uint8)
                        #img4 = stretched_data_uint8  # keep old name for compatibility

                        jpeg_data_size = abs(stretched_data_uint8.size - 1024)                # istd = np.std(hdu.data)
                        # JPEG CODE

                        # enqueue the jpeg quickly up.
                        if not no_AWS:
                            g_dev['cam'].enqueue_for_AWS(jpeg_data_size, paths['im_path'], paths['jpeg_name10'])

                        # assemble the small fits and send that up quickly.
                        i768sq_data_size = hdusmall.data.size
                        # print('ABOUT to print paths.')
                        # print('Sending to:  ', paths['im_path'])
                        # print('Also to:     ', paths['i768sq_name10'])

                        #hdu.writeto(paths['im_path'] + paths['i768sq_name10'], overwrite=True)
                        # This is the new fz file for the small fits, the above thing that gets bz2'ed will be deleted
                        hdufz=fits.CompImageHDU(np.asarray(hdusmall.data, dtype=np.float32), hdusmall.header)
                        hdufz.verify('fix')
                        hdufz.writeto(paths['im_path'] + paths['i768sq_name10'] +'.fz')

                        #hdu.data = resized_a.astype('float')
                        if not no_AWS:
                            g_dev['cam'].enqueue_for_AWS(i768sq_data_size, paths['im_path'], paths['i768sq_name10'] +'.fz')

                            g_dev['obs'].send_to_user("A preview image has been sent to the GUI.", p_level='INFO') ## MTF says that this isn't actuallytrue and isn't actually informative! Will comment out and see if anyone notices.....








                    hdu.writeto(raw_path + raw_name00, overwrite=False)   #Save full raw file locally
                    ## Need to make an FZ file here before things get changed below
                    print ("Making an fz file")
                    hdufz=fits.CompImageHDU(np.asarray(hdu.data, dtype=np.float32), hdu.header)
                    #hdufz.header['FILENAME']=raw_path + raw_name00 +'.fz'
                    hdufz.verify('fix')
                    hdufz.writeto(raw_path + raw_name00 +'.fz')
                    #print('Raw:  ', raw_path + raw_name00)
                    #calibrate(hdu, cal_path+cal_name)

                    self.to_reduce((paths, hdu))
                    #Here we should decimate and send big fits

                    #g_dev['obs'].send_to_user("Raw image saved at the observatory. ", p_level='INFO')
                    #Moved into Calibrate to eliminate race conditon is saving this.
                    # if frame_type in ('bias', 'dark', 'screenflat', 'skyflat'):
                    #     if not self.hint[0:54] == 'Flush':
                    #         hdu.writeto(cal_path + cal_name, overwrite=True)
                    #     else:
                    #         pass
                    #     try:
                    #         os.remove(self.camera_path + 'newest.fits')
                    #     except:
                    #         pass    #  print ("File newest.fits not found, this is probably OK")
                    #     result = {'patch': bi_mean,
                    #             'calc_sky': 0}  #avg_ocn[7]}
                    #     self.exposure_busy = False
                    #     return result #  Note we are not calibrating. Just saving the file.
                    # elif frame_type in ['light']:
                    #     self.enqueue_for_AWS(reduced_data_size, im_path, red_name01)

                   #print("\n\Finish-Exposure is complete, saved:  " + raw_name00)#, raw_data_size, '\n')
                    g_dev['obs'].update_status()
                    result['mean_focus'] = avg_foc[1]
                    try:
                        result['mean_rotation'] = avg_rot[1]
                    except:
                        print ("we ain't got no rotator matey")
                    if not focus_image:
                        result['FWHM'] = None
                    result['half_FD'] = None
                    if self.overscan is not None:
                        result['patch'] = bi_mean - self.overscan
                    else:
                       result['patch'] = bi_mean
                    result['calc_sky'] = 0 #avg_ocn[7]
                    result['temperature'] = 0 #avg_foc[2]
                    # print('GAIN: ', result['patch'], avg_ocn[7], exposure_time, 'g: ', \
                    #      g := round(result['patch']/avg_ocn[7]/exposure_time, 6))

                    result['gain'] = 0
                    result['filter'] = self.current_filter
                    result['error'] == False
                    #g_dev['obs'].send_to_user("Expose cycle completed.", p_level='INFO')    MTF -- I am commenting this out... this actually doesn't add information for the user, mayhaps for us but no use for the observer who has just been told the image was saved anyway
                    self.exposure_busy = False
                    return result
                except Exception as e:
                    print('Header assembly block failed: ', e)
                    print(traceback.format_exc())
                    try:
                        hdu = None
                    except:
                        pass
                    # try:
                    #     hdu1 = None
                    # except:
                    #     pass
                    self.t7 = time.time()
                    result = {'error': True}
                self.exposure_busy = False
                return result
            else:
                time.sleep(1)
                #g_dev['obs'].update_status()
                self.t7 = time.time()
                remaining = round(self.completion_time - self.t7, 1)
                # if remaining > 0:
                #     print (round(remaining, 1), round(100*remaining/self.expsoure, 1))

                if remaining < 0 and notifyReadOutOnlyOnce == 0:
                    print("Reading out image. Time remaining: " + str(round(13 + remaining, 1)), ' sec')
                    g_dev['obs'].send_to_user("Reading out image. Time remaining: " + str(round(13 + remaining, 1)) + ' s.', p_level='INFO')
                    notifyReadOutOnlyOnce=1
                if remaining < -30:
                    print("Camera timed out; probably is no longer connected, resetting it now.")
                    g_dev['obs'].send_to_user("Camera timed out; probably is no longer connected, resetting it now.", p_level='INFO')
                    result = {'error': True}
                    self.exposure_busy = False
                    return result


                #it takes about 15 seconds from AWS to get here for a bias.
        # except Exception as e:

        #     counter += 1
        #     time.sleep(.01)
        #     print('Was waiting for exposure end, arriving here is bad news:  ', e)

        # result = {'error': True}
        # return  result
    def enqueue_for_AWS(self, priority, im_path, name):
        image = (im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)

    def to_reduce(self, to_red):
        #print('Passed to to_reduce:  ', to_red[0], to_red[1].data.shape, to_red[1].header['FILTER'])
        g_dev['obs'].reduce_queue.put(to_red, block=False)


    def mode(ndarray,axis=0):
        if ndarray.size == 1:
            return (ndarray[0],1)
        elif ndarray.size == 0:
            raise Exception('Attempted to find mode on an empty array!')
        try:
            axis = [i for i in range(ndarray.ndim)][axis]
        except IndexError:
            raise Exception('Axis %i out of range for array with %i dimension(s)' % (axis,ndarray.ndim))
        srt = np.sort(ndarray,axis=axis)
        dif = np.diff(srt,axis=axis)
        shape = [i for i in dif.shape]
        shape[axis] += 2
        indices = np.indices(shape)[axis]
        index = tuple([slice(None) if i != axis else slice(1,-1) for i in range(dif.ndim)])
        indices[index][dif == 0] = 0
        indices.sort(axis=axis)
        bins = np.diff(indices,axis=axis)
        location = np.argmax(bins,axis=axis)
        mesh = np.indices(bins.shape)
        index = tuple([slice(None) if i != axis else 0 for i in range(dif.ndim)])
        index = [mesh[i][index].ravel() if i != axis else location.ravel() for i in range(bins.ndim)]
        counts = bins[tuple(index)].reshape(location.shape)
        index[axis] = indices[tuple(index)]
        modals = srt[tuple(index)].reshape(location.shape)
        return (modals, counts)