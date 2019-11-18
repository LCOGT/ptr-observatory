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
#import ptr_events
#import api_calls
#import requests

#import ptr_bz2

'''

Quick images store little, and are mainly for focus eploration.
Thoughts on how to merge CMOS images.

The detector in question is:  G-Sense 4040. The camera is a FLI Kepler.

Pick a setpoint temperature you can maintain over a period of time,
or build a bank of calibrations are various temperatures.  Since we 
are able to hold -20C year-round we have no experience with scaling 
combining calibrations from various temperatures. Dark current 
declines exponentially by a factor of two for every -7C so correction
to an intermediate temperature requires some care.

Start with taking 511HDR and LDR biases then a large number of 
darks (I use 127) of a duration longer than what you plan for any
given actual exposure.  I use 300 seconds.

Median combine themin the usual way, of course subtracting the superbias
from the darks.

I save these in float32.  I divide the dark by the exposure time
so its units are adu/sec.

The most naive combination method can be effected by finding the scale
between the low and high ranges.  Expose so the high gain image has a peak
values around 3600 ADU, but the images can fall off from that central value
somewhat.  Take say 15 0r 31 of these -- star images are needed here

Then take as many low gain images, ideally interleaving the acquisition.  Median
or 3-sigma clip mean to two sets then divide the high by the low.  The result
should be a image with the vast majority of the values tightly distributed
about some value, like 17.xyz.  This is the ratio of the e-/adu gains of the
two settings.

Since this is a full image I find its median and use that value as the 'scale.'

Note no non-linearity is taken into account with this procedure.

Now for two images then on an object, calibrate as above, then multiply the
low gain image by the scale.

Next for the scaled low gain image any pixel which is < 3600, instead use the
corresponding high gain pixel.  If you have derived bad pixel, column or row
maps for each gain range, then they also need to be merged on a per-pixel 
basis with a Boolean OR.

For cosmetic, rather than scientific purposes one, could randomomly change the
3600 threshold with some sort of a distribution to mask any discontinuity at 
that value.  Note I said cosmetic purposes.

Better way:  This involves a light box and careful gain and linearity calibration
of the two LDR and HDR number lines.  If these polynomials are available then
aplly them to each pixel after the dark step.

The non-linearity polynomomials will indicate where the HDR image is starting 
to sauturate and go non-linear.  My choice of 3600 or so is based on the value 
FLI provides.  It might be less or more.  but there is no need to get too close
 to 4095 -- the maximum value for a 12 bit quantity.

Based on detector named gf03, the scale is ~ 17 -- less than 32 (5 bits.)
So multiplying by 17 extends the range above 16 bits.  Since we are dealing with a 
float quantity that really does not matter.  However if you want to keep the merged 
value < 2^16 then instead divide the High data by 2.0, divide the low range data by
(17/2) and use a merge threshold of 3600/2.  Don't forget to update gain in the 
header properly.

There is no reason to do compaction to 2^16 unless some downstream application 
'cuts' at 65535.

'''

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
    axis1 =img_img.shape[0]
    axis2 = img_img.shape[1]
    subAxis1 = axis1/2
    patchHalf1 = axis1/10
    subAxis2 = axis2/2
    patchHalf2 = axis2/10
    sub_img = img_img[int(subAxis1 - patchHalf1):int(subAxis1 + patchHalf1), int(subAxis2 - patchHalf2):int(subAxis2 + patchHalf2) ]
    img_mean = sub_img.mean()
    img_std = sub_img.std()
    #ADD Mode here someday.
    if loud: print('Mean, std:  ', round(img_mean, 1), round(img_std, 2))
    return round(img_mean, 2), round(img_std, 2)

def median8(img, hot_pix):
    #print('1: ',img_img.data)
    axis1 = img.shape[0]
    axis2 = img.shape[1]

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
super_bias_ldr = None
super_dark_90 = None
super_dark_90_ldr = None
super_dark_300 = None
super_dark_300_ldr = None
hotmap_300 = None
hotmap_300_ldr = None
hotpix_300 = None
hotpix_300_ldr = None
super_flat_w = None
super_flat_HA = None

