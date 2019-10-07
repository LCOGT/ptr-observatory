import win32com.client
import pythoncom
import time
import datetime
import os
import math
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.utils.data import get_pkg_data_filename
import sep

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
#import ptr_events
#import api_calls
#import requests

#import ptr_bz2

'''
TO DO

Simplify this routine to exposing, and write image in a well known place.
Prior to exposure, verify mount not slewing, etc -- wait before starting (with a timeout)
then expose.  The central question is does the expose method have a count?  If so we need
sequence numbers.

Next do we calibrate every time and modify the calibration steps as needed.  Last do we solve for sources?

AS a general rule in-line is faster, but only do what is needed.

If bias, no calib, just a long sequence
if dark, only bias
if flat, only bias and dark

if light, BD, F if available, then hotpix if avail.
SEP is the AF optimized version. (no sat, median of values of FWHM.)

Re- move AF logic from the expose code.


OLD TO DO
Annotate fits, incl Wx conditions, other devices
Fix fits to be strictly 80 character records with proper justifications.
Jpeg

Timeout
Power cycle Reset
repeat, then execute blocks     command( [(exposure, bin/area, filter, dither, co-add), ( ...)}, repeat)  co-adds send jpegs
    only for each frame and a DB for the sum.
    
dither
autofocus
bias/dark +screens, skyflats
'''
def imageStats(img_img, loud=False):
    axis1 = 1536
    axis2 = 1536
    subAxis1 = axis1/2
    patchHalf1 = axis1/10
    subAxis2 = axis2/2
    patchHalf2 = axis2/10
    sub_img = img_img[int(subAxis1 - patchHalf1):int(subAxis1 + patchHalf1), int(subAxis2 - patchHalf2):int(subAxis2 + patchHalf2) ]
    img_mean = sub_img.mean()
    img_std = sub_img.std()
    #ADD Mode here someday.
    if loud: print('Mean, std:  ', img_mean, img_std)
    return round(img_mean, 2), round(img_std, 2)

def median8(img, hot_pix):
    #print('1: ',img_img.data)
    axis1 = 1536
    axis2 = 1536

    img = img
    for pix in range(len(hot_pix[0])):
        iy = hot_pix[0][pix]
        ix = hot_pix[1][pix]
        if (0 < iy < axis1 - 1) and (0 < ix < axis2 - 1):
            med = []
            med.append(img[iy-1][ix-1])
            med.append(img[iy-1][ix])
            med.append(img[iy-1][ix+1])
            med.append(img[iy+1][ix-1])
            med.append(img[iy+1][ix])
            med.append(img[iy+1][ix+1])
            med.append(img[iy][ix-1])
            med.append(img[iy][ix+1])
            med = np.median(np.array(med))
            #print('2: ', iy, ix, img[iy][ix], med)
            img[iy][ix] = med
        #This can be slightly improved by edge and corner treatments.
        #There may be an OOB condition.
    return

def simpleColumnFix(img, col):
    fcol = col - 1
    acol = col + 1
    img[:,col] = (img[:,fcol] + img[:,acol])/2
    img = img.astype(np.uint16)
    return img


super_bias = None
super_dark_15 = None
super_dark_30 = None
super_dark_60 = None
super_dark_300 = None
hotmap_300 = None
hotpix_300 = None
super_flat_w = None
super_flat_HA = None

#This is a brute force linear version. This needs to be more sophisticated and camera independent.

def calibrate (hdu, lng_path, frame_type='light'):
    #These variables are gloal in the sense they persist between calls (memoized in a form)
    global super_bias, super_dark_15, super_dark_30, super_dark_60, super_dark_300, \
           super_flat_w, super_flat_HA, hotmap_300, hotpix_300
    loud = True
    if super_bias is None:
        try:
            sbHdu = fits.open(lng_path + 'ldr_mb_1.fits')
            super_bias = sbHdu[0].data#.astype('float32')
            sbHdu.close()
            quick_bias = True
            if loud: print(lng_path + 'ldr_mb_1.fits', 'Loaded')
        except:
            quick_bias = False
            print('WARN: No Bias Loaded.')
