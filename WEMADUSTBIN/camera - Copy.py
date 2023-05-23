"""
Created on Tue Apr 20 22:19:25 2021

@author: obs, wer, dhunt

"""

import copy
import datetime
import os
import math
import shelve
import time
import traceback
import ephem

from astropy.io import fits, ascii
from astropy.time import Time
from astropy.utils.data import check_download_cache
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.nddata import block_reduce
import glob
import numpy as np
import matplotlib.pyplot as plt   # Please do not remove this import.
import sep
from skimage.io import imsave
from skimage.transform import resize
from auto_stretch.stretch import Stretch
import win32com.client
from planewave import platesolve

from scipy import stats

import colour
import queue
import threading

    
from colour_demosaicing import (
    demosaicing_CFA_Bayer_bilinear,
    demosaicing_CFA_Bayer_Malvar2004,
    demosaicing_CFA_Bayer_Menon2007,
    mosaicing_CFA_Bayer)

from PIL import Image , ImageEnhance

from devices.darkslide import Darkslide
import ptr_utility
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

    CONTROL_BRIGHTNESS = c_int(0)
    CONTROL_GAIN = c_int(6)
    CONTROL_OFFSET = c_int(7)
    CONTROL_EXPOSURE = c_int(8)
    CAM_GPS = c_int(36)
    CONTROL_CURTEMP = c_int(14)
    CONTROL_CURPWM = c_int(15)
    CONTROL_MANULPWM = c_int(16)
    CONTROL_CFWPORT = c_int(17)
    CONTROL_CFWSLOTSNUM = c_int(44)
    CONTROL_COOLER = c_int(18)

    camera_params = {}

    so = None

    def __init__(self, dll_path):
        
            # if sys.maxsize > 2147483647:
            #     print(sys.maxsize)
            #     print('64-Bit')
            # else:
            #     print(sys.maxsize)
            #     print('32-Bit')
        self.so = windll.LoadLibrary(dll_path)
        print('Windows')

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

        # self.so.GetQHYCCDNumberOfReadModes.restype = c_uint32
        # self.so.GetQHYCCDNumberOfReadModes.argtypes = [c_void_p, c_void_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32, c_char_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32]

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
    #breakpoint()
    print("cam   + %s" % cam_id.decode('utf-8'))
    global qhycam_id
    qhycam_id=cam_id
    init_camera_param(cam_id)
    qhycam.camera_params[cam_id]['connect_to_pc'] = True
    os.makedirs(cam_id.decode('utf-8'), exist_ok=True)
    # select read mode
    success = qhycam.so.GetReadModesNumber(cam_id, byref(qhycam.camera_params[cam_id]['read_mode_number']))
    if success == qhycam.QHYCCD_SUCCESS:
        #print('-  read mode - %s' % qhycam.camera_params[cam_id]['read_mode_number'].value)
        for read_mode_item_index in range(0, qhycam.camera_params[cam_id]['read_mode_number'].value):
            read_mode_name = create_string_buffer(qhycam.STR_BUFFER_SIZE)
            qhycam.so.GetReadModeName(cam_id, read_mode_item_index, read_mode_name)
            print('%s  %s %s' % (cam_id.decode('utf-8'), read_mode_item_index, read_mode_name.value))
    else:
        print('GetReadModesNumber false')
        qhycam.camera_params[cam_id]['read_mode_number'] = c_uint32(0)

    read_mode_count = qhycam.camera_params[cam_id]['read_mode_number'].value
    # if read_mode_count == 0:
    #     read_mode_count = 1
    # for read_mode_index in range(0, read_mode_count):
    #     test_frame(cam_id, qhycam.stream_single_mode, cam.bit_depth_16, read_mode_index)
    #     test_frame(cam_id, qhycam.stream_live_mode, cam.bit_depth_16, read_mode_index)
    #     test_frame(cam_id, qhycam.stream_single_mode, cam.bit_depth_8, read_mode_index)
    #     test_frame(cam_id, qhycam.stream_live_mode, cam.bit_depth_8, read_mode_index)
    #     qhycam.so.CloseQHYCCD(cam.camera_params[cam_id]['handle'])


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id.decode('utf-8'))


# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
def get_average_l(image):
    im = np.array(image)
    w, h = im.shape
    return np.average(im.reshape(w * h))

# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
def np_array_to_ascii(pil_image, cols, scale, more_levels):
    global gscale1, gscale2
    W, H = pil_image.size[0], pil_image.size[1]
    print("input image dims: %d x %d" % (W, H))
    w = W / cols
    h = w / scale
    rows = int(H / h)

    print("cols: %d, rows: %d" % (cols, rows))
    print("tile dims: %d x %d" % (w, h))
    if cols > W or rows > H:
        print("Image too small for specified cols!")
        exit(0)

    aimg = []
    for j in range(rows):
        y1 = int(j * h)
        y2 = int((j + 1) * h)

        if j == rows - 1:
            y2 = H

        aimg.append("")

        for i in range(cols):
            x1 = int(i * w)
            x2 = int((i + 1) * w)

            if i == cols - 1:
                x2 = W

            img = pil_image.crop((x1, y1, x2, y2))
            avg = int(get_average_l(img))

            if more_levels:
                gsval = gscale1[int((avg * 69) / 255)]
            else:
                gsval = gscale2[int((avg * 9) / 255)]

            aimg[j] += gsval

    return aimg

# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
def init_camera_param(cam_id):
    if not qhycam.camera_params.keys().__contains__(cam_id):
        qhycam.camera_params[cam_id] = {'connect_to_pc': False,
                                     'connect_to_sdk': False,
                                     'EXPOSURE': c_double(1000.0 * 1000.0),
                                     'GAIN': c_double(54.0),
                                     'CONTROL_BRIGHTNESS': c_int(0),
                                     'CONTROL_GAIN': c_int(6),
                                     'CONTROL_EXPOSURE': c_int(8),
                                     'CONTROL_CURTEMP': c_int(14),
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
                                     'channels': c_uint32(),
                                     'read_mode_number': c_uint32(),
                                     'read_mode_index': c_uint32(),
                                     'read_mode_name': c_char('-'.encode('utf-8')),
                                     'prev_img_data': c_void_p(0),
                                     'prev_img': None,
                                     'handle': None,
                                     }