#This is a brute force linear version. This needs to be more sophisticated and camera independent.

def calibrate (hdu, hdu_ldr, lng_path, frame_type='light', start_x=0, start_y=0, quick=False):
    #These variables are gloal in the sense they persist between calls (memoized in a form)
    global super_bias, super_bias_ldr, super_dark_90, super_dark_90_ldr, super_dark_300, \
           super_dark_300_ldr, super_flat_w, super_flat_HA, hotmap_300, hotpix_300, hotmap_300_ldr, hotpix_300_ldr
    loud = True
    #This needs to deal with caching different binnings as well.  And do we skip all this for a quick
    if super_bias is None:
        try:
            sbHdu = fits.open(lng_path + 'mb_1_hdr.fits')
            super_bias = sbHdu[0].data#.astype('float32')
            #Temp fix
            fix = np.where(super_bias > 400)
            super_bias[fix] = int(super_bias.mean())
            sbHdu.close()
            quick_bias = True
            if loud: print(lng_path + 'mb_1_hdr.fits', 'Loaded')
        except:
            quick_bias = False
            print('WARN: No Bias Loaded.')
    if not quick and super_bias_ldr is None and hdu_ldr is not None:
        try:
            sbHdu = fits.open(lng_path + 'mb_1_ldr.fits')
            super_bias_ldr = sbHdu[0].data#.astype('float32')
            #Temp fix
            fix = np.where(super_bias_ldr > 400)
            super_bias[fix] = int(super_bias_ldr.mean())
            sbHdu.close()
            quick_bias_ldr = True
            if loud: print(lng_path + 'mb_1_ldr.fits', 'Loaded')
        except:
            quick_bias_ldr = False
            print('WARN: No Bias Loaded.')
            #    if super_dark_15 is None:
