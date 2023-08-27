"""
Created on Tue Apr 20 22:19:25 2021

@author: obs, wer, dhunt

"""

#import copy
import datetime
import os
#import math
import shelve
import time
import traceback
import ephem
import copy
#import json
import random
from astropy.io import fits#, ascii
from astropy.time import Time
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord, AltAz
#from astropy.table import Table
from astropy.nddata import block_reduce
from astropy import units as u
#import numpy.ma as ma
import glob
import numpy as np
#import matplotlib.pyplot as plt   # Please do not remove this import.
#import sep
#from skimage.io import imsave
#from skimage.transform import resize
#from auto_stretch.stretch import Stretch
import win32com.client
from astropy.stats import sigma_clip, mad_std
#from planewave import platesolve

#from scipy import stats
import math
#import colour
#import queue
import threading

from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)

#import requests
#Incorporate better request retry strategy
#from requests.adapters import HTTPAdapter, Retry
#reqs = requests.Session()
#retries = Retry(total=5,
#               backoff_factor=0.1,
#                status_forcelist=[ 500, 502, 503, 504 ])
#reqs.mount('http://', HTTPAdapter(max_retries=retries))

    
#from colour_demosaicing import (
#    demosaicing_CFA_Bayer_bilinear,
#    demosaicing_CFA_Bayer_Malvar2004,
#    demosaicing_CFA_Bayer_Menon2007,
#    mosaicing_CFA_Bayer)

#from PIL import Image , ImageEnhance

from devices.darkslide import Darkslide
#import ptr_utility
from global_yard import g_dev
from ptr_utility import plog
from ctypes import *


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
fill out fits headers and save the exposure.  Phase 2, and maybe  Phase 3, are wrapped in the 
retry-three-times framework. Next is Phase 4 -- local calibrate and analyze, then Phase 5 -- send to AWS.
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
dgs = "°"

# This class is for QHY camera control
class Qcam:
    LOG_LINE_NUM = 0
    # Python constants
    STR_BUFFER_SIZE = 32

    QHYCCD_SUCCESS = 0
    QHYCCD_ERROR = 0xFFFFFFFF

    stream_single_mode = 0
    stream_live_mode = 1

    bit_depth_8 = 8
    bit_depth_16 = 16
    readmodenum=c_int32(2)
    CONTROL_BRIGHTNESS = c_int(0)
    CONTROL_GAIN = c_int(6)
    CONTROL_USBTRAFFIC = c_int(6)
    CONTROL_OFFSET = c_int(7)
    CONTROL_EXPOSURE = c_int(8)
    CAM_GPS = c_int(36)
    CAM_HUMIDITY = c_int(62)    #WER added these two new attributes.
    CAM_PRESSURE = c_int(63)
    CONTROL_CURTEMP = c_int(14)  #(14)
    CONTROL_CURPWM = c_int(15)
    CONTROL_MANULPWM = c_int(16)
    CONTROL_CFWPORT = c_int(17)
    CONTROL_CFWSLOTSNUM = c_int(44)
    CONTROL_COOLER = c_int(18)

    camera_params = {}

    so = None

    def __init__(self, dll_path):
        

        self.so = windll.LoadLibrary(dll_path)

        self.so.GetQHYCCDParam.restype = c_double
        self.so.GetQHYCCDParam.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDControlAvailable.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDCFWPlugged.argtypes = [c_void_p]

        self.so.GetQHYCCDMemLength.restype = c_ulong
        self.so.OpenQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.argtypes = [c_void_p]
        # self.so.EnableQHYCCDMessage(c_bool(False))
        self.so.EnableQHYCCDMessage(c_bool(True))
        self.so.SetQHYCCDStreamMode.argtypes = [c_void_p, c_uint8]
        self.so.InitQHYCCD.argtypes = [c_void_p]
        self.so.ExpQHYCCDSingleFrame.argtypes = [c_void_p]
        self.so.GetQHYCCDMemLength.argtypes = [c_void_p]
        self.so.BeginQHYCCDLive.argtypes = [c_void_p]
        self.so.SetQHYCCDResolution.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_uint32]
        self.so.GetQHYCCDSingleFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDChipInfo.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDLiveFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.SetQHYCCDParam.argtypes = [c_void_p, c_int, c_double]
        self.so.SetQHYCCDBitsMode.argtypes = [c_void_p, c_uint32]

        #self.so.CancelQHYCCDExposingAndReadout.restype = c_int64
        self.so.CancelQHYCCDExposingAndReadout.argtypes = [c_int64]

        # self.so.GetQHYCCDNumberOfReadModes.restype = c_uint32
        # self.so.GetQHYCCDNumberOfReadModes.argtypes = [c_void_p, c_void_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32, c_char_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32]
        #self.so.GetQHYCCDReadMode.argtypes = [c_void_p,c_uint32]
        self.so.GetReadModesNumber.argtypes = [c_char_p, c_void_p]
        self.so.GetReadModeName.argtypes = [c_char_p, c_uint32, c_char_p]
        self.so.SetQHYCCDReadMode.argtypes = [c_void_p, c_uint32]

    @staticmethod
    def slot_index_to_param(val_slot_index):
        val_slot_index = val_slot_index + 48
        return val_slot_index

    @staticmethod
    def slot_value_to_index(val_slot_value):
        if val_slot_value == 78:
            return -1
        return val_slot_value - 48


@CFUNCTYPE(None, c_char_p)
def pnp_in(cam_id):
    
    plog("QHY Direct connect to camera: %s" % cam_id.decode('utf-8'))
    global qhycam_id
    qhycam_id=cam_id
    init_camera_param(qhycam_id)
    qhycam.camera_params[qhycam_id]['connect_to_pc'] = True   


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id.decode('utf-8'))

# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
def init_camera_param(cam_id):
    if not qhycam.camera_params.keys().__contains__(cam_id):
        qhycam.camera_params[cam_id] = {'connect_to_pc': False,
                                     'connect_to_sdk': False,
                                     'EXPOSURE': c_double(1000.0 * 1000.0),
                                     #'GAIN': c_double(54.0),
                                     'GAIN': c_double(54.0),
                                     'CONTROL_BRIGHTNESS': c_int(0),
                                     #'CONTROL_GAIN': c_int(6),
                                     'CONTROL_GAIN': c_int(6),
                                     #'CONTROL_USBTRAFFIC': c_int(6),
                                     'CONTROL_USBTRAFFIC': c_int(6),
                                     'CONTROL_EXPOSURE': c_int(8),
                                     #'CONTROL_CURTEMP': c_int(14),
                                     'CONTROL_CURTEMP': c_double(14),
                                     'CONTROL_CURPWM': c_int(15),
                                     'CONTROL_MANULPWM': c_int(16),
                                     'CONTROL_COOLER': c_int(18),
                                     'chip_width': c_double(),
                                     'chip_height': c_double(),
                                     'image_width': c_uint32(),
                                     'image_height': c_uint32(),
                                     'pixel_width': c_double(),
                                     'pixel_height': c_double(),
                                     'bits_per_pixel': c_uint32(),
                                     'mem_len': c_ulong(),
                                     'stream_mode': c_uint8(0),
                                     #'read_mode': c_uint8(0),
                                     'channels': c_uint32(),
                                     'read_mode_number': c_uint32(g_dev['obs'].config["camera"]["camera_1_1"]["settings"]['direct_qhy_readout_mode']),
                                     'read_mode_index': c_uint32(g_dev['obs'].config["camera"]["camera_1_1"]["settings"]['direct_qhy_readout_mode']),
                                     'read_mode_name': c_char('-'.encode('utf-8')),
                                     'prev_img_data': c_void_p(0),
                                     'prev_img': None,
                                     'handle': None,
                                     }



# These should eventually be in a utility module
def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    try:
        seq = camShelf[sKey]  # get an 8 character string
    except:
        plog ("Failed to get seq key, starting from zero again")
        seq=1
    seqInt = int(seq)
    seqInt += 1
    seq = ("0000000000" + str(seqInt))[-8:]
    camShelf["Sequence"] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq


def test_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    seq = camShelf[sKey]  # get an 8 character string
    camShelf.close()
    SEQ_Counter = seq
    return seq


def reset_sequence(pCamera):
    try:
        camShelf = shelve.open(
            g_dev['obs'].obsid_path + "ptr_night_shelf/" + str(pCamera) + str(g_dev['obs'].name)
        )
        seqInt = int(-1)
        seqInt += 1
        seq = ("0000000000" + str(seqInt))[-8:]
        plog("Making new seq: ", pCamera, seq)
        camShelf["Sequence"] = seq
        camShelf.close()
        return seq
    except:
        plog("Nothing on the cam shelf in reset_sequence")
        return None
    # seq = camShelf['Sequence']      # a 9 character string


# Default filter needs to be pulled from site camera or filter config