#    if super_dark_15 is None:
#        try:
#            sdHdu = fits.open(lng_path + 'ldr_md_15.fits')
#            dark_15_exposure_level = sdHdu[0].header['EXPTIME']
#            super_dark_15  = sdHdu[0].data.astype('float32')
#            sdHdu.close()
#            quick_dark_15 = True
#            print(lng_path + 'ldr_md_15.fits', 'Loaded')
#        except:
#            quick_dark_15 = False
#            print('WARN: No dark Loaded.')
#    if super_dark_30 is None:
#        try:
#            sdHdu = fits.open(lng_path + 'ldr_md_30.fits')
#            dark_30_exposure_level = sdHdu[0].header['EXPTIME']
#            super_dark_30  = sdHdu[0].data.astype('float32')
#            sdHdu.close()
#            quick_dark_30 = True
#            print(lng_path + 'ldr_md_30.fits', 'Loaded')
#        except:
#            quick_dark_30 = False
#            print('WARN: No dark Loaded.')
#    if super_dark_60 is None:
#        try:
#            sdHdu = fits.open(lng_path + 'ldr_md_60.fits')
#            dark_60_exposure_level = sdHdu[0].header['EXPTIME']
#            super_dark_60  = sdHdu[0].data.astype('float32')
#            sdHdu.close()
#            quick_dark_60 = True
#            print(lng_path + 'ldr_md_60.fits', 'Loaded')
#        except:
#            quick_dark_60 = False
#            print('WARN: No dark Loaded.')
    if super_dark_300 is None:
        try:
            sdHdu = fits.open(lng_path + 'ldr_md_1_300.fits')
            dark_300_exposure_level = sdHdu[0].header['EXPTIME']
            super_dark_300  = sdHdu[0].data#.astype('float32')
            sdHdu.close()
            quick_dark_300 = True
            print(lng_path + 'ldr_md_120.fits', 'Loaded')
        except:
            quick_dark_300 = False
            print('WARN: No dark Loaded.')
    #Note on flats the case is carried through
    if super_flat_w is None:
        try:
            sfHdu = fits.open(lng_path + 'ldr_mf_1_w.fits')
            super_flat_w = sfHdu[0].data.astype('float32')
            quick_flat_w = True
            sfHdu.close()
            if loud: print(lng_path + 'ldr_mf_1_w.fits', 'Loaded')
        except:
            quick_flat_w = False
            print('WARN: No W Flat/Lum Loaded.')
    if super_flat_HA is None:
        try:
            sfHdu = fits.open(lng_path + 'ldr_mf_1_1_HA.fits')
            super_flat_HA = sfHdu[0].data#.astype('float32')
            quick_flat_HA = True
            sfHdu.close()
            if loud: print(lng_path + 'ldr_mf_1_HA.fits', 'Loaded')
        except:
            quick_flat_HA = False
            print('WARN: No HA Flat/Lum Loaded.')
#    if coldmap_120 is None:
#        try:
#            shHdu = fits.open(lng_path + 'ldr_coldmap_1_120.fits')
#            coldmap_120 = shHdu[0].data.astype('uint16')
#            shHdu.close()
#            quick_coldmap_120 = True
#            coldpix_120 = np.where(coldmap_120 > 0)   # 0 vs 1, see hotsection below?
#            print(lng_path + 'ldr_coldmap_1_120.fits', 'Loaded, Lenght = ', len(coldpix_120[0]))
#        except:
#            quick_coldmap_120 = False
#            print('coldmap_120 failed to load.')
    if hotmap_300 is None:
        try:
            shHdu = fits.open(lng_path + 'ldr_hotmap_1_120.fits')
            hotmap_300 = shHdu[0].data#.astype('uint16')
            shHdu.close()
            quick_hotmap_300 = True
            hotpix_300 = np.where(hotmap_300 > 1)  #This is a temp simplifcation
            print(lng_path + 'ldr_hotmap_1_120.fits', 'Loaded, Lenght = ', len(hotpix_300[0]))
        except:
            quick_hotmap_300= False
            print('Hotmap_120 failed to load.')
            
    #Here we actually calibrate
    while True:   #Use break to drop through to exit.  i.e., do not calibrte frames we are acquring for calibration.
        cal_string = ''
        img = hdu.data
        if loud: print('InputImage')
        imageStats(img, loud)
        #breakpoint()
        if frame_type == 'bias': break
        if super_bias is not None:
            img = img - super_bias
            if loud: print('QuickBias result:  ')
            imageStats(img, loud)
            cal_string += 'B'
        data_exposure_level = hdu.header['EXPTIME']
        if frame_type == 'dark': 
            break
        do_dark = True
#        if data_exposure_level <= 15:
#            s_dark = super_dark_15
#            d_exp = 15.
#            h_map = hotmap_60
#            h_pix = hotpix_60
#        elif data_exposure_level <= 30:
#            s_dark = super_dark_30
#            d_exp = 30.
#            h_map = hotmap_60
#            h_pix = hotpix_60
#        elif data_exposure_level <= 60:
#            s_dark = super_dark_60
#            d_exp = 60.
#            h_map = hotmap_120
#            h_pix = hotpix_120
        if data_exposure_level <= 300:
            s_dark = super_dark_300
            d_exp = 300.0 #dark_300_exposure_level #hack to fix bad dark master.
            h_map = hotmap_300
            h_pix = hotpix_300
        else:
            do_dark = False  
        if do_dark:
            #breakpoint()
        #Need to verify dark is not 0 seconds long!
            if d_exp >= data_exposure_level and d_exp >= 1:
                scale = data_exposure_level/d_exp
                img =  (img - s_dark*scale)
                print('QuickDark result: ', scale)
                imageStats(img, loud)