#        try:
#            sdHdu = fits.open(lng_path + 'ldr_md_15.fits')
#            dark_15_exposure_level = sdHdu[0].header['EXPTIME']
#            super_dark_15  = sdHdu[0].data.astype('float32')
#            sdHdu.close()
#           quick_dark_15 = True
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
    if super_dark_90 is None:
        try:
            sdHdu = fits.open(lng_path + 'md_1_90_hdr.fits')
            dark_90_exposure_level = sdHdu[0].header['EXPTIME']
            super_dark_90  = sdHdu[0].data.astype('float32')
            sdHdu.close()
            fix = np.where(super_dark_90 < 0)
            super_dark_90[fix] = 0
            quick_dark_90 = True
            print(lng_path + 'md_1_90_hdr.fits', 'Loaded')
        except:
            quick_dark_90 = False
            print('WARN: No dark Loaded.')
    if super_dark_300 is None:
        try:
            sdHdu = fits.open(lng_path + 'md_1_300_hdr.fits')
            dark_300_exposure_level = sdHdu[0].header['EXPTIME']
            super_dark_300  = sdHdu[0].data#.astype('float32')
            print('sdark_HDR:  ', super_dark_300.mean())
            sdHdu.close()
            fix = np.where(super_dark_300 < 0)
            super_dark_300[fix] = 0
            quick_dark_300 = True
            print(lng_path + 'md_1_300_hdr.fits', 'Loaded')
        except:
            quick_dark_300 = False
            print('WARN: No dark Loaded.')
    if  not quick and super_dark_300_ldr is None and hdu_ldr is not None:
        try:
            sdHdu = fits.open(lng_path + 'md_1_300_ldr.fits')
            dark_300_ldr_exposure_level = sdHdu[0].header['EXPTIME']
            super_dark_300_ldr  = sdHdu[0].data#.astype('float32')
            print('sdark_300_LDR:  ', super_dark_300_ldr.mean())
            sdHdu.close()
            fix = np.where(super_dark_300_ldr < 0)
            super_dark_300_ldr[fix] = 0
            quick_dark_300_ldr = True
            print(lng_path + 'md_1_300_ldr.fits', 'Loaded')
        except:
            quick_dark_300_ldr = False
            print('WARN: No ldr 300 dark Loaded.')
    if  not quick and super_dark_90_ldr is None and hdu_ldr is not None:
        try:
            sdHdu = fits.open(lng_path + 'md_1_90_ldr.fits')
            dark_90_ldr_exposure_level = sdHdu[0].header['EXPTIME']
            super_dark_90_ldr  = sdHdu[0].data#.astype('float32')
            print('sdark_90_LDR:  ', super_dark_90_ldr.mean())
            sdHdu.close()
            fix = np.where(super_dark_90_ldr < 0)
            super_dark_90_ldr[fix] = 0
            quick_dark_90_ldr = True
            print(lng_path + 'md_1_90_ldr.fits', 'Loaded')
        except:
            quick_dark_90_ldr = False
            print('WARN: No ldr 90 dark Loaded.')
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
            if not quick: print('WARN: No HA Flat/Lum Loaded.')
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
            shHdu = fits.open(lng_path + 'hdr_hotmap_300.fits')
            hotmap_300 = shHdu[0].data#.astype('uint16')
            shHdu.close()
            quick_hotmap_300 = True
            hotpix_300 = np.where(hotmap_300 > 60)  #This is a temp simplifcation
            print(lng_path + 'hdr_hotmap_300.fits', 'Loaded, Length = ', len(hotpix_300[0]))
        except:
            quick_hotmap_300= False
            if not quick: print('Hotmap_300 failed to load.')
    if  not quick and hotmap_300_ldr is None and hdu_ldr is not None:
        try:
            shHdu = fits.open(lng_path + 'ldr_hotmap_300.fits')
            hotmap_300_ldr = shHdu[0].data#.astype('uint16')
            shHdu.close()
            quick_hotmap_300_ldr = True
            hotpix_300_ldr = np.where(hotmap_300_ldr > 4)  #This is a temp simplifcation
            print(lng_path + 'ldr_hotmap_300.fits', 'Loaded, Length = ', len(hotpix_300_ldr[0]))
        except:
            quick_hotmap_300_ldr= False
            if not quick: print('Hotmap_300_ldr failed to load.')
            
    #Here we actually calibrate.  
    while True:   #Use break to drop through to exit.  i.e., do not calibrte frames we are acquring for calibration.
        cal_string = ''
        if not quick:
            img = hdu.data.astype('float32')
            if loud: print('InputImage (high):  ', imageStats(img, False))
        else:
            img = hdu.data
        if frame_type == 'bias': break
        if super_bias is not None:
            #if not quick: print(start_x, start_x + img.shape[0], start_y, start_y + img.shape[1])
            img = img - super_bias[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick: 
                if loud: print('QuickBias result (high):  ', imageStats(img, False))
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
        if data_exposure_level <= 90:
            s_dark = super_dark_90
            d_exp = 90.
            h_map = hotmap_300
            h_pix = hotpix_300
        elif data_exposure_level <= 300:
            s_dark = super_dark_300
            d_exp = 300.0 #dark_300_exposure_level #hack to fix bad dark master.
            h_map = hotmap_300
            h_pix = hotpix_300
        else:
            do_dark = False  
        if do_dark:
        #Need to verify dark is not 0 seconds long!
            if d_exp >= data_exposure_level and d_exp >= 1:
                scale = data_exposure_level/d_exp
                img =  (img - s_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])])
                if not quick:
                    print('QuickDark  scale/result(high): ', round(scale, 4), imageStats(img, loud))
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
                if not quick: print('INFO:  Dark exposure too small, skipped this step.')           

        img_filter = hdu.header['FILTER']
        if frame_type[-4:]  == 'flat': break       #Note frame type end inf 'flat, e.g arc_flat, screen_flat, sky_flat
        do_flat = False
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
            if not quick: print('QuickFlat result 9high):  ', imageStats(img, loud))
            
            cal_string +=', SCF'
        #median8(img, h_pix)
        #cal_string +=', HP'
        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')  #This is meant to catch an image change to 'float64'
    while not quick and hdu_ldr is not None:   #Use break to drop through to exit.  i.e., do not calibrte frames we are acquring for calibration.
        cal_string = ''
        img = hdu_ldr.data.astype('float32')
        if loud: print('LDR InputImage', imageStats(img, loud))
        if frame_type == 'bias': break
        if super_bias_ldr is not None:
            print(start_x, start_x + img.shape[0], start_y, start_y + img.shape[1])
            img = img - super_bias_ldr[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if loud: print('LDR QuickBias result:  ', imageStats(img, loud))
            cal_string += 'B'
        data_exposure_level = hdu_ldr.header['EXPTIME']
        if frame_type == 'dark': 
            break
        do_dark = True
        if data_exposure_level <= 90:
            s_dark = super_dark_90_ldr
            d_exp = 90.
            h_map = hotmap_300
            h_pix = hotpix_300
        elif data_exposure_level <= 300:
            s_dark = super_dark_300_ldr
            d_exp = 300.0 #dark_300_exposure_level #hack to fix bad dark master.
            h_map = hotmap_300
            h_pix = hotpix_300
        else:
            do_dark = False  
        if do_dark:
        #Need to verify dark is not 0 seconds long!
            if d_exp >= data_exposure_level and d_exp >= 1:
                scale = data_exposure_level/d_exp
                img =  (img - s_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])])
                print('LDR QuickDark result: ', scale, imageStats(img, loud))          
                cal_string += ', D'
            else:
                print('INFO:  Dark exposure too small, skipped this step.')           
        img_filter = hdu.header['FILTER']
        if frame_type[-4:]  == 'flat': break       #Note frame type end inf 'flat, e.g arc_flat, screen_flat, sky_flat
        do_flat = False
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
            if not quick: print('LDR QuickFlat result:  ', imageStats(img, loud))
            cal_string +=', SCF'
        #median8(img, h_pix)
        #cal_string +=', HP'
            break    #If we get this far we are done.
        if cal_string == '':
            cal_string = 'Uncalibrated'
        hdu_ldr.header['CALHIST'] = cal_string
        hdu_ldr.data = img.astype('float32')
        if not quick: print('Pre merge:  ', hdu.data.max(), hdu_ldr.data.max(), hdu_ldr.data.max()*20.2)
        ldr_scaled = hdu_ldr.data*20.2 #17.2314281698    #20191025b
        jam = np.where(hdu.data > 3600)
        if not quick: print('jam length:  ', len(jam[0]))
        hdu.data[jam] = hdu_ldr.data[jam]*20.2 #17.23142816988    #20191025b
        if not quick: print('Merged hdu.data.max():  ', hdu.data.max())
        #Temp fix for Tim Bq.
        big_max = hdu.data.max()
        fix = np.where(hdu.data < 0)
        if not quick: print('# of 0 fix pixels:  ', len(fix[0]))
        hdu.data[fix] = 0
        if big_max > 65535:
            hdu.data = hdu.data*65500/big_max
        #Just trimmed any spurious negatives and scaled to 0:65550
        
        break
        
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
            self.camera.CoolerOn = True
            self.current_filter = 0
            print('Control is ASCOM camera driver.')

        else:

            self.camera.LinkEnabled = True
            self.description = 'MAXIM'
            self.maxim = True
            self.ascom = False
            self.camera.TemperatureSetpoint = -20.
            self.camera.CoolerOn = True
            self.current_filter = 0
            print('Control is Maxim camera interface.')
        self.exposure_busy = False
        #Set camera to a sensible default state -- this should ultimately be configuration settings 
        self.camera_model = "FLI Kepler 4040 #gf03"
        #self.camera.Binx = 1     #Kepler does not accept a bin
        #self.camera.BinY = 1
        self.cameraXSize = self.camera.CameraXSize  #unbinned
        self.cameraYSize = self.camera.CameraYSize  #unbinned
        self.cameraMaxXBin = self.camera.MaxBinX
        self.cameraMaxYBin = self.camera.MaxBinY
        self.camera.StartX = 0   #This puts the big glow spot almost out of the resulting frame/  This should be a config input
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
        if self.maxim:
            cam_stat = 'unknown'#self.camera.CameraState
        if self.ascom:
            cam_stat = self.camera.CameraState
        status['status'] = str(cam_stat)  #The state could be expanded to be more meaningful.
        if self.maxim:
            status['ccd_temperature'] = str(round(self.camera.Temperature , 3))
        if self.ascom:
            status['ccd_temperature'] = str(round(self.camera.CCDTemperature , 3))
            



    def parse_command(self, command):
        print("Camera Command incoming:  ", command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        

        if action == "expose" and not self.exposure_busy :
            self.expose_command(req, opt, do_sep=False, quick=False)
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
                       gather_status = True, do_sep=False, no_AWS=False, quick=False):
        ''' 
        Apply settings and start an exposure. 
        Quick=True is meant to be fast.  We assume the ASCOM imageBuffer is the source of data, not the Files path.
        '''
        c = self.camera
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
        new_filter = optional_params.get('filter', 'w')
        self.current_filter = new_filter#g_dev['fil'].filter_selected  #TEMP
        count = int(optional_params.get('count', 1))
        if count < 1:
            count = 1   #Hence repeat does not repeat unless > 1
        filter_req = {'filter_name': str(new_filter)}
        filter_opt = {}
        if self.current_filter != new_filter:
            g_dev['fil'].set_name_command(filter_req, filter_opt)
        #NBNB Changing filter may cause a need to shift focus
        self.current_offset = 9000#g_dev['fil'].filter_offset  #TEMP
        area = optional_params.get('size', 100)
        if area == None: area = 100
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
                no_AWS = True
                do_sep = False
                #Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'dark':
                imtypeb = False
                frame_type = 'dark'
                no_AWS = True
                do_sep = False
                #Consider forcing filter to dark if such a filter exists.
        elif imtype.lower() == 'screen_flat' or imtype.lower() == 'sky flat':
            do_sep = False
        elif imtype.lower() == 'quick':
            quick=True
            no_AWS = True
            do_sep = False
        else:
            imtypeb = True
            do_sep = True
        #NBNB This area still needs work to cleanly define shutter, calibration, sep and AWS actions.
                
        print(bin_x, count, self.current_filter, area)# type(area))
        try:
            if type(area) == str and area[-1] =='%':
                area = int(area[0:-1])
        except:
            area = 100
            
        #print('pre area:  ', self.camera, area)
        ##NBNB Need to fold in subtracting overscan for subframes.
        
        #This code is no where general enough for use!
        #Need to first apply binning to the native chip.
        #The results should be computed once and passed on as a specification so there is not possibility
        #of downstream errors. Ichip/bin) / (area or subframe-spec).  Change area into a subframe specification.
        
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
            self.camera.StartX= dist_x
            self.camera.StartY= dist_y 
            self.camera.NumX= num_x 
            self.camera.NumY= num_y
            self.previous_image_name = sub_frame_fraction['definedOnThisFile']
            self.previous_start_x = dist_x
            self.previous_start_y = dist_y
            self.previous_num_x = num_x
            self.previous_num_y = num_y
            self.bpt_flag = False
        elif self.area == self.previous_area and sub_frame_fraction is not None and \
                        (sub_frame_fraction['definedOnThisFile'] == self.previous_image_name):         
            #Here we repeat the previous subframe and do not re-enter and make smaller
            self.camera.StartX = self.previous_start_x
            self.camera.StartY = self.previous_start_y
            dist_x = self.previous_start_x
            dist_y = self.previous_start_y
            self.camera.NumX= self.previous_num_x 
            self.camera.NumY= self.previous_num_y
            self.bpt_flag  = True
        
        elif sub_frame_fraction is None: 
            self.previous_start_x = self.camera.StartX  #These are the subframe values for the new area exposure.
            self.previous_start_y = self.camera.StartY
            dist_x = self.previous_start_x 
            dist_y = self.previous_start_y 
            self.previous_num_x = self.camera.NumX
            self.previous_num_y = self.camera.NumY
            self.previous_num_fraction_x = 1.0
            self.previous_num_fraction_y = 1.0
            self.previous_area = self.area
            self.bpt_flag = False     
            

       #print(self.camera.NumX, self.camera.StartX, self.camera.NumY, self.camera.StartY)
        for seq in range(count):
            #SEQ is the outer repeat count loop.
            if seq > 0: 
                g_dev['obs'].update_status()
            for fil in [self.current_filter]:#, 'N2', 'S2', 'CR']: #range(1)
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
                        #c.SetFullFrame()

                        if self.ascom:
                            c.StartExposure(exposure_time, imtypeb)     #True indicates Light Frame.  Maxim Difference of code
                        elif self.maxim:
                            c.Expose(exposure_time, imtypeb)
                        else:
                            print("Something terribly wrong!")
                        self.t9 = time.time()
                        #We go here to keep this subroutine a reasonable length.
                        self.finish_exposure(exposure_time,  frame_type, count - seq, p_next_filter, p_next_focus, p_dither, \
                                             gather_status, do_sep, no_AWS, dist_x, dist_y, quick=quick)
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
                        gather_status=True, do_sep=False, no_AWS=False, start_x=None, start_y=None, quick=False):
        print("Finish exposure Entered:  ", self.af_step, exposure_time, frame_type, counter, ' to go!')
        print(exposure_time, frame_type, counter, p_next_filter, p_next_focus, p_dither, \
                        gather_status, do_sep, no_AWS, start_x, start_y)
        if self.bpt_flag:
            pass
        if gather_status:   #Does this need to be here
            self.post_mnt = []
            self.post_rot = []
            self.post_foc = []
            self.post_ocn = []
        counter = 0
        while True:
            try:
                self.t3 = time.time()
                if self.camera.ImageReady: #and not self.img_available and self.exposing:
                    self.t4 = time.time()
                    print('Time to ImageReady:  ', self.t4 - self.t2, counter)
                    if not quick and gather_status:
                        g_dev['mnt'].get_quick_status(self.post_mnt)  #stage symmetric around exposure
                        g_dev['rot'].get_quick_status(self.post_rot)
                        g_dev['foc'].get_quick_status(self.post_foc)
                        g_dev['ocn'].get_quick_status(self.post_ocn)
                    self.t5 = time.time()
                    if self.maxim:
                        self.camera.SaveImage('Q:\\archive\\gf03\\newest.fits')
                        #Save image with Maxim Fits Header information, then read back with astropy
                    if self.ascom:
