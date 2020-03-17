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

from os.path import join, dirname, abspath

from skimage import data, io, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure
from skimage.io import imsave
import matplotlib.pyplot as plt 

from PIL import Image
from global_yard import g_dev
import ptr_config
import config_east as config
from devices.calibration import calibrate

import ptr_events

'''
Autofocus NOTE 20200122

As a general rule the focus is stable(temp).  So when code (re)starts, compute and go to that point(filter).

Nautical or astronomical dark, and time of last focus > 2 hours or delta-temp > ?1C, then schedule an 
autofocus.  Presumably system is near the bottom of the focus parabola, but it may not be.

Pick a ~7mag focus star at an Alt of about 60 degrees, generally in the South.  Later on we can start 
chosing and logging a range of altitudes so we can develop(temp, alt).

Take cental image, move in 1x and expose, move out 2x then in 1x and expose, solve the equation and
then finish with a check exposure.   

Now there are cases if for some reason telescope is not near the focus:  first the minimum is at one end
of a linear series.  From that series and the image diameters we can imply where the focus is, subject to
seeing induced errors.  If either case occurs, go to the projected point and try again.

A second case is the focus is WAY off, and or pointing.  Make appropriate adjustments and try again.

The third case is we have a minimum.  Inspection of the FWHM may imply seeing is poor.  In that case
double the exposure and possibly do a 5-point fit rather than a 3-point.

Note at the last exposure it is reasonable to do a minor recalibrate of the pointing.

Once we have fully automatic observing it might make sense to do a more full range test of the focus mechanism
and or visit more altitudes and temeperatures.

1) Implement mag 7 star selection including getting that star at center of rotation.

2) Implement using Sep to reliably find that star.


'''

        
class Camera:

    """ 
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """
    
    ###filter, focuser, rotator must be set up prior to camera.

    def __init__(self, driver: str, name: str, config_in):
        
        self.name = name

        g_dev['cam'] = self
        self.config = config_in
        win32com.client.pythoncom.CoInitialize()
        self.camera = win32com.client.Dispatch(driver)
        #self.camera = win32com.client.Dispatch('ASCOM.FLI.Kepler.Camera')
        #Need logic here if camera denies connection.
        print("Connecting to ASCOM camera:", driver)

        
        if driver[:5].lower() == 'ascom':
            print('ASCOM')
            time.sleep(1)
            self.camera.Connected = True
            self.description = "ASCOM"
            self.maxim = False
            self.ascom = True
            if self.camera.CanSetCCDTemperature:
                self.camera.SetCCDTemperature = -40.0
            self.camera.CoolerOn = True
            self.current_filter = 0
            print('Control is ASCOM camera driver.')

        else:

            self.camera.LinkEnabled = True
            self.description = 'MAXIM'
            self.maxim = True
            self.ascom = False
            self.camera.TemperatureSetpoint = -40.
            self.camera.CoolerOn = True
            self.current_filter = 0
            print('Control is Maxim camera interface.')
        self.exposure_busy = False
        self.cmd_in = None

        self.is_cmos = False
        #Set camera to a sensible default state -- this should ultimately be configuration settings 
        self.camera_model = "FLI Microline e2v DD U42"
        self.camera.Binx = 1     #Kepler 400 does not accept a bin??
        self.camera.BinY = 1
        self.cameraXSize = self.camera.CameraXSize  #unbinned
        self.cameraYSize = self.camera.CameraYSize  #unbinned
        self.cameraMaxXBin = self.camera.MaxBinX
        self.cameraMaxYBin = self.camera.MaxBinY
        self.camera.StartX = 0
        self.camera.StartY = 0
        self.camera.NumX = 2048
        self.camera.Numy = 2048
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
        #self.camera.SetupDialog()
     
                
        
    def get_status(self):
        #status = {"type":"camera"}
        status = {}
        if self.exposure_busy:
            status['busy_lock'] = 'true'
        else:
            status['busy_lock'] = 'false'
        if self.maxim:
            cam_stat = 'unknown' #self.camera.CameraState
        if self.ascom:
            cam_stat = 'unknown' #self.camera.CameraState
        status['status'] = str(cam_stat)  #The state could be expanded to be more meaningful.