#                scale2 = scale*1.1
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                scale2 = scale*1.2
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                scale2 = scale*1.3
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                scale2 = scale*1.4
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                scale2 = scale*1.5
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                scale2 = scale*1.6
#                img2 =  (img - s_dark*scale2)
#                print('QuickDark result: ', scale2)
#                imageStats(img2, loud)
#                img2 =  (img - s_dark*scale)    #put back to correct            
                cal_string += ', D'
            else:
                print('INFO:  Dark exposure too small, skipped this step.')           

        img_filter = hdu.header['FILTER']
        if frame_type[-4:]  == 'flat': break       #Note frame type end inf 'flat, e.g arc_flat, screen_flat, sky_flat
        do_flat = True
        if img_filter == 'w':
            do_flat= False
            #s_flat = super_flat_w
        elif img_filter == 'HA':
            do_flat = False
            #s_flat = super_flat_HA
        else:
            do_flat = False
        if do_flat: # and not g_dev['seq'].active_script == 'make_superscreenflats':
            img = img/s_flat
            print('QuickFlat result:  ', scale)
            imageStats(img, loud)
            cal_string +=', SCF'
        #median8(img, h_pix)
        #cal_string +=', HP'
        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')
    return

        
class Camera:

    """ 
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """
    
    ###filter, focuser, rotator must be set up prior to camera.

    def __init__(self, driver: str, name: str, config):
        
        self.name = name
        g_dev['cam'] = self
        self.config = config
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
            self.camera.SetCCDTemperature = -20.0
            self.current_filter = 0

        else:

            self.camera.connected = True
            self.description = self.camera.Description
            self.maxim = False
            self.camera.SetCCDTemperature = -22.5
            print('Camera __init__ Fault!')
        self.exposure_busy = False
        #Set camera to a sensible default state -- this should ultimately be configuration settings 
        self.camera_model = "FLI Kepler 400 #01"
        #self.camera.Binx = 1     #Kepler does not accept a bin
        #self.camera.BinY = 1
        self.camera.StartX = 256   #This puts the big glow spot almost out of the resulting frame/
        self.camera.StartY = 256
        self.camera.NumX = 1536
        self.camera.Numy = 1536
        
        self.af_mode = False
        self.af_step = -1
        self.f_spot_dia = []
        self.f_positions = []
        #self.save_directory = abspath(join(dirname(__file__), '..', 'images'))   #Where did this come from?
                
    @classmethod
    def fit_quadratic(cls, x, y):     
        #From Meeus, works fine.
        #Abscissa arguments do not to be ordered for this to work.
        #NB Variable names this short can confict with debugger commands.
        if len(x) == len(y):
            p = 0
            q = 0
            r = 0
            s = 0
            t = 0
            u = 0
            v = 0
            for i in range(len(x)):
                p += x[i]
                q += x[i]**2
                r += x[i]**3
                s += x[i]**4
                t += y[i]
                u += x[i]*y[i]
                v += x[i]**2*y[i]
            n = len(x)
            d = n*q*s +2*p*q*r - q*q*q - p*p*s - n*r*r
            a = (n*q*v + p*r*t + p*q*u - q*q*t - p*p*v - n*r*u)/d
            b = (n*s*u + p*q*v + q*r*t - q*q*u - p*s*t - n*r*v)/d
            c = (q*s*t + q*r*u + p*r*v - q*q*v - p*s*u - r*r*t)/d
            print('Quad;  ', a, b, c)
            return (a, b, c)
        else:
            return None
        
    def get_status(self):
        #status = {"type":"camera"}
        status = {}
        if self.exposure_busy:
            status['busy_lock'] = 'true'
        else:
            status['busy_lock'] = 'false'
        cam_stat = self.camera.CameraState
        status['status'] = str(cam_stat)  #The state could be expanded to be more meaningful.
        status['ccd_temperature'] = str(round(self.camera.CCDTemperature , 3))



    def parse_command(self, command):
        print("Camera Command incoming:  ", command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        

        if action == "expose" and not self.exposure_busy :
            self.expose_command(req, opt, do_sep=False)
            self.exposure_busy = False     #Hangup needs to be guarded with a timeout.
            self.active_script = None
            return True    #this resumes Run Thread in Obs.
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
                       gather_status = True, do_sep=False, no_AWS=False):
        ''' Apply settings and start an exposure. '''
        c = self.camera
        print('Expose Entered.  req:  ', required_params, 'opt:  ', optional_params)
        bin_x = int(optional_params.get('bin', 1))
        bin_y = bin_x   #NB This needs fixing
        gain = optional_params.get('gain', 1)

        exposure_time = float(required_params.get('time', 5))
        #exposure_time = max(0.2, exposure_time)  #Saves the shutter, this needs qualify with imtype.
        imtype= required_params.get('image_type', 'Light')
        new_filter = optional_params.get('filter', 'w')
        self.current_filter = g_dev['fil'].filter_selected
        count = int(optional_params.get('count', 1))
        if count < 1:
            count = 1   #Hence repeat does not repeat unless > 1
        filter_req = {'filter_name': str(new_filter)}
        filter_opt = {}
        if self.current_filter != new_filter:
            g_dev['fil'].set_name_command(filter_req, filter_opt)
        #NBNB Changing filter may cause a need to shift focus
        self.current_filter = g_dev['fil'].filter_selected
        self.current_offset = g_dev['fil'].filter_offset
        area = optional_params.get('size', 100)
        if area == None: area = 100
        if imtype.lower() == 'light' or imtype.lower() == 'screen flat' or imtype.lower() == 'sky flat' or imtype.lower() == \
                             'experimental' or imtype.lower() == 'toss':
                                 #here we might eventually turn on spectrograph lamps as needed for the imtype.
            imtypeb = True    #imtypeb passed to open the shutter.
            frame_type = imtype.lower()
        elif imtype.lower() == 'bias':
                exposure_time = 0.0
                imtypeb = False
                frame_type = 'bias'
                no_AWS = True
                #Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'dark':
                imtypeb = False
                frame_type = 'dark'
                no_AWS = True
                #Consider forcing filter to dark if such a filter exists.
        else:
            imtypeb = True
        #NBNB This area still needs work to cleanly define shutter, calibration and AWS actions.
                
        print(bin_x, count, self.current_filter, area)# type(area))
        try:
            if type(area) == str and area[-1] =='%':
                area = int(area[0:-1])
        except:
            area = 100
            
        #print('pre area:  ', self.camera, area)
        ##NBNB Need to fold in subtracting overscan for subframes.
        
        #This code is no where general enough for use!
        #I have fast patched it for 4096x4096 chip/
        
        #NBNBNB Consider jamming camera X Size in first. THios if for a FLI Kepler 4040
        if bin_y == 0 or self.camera.MaxBinX != self.camera.MaxBinY:
            self.bin_x = min(bin_x, self.camera.MaxBinX)
            self.camera.BinX = self.bin_x 
            self.bin_y = min(bin_x, self.camera.MaxBiny)
            self.camera.BinY = self.bin_y
        else:
            self.bin_x = min(bin_x, self.camera.MaxBinX)
            self.camera.Binx = self.bin_x
            self.bin_y = min(bin_y, self.camera.MaxBinY)
            self.camera.BinY = self.bin_y
        self.len_x = 4096#self.camera.CameraXSize//self.bin_x
        self.len_y = 4096#self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
        self.len_xs = 4096#self.len_x - 50   #THIS IS A HACK
        #print(self.len_x, self.len_y)
        
        #"area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg']
        if type(area) == str and area.lower() == "1x-jpg":
            self.camera.NumX = 768
            self.camera.StartX = 1659
            self.camera.NumY = 768
            self.camera.StartY = 1659
            self.area = 37.5
        elif type(area) == str and area.lower() == "2x-jpg":
            self.camera.NumX = 1536
            self.camera.StartX = 1280
            self.camera.NumY = 1536
            self.camera.StartY = 1280
            self.area = 75
        elif type(area) == str and area.lower() == "1/2 jpg":
            self.camera.NumX = 384
            self.camera.StartX = 832
            self.camera.NumY = 384
            self.camera.StartY = 832
            self.area = 18.75
        elif type(area) == str:     #Just defalut to a small area.
            self.camera.NumX = self.len_x//4
            self.camera.StartX = int(self.len_xs/2.667)
            self.camera.NumY = self.len_y//4
            self.camera.StartY = int(self.len_y/2.667)
            self.area = 100
        elif 72 < area <= 100:
            self.camera.NumX = self.len_x
            self.camera.StartX = 0
            self.camera.NumY = self.len_y
            self.camera.StartY = 0
            self.area = 100
        elif 70 <= area <= 72:
            self.camera.NumX = int(self.len_xs/1.4142)
            self.camera.StartX = int(self.len_xs/6.827)
            self.camera.NumY = int(self.len_y/1.4142)
            self.camera.StartY = int(self.len_y/6.827)
            self.area = 71       
        elif area == 50:
            self.camera.NumX = self.len_xs//2
            self.camera.StartX = self.len_xs//4
            self.camera.NumY = self.len_y//2
            self.camera.StartY = self.len_y//4
            self.area = 50
        elif 33 <= area <= 35:
            self.camera.NumX = int(self.len_xs/2.829)
            self.camera.StartX = int(self.len_xs/3.093)
            self.camera.NumY = int(self.len_y/2.829)
            self.camera.StartY = int(self.len_y/3.093)
            self.area = 33
        elif area == 25:
            self.camera.NumX = self.len_xs//4
            self.camera.StartX = int(self.len_xs/2.667)
            self.camera.NumY = self.len_y//4
            self.camera.StartY = int(self.len_y/2.667)
            self.area = 25
        else:
            self.camera.NumX = self.len_x
            self.camera.StartX = 0
            self.camera.NumY = self.len_y
            self.camera.StartY = 0
            self.area = 100
            print("Defult area used. 100%")