#                        if p_next_filter is not None:
#                            print("Post image filter seek here")
#                        if p_next_focus is not None:
#                            print("Post Image focus seek here")
#                        if p_dither:
#                            print("Post image dither step here")
                        img = self.camera.ImageArray
                        img = np.array(img).astype('uint16')   #THIS LINE OF CODE I NECESSARY!
                        #Next line makes the image like those from Default MaximDL
                        img = img.transpose()
                        self.t6 = time.time()
                        #Save image with Fits Header information, then read back with astropy and fill out keywords.
                        hdu = fits.PrimaryHDU(img)
                        hdu1 = fits.HDUList([hdu])
                        try:
                            #This should be a very fast disk.
                            hdu1.writeto('Q:\\archive\\' + 'gf03'+ '\\newest.fits', overwrite=True)
                            #For reasons unclear, this file never seems to close properly.  20191022 WER
                        except:
                            print('Write to newest.fits failed because it is busy, -- reason unknown.')
                            os.remove('Q:\\archive\\' + 'gf03'+ '\\newest.fits')
                            return
                        if not quick:
                            try:
                                ldr_handle = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['d-a-y'] + '\\' + '*low.fits')
                            except:
                                try:
                                    ldr_handle = glob.glob('Q:\\archive\\gf03\\raw_kepler\\' + g_dev['next_day'] + '\\' + '*low.fits')
                                except:
                                    hdu2 = None
                                    print("something went wrong reading in a version of low.fits")
                            hdu2 = fits.open(ldr_handle[0])  #This directory should only have one file.
                            del hdu2[0].header['FILTER']
                            hdu2[0].header['FILTER']= self.current_filter   #Fix bocus filter.
                            hdu2[0].header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                            hdu2[0].header['DATE'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))
                            hdu2[0].header['EXPTIME'] = exposure_time
                            hdu2.writeto('Q:\\archive\\' + 'gf03'+ '\\newest_low.fits', overwrite=True)
                            hdu2.close()
                            os.remove(ldr_handle[0])
                            hdu2 = fits.open('Q:\\archive\\' + 'gf03'+ '\\newest_low.fits')
                        else:
                           hdu2 = None     #No low image is created or saved during a quick operation.

                    #***After this point we no longer care about the camera specific files.
                    if not quick and gather_status:
                        avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                        avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                        avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                        avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                    #print(avg_ocn, avg_foc, avg_rot, avg_mnt)

                    #counter = 0
                    try:
                        #Save the raw data after adding fits header information.
