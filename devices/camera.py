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
# NB this routine is duplicated in sequencer.py. Bad form.



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
        print("Connecting to:  ", driver)


        if driver[:5].lower() == 'ascom':
            print('ASCOM camera is initializing.')
            #Monkey patch in ASCOM specific methods.
            self._connected = self._ascom_connected
            self._connect = self._ascom_connect
            self._setpoint = self._ascom_setpoint
            self._temperature = self._ascom_temperature
            self._expose = self._ascom_expose
            self._stop_expose = self._ascom_stop_expose
            self.description = "ASCOM"
            self.maxim = False
            self.ascom = True
            print('ASCOM is connected:  ', self._connect(True))
            print('Control is ASCOM camera driver.')
        else:
            print('Maxim camera is initializing.')
            #Monkey patch in Maxim specific methods.
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            self._setpoint = self._maxim_setpoint
            self._temperature = self._maxim_temperature
            self._expose = self._maxim_expose
            self._stop_expose = self._maxim_stop_expose
            self.description = 'MAXIM'
            self.maxim = True
            self.ascom = False
            print('Maxim is connected:  ', self._connect(True))
            self.app = win32com.client.Dispatch("Maxim.Application")
            self.app.TelescopeConnected = True
            print("Maxim Telescope Connected: ", self.app.TelescopeConnected)
            print('Control is Maxim camera interface.')
        #print(self._connect(True))
        #print(self._connected())
        print('Cooler Setpoint:  ', self._setpoint(float(self.config['camera']['camera1']['settings']['temp_setpoint'])))
        print(self._temperature())
        cooler_on = self.config['camera']['camera1'] 
        print('Maxim is connected:  ', self._connect(True))
        #  print(self._connected())
        print('Setpoint:  ', self._setpoint(float(self.config['camera']['camera1']['settings']['temp_setpoint'])))
        print('Chip Temperature:  ', self._temperature())
        cooler_on = self.config['camera']['camera1'] \
                               ['settings']['cooler_on'] in ['True', 'true', 'Yes', 'yes', 'On', 'on']
        self.camera.CoolerOn = cooler_on
        # NB Should get and report cooer power
        self.current_filter = 0    #W in Apache Ridge case. #This should come from congig, filter section
        self.exposure_busy = False
        self.cmd_in = None
        self.t7 = None
        self.camera_message = '-'
        self.alias = self.config['camera']['camera1']['name']
        self.site_path = self.config['site_path']
        self.archive_path = self.site_path +'archive/'
        self.camera_path = self.archive_path  + self.alias+ "/"
        self.autosave_path = self.camera_path +'autosave/'
        self.lng_path = self.camera_path + "lng/"
        self.seq_path = self.camera_path + "seq/"
        try:
            os.remove(self.camera_path + 'newest.fits')   #NB This needs to properly clean out all autosaves
        except:
            print ("File newest.fits not found, this is probably OK")
        self.is_cmos = False
        if self.config['camera']['camera1']['settings']['is_cmos']  == 'true':
            self.is_cmos = True
        self.camera_model = self.config['camera']['camera1']['desc']
        #NB We are reading from the actual camera or setting as the case may be.  For initial setup,
        #   we pull from config for some of the various settings.
        try:
            self.camera.BinX = int(self.config['camera']['camera1']['settings']['default_bin'][0])
            self.camera.BinY = int(self.config['camera']['camera1']['settings']['default_bin'][1])
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

    def _maxim_expose(self, exposure_time, imtypeb):
        self.camera.Expose(exposure_time, imtypeb)

    def _maxim_stop_expose(self):
        self.camera.AbortExposure()

    def _ascom_connected(self):
        return self.camera.Connected

    def _ascom_connect(self, p_connect):
        self.camera.Connected = p_connect
        return self.camera.Connected

    def _ascom_temperature(self):
        return self.camera.CCDTemperature

    def _ascom_setpoint(self, p_temp):
        self.camera.SetCCDTemperature = float(p_temp)
        return self.camera.SetCCDTemperature

    def _ascom_expose(self, exposure_time, imtypeb):
            self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
            self.camera.StopExposure()   #ASCOM also has an AbortExposure method.

    def create_simple_sequence(self, exp_time=0, img_type=0, speed=0, suffix='', repeat=1, \
                        readout_mode="", filter_name='W', enabled=1, \
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
        proto_file = open(self.seq_path + 'ptr_saf_pro.seq', 'r')
        proto = proto_file.readlines()
        proto_file.close()
        # for i in range(len(proto)):
        #     print(i, proto[i])

        if column == 1:
            proto[50] = proto[50][:9]  + str(exp_time) + proto[50][12:]
            proto[51] = proto[51][:9]  + str(img_type) + proto[51][10:]
            proto[48] = proto[48][:12] + str(suffix)   + proto[48][12:]
            proto[47] = proto[47][:10] + str(speed)    + proto[47][11:]
            proto[31] = proto[31][:11] + str(repeat)   + proto[31][12:]
            proto[29] = proto[29][:17] + readout_mode  + proto[29][20:]
            proto[13] = proto[13][:12] + filter_name   + proto[13][13:]
            proto[10] = proto[10][:12] + str(enabled)  + proto[10][13:]
            proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
        seq_file = open(self.seq_path + 'ptr_saf.seq', 'w')
        for item in range(len(proto)):
            seq_file.write(proto[item])
        seq_file.close()
        # print(proto)


    #  TEST  create_simple_sequence(exp_time=0, img_type=0, suffix='', repeat=1, \
    #                       binning=3, filter_name='air')


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
        self.user_id = command['user_id']
        self.user_name = command['user_name']
# =============================================================================
# # # =============================================================================
#         if opt['filter'] == 'dark' and opt['bin'] == '2,2':    # Special case, AWS broken 20200405
#              g_dev['seq'].screen_flat_script(req, opt)
# # # =============================================================================
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
                       gather_status = True, do_sep=True, no_AWS=False, quick=False):
        '''
        This is Phase 1:  Setup the camera.
        Apply settings and start an exposure.
        Quick=True is meant to be fast.  We assume the ASCOM/Maxim imageBuffer is the source of data in that mode,
        not the slower File Path.  THe mode used for focusing or other operations where we do not want to save any
        image data.
        '''
        print('Expose Entered.  req:  ', required_params, 'opt:  ', optional_params)
        print("Checking if Maxim is still connected!")
        if self.t7 is not None and (time.time() - self.t7 > 30) and self.maxim:
            self._connect(False)
            self._connect(True)
            self.camera.CoolerOn = True
            
        # try:
        #     probe = False
        #     breakpoint()
        #     self._connect(False)
        #     self._connect(True)
        #     probe = self.connected()
        #     self.camera.CoolerOn = True
        #     print("Maxim is  connected:  ", probe)
        # except:
        #     print("Reconnecting Maxim failed, try again.")
        #     self._connect(False)
        #     self._connect(True)
        #     self.camera.CoolerOn = True
        opt = optional_params
        self.t_0 = time.time()
        self.hint = optional_params.get('hint', '')
        self.script = required_params.get('script', 'None')
        bin_x = optional_params.get('bin', self.config['camera']['camera1'] \
                                                      ['settings']['default_bin'])  #NB this should pick up config default.
        if bin_x == '4, 4':     # For now this is the highest level of binning supported.
            bin_x = 2
        elif bin_x == '3, 3':   # replace with in and various formats or strip spaces.
            bin_x = 2
        elif bin_x == '2, 2':
            bin_x = 2
            self.ccd_sum = '2 2'
        else:
            bin_x = 1
            self.ccd_sum = '1 1'
        bin_y = bin_x   #NB This needs fixing someday!
        self.bin = bin_x
        self.camera.BinX = bin_x
        self.camera.BinY = bin_y
        #gain = float(optional_params.get('gain', self.config['camera']['camera1'] \
        #                                              ['settings']['reference_gain'][bin_x - 1]))
        readout_time = float(self.config['camera']['camera1']['settings']['readout_time'][bin_x - 1])
        exposure_time = float(required_params.get('time', 0.00001))   #  0.0 may be the best default.
        self.estimated_readtime = (exposure_time + 2*readout_time)*1.25*3   #  3 is the outer retry loop maximum.
        #exposure_time = max(0.2, exposure_time)  #Saves the shutter, this needs qualify with imtype.
        imtype= required_params.get('image_type', 'Light')
        if imtype.lower() in ['experimental']:
            g_dev['enc'].wx_test = not g_dev['enc'].wx_test
            return
        count = int(optional_params.get('count', 1))   #FOr now Repeats are external to full expose command.
        lcl_repeat = 1
        if count < 1:
            count = 1   #Hence frame does not repeat unless count > 1

        #  Here we set up the filter, and later on possibly roational composition.
        try:    #20200716   FW throwing error (-4)
            requested_filter_name = str(optional_params.get('filter', 'w'))   #Default should come from config.
            self.current_filter = requested_filter_name
            g_dev['fil'].set_name_command({'filter': requested_filter_name}, {})
        except Exception as e:
            print(e)
            breakpoint()
        #  NBNB Changing filter may cause a need to shift focus
        self.current_offset = '????'#g_dev['fil'].filter_offset  #TEMP   NBNBNB This needs fixing
        #  NB nothing being done here to get focus set properly. Where is this effected?

        sub_frame_fraction = optional_params.get('subframe', None)
        #  The following bit of code is convoluted.  Presumably when we get Autofocus working this will get cleaned up.
        self.toss = False
        self.do_sep = False
        if imtype.lower() in ('light', 'light frame', 'screen flat', 'sky flat', 'experimental', 'test image'):
                                 #here we might eventually turn on spectrograph lamps as needed for the imtype.
            imtypeb = True    #imtypeb will passed to open the shutter.
            frame_type = imtype.lower()
            do_sep = True
            self.do_sep = True
            if imtype.lower() in ('screen flat', 'sky flat', 'guick'):
                do_sep = False
                self.do_sep = False
            if imtype.lower() == 'test image':
                self.toss = True
        elif imtype.lower() == 'bias':
            exposure_time = 0.00001
            imtypeb = False
            frame_type = 'bias'
            no_AWS = False
            do_sep = False
            self.do_sep = False
            # Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'dark':
            imtypeb = False
            frame_type = 'dark'
            no_AWS = False
            do_sep = False
            self.do_sep = False
            # Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'screen flat':
            frame_type = 'screen flat'
        elif imtype.lower() == 'sky flat':
            frame_type = 'flat'
            self.do_sep = False
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

        area = optional_params.get('area', 100)
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
        self.len_x = self.camera.CameraXSize//self.bin_x
        self.len_y = self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
        self.len_xs = 0  # THIS IS A HACK, indicating no overscan.
        # print(self.len_x, self.len_y)
        #  NB Area is just a series of subframes centered on the chip.
        # "area": ['100%', '71%', '50%',  '35%', '25%', '12%']

        if 72 < area <= 100:
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
            self.area = 100
            print("Default area used. 100%")

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
                while g_dev['foc'].focuser.IsMoving or g_dev['rot'].rotator.IsMoving or \
                      g_dev['mnt'].mount.Slewing or g_dev['enc'].enclosure.Slewing:   #Filter is moving??
                    if g_dev['foc'].focuser.IsMoving: st += 'f>'
                    if g_dev['rot'].rotator.IsMoving: st += 'r>'
                    if g_dev['mnt'].mount.Slewing: st += 'm>'
                    if g_dev['enc'].enclosure.Slewing: st += 'd>'
                    print(st)
                    st = ""
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
                    #print('First Entry to inner Camera loop:  ')  #  Do not reference camera, self.camera.StartX, self.camera.StartY, self.camera.NumX, self.camera.NumY, exposure_time)
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

                    if self.maxim or self.ascom:
                        #print('Link Enable check:  ', self._connected())
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
                        if frame_type in ('flat', 'screen flat','screen_flat', 'sky flat', 'sky_flat'):
                            img_type = 3

                        # self.create_simple_sequence(exp_time=exposure_time, img_type=img_type, \
                        #                        filter_name=self.current_filter, binning=bin_x, \
                        #                        repeat=lcl_repeat)
                        # #Clear out priors.
                        # old_autosaves = glob.glob(self.camera_path + 'autosave/*.f*t*')
                        # for old in old_autosaves:
                        #     os.remove(old)
                        if exposure_time < 0.00001:
                            exposure_time = 0.00001
                        if exposure_time > 3600:
                            exposure_time = 3600
                        print('Filter number is:  ', self.camera.Filter)
                        self.entry_time = self.t2
                        self._expose (exposure_time, img_type)
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
                                         gather_status, do_sep, no_AWS, dist_x, dist_y, quick=quick, low=ldr_handle_time, \
                                         high=ldr_handle_high_time, script=self.script, opt=opt)  #  NB all these parameers are crazy!
                    self.exposure_busy = False
                    self.t10 = time.time()
                    #self._stop_expose()
                    print("inner expose took:  ", round(self.t10 - self.t_0 , 2), ' returned:  ', result)
                    self.retry_camera = 0
                    break
                except Exception as e:
                    print('Exception:  ', e)
                    self.retry_camera -= 1
                    continue
            #  This point demarcates the retry_3_times loop
            #print("Retry-3-times completed early:  ", self.retry_camera)
        #  This is the loop point for the seq count loop
        self.t11 = time.time()
        print("full expose seq took:  ", round(self.t11 - self.t_0 , 2), ' returned:  ', result)
        return result

    def stop_command(self, required_params, optional_params):
        ''' Stop the current exposure and return the camera to Idle state. '''
        #NB NB This routine needs work!
        self.exposure_busy = False
        
    ##  NB the number of  keywords is questionable.
    def finish_exposure(self, exposure_time, frame_type, counter, \
                        gather_status=True, do_sep=False, no_AWS=False, start_x=None, start_y=None, quick=False, \
                        low=0, high=0, script='False', opt=None):
        print("Finish exposure Entered:  ", exposure_time, frame_type, counter, \
              gather_status, do_sep, no_AWS, start_x, start_y)
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0
        if self.bin == 1:
            self.completion_time = self.entry_time + exposure_time + 9
        else:
            self.completion_time = self.entry_time + exposure_time + 5
        result = {'error': False}
        while True:
            g_dev['mnt'].get_quick_status(self.post_mnt)
            g_dev['rot'].get_quick_status(self.post_rot)
            g_dev['foc'].get_quick_status(self.post_foc)
            g_dev['ocn'].get_quick_status(self.post_ocn)
            self.t5 = time.time()
            if (self.maxim or self.ascom) and self.camera.ImageReady:
                self.t4 = time.time()
                print("reading out camera, takes ~20 seconds.")
                time.sleep(0.5)   #  THIS appears to be necessary. 20200804 WER
                self.img = self.camera.ImageArray
                self.t7 = time.time()
                print('readout took:  ', round(self.t7 - self.t4, 1), ' sec,')
               
                self._stop_expose()  # Is this necessary?
                if self.maxim:
                    self.camera.SaveImage("D:/000ptr_saf/garbage/junk.fit")
                self.img = np.array(self.img).transpose()  #  .astype('int32')
                # Overscan remove and trim.
                pedastal = 200
                iy, ix = self.img.shape
                if ix == 9600:
                    overscan = int(np.median(self.img[33:, -22:]))
                    trimed = self.img[36 :, : -26] + pedastal - overscan
                    square = trimed[121 : 121 + 6144, 1715 : 1715 + 6144]
                elif ix == 4800:
                    overscan = int(np.median(self.img[17:, -11:]))
                    trimed = self.img[18 :, : -13] + pedastal - overscan
                    square = trimed[61:61 + 3072, 857:857 + 3072]
                else:
                    print("Incorrect chip size or bin specified.")
                smin = np.where(square < 0)    # finds negative pixels
                square[smin] = 0               # marks them as 0
                self.img = square.astype('uint16')
                test_saturated = np.array(self.img)[1536:4608, 1536:4608]
                bi_mean = (test_saturated.mean() + np.median(test_saturated))/2
                if frame_type[-4:] == 'flat' and bi_mean > 33000:
                    print("Flat rejected, too bright:  ", round(bi_mean, 0))
                    result = {}
                    result['patch'] = round(bi_mean, 1)
                    return result   #  signals to flat routine image was rejected
                g_dev['obs'].update_status()
                counter = 0
                avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                try:
                    time.sleep(2)
                    hdu = fits.PrimaryHDU(self.img)
                    self.img = None    #  Does this free up any resource?
                    hdu.header['BUNIT'] = 'adu'
                    hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                    hdu.header['EXPTIME'] = exposure_time   #This is the exposure in seconds specified by the user
                    hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times
                    hdu.header['FILTER '] = self.current_filter  # NB this should read from the wheel!
                    hdu.header['FILTEROF'] = self.current_offset
                    hdu.header['IMAGETYP'] = frame_type   #This report is fixed and it should vary...NEEDS FIXING!
                    if g_dev['scr'] is not None and frame_type == 'screen flat':
                        hdu.header['SCREEN'] = int(g_dev['scr'].bright_setting)
                    #should replace with Monkey patched attributes.
                    if self.maxim:
                        hdu.header['SET-TEMP'] = round(self.camera.TemperatureSetpoint, 3)
                        hdu.header['CCD-TEMP'] = round(self.camera.Temperature, 3)
                    if self.ascom:
                        hdu.header['SET-TEMP'] = round(self.camera.SetCCDTemperature, 3)
                        hdu.header['CCD-TEMP'] = round(self.camera.CCDTemperature, 3)
                    hdu.header['XPIXSZ']   = round(float(self.camera.PixelSizeX*self.camera.BinX), 3)      #Should this adjust with binning?
                    hdu.header['YPIXSZ']   = round(float(self.camera.PixelSizeY*self.camera.BinY), 3)
                    try:
                        hdu.header['XBINING'] = self.camera.BinX
                        hdu.header['YBINING'] = self.camera.BinY
                    except:
                        hdu.header['XBINING'] = 1
                        hdu.header['YBINING'] = 1
                    hdu.header['PEDASTAL'] = -pedastal
                    hdu.header['ERRORVAL'] = 0
                    hdu.header['OVERSCAN'] = overscan
                    hdu.header['PATCH'] = bi_mean    #  A crude value for the central exposure
                    hdu.header['CCDSUM'] = self.ccd_sum
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
                    #  if gather_status:
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
                    hdu.header['SELECTEL'] = "tel1"
                    hdu.header['ROTATOR'] = ""
                    hdu.header['ROTANGLE'] = avg_rot[1]
                    hdu.header['ROTMOVNG'] = avg_rot[2]
                    hdu.header['FOCUS'] = ""
                    hdu.header['FOCUSPOS'] = avg_foc[1]
                    hdu.header['FOCUSTMP'] = avg_foc[2]
                    hdu.header['FOCUSMOV'] = avg_foc[3]
                    hdu.header['WX'] = ""
                    hdu.header['SKY-TEMP'] = avg_ocn[1]
                    hdu.header['AIR-TEMP'] = avg_ocn[2]
                    hdu.header['HUMIDITY'] = avg_ocn[3]
                    hdu.header['DEWPOINT'] = avg_ocn[4]
                    hdu.header['WIND'] = avg_ocn[5]
                    hdu.header['PRESSURE'] = avg_ocn[6]
                    hdu.header['CALC-LUX'] = avg_ocn[7]
                    hdu.header['SKY-LUX'] = avg_ocn[8]
                    if g_dev['enc'] is not None:
                        hdu.header['ROOF']  = g_dev['enc'].get_status()['shutter_status']   #"Open/Closed"
                    hdu.header['DETECTOR'] = self.config['camera']['camera1']['detector']
                    hdu.header['CAMNAME'] = self.config['camera']['camera1']['name']
                    hdu.header['CAMMANUF'] = self.config['camera']['camera1']['manufacturer']
                    hdu.header['GAINUNIT'] = 'e-/ADU'
                    hdu.header['GAIN'] = .584   #20190911   LDR-LDC mode set in ascom
                    hdu.header['RDNOISE'] = 3.5
                    hdu.header['CMOSCAM'] = self.is_cmos
                    hdu.header['CAMGAIN'] = 0
                    hdu.header['CAMBITS'] = 16
                    hdu.header['CAMOFFS'] = 10
                    hdu.header['CAMUSBT'] = 60
                    hdu.header['FULLWELL'] = 32767
                    hdu.header['SATURATE'] = int(self.config['camera']['camera1']['settings']['saturate'])
                    pix_ang = (self.camera.PixelSizeX*self.camera.BinX/(float(self.config['telescope'] \
                                              ['telescope1']['focal_length'])*1000.))
                    hdu.header['PIXSCALE'] = round(math.degrees(math.atan(pix_ang))*3600., 3)
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
                    red_name01 = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '01.fits'
                    #Cal_ and raw_ names are confusing
                    i768sq_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '10.fits'
                    jpeg_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' + im_type + '10.jpg'
                    text_name = self.config['site'] + '-' + current_camera_name + '-' + g_dev['day'] + '-' + \
                        next_seq  + '-' +  im_type + '00.txt'
                    im_path_r = self.camera_path
                    lng_path = self.lng_path
                    hdu.header['DAY-OBS'] = g_dev['day']
                    hdu.header['DATE'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                    hdu.header['ISMASTER'] = False
                    hdu.header['FILEPATH'] = str(im_path_r) +'to_AWS/'
                    hdu.header['FILENAME'] = str(raw_name00)
                    hdu.header['USERNAME'] = self.user_name
                    hdu.header ['USERID'] = self.user_id
                    hdu.header['REQNUM'] = '00000001'
                    hdu.header['BLKUID'] = 'None'
                    hdu.header['BLKSDATE'] = 'None'
                    hdu.header['MOLUID'] = 'None'
                    hdu.header['OBSTYPE'] = 'None'
                    try:    #NB relocate this to Expose entry area.  Fill out except.
                        im_path_r = self.camera_path
                        lng_path = self.lng_path
                        os.makedirs(im_path_r + g_dev['day'] + '/to_AWS/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/raw/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/calib/', exist_ok=True)
                        os.makedirs(im_path_r + g_dev['day'] + '/reduced/', exist_ok=True)
                        #print('Created:  ',im_path + g_dev['day'] + '\\to_AWS\\' )
                        im_path = im_path_r + g_dev['day'] + '/to_AWS/'
                        raw_path = im_path_r + g_dev['day'] + '/raw/'
                        cal_path = im_path_r + g_dev['day'] + '/calib/'
                        red_path = im_path_r + g_dev['day'] + '/reduced/'
                    except:
                        pass

                    text = open(im_path + text_name, 'w')  #This is always needed by AWS to set up database.
                    text.write(str(hdu.header))
                    text.close()
                    text_data_size = min(len(str(hdu.header)) - 4096, 2048)
                    paths = {'im_path':  im_path,
                             'raw_path':  raw_path,
                             'cal_path':  cal_path,
                             'red_path':  red_path,
                             'cal_name':  cal_name,
                             'raw_name00': raw_name00,
                             'red_name01': red_name01,
                             'i768sq_name10': i768sq_name,
                             'i768sq_name11': i768sq_name,
                             'jpeg_name10': jpeg_name,
                             'jpeg_name11': jpeg_name,
                             'text_name00': text_name,
                             'text_name10': text_name,
                             'text_name11': text_name,
                             'frame_type':  frame_type
                             }
                    if not quick and not script in ('True', 'true', 'On', 'on'):
                        self.enqueue_for_AWS(text_data_size, im_path, text_name)
                        self.to_reduce((paths, hdu))
                        hdu.writeto(raw_path + raw_name00, overwrite=True)
                    if script in ('True', 'true', 'On', 'on') or quick:
                        if not self.hint[0:54] == 'Flush':
                            hdu.writeto(cal_path + cal_name, overwrite=True)
                        else:
                            pass
                        try:
                            os.remove(self.camera_path + 'newest.fits')
                        except:
                            pass    #  print ("File newest.fits not found, this is probably OK")
                        result = {'patch': bi_mean,
                                'calc_sky': avg_ocn[7]}
                        return result#  Note we are not calibrating. Just saving the file.
                    print("\n\Finish-Exposure is complete, saved:  " + raw_name00)#, raw_data_size, '\n')
                    g_dev['obs'].update_status()
                    result['mean_focus'] = avg_foc[1]
                    result['mean_rotation'] = avg_rot[1]
                    result['FWHM'] = None
                    result['half_FD'] = None
                    result['patch'] = round(bi_mean, 1)
                    result['calc_sky'] = avg_ocn[7]
                    result['temperature'] = avg_foc[2]
                    result['gain'] = round(bi_mean/(avg_ocn[7]*exposure_time), 6)
                    result['filter'] = self.current_filter
                    return result
                except Exception as e:
                    print('Header assembly block failed: ', e)
                    try:
                        hdu = None
                    except:
                        pass
                    try:
                        hdu1 = None
                    except:
                        pass
                    self.t7 = time.time()
                    result = {'error': True}
                return result
            else:
                time.sleep(2)
                g_dev['obs'].update_status()
                self.t7 = time.time()
                remaining = round(self.completion_time - self.t7, 1)
                print("Exposure time remaining:", remaining)
                #it takes about 15 seconds from AWS to get here for a bias.
        # except Exception as e:
        #     breakpoint()
        #     counter += 1
        #     time.sleep(.01)
        #     print('Was waiting for exposure end, arriving here is bad news:  ', e)

        # result = {'error': True}
        # return  result
    def enqueue_for_AWS(self, priority, im_path, name):
        image = (im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)

    def to_reduce(self, to_red):
        print('Passed to to_reduce:  ', to_red[0], to_red[1].data.shape, to_red[1].header['FILTER'])
        g_dev['obs'].reduce_queue.put(to_red, block=False)