# These should eventually be in a utility module
def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev["cam"].site_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
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
    camShelf = shelve.open(g_dev["cam"].site_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    seq = camShelf[sKey]  # get an 8 character string
    camShelf.close()
    SEQ_Counter = seq
    return seq


def reset_sequence(pCamera):
    try:
        camShelf = shelve.open(
            g_dev["cam"].site_path + "ptr_night_shelf/" + str(pCamera) + str(g_dev['obs'].name)
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
        
        self.last_user_name = "Tobor"
        self.last_user_id = "Tobor"
        self.user_name = "Tobor"

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



        """
        This section loads in the calibration files for flash calibrations
        """
        
        plog("loading flash dark, bias and flat masters frames if available")        
            
        
        self.biasFiles = {}
        self.darkFiles = {}
        self.flatFiles = {}
        self.hotFiles = {}

        
        try:
            #self.biasframe = fits.open(
            tempbiasframe = fits.open(self.config["archive_path"] +'archive/' + self.alias + "/calibmasters" \
                                      + "/BIAS_master_bin1.fits")
            tempbiasframe = np.array(tempbiasframe[0].data, dtype=np.float32)
            self.biasFiles.update({'1': tempbiasframe})
            del tempbiasframe
        except:
            plog("Bias frame for Binning 1 not available")               
            
        
        try:
            #self.darkframe = fits.open(
            tempdarkframe = fits.open(self.config["archive_path"] + 'archive/' + self.alias + "/calibmasters" \
                                      + "/DARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'1': tempdarkframe})
            del tempdarkframe
        except:
            plog("Dark frame for Binning 1 not available")  

        try:            
            fileList = glob.glob(self.config["archive_path"] + 'archive/' + self.alias + "/calibmasters" \
                                 + "/masterFlat*_bin1.npy")
            
            for file in fileList:
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
            #try:
            #self.camera.Action("EnableFullSensor", "enable")
            #except:
            #    pass
            #self.camera.SetFullFrame()
            #self.camera.SetFullFrame
            
            # ASCOM does not have an EnableFullSensor Action apparently - MTF
            
            
            #self.camera.NumX = int(self.camera_x_size)
            #self.camera.NumY = int(self.camera_y_size)

            
            
            
            #breakpoint()
            # try:
            #     actions = self.camera.SupportedActions
            #     if "EnableFullSensor" in actions:
            #         self.camera.Action("EnableFullSensor", "enable")
            #         plog("Chip size expanded to 4132 x 4117")
            # except:
            #     plog("Chip size not expanded.")
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
    
    
    
    
            #gscale1 = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
            #gscale2 = '@%#*+=-:. '
            
            qhycam.so.RegisterPnpEventIn(pnp_in)
            qhycam.so.RegisterPnpEventOut(pnp_out)
            plog("QHY Direct Control is connected:  ")
            qhycam.so.InitQHYCCDResource()
            qhycam.camera_params[qhycam_id]['handle'] = qhycam.so.OpenQHYCCD(qhycam_id)
            if qhycam.camera_params[qhycam_id]['handle'] is None:
                print('open camera error %s' % cam_id)
            
            success = qhycam.so.SetQHYCCDReadMode(qhycam.camera_params[qhycam_id]['handle'], 0) # 0 is Photographic DSO 16 Bit
            qhycam.camera_params[qhycam_id]['stream_mode'] = c_uint8(qhycam.stream_single_mode)
            success = qhycam.so.SetQHYCCDStreamMode(qhycam.camera_params[qhycam_id]['handle'], qhycam.camera_params[qhycam_id]['stream_mode'])
            print('set StreamMode   =' + str(success))
            
            success = qhycam.so.InitQHYCCD(qhycam.camera_params[qhycam_id]['handle'])
            print('init Camera   =' + str(success))
            
            
            mode_name = create_string_buffer(qhycam.STR_BUFFER_SIZE)
            qhycam.so.GetReadModeName(qhycam_id, 0, mode_name) # 0 is Photographic DSO 16 bit

            success = qhycam.so.SetQHYCCDBitsMode(qhycam.camera_params[qhycam_id]['handle'], c_uint32(qhycam.bit_depth_16))

            success = qhycam.so.GetQHYCCDChipInfo(qhycam.camera_params[qhycam_id]['handle'],
                                               byref(qhycam.camera_params[qhycam_id]['chip_width']),
                                               byref(qhycam.camera_params[qhycam_id]['chip_height']),
                                               byref(qhycam.camera_params[qhycam_id]['image_width']),
                                               byref(qhycam.camera_params[qhycam_id]['image_height']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_width']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_height']),
                                               byref(qhycam.camera_params[qhycam_id]['bits_per_pixel']))

            print('info.   =' + str(success))
            
            
            qhycam.camera_params[qhycam_id]['mem_len'] = qhycam.so.GetQHYCCDMemLength(qhycam.camera_params[qhycam_id]['handle'])
            i_w = qhycam.camera_params[qhycam_id]['image_width'].value
            i_h = qhycam.camera_params[qhycam_id]['image_height'].value
            print('c-w:     ' + str(qhycam.camera_params[qhycam_id]['chip_width'].value), end='')
            print('    c-h: ' + str(qhycam.camera_params[qhycam_id]['chip_height'].value))
            print('p-w:     ' + str(qhycam.camera_params[qhycam_id]['pixel_width'].value), end='')
            print('    p-h: ' + str(qhycam.camera_params[qhycam_id]['pixel_height'].value))
            print('i-w:     ' + str(i_w), end='')
            print('    i-h: ' + str(i_h))
            print('bit: ' + str(qhycam.camera_params[qhycam_id]['bits_per_pixel'].value))
            print('mem len: ' + str(qhycam.camera_params[qhycam_id]['mem_len']))

            val_temp = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
            val_pwm = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURPWM)

            # todo  c_uint8 c_uint16??
            #if bit_depth == cam.bit_depth_16:
            print('using c_uint16()')
            qhycam.camera_params[qhycam_id]['prev_img_data'] = (c_uint16 * int(qhycam.camera_params[qhycam_id]['mem_len'] / 2))()
            #else:
            #    print('using c_uint8()')
            #    cam.camera_params[cam_id]['prev_img_data'] = (c_uint8 * cam.camera_params[cam_id]['mem_len'])()

            success = qhycam.QHYCCD_ERROR
            
            
            qhycam.so.SetQHYCCDResolution(qhycam.camera_params[qhycam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                           c_uint32(i_h))
            
            
            # success = qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
            # print('exp  single = ' + str(success))
            
            
            
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()
            
            
            
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(20000))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_GAIN, c_double(30))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_OFFSET, c_double(40))
            
            
            
            
            
            # success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
            #                                       byref(image_width_byref),
            #                                       byref(image_height_byref),
            #                                       byref(bits_per_pixel_byref),
            #                                       byref(qhycam.camera_params[qhycam_id]['channels']),
            #                                       byref(qhycam.camera_params[qhycam_id]['prev_img_data']))
            # print('read  single = ' + str(success))
            
            
            # qhycam.camera_params[qhycam_id]['prev_img'] = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
            # print("---------------->" + str(len(qhycam.camera_params[qhycam_id]['prev_img'])))
            # image_size = i_h * i_w
            # print("image size =     " + str(image_size))
            # print("prev_img_list sub length-->" + str(len(qhycam.camera_params[qhycam_id]['prev_img'])))
            # print("Image W=" + str(i_w) + "        H=" + str(i_h))
            # qhycam.camera_params[qhycam_id]['prev_img'] = qhycam.camera_params[qhycam_id]['prev_img'][0:image_size]
            # image = np.reshape(qhycam.camera_params[qhycam_id]['prev_img'], (i_h, i_w))
            
            # print (image)
            
            
            #breakpoint()
            
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
        self.setpoint = float(self.config["camera"][self.name]["settings"]["temp_setpoint"])
        self._set_setpoint(self.setpoint)
        plog("Cooler setpoint is now:  ", self.setpoint)
        if self.config["camera"][self.name]["settings"][
            "cooler_on"
        ]:  # NB NB why this logic, do we mean if not cooler found on, then turn it on and take the delay?
            self._set_cooler_on()
        plog("Cooler Cooling beginning @:  ", self._temperature())
        #time.sleep(5)
        if self.maxim == True:
            plog("TEC  % load:  ", self._maxim_cooler_power())
        self.current_filter = (
            0  # W in Apache Ridge case. #This should come from config, filter section
        )
        self.exposure_busy = False
        self.cmd_in = None
        self.t7 = None
        self.camera_message = "-"
        #self.site_path = self.config["client_path"]

        self.site_path = self.config["client_path"] + self.config['site_id'] + '/'
        if not os.path.exists(self.site_path):
            os.makedirs(self.site_path)
        self.archive_path = self.config["archive_path"] + self.config['site_id'] + '/'+ "archive/"
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['site_id']):
            os.makedirs(self.config["archive_path"] +'/' + self.config['site_id'])
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['site_id']+ '/'+ "archive/"):
            os.makedirs(self.config["archive_path"] +'/' + self.config['site_id']+ '/'+ "archive/")
        self.camera_path = self.archive_path + self.alias + "/"
        if not os.path.exists(self.camera_path):
            os.makedirs(self.camera_path)
        self.alt_path = self.config[
            "alt_path"
        ]  +'/' + self.config['site_id']+ '/' # NB NB this should come from config file, it is site dependent.
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
                self.config["archive_path"]
                + "archive/"
                + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
            )
            try:
                os.mkdir(
                    self.config["archive_path"]
                    + "archive/"
                    + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
                )
            except:
                plog("Couldn't make autosave directory")
                
        """
        Actually not sure if this is useful anymore if there are no differences 
        between ccds and cmoses? This may just be used for the fits header
        at the end of the day.
        """                
        if self.config["camera"][self.name]["settings"]["is_cmos"] == True:
            self.is_cmos = True
        else:
            self.is_cmos = False
            
        
        self.camera_model = self.config["camera"][self.name]["desc"]
        # NB We are reading from the actual camera or setting as the case may be. For initial setup,
        # we pull from config for some of the various settings.
        # NB NB There is a differenc between normal cameras and the QHY when it is set to Bin2.
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
            self.camera_x_size = self.camera.CameraXSize  #unbinned values. QHY returns 2
            self.camera_y_size = self.camera.CameraYSize  #unbinned
        except:
            self.camera_x_size = self.config['camera'][self.name]['settings']['CameraXSize']
            self.camera_y_size = self.config['camera'][self.name]['settings']['CameraYSize']

        self.camera_start_x = self.config["camera"][self.name]["settings"]["StartX"]
        self.camera_start_y = self.config["camera"][self.name]["settings"]["StartY"]
        if self.config["camera"][self.name]["settings"]["cam_needs_NumXY_init"]:  # WER 20230217
            try:    
                self.camera.NumX = self.camera_x_size
                self.camera.NumY = self.camera_y_size
            except:
                plog ('numx initialise didnot work')
            try:
                self.camera.StartX = 0
                self.camera.StartY = 0
                self.camera.BinX = 1
                self.camera.BinY = 1
            except:
                plog ("self.camera setup didn't work... may be a QHY")
            plog('Num X , y set for QHY camera.')
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


        # A flag to tell the camera main queue
        # whether the separate sep thread has completed yet
        self.sep_processing=False

        
        try:
            seq = test_sequence(self.alias)
        except:
            reset_sequence(self.alias)
            
        
    


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

    # def _theskyx_set_setpoint(self, p_temp):
    #     plog("NOT SURE HOW TO SET TEMP POINT IN THE SKY YET")
    #     self.camera.TemperatureSetPoint = float(p_temp)
    #     return self.camera.TemperatureSetPoint

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
        #plog("I am not sure what this function is asking for")
        return self.camera.RegulateTemperature  # NB NB NB This would be a good place to put a warming protector

    def _theskyx_set_cooler_on(self):
        self.camera.RegulateTemperature = True
        #plog("3s wait for cooler to start up.")
        #time.sleep(3)
        return (
            self.camera.RegulateTemperature
        )  # NB NB NB This would be a good place to put a warming protector

    def _theskyx_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        return self.camera.TemperatureSetpoint

    def _theskyx_setpoint(self):
        return self.camera.TemperatureSetpoint

    def theskyx_async_expose(self):
        self.async_exposure_lock=True
        tempcamera = win32com.client.Dispatch(self.driver)
        tempcamera.Connect()
        tempcamera.TakeImage()
        tempcamera.ShutDownTemperatureRegulationOnDisconnect = False
        #tempcamera.Disconnect()
        self.async_exposure_lock=False

    def _theskyx_expose(self, exposure_time, imtypeb):
        self.camera.ExposureTime = exposure_time
        plog ("imtypeb: " + str(imtypeb))
        if imtypeb == 0:
            self.camera.Frame = 3 
        else:
            self.camera.Frame = 1
        #breakpoint()
        #self.async_camera_exposure_queue.put('expose_please', block=False)
        thread=threading.Thread(target=self.theskyx_async_expose)
        thread.start()
        #breakpoint()
        #self.camera.TakeImage()
    


    def _theskyx_stop_expose(self):
        self.camera.AbortExposure()

    def _theskyx_imageavailable(self):
        plog(self.camera.IsExposureComplete)
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
        return self.camera.Temperature

    def _maxim_cooler_power(self):
        return self.camera.CoolerPower

    def _maxim_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _maxim_cooler_on(self):
        return (
            self.camera.CoolerOn
        )  # NB NB NB This would be a good place to put a warming protector

    def _maxim_set_cooler_on(self):
        self.camera.CoolerOn = True
        #plog("3s wait for cooler to start up.")
        #time.sleep(3)
        return (
            self.camera.CoolerOn
        )  # NB NB NB This would be a good place to put a warming protector

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
            print ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp

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

    def _ascom_expose(self, exposure_time, imtypeb):
        self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
        self.camera.StopExposure()  # ASCOM also has an AbortExposure method.

    def _ascom_getImageArray(self):
        return np.asarray(self.camera.ImageArray)


    def _qhyccd_connected(self):
        print ("MTF still has to connect QHY stuff")
        return True
    
    def _qhyccd_imageavailable(self):
        print ("QHY CHECKING FOR IMAGE AVAILABLE - NOT YET IMPLEMENTED - MTF")
        return True
    
    def _qhyccd_connect(self, p_connect):
        #self.camera.Connected = p_connect
        print ("I guess the QHY is connected!")
        return True
    
    def _qhyccd_temperature(self):
        try: 
            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
        except:
            print ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp
    
    def _qhyccd_cooler_on(self):
        print ("QHY CHECKING IF COOLER IS ON - NOT YET IMPLEMENTED")
        
        return True
    
    def _qhyccd_set_cooler_on(self):
        try: 
            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
        except:
            print ("failed at getting the CCD temperature")
            temptemp=999.9
        return True
        #self.camera.CoolerOn = True
        #return self.camera.CoolerOn
    
    def _qhyccd_set_setpoint(self, p_temp):
        #if self.camera.CanSetCCDTemperature:
        #    self.camera.SetCCDTemperature = float(p_temp)
        #    return self.camera.SetCCDTemperature
        #else:
        #    plog("Camera cannot set cooling temperature.")
        #    return p_temp

        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP, c_double(-10))
        #breakpoint()
        print (temptemp)
        return 
    
    def _qhyccd_setpoint(self):
        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP, c_double(-10))
        print (temptemp)
        return 
    
    def _qhyccd_expose(self, exposure_time, imtypeb):
        
        success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exposure_time*1000*1000))
        qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
        
        
        
        #self.camera.StartExposure(exposure_time, imtypeb)
    
    def _qhyccd_stop_expose(self):
        success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
        #self.camera.StopExposure()  # ASCOM also has an AbortExposure method.
    
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
        #print('read  single = ' + str(success))
        
        
        i_w = qhycam.camera_params[qhycam_id]['image_width'].value
        i_h = qhycam.camera_params[qhycam_id]['image_height'].value
        #qhycam.camera_params[qhycam_id]['prev_img'] = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
        #print("---------------->" + str(len(qhycam.camera_params[qhycam_id]['prev_img'])))
        image_size = i_h * i_w
        #print("image size =     " + str(image_size))
        #print("prev_img_list sub length-->" + str(len(qhycam.camera_params[qhycam_id]['prev_img'])))
        #print("Image W=" + str(i_w) + "        H=" + str(i_h))
        qhycam.camera_params[qhycam_id]['prev_img'] = qhycam.camera_params[qhycam_id]['prev_img'][0:image_size]
        #image = 
        
        #print (image)
        
        
        
        return np.reshape(qhycam.camera_params[qhycam_id]['prev_img'], (i_h, i_w)) #image





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
        if self.maxim:
            cam_stat = "Not implemented yet"  #
        if self.ascom:
            cam_stat = "ASCOM camera not implemented yet"  # self.camera.CameraState
        if self.theskyx:
            cam_stat = "TheSkyX camera not implemented yet"  # self.camera.CameraState
        if self.qhydirect:
            cam_stat = "QHYCCD camera not implemented yet"  # self.camera.CameraState
        status[
            "status"
        ] = cam_stat  # The state could be expanded to be more meaningful.
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
        if action == "expose" and not self.exposure_busy:
            self.expose_command(req, opt, do_sep=True, quick=False)
            self.exposure_busy = False  # Hangup needs to be guarded with a timeout.
            self.active_script = None

        elif action == "expose" and self.exposure_busy:
            plog("Cannot expose, camera is currently busy, waiting for exposure to clear")
            while True:
                if self.exposure_busy:
                    time.sleep(0.5)
                else:
                    break
            self.expose_command(req, opt, do_sep=True, quick=False)
            self.exposure_busy = False  # Hangup needs to be guarded with a timeout.
            self.active_script = None

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
        gather_status=True,
        do_sep=True,
        no_AWS=False,
        quick=False,
        solve_it=False,
        calendar_event_id=None,
        skip_open_check=False,
        skip_daytime_check=False
    ):
        """
        This is Phase 1:  Setup the camera.
        Apply settings and start an exposure.
        Quick=True is meant to be fast.  We assume the ASCOM/Maxim imageBuffer is the source of data in that mode,
        not the slower File Path.  THe mode used for focusing or other operations where we do not want to save any
        image data.
        """
        
        # First check that it isn't an exposure that doesn't need a check (e.g. bias, darks etc.)
        if not skip_open_check:
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
        
        
        if not skip_daytime_check:
            sun_az, sun_alt = g_dev['evnt'].sun_az_alt_now()
            if sun_alt > -5:
                if exposure_time > float(self.config["camera"][self.name]["settings"]['max_daytime_exposure']):
                    g_dev['obs'].send_to_user("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    plog("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    exposure_time = float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])
            #breakpoint()
            
            
        
        self.exposure_busy = True # This really needs to be here from the start
        # We've had multiple cases of multiple camera exposures trying to go at once
        # And it is likely because it takes a non-zero time to get to Phase II
        # So even in the setup phase the "exposure" is "busy"
        
        self.tempStartupExposureTime=time.time()


        # # Force a reseek //eventually dither//
        # try:
        #     if (
        #         g_dev["mnt"].last_seek_time < self.t0 - 180  #NB this is faulting, no se.f.t0 exists
        #     ):  # NB Consider upping this to 300 to 600 sec.
        #         plog("re_seeking")
        #         g_dev["mnt"].re_seek(
        #             0
        #         )  # is a placeholder for a dither value being passed.
        # except:
        #     pass


        opt = optional_params
        plog ("optional params :", opt)
        self.hint = optional_params.get("hint", "")
        self.script = required_params.get("script", "None")
        
        
        no_AWS, self.toss = True if imtype.lower() == "test image" else False, False
        quick = True if imtype.lower() == "quick" else False
        #  NBNB this is obsolete and needs rework 20221002 WER
        if imtype.lower() in (
            "quick",
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
            do_sep = False
        else:
            do_sep = True

        if imtype.lower() in ("bias", "dark", "lamp flat"):
            if imtype.lower() == "bias":
                exposure_time = 0.0
            imtypeb = False  # don't open the shutter.
            lamps = "turn on led+tungsten lamps here, if lampflat"
            frame_type = imtype.replace(" ", "")
        elif imtype.lower() in ("near flat", "thor flat", "arc flat"):
            imtypeb = False
            lamps = "turn on ThAr or NeAr lamps here"
            frame_type = "arc"
        elif imtype.lower() in ("sky flat", "screen flat", "solar flat"):
            imtypeb = True  # open the shutter.
            lamps = "screen lamp or none"
            frame_type = imtype.replace(
                " ", ""
            )  # note banzai doesn't appear to include screen or solar flat keywords.
        elif imtype.lower() == "focus":
            frame_type = "focus"
            imtypeb = True
            lamps = None
        else:  # 'light', 'experimental', 'autofocus probe', 'quick', 'test image', or any other image type
            imtypeb = True
            lamps = None
            if imtype.lower() in ("experimental", "autofocus probe", "auto_focus"):
                frame_type = "experimental"
            else:
                frame_type = "expose"
        
        self.smartstack = required_params.get('smartstack', 'yes')
        self.longstack = required_params.get('longstackswitch', 'no')
    
        if self.longstack == 'no':
            LongStackID ='no'
        elif not 'longstackname' in required_params:
            LongStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
        else:
            LongStackID = required_params['longstackname']


        self.blockend = required_params.get('block_end', "None")


        self.pane = optional_params.get("pane", None)


        bin_x = 1               
        bin_y = 1  # NB This needs fixing someday!
        self.bin = 1
        self.ccd_sum = str(1) + ' ' + str(1)
        bin_x = 1
        bin_y = 1
        


        readout_time = float(
            self.config["camera"][self.name]["settings"]["cycle_time"]
        )

    
        
        self.estimated_readtime = (
            exposure_time + readout_time
        )  


        count = int(
            optional_params.get("count", 1)
        )  
        
        lcl_repeat = 1
        if count < 1:
            count = 1  # Hence frame does not repeat unless count > 1

        # Here we set up the filter, and later on possibly rotational composition.
        try:
            
            if g_dev["fil"].null_filterwheel == False:
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
                    self.current_filter = g_dev["fil"].set_name_command(
                        {"filter": requested_filter_name}, {}
                    )
                    
                    self.current_offset = g_dev[
                        "fil"
                    ].filter_offset  # TEMP   NBNBNB This needs fixing
                    
                self.current_filter = g_dev['fil'].filter_selected
                
                if self.current_filter == "none":
                    plog("skipping exposure as no adequate filter match found")
                    self.exposure_busy = False
                    return
            else:
                #plog ("No filter wheel, not selecting a filter")
                self.current_filter = self.config["filter_wheel"]["filter_wheel1"]["name"]
        except Exception as e:
            plog("Camera filter setup:  ", e)
            plog(traceback.format_exc())      

        self.len_x = self.camera_x_size // bin_x
        self.len_y = self.camera_y_size // bin_y  # Unit is binned pixels.
        self.len_xs = 0  # THIS IS A HACK, indicating no overscan.
        
         # Always check rotator just before exposure
        rot_report=0
        if g_dev['rot']!=None:                
            while g_dev['rot'].rotator.IsMoving:                    
                #if g_dev['rot'].rotator.IsMoving:                                         
                    if rot_report == 0:
                        plog("Waiting for camera rotator to catch up. ")
                        g_dev["obs"].send_to_user("Waiting for camera rotator to catch up before exposing.")
                                    
                        rot_report=1
                    time.sleep(0.2)                                
                            

        self.expresult = {}  #  This is a default return just in case
        num_retries = 0
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
                if g_dev['events']['Observing Ends'] < ephem.Date(ephem.now()+ (exposure_time *ephem.second)):
                    plog ("Sorry, exposures are outside of night time.")
                    self.exposure_busy = False
                    break

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
            if not imtype.lower() in ["light"]:
                Nsmartstack=1
                SmartStackID='no'
            elif (self.smartstack == 'yes' or self.smartstack == True) and (exposure_time >= 3*ssExp):
                Nsmartstack=np.ceil(exposure_time / ssExp)
                exposure_time=ssExp
                SmartStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
            else:
                Nsmartstack=1
                SmartStackID='no'
        
            self.retry_camera = 3
            self.retry_camera_start_time = time.time()

            #Repeat camera acquisition loop to collect all smartstacks necessary
            #The variable Nsmartstacks defaults to 1 - e.g. normal functioning
            #When a smartstack is not requested.
            for sskcounter in range(int(Nsmartstack)):
                if Nsmartstack > 1 :
                    plog ("Smartstack " + str(sskcounter+1) + " out of " + str(Nsmartstack))
                    g_dev['obs'].update_status(cancel_check=False)
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
                        return

                    # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                    if not 'None' in self.blockend: # Only do this check if a block end was provided.
                        
                    # Check that the exposure doesn't go over the end of a block
                        endOfExposure = datetime.datetime.now() + datetime.timedelta(seconds=exposure_time)
                        now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'
                        blockended = now_date_timeZ  >= self.blockend
                        if blockended or ephem.Date(ephem.now()+ (exposure_time *ephem.second)) >= \
                            g_dev['events']['End Morn Bias Dark']:
                            plog ("Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            self.exposure_busy = False
                            return 'blockend'
                    
                    # Check that the calendar event that is running the exposure
                    # Hasn't completed already
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    #print ("LOOKING FOR CALENDAR!")
                    if not calendar_event_id == None:
                        g_dev['obs'].scan_requests()
                        foundcalendar=False                    
                        for tempblock in g_dev['obs'].blocks:
                            print (tempblock['event_id'])
                            if tempblock['event_id'] == calendar_event_id :
                                print ("FOUND CALENDAR!")
                                foundcalendar=True
                        if foundcalendar == False:
                            print ("could not find calendar entry, cancelling out of block.")
                            self.exposure_busy = False
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            return 'calendarend'
                    
                        #breakpoint()    
                    
                    # NB Here we enter Phase 2
                    try:
                        #self.t1 = time.time()
                        self.exposure_busy = True                       

                        if self.maxim or self.ascom or self.theskyx or self.qhydirect:

                            ldr_handle_time = None
                            ldr_handle_high_time = None  #  This is not maxim-specific

                            if self.darkslide and imtypeb:
                                if self.darkslide_state != 'Open':
                                    self.darkslide_instance.openDarkslide()
                                    self.darkslide_open = True
                                    self.darkslide_state = 'Open'
                            elif self.darkslide and not imtypeb:
                                if self.darkslide_state != 'Closed':
                                    self.darkslide_instance.closeDarkslide()
                                    self.darkslide_open = False
                                    self.darkslide_state = 'Closed'
                            else:
                                pass
 
                            self.pre_mnt = []
                            self.pre_rot = []
                            self.pre_foc = []
                            self.pre_ocn = []
                            self.t2p1 = time.time()
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
                                    + " focus exposure.",
                                    p_level="INFO",
                                )
                            else:
                                if "object_name" in opt:
                                    g_dev["obs"].send_to_user(
                                        "Starting "
                                        + str(exposure_time)
                                        + "s exposure of "
                                        + str(opt["object_name"])
                                        + " by user: "
                                        + str(self.user_name),
                                        p_level="INFO",
                                    )
                                else:
                                    g_dev["obs"].send_to_user(
                                        "Starting an unnamed frame by user: "
                                        + str(self.user_name),
                                        p_level="INFO",
                                    )
                            try:
                                g_dev["ocn"].get_quick_status(
                                    self.pre_ocn
                                )  # NB NB WEMA must be running or this may fault.
                            except:
                                plog(
                                    "ocn quick status failing"
                                )
                            g_dev["foc"].get_quick_status(self.pre_foc)
                            try:
                                g_dev["rot"].get_quick_status(self.pre_rot)
                            except:
                                #plog("There is perhaps no rotator")
                                pass

                            g_dev["mnt"].get_rapid_exposure_status(
                                self.pre_mnt
                            )  # Should do this close to the exposure

                            if imtypeb:
                                imtypeb = 1
                            else:
                                imtypeb = 0
                            self.t2 = time.time()
                
                            # Good spot to check if we need to nudge the telescope
                            check_platesolve_and_nudge()   
                            
                            self._expose(exposure_time, imtypeb)
                            
                            g_dev['obs'].time_since_last_exposure = time.time()
                        else:
                            plog("Something terribly wrong, driver not recognized.!")
                            self.expresult = {}
                            self.expresult["error":True]
                            self.exposure_busy = False
                            return self.expresult
                        #self.t9 = time.time()
                        
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
                            bin_x=bin_x
                        )  # NB all these parameters are crazy!
                        self.exposure_busy = False
                        #self.t10 = time.time()

                        self.retry_camera = 0
                        break
                    except Exception as e:
                        plog("Exception in camera retry loop:  ", e)
                        plog(traceback.format_exc())
                        self.retry_camera -= 1
                        num_retries += 1
                        self.exposure_busy = False
                        continue
        #  This is the loop point for the seq count loop
        #self.t11 = time.time()
        self.exposure_busy = False
        return self.expresult

    def stop_command(self, required_params, optional_params):
        """Stop the current exposure and return the camera to Idle state."""
        self._stop_expose()
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
        bin_x=1
    ):
        plog(
            "Finish exposure Entered:  " + str(exposure_time) + "sec.;   # of ",
            frame_type,
            "to go: ",
            counter,
        )



        #plog ("Smart Stack ID: " + smartstackid)
        # g_dev["obs"].send_to_user(
        #     "Starting "
        #     + str(exposure_time)
        #     + " second exposure. Number of "
        #     + frame_type
        #     + " frames remaining: "
        #     + str(counter),
        #     p_level="INFO",
        # )
        # , gather_status, do_sep, no_AWS, start_x, start_y, opt['area'])
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

        self.completion_time = self.t2 + cycle_time
        self.expresult = {"error": False}
        quartileExposureReport = 0
        self.plog_exposure_time_counter_timer=time.time() -3.0
        
        exposure_scan_request_timer=time.time()
        
        while True:  # This loop really needs a timeout.
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []        

            
            if (
                time.time() < self.completion_time or self.async_exposure_lock==True
            ):  
                #self.t7b = time.time()
                
                
                # Scan requests every 4 seconds... primarily hunting for a "Cancel/Stop"
                if exposure_scan_request_timer - time.time() > 4:                    
                    exposure_scan_request_timer=time.time()
                    g_dev['obs'].scan_requests()
                
                remaining = round(self.completion_time - time.time(), 1)
                
                
                if remaining > 0:  
                    if time.time() - self.plog_exposure_time_counter_timer > 10.0:
                        self.plog_exposure_time_counter_timer=time.time()
                        plog(
                            '||  ' + str(round(remaining, 1)) + "sec.",
                            str(round(100 * remaining / cycle_time, 1)) + "%",
                        )  #|| used to flag this line in plog().
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
                        if (exposure_time > 120):
                            g_dev["obs"].update_status(cancel_check=False)

                continue

            incoming_image_list = []
            #self.t4 = time.time()

            if self.async_exposure_lock == False and self._imageavailable():   #NB no more file-mode
                try:
                    g_dev["mnt"].get_rapid_exposure_status(
                        self.post_mnt
                    )  # Need to pick which pass was closest to image completion
                except:
                    #plog("need to get this mount status done")
                    pass
                try:
                    g_dev["rot"].get_quick_status(self.post_rot)
                except:
                    #plog("There is no rotator?")
                    pass
                g_dev["foc"].get_quick_status(self.post_foc)
                try:
                    g_dev["ocn"].get_quick_status(self.post_ocn)
                except:
                    #plog("OCN status not quick updated")
                    pass
                

                self.t4p4 = time.time()
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
                        if "Image Not Available" in str(e):
                            plog("Still waiting for file to arrive: ", e)
                        time.sleep(3)
                        retrycounter = retrycounter + 1          
                self.t4p5 = time.time()

                
                plog("READOUT READOUT READOUT:  ", round(self.t4p5-self.t4p4, 1))

                if frame_type in ["bias", "dark"] or frame_type[-4:] == ['flat']:
                    plog("Median of full-image area bias, dark or flat:  ", np.median(self.img))

                pedastal = 0
                self.overscan = 0

               
                pier_side = g_dev["mnt"].pier_side  # 0 == Tel Looking West, is flipped.
            
                ix, iy = self.img.shape
                #self.t77 = time.time() 

                image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                # Get bi_mean of middle patch for flat usage                
                #test_saturated = np.array(self.img[ix // 3 : ix * 2 // 3, iy // 3 : iy * 2 // 3]) 
                test_saturated = self.img[ix // 3 : ix * 2 // 3, iy // 3 : iy * 2 // 3]
                # 1/9th the chip area, but central.   NB NB why 3, is this what flat uses???
                bi_mean = round((test_saturated.mean() + np.median(test_saturated)) / 2, 1)
                
                
                if frame_type[-4:] == "flat":                      
                    
                    if (
                        bi_mean
                        >= 0.75* image_saturation_level
                    ):
                        plog("Flat rejected, center is too bright:  ", bi_mean)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too bright.", p_level="INFO"
                        )
                        self.expresult["error"] = True
                        self.expresult["patch"] = bi_mean
                        return self.expresult  # signals to flat routine image was rejected, prompt return
                    
                    elif (
                        bi_mean
                        <= 0.25 * image_saturation_level
                    ):
                        plog("Flat rejected, center is too dim:  ", bi_mean)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        self.expresult["error"] = True
                        self.expresult["patch"] = bi_mean
                        return self.expresult  # signals to flat routine image was rejected, prompt return
                    else:
                        plog('Good flat value! :  ', bi_mean)
                    
                if not g_dev["cam"].exposure_busy:
                    self.expresult = {"stopped": True}
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
                    #plog("No Rotator")
                try:
                    avg_ocn = g_dev["ocn"].get_average_status(
                        self.pre_ocn, self.post_ocn
                    )
                except:
                    pass
                    #plog("no ocn")

                try:
                     
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
                        hdu = fits(
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

                    
                    #This should plot out  0,0 color pixel for an OSC camera and plot it. Yellow is larger! 
                    # self.tsp = hdu.data
                    # plog(self.tsp[0:2, 24:26])
                    # plt.imshow(self.tsp[0:2, 24:26])
                    # del self.tsp

                    # It is faster to store the current binning than keeping on asking ASCOM throughout this
                    #tempBinningCodeX=self.camera.BinX
                    #tempBinningCodeY=self.camera.BinY
                    tempBinningCodeX=self.bin
                    tempBinningCodeY=self.bin


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
                        round(float(hdu.header["CCDXPIXE"] * tempBinningCodeX), 3),
                        "[um] Size of binned pixel",
                    )
                    hdu.header["YPIXSZ"] = (
                        round(float(hdu.header["CCDYPIXE"] * tempBinningCodeY), 3),
                        "[um] Size of binned pixel",
                    )
                    try:
                        hdu.header["XBINING"] = (
                            tempBinningCodeX,
                            "Pixel binning in x direction",
                        )
                        hdu.header["YBINING"] = (
                            tempBinningCodeY,
                            "Pixel binning in y direction",
                        )
                    except:
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
                    if self.maxim:

                        hdu.header["CCDSTEMP"] = (
                            round(self.camera.TemperatureSetpoint, 3),
                            "[C] CCD set temperature",
                        )
                        hdu.header["CCDATEMP"] = (
                            round(self.camera.Temperature, 3),
                            "[C] CCD actual temperature",
                        )

                    if self.ascom:
                        hdu.header["CCDSTEMP"] = (
                            round(self.camera.SetCCDTemperature, 3),
                            "[C] CCD set temperature",
                        )
                        hdu.header["CCDATEMP"] = (
                            round(self.camera.CCDTemperature, 3),
                            "[C] CCD actual temperature",
                        )
                    hdu.header["COOLERON"] = self._cooler_on()
                    hdu.header["SITEID"] = (
                        self.config["site_id"].replace("-", "").replace("_", "")
                    )
                    hdu.header["TELID"] = self.config["telescope"]["telescope1"][
                        "telescop"
                    ][:4]
                    hdu.header["TELESCOP"] = self.config["telescope"]["telescope1"][
                        "telescop"
                    ][:4]
                    hdu.header["PTRTEL"] = self.config["telescope"]["telescope1"][
                        "ptrtel"
                    ]
                    hdu.header["PROPID"] = "ptr-" + self.config["site_id"] + "-001-0001"
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
                        self.config["camera"][self.name]["settings"]["reference_gain"],
                        "[e-/ADU] Pixel gain",
                    )
                    hdu.header["RDNOISE"] = (
                        self.config["camera"][self.name]["settings"]["reference_noise"],
                        "[e-/pixel] Read noise",
                    )
                    hdu.header["CMOSCAM"] = (self.is_cmos, "Is CMOS camera")
                    try:
                        hdu.header["FULLWELL"] = (
                            self.config["camera"][self.name]["settings"][
                                "fullwell_capacity"
                            ],
                            "Full well capacity",
                        )
                    except:
                        plog ("Full well capacity not set for this binning in the site-config")
                    hdu.header["CMOSGAIN"] = (0, "CMOS Camera System Gain")
                    hdu.header["CMOSOFFS"] = (10, "CMOS Camera offset")
                    hdu.header["CAMOFFS"] = (10, "Camera offset")
                    hdu.header["CAMGAIN"] = (0, "Camera gain")
                    hdu.header["CAMUSBT"] = (60, "Camera USB traffic")
                    hdu.header["TIMESYS"] = ("UTC", "Time system used")
                    hdu.header["DATE"] = (
                        datetime.date.strftime(
                            datetime.datetime.utcfromtimestamp(self.t2), "%Y-%m-%d"
                        ),
                        "Date FITS file was written",
                    )
                    hdu.header["DATE-OBS"] = (
                        datetime.datetime.isoformat(
                            datetime.datetime.utcfromtimestamp(self.t2)
                        ),
                        "Start date and time of observation",
                    )
                    hdu.header["DAY-OBS"] = (
                        g_dev["day"],
                        "Date at start of observing night",
                    )
                    hdu.header["MJD-OBS"] = (
                        Time(self.t2, format="unix").mjd,
                        "[UTC days] Modified Julian Date start date/time",
                    )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
                    yesterday = datetime.datetime.now() - datetime.timedelta(1)
                    hdu.header["L1PUBDAT"] = datetime.datetime.strftime(
                        yesterday, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )  # IF THIS DOESN"T WORK, subtract the extra datetime ...
                    hdu.header["JD-START"] = (
                        Time(self.t2, format="unix").jd,
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
                    hdu.header["DATE-OBS"] = datetime.datetime.isoformat(
                        datetime.datetime.utcfromtimestamp(self.t2)
                    )
                    hdu.header[
                        "EXPTIME"
                    ] = exposure_time  # This is the exposure in seconds specified by the user
                    hdu.header[
                        "EXPOSURE"
                    ] = exposure_time  # Ideally this needs to be calculated from actual times
                    hdu.header["FILTER"] = (
                        self.current_filter,
                        "Filter type",
                    )  # NB this should read from the wheel!
                    if g_dev["fil"].null_filterwheel == False:
                        try:
                            hdu.header["FILTEROF"] = (self.current_offset, "Filter offset")
                        except:
                            pass # sometimes the offset isn't set on the first filter of the eve
                        hdu.header["FILTRNUM"] = (
                           "PTR_ADON_HA_0023",
                           "An index into a DB",
                           ) 
                    else:
                        hdu.header["FILTEROF"] = ("No Filter", "Filer offset")
                        hdu.header["FILTRNUM"] = (
                            "No Filter",
                            "An index into a DB",
                        )  # Get a number from the hardware or via Maxim.  NB NB why not cwl and BW instead, plus P
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
                        #plog ("need to fix TIMSEC etc. in site-config")
                        pass

                    hdu.header["SATURATE"] = (
                        float(image_saturation_level),
                        "[ADU] Saturation level",
                    )  # will come from config(?)
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
                        round(float(self.config["latitude"]), 6),
                        "[Deg N] Telescope Latitude",
                    )
                    hdu.header["LONGITUD"] = (
                        round(float(self.config["longitude"]), 6),
                        "[Deg E] Telescope Longitude",
                    )
                    hdu.header["HEIGHT"] = (
                        round(float(self.config["elevation"]), 2),
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


                    tempRAdeg = float(g_dev["mnt"].current_icrs_ra) * 15
                    tempDECdeg = g_dev["mnt"].current_icrs_dec



                    tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
                    tempointing=tempointing.to_string("hmsdms").split(' ')

                    hdu.header["RA"] = (
                        tempRAdeg,
                        "[deg] Telescope right ascension",
                    )
                    hdu.header["DEC"] = (
                        tempDECdeg,
                        "[deg] Telescope declination",
                    )
                    hdu.header["ORIGRA"] = hdu.header["RA"]
                    hdu.header["ORIGDEC"] = hdu.header["DEC"]
                    hdu.header["RAhrs"] = (
                        g_dev["mnt"].current_icrs_ra,
                        "[hrs] Telescope right ascension",
                    )
                    hdu.header["RA-hms"] = tempointing[0]
                    hdu.header["DEC-dms"] = tempointing[1]

                    hdu.header["TARG-CHK"] = (
                        (g_dev["mnt"].current_icrs_ra * 15)
                        + g_dev["mnt"].current_icrs_dec,
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

                    hdu.header["TARGRA"] = float(g_dev["mnt"].current_icrs_ra) * 15
                    hdu.header["TARGDEC"] = g_dev["mnt"].current_icrs_dec
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

                    try:
                        hdu.header["OBSERVER"] = (
                            self.user_name,
                            "Observer name",
                        )
                    except:
                        hdu.header["OBSERVER"] = (
                            "kilroy visited",
                            "Observer name",
                        )
                    hdu.header["OBSNOTE"] = self.hint[0:54]  # Needs to be truncated.
                    if self.maxim:
                        hdu.header[
                            "FLIPSTAT"
                        ] = "None"  # This is a maxim camera setup, not a flip status
                    hdu.header["DITHER"] = (0, "[] Dither")
                    hdu.header["OPERATOR"] = ("WER", "Site operator")
                    hdu.header["ENCLOSUR"] = (
                        self.config["enclosure"]["enclosure1"]["name"],
                        "Enclosure description",
                    )  # "Clamshell"   #Need to document shutter status, azimuth, internal light.
                    if g_dev["enc"].is_dome:
                        hdu.header["DOMEAZ"] = (
                            g_dev["enc"].status["dome_azimuth"],
                            "Dome azimuth",
                        )
                    hdu.header["ENCLIGHT"] = ("Off/White/Red/NIR", "Enclosure lights")
                    hdu.header["ENCRLIGT"] = ("", "Enclosure red lights state")
                    hdu.header["ENCWLIGT"] = ("", "Enclosure white lights state")
                    if g_dev["enc"] is not None:
                        try:

                            hdu.header["ENC1STAT"] = g_dev["enc"].status[
                                "shutter_status"
                            ]  # "Open/Closed" enclosure 1 status
                        except:
                            pass

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
                        avg_mnt["azimuth"],
                        "[deg] Azimuth axis positions",
                    )
                    hdu.header["ALTITUDE"] = (
                        avg_mnt["altitude"],
                        "[deg] Altitude axis position",
                    )
                    hdu.header["ZENITH"] = (avg_mnt["zenith_distance"], "[deg] Zenith")
                    hdu.header["AIRMASS"] = (
                        avg_mnt["airmass"],
                        "Effective mean airmass",
                    )
                    g_dev["airmass"] = float(avg_mnt["airmass"])
                    hdu.header["REFRACT"] = (
                        round(g_dev["mnt"].refraction_rev, 3),
                        "asec",
                    )
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
                        #plog("have to have no rotator header itesm when no rotator")
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

                    try:
                        hdu.header["PIXSCALE"] = (
                            self.config["camera"][self.name]["settings"]["pix_scale"],
                            "[arcsec/pixel] Nominal pixel scale on sky",
                        )
                        pixscale = float(hdu.header["PIXSCALE"])
                    except:
                        # There really needs to be a pixelscale in the header and the variable, even if it is wrong!
                        plog ("pixel scale not set in the site-config for this binning")
                        #
                        hdu.header["PIXSCALE"] = (
                            0.6
                            ,
                            "[arcsec/pixel] Nominal pixel scale on sky",
                        )
                        pixscale = float(0.6)
                        
                    hdu.header["REQNUM"] = ("00000001", "Request number")
                    hdu.header["ISMASTER"] = (False, "Is master image")
                    current_camera_name = self.alias

                    next_seq = next_sequence(current_camera_name)
                    hdu.header["FRAMENUM"] = (int(next_seq), "Running frame number")
                    hdu.header["SMARTSTK"] = smartstackid # ID code for an individual smart stack group                                        
                    hdu.header["SSTKNUM"] = sskcounter
                    hdu.header['SSTKLEN'] = Nsmartstack
                    

                    hdu.header["LONGSTK"] = longstackid # Is this a member of a longer stack - to be replaced by 
                                                        #   longstack code soon

                    if pedastal is not None:
                        hdu.header["PEDESTAL"] = (
                            -pedastal,
                            "adu, add this for zero based image.",
                        )
                        hdu.header["PATCH"] = (
                            bi_mean - pedastal
                        )  # A crude value for the central exposure - pedastal
                    else:
                        hdu.header["PEDESTAL"] = (0.0, "Dummy value for a raw image")
                        hdu.header[
                            "PATCH"
                        ] = bi_mean  # A crude value for the central exposure
                    hdu.header["ERRORVAL"] = 0
                    hdu.header["IMGAREA"] = opt["area"]
                    hdu.header[
                        "XORGSUBF"
                    ] = (
                        self.camera_start_x
                    )  # This makes little sense to fix...  NB ALL NEEDS TO COME FROM CONFIG!!
                    hdu.header["YORGSUBF"] = self.camera_start_y
                    try:
                        hdu.header["USERNAME"] = self.user_name
                        hdu.header["USERID"] = (
                            str(self.user_id).replace("-", "").replace("|", "")
                        )
                    except:

                        hdu.header["USERNAME"] = self.last_user_name
                        hdu.header["USERID"] = (
                            str(self.last_user_id).replace("-", "").replace("|", "")
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
                            f_ext += frame_type[0] + "_" + str(tempBinningCodeX)
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
                                + str(tempBinningCodeX)
                                + "_"
                                + str(self.current_filter)
                            )
                    cal_name = (
                        self.config["site"]
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
                        self.config["site"]
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
                    red_name01 = (
                        self.config["site"]
                        + "-"
                        + current_camera_name
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "01.fits"
                    )
                    red_name01_lcl = (
                        red_name01[:-9]
                        + pier_string
                        + self.current_filter
                        + "-"
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
                        self.config["site"]
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
                        self.config["site"]
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
                        self.config["site"]
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


                    text = open(
                        im_path + text_name, "w"
                    )  # This is needed by AWS to set up database.
                    text.write(str(hdu.header))   #This causes the Warning output. 
                    text.close()

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

                    # This command uploads the text file information at high priority to AWS. 
                    # No point sending if part of a smartstack



                    # If the file isn't a calibration frame, then undertake a flash reduction quickly
                    # To make a palatable jpg AS SOON AS POSSIBLE to send to AWS
                    if not frame_type.lower() in (
                        "bias",
                        "dark",
                        "flat",
                        "screenflat",
                        "skyflat",
                    ):  # Don't process jpgs or small fits for biases and darks

                        # Make a copy of hdu to use as jpg and small fits as well as a local raw used file for 
                        # planewave solves
                        hdusmalldata = np.array(hdu.data.astype("float32"))
                            
                        # Quick flash bias and dark frame                           
                        
                        flashbinning=1
                        
                        try:
                            hdusmalldata = hdusmalldata - self.biasFiles[str(flashbinning)]
                            hdusmalldata = hdusmalldata - (self.darkFiles[str(flashbinning)] * exposure_time)
                            
                        except Exception as e:
                            plog("debias/darking light frame failed: ", e)
                            
                        # Quick flat flat frame
                        try:
                            tempFlatFrame = np.load(self.flatFiles[str(self.current_filter + "_bin" + str(flashbinning))])

                            hdusmalldata = np.divide(hdusmalldata, tempFlatFrame)
                            del tempFlatFrame
                        except Exception as e:
                            plog("flatting light frame failed", e)
                            #plog (traceback.format_exc())
                            #breakpoint()

                        # Crop unnecessary rough edges off preview images that unnecessarily skew the scaling
                        # This is particularly necessary for SRO, but I've seen many cameras where cropping
                        # Needs to happen.
                        #  NB NB NB For the qhy chips there is a substantial L shaped overscan
                        #      region that needs to be trimmed.  I will change the MRC config
                        #      to do this.  The current bias correction is a bit too simple
                        #      but for now, this is Ok.  I will leave the trim at 1 pixel for the sides oposite
                        #      the "L". This does not show well on OSC images.  --- WER 20220225

                        
                        #First trim overscan region:
                        yw = self.config["camera"][self.name]["settings"]["y_width"]
                        xs = self.config["camera"][self.name]["settings"]["x_start"]

                        hdusmalldata = hdusmalldata[xs:, :yw]   
                        if (
                            self.config["camera"][self.name]["settings"]["crop_preview"]
                            == True
                        ):
                            yb = self.config["camera"][self.name]["settings"][
                                "crop_preview_ybottom"
                            ]
                            yt = self.config["camera"][self.name]["settings"][
                                "crop_preview_ytop"
                            ]
                            xl = self.config["camera"][self.name]["settings"][
                                "crop_preview_xleft"
                            ]
                            xr = self.config["camera"][self.name]["settings"][
                                "crop_preview_xright"
                            ]
                            hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]
                            

                        # Every Image gets SEP'd and gets it's catalogue sent up pronto ahead of the big fits
                        # Focus images use it for focus, Normal images also report their focus.
                        hdufocusdata = np.array(hdusmalldata)
                        
                        
                        # IMMEDIATELY SEND TO SEP QUEUE
                        self.sep_processing=True
                        self.to_sep((hdufocusdata, pixscale, float(hdu.header["RDNOISE"]), avg_foc[1], focus_image))
                        #self.sep_processing=True
                        
                        
                        
                        
                        # If this a bayer image, then we need to make an appropriate image that is monochrome
                        # That gives the best chance of finding a focus AND for pointing while maintaining resolution.
                        # This is best done by taking the two "real" g pixels and interpolating in-between 
                        binfocus=1
                        if self.config["camera"][self.name]["settings"]["is_osc"]:
                            #plog ("interpolating bayer grid for focusing purposes.")
                            if self.config["camera"][self.name]["settings"]["osc_bayer"] == 'RGGB':                              
                                # Only separate colours if needed for colour jpeg
                                if smartstackid == 'no':
                                    # Checkerboard collapse for other colours for temporary jpeg                                
                                    # Create indexes for B, G, G, R images                                
                                    xshape=hdufocusdata.shape[0]
                                    yshape=hdufocusdata.shape[1]
    
                                    # B pixels
                                    #list_0_1 = np.array([ [0,0], [0,1] ])
                                    list_0_1 = np.asarray([ [0,0], [0,1] ])
                                    checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                    #checkerboard=np.array(checkerboard)
                                    hdublue=(block_reduce(hdufocusdata * checkerboard ,2))
                                    
                                    # R Pixels
                                    list_0_1 = np.asarray([ [1,0], [0,0] ])
                                    checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                    #checkerboard=np.array(checkerboard)
                                    hdured=(block_reduce(hdufocusdata * checkerboard ,2))
                                    
                                    # G top right Pixels
                                    list_0_1 = np.asarray([ [0,1], [0,0] ])
                                    checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                    #checkerboard=np.array(checkerboard)
                                    #GTRonly=(block_reduce(hdufocusdata * checkerboard ,2))
                                    hdugreen=(block_reduce(hdufocusdata * checkerboard ,2))
                                    
                                    # G bottom left Pixels
                                    list_0_1 = np.asarray([ [0,0], [1,0] ])
                                    checkerboard=np.tile(list_0_1, (xshape//2, yshape//2))
                                    checkerboard=np.array(checkerboard)
                                    GBLonly=(block_reduce(hdufocusdata * checkerboard ,2))                                
                                    
                                    # Sum two Gs together and half them to be vaguely on the same scale
                                    #hdugreen = np.array((GTRonly + GBLonly) / 2)
                                    #del GTRonly
                                    #del GBLonly

                                    del checkerboard
                                    
                                
                            else:
                                plog ("this bayer grid not implemented yet")
                        
                        
                        # This is holding the flash reduced fits file waiting to be saved
                        # AFTER the jpeg has been sent up to AWS.
                        hdureduceddata = np.array(hdusmalldata)                      

                        # Code to stretch the image to fit into the 256 levels of grey for a jpeg
                        # But only if it isn't a smartstack, if so wait for the reduce queue
                        if smartstackid == 'no':
                            
                            if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
                                xshape=hdugreen.shape[0]
                                yshape=hdugreen.shape[1]
                                
                                #histogram matching
                                
                                #plog (np.median(hdublue))
                                #plog (np.median(hdugreen))
                                #plog (np.median(hdured))

                                #breakpoint()
                                
                                # The integer mode of an image is typically the sky value, so squish anything below that
                                bluemode=stats.mode((hdublue.astype('int16').flatten()), keepdims=True)[0] - 25
                                redmode=stats.mode((hdured.astype('int16').flatten()), keepdims=True)[0] - 25
                                greenmode=stats.mode((hdugreen.astype('int16').flatten()), keepdims=True)[0] - 25                          
                                hdublue[hdublue < bluemode] = bluemode
                                hdugreen[hdugreen < greenmode] = greenmode
                                hdured[hdured < redmode] =redmode
                                
                                
                                # Then bring the background level up a little from there
                                # blueperc=np.nanpercentile(hdublue,0.75)
                                # greenperc=np.nanpercentile(hdugreen,0.75)
                                # redperc=np.nanpercentile(hdured,0.75)
                                # hdublue[hdublue < blueperc] = blueperc
                                # hdugreen[hdugreen < greenperc] = greenperc
                                # hdured[hdured < redperc] = redperc
                                
                                
                                
                                
                                #hdublue = hdublue * (np.median(hdugreen) / np.median(hdublue))
                                #hdured = hdured * (np.median(hdugreen) / np.median(hdured))
 
                                
                                blue_stretched_data_float = Stretch().stretch(hdublue)*256
                                ceil = np.percentile(blue_stretched_data_float,100) # 5% of pixels will be white
                                floor = np.percentile(blue_stretched_data_float,self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut']) # 5% of pixels will be black
                                #a = 255/(ceil-floor)
                                #b = floor*255/(floor-ceil)
                                blue_stretched_data_float[blue_stretched_data_float<floor]=floor
                                blue_stretched_data_float=blue_stretched_data_float-floor
                                blue_stretched_data_float=blue_stretched_data_float * (255/np.max(blue_stretched_data_float))
                                
                                #blue_stretched_data_float = np.maximum(0,np.minimum(255,blue_stretched_data_float*a+b)).astype(np.uint8)
                                #blue_stretched_data_float[blue_stretched_data_float < floor] = floor
                                del hdublue
                                
                                
                                green_stretched_data_float = Stretch().stretch(hdugreen)*256
                                ceil = np.percentile(green_stretched_data_float,100) # 5% of pixels will be white
                                floor = np.percentile(green_stretched_data_float,self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut']) # 5% of pixels will be black
                                #a = 255/(ceil-floor)
                                green_stretched_data_float[green_stretched_data_float<floor]=floor
                                green_stretched_data_float=green_stretched_data_float-floor
                                green_stretched_data_float=green_stretched_data_float * (255/np.max(green_stretched_data_float))
                                
                                
                                #b = floor*255/(floor-ceil)
                                
                                
                                #green_stretched_data_float[green_stretched_data_float < floor] = floor
                                #green_stretched_data_float = np.maximum(0,np.minimum(255,green_stretched_data_float*a+b)).astype(np.uint8)
                                del hdugreen
                                
                                red_stretched_data_float = Stretch().stretch(hdured)*256
                                ceil = np.percentile(red_stretched_data_float,100) # 5% of pixels will be white
                                floor = np.percentile(red_stretched_data_float,self.config["camera"][g_dev['cam'].name]["settings"]['osc_background_cut']) # 5% of pixels will be black
                                #a = 255/(ceil-floor)
                                #b = floor*255/(floor-ceil)
                                #breakpoint()
                                
                                red_stretched_data_float[red_stretched_data_float<floor]=floor
                                red_stretched_data_float=red_stretched_data_float-floor
                                red_stretched_data_float=red_stretched_data_float * (255/np.max(red_stretched_data_float))
                                
                                
                                #red_stretched_data_float[red_stretched_data_float < floor] = floor
                                #red_stretched_data_float = np.maximum(0,np.minimum(255,red_stretched_data_float*a+b)).astype(np.uint8)
                                del hdured 
                                
                                
                                
                                
                                
                                
                                rgbArray=np.zeros((xshape,yshape,3), 'uint8')
                                rgbArray[..., 0] = red_stretched_data_float#*256
                                rgbArray[..., 1] = green_stretched_data_float#*256
                                rgbArray[..., 2] = blue_stretched_data_float#*256

                                del red_stretched_data_float
                                del blue_stretched_data_float
                                del green_stretched_data_float
                                colour_img = Image.fromarray(rgbArray, mode="RGB")
                                
                                
                                # adjust brightness
                                brightness=ImageEnhance.Brightness(colour_img)
                                brightness_image=brightness.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_brightness_enhance'])
                                del colour_img
                                del brightness
                                
                                # adjust contrast
                                contrast=ImageEnhance.Contrast(brightness_image)
                                contrast_image=contrast.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_contrast_enhance'])
                                del brightness_image
                                del contrast
                                
                                # adjust colour
                                colouradj=ImageEnhance.Color(contrast_image)
                                colour_image=colouradj.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_colour_enhance'])
                                del contrast_image
                                del colouradj
                                
                                # adjust saturation
                                satur=ImageEnhance.Color(colour_image)
                                satur_image=satur.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_saturation_enhance'])
                                del colour_image
                                del satur
                                
                                # adjust sharpness
                                sharpness=ImageEnhance.Sharpness(satur_image)
                                final_image=sharpness.enhance(self.config["camera"][g_dev['cam'].name]["settings"]['osc_sharpness_enhance'])
                                del satur_image
                                del sharpness
                                
                                
                                # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                                if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                                    final_image=final_image.transpose(Image.TRANSPOSE)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                                    final_image=final_image.transpose(Image.FLIP_LEFT_RIGHT)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                                    final_image=final_image.transpose(Image.FLIP_TOP_BOTTOM)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_180)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_90)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_270)
                                    
                                # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                                # to maintain the orientation. whether it is 1 or 0 that is flipped
                                # is sorta arbitrary... you'd use the site-config settings above to 
                                # set it appropriately and leave this alone.
                                if g_dev['mnt'].pier_side == 1:
                                    final_image=final_image.transpose(Image.ROTATE_180)
                                
                                #breakpoint()
                                # Save BIG version of JPEG.
                                final_image.save(
                                    paths["im_path"] + paths['jpeg_name10'].replace('EX10','EX20')
                                )
                                
                                ## Resizing the array to an appropriate shape for the small jpg
                                iy, ix = final_image.size
                                if iy == ix:
                                    #final_image.resize((1280, 1280))
                                    final_image=final_image.resize((900, 900))
                                else:
                                    #final_image.resize((int(1536 * iy / ix), 1536))
                                    if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                        final_image=final_image.resize((int(900 * iy / ix), 900))
                                    else:
                                        final_image=final_image.resize((900, int(900 * iy / ix)))
                                
                                    
                                final_image.save(
                                    paths["im_path"] + paths["jpeg_name10"]
                                )
                                del final_image
                                
                            else:
                                # Making cosmetic adjustments to the image array ready for jpg stretching
                                #breakpoint()
                                
                                #hdusmalldata = np.asarray(hdusmalldata)
                                
                                #breakpoint()
                                # hdusmalldata[
                                #     hdusmalldata
                                #     > image_saturation_level
                                # ] = image_saturation_level
                                # #hdusmalldata[hdusmalldata < -100] = -100
                                hdusmalldata = hdusmalldata - np.min(hdusmalldata)


                                stretched_data_float = Stretch().stretch(hdusmalldata+1000)
                                stretched_256 = 255 * stretched_data_float
                                hot = np.where(stretched_256 > 255)
                                cold = np.where(stretched_256 < 0)
                                stretched_256[hot] = 255
                                stretched_256[cold] = 0
                                stretched_data_uint8 = stretched_256.astype("uint8")
                                hot = np.where(stretched_data_uint8 > 255)
                                cold = np.where(stretched_data_uint8 < 0)
                                stretched_data_uint8[hot] = 255
                                stretched_data_uint8[cold] = 0
                                
                                iy, ix = stretched_data_uint8.shape
                                #stretched_data_uint8 = Image.fromarray(stretched_data_uint8)
                                final_image = Image.fromarray(stretched_data_uint8)
                                # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                                if self.config["camera"][g_dev['cam'].name]["settings"]["transpose_jpeg"]:
                                    final_image=final_image.transpose(Image.TRANSPOSE)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['flipx_jpeg']:
                                    final_image=final_image.transpose(Image.FLIP_LEFT_RIGHT)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['flipy_jpeg']:
                                    final_image=final_image.transpose(Image.FLIP_TOP_BOTTOM)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate180_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_180)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate90_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_90)
                                if self.config["camera"][g_dev['cam'].name]["settings"]['rotate270_jpeg']:
                                    final_image=final_image.transpose(Image.ROTATE_270)
                                    
                                # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
                                # to maintain the orientation. whether it is 1 or 0 that is flipped
                                # is sorta arbitrary... you'd use the site-config settings above to 
                                # set it appropriately and leave this alone.
                                if g_dev['mnt'].pier_side == 1:
                                    final_image=final_image.transpose(Image.ROTATE_180)
                                
                                
                                # Save BIG version of JPEG.
                                final_image.save(
                                    paths["im_path"] + paths['jpeg_name10'].replace('EX10','EX20')
                                )
                                
                                # Resizing the array to an appropriate shape for the jpg and the small fits
                                
                                
                                if iy == ix:
                                    # hdusmalldata = resize(
                                    #     hdusmalldata, (1280, 1280), preserve_range=True
                                    # )
                                    final_image = final_image.resize(
                                         (900, 900)
                                    )
                                else:
                                    # stretched_data_uint8 = resize(
                                    #     stretched_data_uint8,
                                    #     (int(1536 * iy / ix), 1536),
                                    #     preserve_range=True,
                                    # )
                                    # stretched_data_uint8 = resize(
                                    #     stretched_data_uint8,
                                    #     (int(900 * iy / ix), 900),
                                    #     preserve_range=True,
                                    # ) 
                                    if self.config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
                                        final_image = final_image.resize(
                                            
                                            (int(900 * iy / ix), 900)
                                            
                                        ) 
                                    else:
                                        final_image = final_image.resize(
                                            
                                            (900, int(900 * iy / ix))
                                            
                                        ) 
                                #stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
                                final_image.save(
                                    paths["im_path"] + paths["jpeg_name10"]
                                )
                                del final_image
                            
                        del hdusmalldata
                            

                        # Try saving the jpeg to disk and quickly send up to AWS to present for the user
                        # GUI
                        if smartstackid == 'no':
                            try:
                                
                                if not no_AWS:
                                    g_dev["cam"].enqueue_for_fastAWS(
                                        100, paths["im_path"], paths["jpeg_name10"]
                                    )
                                    g_dev["cam"].enqueue_for_fastAWS(
                                        1000, paths["im_path"], paths["jpeg_name10"].replace('EX10','EX20')
                                    )
                                    g_dev["obs"].send_to_user(
                                        "A preview image of the single image has been sent to the GUI.",
                                        p_level="INFO",
                                    )
                            except:
                                plog(
                                    "there was an issue saving the preview jpg. Pushing on though"
                                )
                       
                        
                        
                        

                        

                        # AT THIS STAGE WAIT FOR SEP TO COMPLETE      
                        #print (self.sep_queue)
                        x = 0
                        while x == 0:
                            if g_dev['cam'].sep_processing:
                                time.sleep(1)
                                print ("waiting for SEP to complete")
                                #breakpoint()
                            else:
                                x = 1
                            
                        hdu.header["SEPSKY"] = g_dev['cam'].sepsky
                        
                        
                        

                        #if 'rfr' in locals():

                        hdu.header["FWHM"] = ( str(self.rfp), 'FWHM in pixels')
                        hdu.header["FWHMpix"] = ( str(self.rfp), 'FWHM in pixels')
                        hdu.header["FWHMasec"] = ( str(self.rfr), 'FWHM in arcseconds')
                        hdu.header["FWHMstd"] = ( str(self.rfs), 'FWHM standard deviation in arcseconds')

                        #if focus_image == False:
                        text = open(
                            im_path + text_name, "w"
                        )  # This is needed by AWS to set up database.
                        text.write(str(hdu.header))
                        text.close()
                        self.enqueue_for_fastAWS(10, im_path, text_name)
                        
                        #if focus_image == False:
                        try:
                            self.enqueue_for_fastAWS(200, im_path, text_name.replace('.txt', '.sep'))
                            #plog("Sent SEP up")
                        except:
                            plog("Failed to send SEP up for some reason")


                         # Set up RA and DEC headers for BANZAI
                         # needs to be done AFTER text file is sent up.
                         # Text file RA and Dec and BANZAI RA and Dec are gormatted different

                        tempRAdeg = float(g_dev["mnt"].current_icrs_ra) * 15
                        tempDECdeg = g_dev["mnt"].current_icrs_dec
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
                            g_dev["mnt"].current_icrs_ra,
                            "[hrs] Telescope right ascension",
                        )
                        hdu.header["RA-deg"] = tempRAdeg
                        hdu.header["DEC-deg"] = tempDECdeg

                        hdu.header["TARG-CHK"] = (
                            (g_dev["mnt"].current_icrs_ra * 15)
                            + g_dev["mnt"].current_icrs_dec,
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

                        hdu.header["CRVAL1"] = tempRAdeg
                        hdu.header["CRVAL2"] = tempDECdeg
                        hdu.header["CRPIX1"] = float(hdu.header["NAXIS1"])/2
                        hdu.header["CRPIX2"] = float(hdu.header["NAXIS2"])/2


                        source_delete=['thresh','npix','tnpix','xmin','xmax','ymin','ymax','x2','y2','xy','errx2',\
                                       'erry2','errxy','a','b','theta','cxx','cyy','cxy','cflux','cpeak','xcpeak','ycpeak']
                        #for sourcedel in source_delete:
                        #    breakpoint()
                        self.sources.remove_columns(source_delete)

                        self.sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)



                        # Make  sure the alt paths exist
                        if self.config["save_to_alt_path"] == "yes":
                            os.makedirs(
                                self.alt_path + g_dev["day"], exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/raw/", exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/reduced/", exist_ok=True
                            )
                            os.makedirs(
                                self.alt_path + g_dev["day"] + "/calib/", exist_ok=True)


                        
                        
                        
                        # If this is a focus image, save focus image, estimate pointing, and estimate pointing
                        # We want to estimate pointing in the main thread so it has enough time to correct the
                        # pointing during focus, not when it quickly moves back to the target. Takes longer
                        # during focussing, but reduces the need for pointing nudges and bounces on
                        # target images.
                        #
                        # It will also do a pointing check at the end of a smartstack
                        #
                        # It will also do a pointing check periodically during normal use on a timer.
                        #
                        # This is all done outside the reduce queue to guarantee the pointing check is done
                        # prior to the next exposure                        

                        if focus_image == True or solve_it == True or ((Nsmartstack == sskcounter+1) and Nsmartstack > 1)\
                                                   or g_dev['obs'].images_since_last_solve > g_dev['obs'].config["solve_nth_image"] or (datetime.datetime.now() - g_dev['obs'].last_solve_time)  > datetime.timedelta(minutes=g_dev['obs'].config["solve_timer"]):
                                                       
                            cal_name = (
                                cal_name[:-9] + "F012" + cal_name[-7:]
                            )                            
                            
                            # Check this is not an image in a smartstack set.
                            # No shifts in pointing are wanted in a smartstack set!
                            image_during_smartstack=False
                            if Nsmartstack > 1 and not (Nsmartstack == sskcounter+1):
                                image_during_smartstack=True
                            
                            
                            if len(self.sources) >= 5 and len(self.sources) < 1000 and not image_during_smartstack and not self.pointing_correction_requested_by_platesolve_thread and g_dev['obs'].platesolve_queue.empty():
                                
                                
                                # NEED TO CHECK HERE THAT THERE ISN"T ALREADY A PLATE SOLVE IN THE THREAD!
                                self.to_platesolve((g_dev['cam'].hdufocusdatahold, hdu.header, cal_path, cal_name, frame_type, time.time()))
                                
                            else:
                                plog ("Platesolve wasn't attempted due to lack of sources (or sometimes too many!) or it was during a smartstack")
                                
                                #Still save the file to disk if platesolve not attempted
                                if self.config['keep_focus_images_on_disk']:
                                    hdufocus=fits.PrimaryHDU()
                                    hdufocus.data=hdufocusdata                            
                                    hdufocus.header=hdu.header
                                    hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
                                    hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
                                    hdufocus.writeto(cal_path + cal_name, overwrite=True, output_verify='silentfix')
                                    pixscale=hdufocus.header['PIXSCALE']
                                    if self.config["save_to_alt_path"] == "yes":
                                        self.to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocus.data, hdufocus.header, \
                                                                        frame_type))
                                    
                                    try:
                                        g_dev['cam'].hdufocusdatahold.close()
                                    except:
                                        pass
                                    del g_dev['cam'].hdufocusdatahold
                                    del hdufocus
                                    #os.remove(cal_path + cal_name)                             
                                
                                del g_dev['cam'].hdufocusdatahold
                              
                            
                            if focus_image == True :
                                focus_image = False
                                plog ("Time Taken From Exposure start to finish : "  + str(time.time()\
                                       - self.tempStartupExposureTime))
                                return self.expresult

                        #breakpointbreakpoint()

                        

                    # Now that the jpeg has been sent up pronto,
                    # We turn back to getting the bigger raw, reduced and fz files dealt with
                    
                    self.to_slow_process(5,('fz_and_send', raw_path + raw_name00 + ".fz", hdu.data, hdu.header, frame_type))                    

        
                    # Similarly to the above. This saves the RAW file to disk
                    # it works 99.9999% of the time.
                   
                    if self.config['save_raw_to_disk']:
                       self.to_slow_process(1000,('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type))
                    
                    # Similarly to the above. This saves the REDUCED file to disk
                    # it works 99.9999% of the time.
                    if "hdureduceddata" in locals():
                        # If a CMOS camera, bin to requested binning
                        if self.is_cmos and self.bin != 1:
                            #plog ("Binning 1x1 to " + str(self.bin))
                            hdureduceddata=(block_reduce(hdureduceddata,self.bin)) 
                        
                        if smartstackid == 'no':
                            if self.config['keep_reduced_on_disk']:
                                plog ("saving reduced file anyway!")
                                self.to_slow_process(1000,('reduced', red_path + red_name01, hdureduceddata, hdu.header, \
                                                       frame_type))
                        else:                            
                            saver = 0
                            saverretries = 0
                            while saver == 0 and saverretries < 10:
                                try:
                                    hdureduced=fits.PrimaryHDU()
                                    hdureduced.data=hdureduceddata                            
                                    hdureduced.header=hdu.header
                                    hdureduced.header["NAXIS1"] = hdureduceddata.shape[0]
                                    hdureduced.header["NAXIS2"] = hdureduceddata.shape[1]
                                    #hdureduced.data=hdureduced.data.astype("float32")
                                    hdureduced.data=hdureduced.data.astype("float32")
                                    hdureduced.writeto(
                                        red_path + red_name01, overwrite=True, output_verify='silentfix'
                                    )  # Save flash reduced file locally
                                    saver = 1
                                except Exception as e:
                                    plog("Failed to write raw file: ", e)
                                    if "requested" in e and "written" in e:
    
                                        plog(check_download_cache())
                                    plog(traceback.format_exc())
                                    time.sleep(10)
                                    saverretries = saverretries + 1
                    
                    
                    
                    # For sites that have "save_to_alt_path" enabled, this routine
                    # Saves the raw and reduced fits files out to the provided directories
                    
                    if self.config["save_to_alt_path"] == "yes":
                        self.to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                       frame_type))
                        if "hdureduced" in locals():
                            self.to_slow_process(1000,('reduced_alt_path', self.alt_path + g_dev["day"] + "/reduced/" + red_name01, hdureduceddata, hdu.header, \
                                                               frame_type))
                            
                        
                      
                        # try:
                        #     hdu.writeto(
                        #         self.alt_path + g_dev["day"] + "/raw/" + raw_name00,
                        #         overwrite=True, output_verify='silentfix'
                        #     )  # Save full raw file locally
                        #     if "hdureduced" in locals():
                        #         hdureduced.writeto(
                        #             self.alt_path
                        #             + g_dev["day"]
                        #             + "/reduced/"
                        #             + red_name01,
                        #             overwrite=True, output_verify='silentfix'
                        #         )  # Save full raw file locally
                        #     saver = 1
                        # except Exception as e:
                        #     plog("Failed to write raw file: ", e)
                        #     if "requested" in e and "written" in e:

                        #         plog(check_download_cache())
                        #     plog(traceback.format_exc())
                        #     time.sleep(10)
                        #     saverretries = saverretries + 1

                    # remove file from memory
                    
                    try: 
                        hdu.close()
                    except:
                        pass
                    del hdu  # remove file from memory now that we are doing with it
                    
                    if "hdureduced" in locals():                        
                        try: 
                            hdureduced.close()
                        except:
                            pass
                        del hdureduced  # remove file from memory now that we are doing with it


                    # Good spot to check if we need to nudge the telescope
                    check_platesolve_and_nudge()                 
                    
                

                    # The paths to these saved files and the pixelscale are sent to the reduce queue
                    # Currently the reduce queue platesolves the images and monitors the focus.
                    # Soon it will also smartstack
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
                    ]) and smartstackid != 'no' :
                        self.to_reduce((paths, pixscale, smartstackid, sskcounter, Nsmartstack, self.sources))
                    else:
                        if not self.config['keep_reduced_on_disk']:
                            try:                                
                                os.remove(red_path + red_name01)
                                plog ("removed reduced file")
                            except:
                                plog ("couldn't remove reduced file for some reason")

                    if not g_dev["cam"].exposure_busy:
                        self.expresult = {"stopped": True}
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
                        #plog("we ain't got no rotator matey")
                    if not focus_image:
                        self.expresult["FWHM"] = None
                    self.expresult["half_FD"] = None
                    if self.overscan is not None:
                        self.expresult["patch"] = bi_mean - self.overscan
                    else:
                        self.expresult["patch"] = bi_mean
                    self.expresult["calc_sky"] = 0  # avg_ocn[7]
                    self.expresult["temperature"] = 0  # avg_foc[2]
                    self.expresult["gain"] = 0
                    self.expresult["filter"] = self.current_filter
                    self.expresult["error"] == False
                    self.exposure_busy = False

                    plog ("Time Taken From Exposure start to finish : "  +str(time.time() - self.tempStartupExposureTime))

                    return self.expresult
                except Exception as e:
                    plog("Header assembly block failed: ", e)
                    plog(traceback.format_exc())
                    self.t7 = time.time()
                    self.expresult = {"error": True}
                self.exposure_busy = False
                plog ("Time Taken From Exposure start to finish : "  +str(time.time() - self.tempStartupExposureTime))
                return self.expresult
            else:
                #self.t7 = time.time()
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
                    plog ("Time Taken From Exposure start to finish : "  +str(time.time() - self.tempStartupExposureTime))
                    return self.expresult
            time.sleep(0.1)

    def enqueue_for_AWS(self, priority, im_path, name):
        image = (im_path, name)
        g_dev["obs"].aws_queue.put((priority, image), block=False)

    def enqueue_for_fastAWS(self, priority, im_path, name):
        image = (im_path, name)
        g_dev["obs"].fast_queue.put((priority, image), block=False)

    def to_reduce(self, to_red):
        g_dev["obs"].reduce_queue.put(to_red, block=False)
        
    def to_slow_process(self, priority, to_slow):
        g_dev["obs"].slow_camera_queue.put((priority, to_slow), block=False)
    
    def to_platesolve(self, to_platesolve):
        g_dev["obs"].platesolve_queue.put( to_platesolve, block=False)
    
    def to_sep(self, to_sep):
        g_dev["obs"].sep_queue.put( to_sep, block=False)
        
def wait_for_slew():    
    
    try:
        if not g_dev['mnt'].mount.AtPark:
            movement_reporting_timer=time.time()
            while g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                #if g_dev['mnt'].mount.Slewing: plog( 'm>')
                #if g_dev['enc'].status['dome_slewing']: st += 'd>'
                if time.time() - movement_reporting_timer > 2.0:
                    plog( 'm>')
                    movement_reporting_timer=time.time()
                #time.sleep(0.1)
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
            pass #breakpoint()
    return 

def check_platesolve_and_nudge():
    
    # This block repeats itself in various locations to try and nudge the scope
    # If the platesolve requests such a thing.
    if g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
        g_dev['obs'].pointing_correction_requested_by_platesolve_thread = False
        if g_dev['obs'].pointing_correction_request_time > g_dev['obs'].time_since_last_slew: # Check it hasn't slewed since request                        
            plog ("I am nudging the telescope slightly at the request of platesolve!")                            
            g_dev['mnt'].mount.SlewToCoordinatesAsync(g_dev['obs'].pointing_correction_request_ra, g_dev['obs'].pointing_correction_request_dec)
            g_dev['obs'].time_since_last_slew = time.time()
            wait_for_slew()