#                        if not quick:
#                            #hdu1 =  fits.open('Q:\\archive\\gf03\\newest.fits')
#                            hdu = hdu1[0]   #get the Primary header and date
#                            #hdu.data = hdu.data.astype('uint16')    #This is probably redundant but forces unsigned storage
#                            #self.hdu_data1 = hdu.data.copy()   #NEVER USED??
#                        else:
#                            hdu = hdu1[0]
                        hdu = hdu1[0]
                        hdu.header['BUNIT']    = 'adu'
                        hdu.header['DATE-OBS'] = datetime.datetime.isoformat(datetime.datetime.utcfromtimestamp(self.t2))   
                        hdu.header['EXPTIME']  = exposure_time   #This is the exposure in seconds specified by the user                  
                        hdu.header['EXPOSURE'] = exposure_time   #Ideally this needs to be calculated from actual times                    
                        hdu.header['FILTER ']  = self.current_filter
                        hdu.header['FILTEROF']  = self.current_offset
                        if g_dev['scr'].dark_setting == 'Light':
                            hdu.header['SCREEN'] = g_dev['scr'].bright_setting
                        hdu.header['IMAGETYP'] = 'Light Frame'
                        if self.maxim:
                            hdu.header['SET-TEMP'] = round(self.camera.TemperatureSetpoint, 3)                 
                            hdu.header['CCD-TEMP'] = round(self.camera.Temperature, 3)
                        if self.ascom:
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
                        hdu.header['OBSERVER'] = 'WER DEV'                                                            
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
        
                        hdu.header['DETECTOR'] = "G-Sense CMOS 4040"
                        hdu.header['CAMNAME'] = 'gf03'
                        hdu.header['CAMANUF'] = 'Finger Lakes Instrumentation'
