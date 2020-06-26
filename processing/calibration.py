# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 20:08:38 2019
wer
"""
import time
import threading
import queue
import numpy as np
#import matplotlib.pyplot as plt
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
'''
Comments are obsolete as of 20200624  WER
This is kludge code just to quickly partially calibrate images for the AWS 768^2 postage.
WE need to re-think how this will work, ie use BONSAI locally or not.

Name of module is a bit deceptive, this is more like 'create_postage'.
'''


#Here we set up the arriving queue of data. but at the end of the module load


#These are essentially cached supers.  Probably they could be class variables. use memoize module??
super_bias = None
super_bias_2 = None
super_dark = None
super_dark_2 = None
hotmap = None
hotpix = None
super_flat_w = None
super_flat_air = None
super_flat_B= None
super_flat_V = None
super_flat_R = None
super_flat_EXO = None
super_flat_g = None
super_flat_r = None
super_flat_i = None
super_flat_O3 = None
super_flat_HA = None
super_flat_N2 = None
super_flat_S2 = None
dark_exposure_level = 0.0



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
    if loud: print('Central 10% Mean, std:  ', round(img_mean, 1), round(img_std, 2))
    return round(img_mean, 2), round(img_std, 2)

def median8(img, hot_pix):
    #print('1: ',img_img.data)
    axis1 = img.shape[0]
    axis2 = img.shape[1]

    img = img
    for pix in range(len(hot_pix[0])):
        iy = hot_pix[0][pix]
        ix = hot_pix[1][pix]
        if (0 < iy < axis1 - 1) and (0 < ix < axis2 - 1):   #Needs fixing for boundary condtions.
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

#This is a brute force linear version. This needs to be more sophisticated and camera independent.

def calibrate (hdu, lng_path, frame_type='light', quick=False):
    #These variables are gloal in the sense they persist between calls (memoized so to speak, should use that facility.)
    global super_bias, super_bias_2, super_dark, super_dark_2, hotmap, hotpix, super_flat_air, super_flat_w, \
        super_flat_B, super_flat_V, super_flat_R, super_flat_EXO, super_flat_g, super_flat_r, super_flat_i, \
        super_flat_O3, super_flat_HA, super_flat_N2, super_flat_S2, dark_exposure_level
    loud = True
    #This needs to deal with caching different binnings as well.  And do we skip all this for a quick
    if not quick:
        if super_bias is None:
            try:
                sbHdu = fits.open(lng_path + 'mb_1.fits')
                super_bias = sbHdu[0].data#.astype('float32')
                #Temp fix
                #fix = np.where(super_bias > 400)
                #super_bias[fix] = int(super_bias.mean())
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'mb_1.fits', 'Loaded')
            except:
                quick_bias = False
                print('WARN: No Bias_1 Loaded.')
        if super_bias_2 is None:
            try:
                sbHdu = fits.open(lng_path + 'mb_2.fits')
                super_bias_2 = sbHdu[0].data#.astype('float32')
                #Temp fix
                #fix = np.where(super_bias > 400)
                #super_bias[fix] = int(super_bias.mean())
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'mb_2.fits', 'Loaded')
            except:
                quick_bias = False
                print('WARN: No Bias_2 Loaded.')
        # if super_dark_90 is None:
        #     try:
        #         sdHdu = fits.open(lng_path + 'md_1_90.fits')
        #         dark_90_exposure_level = sdHdu[0].header['EXPTIME']
        #         super_dark_90  = sdHdu[0].data.astype('float32')
        #         print('sdark_90:  ', super_dark_90.mean())
        #         sdHdu.close()
        #         #fix = np.where(super_dark_90 < 0)
        #         #super_dark_90[fix] = 0
        #         quick_dark_90 = True
        #         print(lng_path + 'md_1_90.fits', 'Loaded')
        #     except:
        #         quick_dark_90 = False
        #         print('WARN: No dark_1_90 Loaded.')
        if super_dark is None:
            try:
                sdHdu = fits.open(lng_path + 'md_1_360.fits')
                dark_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark = sdHdu[0].data/dark_exposure_level  #Convert to adu/sec
                super_dark = super_dark.astype('float32')
                print('sdark:  ', super_dark.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark= True
                dark_exposure_level = 360.
                print(lng_path + 'md_1_360.fits', 'Loaded')
            except:
               quick_dark = False
               print('WARN: No dark_1 Loaded.')
        if super_dark_2 is None:
            try:
                sdHdu = fits.open(lng_path + 'md_2_120.fits')
                dark_2_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_2  = sdHdu[0].data/dark_2_exposure_level  #Converto to ADU/sec
                super_dark_2 = super_dark_2.astype('float32')
                print('sdark_2:  ', super_dark_2.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_2 = True
                dark_exposure_level = 120.
                print(lng_path + 'md_2_120.fits', 'Loaded')
            except:
                quick_dark_2 = False
                print('WARN: No dark_2 Loaded.')

        if super_flat_w is None:
            try:
                sfHdu = fits.open(lng_path + 'mf_w.fits')
                super_flat_w = sfHdu[0].data.astype('float32')
                quick_flat_w = True
                sfHdu.close()
                if loud: print(lng_path + 'm1_w.fits', 'Loaded')
            except:
                quick_flat_w = False
                print('WARN: No W Flat/Lum Loaded.')
        if super_flat_HA is None:
            try:
                sfHdu = fits.open(lng_path + 'mf_HA.fits')
                super_flat_HA = sfHdu[0].data#.astype('float32')
                quick_flat_HA = True
                sfHdu.close()
                if loud: print(lng_path + 'mf_HA.fits', 'Loaded')
            except:
                quick_flat_HA = False
                if not quick: print('WARN: No HA Flat/Lum Loaded.')

#        if hotmap_360 is None:
#            try:
#                shHdu = fits.open(lng_path + 'hdr_hotmap_360.fits')
#                hotmap_360 = shHdu[0].data#.astype('uint16')
#                shHdu.close()
#                quick_hotmap_360 = True
#                hotpix_360 = np.where(hotmap_360 > 60)  #This is a temp simplifcation
#                print(lng_path + 'hdr_hotmap_360.fits', 'Loaded, Length = ', len(hotpix_360[0]))
#            except:
            quick_hotmap_360= False
#                if not quick: print('Hotmap_360 failed to load.')

    #this whole area need to be re-thought to better cache and deal with a mix of flats and binnings  Right now partial
    #brute force.
    while True:   #Use break to drop through to exit.  i.e., do not calibrate frames we are acquring for calibration.

        cal_string = ''
        if not quick:
            img = hdu.data.astype('float32')
            mn, std = imageStats(img, False)
            if loud: print('InputImage (high):  ', imageStats(img, False))
        else:
            img = hdu.data
        if frame_type == 'bias':
            break    #  Do not bias calibrate a bias.
        if super_bias is not None :   #NB Need to qualify with binning
            img = img - super_bias[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick:
                if loud: print('QuickBias result (high):  ', imageStats(img, False))
            cal_string += 'B'
        data_exposure_level = hdu.header['EXPTIME']
        if frame_type == 'dark':
            break   #  Do not dark calibrate a dark.

        # NB Qualify if dark exists and by binning
        #Need to verify dark is not 0 seconds long!
        if super_dark is not None:  #  and quick_dark_90:
            if data_exposure_level > dark_exposure_level:
                print("WARNING:  Master dark being used over-scaled")
            img =  (img - super_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1]) \
                                ]*data_exposure_level)
            if not quick:
                print('QuickDark: ', imageStats(img, loud))
            cal_string += ', D'
        else:
            if not quick: print('INFO:  Light exposure too small, skipped this step.')
        img_filter = hdu.header['FILTER']
        if frame_type[-4:]  == 'flat':   #  Note frame type ends 'flat, e.g arc_flat, screen_flat, sky_flat
            break       #  Do not fla calibrate a flat.
        do_flat = False
        if img_filter in ['w', 'W']:
            do_flat = True
            s_flat = super_flat_w
        elif img_filter in ['HA', 'Ha', 'ha']:
            do_flat = True
            s_flat = super_flat_HA
        else:
            do_flat = False
        if do_flat: # and not g_dev['seq'].active_script == 'make_superscreenflats':
            try:
                img = img/s_flat
                cal_string +=', SCF'
            except:
                print("Flat field math failed.")
            if not quick: print('QuickFlat result (high):  ', imageStats(img, loud))


        #median8(img, h_pix)
        #cal_string +=', HP'
        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')  #This is meant to catch an image cast to 'float64'
    fix = np.where(hdu.data < 0)
    if not quick: print('# of < 0  pixels:  ', len(fix[0]))  #  Do not change values here.
    hdu.data[fix] = 0
    # big_max = hdu.data.max()
    # if big_max > 65535.:   #This scaling is problematic.
    #     hdu.data = hdu.data*(65530./big_max)
    return round((hdu.data.mean() + np.median(hdu.data))/2, 1)

    '''
    Notes:

    Use a central patch to define the tri-mean value.
    Need to integrate overscan bias correct and trim.
    Expand to other binnings or design to cache 1 or 2 prior binnings,
    or build a special faster routine just for autofocus reduction.


    '''





if __name__ == '__main__':
    pass