# #NBNBNB Consider jamming camera X Size in first.  THis is for a FLI Kepler 400
#        if bin_y == 0 or self.camera.MaxBinX != self.camera.MaxBinY:
#            self.bin_x = min(bin_x, self.camera.MaxBinX)
#            self.camera.BinX = self.bin_x 
#            self.bin_y = min(bin_x, self.camera.MaxBiny)
#            self.camera.BinY = self.bin_y
#        else:
#            self.bin_x = min(bin_x, self.camera.MaxBinX)
#            self.camera.Binx = self.bin_x
#            self.bin_y = min(bin_y, self.camera.MaxBinY)
#            self.camera.BinY = self.bin_y
#        self.len_x = 1536#self.camera.CameraXSize//self.bin_x
#        self.len_y = 1536#self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
#        self.len_xs = 1536#self.len_x - 50   #THIS IS A HACK
#        #print(self.len_x, self.len_y)
#        
#        #"area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg']
#        if type(area) == str and area.lower() == "1x-jpg":
#            self.camera.NumX = 768
#            self.camera.StartX = 640
#            self.camera.NumY = 768
#            self.camera.StartY = 640
#            self.area = 37.5
#        elif type(area) == str and area.lower() == "2x-jpg":
#            self.camera.NumX = 1536
#            self.camera.StartX = 256
#            self.camera.NumY = 1536
#            self.camera.StartY = 256
#            self.area = 75
#        elif type(area) == str and area.lower() == "1/2 jpg":
#            self.camera.NumX = 384
#            self.camera.StartX = 832
#            self.camera.NumY = 384
#            self.camera.StartY = 832
#            self.area = 18.75
#        elif type(area) == str:     #Just defalut to a small area.
#            self.camera.NumX = self.len_x//4
#            self.camera.StartX = int(self.len_xs/2.667)
#            self.camera.NumY = self.len_y//4
#            self.camera.StartY = int(self.len_y/2.667)
#            self.area = 100
#        elif 72 < area <= 100:
#            self.camera.NumX = self.len_x
#            self.camera.StartX = 256
#            self.camera.NumY = self.len_y
#            self.camera.StartY = 256
#            self.area = 100
#        elif 70 <= area <= 72:
#            self.camera.NumX = int(self.len_xs/1.4142)
#            self.camera.StartX = int(self.len_xs/6.827)
#            self.camera.NumY = int(self.len_y/1.4142)
#            self.camera.StartY = int(self.len_y/6.827)
#            self.area = 71       
#        elif area == 50:
#            self.camera.NumX = self.len_xs//2
#            self.camera.StartX = self.len_xs//4
#            self.camera.NumY = self.len_y//2
#            self.camera.StartY = self.len_y//4
#            self.area = 50
#        elif 33 <= area <= 35:
#            self.camera.NumX = int(self.len_xs/2.829)
#            self.camera.StartX = int(self.len_xs/3.093)
#            self.camera.NumY = int(self.len_y/2.829)
#            self.camera.StartY = int(self.len_y/3.093)
#            self.area = 33
#        elif area == 25:
#            self.camera.NumX = self.len_xs//4
#            self.camera.StartX = int(self.len_xs/2.667)
#            self.camera.NumY = self.len_y//4
#            self.camera.StartY = int(self.len_y/2.667)
#            self.area = 25
#        else:
#            self.camera.NumX = self.len_x
#            self.camera.StartX = 256
#            self.camera.NumY = self.len_y
#            self.camera.StartY = 256
#            self.area = 100
#            print("Defult area used. 100%")
       #print(self.camera.NumX, self.camera.StartX, self.camera.NumY, self.camera.StartY)
        for seq in range(count):
            #SEQ is the outer repeat count loop.
            if seq > 0: 
                g_dev['obs'].update_status()
            for fil in [self.current_filter]:#, 'N2', 'S2', 'CR']: #range(1)