#                        try:
#                            hdu.header['GAIN'] = g_dev['cam'].camera.gain
                        #print('Gain was read;  ', g_dev['cam'].camera.gain)
#                        except:                                
#                            hdu.header['GAIN'] = 1.18
                        hdu.header['GAINUNIT'] = 'e-/ADU'
                        hdu.header['GAIN'] = 2.2   #20190911   LDR-LDC mode set in ascom
                        hdu.header['RDNOISE'] = 4.86
                        hdu.header['CMOSCAM'] = True
                        hdu.header['CMOSMODE'] = 'HDR-LDC'  #Need to figure out how to read this from setup.
                        hdu.header['SATURATE'] = 3600
                        hdu.header['PIXSCALE'] = 0.85*self.camera.BinX

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
                        
                        
                        if not quick:
                            hdu1.writeto(raw_path + raw_name00, overwrite=True)
                            hdu1.close()
                            text = open(im_path + text_name, 'w')
                            text.write(str(hdu.header))
                            text.close()
                        text_data_size = len(str(hdu.header)) - 2048
                        raw_data_size = hdu.data.size

                        print("\n\Finish-Exposure is complete:  " + raw_name00, raw_data_size, '\n')
                        calibrate(hdu, hdu2[0], lng_path, frame_type, start_x=start_x, start_y=start_y, quick=quick)
                    
                        if not quick:
                            hdu1.writeto(cal_path + cal_name, overwrite=True)   #THis needs qualifying and should not be so general.
                            hdu1.writeto(im_path + raw_name01, overwrite=True)