class Camera:
    """A camera instrument.

    See http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm

    The filter, focuser, rotator must be set up prior to camera.
    Since this is a class definition we need to pre-enter with a list of classes
    to be created by a camera factory.
    """

    def __init__(self, driver: str, name: str, config: dict):
        """
        Added monkey patches to make ASCOM/Maxim differences
        go away from the bulk of the in-line code.
        Try to be more consistent about use of filter names rather than
        numbers.

        Outline: if there is a selector then iterate over it for cameras
        and ag's to create.  Name instances cam or ag_<tel>_<sel-port>'.
        Once this is done g_dev['cam'] refers to the selected instance.
        """
        
        self.last_user_name = "none"
        self.last_user_id = "none"
        self.user_name = "none"
        self.user_id = "none"

        self.name = name
        self.driver = driver
        g_dev[name + "_cam_retry_driver"] = driver
        g_dev[name + "_cam_retry_name"] = name
        g_dev[name + "_cam_retry_config"] = config
        g_dev[name + "_cam_retry_doit"] = False
        g_dev[name] = self
        if name == "camera_1_1":  # NBDefaults sets up Selected 'cam'
            g_dev["cam"] = self
        self.config = config
        self.alias = config["camera"][self.name]["name"]
        win32com.client.pythoncom.CoInitialize()
        plog(driver, name)
        if not driver == "QHYCCD_Direct_Control":
            self.camera = win32com.client.Dispatch(driver)
        else:
            self.camera = None
        self.async_exposure_lock=False # This is needed for TheSkyx (and maybe future programs) where the 
                                       # exposure has to be called from a separate thread and then waited 
                                       # for in the main thread

        # Sets up paths and structures
        
        self.obsid_path = g_dev['obs'].obsid_path
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)
        self.local_calibration_path = g_dev['obs'].local_calibration_path
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path)
        
        self.archive_path = self.config["archive_path"] + self.config['obs_id'] + '/'+ "archive/"
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['obs_id']):
            os.makedirs(self.config["archive_path"] +'/' + self.config['obs_id'])
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['obs_id']+ '/'+ "archive/"):
            os.makedirs(self.config["archive_path"] +'/' + self.config['obs_id']+ '/'+ "archive/")
        self.camera_path = self.archive_path + self.alias + "/"
        if not os.path.exists(self.camera_path):
            os.makedirs(self.camera_path)
        self.alt_path = self.config[
            "alt_path"
        ]  +'/' + self.config['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.
        if not os.path.exists(self.config[
            "alt_path"
        ]):
            os.makedirs(self.config[
            "alt_path"
        ])
        
        if not os.path.exists(self.alt_path):
            os.makedirs(self.alt_path)
        self.autosave_path = self.camera_path + "autosave/"
        self.lng_path = self.camera_path + "lng/"
        self.seq_path = self.camera_path + "seq/"
        if not os.path.exists(self.autosave_path):
            os.makedirs(self.autosave_path)
        if not os.path.exists(self.lng_path):
            os.makedirs(self.lng_path)
        if not os.path.exists(self.seq_path):
            os.makedirs(self.seq_path)

        # Just need to initialise this filter thing
        self.current_offset  = 0

        """
        This section loads in the calibration files for flash calibrations
        """
        
        plog("loading flash dark, bias and flat masters frames if available")        
            
        
        self.biasFiles = {}
        self.darkFiles = {}
        self.flatFiles = {}
        self.hotFiles = {}

        g_dev['obs'].obs_id
        g_dev['cam'].alias
        tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'
     
        try:            
            tempbiasframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib + "BIAS_master_bin1.fits")
            tempbiasframe = np.array(tempbiasframe[0].data, dtype=np.float32)
            self.biasFiles.update({'1': tempbiasframe})
            del tempbiasframe
        except:
            plog("Bias frame for Binning 1 not available")
        
        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "DARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'1': tempdarkframe})
            del tempdarkframe
        except:
            plog("Dark frame for Binning 1 not available")  

        try:  
            fileList = glob.glob(self.local_calibration_path + "archive/" + self.alias + "/calibmasters/masterFlat*_bin1.npy")
            for file in fileList:
                if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                    tempflatframe=np.load(file)
                    self.flatFiles.update({file.split('_')[-2]: np.array(tempflatframe)})
                    del tempflatframe
                else:
                    self.flatFiles.update({file.split("_")[1].replace ('.npy','') + '_bin1': file})
            # To supress occasional flatfield div errors
            np.seterr(divide="ignore")
        except:
            plog("Flat frames not loaded or available")


        """
        This section connects the appropriate methods for various
        camera actions for various drivers. Each separate software
        has it's own unique and annoying way of doing things'
        """
               
        plog("Connecting to:  ", driver)

        if driver[:5].lower() == "ascom":
            plog("ASCOM camera is initializing.")
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
            self.qhydirect = False
            plog("ASCOM is connected:  ", self._connect(True))
            plog("Control is ASCOM camera driver.")

        elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
            plog("Connecting to TheSkyX")
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
            self.camera.AutoSaveOn = 1
            self.camera.Subframe = 0 
            self.description = "TheSkyX"
            self.maxim = False
            self.ascom = False
            self.theskyx = True
            self.qhydirect = False
            plog("TheSkyX is connected:  ")
            self.app = win32com.client.Dispatch("CCDSoft2XAdaptor.ccdsoft5Camera")
        
        elif driver == "QHYCCD_Direct_Control":
            global qhycam
            plog("Connecting directly to QHY")
            qhycam = Qcam(os.path.join("support_info/qhysdk/x64/qhyccd.dll"))
            
            qhycam.so.RegisterPnpEventIn(pnp_in)
            qhycam.so.RegisterPnpEventOut(pnp_out)
            qhycam.so.InitQHYCCDResource()
            qhycam.camera_params[qhycam_id]['handle'] = qhycam.so.OpenQHYCCD(qhycam_id)
            if qhycam.camera_params[qhycam_id]['handle'] is None:
                print('open camera error %s' % cam_id)
            
            read_mode=self.config["camera"][self.name]["settings"]['direct_qhy_readout_mode']
            numModes=c_int32()
            
            #success = qhycam.so.GetQHYCCDNumberOfReadModes(qhycam.camera_params[qhycam_id]['handle'],numModes)
            #print (numModes)
            success = qhycam.so.SetQHYCCDReadMode(qhycam.camera_params[qhycam_id]['handle'], read_mode) # 0 is Photographic DSO 16 Bit
            #print ("******")
            #print (success)
            #print (read_mode)
            qhycam.camera_params[qhycam_id]['stream_mode'] = c_uint8(qhycam.stream_single_mode)
            success = qhycam.so.SetQHYCCDStreamMode(qhycam.camera_params[qhycam_id]['handle'], qhycam.camera_params[qhycam_id]['stream_mode'])
           
            success = qhycam.so.InitQHYCCD(qhycam.camera_params[qhycam_id]['handle'])
            
            #qhycam.camera_params[qhycam_id]['read_mode'] = c_uint8(qhycam.stream_single_mode)
            #breakpoint()
            #success=qhycam.so.GetQHYCCDReadMode(qhycam.camera_params[qhycam_id]['handle'], qhycam.camera_params[qhycam_id]['read_mode'])
            #print (qhycam.camera_params[qhycam_id]['read_mode'])
            
            #breakpoint()
            
            
            mode_name = create_string_buffer(qhycam.STR_BUFFER_SIZE)
            qhycam.so.GetReadModeName(qhycam_id, read_mode, mode_name) # 0 is Photographic DSO 16 bit
            read_mode_name_str = mode_name.value.decode('utf-8').replace(' ', '_')
            plog ("Read Mode: "+ read_mode_name_str)
            #breakpoint()
            success = qhycam.so.SetQHYCCDBitsMode(qhycam.camera_params[qhycam_id]['handle'], c_uint32(qhycam.bit_depth_16))

            success = qhycam.so.GetQHYCCDChipInfo(qhycam.camera_params[qhycam_id]['handle'],
                                               byref(qhycam.camera_params[qhycam_id]['chip_width']),
                                               byref(qhycam.camera_params[qhycam_id]['chip_height']),
                                               byref(qhycam.camera_params[qhycam_id]['image_width']),
                                               byref(qhycam.camera_params[qhycam_id]['image_height']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_width']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_height']),
                                               byref(qhycam.camera_params[qhycam_id]['bits_per_pixel']))
           
            qhycam.camera_params[qhycam_id]['mem_len'] = qhycam.so.GetQHYCCDMemLength(qhycam.camera_params[qhycam_id]['handle'])
            i_w = qhycam.camera_params[qhycam_id]['image_width'].value
            i_h = qhycam.camera_params[qhycam_id]['image_height'].value
            
            qhycam.camera_params[qhycam_id]['prev_img_data'] = (c_uint16 * int(qhycam.camera_params[qhycam_id]['mem_len'] / 2))()
           
            success = qhycam.QHYCCD_ERROR
                        
            qhycam.so.SetQHYCCDResolution(qhycam.camera_params[qhycam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                           c_uint32(i_h))      
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()
            
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(20000))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_GAIN, c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_gain'])))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_OFFSET, c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_offset'])))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_USBTRAFFIC,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_speed'])))
                        
            self._connected = self._qhyccd_connected
            self._connect = self._qhyccd_connect
            self._set_setpoint = self._qhyccd_set_setpoint
            self._setpoint = self._qhyccd_setpoint
            self._temperature = self._qhyccd_temperature
            self._cooler_on = self._qhyccd_cooler_on
            self._set_cooler_on = self._qhyccd_set_cooler_on
            self._expose = self._qhyccd_expose
            self._stop_expose = self._qhyccd_stop_expose
            self._imageavailable = self._qhyccd_imageavailable
            self._getImageArray = self._qhyccd_getImageArray
            
            self.description = "QHYDirectControl"
            self.maxim = False
            self.ascom = False
            self.theskyx = False
            self.qhydirect = True
            
        else:
            plog("Maxim camera is initializing.")
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

            self.description = "MAXIM"
            self.maxim = True
            self.ascom = False
            self.theskyx = False
            self.qhydirect = False
            plog("Maxim is connected:  ", self._connect(True))
            self.app = win32com.client.Dispatch("Maxim.Application")
            plog(self.camera)
            self.camera.SetFullFrame()
            self.camera.SetFullFrame

            plog("Control is via Maxim camera interface, not ASCOM.")
            plog("Please note telescope is NOT connected to Maxim.")

        # Before anything, abort any exposures because sometimes a long exposure
        # e.g. 500s could keep on going with theskyx (and maybe Maxin)
        # and still be going on at a restart and crash the connection
        try:
            self._stop_expose()
        except:
            pass
        
        # NB NB Consider starting at low end of cooling and then gradually increasing it
        #plog("Cooler started @:  ", self._setpoint())
        self.setpoint = float(self.config["camera"][self.name]["settings"]["temp_setpoint"]) # This is the config setpoint
        self.current_setpoint =  float(self.config["camera"][self.name]["settings"]["temp_setpoint"]) # This setpoint can change if there is camera warming during the day etc.
        self._set_setpoint(self.setpoint)
        self.day_warm = float(self.config["camera"][self.name]["settings"]['day_warm'])
        self.day_warm_degrees = float(self.config["camera"][self.name]["settings"]['day_warm_degrees'])
        self.protect_camera_from_overheating=float(self.config["camera"][self.name]["settings"]['protect_camera_from_overheating'])
        
        plog("Cooler setpoint is now:  ", self.setpoint)
        if self.config["camera"][self.name]["settings"][
            "cooler_on"
        ]:  # NB NB why this logic, do we mean if not cooler found on, then turn it on and take the delay?
            self._set_cooler_on()
        temp, humid, pressure =self._temperature()
        plog("Cooling beginning @:  ", temp)
        plog("Humidity and pressure:  ", humid, pressure)

        if self.maxim == True:
            plog("TEC  % load:  ", self._maxim_cooler_power())
        self.current_filter = (
            0  # W in Apache Ridge case. #This should come from config, filter section
        )
        self.exposure_busy = False
        self.currently_in_smartstack_loop=False
        
        
        
        self.start_time_of_observation = time.time()
        self.current_exposure_time = 20
        
        
        self.expresult=None
        
        self.cmd_in = None
        self.t7 = None
        self.camera_message = "-"

        self.camera_known_gain=self.config["camera"][self.name]["settings"]["camera_gain"]
        self.camera_known_gain_stdev=self.config["camera"][self.name]["settings"]['camera_gain_stdev']
        self.camera_known_readnoise=self.config["camera"][self.name]["settings"]['read_noise']
        self.camera_known_readnoise_stdev=self.config["camera"][self.name]["settings"]['read_noise_stdev']
        """
        TheSkyX runs on a file mode approach to images rather 
        than a direct readout from the camera, so this path 
        is set here.
        """
        if (
            self.config["camera"]["camera_1_1"]["driver"]
            == "CCDSoft2XAdaptor.ccdsoft5Camera"
        ):
            
            self.camera.AutoSavePath = (
                self.archive_path
                + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
            )
            try:
                os.mkdir(
                    self.archive_path
                    + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
                )
            except:
                plog("Couldn't make autosave directory")
                
        """
        Actually not sure if this is useful anymore if there are no differences 
        between ccds and cmoses? This may just be used for the fits header
        at the end of the day.  Yes I just want to inform the user downstream and or
        trigger Telegraph noise correction -- all TBD. WER
        """                
        if self.config["camera"][self.name]["settings"]["is_cmos"] == True:
            self.is_cmos = True
        else:
            self.is_cmos = False
            
        
        self.camera_model = self.config["camera"][self.name]["desc"]
        # NB We are reading from the actual camera or setting as the case may be. For initial setup,
        # we pull from config for some of the various settings.
        # NB NB There is a differenc between normal cameras and the QHY when it is set to Bin2.
        if self.camera is not None:
            try:

                self.camera.BinX = 1
                self.camera.BinY = 1
            except:
                plog("Problem setting up 1x1 binning at startup.")
            
        try:
            self.overscan_x = int(
                self.config["camera"][self.name]["settings"]["overscan_x"]
            )
            self.overscan_y = int(
                self.config["camera"][self.name]["settings"]["overscan_y"]
            )
        except:
            pass

        try:
            if self.qhydirect:
                # YES! IT DOES SEEM THAT QHY HAS x and y reversed for width and height
                self.camera_y_size = qhycam.camera_params[qhycam_id]['image_width'].value
                self.camera_x_size = qhycam.camera_params[qhycam_id]['image_height'].value
                self.camera_image_size = i_h * i_w
                plog('Num X, Y are now set for QHY camera.')
            else:
                self.camera_x_size = self.camera.CameraXSize  #unbinned values. QHY returns 2
                self.camera_y_size = self.camera.CameraYSize  #unbinned
        except:
            self.camera_x_size = self.config['camera'][self.name]['settings']['CameraXSize']
            self.camera_y_size = self.config['camera'][self.name]['settings']['CameraYSize']

        self.camera_start_x = self.config["camera"][self.name]["settings"]["StartX"]
        self.camera_start_y = self.config["camera"][self.name]["settings"]["StartY"]
        if self.config["camera"][self.name]["settings"]["cam_needs_NumXY_init"] and self.camera is not None:  # WER 20230217
            try:    
                self.camera.NumX = self.camera_x_size
                self.camera.NumY = self.camera_y_size
            except:
                plog ('num x,y initialise did not work')
            try:
                self.camera.StartX = 0
                self.camera.StartY = 0
                self.camera.BinX = 1
                self.camera.BinY = 1
            except:
                plog ("self.camera setup didn't work... may be a QHY")
            
        self.camera_num_x = int(1)  #NB I do not recognize this.    WER  Apprently not used.

        self.af_mode = False
        self.af_step = -1
        self.f_spot_dia = []
        self.f_positions = []

        self.hint = None
        self.focus_cache = None
        self.darkslide = False
        self.darkslide_state = "N.A."   #Not Available.
        if self.config["camera"][self.name]["settings"]["has_darkslide"]:
            self.darkslide = True
            self.darkslide_state = 'Unknown'
            com_port = self.config["camera"][self.name]["settings"]["darkslide_com"]
            self.darkslide_instance = Darkslide(
                com_port
            )  
            # As it takes 12seconds to open, make sure it is either Open or Shut at startup
            if self.darkslide_state != 'Open':
                self.darkslide_instance.openDarkslide()
                self.darkslide_open = True
                self.darkslide_state = 'Open'

        #breakpoint()


        # A flag to tell the camera main queue
        # whether the separate sep thread has completed yet
        self.sep_processing=False
        
        try:
            seq = test_sequence(self.alias)
        except:
            reset_sequence(self.alias)
        try:
            self._stop_expose()
        except:
            pass
        
    # Patchable methods   NB These could be default ASCOM
    def _connected(self):
        plog("This is un-patched _connected method")
        return False

    def _connect(self, p_connect):
        plog("This is un-patched _connect method:  ", p_connect)
        return False

    def _setpoint(self):
        plog("This is un-patched cooler _setpoint method")
        return

    # The patches. Note these are essentially getter-setter/property constructs.

    def _theskyx_connected(self):
        return self.camera.LinkEnabled

    def _theskyx_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _theskyx_temperature(self):
        return self.camera.Temperature, 999.9, 999.9

    def _theskyx_cooler_power(self):
        return self.camera.CoolerPower

    def _theskyx_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _theskyx_cooler_on(self):
        return self.camera.RegulateTemperature  

    def _theskyx_set_cooler_on(self):
        self.camera.RegulateTemperature = True        
        return (
            self.camera.RegulateTemperature
        )  

    def _theskyx_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        self.current_setpoint = p_temp
        return self.camera.TemperatureSetpoint

    def _theskyx_setpoint(self):
        return self.camera.TemperatureSetpoint

    def theskyx_async_expose(self):
        self.async_exposure_lock=True
        tempcamera = win32com.client.Dispatch(self.driver)
        tempcamera.Connect()
        try:
            tempcamera.TakeImage()
        except:
            plog(traceback.format_exc()) 
            plog("MTF hunting this error")
            breakpoint()
        tempcamera.ShutDownTemperatureRegulationOnDisconnect = False
        self.async_exposure_lock=False

    def _theskyx_expose(self, exposure_time, bias_dark_or_light_type_frame):
        self.camera.ExposureTime = exposure_time
        if bias_dark_or_light_type_frame == 'dark':            
            self.camera.Frame = 3 
        elif bias_dark_or_light_type_frame == 'bias':            
            self.camera.Frame = 2 
        else:
            self.camera.Frame = 1        
        thread=threading.Thread(target=self.theskyx_async_expose)
        thread.start()

    def _theskyx_stop_expose(self):
        self.camera.AbortExposure()
        g_dev['cam'].expresult["stopped"] = True

    def _theskyx_imageavailable(self):
        #plog(self.camera.IsExposureComplete)
        return self.camera.IsExposureComplete

    def _theskyx_getImageArray(self): 
        imageTempOpen=fits.open(self.camera.LastImageFileName, uint=False)[0].data.astype("float32")
        try:
            os.remove(self.camera.LastImageFileName)
        except Exception as e:
            plog ("Could not remove theskyx image file: ",e)
        return imageTempOpen

    def _maxim_connected(self):
        return self.camera.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _maxim_temperature(self):
        return self.camera.Temperature, 999.9, 999.9

    def _maxim_cooler_power(self):
        return self.camera.CoolerPower

    def _maxim_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _maxim_cooler_on(self):
        return (
            self.camera.CoolerOn
        ) 

    def _maxim_set_cooler_on(self):
        self.camera.CoolerOn = True
        return (
            self.camera.CoolerOn
        )  

    def _maxim_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        self.current_setpoint = p_temp
        return self.camera.TemperatureSetpoint

    def _maxim_setpoint(self):
        return self.camera.TemperatureSetpoint

    def _maxim_expose(self, exposure_time, bias_dark_or_light_type_frame):        
        if bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark':
            imtypeb=0
        else:
            imtypeb=1        
        self.camera.Expose(exposure_time, imtypeb)

    def _maxim_stop_expose(self):
        self.camera.AbortExposure()
        g_dev['cam'].expresult["stopped"] = True

    def _maxim_imageavailable(self):
        return self.camera.ImageReady

    def _maxim_getImageArray(self):
        return np.asarray(self.camera.ImageArray)

    def _ascom_connected(self):
        return self.camera.Connected

    def _ascom_imageavailable(self):
        return self.camera.ImageReady

    def _ascom_connect(self, p_connect):
        self.camera.Connected = p_connect
        return self.camera.Connected

    def _ascom_temperature(self):
        try: 
            temptemp=self.camera.CCDTemperature
        except:
            plog ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp, 999.9, 999.9

    def _ascom_cooler_on(self):
        return (
            self.camera.CoolerOn
        )  # NB NB NB This would be a good place to put a warming protector

    def _ascom_set_cooler_on(self):
        self.camera.CoolerOn = True
        return self.camera.CoolerOn

    def _ascom_set_setpoint(self, p_temp):
        if self.camera.CanSetCCDTemperature:
            self.camera.SetCCDTemperature = float(p_temp)
            self.current_setpoint = p_temp
            return self.camera.SetCCDTemperature
        else:
            plog("Camera cannot set cooling temperature.")
            return p_temp

    def _ascom_setpoint(self):
        if self.camera.CanSetCCDTemperature:
            return self.camera.SetCCDTemperature
        else:
            plog("Camera cannot set cooling temperature: Using 10.0C")
            return 10.0

    def _ascom_expose(self, exposure_time, bias_dark_or_light_type_frame):
        
        if bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark':
            imtypeb=0
        else:
            imtypeb=1
        
        self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
        self.camera.StopExposure()  # ASCOM also has an AbortExposure method.
        g_dev['cam'].expresult["stopped"] = True

    def _ascom_getImageArray(self):
        return np.asarray(self.camera.ImageArray)


    def _qhyccd_connected(self):
        print ("MTF still has to connect QHY stuff")
        return True
    
    def _qhyccd_imageavailable(self):
        #print ("QHY CHECKING FOR IMAGE AVAILABLE - DOESN'T SEEM TO BE IMPLEMENTED! - MTF")
        #print ("AT THE SAME TIME THE READOUT IS SO RAPID, THIS FUNCTION IS SORTA MEANINGLESS FOR THE QHY.")
        return True
    
    def _qhyccd_connect(self, p_connect):
        #self.camera.Connected = p_connect
        #print ("QHY doesn't have an obvious - IS CONNECTED - function")
        return True
    
    def _qhyccd_temperature(self):
        try: 

            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
            humidity = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_HUMIDITY)
            pressure = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_PRESSURE)
        except:
            print ("failed at getting the CCD temperature, humidity or pressure.")
            temptemp=999.9
        return temptemp, humidity, pressure
    
    def _qhyccd_cooler_on(self):
        #print ("QHY DOESN'T HAVE AN IS COOLER ON METHOD)
        #breakpoint()
        #temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(self.setpoint))
        return True
    
    def _qhyccd_set_cooler_on(self):     
        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(self.current_setpoint))
        return True

    
    def _qhyccd_set_setpoint(self, p_temp):        
        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(p_temp))
        self.current_setpoint = p_temp        
        return p_temp
    
    def _qhyccd_setpoint(self):        
        try: 
            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
        except:
            print ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp
    
    def _qhyccd_expose(self, exposure_time, bias_dark_or_light_type_frame):
        
        success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exposure_time*1000*1000))
        qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
       
    def _qhyccd_stop_expose(self):
        g_dev['cam'].expresult["stopped"] = True
        try:
            qhycam.so.CancelQHYCCDExposingAndReadout(qhycam.camera_params[qhycam_id]['handle'])
        except:
            plog(traceback.format_exc()) 
            #print (success)
        
       
    def _qhyccd_getImageArray(self):
        image_width_byref = c_uint32()
        image_height_byref = c_uint32()
        bits_per_pixel_byref = c_uint32()

        success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
                                              byref(image_width_byref),
                                              byref(image_height_byref),
                                              byref(bits_per_pixel_byref),
                                              byref(qhycam.camera_params[qhycam_id]['channels']),
                                              byref(qhycam.camera_params[qhycam_id]['prev_img_data']))
        
        image = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
        image = np.reshape(image[0:self.camera_image_size], (self.camera_x_size, self.camera_y_size))
        
        return np.asarray(image)


    def create_simple_autosave(
        self,
        exp_time=0,
        img_type=0,
        speed=0,
        suffix="",
        repeat=1,
        readout_mode="Normal",
        filter_name="W",
        enabled=1,
        binning=1,
        binmode=0,
        column=1,
    ):
        # Creates a valid Maxium Autosave file.
        exp_time = round(abs(float(exp_time)), 3)
        if img_type > 3:
            img_type = 0
        repeat = abs(int(repeat))
        if repeat < 1:
            repeat = 1
        binning = abs(int(1))
        if filter_name == "":
            filter_name = "w"
        proto_file = open(self.camera_path + "seq/ptr_proto.seq")
        proto = proto_file.readlines()
        proto_file.close()

        if column == 1:
            proto[51] = proto[51][:9] + str(img_type) + proto[51][10:]
            proto[50] = proto[50][:9] + str(exp_time) + proto[50][12:]
            proto[48] = proto[48][:12] + str(suffix) + proto[48][12:]
            proto[47] = proto[47][:10] + str(speed) + proto[47][11:]
            proto[31] = proto[31][:11] + str(repeat) + proto[31][12:]
            proto[29] = proto[29][:17] + readout_mode + proto[29][23:]
            proto[13] = proto[13][:12] + filter_name + proto[13][13:]
            proto[10] = proto[10][:12] + str(enabled) + proto[10][13:]
            proto[1] = proto[1][:12] + str(binning) + proto[1][13:]
        seq_file = open(self.camera_path + "seq/ptr_mrc.seq", "w")
        for item in range(len(proto)):
            seq_file.write(proto[item])
        seq_file.close()

    def get_status(self):
        status = {}
        status["active_camera"] = self.name
        if self.config["camera"][self.name]["settings"]["has_darkslide"]:
            status["darkslide"] = g_dev["drk"].slideStatus
        else:
            status["darkslide"] = "unknown"
        # if self.exposure_busy:
        #     status["busy_lock"] = True
        # else:
        #     status["busy_lock"] = False
        #if self.maxim:
        #    cam_stat = "Not implemented yet"  #
        #if self.ascom:
        #    cam_stat = "ASCOM camera not implemented yet"  # self.camera.CameraState
        #if self.theskyx:
        #    cam_stat = "TheSkyX camera not implemented yet"  # self.camera.CameraState
        #if self.qhydirect:
        #    breakpoint()
        #    cam_stat = self.config['camera'][self.name]['name'] + " connected. # self.camera.CameraState
       
        cam_stat = self.config['camera'][self.name]['name'] + " connected." # self.camera.CameraState
        status[
            "status"
        ] = cam_stat  # The state could be expanded to be more meaningful. for instance repport TEC % TEmp, temp setpoint...
        return status

    def parse_command(self, command):
        #plog("Camera Command incoming:  ", command)
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]
        self.user_id = command["user_id"]
        if self.user_id != self.last_user_id:
            self.last_user_id = self.user_id
        self.user_name = command["user_name"]

        #plog(opt)
        if (
            "object_name" in opt
        ):
            if opt["object_name"] == "":
                opt["object_name"] = "Unspecified"
            plog("Target Name:  ", opt["object_name"])
        else:
            opt["object_name"] = "Unspecified"
            plog("Target Name:  ", opt["object_name"])
        if self.user_name != self.last_user_name:
            self.last_user_name = self.user_name
        if action == "expose":# and not self.exposure_busy:            
            
            if self.exposure_busy:
                plog("Cannot expose, camera is currently busy, waiting for exposure to clear")
                while True:
                    if self.exposure_busy:
                        time.sleep(0.5)
                    else:
                        break
            
            if req['longstack'] or req['longstack'] == 'yes':
                req['longstackname'] = (datetime.datetime.now().strftime("%d%m%y%H%M%S") + 'lngstk')
            print (req)
            #breakpoint()
            #breakpoint()
            
            if req['image_type'].lower() in (            
                "bias",
                "dark",
                "screen flat",
                "sky flat",
                "near flat",
                "thor flat",
                "arc flat",
                "lamp flat",
                "solar flat",
            ):
                manually_requested_calibration=True
            else:
                manually_requested_calibration=False
            
            self.expose_command(req, opt, user_id=command['user_id'], user_name=command['user_name'], user_roles=command['user_roles'], quick=False, manually_requested_calibration=manually_requested_calibration)
            self.exposure_busy = False  # Hangup needs to be guarded with a timeout.
            self.active_script = None

        #elif action == "expose" and 

            

            #self.expose_command(req, opt, user_id=command['user_id'], user_name=command['user_name'], user_roles=command['user_roles'], do_sep=True, quick=False)
            #self.exposure_busy = False  # Hangup needs to be guarded with a timeout.
            #self.active_script = None

        elif action == "darkslide_close":

            g_dev["drk"].closeDarkslide()
            plog("Closing the darkslide.")
            self.darkslide_state = 'Closed'
        elif action == "darkslide_open":

            g_dev["drk"].openDarkslide()
            plog("Opening the darkslide.")
            self.darkslide_state = 'Open'
        elif action == "stop":
            self.stop_command(req, opt)
            self.exposure_busy = False
            plog("STOP  STOP  STOP received.")
        else:

            plog(f"Command <{action}> not recognized.")

    ###############################
    #       Camera Commands       #
    ###############################

    """'
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
    """

    def expose_command(
        self,
        required_params,
        optional_params,
        user_id='None',
        user_name='None',
        user_roles='None',
        gather_status=True,
        do_sep=True,
        no_AWS=False,
        quick=False,
        solve_it=False,
        calendar_event_id=None,
        skip_open_check=False,
        skip_daytime_check=False,
        manually_requested_calibration=False
    ):
        """
        This is Phase 1:  Setup the camera.
        Apply settings and start an exposure.
        Quick=True is meant to be fast.  We assume the ASCOM/Maxim imageBuffer is the source of data in that mode,
        not the slower File Path.  THe mode used for focusing or other operations where we do not want to save any
        image data.
        """

        # First check that it isn't an exposure that doesn't need a check (e.g. bias, darks etc.)
        if not g_dev['obs'].assume_roof_open and not skip_open_check:
        #Second check, if we are not open and available to observe, then .... don't observe!        
            if (g_dev['obs'].open_and_enabled_to_observe==False and g_dev['enc'].mode == 'Automatic') and (not g_dev['obs'].debug_flag) :
                g_dev['obs'].send_to_user("Refusing exposure request as the observatory is not enabled to observe.")
                plog("Refusing exposure request as the observatory is not enabled to observe.")
                return
        
        # Need to pick up exposure time here
        exposure_time = float(
            required_params.get("time", 1.0)
        ) 
        
        #Third check, check it isn't daytime and institute maximum exposure time 
        #Unless it is a command from the sequencer flat_scripts or a requested calibration frame
        
        imtype = required_params.get("image_type", "light")
        
        
        skip_daytime_check=False
        skip_calibration_check=False
        
        if imtype.lower() in (            
            "bias",
            "dark",
            "screen flat",
            "sky flat",
            "near flat",
            "thor flat",
            "arc flat",
            "lamp flat",
            "solar flat",
        ):
            skip_daytime_check=True
            skip_calibration_check=True
        
        
        if not skip_daytime_check and g_dev['obs'].daytime_exposure_time_safety_on:
            sun_az, sun_alt = g_dev['evnt'].sun_az_alt_now()
            if sun_alt > -5:
                if exposure_time > float(self.config["camera"][self.name]["settings"]['max_daytime_exposure']):
                    g_dev['obs'].send_to_user("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    plog("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    exposure_time = float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])
            #breakpoint()
            
        # Need to check that we are not in the middle of flats, biases or darks
        
        # Fifth thing, check that the sky flat latch isn't on
        # (I moved the scope during flats once, it wasn't optimal)
        if not skip_calibration_check:
            if g_dev['seq'].morn_sky_flat_latch  or g_dev['seq'].eve_sky_flat_latch or g_dev['seq'].sky_flat_latch:
                g_dev['obs'].send_to_user("Refusing exposure request as the observatory is currently undertaking flats.")
                plog("Refusing exposure request as the observatory is currently taking flats.")
                return
        
        self.exposure_busy = True # This really needs to be here from the start
        # We've had multiple cases of multiple camera exposures trying to go at once
        # And it is likely because it takes a non-zero time to get to Phase II
        # So even in the setup phase the "exposure" is "busy"

        opt = optional_params
        self.hint = optional_params.get("hint", "")
        self.script = required_params.get("script", "None")        
        
        # no_AWS, self.toss = True if imtype.lower() == "test image" else False, False
        # quick = True if imtype.lower() == "quick" else False
        # #  NBNB this is obsolete and needs rework 20221002 WER
        # if imtype.lower() in (
        #     "quick",
        #     "bias",
        #     "dark",
        #     "screen flat",
        #     "sky flat",
        #     "near flat",
        #     "thor flat",
        #     "arc flat",
        #     "lamp flat",
        #     "solar flat",
        # ):
        #     do_sep = False
        # else:
        #     do_sep = True

        if imtype.lower() in ("bias"):
            
            exposure_time = 0.0
            bias_dark_or_light_type_frame = 'bias'  # don't open the shutter.  
            frame_type = imtype.replace(" ", "")
        
        elif imtype.lower() in ("dark", "lamp flat"):
            
            bias_dark_or_light_type_frame = 'dark'  # don't open the shutter.
            lamps = "turn on led+tungsten lamps here, if lampflat"
            frame_type = imtype.replace(" ", "")
        
        elif imtype.lower() in ("near flat", "thor flat", "arc flat"):
            bias_dark_or_light_type_frame = 'light'
            lamps = "turn on ThAr or NeAr lamps here"
            frame_type = "arc"
        elif imtype.lower() in ("sky flat", "screen flat", "solar flat"):
            bias_dark_or_light_type_frame = 'light'  # open the shutter.
            lamps = "screen lamp or none"
            frame_type = imtype.replace(
                " ", ""
            )  # note banzai doesn't appear to include screen or solar flat keywords.
        elif imtype.lower() == "focus":
            frame_type = "focus"
            bias_dark_or_light_type_frame = 'light'
            lamps = None
        else:  # 'light', 'experimental', 'autofocus probe', 'quick', 'test image', or any other image type
            bias_dark_or_light_type_frame = 'light'
            lamps = None
            if imtype.lower() in ("experimental", "autofocus probe", "auto_focus"):
                frame_type = "experimental"
            else:
                frame_type = "expose"
        
        self.smartstack = required_params.get('smartstack', True)
        self.longstack = required_params.get('longstackswitch', False)

    
        if self.longstack == 'no':
            LongStackID ='no'
        elif not 'longstackname' in required_params:
            LongStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
        else:
            LongStackID = required_params['longstackname']

        #breakpoint()

        #g_dev['seq'].blockend = required_params.get('block_end', "None")
        self.pane = optional_params.get("pane", None)

        bin_x = 1               
        #bin_y = 1  # NB This needs fixing someday!
        self.native_bin = self.config["camera"][self.name]["settings"]["native_bin"]
        self.ccd_sum = str(1) + ' ' + str(1)

        readout_time = float(
            self.config["camera"][self.name]["settings"]["cycle_time"]
        )
        self.estimated_readtime = (
            exposure_time + readout_time
        )  
        count = int(
            optional_params.get("count", 1)
        )  
        
        #lcl_repeat = 1
        if count < 1:
            count = 1  # Hence frame does not repeat unless count > 1

        # Here we set up the filter, and later on possibly rotational composition.
        try:
            if g_dev["fil"].null_filterwheel == False:
                
                if imtype in ['bias','dark']:
                    requested_filter_name = 'dark'
                else:
                    requested_filter_name = str(
                        optional_params.get(
                            "filter",
                            self.config["filter_wheel"]["filter_wheel1"]["settings"][
                                "default_filter"
                            ],
                        )
                    )  
                
                # Check if filter needs changing, if so, change.                
                if not g_dev['fil'].filter_selected == requested_filter_name:
                    try:
                        self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command(
                            {"filter": requested_filter_name}, {}
                        )
                        
                        self.current_offset = g_dev[
                            "fil"
                        ].filter_offset  # TEMP   NBNBNB This needs fixing
                    except:
                        plog ("Failed to change filter! Cancelling exposure.")
                        ##DEBUG Error on 20230703  System halted here. putting in
                        ##a breakpoint to catch this path next time.  WER
                        plog(traceback.format_exc())  
                        breakpoint()
                        return 
                    
                
                
                if self.current_filter == "none" or self.current_filter == None :
                    plog("skipping exposure as no adequate filter match found")
                    g_dev["obs"].send_to_user("Skipping Exposure as no adequate filter found for requested observation")
                    self.exposure_busy = False
                    return
                
                self.current_filter = g_dev['fil'].filter_selected
            else:
                self.current_filter = self.config["filter_wheel"]["filter_wheel1"]["name"]
        except Exception as e:
            plog("Camera filter setup:  ", e)
            plog(traceback.format_exc())      

        this_exposure_filter = self.current_filter
        if g_dev["fil"].null_filterwheel == False:            
            exposure_filter_offset = self.current_offset
        else:
            exposure_filter_offset = 0

        #self.len_x = self.camera_x_size // bin_x
        #self.len_y = self.camera_y_size // bin_y  # Unit is binned pixels.
        #self.len_xs = 0  # THIS IS A HACK, indicating no overscan.
        
         # Always check rotator just before exposure  The Rot jitters wehn parked so
         # this give rot moving report during bia darks
        rot_report=0
        if g_dev['rot']!=None:
            if not g_dev['mnt'].mount.AtPark:                
                while g_dev['rot'].rotator.IsMoving:    #This signal fibrulates!                
                    #if g_dev['rot'].rotator.IsMoving:                                       
                        if rot_report == 0 and imtype not in ['bias', 'dark']:
                            plog("Waiting for camera rotator to catch up. ")
                            g_dev["obs"].send_to_user("Waiting for camera rotator to catch up before exposing.")
                                        
                            rot_report=1
                        time.sleep(0.2)
                        if g_dev["obs"].stop_all_activity:
                            plog('stop_all_activity cancelling camera exposure')
                            return                              
                                

        self.expresult = {}  #  This is a default return just in case
        num_retries = 0
        incoming_exposure_time=exposure_time
        for seq in range(count):
            
            # SEQ is the outer repeat loop and takes count images; those individual exposures are wrapped in a
            # retry-3-times framework with an additional timeout included in it.
            if seq > 0:
                g_dev["obs"].update_status(cancel_check=False)
                # breakpoint()
                # if not g_dev["cam"].exposure_busy:
                #     self.expself.expresult = {"stopped": True}
                #     return self.expresult

            ## Vital Check : Has end of observing occured???
            ## Need to do this, SRO kept taking shots til midday without this
            if imtype.lower() in ["light"] or imtype.lower() in ["expose"]:
                if g_dev['events']['Observing Ends'] < ephem.Date(ephem.now()+ (exposure_time *ephem.second)) and not g_dev['obs'].debug_flag:
                    plog ("Sorry, exposures are outside of night time.")
                    self.exposure_busy = False
                    return 'outsideofnighttime'

            self.pre_mnt = []
            self.pre_rot = []
            self.pre_foc = []
            self.pre_ocn = []

            # Within each count - which is a single requested exposure, IF it is a smartstack
            # Then we divide each count up into individual smartstack exposures.
            ssExp=self.config["camera"][self.name]["settings"]['smart_stack_exposure_time']
            if g_dev["fil"].null_filterwheel == False:
                if self.current_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u']:
                    ssExp = ssExp * 3.0 # For narrowband and low throughput filters, increase base exposure time.
            if not imtype.lower() in ["light", "expose"]:
                Nsmartstack=1
                SmartStackID='no'
                exposure_time=incoming_exposure_time
            elif (self.smartstack == 'yes' or self.smartstack == True) and (incoming_exposure_time >= 3*ssExp):
                Nsmartstack=np.ceil(incoming_exposure_time / ssExp)
                exposure_time=ssExp
                SmartStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
            else:
                Nsmartstack=1
                SmartStackID='no'
                exposure_time=incoming_exposure_time
        
            self.retry_camera = 3
            self.retry_camera_start_time = time.time()

            #Repeat camera acquisition loop to collect all smartstacks necessary
            #The variable Nsmartstacks defaults to 1 - e.g. normal functioning
            #When a smartstack is not requested.
            for sskcounter in range(int(Nsmartstack)):
                
                    
                self.tempStartupExposureTime=time.time()
                if Nsmartstack > 1 :
                    self.currently_in_smartstack_loop=True
                    plog ("Smartstack " + str(sskcounter+1) + " out of " + str(Nsmartstack))
                    g_dev['obs'].update_status(cancel_check=False)
                    initial_smartstack_ra= g_dev['mnt'].mount.RightAscension
                    initial_smartstack_dec= g_dev['mnt'].mount.Declination
                else:
                    initial_smartstack_ra= None
                    initial_smartstack_dec= None
                    self.currently_in_smartstack_loop=False
                self.retry_camera = 3
                self.retry_camera_start_time = time.time()
                while self.retry_camera > 0:
                    if g_dev["obs"].stop_all_activity:

                        if self.expresult != None and self.expresult != {}:
                            if self.expresult["stopped"] is True:
                                g_dev["obs"].stop_all_activity = False
                                plog("Camera retry loop stopped by Cancel Exposure")
                                self.exposure_busy = False
                        self.exposure_busy = False
                        plog ("stop_all_activity cancelling out of camera exposure")
                        self.currently_in_smartstack_loop=False
                        return

                    

                    # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                    if g_dev['seq'].blockend != None: # Only do this check if a block end was provided.
                        
                    # Check that the exposure doesn't go over the end of a block
                        endOfExposure = datetime.datetime.now() + datetime.timedelta(seconds=exposure_time)
                        now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'
                        
                        blockended = now_date_timeZ  >= g_dev['seq'].blockend
                        
                        if blockended or ephem.Date(ephem.now()+ (exposure_time *ephem.second)) >= \
                            g_dev['events']['End Morn Bias Dark']:
                            plog ("Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            self.exposure_busy = False
                            self.currently_in_smartstack_loop=False
                            return 'blockend'
                    
                    # Check that the calendar event that is running the exposure
                    # Hasn't completed already
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    if not calendar_event_id == None:
                        g_dev['obs'].scan_requests()
                        foundcalendar=False    
                        g_dev['seq'].update_calendar_blocks()
                        for tempblock in g_dev['seq'].blocks:
                            try:
                                if tempblock['event_id'] == calendar_event_id :
                                    foundcalendar=True
                                    g_dev['seq'].blockend=tempblock['end']
                                    #breakpoint()
                            except:
                                plog("glitch in calendar finder")
                                plog(str(tempblock))
                        if foundcalendar == False:
                            plog ("could not find calendar entry, cancelling out of block.")
                            self.exposure_busy = False
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            self.currently_in_smartstack_loop=False
                            return 'calendarend'
                    
                    # Check that the roof hasn't shut
                    g_dev['obs'].get_enclosure_status_from_aws()
                    
                    if not g_dev['obs'].assume_roof_open and 'Closed' in g_dev['obs'].enc_status['shutter_status'] and (not g_dev['obs'].debug_flag) and imtype not in ['bias', 'dark']:
                        
                        plog("Roof shut, exposures cancelled.")
                        g_dev["obs"].send_to_user("Roof shut, exposures cancelled.")
                        
                        self.open_and_enabled_to_observe = False
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            g_dev['obs'].cancel_all_activity()  #NB Kills bias dark
                        if not g_dev['mnt'].mount.AtPark:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                        self.exposure_busy = False
                        plog ("And Cancelling SmartStacks.")
                        Nsmartstack=1
                        sskcounter=2
                        self.currently_in_smartstack_loop=False
                        return 'roofshut'
                    
                    # NB Here we enter Phase 2
                    try:
                        #self.t1 = time.time()
                        self.exposure_busy = True                       

                        if self.maxim or self.ascom or self.theskyx or self.qhydirect:

                            ldr_handle_time = None
                            ldr_handle_high_time = None  #  This is not maxim-specific

                            if self.darkslide and bias_dark_or_light_type_frame == 'light':
                                if self.darkslide_state != 'Open':
                                    self.darkslide_instance.openDarkslide()
                                    self.darkslide_open = True
                                    self.darkslide_state = 'Open'
                            elif self.darkslide and (bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark'):
                                if self.darkslide_state != 'Closed':
                                    self.darkslide_instance.closeDarkslide()
                                    self.darkslide_open = False
                                    self.darkslide_state = 'Closed'
                            #else:
                            #    pass
 
                            self.pre_mnt = []
                            self.pre_rot = []
                            self.pre_foc = []
                            self.pre_ocn = []
                            self.t2p1 = time.time()
                            
                            try:
                                g_dev["ocn"].get_quick_status(
                                    self.pre_ocn
                                )  # NB NB WEMA must be running or this may fault.
                            except:
                                pass
                            g_dev["foc"].get_quick_status(self.pre_foc)
                            try:
                                g_dev["rot"].get_quick_status(self.pre_rot)
                            except:
                                pass

                            g_dev["mnt"].get_rapid_exposure_status(
                                self.pre_mnt
                            )  # Should do this close to the exposure
                
                            # Good spot to check if we need to nudge the telescope
                            g_dev['obs'].check_platesolve_and_nudge()   
                            g_dev['obs'].time_of_last_exposure = time.time()
                            g_dev['obs'].update()
                            
                            
                            # Make sure the latest mount_coordinates are updated. HYPER-IMPORTANT!
                            g_dev["mnt"].get_mount_coordinates()
                            ra_at_time_of_exposure = g_dev["mnt"].current_icrs_ra
                            dec_at_time_of_exposure = g_dev["mnt"].current_icrs_dec
                            observer_user_name = user_name

                            try:
                                self.user_id = user_id
                                if self.user_id != self.last_user_id:
                                    self.last_user_id = self.user_id
                                observer_user_id= self.user_id
                            except:
                                observer_user_id= 'Tobor'
                                plog("Failed user_id")

                            # Calculate current airmass now
                            try:
                                rd = SkyCoord(ra=ra_at_time_of_exposure*u.hour, dec=dec_at_time_of_exposure*u.deg)            
                            except:
                                icrs_ra, icrs_dec = g_dev['mnt'].get_mount_coordinates()
                                rd = SkyCoord(ra=icrs_ra*u.hour, dec=icrs_dec*u.deg)
                            aa = AltAz (location=g_dev['mnt'].site_coordinates, obstime=Time.now())
                            rd = rd.transform_to(aa)
                            alt = float(rd.alt/u.deg)
                            az = float(rd.az/u.deg) 
                            zen = round((90 - alt), 3)
                            if zen > 90:
                                zen = 90.0
                            if zen < 0.1:    #This can blow up when zen <=0!
                                new_z = 0.1
                            else:
                                new_z = zen
                            sec_z = 1/math.cos(math.radians(new_z))
                            airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
                            if airmass > 10: airmass = 10
                            airmass = round(airmass, 4)
                            
                            airmass_of_observation = airmass
                            azimuth_of_observation = az
                            altitude_of_observation = alt
                            start_time_of_observation=time.time()
                            self.start_time_of_observation=time.time()
                            self.current_exposure_time=exposure_time
                            # Always check rotator just before exposure  The Rot jitters wehn parked so
                            # this give rot moving report during bia darks
                            rot_report=0
                            if g_dev['rot']!=None:      
                                if not g_dev['mnt'].mount.AtPark:
                                    while g_dev['rot'].rotator.IsMoving:    #This signal fibrulates!                
                                        #if g_dev['rot'].rotator.IsMoving:                                       
                                         if rot_report == 0 :
                                             plog("Waiting for camera rotator to catch up. ")
                                             g_dev["obs"].send_to_user("Waiting for camera rotator to catch up before exposing.")
                                                         
                                             rot_report=1
                                         time.sleep(0.2) 
                                         if g_dev["obs"].stop_all_activity:
                                             plog ("stop_all_activity cancelling out of camera exposure")
                                             self.currently_in_smartstack_loop=False
                                             return
                            
                            if (bias_dark_or_light_type_frame in ["bias", "dark"] or 'flat' in frame_type) and not manually_requested_calibration:
                                #plog("Median of full-image area bias, dark or flat:  ", np.median(self.img))
                                
                                # Check that the temperature is ok before accepting
                                current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                                current_camera_temperature = float(current_camera_temperature)   
                                if abs(float(current_camera_temperature) - float(g_dev['cam'].setpoint)) > 1.5:
                                    plog ("temperature out of range for calibrations ("+ str(current_camera_temperature)+"), NOT attempting calibration frame")
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                                    self.expresult = {}
                                    self.expresult["error"] = True
                                    self.exposure_busy = False
                                    self.currently_in_smartstack_loop=False
                                    return self.expresult
                                    
                                else:
                                    plog ("temperature in range for calibrations ("+ str(current_camera_temperature)+"), attempting calibration frame")
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True
                            
                            self._expose(exposure_time, bias_dark_or_light_type_frame)
                            
                            
                        else:
                            plog("Something terribly wrong, driver not recognized.!")
                            self.expresult = {}
                            self.expresult["error":True]
                            self.exposure_busy = False
                            self.currently_in_smartstack_loop=False
                            return self.expresult
                        
                        # We call below to keep this subroutine a reasonable length, Basically still in Phase 2
                        self.expresult = self.finish_exposure(
                            exposure_time,
                            frame_type,
                            count - seq,
                            gather_status,
                            do_sep,
                            no_AWS,
                            None,
                            None,
                            quick=quick,
                            low=ldr_handle_time,
                            high=ldr_handle_high_time,
                            script=self.script,
                            opt=opt,
                            solve_it=solve_it,
                            smartstackid=SmartStackID,
                            longstackid=LongStackID,
                            sskcounter=sskcounter,
                            Nsmartstack=Nsmartstack,
                            bin_x=bin_x,
                            this_exposure_filter=this_exposure_filter,
                            start_time_of_observation=start_time_of_observation,
                            exposure_filter_offset=exposure_filter_offset,
                            ra_at_time_of_exposure=ra_at_time_of_exposure,
                            dec_at_time_of_exposure=dec_at_time_of_exposure,
                            observer_user_name=observer_user_name,
                            observer_user_id=observer_user_id,
                            airmass_of_observation=airmass_of_observation,
                            azimuth_of_observation = azimuth_of_observation,
                            altitude_of_observation = altitude_of_observation,
                            manually_requested_calibration=manually_requested_calibration,
                            initial_smartstack_ra=initial_smartstack_ra, 
                            initial_smartstack_dec= initial_smartstack_dec
                        )  # NB all these parameters are crazy!
                        self.exposure_busy = False
                        self.retry_camera = 0
                        self.currently_in_smartstack_loop=False
                        break
                    except Exception as e:
                        plog("Exception in camera retry loop:  ", e)
                        plog(traceback.format_exc())
                        self.retry_camera -= 1
                        num_retries += 1
                        self.exposure_busy = False
                        self.currently_in_smartstack_loop=False
                        continue
        #  This is the loop point for the seq count loop
        self.exposure_busy = False
        self.currently_in_smartstack_loop=False
        return self.expresult

    def stop_command(self, required_params, optional_params):
        """Stop the current exposure and return the camera to Idle state."""
        self._stop_expose()
        g_dev['cam'].expresult["stopped"] = True
        self.exposure_busy = False
        self.exposure_halted = True

    def finish_exposure(
        self,
        exposure_time,
        frame_type,
        counter,
        seq,
        gather_status=True,
        do_sep=False,
        no_AWS=False,
        start_x=None,
        start_y=None,
        quick=False,
        low=0,
        high=0,
        script="False",
        opt=None,
        solve_it=False,
        smartstackid='no',
        longstackid='no',
        sskcounter=0,
        Nsmartstack=1,
        bin_x=1,
        this_exposure_filter=None,
        start_time_of_observation=None,
        exposure_filter_offset=None,
        ra_at_time_of_exposure=None,
        dec_at_time_of_exposure=None,
        observer_user_name=None,
        observer_user_id=None,
        airmass_of_observation=None,
        azimuth_of_observation=None,
        altitude_of_observation=None,
        manually_requested_calibration=False,
        initial_smartstack_ra=None, 
        initial_smartstack_dec=None
        
    ):
        
          
        
        plog(
            "Exposure Started:  " + str(exposure_time) + "s ",
            frame_type
        )
        
        try:
            filter_ui_info=opt['filter']
        except:
            filter_ui_info='filterless'
            
        if frame_type in (
            "flat",
            "screenflat",
            "skyflat",
            "dark",
            "bias",
        ):
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + " calibration exposure.",
                p_level="INFO",
            )
        elif frame_type in ("focus", "auto_focus"):
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + "  exposure.",
                p_level="INFO",
            )
        elif frame_type in ("pointing"):
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + "  exposure.",
                p_level="INFO",
            )
            
        elif Nsmartstack > 1 and self.current_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u']:
            plog ("Starting narrowband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " of "
            + str(opt["object_name"]) 
            + " by user: " + str(observer_user_name))
            g_dev["obs"].send_to_user ("Starting narrowband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " by user: " + str(observer_user_name))
        elif Nsmartstack > 1 :
            plog ("Starting broadband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " of "
            + str(opt["object_name"]) 
            + " by user: " + str(observer_user_name))
            g_dev["obs"].send_to_user ("Starting broadband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " by user: " + str(observer_user_name))
        else:
            if "object_name" in opt:
                g_dev["obs"].send_to_user(
                    "Starting "
                    + str(exposure_time)
                    + "s " + str(filter_ui_info) + " exposure of "
                    + str(opt["object_name"])
                    + " by user: "
                    + str(observer_user_name) + '. ' + str(int(opt['count']) - int(counter) + 1) + " of " + str(opt['count']),
                    p_level="INFO",
                )
            
        self.status_time = time.time() + 10
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0

        cycle_time = (
            float(self.config["camera"][self.name]["settings"]['cycle_time'])
            + exposure_time
        )

        self.completion_time = start_time_of_observation + cycle_time
        self.expresult = {"error": False}
        quartileExposureReport = 0
        self.plog_exposure_time_counter_timer=time.time() -3.0
        
        exposure_scan_request_timer=time.time()
        g_dev["obs"].exposure_halted_indicator =False
        while True:  # This loop really needs a timeout.
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []        

            
            if (
                time.time() < self.completion_time or self.async_exposure_lock==True
            ):  
                
                # Scan requests every 4 seconds... primarily hunting for a "Cancel/Stop"
                if time.time() - exposure_scan_request_timer > 4:                    
                    exposure_scan_request_timer=time.time()
                    
                    g_dev['obs'].scan_requests()
                    
                    if g_dev["obs"].exposure_halted_indicator:
                        self.expresult["error"] = True
                        self.expresult["stopped"] = True
                        #self.expresult["patch"] = bi_mean
                        g_dev["obs"].exposure_halted_indicator =False
                        plog ("Exposure Halted Indicator On. Cancelling Exposure.")
                        return self.expresult

                remaining = round(self.completion_time - time.time(), 1)
                
                if remaining > 0:  
                    if time.time() - self.plog_exposure_time_counter_timer > 10.0:
                        self.plog_exposure_time_counter_timer=time.time()
                        plog(
                            '||  ' + str(round(remaining, 1)) + "sec.",
                            str(round(100 * remaining / cycle_time, 1)) + "%",
                        )  #|| used to flag this line in plog().
                        
                        # Here scan for requests
                        g_dev['obs'].update()
                        
                        
                    if (
                        quartileExposureReport == 0
                    ):  # Silly daft but workable exposure time reporting by MTF
                        initialRemaining = remaining
                        quartileExposureReport = quartileExposureReport + 1
                    if (
                        quartileExposureReport == 1
                        and remaining < initialRemaining * 0.75
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 25% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        if (exposure_time > 120):
                            g_dev["obs"].update_status(cancel_check=False)

                    if (
                        quartileExposureReport == 2
                        and remaining < initialRemaining * 0.50
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 50% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        if (exposure_time > 60):
                            g_dev["obs"].update_status(cancel_check=False)

                    if (
                        quartileExposureReport == 3
                        and remaining < initialRemaining * 0.25
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 75% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        #if (exposure_time > 120):
                        #    g_dev["obs"].update_status(cancel_check=False)


                continue
            elif self.async_exposure_lock == False and self._imageavailable():   #NB no more file-mode
                
                pixscale = float(self.config["camera"][self.name]["settings"]["1x1_pix_scale"])
                # Immediately nudge scope to a different point in the smartstack dither                
                if Nsmartstack > 1 and not (Nsmartstack == sskcounter+1):
                    #breakpoint()
                    ra_random_dither=(((random.randint(0,50)-25) * pixscale / 3600 ) / 15) 
                    dec_random_dither=((random.randint(0,50)-25) * pixscale /3600 )
                    print(initial_smartstack_ra + ra_random_dither)
                    print(initial_smartstack_dec + dec_random_dither)
                    try:
                        g_dev['mnt'].mount.SlewToCoordinatesAsync(initial_smartstack_ra + ra_random_dither, initial_smartstack_dec + dec_random_dither) 
                    except Exception as e:
                        plog (traceback.format_exc())
                        if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                            
                            plog("The SkyX had an error.")
                            plog("Usually this is because of a broken connection.")
                            plog("Killing then waiting 60 seconds then reconnecting")
                            g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)
                        
                # Otherwise immediately nudge scope back to initial pointing in smartstack
                elif Nsmartstack > 1 and (Nsmartstack == sskcounter+1):
                    try:
                        g_dev['mnt'].mount.SlewToCoordinatesAsync(initial_smartstack_ra, initial_smartstack_dec)    
                    except Exception as e:
                        plog (traceback.format_exc())
                        if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                            
                            plog("The SkyX had an error.")
                            plog("Usually this is because of a broken connection.")
                            plog("Killing then waiting 60 seconds then reconnecting")
                            g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)
                        
                    wait_for_slew()
                    g_dev['obs'].check_platesolve_and_nudge()
            
                incoming_image_list = []    
                try:
                    g_dev["mnt"].get_rapid_exposure_status(
                        self.post_mnt
                    )  # Need to pick which pass was closest to image completion
                except:
                    pass
                try:
                    g_dev["rot"].get_quick_status(self.post_rot)
                except:
                    pass
                g_dev["foc"].get_quick_status(self.post_foc)
                try:
                    g_dev["ocn"].get_quick_status(self.post_ocn)
                except:
                    pass
                

                imageCollected = 0
                retrycounter = 0
                while imageCollected != 1:   
                    if retrycounter == 8:
                        self.expresult = {"error": True}
                        plog("Retried 8 times and didn't get an image, giving up.")
                        return self.expresult
                    try:
                        self.img = self._getImageArray()  # As read, this is a Windows Safe Array of longs
                        imageCollected = 1
                    except Exception as e:
                        plog(e)
                        plog (traceback.format_exc())
                        if "Image Not Available" in str(e):
                            plog("Still waiting for file to arrive: ", e)
                        time.sleep(3)
                        retrycounter = retrycounter + 1          

                if (frame_type in ["bias", "dark"] or frame_type[-4:] == ['flat']) and not manually_requested_calibration:
                    plog("Median of full-image area bias, dark or flat:  ", np.median(self.img))
                    
                    # Check that the temperature is ok before accepting
                    current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                    current_camera_temperature = float(current_camera_temperature)   
                    if abs(float(current_camera_temperature) - float(g_dev['cam'].setpoint)) > 1.5:
                        plog ("temperature out of range for calibrations ("+ str(current_camera_temperature)+"), rejecting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                        self.expresult = {}
                        self.expresult["error":True]
                        self.exposure_busy = False
                        return self.expresult
                        
                    else:
                        plog ("temperature in range for calibrations ("+ str(current_camera_temperature)+"), accepting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True
                    
                    # For a dark, check that the debiased dark has an adequately low value
                    # If there is no master bias, it will just skip this check
                    if frame_type in ["dark"]:
                        try:
                            debiaseddarkmedian= np.nanmedian(self.img - self.biasFiles[str(1)]) / exposure_time
                            plog ("Debiased 1s Dark Median is " + str(debiaseddarkmedian))
                            if debiaseddarkmedian > 1.0:
                                plog ("Reject!")
                                self.expresult = {}
                                self.expresult["error":True]
                                self.exposure_busy = False
                                return self.expresult
                                
                        except:
                            pass
                    

                self.overscan = 0

               
                pier_side = g_dev["mnt"].pier_side  # 0 == Tel Looking West, is flipped.
            
                ix, iy = self.img.shape

                image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                
                # For OSC's flats are a bit more tricky! We need to get
                # the brightest part of the bayer range to be in the upper range.
                if self.config["camera"][self.name]["settings"]['is_osc']:
                    temp_is_osc=True
                    osc_fits=copy.deepcopy(self.img)
                    
                    debayered=[]
                    max_median=0                    
                    
                    debayered.append(osc_fits[::2, ::2])
                    debayered.append(osc_fits[::2, 1::2])
                    debayered.append(osc_fits[1::2, ::2])
                    debayered.append(osc_fits[1::2, 1::2])
                    
                    # crop each of the images to the central region
                    oscounter=0
                    for oscimage in debayered:
                        cropx = int( (oscimage.shape[0] -500)/2)
                        cropy = int((oscimage.shape[1] -500) /2)
                        oscimage=oscimage[cropx:-cropx, cropy:-cropy]
                        #oscimage = sigma_clip(camera_gain_estimate_image, masked=False, axis=None)
                        oscmedian=np.nanmedian(oscimage)
                        if oscmedian > max_median:
                            max_median=copy.deepcopy(oscmedian)
                            brightest_bayer=copy.deepcopy(oscounter)
                        oscounter=oscounter+1
                    
                    del osc_fits
                    del debayered
                    
                    #plog ("Brightest Bayer " + str(brightest_bayer))
                    central_median=max_median
                
                else:
                    temp_is_osc=False
                    osc_fits=copy.deepcopy(self.img)
                    cropx = int( (osc_fits.shape[0] -500)/2)
                    cropy = int((osc_fits.shape[1] -500) /2)
                    osc_fits=osc_fits[cropx:-cropx, cropy:-cropy]
                    #oscimage = sigma_clip(camera_gain_estimate_image, masked=False, axis=None)
                    central_median=np.nanmedian(osc_fits)
                    
                    
                
                # Get bi_mean of middle patch for flat usage                
                #test_saturated = self.img[ix // 3 : ix * 2 // 3, iy // 3 : iy * 2 // 3]
                # 1/9th the chip area, but central.   NB NB why 3, is this what flat uses???
                #bi_mean = round((test_saturated.mean() + np.median(test_saturated)) / 2, 1)
                
                
                if frame_type[-4:] == "flat":                      
                    
                    if (
                        central_median
                        >= 0.70* image_saturation_level
                    ):
                        plog("Flat rejected, center is too bright:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too bright.", p_level="INFO"
                        )
                        self.expresult["error"] = True
                        self.expresult["patch"] = central_median
                        self.expresult["camera_gain"] = np.nan
                        return self.expresult  # signals to flat routine image was rejected, prompt return
                    
                    elif (
                        central_median
                        <= 0.25 * image_saturation_level
                    ) and not temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        self.expresult["error"] = True
                        self.expresult["patch"] = central_median
                        self.expresult["camera_gain"] = np.nan
                        return self.expresult  # signals to flat routine image was rejected, prompt return
                    elif (
                        central_median
                        <= 0.5 * image_saturation_level
                    ) and temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        self.expresult["error"] = True
                        self.expresult["patch"] = central_median
                        self.expresult["camera_gain"] = np.nan
                        return self.expresult  # signals to flat routine image was rejected, prompt return
                    else:
                        #plog('Good flat value! :  ', central_median)
                        
                        
                        # Now estimate camera gain.
                        camera_gain_estimate_image=copy.deepcopy(self.img)
                        # First we debias,dedark and flatfield the image with the previous master
                        try:
                            # Don't calibrate! That throws things out! 
                            # try:
                            #     camera_gain_estimate_image = camera_gain_estimate_image - self.biasFiles[str(1)]
                            #     camera_gain_estimate_image = camera_gain_estimate_image - (self.darkFiles[str(1)] * exposure_time)
                            # except:
                            #     pass
                            
                            # # Attempt to flatfield the image, which may not work if
                            # # This is the first time the filter is being run.
                            # try:
                            #     if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                            #         camera_gain_estimate_image = np.divide(camera_gain_estimate_image, self.flatFiles[self.current_filter])                               
                            #     else:
                            #         camera_gain_estimate_image = np.divide(camera_gain_estimate_image, np.load(self.flatFiles[str(self.current_filter + "_bin" + str(1))]))
                            # except:
                            #     pass
                            
                            # Get the brightest bayer layer for gains
                            if self.config["camera"][self.name]["settings"]['is_osc']:
                                #plog ("Brightest Bayer " + str(brightest_bayer))
                                if brightest_bayer == 0:                                                                             
                                    camera_gain_estimate_image=camera_gain_estimate_image[::2, ::2]
                                elif brightest_bayer == 1:   
                                    camera_gain_estimate_image=camera_gain_estimate_image[::2, 1::2]
                                elif brightest_bayer == 2:    
                                    camera_gain_estimate_image=camera_gain_estimate_image[1::2, ::2]
                                elif brightest_bayer == 3:    
                                    camera_gain_estimate_image=camera_gain_estimate_image[1::2, 1::2]
                            
                            cropx = int( (camera_gain_estimate_image.shape[0] -500)/2)
                            cropy = int((camera_gain_estimate_image.shape[1] -500) /2)
                            camera_gain_estimate_image=camera_gain_estimate_image[cropx:-cropx, cropy:-cropy]
                            camera_gain_estimate_image = sigma_clip(camera_gain_estimate_image, masked=False, axis=None)
                            
                            
                            
                            cge_median=np.nanmedian(camera_gain_estimate_image)
                            cge_stdev=np.nanstd(camera_gain_estimate_image)
                            cge_sqrt=pow(cge_median,0.5)
                            cge_gain=1/pow(cge_sqrt/cge_stdev, 2)
                            
                            #plog ("Camera gain median: " + str(cge_median) + " stdev: " +str(cge_stdev)+ " sqrt: " + str(cge_sqrt) + " gain: " +str(cge_gain))
                            
                            
                            
                            
                            
                            # low values SHOULD be ok. 
                            #if (self.camera_known_gain - 3 *self.camera_known_gain_stdev) < cge_gain < (self.camera_known_gain + 3 *self.camera_known_gain_stdev):
                            if cge_gain < (self.camera_known_gain + 3 *self.camera_known_gain_stdev):
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Good Gain: ' + str(round(cge_gain,2)))
                                plog('Good flat value:  ' +str(central_median) + ' Good Gain: ' + str(cge_gain))    
                                
                            elif (not self.config['camera']['camera_1_1']['settings']['reject_new_flat_by_known_gain']):
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Bad Gain: ' + str(round(cge_gain,2)) + ' Flat rejection by gain is off.')    
                                plog('Good flat value:  ' +str(central_median) + ' Bad Gain: ' + str(cge_gain) + ' Flat rejection by gain is off.')    
                            
                            else:
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Bad Gain: ' + str(round(cge_gain,2)) + ' Flat rejected.')    
                                plog('Good flat value:  ' +str(central_median) + ' Bad Gain: ' + str(cge_gain) + ' Flat rejected.')    
                                self.expresult["error"] = True
                                self.expresult["patch"] = central_median
                                self.expresult["camera_gain"] = np.nan
                                return self.expresult  # signals to flat routine image was rejected, prompt return
                            
                            self.expresult["camera_gain"] = cge_gain
                            
                        
                        except Exception as e:
                            plog("Could not estimate the camera gain from this flat.")
                            plog(e) 
                            #plog(traceback.format_exc()) 
                            self.expresult["camera_gain"] = np.nan
                            
                        # # Quick flat flat frame
                        # try:
                        #     if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                        #         camera_gain_estimate_image = np.divide(camera_gain_estimate_image, self.flatFiles[self.current_filter])                               
                        #     else:
                        #         camera_gain_estimate_image = np.divide(camera_gain_estimate_image, np.load(self.flatFiles[str(self.current_filter + "_bin" + str(flashbinning))]))
                        # except:
                            
                            
                        
                        
                        self.expresult["error"] = False
                        self.expresult["patch"] = central_median
                    
                if not g_dev["cam"].exposure_busy:
                    self.expresult = {"stopped": True}
                    plog ("exposure busy cancelling out of camera")
                    return self.expresult
                

                counter = 0

                avg_mnt = g_dev["mnt"].get_average_status(self.pre_mnt, self.post_mnt)
                avg_foc = g_dev["foc"].get_average_status(self.pre_foc, self.post_foc)
                try:
                    avg_rot = g_dev["rot"].get_average_status(
                        self.pre_rot, self.post_rot
                    )
                except:
                    pass
                try:
                    avg_ocn = g_dev["ocn"].get_average_status(
                        self.pre_ocn, self.post_ocn
                    )
                except:
                    pass

                try:
                    # THIS IS THE SECTION WHERE THE ORIGINAL FITS IMAGES ARE ROTATED
                    # OR TRANSPOSED. THESE ARE ONLY USED TO ORIENTATE THE FITS
                    # IF THERE IS A MAJOR PROBLEM with the original orientation
                    # If you want to change the display on the UI, use the jpeg
                    # alterations later on.
                    if self.config["camera"][self.name]["settings"]["transpose_fits"]:
                        hdu = fits.PrimaryHDU(
                            self.img.transpose().astype('float32'))
                    elif self.config["camera"][self.name]["settings"]["flipx_fits"]:
                        hdu = fits.PrimaryHDU(
                            np.fliplr(self.img.astype('float32'))
                        )                      
                    elif self.config["camera"][self.name]["settings"]["flipy_fits"]:
                        hdu = fits.PrimaryHDU(
                            np.flipud(self.img.astype('float32'))
                        )                      
                    elif self.config["camera"][self.name]["settings"]["rotate90_fits"]:
                        hdu = fits.PrimaryHDU(
                            np.rot90(self.img.astype('float32'))
                        )                      
                    elif self.config["camera"][self.name]["settings"]["rotate180_fits"]:
                        hdu = fits.PrimaryHDU(
                            np.rot90(self.img.astype('float32'),2)
                        )                      
                    elif self.config["camera"][self.name]["settings"]["rotate270_fits"]:
                        hdu = fits.PrimaryHDU(
                            np.rot90(self.img.astype('float32'),3)
                        )                                                             
                    else:
                        hdu = fits.PrimaryHDU(
                            self.img.astype('float32')
                        )                  
                    del self.img

                    # assign the keyword values and comment of the keyword as a tuple to write both to header.

                    hdu.header["BUNIT"] = ("adu", "Unit of array values")
                    hdu.header["CCDXPIXE"] = (
                        self.config["camera"][self.name]["settings"]["x_pixel"],
                        "[um] Size of unbinned pixel, in X",
                    )
                    hdu.header["CCDYPIXE"] = (
                        self.config["camera"][self.name]["settings"]["y_pixel"],
                        "[um] Size of unbinned pixel, in Y",
                    )
                    hdu.header["XPIXSZ"] = (
                        round(float(hdu.header["CCDXPIXE"]), 3),
                        "[um] Size of binned pixel",
                    )
                    hdu.header["YPIXSZ"] = (
                        round(float(hdu.header["CCDYPIXE"]), 3),
                        "[um] Size of binned pixel",
                    )
                    hdu.header["XBINING"] = (1, "Pixel binning in x direction")
                    hdu.header["YBINING"] = (1, "Pixel binning in y direction")

                    hdu.header['CONFMODE'] = ('default',  'LCO Configuration Mode')
                    hdu.header["DOCOSMIC"] = (
                        self.config["camera"][self.name]["settings"]["do_cosmics"],
                        "Header item to indicate whether to do cosmic ray removal",
                    )

                    hdu.header["CCDSUM"] = (self.ccd_sum, "Sum of chip binning")

                    hdu.header["RDMODE"] = (
                        self.config["camera"][self.name]["settings"]["read_mode"],
                        "Camera read mode",
                    )
                    hdu.header["RDOUTM"] = (
                        self.config["camera"][self.name]["settings"]["readout_mode"],
                        "Camera readout mode",
                    )
                    hdu.header["RDOUTSP"] = (
                        self.config["camera"][self.name]["settings"]["readout_speed"],
                        "[FPS] Readout speed",
                    )
                    tempccdtemp, ccd_humidity, ccd_pressure = (g_dev['cam']._temperature())
                    hdu.header["CCDSTEMP"] = (
                        round(self.setpoint, 2),     #WER fixed.
                        "[C] CCD set temperature",
                    )
                    hdu.header["COOLERON"] = self._cooler_on()
                    hdu.header["CCDATEMP"] = (
                        round(tempccdtemp, 2),
                        "[C] CCD actual temperature",
                    )
                    hdu.header["CCDHUMID"] = round(ccd_humidity, 1)
                    hdu.header["CCDPRESS"] = round(ccd_pressure, 1)
                    hdu.header["OBSID"] = (
                        self.config["obs_id"].replace("-", "").replace("_", "")
                    )
                    hdu.header["SITEID"] = (
                        self.config["wema_name"].replace("-", "").replace("_", "")
                    )
                    #hdu.header["OBSID"] = (
                    #    self.config["obs_id"].replace("-", "").replace("_", "")
                    #)
                    
                    #hdu.header["SITE"] = (
                    #    self.config["observatory_location"].replace("-", "").replace("_", "")
                    #)
                    #hdu.header["SITEID"] = (
                    #    self.config["obs_id"].replace("-", "").replace("_", "")
                    #)
                    #hdu.header["OBSLOCAT"] = (
                    #    self.config["observatory_location"].replace("-", "").replace("_", "")
                    #)
                    hdu.header["TELID"] = self.config["telescope"]["telescope1"][
                        "telescop"
                    ][:4]
                    hdu.header["TELESCOP"] = self.config["telescope"]["telescope1"][
                        "telescop"
                    ][:4]
                    hdu.header["PTRTEL"] = self.config["telescope"]["telescope1"][
                        "ptrtel"
                    ]
                    hdu.header["PROPID"] = "ptr-" + self.config["obs_id"] + "-001-0001"
                    hdu.header["BLKUID"] = (
                        "1234567890",
                        "Just a placeholder right now. WER",
                    )
                    hdu.header["INSTRUME"] = (self.alias, "Name of camera")
                    hdu.header["CAMNAME"] = (self.camera_model, "Instrument used")
                    hdu.header["DETECTOR"] = (
                        self.config["camera"][self.name]["detector"],
                        "Name of camera detector",
                    )
                    hdu.header["CAMMANUF"] = (
                        self.config["camera"][self.name]["manufacturer"],
                        "Name of camera manufacturer",
                    )
                    hdu.header["DARKSLID"] = (self.darkslide_state, "Darkslide state")
                    hdu.header['SHUTTYPE'] = (self.config["camera"][self.name]["settings"]["shutter_type"], 
                                              'Type of shutter')
                    hdu.header["GAIN"] = (
                        self.config["camera"][self.name]["settings"]["camera_gain"],
                        "[e-/ADU] Pixel gain",
                    )
                    hdu.header["RDNOISE"] = (
                        self.config["camera"][self.name]["settings"]["read_noise"],
                        "[e-/pixel] Read noise",
                    )
                    hdu.header["CMOSCAM"] = (self.is_cmos, "Is CMOS camera")
                    hdu.header["OSCCAM"] = (self.config["camera"][self.name]["settings"]['is_osc'], "Is OSC camera")
                    hdu.header["OSCMONO"] = (False, "If OSC, is this a mono image or a bayer colour image.")
                    
                    hdu.header["FULLWELL"] = (
                        self.config["camera"][self.name]["settings"][
                            "fullwell_capacity"
                        ],
                        "Full well capacity",
                    )
                
                    if self.is_cmos and self.driver ==  "QHYCCD_Direct_Control":
                        hdu.header["CMOSGAIN"] = (self.config["camera"][self.name][
                            "settings"
                        ]['direct_qhy_gain'], "CMOS Camera System Gain")
                        
                        
                        hdu.header["CMOSOFFS"] = (self.config["camera"][self.name][
                            "settings"
                        ]['direct_qhy_offset'], "CMOS Camera System Offset")

                        hdu.header["CAMUSBT"] = (self.config["camera"][self.name][
                            "settings"
                        ]['direct_qhy_usb_speed'], "Camera USB traffic")
                        hdu.header["READMODE"] = (self.config["camera"][self.name][
                            "settings"
                        ]['direct_qhy_readout_mode'], "QHY Readout Mode")
    
                        
                    hdu.header["TIMESYS"] = ("UTC", "Time system used") 
                                       
                    hdu.header["DATE"] = (
                        datetime.datetime.isoformat(
                            datetime.datetime.utcfromtimestamp(start_time_of_observation)
                        ),
                        "Start date and time of observation"
                    )
                    
                    hdu.header["DATE-OBS"] = (
                        datetime.datetime.isoformat(
                            datetime.datetime.utcfromtimestamp(start_time_of_observation)
                        ),
                        "Start date and time of observation"
                    )
                    hdu.header["DAY-OBS"] = (
                        g_dev["day"],
                        "Date at start of observing night"
                    )
                    hdu.header["MJD-OBS"] = (
                        Time(start_time_of_observation, format="unix").mjd,
                        "[UTC days] Modified Julian Date start date/time",
                    )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
                    yesterday = datetime.datetime.now() - datetime.timedelta(1)
                    hdu.header["L1PUBDAT"] = datetime.datetime.strftime(
                        yesterday, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )  # IF THIS DOESN"T WORK, subtract the extra datetime ...
                    hdu.header["JD-START"] = (
                        Time(start_time_of_observation, format="unix").jd,
                        "[UTC days] Julian Date at start of exposure",
                    )
                    hdu.header["OBSTYPE"] = (
                        frame_type.upper(),
                        "Observation type",
                    )  # This report is fixed and it should vary...NEEDS FIXING!
                    if frame_type.upper() == "SKY FLAT":
                       frame_type =="SKYFLAT" 
                    hdu.header["IMAGETYP"] = (frame_type.upper(), "Observation type")
                    hdu.header["EXPTIME"] = (
                        exposure_time,
                        "[s] Requested exposure length",
                    )  # This is the exposure in seconds specified by the user
                    hdu.header["BUNIT"] = "adu"
                    hdu.header[
                        "EXPTIME"
                    ] = exposure_time  # This is the exposure in seconds specified by the user
                    hdu.header[
                        "EXPOSURE"
                    ] = exposure_time  # Ideally this needs to be calculated from actual times
                    hdu.header["FILTER"] = (
                        this_exposure_filter,
                        "Filter type")
                    if g_dev["fil"].null_filterwheel == False:
                        hdu.header["FILTEROF"] = (exposure_filter_offset, "Filter offset")
                        
                        hdu.header["FILTRNUM"] = (
                           "PTR_ADON_HA_0023",
                           "An index into a DB",
                           ) 
                    else:
                        hdu.header["FILTEROF"] = ("No Filter", "Filter offset")
                        hdu.header["FILTRNUM"] = (
                            "No Filter",
                            "An index into a DB",
                        )  # Get a number from the hardware or via Maxim.  NB NB why not cwl and BW instead, plus P
                    
                    # THESE ARE THE RELEVANT FITS HEADER KEYWORDS
                    # FOR OSC MATCHING AT A LATER DATE.
                    # THESE ARE SET TO DEFAULT VALUES FIRST AND
                    # THINGS CHANGE LATER BEFORE BANZAI
                    hdu.header["OSCMATCH"] = 'no'
                    hdu.header['OSCSEP'] = 'no'
                    if g_dev["scr"] is not None and frame_type == "screenflat":
                        hdu.header["SCREEN"] = (
                            int(g_dev["scr"].bright_setting),
                            "Screen brightness setting",
                        )
                    try:
                        hdu.header["DATASEC"] = self.config["camera"][self.name][
                            "settings"
                        ]["data_sec"]
                        hdu.header["DETSEC"] = self.config["camera"][self.name][
                            "settings"
                        ]["det_sec"]
                        hdu.header["BIASSEC"] = self.config["camera"][self.name][
                            "settings"
                        ]["bias_sec"]
                        hdu.header["TRIMSEC"] = self.config["camera"][self.name][
                            "settings"
                        ]["trim_sec"]
                        
                    except:
                        pass

                    hdu.header["SATURATE"] = (
                        float(image_saturation_level),
                        "[ADU] Saturation level",
                    )  
                    hdu.header["MAXLIN"] = (
                        float(
                            self.config["camera"][self.name]["settings"][
                                "max_linearity"
                            ]
                        ),
                        "[ADU] Non-linearity level",
                    )
                    if self.pane is not None:
                        hdu.header["MOSAIC"] = (True, "Is mosaic")
                        hdu.header["PANE"] = self.pane

                    hdu.header["FOCAL"] = (
                        round(
                            float(
                                self.config["telescope"]["telescope1"]["focal_length"]
                            ),
                            2,
                        ),
                        "[mm] Telescope focal length",
                    )
                    hdu.header["APR-DIA"] = (
                        round(
                            float(self.config["telescope"]["telescope1"]["aperture"]), 2
                        ),
                        "[mm] Telescope aperture",
                    )
                    hdu.header["APR-AREA"] = (
                        round(
                            float(
                                self.config["telescope"]["telescope1"][
                                    "collecting_area"
                                ]
                            ),
                            1,
                        ),
                        "[mm^2] Telescope collecting area",
                    )
                    hdu.header["LATITUDE"] = (
                        round(float(g_dev['evnt'].wema_config["latitude"]), 6),
                        "[Deg N] Telescope Latitude",
                    )
                    hdu.header["LONGITUD"] = (
                        round(float(g_dev['evnt'].wema_config["longitude"]), 6),
                        "[Deg E] Telescope Longitude",
                    )
                    hdu.header["HEIGHT"] = (
                        round(float(g_dev['evnt'].wema_config["elevation"]), 2),
                        "[m] Altitude of Telescope above sea level",
                    )
                    hdu.header["MPC-CODE"] = (
                        self.config["mpc_code"],
                        "Site code",
                    )  # This is made up for now.

                    if "object_name" in opt:
                        if (
                            opt["object_name"] != "Unspecified"
                            and opt["object_name"] != ""
                        ):
                            hdu.header["OBJECT"] = opt["object_name"]
                            hdu.header["OBJSPECF"] = "yes"
                    elif (
                        g_dev["mnt"].object != "Unspecified"
                        or g_dev["mnt"].object != "empty"
                    ):
                        hdu.header["OBJECT"] = (g_dev["mnt"].object, "Object name")
                        hdu.header["OBJSPECF"] = "yes"
                    else:
                        RAtemp = g_dev["mnt"].current_icrs_ra
                        DECtemp = g_dev["mnt"].current_icrs_dec
                        RAstring = f"{RAtemp:.1f}".replace(".", "h")
                        DECstring = f"{DECtemp:.1f}".replace("-", "n").replace(".", "d")
                        hdu.header["OBJECT"] = RAstring + "ra" + DECstring + "dec"
                        hdu.header["OBJSPECF"] = "no"

                    if frame_type in (
                        "bias",
                        "dark",
                        "lampflat",
                        "skyflat",
                        "screenflat",
                        "solarflat",
                        "arc",
                    ):
                        hdu.header["OBJECT"] = frame_type
                    if not any("OBJECT" in s for s in hdu.header.keys()):
                        RAtemp = g_dev["mnt"].current_icrs_ra
                        DECtemp = g_dev["mnt"].current_icrs_dec
                        RAstring = f"{RAtemp:.1f}".replace(".", "h")
                        DECstring = f"{DECtemp:.1f}".replace("-", "n").replace(".", "d")
                        hdu.header["OBJECT"] = RAstring + "ra" + DECstring + "dec"
                        hdu.header["OBJSPECF"] = "no"


                    # tempRAdeg = float(ra_at_time_of_exposure) * 15
                    # tempDECdeg = dec_at_time_of_exposure
                    # tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
                    # tempointing=tempointing.to_string("hmsdms").split(' ')

                    # hdu.header["RA"] = (
                    #     tempRAdeg,
                    #     "[deg] Telescope right ascension",
                    # )
                    # hdu.header["DEC"] = (
                    #     tempDECdeg,
                    #     "[deg] Telescope declination",
                    # )
                    # hdu.header["ORIGRA"] = hdu.header["RA"]
                    # hdu.header["ORIGDEC"] = hdu.header["DEC"]
                    # hdu.header["RAhrs"] = (
                    #     ra_at_time_of_exposure,
                    #     "[hrs] Telescope right ascension",
                    # )
                    # hdu.header["RA-hms"] = tempointing[0]
                    # hdu.header["DEC-dms"] = tempointing[1]

                    # hdu.header["TARG-CHK"] = (
                    #     (ra_at_time_of_exposure * 15)
                    #     + dec_at_time_of_exposure,
                    #     "[deg] Sum of RA and dec",
                    # )
                    # hdu.header["CATNAME"] = (g_dev["mnt"].object, "Catalog object name")
                    # hdu.header["CAT-RA"] = (
                    #     tempointing[0],
                    #     "[hms] Catalog RA of object",
                    # )
                    # hdu.header["CAT-DEC"] = (
                    #     tempointing[1],
                    #     "[dms] Catalog Dec of object",
                    # )

                    # hdu.header["TARGRA"] = float(ra_at_time_of_exposure) * 15
                    # hdu.header["TARGDEC"] = dec_at_time_of_exposure
                    try:
                        hdu.header["SID-TIME"] = (
                            self.pre_mnt[3],
                            "[deg] Sidereal time",
                        )
                        hdu.header["OBJCTRA"] = (
                            float(self.pre_mnt[1]) * 15,
                            "[deg] Object RA",
                        )
                        hdu.header["OBJCTDEC"] = (self.pre_mnt[2], "[deg] Object dec")
                    except:
                        plog("problem with the premount?")

                    hdu.header["OBSERVER"] = (
                        observer_user_name,
                        "Observer name",
                    )
                    hdu.header["OBSNOTE"] = self.hint[0:54]  # Needs to be truncated.
                    if self.maxim:
                        hdu.header[
                            "FLIPSTAT"
                        ] = "None"  # This is a maxim camera setup, not a flip status
                    hdu.header["DITHER"] = (0, "[] Dither")
                    hdu.header["OPERATOR"] = ("WER", "Site operator")
                    #hdu.header["ENCLOSUR"] = (
                    #    self.config["enclosure"]["enclosure1"]["name"],
                    #    "Enclosure description",
                    #)  # "Clamshell"   #Need to document shutter status, azimuth, internal light.
                    #if g_dev["enc"].is_dome:
                    #    hdu.header["DOMEAZ"] = (
                    #        g_dev["enc"].status["dome_azimuth"],
                    #        "Dome azimuth",
                    #    )
                    hdu.header["ENCLIGHT"] = ("Off/White/Red/NIR", "Enclosure lights")
                    hdu.header["ENCRLIGT"] = ("", "Enclosure red lights state")
                    hdu.header["ENCWLIGT"] = ("", "Enclosure white lights state")
                    #if g_dev["enc"] is not None:
                    #    try:

                    #        hdu.header["ENC1STAT"] = g_dev["enc"].status[
                    #            "shutter_status"
                    #        ]  # "Open/Closed" enclosure 1 status
                    #    except:
                    #        pass

                    hdu.header["MNT-SIDT"] = (
                        avg_mnt["sidereal_time"],
                        "[hrs] Mount sidereal time",
                    )
                    hdu.header["MNT-RA"] = (
                        float(avg_mnt["right_ascension"]) * 15,
                        "[deg] Mount RA",
                    )
                    ha = avg_mnt["sidereal_time"] - avg_mnt["right_ascension"]
                    while ha >= 12:
                        ha -= 24.0
                    while ha < -12:
                        ha += 24.0
                    hdu.header["MNT-HA"] = (
                        round(ha, 5),
                        "[hrs] Average mount hour angle",
                    )  # Note these are average mount observed values.
                    g_dev["ha"] = round(ha, 5)
                    hdu.header["MNT-DEC"] = (
                        avg_mnt["declination"],
                        "[deg] Average mount declination",
                    )
                    hdu.header["MNT-RAV"] = (
                        avg_mnt["tracking_right_ascension_rate"],
                        "[] Mount tracking RA rate",
                    )
                    hdu.header["MNT-DECV"] = (
                        avg_mnt["tracking_declination_rate"],
                        "[] Mount tracking dec rate",
                    )
                    hdu.header["AZIMUTH "] = (
                        azimuth_of_observation,
                        "[deg] Azimuth axis positions",
                    )
                    hdu.header["ALTITUDE"] = (
                        altitude_of_observation,
                        "[deg] Altitude axis position",
                    )
                    hdu.header["ZENITH"] = (90 - altitude_of_observation, "[deg] Zenith")
                    hdu.header["AIRMASS"] = (
                        #avg_mnt["airmass"],
                        airmass_of_observation,
                        "Effective mean airmass",
                    )
                    g_dev["airmass"] = float(airmass_of_observation)
                    try:
                        hdu.header["REFRACT"] = (
                            round(g_dev["mnt"].refraction_rev, 3),
                            "asec",
                        )
                    except:
                        pass
                    hdu.header["MNTRDSYS"] = (
                        avg_mnt["coordinate_system"],
                        "Mount coordinate system",
                    )
                    hdu.header["POINTINS"] = (avg_mnt["instrument"], "")
                    hdu.header["MNT-PARK"] = (avg_mnt["is_parked"], "Mount is parked")
                    hdu.header["MNT-SLEW"] = (avg_mnt["is_slewing"], "Mount is slewing")
                    hdu.header["MNT-TRAK"] = (
                        avg_mnt["is_tracking"],
                        "Mount is tracking",
                    )
                    try:
                        if pier_side == 0:
                            hdu.header["PIERSIDE"] = ("Look West", "Pier on  East side")
                            hdu.header["IMGFLIP"] = (True, "Is flipped")
                            pier_string = "lw-"
                        elif pier_side == 1:
                            hdu.header["PIERSIDE"] = ("Look East", "Pier on West side")
                            hdu.header["IMGFLIP"] = (False, "Is flipped")
                            pier_string = "le-"
                    except:
                        hdu.header["PIERSIDE"] = "Undefined"
                        pier_string = ""
                    
                    try:
                        hdu.header["HACORR"] = (
                            g_dev["mnt"].ha_corr,
                            "[deg] Hour angle correction",
                        )  # Should these be averaged?
                        hdu.header["DECCORR"] = (
                            g_dev["mnt"].dec_corr,
                            "[deg] Declination correction",
                        )
                    except:
                        pass
                    hdu.header["OTA"] = "Main"
                    hdu.header["SELECTEL"] = ("tel1", "Nominted OTA for pointing")
                    try:
                        hdu.header["ROTATOR"] = (
                            self.config["rotator"]["rotator1"]["name"],
                            "Rotator name",
                        )
                        hdu.header["ROTANGLE"] = (avg_rot[1], "[deg] Rotator angle")
                        hdu.header["ROTMOVNG"] = (avg_rot[2], "Rotator is moving")
                    except:
                        pass

                    try:
                        hdu.header["FOCUS"] = (
                            self.config["focuser"]["focuser1"]["name"],
                            "Focuser name",
                        )
                        hdu.header["FOCUSPOS"] = (avg_foc[1], "[um] Focuser position")
                        hdu.header["FOCUSTMP"] = (avg_foc[2], "[C] Focuser temperature")
                        hdu.header["FOCUSMOV"] = (avg_foc[3], "Focuser is moving")
                    except:
                        plog("There is something fishy in the focuser routine")
                    try:
                        hdu.header["WXSTATE"] = (
                            g_dev["ocn"].wx_is_ok,
                            "Weather system state",
                        )
                        hdu.header["SKY-TEMP"] = (avg_ocn[1], "[C] Sky temperature")
                        hdu.header["AIR-TEMP"] = (
                            avg_ocn[2],
                            "[C] External temperature",
                        )
                        hdu.header["HUMIDITY"] = (avg_ocn[3], "[%] Percentage humidity")
                        hdu.header["DEWPOINT"] = (avg_ocn[4], "[C] Dew point")
                        hdu.header["WINDSPEE"] = (avg_ocn[5], "[km/h] Wind speed")
                        hdu.header["PRESSURE"] = (
                            avg_ocn[6],
                            "[mbar] Atmospheric pressure",
                        )
                        hdu.header["CALC-LUX"] = (
                            avg_ocn[7],
                            "[mag/arcsec^2] Expected sky brightness",
                        )
                        hdu.header["SKYMAG"] = (
                            avg_ocn[8],
                            "[mag/arcsec^2] Measured sky brightness",
                        )
                    except:
                        #plog("have to not have ocn header items when no ocn")
                        pass

                    #try:
                    hdu.header["PIXSCALE"] = (
                        float(pixscale),
                        "[arcsec/pixel] Nominal pixel scale on sky",
                    )
                    #pixscale = float(hdu.header["PIXSCALE"])
                    
                    hdu.header["DRZPIXSC"] = (self.config["camera"][self.name]["settings"]['drizzle_value_for_later_stacking'], 'Target pixel scale for drizzling')
                       
                    hdu.header["REQNUM"] = ("00000001", "Request number")
                    hdu.header["ISMASTER"] = (False, "Is master image")
                    current_camera_name = self.alias

                    next_seq = next_sequence(current_camera_name)
                    hdu.header["FRAMENUM"] = (int(next_seq), "Running frame number")
                    #plog (str(smartstackid) + " SMARTSTACKID - temp MTF check")
                    hdu.header["SMARTSTK"] = smartstackid # ID code for an individual smart stack group
                    #plog (str(longstackid) + " LONGSTACKID - temp MTF check")
                    hdu.header["SSTKNUM"] = sskcounter
                    hdu.header['SSTKLEN'] = Nsmartstack
                    hdu.header["LONGSTK"] = longstackid # Is this a member of a longer stack - to be replaced by 
                                                        #   longstack code soon

                    hdu.header["PEDESTAL"] = (0.0, "This value has been added to the data")
                    hdu.header[
                        "PATCH"
                    ] = central_median # A crude value for the central exposure
                    hdu.header["ERRORVAL"] = 0
                    hdu.header["IMGAREA"] = opt["area"]
                    hdu.header[
                        "XORGSUBF"
                    ] = (
                        self.camera_start_x
                    )  # This makes little sense to fix...  NB ALL NEEDS TO COME FROM CONFIG!!
                    hdu.header["YORGSUBF"] = self.camera_start_y
                    
                    hdu.header["USERNAME"] = observer_user_name
                    hdu.header["USERID"] = (
                        str(observer_user_id).replace("-", "").replace("|", "").replace('@','at')
                    )
                               

                    im_type = "EX"  # or EN for engineering....
                    f_ext = ""

                    if frame_type in (
                        "bias",
                        "dark",
                        "lampflat",
                        "skyflat",
                        "screenflat",
                        "solarflat",
                        "arc",
                    ):
                        f_ext = "-"
                        if opt["area"] == 150:
                            f_ext += "f"
                        if frame_type[0:4] in ("bias", "dark"):
                            f_ext += frame_type[0] + "_" + str(1)
                        if frame_type in (
                            "lampflat",
                            "skyflat",
                            "screenflat",
                            "solarflat",
                            "arc",
                            "expose",
                        ):
                            f_ext += (
                                frame_type[:2]
                                + "_"
                                + str(1)
                                + "_"
                                + str(this_exposure_filter)
                            )
                    cal_name = (
                        self.config["obs_id"]
                        + "-"
                        + current_camera_name 
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + f_ext
                        + "-"
                        + im_type
                        + "00.fits"
                    )
                    raw_name00 = (
                        self.config["obs_id"]
                        + "-"
                        + current_camera_name
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "00.fits"
                    )
                    
                    if self.config['save_reduced_file_numberid_first']:
                        red_name01 = (next_seq + "-" +self.config["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" +  str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")                        
                    else:
                        red_name01 = (self.config["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" + next_seq+ "-" + str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")                        
                    
                    red_name01_lcl = (
                        red_name01[:-9]
                        + pier_string + '-'
                        + this_exposure_filter
                        + red_name01[-9:]
                    )
                    if self.pane is not None:
                        red_name01_lcl = (
                            red_name01_lcl[:-9]
                            + pier_string
                            + "p"
                            + str(abs(self.pane))
                            + "-"
                            + red_name01_lcl[-9:]
                        )
                    i768sq_name = (
                        self.config["obs_id"]
                        + "-"
                        + current_camera_name
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "10.fits"
                    )
                    jpeg_name = (
                        self.config["obs_id"]
                        + "-"
                        + current_camera_name
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "10.jpg"
                    )
                    text_name = (
                        self.config["obs_id"]
                        + "-"
                        + current_camera_name
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "00.txt"
                    )
                    im_path_r = self.camera_path

                    hdu.header["FILEPATH"] = str(im_path_r) + "to_AWS/"
                    hdu.header["ORIGNAME"] = str(raw_name00 + ".fz")

                    tempRAdeg = ra_at_time_of_exposure * 15
                    tempDECdeg = dec_at_time_of_exposure
                    tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
                    tempointing=tempointing.to_string("hmsdms").split(' ')
     
                    hdu.header["RA"] = (
                        tempointing[0],
                        "[hms] Telescope right ascension",
                    )
                    hdu.header["DEC"] = (
                        tempointing[1],
                        "[dms] Telescope declination",
                    )
                    hdu.header["ORIGRA"] = hdu.header["RA"]
                    hdu.header["ORIGDEC"] = hdu.header["DEC"]
                    hdu.header["RAhrs"] = (
                        ra_at_time_of_exposure,
                        "[hrs] Telescope right ascension",
                    )
                    hdu.header["RADEG"] = tempRAdeg 
                    hdu.header["DECDEG"] = tempDECdeg
     
                    hdu.header["TARG-CHK"] = (
                        (ra_at_time_of_exposure * 15)
                        + dec_at_time_of_exposure,
                        "[deg] Sum of RA and dec",
                    )
                    hdu.header["CATNAME"] = (g_dev["mnt"].object, "Catalog object name")
                    hdu.header["CAT-RA"] = (
                        tempointing[0],
                        "[hms] Catalog RA of object",
                    )
                    hdu.header["CAT-DEC"] = (
                        tempointing[1],
                        "[dms] Catalog Dec of object",
                    )
                    hdu.header["OFST-RA"] = (
                        tempointing[0],
                        "[hms] Catalog RA of object (for BANZAI only)",
                    )
                    hdu.header["OFST-DEC"] = (
                        tempointing[1],
                        "[dms] Catalog Dec of object",
                    )
     
     
                    hdu.header["TPT-RA"] = (
                        tempointing[0],
                        "[hms] Catalog RA of object (for BANZAI only",
                    )
                    hdu.header["TPT-DEC"] = (
                        tempointing[1],
                        "[dms] Catalog Dec of object",
                    )
                    
                    hdu.header["RA-hms"] = tempointing[0]
                    hdu.header["DEC-dms"] = tempointing[1]
                    
                    hdu.header["CTYPE1"] = 'RA---TAN'
                    hdu.header["CTYPE2"] = 'DEC--TAN'
                    hdu.header["CDELT1"] = pixscale / 3600
                    hdu.header["CDELT2"] = pixscale / 3600
                    hdu.header["CRVAL1"] = tempRAdeg
                    hdu.header["CRVAL2"] = tempDECdeg
                    hdu.header["CRPIX1"] = float(hdu.header["NAXIS1"])/2
                    hdu.header["CRPIX2"] = float(hdu.header["NAXIS2"])/2                    

                    try:  #  NB relocate this to Expose entry area.  Fill out except.  Might want to check on available space.
                        im_path_r = self.camera_path
                        os.makedirs(
                            im_path_r + g_dev["day"] + "/to_AWS/", exist_ok=True
                        )
                        os.makedirs(im_path_r + g_dev["day"] + "/raw/", exist_ok=True)
                        os.makedirs(im_path_r + g_dev["day"] + "/calib/", exist_ok=True)
                        os.makedirs(
                            im_path_r + g_dev["day"] + "/reduced/", exist_ok=True
                        )
                        im_path = im_path_r + g_dev["day"] + "/to_AWS/"
                        raw_path = im_path_r + g_dev["day"] + "/raw/"
                        cal_path = im_path_r + g_dev["day"] + "/calib/"
                        red_path = im_path_r + g_dev["day"] + "/reduced/"

                    except:
                        pass

                    paths = {
                        "im_path": im_path,
                        "raw_path": raw_path,
                        "cal_path": cal_path,
                        "red_path": red_path,
                        "red_path_aux": None,
                        "cal_name": cal_name,
                        "raw_name00": raw_name00,
                        #'fzraw_name00': fzraw_name00,
                        "red_name01": red_name01,
                        "red_name01_lcl": red_name01_lcl,
                        "i768sq_name10": i768sq_name,
                        "i768sq_name11": i768sq_name,
                        "jpeg_name10": jpeg_name,
                        "jpeg_name11": jpeg_name,
                        "text_name00": text_name,
                        "text_name10": text_name,
                        "text_name11": text_name,
                        "frame_type": frame_type,
                    }

                    if frame_type[-5:] in ["focus", "probe", "ental"]:
                        focus_image = True
                    else:
                        focus_image = False

                    # If the file isn't a calibration frame, then undertake a flash reduction quickly
                    # To make a palatable jpg AS SOON AS POSSIBLE to send to AWS
                    if (not frame_type.lower() in (
                        "bias",
                        "dark",
                        "flat",
                        "screenflat",
                        "skyflat",
                    )) or (manually_requested_calibration):  # Don't process jpgs or small fits for biases and darks

                        # Make a copy of hdu to use as jpg and small fits as well as a local raw used file for 
                        # planewave solves
                        hdusmalldata = copy.deepcopy(hdu.data.astype("float32"))
                            
                        # Quick flash bias and dark frame                           
                        
                        #flashbinning=1
                        if not manually_requested_calibration:
                            try:
                                hdusmalldata = hdusmalldata - self.biasFiles[str(1)]
                                hdusmalldata = hdusmalldata - (self.darkFiles[str(1)] * exposure_time)
                                
                            except Exception as e:
                                plog("debias/darking light frame failed: ", e)
                                
                            # Quick flat flat frame
                            try:
                                if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                                    hdusmalldata = np.divide(hdusmalldata, self.flatFiles[self.current_filter])                               
                                else:
                                    hdusmalldata = np.divide(hdusmalldata, np.load(self.flatFiles[str(self.current_filter + "_bin" + str(1))]))
                                
                            except Exception as e:
                                plog("flatting light frame failed", e)
                                #plog(traceback.format_exc()) 
                        
                        
                        # This saves the REDUCED file to disk
                        # If this is for a smartstack, this happens immediately in the camera thread after we have a "reduced" file
                        # So that the smartstack queue can start on it ASAP as smartstacks
                        # are by far the longest task to undertake.
                        # If it isn't a smartstack, it gets saved in the slow process queue.
                        if "hdusmalldata" in locals():
                            
                            # Set up reduced header
                            hdusmallheader=copy.deepcopy(hdu.header)
                            if not manually_requested_calibration:
                                #From the reduced data, crop around the edges of the
                                #raw 1x1 image to get rid of overscan and crusty edge bits
                                edge_crop=self.config["camera"][self.name]["settings"]['reduced_image_edge_crop']
                                hdusmalldata=hdusmalldata[edge_crop:-edge_crop,edge_crop:-edge_crop]
                                
                                hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) - (edge_crop * 2)
                                hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) - (edge_crop * 2)
                                hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) - (edge_crop * 2)
                                hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) - (edge_crop * 2)
                                
                                # bin to native binning
                                if self.native_bin != 1:
                                    hdusmalldata=(block_reduce(hdusmalldata,self.native_bin))                                 
                                    hdusmallheader['XBINING']=self.native_bin
                                    hdusmallheader['YBINING']=self.native_bin
                                    hdusmallheader['PIXSCALE']=float(hdu.header['PIXSCALE']) * self.native_bin
                                    pixscale=float(hdu.header['PIXSCALE'])
                                    hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) / self.native_bin
                                    hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) / self.native_bin
                                    hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) / self.native_bin
                                    hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) / self.native_bin
                                    hdusmallheader['CDELT1']=float(hdu.header['CDELT1']) * self.native_bin
                                    hdusmallheader['CDELT2']=float(hdu.header['CDELT2']) * self.native_bin
                                    hdusmallheader['CCDXPIXE']=float(hdu.header['CCDXPIXE']) * self.native_bin
                                    hdusmallheader['CCDYPIXE']=float(hdu.header['CCDYPIXE']) * self.native_bin
                                    hdusmallheader['XPIXSZ']=float(hdu.header['XPIXSZ']) * self.native_bin
                                    hdusmallheader['YPIXSZ']=float(hdu.header['YPIXSZ']) * self.native_bin
                                    
                                    hdusmallheader['SATURATE']=float(hdu.header['SATURATE']) * pow( self.native_bin,2)
                                    hdusmallheader['FULLWELL']=float(hdu.header['FULLWELL']) * pow( self.native_bin,2)
                                    hdusmallheader['MAXLIN']=float(hdu.header['MAXLIN']) * pow( self.native_bin,2)
                               
                                # Add a pedestal to the reduced data
                                # This is important for a variety of reasons
                                # Some functions don't work with arrays with negative values
                                # 2000 SHOULD be enough.
                                hdusmalldata=hdusmalldata+200.0
                                hdusmallheader['PEDESTAL']=200
                            
                            
                            # Every Image gets SEP'd and gets it's catalogue sent up pronto ahead of the big fits
                            # Focus images use it for focus, Normal images also report their focus.
                            # IMMEDIATELY SEND TO SEP QUEUE
                            # NEEDS to go up as fast as possible ahead of smartstacks to faciliate image matching.
                            self.sep_processing=True
                            
                            if g_dev['foc'].theskyx:
                                focus_position=g_dev['foc'].focuser.focPosition()*g_dev['foc'].steps_to_micron
                            else:
                                focus_position=g_dev['foc'].focuser.Position*g_dev['foc'].steps_to_micron
                            self.to_sep((hdusmalldata, pixscale, float(hdu.header["RDNOISE"]), avg_foc[1], focus_image, im_path, text_name, hdusmallheader, cal_path, cal_name, frame_type, focus_position, self.native_bin))
                            
                            
                            if smartstackid != 'no':
                                try:
                                    np.save(red_path + red_name01.replace('.fits','.npy'), hdusmalldata)
                                    hdusstack=fits.PrimaryHDU()
                                    hdusstack.header=hdusmallheader
                                    hdusstack.header["NAXIS1"] = hdusmalldata.shape[0]
                                    hdusstack.header["NAXIS2"] = hdusmalldata.shape[1]
                                    hdusstack.writeto(red_path + red_name01.replace('.fits','.head'), overwrite=True, output_verify='silentfix')
                                    saver = 1
                                except Exception as e:
                                    plog("Failed to write raw file: ", e)
                            
                            if smartstackid == 'no':
                                if self.config['keep_reduced_on_disk']:
                                    self.to_slow_process(1000,('reduced', red_path + red_name01, hdusmalldata, hdusmallheader, \
                                                           frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                            # else:                            
                            #     saver = 0
                            #     saverretries = 0
                            #     while saver == 0 and saverretries < 10:
                            #         try:
                            #             np.save(red_path + red_name01.replace('.fits','.npy'), hdusmalldata)
                            #             hdusstack=fits.PrimaryHDU()
                            #             hdusstack.header=hdusmallheader
                            #             hdusstack.header["NAXIS1"] = hdusmalldata.shape[0]
                            #             hdusstack.header["NAXIS2"] = hdusmalldata.shape[1]
                            #             hdusstack.writeto(red_path + red_name01.replace('.fits','.head'), overwrite=True, output_verify='silentfix')
                            #             saver = 1
                            #         except Exception as e:
                            #             plog("Failed to write raw file: ", e)
                            #             if "requested" in e and "written" in e:
        
                            #                 plog(check_download_cache())
                            #             plog(traceback.format_exc())
                            #             time.sleep(10)
                            #             saverretries = saverretries + 1

                            # This puts the file into the smartstack queue
                            # And gets it underway ASAP.
                            if ( not frame_type.lower() in [
                                "bias",
                                "dark",
                                "flat",
                                "solar",
                                "lunar",
                                "skyflat",
                                "screen",
                                "spectrum",
                                "auto_focus",
                                "focus",
                                "pointing"
                            ]) and smartstackid != 'no' :
                                self.to_smartstack((paths, pixscale, smartstackid, sskcounter, Nsmartstack, g_dev['mnt'].pier_side))
                            else:
                                if not self.config['keep_reduced_on_disk']:
                                    try:                                
                                        os.remove(red_path + red_name01)
                                    except:
                                        pass
                        
                        # Send data off to process jpeg
                        # This is for a non-focus jpeg
                        if focus_image == False:
                            self.to_mainjpeg((hdusmalldata, smartstackid, paths, g_dev['mnt'].pier_side))
                                                
                        # If this is a focus image, we need to wait until the SEP queue is finished and empty to pick up the latest
                        # FWHM. 
                        if focus_image == True:
                            reported=0
                        
                            plog ("Exposure Complete")

                            g_dev["obs"].send_to_user("Exposure Complete")
                            #queue_clear_time = time.time()
                            while True:
                                if self.sep_processing==False and g_dev['obs'].sep_queue.empty():
                                    break
                                else:
                                    if reported ==0:
                                        plog ("FOCUS: Waiting for SEP processing to complete and queue to clear")
                                        reported=1
                                    pass
                            focus_image = False
                            
                            return self.expresult                        

                        # Good spot to check if we need to nudge the telescope
                        # Allowed to on the last loop of a smartstack
                        # We need to clear the nudge before putting another platesolve in the queue
                        if (Nsmartstack > 1 and (Nsmartstack == sskcounter+1))  :
                            self.currently_in_smartstack_loop=False                    
                        g_dev['obs'].check_platesolve_and_nudge()

                        if not manually_requested_calibration and solve_it == True or ((Nsmartstack == sskcounter+1) and Nsmartstack > 1)\
                                                   or g_dev['obs'].images_since_last_solve > g_dev['obs'].config["solve_nth_image"] or (datetime.datetime.now() - g_dev['obs'].last_solve_time)  > datetime.timedelta(minutes=g_dev['obs'].config["solve_timer"]):
                                                       
                            cal_name = (
                                cal_name[:-9] + "F012" + cal_name[-7:]
                            )                            
                            
                            # Check this is not an image in a smartstack set.
                            # No shifts in pointing are wanted in a smartstack set!
                            image_during_smartstack=False
                            if Nsmartstack > 1 and not (Nsmartstack == sskcounter+1):
                                image_during_smartstack=True
                            
                            
                                
                            
                            if not image_during_smartstack and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread and g_dev['obs'].platesolve_queue.empty() and not g_dev['obs'].platesolve_is_processing:
                                
                                # Make sure any dither or return nudge has finished before platesolution
                                wait_for_slew()
                                # NEED TO CHECK HERE THAT THERE ISN"T ALREADY A PLATE SOLVE IN THE THREAD!
                                self.to_platesolve((hdusmalldata, hdusmallheader, cal_path, cal_name, frame_type, time.time(), pixscale, g_dev['mnt'].mount.RightAscension,g_dev['mnt'].mount.Declination))
                                # If it is the last of a set of smartstacks, we actually want to 
                                # wait for the platesolve and nudge before starting the next smartstack.
                                               
                                    
                                    
                                
                           
                    # Now that the jpeg, sep and platesolve has been sent up pronto,
                    # We turn back to getting the bigger raw, reduced and fz files dealt with
                    if not ( frame_type.lower() in [
                        "bias",
                        "dark",
                        "flat",
                        "focus",
                        "skyflat",
                        "pointing"
                        ]):
                        self.to_slow_process(5,('fz_and_send', raw_path + raw_name00 + ".fz", copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))                    

        
                    # If the files are local calibrations, save them out to the local calibration directory
                    if not manually_requested_calibration and ( frame_type.lower() in [
                        "bias",
                        "dark",
                        "flat",
                        
                        "skyflat"]):
                        self.to_slow_process(200000000, ('localcalibration', raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                    # Similarly to the above. This saves the RAW file to disk
                    # it works 99.9999% of the time.
                   
                    if self.config['save_raw_to_disk']:
                       self.to_slow_process(1000,('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                    
                    
                    # For sites that have "save_to_alt_path" enabled, this routine
                    # Saves the raw and reduced fits files out to the provided directories
                    if self.config["save_to_alt_path"] == "yes":
                        self.to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                       frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                        if "hdusmalldata" in locals():
                            self.to_slow_process(1000,('reduced_alt_path', self.alt_path + g_dev["day"] + "/reduced/" + red_name01, hdusmalldata, hdusmallheader, \
                                                               frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                            
                        
                    # remove file from memory
                    try: 
                        hdu.close()
                    except:
                        pass
                    del hdu  # remove file from memory now that we are doing with it
                    
                    if "hdusmalldata" in locals():                        
                        try: 
                            hdusmalldata.close()
                        except:
                            pass
                        del hdusmalldata  # remove file from memory now that we are doing with it
                                    
                    
                    if not g_dev["cam"].exposure_busy:
                        self.expresult = {"stopped": True}
                        plog ("exposure busy cancelling out of camera")
                        return self.expresult
                    #self.expresult["mean_focus"] = avg_foc[1]
                    try:
                        self.expresult["mean_focus"] = avg_foc[1]
                    except:
                        pass

                    try:
                        self.expresult["mean_rotation"] = avg_rot[1]
                    except:
                        pass
                    if not focus_image:
                        self.expresult["FWHM"] = None
                    self.expresult["half_FD"] = None
                    if self.overscan is not None:
                        self.expresult["patch"] = central_median- self.overscan
                    else:
                        self.expresult["patch"] = central_median
                    self.expresult["calc_sky"] = 0  # avg_ocn[7]
                    self.expresult["temperature"] = 0  # avg_foc[2]
                    self.expresult["gain"] = 0
                    self.expresult["filter"] = self.current_filter
                    self.expresult["error"] == False
                    self.exposure_busy = False

                    plog("Exposure Complete")
                    g_dev["obs"].send_to_user("Exposure Complete")

                    return self.expresult
                except Exception as e:
                    plog("Header assembly block failed: ", e)
                    plog(traceback.format_exc())
                    self.t7 = time.time()
                    self.expresult = {"error": True}
                self.exposure_busy = False
                plog("Exposure Complete")
                g_dev["obs"].send_to_user("Exposure Complete")
                return self.expresult
            else:
                remaining = round(self.completion_time - time.time(), 1)

                if remaining < -30:
                    plog(
                        "Camera timed out; probably is no longer connected, resetting it now."
                    )
                    g_dev["obs"].send_to_user(
                        "Camera timed out; probably is no longer connected, resetting it now.",
                        p_level="INFO",
                    )
                    self.expresult = {"error": True}
                    self.exposure_busy = False
                    plog ("Exposure Complete")
                    g_dev["obs"].send_to_user("Exposure Complete")
                    return self.expresult
            time.sleep(0.1)

    
        
def wait_for_slew():    
    
    try:
        if not g_dev['mnt'].mount.AtPark:
            movement_reporting_timer=time.time()
            while g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                if time.time() - movement_reporting_timer > 2.0:
                    plog( 'm>')
                    movement_reporting_timer=time.time()
                g_dev['obs'].update_status(mount_only=True, dont_wait=True)            
            
    except Exception as e:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        if 'pywintypes.com_error' in str(e):
            plog ("Mount disconnected. Recovering.....")
            time.sleep(30)
            g_dev['mnt'].mount.Connected = True
            #g_dev['mnt'].home_command()
        else:
            pass
    return 

# def check_platesolve_and_nudge(auto_center_off):
    
#     # This block repeats itself in various locations to try and nudge the scope
#     # If the platesolve requests such a thing.
#     if g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
#         g_dev['obs'].pointing_correction_requested_by_platesolve_thread = False
#         if g_dev['obs'].pointing_correction_request_time > g_dev['obs'].time_of_last_slew: # Check it hasn't slewed since request                        
            
#             if auto_center_off:
#                 plog ("Telescope off-center, but auto-centering turned off")
#             else:
#                 plog("Re-centering Telescope Slightly.")
#                 g_dev['obs'].send_to_user("Re-centering Telescope Slightly.")                           
#                 g_dev['mnt'].mount.SlewToCoordinatesAsync(g_dev['obs'].pointing_correction_request_ra, g_dev['obs'].pointing_correction_request_dec)
#                 g_dev['obs'].time_of_last_slew = time.time()
#                 wait_for_slew()