#                if fil == 'CR': exposure_time /= 2.5
#                if fil == 'S2': exposure_time *= 1
                #Change filter here
                print('\nFilter:  ',  (fil +' ')*5, '\n')
                for rpt in range(1):
                    #Repeat that filter rpt-times
                    #print('\n   REPEAT REPEAT REPEAT:  ', rpt, '\n')
                    try:
                        #print("starting exposure, area =  ", self.area)
                        #NB NB Ultimately we need to be a thread.
                        self.pre_mnt = []
                        self.pre_rot = []
                        self.pre_foc = []
                        self.pre_ocn = []
                        #Check here for filter, guider, still moving  THIS IS A CLASSIC case where a timeout is a smart idea.
                        while  g_dev['foc'].focuser.IsMoving or \
                           g_dev['rot'].rotator.IsMoving or \
                           g_dev['mnt'].mount.Slewing or \
                           g_dev['fil'].filter_front.Position == -1 or \
                           g_dev['fil'].filter_back.Position == -1:
                           print('Filter, focus, rotator or mount is still moving.')
                           time.sleep(0.5)
                        self.t1 = time.time()
                        #Used to inform fits header where telescope is for scripts like screens.
                        g_dev['ocn'].get_quick_status(self.pre_ocn)
                        g_dev['foc'].get_quick_status(self.pre_foc)
                        g_dev['rot'].get_quick_status(self.pre_rot)
                        g_dev['mnt'].get_quick_status(self.pre_mnt)  #stage two quick_get_'s symmetric around exposure
                        self.exposure_busy = True                        
                        print('First Entry', c.StartX, c.StartY, c.NumX, c.NumY, exposure_time)
                        self.t2 = time.time()       #Immediately before Exposure
                        c.StartExposure(exposure_time, imtypeb)     #True indicates Light Frame.
                        self.t9 = time.time()
                        #We go here to keep this subroutine a reasonable length.
                        self.finish_exposure(exposure_time,  frame_type, count - seq, p_next_filter, p_next_focus, p_dither, \
                                             gather_status, do_sep, no_AWS)
                        self.exposure_busy = False
                        self.t10 = time.time()
                        #self.exposure_busy = False  Need to be able to do repeats
                        #g_dev['obs'].update()   This may cause loosing this thread
                    except Exception as e:
                        print("failed exposure")
                        print(e)
                        self.t11 = time.time()
                        return   #Presumably this premature return cleans things out so they can still run?
        self.t11 = time.time()
        return

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
                        gather_status=True, do_sep=False, no_AWS=False):
        print("Finish exposure Entered:  ", self. af_step, exposure_time, frame_type, counter)
        if gather_status:   #Does this need to be here?
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []
        #counter = 0
        while True:
            try:
                self.t3 = time.time()
                if self.camera.ImageReady: #and not self.img_available and self.exposing:
                    self.t4 = time.time()
                    img = self.camera.ImageArray
                    #I think this should be lifted higher.
                    if gather_status:
                        g_dev['mnt'].get_quick_status(self.post_mnt)  #stage symmetric around exposure
                        g_dev['rot'].get_quick_status(self.post_rot)
                        g_dev['foc'].get_quick_status(self.post_foc)
                        g_dev['ocn'].get_quick_status(self.post_ocn)
                    self.t5 = time.time()
                    ###Here is the place to potentially pipeline dithers, next filter, focus, etc.
                    if p_next_filter is not None:
                        print("Post image filter seek here")
                    if p_next_focus is not None:
                        print("Post Image focus seek here")
                    if p_dither:
                        print("Post image dither step here")
                    #img = self.camera.ImageArray
                    img = np.array(img).astype('uint16')
                    #Makes the image like those from Default MaximDL
                    img = img.transpose()
                    self.t6 = time.time()
                    #Save image with Fits Header information, then read back with astropy
                    hdu = fits.PrimaryHDU(img)