#        if self.maxim:
#            status['ccd_temperature'] = str(round(self.camera.Temperature , 3))
#        if self.ascom:
#            status['ccd_temperature'] = str(round(self.camera.CCDTemperature , 3))
            



    def parse_command(self, command):
        print("Camera Command incoming:  ", command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        

        if action == "expose" and not self.exposure_busy :
            self.expose_command(req, opt, do_sep=False, quick=False)
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

    def expose_command(self, required_params, optional_params, p_next_filter=None, p_next_focus=None, p_dither=False, \
                       gather_status = True, do_sep=False, no_AWS=False, quick=False, halt=False):
        ''' 
        Apply settings and start an exposure. 
        Quick=True is meant to be fast.  We assume the ASCOM imageBuffer is the source of data, not the Files path.
        '''
        print('Expose Entered.  req:  ', required_params, 'opt:  ', optional_params)
        
        bin_x = optional_params.get('bin', '1,1')
        if bin_x == '2,2':
            bin_x = 2
        else:
            bin_x = 1
        bin_y = bin_x   #NB This needs fixing
        gain = optional_params.get('gain', 1)
        exposure_time = float(required_params.get('time', 5))
        #exposure_time = max(0.2, exposure_time)  #Saves the shutter, this needs qualify with imtype.
        imtype= required_params.get('image_type', 'Light')    

        count = int(optional_params.get('count', 1))
        if count < 1:
            count = 1   #Hence repeat does not repeat unless > 1


        #NBNB Changing filter may cause a need to shift focus
        self.current_offset = 6300#g_dev['fil'].filter_offset  #TEMP
        sub_frame_fraction = optional_params.get('subframe', None)
        if imtype.lower() == 'light' or imtype.lower() == 'screen flat' or imtype.lower() == 'sky flat' or imtype.lower() == \
                             'experimental' or imtype.lower() == 'toss' :
                                 #here we might eventually turn on spectrograph lamps as needed for the imtype.
            imtypeb = True    #imtypeb passed to open the shutter.
            frame_type = imtype.lower()
            do_sep = True
            if imtype.lower() == 'screen_flat' or imtype.lower() == 'sky flat' or imtype.lower() == 'guick':
                do_sep = False
        elif imtype.lower() == 'bias':
                exposure_time = 0.0
                imtypeb = False
                frame_type = 'bias'
                no_AWS = False
                do_sep = False
                #Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'dark':
                imtypeb = False
                frame_type = 'dark'
                no_AWS = False
                do_sep = False
                #Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'screen_flat' or imtype.lower() == 'sky flat':
            do_sep = False
        elif imtype.lower() == 'quick':
            quick=True
            no_AWS = False   #Send only a JPEG
            do_sep = False
            imtypeb = True
            frame_type = 'light'
        else:
            imtypeb = True
            do_sep = True
        #NBNB This area still needs work to cleanly define shutter, calibration, sep and AWS actions.

        area = optional_params.get('size', 100)
        if area == None: area = 100
        sub_frame_fraction = optional_params.get('subframe', None)                
        try:
            if type(area) == str and area[-1] =='%':
                area = int(area[0:-1])
        except:
            area = 100
        if bin_y == 0 or self.cameraMaxXBin != self.cameraMaxYBin:
            self.bin_x = min(bin_x, self.cameraMaxXBin)
            self.cameraBinX = self.bin_x 
            self.bin_y = min(bin_x, self.cameraMaxYBin)
            self.cameraBinY = self.bin_y
        else:
            self.bin_x = min(bin_x, self.cameraMaxXBin)
            self.cameraBinx = self.bin_x
            self.bin_y = min(bin_y, self.cameraMaxYBin)
            self.cameraBinY = self.bin_y
        self.len_x = 4096#self.camera.CameraXSize//self.bin_x
        self.len_y = 4096#self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
        self.len_xs = 4096#self.len_x - 50   #THIS IS A HACK
        #print(self.len_x, self.len_y)
        
        #"area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg']
        if type(area) == str and area.lower() == "1x-jpg":
            self.cameraNumX = 768
            self.cameraStartX = 1659
            self.cameraNumY = 768
            self.cameraStartY = 1659
            self.area = 37.5
        elif type(area) == str and area.lower() == "2x-jpg":
            self.cameraNumX = 1536
            self.cameraStartX = 1280
            self.cameraNumY = 1536
            self.cameraStartY = 1280
            self.area = 75
        elif type(area) == str and area.lower() == "1/2 jpg":
            self.cameraNumX = 384
            self.cameraStartX = 832
            self.cameraNumY = 384
            self.cameraStartY = 832
            self.area = 18.75
        elif type(area) == str:     #Just defalut to a small area.
            self.cameraNumX = self.len_x//4
            self.cameraStartX = int(self.len_xs/2.667)
            self.cameraNumY = self.len_y//4
            self.cameraStartY = int(self.len_y/2.667)
            self.area = 100
        elif 72 < area <= 100:
            self.cameraNumX = self.len_x
            self.cameraStartX = 0
            self.cameraNumY = self.len_y
            self.cameraStartY = 0
            self.area = 100
        elif 70 <= area <= 72:
            self.cameraNumX = int(self.len_xs/1.4142)
            self.cameraStartX = int(self.len_xs/6.827)
            self.cameraNumY = int(self.len_y/1.4142)
            self.cameraStartY = int(self.len_y/6.827)
            self.area = 71       
        elif area == 50:
            self.cameraNumX = self.len_xs//2
            self.cameraStartX = self.len_xs//4
            self.cameraNumY = self.len_y//2
            self.cameraStartY = self.len_y//4
            self.area = 50
        elif 33 <= area <= 35:
            self.cameraNumX = int(self.len_xs/2.829)
            self.cameraStartX = int(self.len_xs/3.093)
            self.cameraNumY = int(self.len_y/2.829)
            self.cameraStartY = int(self.len_y/3.093)
            self.area = 33
        elif area == 25:
            self.cameraNumX = self.len_xs//4
            self.cameraStartX = int(self.len_xs/2.667)
            self.cameraNumY = self.len_y//4
            self.cameraStartY = int(self.len_y/2.667)
            self.area = 25
        else:
            self.cameraNumX = self.len_x
            self.cameraStartX = 0
            self.cameraNumY = self.len_y
            self.cameraStartY = 0
            self.area = 100
            print("Defult area used. 100%")
            
        #Next apply any subframe setting here.  Be very careful to keep fractional specs and pixel values disinguished.
        if self.area == self.previous_area and sub_frame_fraction is not None and \
                        (sub_frame_fraction['definedOnThisFile'] != self.previous_image_name):
            sub_frame_fraction_xw = abs(sub_frame_fraction['x1'] - sub_frame_fraction['x0'])
            if sub_frame_fraction_xw < 1/32.:
                sub_frame_fraction_xw = 1/32.
            else:
                pass   #Adjust to center position of sub-size frame
            sub_frame_fraction_yw = abs(sub_frame_fraction['y1'] - sub_frame_fraction['y0'])
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
            dist_x = int(self.previous_start_x + self.previous_num_x*sub_frame_fraction_x)
            dist_y = int(self.previous_start_y +self.previous_num_y*sub_frame_fraction_y)
            self.cameraStartX= dist_x
            self.cameraStartY= dist_y 
            self.cameraNumX= num_x 
            self.cameraNumY= num_y
            self.previous_image_name = sub_frame_fraction['definedOnThisFile']
            self.previous_start_x = dist_x
            self.previous_start_y = dist_y
            self.previous_num_x = num_x
            self.previous_num_y = num_y
            self.bpt_flag = False
        elif self.area == self.previous_area and sub_frame_fraction is not None and \
                          (sub_frame_fraction['definedOnThisFile'] == self.previous_image_name):         
            #Here we repeat the previous subframe and do not re-enter and make smaller
            self.cameraStartX = self.previous_start_x
            self.cameraStartY = self.previous_start_y
            dist_x = self.previous_start_x
            dist_y = self.previous_start_y
            self.cameraNumX= self.previous_num_x 
            self.cameraNumY= self.previous_num_y
            self.bpt_flag  = True
        
        elif sub_frame_fraction is None: 
            self.previous_start_x = self.cameraStartX  #These are the subframe values for the new area exposure.
            self.previous_start_y = self.cameraStartY
            dist_x = self.previous_start_x 
            dist_y = self.previous_start_y 
            self.previous_num_x = self.cameraNumX
            self.previous_num_y = self.cameraNumY
            self.previous_num_fraction_x = 1.0
            self.previous_num_fraction_y = 1.0
            self.previous_area = self.area
            self.bpt_flag = False          
            

       #print(self.camera.NumX, self.camera.StartX, self.camera.NumY, self.camera.StartY)
        for seq in range(count):
            #SEQ is the outer repeat count loop.
            if seq > 0: 
                g_dev['obs'].update_status()
#            if self.current_filter == 'u':
#                bolt = [ 'O3', 'HA', 'N2', 'S2', 'ContR', 'zs', 'u']
#                ptr_events.flat_spot_now(go=True)
#            elif self.current_filter == 'PL':
#                bolt = [ 'PR', 'PG', 'PB', 'PL']
#            elif self.current_filter == 'g':
#                bolt = [ 'r', 'i', 'zs', 'u', 'w', 'g']
#            else:
            bolt = [self.current_filter]
                
            for fil in bolt:  # 'N2', 'S2', 'CR']: #range(1)                
             
                filter_req = {'filter_name': str(fil)}
                filter_opt = {}


                for rpt in range(1):
                    #Repeat that filter rpt-times
                    #print('\n   REPEAT REPEAT REPEAT:  ', rpt, '\n')
                    self.pre_mnt = []
                    self.pre_rot = []
                    self.pre_foc = []
                    self.pre_ocn = []
                    try:
                        #print("starting exposure, area =  ", self.area)
                        #NB NB Ultimately we need to be a thread.
                        pass
                        #Check here for filter, guider, still moving  THIS IS A CLASSIC case where a timeout is a smart idea.
                        #                           g_dev['mnt'].mount.Slewing or \

                        self.t1 = time.time()
                        #Used to inform fits header where telescope is for scripts like screens.
                        #g_dev['ocn'].get_quick_status(self.pre_ocn)
                        #g_dev['mnt'].get_quick_status(self.pre_mnt)  #stage two quick_get_'s symmetric around exposure
                        self.exposure_busy = True                       
                        print('First Entry', self.camera.StartX, self.camera.StartY, self.camera.NumX, self.camera.NumY, exposure_time)
                        if self.ascom and self.is_cmos:
                            breakpoint()
#                            try:
#                                ldr_handle= glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['next_day'] + '\\' + '*low.fits')
#                                ldr_handle_high= glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['next_day'] + '\\' + '*high.fits')
#                            except:
#                                print("Something went wrong reading in a version of low / or high.fits")
#                            if ldr_handle == [] or ldr_handle_high == []:
#                                try:
#                                    ldr_handle = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['d-a-y'] + '\\' + '*low.fits')
#                                    ldr_handle_high = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['d-a-y'] + '\\' + '*high.fits')
#                                except:
#                                    print("Something went wrong reading in a version of low / or high.fits")  
#                            if len(ldr_handle_high) > 0:
#                                for item in ldr_handle_high:
#                                    os.remove(item)
#                            if len(ldr_handle) > 0:
#                                for item in ldr_handle:
#                                    os.remove(item)
#
#                            self.camera.AbortExposure()
#                            self.t2 = time.time()       #Immediately before Exposure
#                            self.camera.StartExposure(exposure_time, imtypeb)     #True indicates Light Frame.  Maxim Difference of code
                        if self.maxim and self.is_cmos:
                            breakpoint()
#                            #This code grooms away older unuseable raw Kepler 12 bit images, presuming they exist and deals
#                            #With oddities of directory naming by FliCam Server.
#                            try:
#                                ldr_handle = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['next_day'] + '\\' + '*low.fits')
#                                ldr_handle_high = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['next_day'] + '\\' + '*high.fits')
#                            except:
#                                print("Something went wrong reading in a version of low / or high.fits")
#                            if ldr_handle == [] or ldr_handle_high == []:
#                                try:
#                                    ldr_handle = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['d-a-y'] + '\\' + '*low.fits')
#                                    ldr_handle_high = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['d-a-y'] + '\\' + '*high.fits')
#                                except:
#                                    print("Something went wrong reading in a version of low / or high.fits")  
#                            if len(ldr_handle_high) > 0:
#                                new_list = []
#                                for item in ldr_handle_high:
#                                    new_list.append( (os.stat(item).st_mtime, item))
#                                new_list.sort()
#                                ldr_handle_high_time = new_list[-1][0]
#                                    #os.remove(item)
#                                    #pass
#                            else:
#                                ldr_handle_high_time = time.time()
#                            if len(ldr_handle) > 0:
#
#                                new_list = []
#                                for item in ldr_handle:
#                                    new_list.append( (os.stat(item).st_mtime, item))
#                                new_list.sort()
#                                ldr_handle_time = new_list[-1][0]
#                                    #os.remove(item)
#                                    #pass
#                            else:
#                                ldr_handle_time = time.time()
#                            print('Link Enable:  ', self.camera.LinkEnabled)
#                            self.camera.AbortExposure()
#                            g_dev['ocn'].get_quick_status(self.pre_ocn)
#                            g_dev['foc'].get_quick_status(self.pre_foc)
#                            g_dev['rot'].get_quick_status(self.pre_rot)
#                            g_dev['mnt'].get_quick_status(self.pre_mnt)
#                            self.t2 = time.time()
#                            print("Starting exposure at:  ", self.t2)
#                            self.camera.Expose(exposure_time, imtypeb)
                        elif self.ascom:
                            breakpoint()
#                            self.camera.AbortExposure()
#                            g_dev['ocn'].get_quick_status(self.pre_ocn)
#                            g_dev['foc'].get_quick_status(self.pre_foc)
#                            g_dev['rot'].get_quick_status(self.pre_rot)
#                            g_dev['mnt'].get_quick_status(self.pre_mnt)
#                            self.t2 = time.time()       #Immediately before Exposure
#                            self.camera.StartExposure(exposure_time, imtypeb) 
#                            
                        elif self.maxim:
                            print('Link Enable:  ', self.camera.LinkEnabled)
                            self.camera.AbortExposure()
                            g_dev['ocn'].get_quick_status(self.pre_ocn)
                            g_dev['foc'].get_quick_status(self.pre_foc)
                            g_dev['rot'].get_quick_status(self.pre_rot)
                            g_dev['mnt'].get_quick_status(self.pre_mnt)
                            self.t2 = time.time()
                            print("Starting exposure at:  ", self.t2)
                            self.camera.Expose(exposure_time, imtypeb)
                            ldr_handle_time = None
                            ldr_handle_high_time = None
                        else:
                            print("Something terribly wrong, driver not recognized.!")
                        self.t9 = time.time()
                        #We go here to keep this subroutine a reasonable length.
                        result = self.finish_exposure(exposure_time,  frame_type, count - seq, p_next_filter, p_next_focus, p_dither, \
                                             gather_status, do_sep, no_AWS, dist_x, dist_y, quick=quick, halt=halt, low=ldr_handle_time, \
                                             high=ldr_handle_high_time)
                        self.exposure_busy = False
                        self.t10 = time.time()
                        
                        ##NB NB NB Should there be a return here?
                        
                        #self.exposure_busy = False  Need to be able to do repeats
                    except Exception as e:
                        print("failed exposure")
                        print(e)
                        self.t11 = time.time()
                        return None  #Presumably this premature return cleans things out so they can still run?
        self.t11 = time.time()
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
        self.camera.AbortExposure()
        self.exposure_busy = False

        # Alternative: self.camera.StopExposure() will stop the exposure and 
        # initiate the readout process. 
        


    ###############################
    #       Helper Methods        #
    ###############################
    
    def finish_exposure(self, exposure_time, frame_type, counter, p_next_filter=None, p_next_focus=None, p_dither=False, \
                        gather_status=True, do_sep=False, no_AWS=False, start_x=None, start_y=None, quick=False, halt=False, \
                        low=0, high=0):
        #print("Finish exposure Entered:  ", self.af_step, exposure_time, frame_type, counter, ' to go!')
        print("Finish exposure Entered:  ", exposure_time, frame_type, counter, p_next_filter, p_next_focus, p_dither, \
                        gather_status, do_sep, no_AWS, start_x, start_y)
        if self.bpt_flag:
            pass
        if gather_status:   #Does this need to be here
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []
        counter = 0
        while True:     #THis is where we should have an outer timeout system
            try:
                if self.maxim and self.camera.ImageReady: #and not self.img_available and self.exposing:
                    self.t4 = time.time()
                   
                    if not quick and gather_status:
                        g_dev['mnt'].get_quick_status(self.post_mnt)  #stage symmetric around exposure
                        g_dev['rot'].get_quick_status(self.post_rot)
                        g_dev['foc'].get_quick_status(self.post_foc)
                        g_dev['ocn'].get_quick_status(self.post_ocn)
                    self.t5 = time.time()
                    ###Here is the place to potentially pipeline dithers, next filter, focus, etc.
#                    if p_next_filter is not None:
#                        print("Post image filter seek here")
#                    if p_next_focus is not None:
#                        print("Post Image focus seek here")
#                    if p_dither == True:
#                        print("Post image dither step here")
                    self.t6 = time.time()
                    self.img = self.camera.ImageArray
                    self.t7 = time.time()
                    #Save image with Maxim Header information, then read back with astropy and use the
                    #lqtter code for fits manipulation.
                    #This should be a very fast disk.
                    self.camera.SaveImage('Q:\\archive\\kf01\\newest.fits')#, overwrite=True)
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
                        hdu1 =  fits.open('Q:\\archive\\kf01\\newest.fits')
                        hdu = hdu1[0]
                        hdu.header['BUNIT']    = 'adu'
                        hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))   
                        hdu.header['EXPTIME']  = exposure_time   #This is the exposure in seconds specified by the user                  
                        hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times                    
                        hdu.header['FILTER ']  = self.current_filter
                        hdu.header['FILTEROF']  = self.current_offset
                        if g_dev['scr'] is not None and g_dev['scr'].dark_setting == 'Light':
                            hdu.header['SCREEN'] = g_dev['scr'].bright_setting
                        hdu.header['IMAGETYP'] = 'Light Frame'   #This report is fixed and it should vary...NEEDS FIXING!
                        if self.maxim:
                            hdu.header['SET-TEMP'] = round(self.camera.TemperatureSetpoint, 3)                 
                            hdu.header['CCD-TEMP'] = round(self.camera.Temperature, 3)
                        if self.ascom:
                            hdu.header['SET-TEMP'] = round(self.camera.SetCCDTemperature, 3)                 
                            hdu.header['CCD-TEMP'] = round(self.camera.CCDTemperature, 3)
                        hdu.header['XPIXSZ']   = self.camera.PixelSizeX      #Should this adjust with binning?
                        hdu.header['YPIXSZ']   = self.camera.PixelSizeY          
                        try:
                            hdu.header['XBINING'] = self.camera.BinX                      
                            hdu.header['YBINING'] = self.camera.BinY 
                        except:
                            hdu.header['XBINING'] = 1                       
                            hdu.header['YBINING'] = 1
                        hdu.header['CCDSUM'] = '1 1'  
                        hdu.header['XORGSUBF'] = 768     #This makes little sense to fix...  NB ALL NEEDS TO COME FROM CONFIG!!   
                        hdu.header['YORGSUBF'] = 768           
                        hdu.header['READOUTM'] = 'Monochrome'                                                         
                        hdu.header['TELESCOP'] = 'PlaneWave CDK 500mm'
                        hdu.header['FOCAL'] = 3500.
                        hdu.header['APR-DIA']   = 500.          
                        hdu.header['APR-AREA']  = 128618.8174364                       
                        hdu.header['SITELAT']  = 34.34293028            
                        hdu.header['SITE-LNG'] = -119.68105
                        hdu.header['SITE-ELV'] = 317.75
                        hdu.header['MPC-CODE'] = 'vz123'              
                        hdu.header['JD-START'] = 'bogus'       # Julian Date at start of exposure               
                        hdu.header['JD-HELIO'] = 'bogus'       # Heliocentric Julian Date at exposure midpoint
                        hdu.header['OBJECT']   = ''
                        hdu.header['SID-TIME'] = self.pre_mnt[3]
                        hdu.header['OBJCTRA']  = self.pre_mnt[1]
                        hdu.header['OBJCTDEC'] = self.pre_mnt[2]
                        hdu.header['OBRARATE'] = self.pre_mnt[4]
                        hdu.header['OBDECRAT']  = self.pre_mnt[5]                                                       
                        hdu.header['TELESCOP'] = 'PW 0m45 CDK'          
                        hdu.header['INSTRUME'] = 'FLI4040 CMOS USB3'                                                      
                        hdu.header['OBSERVER'] = 'WER DEV'                                                            
                        hdu.header['NOTE']    = 'Bring up Images'                                                     
                        hdu.header['FLIPSTAT'] = 'None'  
                        hdu.header['SEQCOUNT'] = int(counter)
                        hdu.header['DITHER']   = 0
                        hdu.header['IMGTYPE']  = frame_type
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
        
                        hdu.header['DETECTOR'] = "Kodak 16803"
                        hdu.header['CAMNAME'] = 'df01'
                        hdu.header['CAMMANUF'] = 'Finger Lakes Instrumentation'
    #                        try:
    #                            hdu.header['GAIN'] = g_dev['cam'].camera.gain
                        #print('Gain was read;  ', g_dev['cam'].camera.gain)
    #                        except:                                
    #                            hdu.header['GAIN'] = 1.18
                        hdu.header['GAINUNIT'] = 'e-/ADU'
                        hdu.header['GAIN'] = 1.2   #20190911   LDR-LDC mode set in ascom
                        hdu.header['RDNOISE'] = 8
                        hdu.header['CMOSCAM'] = False
                        #hdu.header['CMOSMODE'] = 'HDR-HDC'  #Need to figure out how to read this from setup.
                        hdu.header['SATURATE'] = 60000
                        hdu.header['PIXSCALE'] = 0.85*self.camera.BinX
    
                        #Need to assemble a complete header here
                        #hdu1.writeto('Q:\\archive\\ea03\\new2b.fits')#, overwrite=True)
                        alias1 = self.config['camera']['camera1']['alias']
                        im_type = 'EX'   #or EN for engineering....
                        f_ext = ""
