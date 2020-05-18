import win32com.client
import pythoncom
import redis
import time
import datetime
import os
import math
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.utils.data import get_pkg_data_filename
import sep
import glob
import shelve

from os.path import join, dirname, abspath

from skimage import data, io, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure
from skimage.io import imsave
import matplotlib.pyplot as plt

from PIL import Image
from global_yard import g_dev
from processing.calibration import calibrate
from devices.sequencer import Sequencer

"""
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

Note Camera at saf just set to hardware binning.


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

def reset_sequence(pCamera):
    camShelf = shelve.open(g_dev['cam'].site_path + 'ptr_night_shelf/' + str(pCamera))
    #seq = camShelf['Sequence']      # a 9 character string
    seqInt = int(-1)
    seqInt  += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    print('Making new seq: ' , pCamera, seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    return seq

# Default filter needs to be pulled from site camera or filter config
def create_simple_sequence(exp_time=0, img_type=0, speed=0, suffix='', repeat=1, \
                    readout_mode="RAW Mono", filter_name='W', enabled=1, \
                    binning=1, binmode=0, column=1):
    exp_time = round(abs(float(exp_time)), 3)
    if img_type > 3:
        img_type = 0
    repeat = abs(int(repeat))
    if repeat < 1:
        repeat = 1
    binning = abs(int(binning))
    if binning > 4:
        binning = 4
    if filter_name == "":
        filter_name = 'W'
    proto_file = open('D:/archive/archive/kb01/seq/ptr_saf.pro')
    proto = proto_file.readlines()
    proto_file.close()
    print(proto, '\n\n')

    if column == 1:
        proto[62] = proto[62][:9]  + str(exp_time) + proto[62][12:]
        proto[63] = proto[63][:9]  + str(img_type) + proto[63][10:]
        proto[58] = proto[58][:12] + str(suffix)   + proto[58][12:]
        proto[56] = proto[56][:10] + str(speed)    + proto[56][11:]
        proto[37] = proto[37][:11] + str(repeat)   + proto[37][12:]
        proto[33] = proto[33][:17] + readout_mode  + proto[33][20:]
        proto[15] = proto[15][:12] + filter_name   + proto[15][13:]
        proto[11] = proto[11][:12] + str(enabled)  + proto[11][13:]
        proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
    seq_file = open('D:/archive/archive/kb01/seq/ptr_saf.seq', 'w')
    for item in range(len(proto)):
        seq_file.write(proto[item])
    seq_file.close()
    print(proto)


#  TEST  create_simple_sequence(exp_time=0, img_type=0, suffix='', repeat=1, \
#                       binning=3, filter_name='air')


class Camera:

    """
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """

    ###filter, focuser, rotator must be set up prior to camera.

    def __init__(self, driver: str, name: str, config: dict):
        """
        Added monkey patches to make ASCOM/Maxim differences
        go away from the bulk of the in-line code.

        Try to be more consistent about use of filter names rather than
        numbers.

        """

        self.name = name

        g_dev['cam'] = self
        self.config = config
        win32com.client.pythoncom.CoInitialize()
        self.camera = win32com.client.Dispatch(driver)
        #self.camera = win32com.client.Dispatch('ASCOM.FLI.Kepler.Camera')
        #Need logic here if camera denies connection.
        print("Connecting to ASCOM camera:", driver)
        if driver[:5].lower() == 'ascom':
            print('ASCOM camera is initializing.')
            self.camera.Connected = True
            self.description = "ASCOM"
            self.maxim = False
            self.ascom = True
            if self.camera.CanSetCCDTemperature:
                self.camera.SetCCDTemperature = float(self.config['camera']['camera1'] \
                                                      ['settings']['temp_setpoint'])
                self.temperature_setpoint = self.camera.SetCCDTemperature
                cooler_on = self.config['camera']['camera1'] \
                                       ['settings']['cooler_on'] in ['True', 'true', 'Yes', 'yes', 'On', 'on']
            self.camera.CoolerOn = cooler_on
            self.current_filter = 2     #A WMD reference -- needs fixing.

            print('Control is ASCOM camera driver.')
        else:
            print('Maxim camera is initializing.')
            #Monkey patch in Maxim specific
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            self._setpoint = self._maxim_setpoint
            self._temperature = self._maxim_temperature
            self.description = 'MAXIM'
            self.maxim = True
            self.ascom = False
            print(self._connect(True))
            print(self._connected())
            print(self._setpoint(float(self.config['camera']['camera1'] \
                                      ['settings']['temp_setpoint'])))
            print(self._temperature)

            cooler_on = self.config['camera']['camera1'] \
                                   ['settings']['cooler_on'] in ['True', 'true', 'Yes', 'yes', 'On', 'on']
            self.camera.CoolerOn = cooler_on
            self.current_filter = 0    #W in Apache Ridge case.

            print('Control is Maxim camera interface.')
        # breakpoint()
        # # #self.camera.StartSequence('D:\\archive\\archive\\kb01\\seq\\ptr_saf.seq')
        # create_simple_sequence(exp_time=720, img_type=2,filter_name='V')
        # self.camera.StartSequence('D:/archive/archive/kb01/seq/ptr_saf_darks.seq')
        # for item in range(50):
        #     seq = self.camera.SequenceRunning
        #     print('Link:  ', self.camera.LinkEnabled,'  AutoSave:  ',  seq)
        #     if not seq:
        #         break
        #     time.sleep(30)

        # print('Exposure Finished:  ', item*0.5, ' seconds.')
        # breakpoint()
        self.exposure_busy = False
        self.cmd_in = None
        self.camera_message = '-'
        self.alias = self.config['camera']['camera1']['name']
        self.site_path = self.config['site_path']
        self.archive_path = self.site_path +'archive/'
        self.camera_path = self.archive_path  + self.alias+ "/"
        self.autosave_path = self.camera_path +'autosave/'
        self.lng_path = self.camera_path + "lng/"
        try:
            os.remove(self.camera_path + 'newest.fits')   #NB This needs to properly clean out all autosaves
        except:
            print ("File newest.fits not found, this is probably OK")
        self.is_cmos = False
        if self.config['camera']['camera1']['settings']['is_cmos']  == 'true':
            self.is_cmos = False
        self.camera_model = self.config['camera']['camera1']['desc']
        #NB We are reading from the actual camera or setting as the case may be.  For initial setup,
        #   we pull from config for some of the various settings.
        try:
            self.camera.BinX = int(self.config['camera']['camera1']['settings']['default_bin'])
            self.camera.BinY = int(self.config['camera']['camera1']['settings']['default_bin'])
            #NB we need to be sure AWS picks up this default.config.site_config['camera']['camera1']['settings']['default_bin'])
        except:
            print('Camera only accepts Bins = 1.')
            self.camera.BinX = 1
            self.camera.BinY = 1
        self.overscan_x =  int(self.config['camera']['camera1']['settings']['overscan_x'])
        self.overscan_y =  int(self.config['camera']['camera1']['settings']['overscan_y'])
        self.camera_x_size = self.camera.CameraXSize  #unbinned values.
        self.camera_y_size = self.camera.CameraYSize  #unbinned
        self.camera_max_x_bin = self.camera.MaxBinX
        self.camera_max_y_bin = self.camera.MaxBinY
        self.camera_start_x = self.camera.StartX
        self.camera_start_y = self.camera.StartY
        self.camera_num_x = self.camera.NumX    #These are affected binned values.
        self.camera_num_y = self.camera.NumY
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
        self.t_0 = time.time()
        self.hint = None
        #self.camera.SetupDialog()

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



    #The patches.   Note these are essentially a getter-setter/property constructs.
    def _maxim_connected(self):
        return self.camera.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _maxim_temperature(self):
        return self.camera.Temperature

    def _maxim_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        return self.camera.TemperatureSetpoint



    #  NB Need to add in ASCOM versions



    def get_status(self):
        #status = {"type":"camera"}
        status = {}
        if self.exposure_busy:
            status['busy_lock'] = 'true'
        else:
            status['busy_lock'] = 'false'
        if self.maxim:
            cam_stat = 'Not implemented yet' #
            #print('AutoSave:  ', self.camera.SequenceRunning)
        if self.ascom:
            cam_stat = 'Not implemented yet' #self.camera.CameraState
        status['status'] = str(cam_stat).lower()  #The state could be expanded to be more meaningful.
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
# =============================================================================
# # =============================================================================
        if opt['filter'] == 'dark' and opt['bin'] == '2,2':    # Special case, AWS broken 20200405
             g_dev['seq'].screen_flat_script(req, opt)
# # =============================================================================
# =============================================================================
        if action == "expose" and not self.exposure_busy :
            self.expose_command(req, opt, do_sep=True, quick=False)
            self.exposure_busy = False     #Hangup needs to be guarded with a timeout.
            self.active_script = None

#        elif action == "expose" and script_mode == 'make_superscreenflats':
#            self.screen_flat_script(req, opt)
#            self.exposure_busy = False
#            self.active_script = 'make_superscreenflats'
        elif action == "stop":
            self.stop_command(req, opt)
            self.exposure_busy = False
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
                       gather_status = True, do_sep=False, no_AWS=False, quick=False, halt=False):
        '''
        This is Phase 1:  Setup the camera.
        Apply settings and start an exposure.
        Quick=True is meant to be fast.  We assume the ASCOM/Maxim imageBuffer is the source of data in that mode,
        not the slower File Path.  THe mode used for focusing or other operations where we do not want to save any
        image data.
        '''
        print('Expose Entered.  req:  ', required_params, 'opt:  ', optional_params)
        opt = optional_params
        self.t_0 = time.time()
        self.hint = optional_params.get('hint', '')
        self.script = required_params.get('script', 'None')
        bin_x = optional_params.get('bin', self.config['camera']['camera1'] \
                                                      ['settings']['default_bin'])  #NB this should pick up config default.
        if bin_x == '4,4':# For now this is thei highest level of binning supported.
            bin_x = 4
        elif bin_x == '3,3':
            bin_x = 3
        elif bin_x == '2,2':
            bin_x = 2
        else:
            bin_x = 1
        bin_y = bin_x   #NB This needs fixing someday!
        #self.camera.BinX = bin_x
        #self.camera.BinY = bin_y
        #gain = float(optional_params.get('gain', self.config['camera']['camera1'] \
        #                                              ['settings']['reference_gain'][bin_x - 1]))
        readout_time = float(self.config['camera']['camera1']['settings']['readout_time'][bin_x - 1])
        exposure_time = float(required_params.get('time', 0.0))   #  0.0 may be the best default.
        self.estimated_readtime = (exposure_time + 2*readout_time)*1.25*3   #  3 is the outer retry loop maximum.
        #exposure_time = max(0.2, exposure_time)  #Saves the shutter, this needs qualify with imtype.
        imtype= required_params.get('image_type', 'Light')

        count = int(optional_params.get('count', 1))   #FOr now Repeats are external to full expose command.
        lcl_repeat = 1
        if count < 1:
            count = 1   #Hence frame does not repeat unless count > 1

        #  Here we set up the filter, and later on possibly roational composition.
        requested_filter_name = str(optional_params.get('filter', 'w'))   #Default should come from config.
        self.current_filter = requested_filter_name
        #  Patch around early filter change to test relaibility of autosave
        #g_dev['fil'].set_name_command({'filter': requested_filter_name}, {})

        #  NBNB Changing filter may cause a need to shift focus
        self.current_offset = 6300#g_dev['fil'].filter_offset  #TEMP   NBNBNB This needs fixing
        #  NB nothing being done here to get focus set properly. Where is this effected?

        sub_frame_fraction = optional_params.get('subframe', None)
        #  The following bit of code is convoluted.  Presumably when we get Autofocus working this will get cleaned up.
        if imtype.lower() in ('light', 'light frame', 'screen flat', 'sky flat', 'experimental', 'toss'):
                                 #here we might eventually turn on spectrograph lamps as needed for the imtype.
            imtypeb = True    #imtypeb will passed to open the shutter.
            frame_type = imtype.lower()
            do_sep = True
            if imtype.lower() in ('screen flat', 'sky flat', 'guick'):
                do_sep = False
        elif imtype.lower() == 'bias':
            exposure_time = 0.0
            imtypeb = False
            frame_type = 'bias'
            no_AWS = False
            do_sep = False
            # Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'dark':
            imtypeb = False
            frame_type = 'dark'
            no_AWS = False
            do_sep = False
            # Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'screen flat':
            frame_type = 'screen flat'
        elif imtype.lower() == 'sky flat':
            frame_type = 'flat'
        elif imtype.lower() == 'quick':
            quick = True
            no_AWS = False   # Send only an informational JPEG??
            do_sep = False
            imtypeb = True
            frame_type = 'light'
        else:
            imtypeb = True
            do_sep = True
        # NBNB This area still needs work to cleanly define shutter, calibration, sep and AWS actions.

        area = optional_params.get('size', 100)
        if area is None or area == 'chip':   #  Temporary patch to deal with 'chip'
            area = 100
        sub_frame_fraction = optional_params.get('subframe', None)
        # Need to put in support for chip mode once we have implmented in-line bias correct and trim.
        try:
            if type(area) == str and area[-1] == '%':
                area = int(area[0:-1])
        except:
            area = 100
        if bin_y == 0 or self.camera_max_x_bin != self.camera_max_y_bin:
            self.bin_x = min(bin_x, self.camera_max_x_bin)
            self.cameraBinY = self.bin_y
        else:
            self.bin_x = min(bin_x, self.camera_max_x_bin)
            self.cameraBinx = self.bin_x
            self.bin_y = min(bin_y, self.camera_max_y_bin)
            self.cameraBinY = self.bin_y
        self.len_x = 3100 # self.camera.CameraXSize//self.bin_x
        self.len_y = 2058 # self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
        self.len_xs = 0  # THIS IS A HACK, indicating no overscan.
        # print(self.len_x, self.len_y)

        # "area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg', 'chip' ]
        if type(area) == str and area.lower() == "1x-jpg":
            self.camera_num_x = 768                 # 768 is the size of the JPEG
            self.camera_start_x = 1659              # NB Where are these absolute numbers coming from?  This needs testing!!
            self.camera_num_y = 768
            self.camera_start_y = 1659
            self.area = 37.5
        elif type(area) == str and area.lower() == "2x-jpg":
            self.camera_num_x = 1536
            self.camera_start_x = 1280
            self.camera_num_y = 1536
            self.camera_start_y = 1280
            self.area = 75
        elif type(area) == str and area.lower() == "1/2 jpg":
            self.camera_num_x = 384
            self.camera_start_x = 832
            self.camera_num_y = 384
            self.camera_start_y = 832
            self.area = 18.75
        elif type(area) == str:     #Just default to a small area, for now 1/16th.
            self.camera_num_x = self.len_x//4
            self.camera_start_x = int(self.len_xs/2.667)
            self.camera_num_y = self.len_y//4
            self.camera_start_y = int(self.len_y/2.667)
            self.area = 100
        elif 72 < area <= 100:
            self.camera_num_x = self.len_x
            self.camera_start_x = 0
            self.camera_num_y = self.len_y
            self.camera_start_y = 0
            self.area = 100
        elif 70 <= area <= 72:
            self.camera_num_x = int(self.len_xs/1.4142)
            self.camera_start_x = int(self.len_xs/6.827)
            self.camera_num_y = int(self.len_y/1.4142)
            self.camera_start_y = int(self.len_y/6.827)
            self.area = 71
        elif area == 50:
            self.camera_num_x = self.len_xs//2
            self.camera_start_x = self.len_xs//4
            self.camera_num_y = self.len_y//2
            self.camera_start_y = self.len_y//4
            self.area = 50
        elif 33 <= area <= 35:
            self.camera_num_x = int(self.len_xs/2.829)
            self.camera_start_x = int(self.len_xs/3.093)
            self.camera_num_y = int(self.len_y/2.829)
            self.camera_start_y = int(self.len_y/3.093)
            self.area = 33
        elif area == 25:
            self.camera_num_x = self.len_xs//4
            self.camera_start_x = int(self.len_xs/2.667)
            self.camera_num_y = self.len_y//4
            self.camera_start_y = int(self.len_y/2.667)
            self.area = 25
        else:
            self.camera_num_x = self.len_x
            self.camera_start_x = 0
            self.camera_num_y = self.len_y
            self.camera_start_y = 0
            self.area = 100
            print("Defult area used. 100%")

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
        result = (-1, -1)  #  This is a default return just in case
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
                while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                      g_dev['mnt'].mount.Slewing or g_dev['enc'].enclosure.Slewing:
                    print(">>")
                    time.sleep(0.2)
                    if seq > 0:
                        g_dev['obs'].update_status()
            except:
                print("Motion check faulted.")
            if seq > 0:
                g_dev['obs'].update_status()   # NB Make sure this routine has a fault guard.
            self.retry_camera = 3
            self.retry_camera_start_time = time.time()

            while self.retry_camera > 0:
                #NB Here we enter Phase 2
                try:
                    self.t1 = time.time()
                    self.exposure_busy = True
                    print('First Entry to inner Camera loop:  ')  #  Do not reference camera, self.camera.StartX, self.camera.StartY, self.camera.NumX, self.camera.NumY, exposure_time)
                    #First lets verify we are connected or try to reconnect.
                    try:
                        if not self._connected():
                            breakpoint()
                            self._connect(True)
                            print('1st Reset LinkEnabled/Connected right before exposure')
                    except:
                        print("2nd Retry to set up camera connected.")
                        time.sleep(2)
                        if not self._connected:
                            breakpoint()
                            self._connect(True)
                            print('2nd Reset LinkEnabled/Connected right before exposure')
                    #  At this point we really should be connected!!
                    if self.ascom:
                        #self.camera.AbortExposure()
                        g_dev['ocn'].get_quick_status(self.pre_ocn)
                        g_dev['foc'].get_quick_status(self.pre_foc)
                        g_dev['rot'].get_quick_status(self.pre_rot)
                        g_dev['mnt'].get_quick_status(self.pre_mnt)
                        self.t2 = time.time()       #Immediately before Exposure
                        self.camera.StartExposure(exposure_time, imtypeb)
                    elif self.maxim:
                        print('Link Enable check:  ', self._connected())
                        g_dev['ocn'].get_quick_status(self.pre_ocn)
                        g_dev['foc'].get_quick_status(self.pre_foc)
                        g_dev['rot'].get_quick_status(self.pre_rot)
                        g_dev['mnt'].get_quick_status(self.pre_mnt)
                        self.t2 = time.time()
                        ldr_handle_high_time = None  #  This is not maxim-specific
                        ldr_handle_time = None
                        try:
                            os.remove(self.camera_path + 'newest.fits')
                        except:
                            pass   #  print ("File newest.fits not found, this is probably OK")
                        if imtypeb:
                            img_type = 0
                        if frame_type == 'bias':
                            img_type = 1
                        if frame_type == 'dark':
                            img_type = 2
                        if frame_type in ('flat', 'screen flat', 'sky flat'):
                            img_type = 3
                        create_simple_sequence(exp_time=exposure_time, img_type=img_type, \
                                               filter_name=self.current_filter, binning=bin_x, \
                                               repeat=lcl_repeat)
                        #Clear out priors.
                        old_autosaves = glob.glob(self.camera_path + 'autosave/*.f*t*')
                        for old in old_autosaves:
                            os.remove(old)
                        self.entry_time = self.t2
                        self.camera.StartSequence('D:/archive/archive/kb01/seq/ptr_saf.seq')
                        print("Starting autosave  at:  ", self.entry_time)
                    else:
                        print("Something terribly wrong, driver not recognized.!")
                        breakpoint()
                        result = {}
                        result['error': True]
                        return result
                    self.t9 = time.time()

                    do_sep=False
                    #We go here to keep this subroutine a reasonable length, Basically still in Phase 2
                    result = self.finish_exposure(exposure_time,  frame_type, count - seq, \
                                         gather_status, do_sep, no_AWS, dist_x, dist_y, quick=quick, halt=halt, low=ldr_handle_time, \
                                         high=ldr_handle_high_time, script=self.script, opt=opt)  #  NB all these parameers are crazy!
                    self.exposure_busy = False
                    self.t10 = time.time()
                    #self.camera.AbortExposure()
                    print("inner expose returned:  ", result)
                    self.retry_camera = 0
                    break
                except Exception as e:
                    print('Exception:  ', e)
                    self.retry_camera -= 1
                    continue
            #  This point demarcates the retry_3_times loop
            print("Retry-3-times completed early:  ", self.retry_camera)
        #  This is the loop point for the seq count loop
        self.t11 = time.time()
        print("full expose seq took:  ", round(self.t11 - self.t_0 , 2), ' returned:  ', result)
        return result

#        for i in range(20):
#            pc = c.PercentCompleted
#            print(f"{pc}%")
#            if pc >= 100:
#                self.save_image()
#                break
#            time.sleep(1)

    def stop_command(self, required_params, optional_params):
        ''' Stop the current exposure and return the camera to Idle state. '''
        #NB NB This routine needs work!
        #self.camera.AbortExposure()
        self.exposure_busy = False

        # Alternative: self.camera.StopExposure() will stop the exposure and
        # initiate the readout process.



    ##  NB the number of  keywords is questionable.

    def finish_exposure(self, exposure_time, frame_type, counter, \
                        gather_status=True, do_sep=False, no_AWS=False, start_x=None, start_y=None, quick=False, halt=False, \
                        low=0, high=0, script='False', opt=None):
        #print("Finish exposure Entered:  ", self.af_step, exposure_time, frame_type, counter, ' to go!')
        print("Finish exposure Entered:  ", exposure_time, frame_type, counter,  \
                        gather_status, do_sep, no_AWS, start_x, start_y)

        if gather_status:   #Does this need to be here
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []
        counter = 0

        self.completion_time = self.entry_time + exposure_time + 8.8
        result = {'error': False}
        while True:     #THis is where we should have a camera probe throttle and timeout system
            try:
                #if self.maxim and self.camera.ImageReady: #and not self.img_available and self.exposing:
                result_file = glob.glob(self.autosave_path + '*f*t*')
                if self.maxim and len(result_file) > 0:
                    self.t4 = time.time()
                    print("entered phase 3")
                    # if not self._connected():
                    #     breakpoint()

                    #if not quick and gather_status:
                    if not quick and  gather_status:
                        #The image is ready
                        g_dev['mnt'].get_quick_status(self.post_mnt)  #stage symmetric around exposure
                        g_dev['rot'].get_quick_status(self.post_rot)
                        g_dev['foc'].get_quick_status(self.post_foc)
                        g_dev['ocn'].get_quick_status(self.post_ocn)
                    self.t5 = time.time()
                    # self.t6 = time.time()
                    # breakpoint()
                    # self.img = self.camera.ImageArray
                    # self.t7 = time.time()

                    # if frame_type[-4:] == 'flat':
                    #     test_saturated = np.array(self.img)
                    #     if (test_saturated.mean() + np.median(test_saturated))/2 > 50000:   # NB Should we sample a patch?
                    #         # NB How do we be sure Maxim does not hang?
                    #         print("Flat rejected, too bright:  ", round(test_saturated.mean, 0))
                    #         self.camera.AbortExposure()
                    #         return 65535, 0   # signals to flat routine image was rejected
                    # else:

                    #     g_dev['obs'].update_status()
                    #Save image with Maxim Header information, then read back with astropy and use the
                    #lqtter code for fits manipulation.
                    #This should be a very fast disk.
                    #
                    counter = 0
                    if not quick and gather_status:
                        avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                        avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                        avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                        avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                    else:
                        avg_foc = [0,0]   #This needs a serious clean-up
                    try:
                        #Save the raw data after adding fits header information.
#                        if not quick:
                        time.sleep(2)
                        img_name = glob.glob(self.camera_path + 'autosave/*.f*t*')
                        img_name.sort()
                        hdu1 =  fits.open(img_name[-1])
                        hdu = hdu1[0]
                        hdu.header['BUNIT']    = 'adu'
                        hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                        hdu.header['EXPTIME']  = exposure_time   #This is the exposure in seconds specified by the user
                        hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times
                        hdu.header['FILTER ']  = self.current_filter
                        hdu.header['FILTEROF']  = self.current_offset
                        if g_dev['scr'] is not None and frame_type == 'screen flat':
                            hdu.header['SCREEN'] = int(g_dev['scr'].bright_setting)
                        hdu.header['IMAGETYP'] = frame_type   #This report is fixed and it should vary...NEEDS FIXING!
                        if self.maxim:
                            hdu.header['SET-TEMP'] = round(self.camera.TemperatureSetpoint, 3)
                            hdu.header['CCD-TEMP'] = round(self.camera.Temperature, 3)
                        if self.ascom:
                            hdu.header['SET-TEMP'] = round(self.camera.SetCCDTemperature, 3)
                            hdu.header['CCD-TEMP'] = round(self.camera.CCDTemperature, 3)
                        hdu.header['XPIXSZ']   = round(float(self.camera.PixelSizeX), 3)      #Should this adjust with binning?
                        hdu.header['YPIXSZ']   = round(float(self.camera.PixelSizeY), 3)
                        try:
                            hdu.header['XBINING'] = self.camera.BinX
                            hdu.header['YBINING'] = self.camera.BinY
                        except:
                            hdu.header['XBINING'] = 1
                            hdu.header['YBINING'] = 1
                        hdu.header['CCDSUM'] = '1 1'
                        hdu.header['XORGSUBF'] = self.camera_start_x    #This makes little sense to fix...  NB ALL NEEDS TO COME FROM CONFIG!!
                        hdu.header['YORGSUBF'] = self.camera_start_y
                        hdu.header['READOUTM'] = 'Monochrome'    #NB this needs to be updated
                        hdu.header['TELESCOP'] = self.config['telescope']['telescope1']['desc']
                        hdu.header['FOCAL']    = round(float(self.config['telescope']['telescope1']['focal_length']), 2)
                        hdu.header['APR-DIA']  = round(float(self.config['telescope']['telescope1']['aperture']), 2)
                        hdu.header['APR-AREA'] = round(float(self.config['telescope']['telescope1']['collecting_area']), 1)
                        hdu.header['SITELAT']  = round(float(self.config['latitude']), 6)
                        hdu.header['SITE-LNG'] = round(float(self.config['longitude']), 6)
                        hdu.header['SITE-ELV'] = round(float(self.config['elevation']), 2)
                        hdu.header['MPC-CODE'] = 'zzzzz'       # This is made up for now.
                        hdu.header['JD-START'] = 'bogus'       # Julian Date at start of exposure
                        hdu.header['JD-HELIO'] = 'bogus'       # Heliocentric Julian Date at exposure midpoint
                        hdu.header['OBJECT']   = ''
                        hdu.header['SID-TIME'] = self.pre_mnt[3]
                        hdu.header['OBJCTRA']  = self.pre_mnt[1]
                        hdu.header['OBJCTDEC'] = self.pre_mnt[2]
                        hdu.header['OBRARATE'] = self.pre_mnt[4]
                        hdu.header['OBDECRAT'] = self.pre_mnt[5]
                        hdu.header['INSTRUME'] = self.camera_model
                        hdu.header['OBSERVER'] = 'WER DEV'
                        hdu.header['NOTE']     = self.hint[0:54]            #Needs to be truncated.
                        hdu.header['FLIPSTAT'] = 'None'
                        hdu.header['SEQCOUNT'] = int(counter)
                        hdu.header['DITHER']   = 0
                        hdu.header['OPERATOR'] = "WER"
                        hdu.header['ENCLOSE']  = "Clamshell"   #Need to document shutter status, azimuth, internal light.
                        hdu.header['DOMEAZ']  = "NA"   #Need to document shutter status, azimuth, internal light.
                        hdu.header['ENCLIGHT'] ="Off/White/Red/IR"
                        if not quick and gather_status:
                            hdu.header['MNT-SIDT'] = avg_mnt['sidereal_time']
                            ha = avg_mnt['right_ascension'] - avg_mnt['sidereal_time']
                            hdu.header['MNT-RA'] = avg_mnt['right_ascension']
                            while ha >= 12:
                                ha -= 24.
                            while ha < -12:
                                ha += 24.
                            hdu.header['MNT-HA'] = round(ha, 4)
                            hdu.header['MNT-DEC'] = avg_mnt['declination']
                            hdu.header['MNT-RAV'] = avg_mnt['tracking_right_ascension_rate']
                            hdu.header['MNT-DECV'] = avg_mnt['tracking_declination_rate']
                            hdu.header['AZIMUTH '] = avg_mnt['azimuth']
                            hdu.header['ALTITUDE'] = avg_mnt['altitude']
                            hdu.header['ZENITH  '] = avg_mnt['zenith_distance']
                            hdu.header['AIRMASS '] = avg_mnt['airmass']
                            hdu.header['MNTRDSYS'] = avg_mnt['coordinate_system']
                            hdu.header['POINTINS'] = avg_mnt['instrument']
                            hdu.header['MNT-PARK'] = avg_mnt['is_parked']
                            hdu.header['MNT-SLEW'] = avg_mnt['is_slewing']
                            hdu.header['MNT-TRAK'] = avg_mnt['is_tracking']
                            hdu.header['OTA'] = ""
                            hdu.header['ROTATOR'] = ""
                            hdu.header['ROTANGLE'] = avg_rot[1]
                            hdu.header['ROTMOVNG'] = avg_rot[2]
                            hdu.header['FOCUS'] = ""
                            hdu.header['FOCUSPOS'] = avg_foc[1]
                            hdu.header['FOCUSTEM'] = avg_foc[2]
                            hdu.header['FOCUSMOV'] = avg_foc[3]
                            hdu.header['WX'] = ""
                            hdu.header['SKY-TEMP'] = avg_ocn[1]
                            hdu.header['AIR-TEMP'] = avg_ocn[2]
                            hdu.header['HUMIDITY'] = avg_ocn[3]
                            hdu.header['DEWPOINT'] = avg_ocn[4]
                            hdu.header['WIND'] = avg_ocn[5]
                            hdu.header['PRESSURE'] = avg_ocn[6]
                            hdu.header['CALC-LUX'] = avg_ocn[7]
                            hdu.header['SKY-HZ'] = avg_ocn[8]
                            if g_dev['enc'] is not None:
                                hdu.header['ROOF']  = g_dev['enc'].get_status()['shutter_status']   #"Open/Closed"
                        hdu.header['DETECTOR'] = self.config['camera']['camera1']['detector']
                        hdu.header['CAMNAME'] = self.config['camera']['camera1']['name']
                        hdu.header['CAMMANUF'] = self.config['camera']['camera1']['manufacturer']
    #                        try:
    #                            hdu.header['GAIN'] = g_dev['cam'].camera.gain
                        #print('Gain was read;  ', g_dev['cam'].camera.gain)
    #                        except:
    #                            hdu.header['GAIN'] = 1.18
                        hdu.header['GAINUNIT'] = 'e-/ADU'
                        hdu.header['GAIN'] = 1.2   #20190911   LDR-LDC mode set in ascom
                        hdu.header['RDNOISE'] = 8
                        hdu.header['CMOSCAM'] = self.is_cmos
                        #hdu.header['CMOSMODE'] = 'HDR-HDC'  #Need to figure out how to read this from setup.
                        hdu.header['SATURATE'] = int(self.config['camera']['camera1']['settings']['saturate'])
                        #NB This needs to be properly computed
                        pix_ang = (self.camera.PixelSizeX*self.camera.BinX/(float(self.config['telescope'] \
                                                  ['telescope1']['focal_length'])*1000.))
                        hdu.header['PIXSCALE'] = round(math.degrees(math.atan(pix_ang))*3600., 2)


                        #Need to assemble a complete header here
                        #hdu1.writeto('Q:\\archive\\ea03\\new2b.fits')#, overwrite=True)
                        #NB rename to ccurrent_camera
                        current_camera_name = self.config['camera']['camera1']['name']
                        # NB This needs more deveopment
                        im_type = 'EX'   #or EN for engineering....
                        f_ext = ""
                        next_seq = next_sequence(current_camera_name)
                        if frame_type[-4:] == 'flat':
                            f_ext = '-' + str(self.current_filter)    #Append flat string to local image name
                        cal_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                                                    next_seq  + f_ext + '-'  + im_type + '00.fits'
                        raw_name00 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                            next_seq  + '-' + im_type + '00.fits'
                        raw_name01 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                            next_seq  + '-' + im_type + '01.fits'
                        #Cal_ and raw_ names are confusing
                        db_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                            next_seq  + '-' + im_type + '13.fits'
                        jpeg_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                            next_seq  + '-' + im_type + '13.jpg'
                        text_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                            next_seq  + '-' +  im_type + '01.txt'

                        im_path_r = self.camera_path
                        lng_path = self.lng_path
                        hdu.header['DAY-OBS'] = g_dev['day']
                        hdu.header['DATE'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                        hdu.header['ISMASTER'] = False
                        hdu.header['FILEPATH'] = str(im_path_r) +'to_AWS\\'
                        hdu.header['FILENAME'] = str(raw_name00)
                        hdu.header['REQNUM'] = '00000001'
                        hdu.header['BLKUID'] = 'None'
                        hdu.header['BLKSDATE'] = 'None'
                        hdu.header['MOLUID'] = 'None'
                        hdu.header['OBSTYPE'] = 'None'
                        #print('Creating:  ', im_path + g_dev['day'] + '\\to_AWS\\  ... subdirectory.')
                        try:

                            os.makedirs(im_path_r + g_dev['day'] + '/to_AWS/', exist_ok=True)
                            os.makedirs(im_path_r + g_dev['day'] + '/raw/', exist_ok=True)
                            os.makedirs(im_path_r + g_dev['day'] + '/calib/', exist_ok=True)
                            #print('Created:  ',im_path + g_dev['day'] + '\\to_AWS\\' )
                            im_path = im_path_r + g_dev['day'] + '/to_AWS/'
                            raw_path = im_path_r + g_dev['day'] + '/raw/'
                            cal_path = im_path_r + g_dev['day'] + '/calib/'
                        except:
                            pass

                        text = open(im_path + text_name, 'w')  #This is always needed by AWS to set up database.
                        text.write(str(hdu.header))
                        text.close()
                        text_data_size = len(str(hdu.header)) - 4096
                        if not quick and not script in ('True', 'true', 'On', 'on'):
                            hdu.writeto(raw_path + raw_name00, overwrite=True)
                        if script in ('True', 'true', 'On', 'on'):
                            hdu.writeto(cal_path + cal_name, overwrite=True)
                            try:
                                os.remove(self.camera_path + 'newest.fits')
                            except:
                                pass    #  print ("File newest.fits not found, this is probably OK")
                            return {'patch': 0.0}   #  Note we are not calibrating. Just saving the file.
                            # NB^ We always write files to raw, except quick(autofocus) frames.
                            # hdu.close()
                        # raw_data_size = hdu.data.size

                        print("\n\Finish-Exposure is complete:  " + raw_name00)#, raw_data_size, '\n')
                        g_dev['obs'].update_status()
                        #NB Important decision here, do we flash calibrate screen and sky flats?  For now, Yes.

                        cal_result = calibrate(hdu, None, lng_path, frame_type, start_x=start_x, start_y=start_y, quick=quick)
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
                        spot = None
                        if do_sep:
                            try:
                                img = hdu.data.copy().astype('float')
                                bkg = sep.Background(img)
                                #bkg_rms = bkg.rms()
                                img -= bkg
                                sources = sep.extract(img, 7, err=1, minarea=30)#, filter_kernel=kern)
                                sources.sort(order = 'cflux')
                                print('No. of detections:  ', len(sources))
                                sep_result = []
                                spots = []
                                for source in sources:
                                    a0 = source['a']
                                    b0 =  source['b']
                                    if (a0 - b0)/(a0 + b0)/2 > 0.1:    #This seems problematic and should reject if peak > saturation
                                        continue
                                    r0 = round(math.sqrt(a0**2 + b0**2), 2)
                                    sep_result.append((round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), \
                                                   round(r0), 2))
                                    spots.append(round((r0), 2))
                                spot = np.array(spots)
                                try:
                                    spot = np.median(spot[int(len(spot)*0.5):int(len(spot)*0.75)])
                                    print(sep_result, '\n', 'Spot and flux:  ', spot, source['cflux'], len(sources), avg_foc[1], '\n')
                                    if len(sep_result) < 5:
                                        spot = None
                                except:
                                    spot = None
                            except:
                                spot = None
                        if spot == None:
                            if opt is not None:
                                spot = opt.get('fwhm_sim', 0.0)

                        if not quick:
                            hdu.header["PATCH"] = cal_result
                            if spot is not None:
                                hdu.header['SPOTFWHM'] = round(spot, 2)
                            else:
                                hdu.header['SPOTFWHM'] = "None"
                            hdu1.writeto(im_path + raw_name01, overwrite=True)
                        raw_data_size = hdu1[0].data.size
                        g_dev['obs'].update_status()
                        #Here we need to process images which upon input, may not be square.  The way we will do that
                        #is find which dimension is largest.  We then pad the opposite dimension with 1/2 of the difference,
                        #and add vertical or horizontal lines filled with img(min)-2 but >=0.  The immediate last or first line
                        #of fill adjacent to the image is set to 80% of img(max) so any subsequent subframing selections by the
                        #user is informed. If the incoming image dimensions are odd, they wil be decreased by one.  In essence
                        #we wre embedding a non-rectaglular image in a "square" and scaling it to 768^2.  We will impose a
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

                        db_data_size = hdu.data.size
                        hdu1.writeto(im_path + db_name, overwrite=True)
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
                        imsave(im_path + jpeg_name, img3)
                        jpeg_data_size = img3.size - 1024
                        if not no_AWS:  #IN the no+AWS case should we skip more of the above processing?
                            self.enqueue_image(text_data_size, im_path, text_name)
                            self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                            if not quick:
                                self.enqueue_image(db_data_size, im_path, db_name)
                                self.enqueue_image(raw_data_size, im_path, raw_name01)
                            print('Sent to AWS Queue.')
                        time.sleep(0.5)
                        self.img = None
                        # try:
                        #     self.camera.AbortExposure()
                        # except:
                        #     pass
                        try:
                            hdu = None
                        except:
                            pass
                        try:
                            hdu1 = None
                        except:
                            pass
                        result['mean_focus'] = avg_foc[1]
                        result['mean_rotation'] = avg_rot[1]
                        result['FWHM'] = spot
                        result['half_FD'] = None
                        result['patch'] = cal_result
                        result['temperature'] = avg_foc[2]
                        return result
                    except Exception as e:
                        print('Header assembly block failed: ', e)
                        breakpoint()
                        # try:
                        #     self.camera.AbortExposure()
                        # except:
                        #     pass
                        try:
                            hdu = None
                        except:
                            pass
                        try:
                            hdu1 = None
                        except:
                            pass
                        self.t7 = time.time()
                    return result['error': True]
                else:     #here we are in waiting for imageReady loop and could send status and check Queue
                    time.sleep(.3)
                    g_dev['obs'].update_status()   #THIS CALL MUST NOT ACCESS MAXIM OBJECT!
                    time_now = self.t7= time.time()
                    remaining = round(self.completion_time - time_now, 1)
                    loop_count = int(remaining/0.3)

                    print("Basic camera wait loop, be patient:  ", round(remaining, 1), ' sec.')
                    for i in range(loop_count):
                        #g_dev['obs'].update_status()
                        time.sleep(0.3)
                        if i % 30 == 0:
                            time_now = self.t7= time.time()
                            remaining = round(self.completion_time - time_now, 1)
                            print("Basic camera wait loop, be patient:  ", round(remaining, 1), ' sec.')
                            g_dev['obs'].update_status()
                        # if i % 100 == 45:
                        #     lcl_connected = self._connected()
                        #     if i < loop_count*0.95 and not lcl_connected:
                        #         print("Connected dr0pped")
                        #         breakpoint()
                        #     print('Camera is connected:  ', lcl_connected)
                        # if i % 100 == 75:
                        #     lcl_running = self.camera.SequenceRunning
                        #     if i < loop_count * 0.95 and not lcl_running:
                        #         print("Sequence dropped out.")
                        #         breakpoint()
                        #     else:
                        #         print('Sequencer is Busy:  ', lcl_running)

                    #it takes about 15 seconds from AWS to get here for a bias.
            except Exception as e:
                breakpoint()
                counter += 1
                time.sleep(.01)
                #This should be counted down for a loop cancel.
                print('Was waiting for exposure end, arriving here is bad news:  ', e)

                # try:
                #     self.camera.AbortExposure()
                # except:
                #     pass
                try:
                    hdu = None
                except:
                    pass
                try:
                    hdu1 = None
                except:
                    pass
                return  result['error': True]

        #definitely try to clean up any messes.
        # try:
        #     self.camera.AbortExposure()
        # except:
        #     pass
        try:
            hdu = None
        except:
            pass
        try:
            hdu1 = None
        except:
            pass

        self.t8 = time.time()
        result['error': True]
        print('Outer Try:  ', result )
        return result

    def enqueue_image(self, priority, im_path, name):
        image = (im_path, name)
        #print("stuffing Queue:  ", priority, im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)