#                    hdu.header['COMMENT'] = ('Kilroy was here.', 'Here as well.')
                    hdul = fits.HDUList([hdu])
                    hdul.writeto('Q:\\archive\\' + 'gf03'+ '\\newest.fits', overwrite=True)
                    #This should be a very fast disk.
                    #self.camera.SaveImage('Q:\\archive\\ea03\\newest.fits')#, overwrite=True)  #This was a Maxim Command.
                    if gather_status:
                        avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                        avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                        avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                        avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                    #print(avg_ocn, avg_foc, avg_rot, avg_mnt)

                    #counter = 0
                    try:
                        #Save the raw data after adding fits header information.
                        hdu1 =  fits.open('Q:\\archive\\gf03\\newest.fits')
                        hdu = hdu1[0]   #get the Primary header and date
                        hdu.data = hdu.data.astype('uint16')    #This is probably redundant but forces unsigned storage
                        self.hdu_data1 = hdu.data.copy()
                        hdu.header['BUNIT']    = 'adu'
                        hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))   
                        hdu.header['EXPTIME']  = exposure_time   #This is the exposure in seconds specified by the user                  
                        hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times                    
                        hdu.header['FILTER ']  = self.current_filter
                        hdu.header['FILTEROF']  = self.current_offset
                        if g_dev['scr'].dark_setting == 'Light':
                            hdu.header['SCREEN'] = g_dev['scr'].bright_setting
                        hdu.header['IMAGETYP'] = 'Light Frame'  
                        hdu.header['SET-TEMP'] = round(self.camera.SetCCDTemperature, 3)                 
                        hdu.header['CCD-TEMP'] = round(self.camera.CCDTemperature, 3)    
                        hdu.header['XPIXSZ']   = self.camera.CameraXSize       
                        hdu.header['YPIXSZ']   = self.camera.CameraySize         
                        try:
                            hdu.header['XBINING'] = self.camera.BinX                      
                            hdu.header['YBINING'] = self.camera.BinY 
                        except:
                            hdu.header['XBINING'] = 1                       
                            hdu.header['YBINING'] = 1
                        hdu.header['CCDSUM'] = '1 1'  
                        hdu.header['XORGSUBF'] = 768          
                        hdu.header['YORGSUBF'] = 768           
                        hdu.header['READOUTM'] = 'Monochrome'                                                         
                        hdu.header['TELESCOP'] = 'PlaneWave CDK 432mm'
                        hdu.header['APR-DIA']   = 432.          
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
                        hdu.header['INSTRUME'] = 'FLI4 CMOS USB3'                                                      
                        hdu.header['OBSERVER'] = 'WER     '                                                            
                        hdu.header['NOTE']    = 'Bring up Images'                                                     
                        hdu.header['FLIPSTAT'] = 'None'  
                        hdu.header['SEQCOUNT'] = int(counter)
                        hdu.header['DITHER']   = 0
                        hdu.header['IMGTYPE']  = frame_type
                        hdu.header['OPERATOR'] = "WER"
                        hdu.header['ENCLOSE']  = "Clamshell"   #Need to document shutter status, azimuth, internal light.
                        hdu.header['DOMEAZ']  = "None"   #Need to document shutter status, azimuth, internal light.
                        hdu.header['ROOF']  = "Open/Closed"   #Need to document shutter status, azimuth, internal light.
                        hdu.header['ENCLIGHT'] ="White/Red/IR/Off"
                        if gather_status:
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
        
                        hdu.header['DETECTOR'] = "G-Sense CMOS 400"
                        hdu.header['CAMNAME'] = 'gf03'