##                        if b.data.shape[1] == 2098:
##                            overscan = hdu.data[:, 2048:]
##                            medover = np.median(overscan)
##                            print('Overscan median =  ', medover)
##                            hdu.data = hdu.data[:, :2048] - medover
##                        else:
##                            hdu.data = hdu.data # - 1310.0     #This deaals with all subframes
                        do_sep = False
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
                            
                            try:
                                spot = np.median(spot[-5:])
                                print(result, '\n', 'Spot and flux:  ', spot, source['cflux'], '\n')
                            except:
                                pass                            
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
                            self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                            if not quick:
                                self.enqueue_image(text_data_size, im_path, text_name)
                                self.enqueue_image(db_data_size, im_path, db_name)
                                self.enqueue_image(raw_data_size, im_path, raw_name01)                       
                        self.img = None
                        #hdu.close()
                        hdu = None
                        try:
                            'Q:\\archive\\' + 'gf03'+ '\\newest.fits'
                            'Q:\\archive\\' + 'gf03'+ '\\newest_low.fits'
                        except:
                            print(' 2 Could not remove newest.fits.')
                    except:   
                        print('Header assembly block failed.')
                        self.t7 = time.time()
                        breakpoint()
                    return
                else:               #here we are in waiting for imageReady loop and could send status and check Queue
                    counter += 1
                    time.sleep(.01)                    
                    #if not quick:
                    #   g_dev['obs'].update()    #This keeps status alive while camera is looping
                    continue
                self.t7= time.time()
            except:
                counter += 1
                time.sleep(.01)
                #This shouldbe counted down for a loop cancel.
                continue
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
        try:
            hdu2.close()
            hdu2 = none
        except:
            pass
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
    config = {    'camera': {
        'camera1': {
            'parent': 'telescope1',
            'alias': 'gf03',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Kepler 4040',
            'driver':  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',
            'settings': {
                'x_start':  '0',
                'y_start':  '0',
                'x_width':  '4096',
                'y_width':  '4096',
                'overscan_x': '0',
                'overscan_y': '0',
                'north_offset': '0.0',
                'east_offset': '0.0',
                'rotation': '0.0',
                'min_exposure': '0.200',
                'max_exposure': '300.0',
                'can_subframe':  'true',
                'is_cmos':  'true',
                'area': ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
                'bin_modes':  [['1', '1'], ['2', '2']],     #Meaning no binning if list has only one entry
                                               #otherwise enumerate all xy modes: [[1,1], [1,2], ...[3,2]...]
                'has_darkslide':  'false',
                'has_screen': 'true',
#                'darkslide':  ['Auto', 'Open', 'Close'],
                'screen_settings':  {
                    'screen_saturation':  '157.0',
                    'screen_x4':  '-4E-12',  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  '3E-08',
                    'screen_x2':  '-9E-05',
                    'screen_x1':  '.1258',
                    'screen_x0':  '8.683' 
                },
            },
        },
                   
    },
   }
    req = {'time': 2,  'alias': 'gf03', 'image_type': 'Light', 'filter': 2}
    opt = {'size': 100}
    #cam = Camera('Maxim.CCDCamera', "gf03", config)
    cam = Camera('ASCOM.FLI.Kepler.Camera', "gf03", config)
    cam.expose_command(req, opt, gather_status=False, quick=True)

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
    



        
    