#                        if frame_type[-4:] == 'flat':
#                            f_ext = '-' + self.current_filter    #Append flat string to local image name
                        next_seq = ptr_config.next_seq(alias1)
#                        cal_name = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + f_ext + '-'  + \
#                                                       im_type + '01.fits'
                        raw_name00 = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '00.fits'
                        raw_name01 = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '01.fits'
                        #Cal_ and raw_ names are confusing
                        db_name = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '13.fits'
                        jpeg_name = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '13.jpg'
                        text_name = self.config['site'] + '-' + alias1 + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '01.txt'
                        im_path_r = 'Q:\\archive\\' + alias1 +'\\'
                        lng_path = im_path_r + 'lng\\'
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
                            
                            os.makedirs(im_path_r + g_dev['day'] + '\\to_AWS\\', exist_ok=True)
                            os.makedirs(im_path_r + g_dev['day'] + '\\raw\\', exist_ok=True)
                            os.makedirs(im_path_r + g_dev['day'] + '\\calib\\', exist_ok=True)
                            #print('Created:  ',im_path + g_dev['day'] + '\\to_AWS\\' )
                            im_path = im_path_r + g_dev['day'] + '\\to_AWS\\'
                            raw_path = im_path_r + g_dev['day'] + '\\raw\\'
                            cal_path = im_path_r + g_dev['day'] + '\\calib\\'
                        except:
                            pass
                        
                        text = open(im_path + text_name, 'w')  #This is always needed by AWS to set up database.
                        text.write(str(hdu.header))
                        text.close()
                        text_data_size = len(str(hdu.header)) - 4096                        
                        if not quick:
                            hdu.writeto(raw_path + raw_name00, overwrite=True)
                            #hdu.close()
                        #raw_data_size = hdu.data.size
    
                        print("\n\Finish-Exposure is complete:  " + raw_name00)#, raw_data_size, '\n')
    
                        calibrate(hdu, None, lng_path, frame_type, start_x=start_x, start_y=start_y, quick=quick)
                        #Note we may be using different files if calibrate is null.
                        if not quick:
                            hdu1.writeto(im_path + raw_name01, overwrite=True)
                        do_sep = True
                        raw_data_size = hdu1[0].data.size
                        if do_sep:
                            try:
                                img = hdu.data.copy().astype('float')
                                bkg = sep.Background(img)
                                #bkg_rms = bkg.rms()
                                img -= bkg
                                sources = sep.extract(img, 7, err=1, minarea=30)#, filter_kernel=kern)
                                sources.sort(order = 'cflux')
                                print('No. of detections:  ', len(sources))
                                result = []
                                spots = []
                                for source in sources:
                                    a0 = source['a']
                                    b0 =  source['b']
                                    if (a0 - b0)/(a0 + b0)/2 > 0.1:    #This seems problematic and should reject if peak > saturation
                                        continue
                                    r0 = round(math.sqrt(a0**2 + b0**2), 2)
                                    result.append((round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), \
                                                   round(r0), 2))
                            
                                    spots.append(round((r0), 2))
                                spot = np.array(spots)
                                
                                try:
                                    spot = np.median(spot[int(len(spot)*0.5):int(len(spot)*0.75)])
                                    print(result, '\n', 'Spot and flux:  ', spot, source['cflux'], len(sources), avg_foc[1], '\n')
                                    if len(result) < 5:
                                        spot = None
                                except:
                                    pass
                            except:
                                spot = None
                        if halt: pass
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
                        if in_shape[0] < in_shape[1]:
                            diff = int(abs(in_shape[1] - in_shape[0])/2)
                            in_max = int(hdu.data.max()*0.8)
                            in_min = int(hdu.data.min() - 2)   
                            if in_min < 0: 
                                in_min = 0
                            new_img = np. zeros((in_shape[1], in_shape[1]))    #new square array
                            new_img[0:diff - 1, :] = in_min
                            new_img[diff-1, :] = in_max
                            new_img[diff:(diff + in_shape[0]), :]
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
                            new_img[:, diff:(diff + in_shape[1])]
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
                        if not no_AWS:                        
                            self.enqueue_image(text_data_size, im_path, text_name)
                            self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                            if not quick:
                                self.enqueue_image(db_data_size, im_path, db_name)
                                self.enqueue_image(raw_data_size, im_path, raw_name01)
                            print('Sent to AWS Queue.')
                        self.img = None
                        #hdu.close()
                        hdu = None
    #                        try:
    #                            'Q:\\archive\\' + 'gf03'+ '\\newest.fits'
    #                            'Q:\\archive\\' + 'gf03'+ '\\newest_low.fits'
    #                        except:
    #                            print(' 2 Could not remove newest.fits.')
                        print('Returning #1:  ', spot, avg_foc[1] )
                        return (spot, avg_foc[1])
                    except:   
                        print('Header assembly block failed.')
                        self.t7 = time.time()
    
                    return (None ,None)
                else:               #here we are in waiting for imageReady loop and could send status and check Queue
                    time.sleep(.3)                    
                    #if not quick:
                    #   g_dev['obs'].update()    #This keeps status alive while camera is loopin
                    self.t7= time.time()
                    print("Basic camera file wait loop loop expired")
                    #it takes about 15 seconds from AWS to get here for a bias.
            except:
                counter += 1
                time.sleep(.01)
                #This shouldbe counted down for a loop cancel.
                print('Wait for exposure end, but getting here is bad.')
                return (None, None)

        #definitely try to clean up any messes.
        try:
            hdu.close()
            hdu = None
        except:
            pass
        try:
            hdu1.close()
            hdu1 = None
        except:
            pass

        self.t8 = time.time()
        print('Returning #2:  ', spot, avg_foc[1] )
        return (spot, avg_foc[1])
            
    def enqueue_image(self, priority, im_path, name):
        image = (im_path, name)
        #print("stuffing Queue:  ", priority, im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)