#                        try:
#                            hdu.header['GAIN'] = g_dev['cam'].camera.gain
                        print('Gain was read;  ', g_dev['cam'].camera.gain)
#                        except:                                
#                            hdu.header['GAIN'] = 1.18
                        hdu.header['GAINUNIT'] = 'e-'
                        hdu.header['GAIN'] = 4.41   #20190911   LDR-LDC mode set in ascom
                        hdu.header['RDNOISE'] = 4.86
                        hdu.header['CMOSMODE'] = 'HDR-LDC'  #Need to figure out how to read this from setup.
                        hdu.header['SATURATE'] = 4095
                        hdu.header['PIXSCALE'] = 0.85

                        #Need to assemble a complete header here
                        #hdu1.writeto('Q:\\archive\\ea03\\new2b.fits')#, overwrite=True)
                        alias = self.config['camera']['camera1']['alias']
                        im_type = 'EX'   #or EN for engineering....
                        f_ext = ""
                        if frame_type[-4:] == 'flat':
                            f_ext = '-' + self.current_filter    #Append flat string to local image name
                        next_seq = ptr_config.next_seq(alias)
                        cal_name = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + f_ext + '-'  + \
                                                       im_type + '01.fits'
                        raw_name00 = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '00.fits'
                        raw_name01 = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '01.fits'
                        #Cal_ and raw_ names are confusing
                        db_name = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '13.fits'
                        jpeg_name = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '13.jpg'
                        text_name = self.config['site'] + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + \
                                                       im_type + '01.txt'
                        im_path_r = 'Q:\\archive\\' + alias +'\\'
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
                        
                        
                        hdu1.writeto(raw_path + raw_name00, overwrite=True)
                        text = open(im_path + text_name, 'w')
                        text.write(str(hdu.header))
                        text.close()
                        text_data_size = len(str(hdu.header)) - 2048
                        raw_data_size = hdu.data.size

                        print("\n\Finish-Exposure is complete:  " + raw_name00, raw_data_size, '\n')
                        #Now make the db_image:
                        #THis should be moved into the transfer process and processed in parallel
                        #hdu.data.astype('float32')
                       
                        calibrate(hdu, lng_path, frame_type)
                        hdu1.writeto(cal_path + cal_name, overwrite=True)
                        hdu1.writeto(im_path + raw_name01, overwrite=True)
#                        
##                        if hdu.data.shape[1] == 2098:
##                            overscan = hdu.data[:, 2048:]
##                            medover = np.median(overscan)
##                            print('Overscan median =  ', medover)
##                            hdu.data = hdu.data[:, :2048] - medover
##                        else:
##                            hdu.data = hdu.data # - 1310.0     #This deaals with all subframes
                        if do_sep:
                            img = hdu.data.copy().astype('float')
                            bkg = sep.Background(img)
                            bkg_rms = bkg.rms()
                            img -= bkg
                            sources = sep.extract(img, 2.5, err=bkg_rms, minarea=30)#, filter_kernel=kern)
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
                            spot = np.median(spot)
                            try:
                                print('Spot and flux:  ', spot, source['cflux'], '\n', sources)
                            except:
                                pass
                            
                        resized_a = resize(hdu.data, (768, 768), preserve_range=True)
                        #print(resized_a.shape, resized_a.astype('uint16'))
                        hdu.data = resized_a.astype('uint16')
                        db_data_size = hdu.data.size
                        hdu1.writeto(im_path + db_name, overwrite=True)
                        hdu.data = resized_a.astype('float')
                        istd = np.std(hdu.data)
                        imean = np.mean(hdu.data)                                             
                        img3 = hdu.data/(imean + 3*istd)
                        fix = np.where(img3 >= 0.999)
                        fiz = np.where(img3 <= -0.1)
                        img3[fix] = .999
                        img3[fiz] = -0.1
                        #img3[:, 384] = 0.995
                        #img3[384, :] = 0.995
                        print(istd, img3.max(), img3.mean(), img3.min())
                        imsave(im_path + jpeg_name, img3)
                        jpeg_data_size = img3.size - 1024
                        if not no_AWS:                        
                            self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                            self.enqueue_image(text_data_size, im_path, text_name)
                            self.enqueue_image(db_data_size, im_path, db_name)
                            self.enqueue_image(raw_data_size, im_path, raw_name01)                       
                        self.img = None
                        hdu = None
                    except:   
                        breakpoint()
                        print('Header assembly block failed.')
                        self.t7 = time.time()
                    return
                else:               #here we are in waiting for imageReady loop and could send status and check Queue
                    counter += 1
                    #g_dev['obs'].update()    #This keeps status alive while camera is looping
                    continue
                self.t7= time.time()
            except:
                counter += 1
                time.sleep(1)
                continue
        self.t8 = time.time()
        return
            

#
#            #                        self.last_image_name = f'{int(time.time())}_{site}_testimage_{duration}s_no{self.image_number}.jpg'
#            #                        print(f"image file: {self.last_image_name}")
#            #                        self.images.append(self.last_image_name)
#            #                        #self.save_image(self.last_image_name)
#            #                        self.image_number += 1


          

    def enqueue_image(self, priority, im_path, name):
        image = (im_path, name)
        #print("stuffing Queue:  ", priority, im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)
        
#        aws_req = {"object_name": "raw_data/2019/" + name}
#        aws_resp = g_dev['obs'].api.authenticated_request('GET', 'WMD/upload/', aws_req)
#
#        with open(im_path + name , 'rb') as f:
#            files = {'file': (im_path + name, f)}
#            http_response = requests.post(aws_resp['url'], data=aws_resp['fields'], files=files)
#            print("\n\nhttp_response:  ", http_response, '\n')
        

if __name__ == '__main__':
#    import config
    req = {'time': 2,  'alias': 'gf03', 'image_type': 'Light', 'filter': 2}
    opt = {'size': 100}
    cam = Camera('ASCOM.FLI.Kepler.Camera', "gf03")
    cam.expose_command(req, opt, gather_status=False)

#    This fragment directly runs the camera not through the routines above
#    cam.camera.StartExposure(0.001, False)
#    elapsed = 0
#    while not cam.camera.ImageReady:
#        time.sleep(0.1)
#        elapsed += 0.1
#        print(round(elapsed, 1))
#    bs = time.time()
#    b = cam.camera.ImageArray
#    print(b[23][23], time.time() - bs)
#    b = np.array(b).astype('uint16')
#
#    cam.camera.StartExposure(5.0, True)
#    elapsed = 0
#    while not cam.camera.ImageReady:
#        time.sleep(0.1)
#        elapsed += 0.1
#        print(round(elapsed, 1))
#    ls = time.time()
#    l = cam.camera.ImageArray
#    print(l[23][23], time.time() - ls)
#    l = np.array(l).astype('uint16')
#    print(type(b), type(l))
#    d = l-b
#    print(d[23][23])
    



        
    
