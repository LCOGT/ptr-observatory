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
super_dark_2_long = None
hot_map = None
hot_pix = None
screen_flat_w = None
screen_flat_air = None
screen_flat_JU = None
screen_flat_JB = None
screen_flat_JV = None
screen_flat_Rc = None
screen_flat_Ic = None
screen_flat_EXO = None
screen_flat_NIR = None
screen_flat_up = None
screen_flat_gp = None
screen_flat_rp = None
screen_flat_ip = None
screen_flat_zp = None
screen_flat_z = None
screen_flat_y = None
screen_flat_O3 = None
screen_flat_HA = None
screen_flat_N2 = None
screen_flat_S2 = None
screen_flat_CR = None
screen_flat_PL = None
screen_flat_PR = None
screen_flat_PG = None
screen_flat_PB = None
screen_flat_EXO = None
screen_flat_dif = None
#
sky_flat_w = None
sky_flat_air = None
sky_flat_JU= None
sky_flat_JB= None
sky_flat_JV = None
sky_flat_Rc = None
sky_flat_Ic = None
sky_flat_EXO = None
sky_flat_up = None
sky_flat_gp = None
sky_flat_rp = None
sky_flat_ip = None
sky_flat_zp = None
sky_flat_z = None
sky_flat_y = None
sky_flat_O3 = None
sky_flat_HA = None
sky_flat_N2 = None
sky_flat_S2 = None
sky_flat_CR = None
sky_flat_PL = None
sky_flat_PR = None
sky_flat_PG = None
sky_flat_PB = None
sky_flat_NIR = None
sky_flat_EXO = None
sky_flat_air = None
sky_flat_dif = None
dark_exposure_level = 0.0
dark_2_exposure_level = 0
dark_long_exposure_level = 0.0


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
    global super_bias, super_bias_2, super_dark, super_dark_2, hot_map, hot_pix, screen_flat_air, screen_flat_w, screen_flat_JU, \
        screen_flat_JB, screen_flat_JV, screen_flat_Rc, screen_flat_Ic, screen_flat_up, screen_flat_gp, screen_flat_rp, screen_flat_ip, \
        screen_flat_zp, screen_flat_z, screen_flat_y, screen_flat_O3, screen_flat_HA, screen_flat_N2, screen_flat_S2, screen_flat_EXO, \
        screen_flat_PL ,screen_flat_PB, screen_flat_PG, screen_flat_PR, screen_flat_NIR,  screen_flat_CR, screen_flat_dif,  \
        dark_exposure_level, super_dark_2_long, dark_2_exposure_level
    loud = False

    #This needs to deal with caching different binnings as well.  And do we skip all this for a quick
    if not quick:
        if super_bias is None:
            try:
                sbHdu = fits.open(lng_path + 'b_1-10.fits')
                super_bias = sbHdu[0].data#.astype('float32')
                pedastal = sbHdu[0].header['PEDASTAL']
                super_bias = super_bias + pedastal
                #Temp fix
                #fix = np.where(super_bias > 400)
                #super_bias[fix] = int(super_bias.mean())
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'b_1-10.fits', 'Loaded')
            except:
                quick_bias = False
                #print('WARN: No Bias_1 Loaded.')

        if super_bias_2 is None:
            try:
                sbHdu = fits.open(lng_path + 'b_2.fits')
                super_bias_2 = sbHdu[0].data#.astype('float32')
                pedastal = sbHdu[0].header['PEDASTAL']
                super_bias_2 = super_bias_2 + pedastal
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'b_2.fits', 'Loaded')
            except:
                quick_bias = False
                g_dev['obs'].send_to_user(" No bias_2 loaded.", p_level ='WARNING')

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
                sdHdu = fits.open(lng_path + 'd_1_180-10.fits')
                dark_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark = sdHdu[0].data/dark_exposure_level  #Convert to adu/sec
                super_dark = super_dark.astype('float32')
                if loud: print('sdark:  ', super_dark.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark= True
                if loud: print(lng_path + 'd_1_180-10.fits', 'Loaded')
            except:
               quick_dark = False
               if loud: print('WARN: No dark_1 Loaded.')
        if super_dark_2 is None:
            try:
                sdHdu = fits.open(lng_path + 'd_2.fits')
                dark_2_exposure_level = sdHdu[0].header['EXPTIME']

                super_dark_2  = sdHdu[0].data/dark_2_exposure_level  #Converto to ADU/sec
                super_dark_2 = super_dark_2.astype('float32')
                if loud: print('sdark_2:  ', super_dark_2.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_2 = True
                if loud: print(lng_path + 'd_2.fits', 'Loaded')
            except:
                quick_dark_2 = False
                if loud: print('WARN: No dark_2 Loaded.')
        if super_dark_2_long is None:
            try:
                sdHdu = fits.open(lng_path + 'd_2_long.fits')
                dark_2_long_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_2_long  = sdHdu[0].data/dark_2_long_exposure_level  #Converto to ADU/sec
                super_dark_2_long = super_dark_2_long.astype('float32')
                if loud: print('sdark_2:  ', super_dark_2_long.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_2_long = True
                if loud: print(lng_path + 'd_2_long.fits', 'Loaded')
            except:
                quick_dark_2_long = False
                if loud: print('WARN: No dark_2_long Loaded.')

        if screen_flat_w is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_w.fits')
                screen_flat_w = sfHdu[0].data.astype('float32')
                quick_flat_w = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_w.fits', 'Loaded')
            except:
                quick_flat_w = False
                if loud: print('WARN: No w Flat/Lum Loaded.')
        if screen_flat_JU is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_JU.fits')
                screen_flat_JU = sfHdu[0].data.astype('float32')
                quick_flat_JU = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_JU.fits', 'Loaded')
            except:
                quick_flat_JU = False
                if loud: print('WARN: No JU Flat/Lum Loaded.')
        if screen_flat_JB is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_JB.fits')
                screen_flat_JB = sfHdu[0].data.astype('float32')
                quick_flat_JB = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_JB.fits', 'Loaded')
            except:
                quick_flat_JB = False
                if loud: print('WARN: No B Flat/Lum Loaded.')
        if screen_flat_JV is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_JV.fits')
                screen_flat_JV = sfHdu[0].data.astype('float32')
                quick_flat_JV = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_JV.fits', 'Loaded')
            except:
                quick_flat_JV = False
                if loud: print('WARN: No V Flat/Lum Loaded.')
        if screen_flat_Rc is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_Rc.fits')
                screen_flat_Rc = sfHdu[0].data.astype('float32')
                quick_flat_Rc = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_Rc.fits', 'Loaded')
            except:
                quick_flat_Rc = False
                if loud: print('WARN: No Rc Flat/Lum Loaded.')
        if screen_flat_Ic is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_Ic.fits')
                screen_flat_Ic = sfHdu[0].data.astype('float32')
                quick_flat_Ic = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_Ic.fits', 'Loaded')
            except:
                quick_flat_Ic = False
                if loud: print('WARN: No Ic Flat/Lum Loaded.')
        if screen_flat_up is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_up.fits')
                screen_flat_up = sfHdu[0].data.astype('float32')
                quick_flat_up = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_up.fits', 'Loaded')
            except:
                quick_flat_up = False
                if loud: print('WARN: No up Flat/Lum Loaded.')
        if screen_flat_gp is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_gp.fits')
                screen_flat_gp = sfHdu[0].data.astype('float32')
                quick_flat_gp = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_gp.fits', 'Loaded')
            except:
                quick_flat_gp = False
                if loud: print('WARN: No gp Flat/Lum Loaded.')
        if screen_flat_rp is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_rp.fits')
                screen_flat_rp = sfHdu[0].data.astype('float32')
                quick_flat_rp = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_rp.fits', 'Loaded')
            except:
                quick_flat_rp = False
                if loud: print('WARN: No rp Flat/Lum Loaded.')
        if screen_flat_ip is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_ip.fits')
                screen_flat_ip = sfHdu[0].data.astype('float32')
                quick_flat_ip = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_ip.fits', 'Loaded')
            except:
                quick_flat_ip = False
                if loud: print('WARN: No ip Flat/Lum Loaded.')
        if screen_flat_zp is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_zp.fits')
                screen_flat_zp = sfHdu[0].data.astype('float32')
                quick_flat_zp = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_zp.fits', 'Loaded')
            except:
                quick_flat_zp = False
                if loud: print('WARN: No zp Flat/Lum Loaded.')        
        if screen_flat_z is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_z.fits')
                screen_flat_z = sfHdu[0].data.astype('float32')
                quick_flat_z = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_z.fits', 'Loaded')
            except:
                quick_flat_z = False
                if loud: print('WARN: No z Flat/Lum Loaded.')
        if screen_flat_y is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_y.fits')
                screen_flat_y = sfHdu[0].data.astype('float32')
                quick_flat_y = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_y.fits', 'Loaded')
            except:
                quick_flat_y = False
                if loud: print('WARN: No y Flat/Lum Loaded.')
        if screen_flat_HA is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_HA.fits')
                screen_flat_HA = sfHdu[0].data.astype('float32')
                quick_flat_HA = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_HA.fits', 'Loaded')
            except:
                quick_flat_HA = False
                if loud: print('WARN: No HA Flat/Lum Loaded.')
        if screen_flat_O3:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_O3.fits')
                screen_flat_O3 = sfHdu[0].data.astype('float32')
                quick_flat_O3 = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_O3.fits', 'Loaded')
            except:
                quick_flat_O3 = False
                if loud: print('WARN: No O3 Flat/Lum Loaded.')
        if screen_flat_N2 is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_N2.fits')
                screen_flat_N2 = sfHdu[0].data.astype('float32')
                quick_flat_N2 = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_N2.fits', 'Loaded')
            except:
                quick_flat_N2 = False
                if loud: print('WARN: No N2 Flat/Lum Loaded.')
        if screen_flat_S2 is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_S2.fits')
                screen_flat_S2 = sfHdu[0].data.astype('float32')
                quick_flat_S2 = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_S2.fits', 'Loaded')
            except:
                quick_flat_S2 = False
                if loud: print('WARN: No S2 Flat/Lum Loaded.')
        if screen_flat_CR is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_CR.fits')
                screen_flat_CR = sfHdu[0].data.astype('float32')
                quick_flat_CR = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_CR.fits', 'Loaded')
            except:
                quick_flat_CR = False
                if loud: print('WARN: No CR Flat/Lum Loaded.')

        if screen_flat_CR is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_CR.fits')
                screen_flat_CR = sfHdu[0].data.astype('float32')
                quick_flat_CR = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_CR.fits', 'Loaded')
            except:
                quick_flat_CR = False
                if loud: print('WARN: No CR Flat/Lum Loaded.')

        if screen_flat_PL is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_PL.fits')
                screen_flat_PL = sfHdu[0].data.astype('float32')
                quick_flat_PL = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_PL.fits', 'Loaded')
            except:
                quick_flat_PL = False
                if loud: print('WARN: No PL Flat/Lum Loaded.')
        if screen_flat_PB is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_PB.fits')
                screen_flat_PB = sfHdu[0].data.astype('float32')
                quick_flat_PB = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_PB.fits', 'Loaded')
            except:
                quick_flat_PB = False
                if loud: print('WARN: No PB Flat/Lum Loaded.')
        if screen_flat_PR is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_PR.fits')
                screen_flat_PR = sfHdu[0].data.astype('float32')
                quick_flat_PR = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_PR.fits', 'Loaded')
            except:
                quick_flat_PR = False
                if loud: print('WARN: No PR Flat/Lum Loaded.')
        if screen_flat_PG is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_PG.fits')
                screen_flat_PG = sfHdu[0].data.astype('float32')

                quick_flat_PG = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_PG.fits', 'Loaded')
            except:
                quick_flat_PG = False
                if loud: print('WARN: No PG Flat/Lum Loaded.')
        if screen_flat_NIR is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_NIR.fits')
                screen_flat_NIR = sfHdu[0].data.astype('float32')
                quick_flat_NIR = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_NIR.fits', 'Loaded')
            except:
                quick_flat_NIR = False
                if loud: print('WARN: No NIR Flat/Lum Loaded.')
        if screen_flat_EXO is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_exo.fits')
                screen_flat_EXO = sfHdu[0].data.astype('float32')
                quick_flat_EXO = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_exo.fits', 'Loaded')
            except:
                quick_flat_EXO = False
                if loud: print('WARN: No EXO Flat/Lum Loaded.')
        if screen_flat_air is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_air.fits')
                screen_flat_air = sfHdu[0].data.astype('float32')
                quick_flat_air = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_air.fits', 'Loaded')
            except:
                quick_flat_air = False
                if loud: print('WARN: No air Flat/Lum Loaded.')
        if screen_flat_dif is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2_dif.fits')
                screen_flat_dif = sfHdu[0].data.astype('float32')
                quick_flat_dif = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2_dif.fits', 'Loaded')
            except:
                quick_flat_dif = False
                if loud: print('WARN: No dif Flat/Lum Loaded.')

        if hot_pix is None:
            try:
                shHdu = fits.open(lng_path + 'h_2.fits')
                hot_map = shHdu[0].data
                hot_pix = np.where(hot_map > 1)
                apply_hot = True
                print(lng_path + 'h_2.fits', 'Loaded')
            except:
                apply_hot = False
                print('WARN: No Hot Map Bin 2 Loaded.')


    while True:   #Use break to drop through to exit.  i.e., do not calibrate frames we are acquring for calibration.
        
            
# =============================================================================
# # =============================================================================
# #           NB NB NB For the moment we have limited bin 1 and sub-frame calibrations
# # =============================================================================
# =============================================================================
      
        start_x = 0
        start_y = 0
        cal_string = ''
        if not quick:
            img = hdu.data.astype('float32')
            pedastal = hdu.header['PEDASTAL']
            img = img + pedastal
            mn, std = imageStats(img, False)
            if loud: print('InputImage (high):  ', imageStats(img, False))
        else:
            img = hdu.data.astype('float32')
            pedastal = hdu.header['PEDASTAL']
            img = img + pedastal
        ix, iy = img.shape
        area  = hdu.header['IMGAREA']
        binning = hdu.header['XBINING']
                           
# =============================================================================
# # =============================================================================
# #           NB NB NB For the moment we have limited bin 1 and sub-frame calibrations
# # =============================================================================
# =============================================================================
        if frame_type in ['bias']:
            break    #  Do not bias calibrate a bias. 
        if super_bias is not None and binning == 1 :
            img = img - super_bias[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick:
                if loud: print('QuickBias_1 result (high):  ', imageStats(img, False))
            cal_string += 'B'
        if super_bias_2 is not None and binning == 2 :
            img = img - super_bias_2[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick:
                if loud: print('QuickBias_2 result (high):  ', imageStats(img, False))
            cal_string += 'B'
        data_exposure_level = hdu.header['EXPTIME']
        if frame_type == 'dark':
            break   #  Do not dark calibrate a dark.
        # NB NB NB THis data Exposure level code seems wrong.
        # NB Qualify if dark exists and by binning
        #Need to verify dark is not 0 seconds long!
        if super_dark is not None and binning == 1:
            if data_exposure_level > dark_exposure_level:
                if loud: print("WARNING:  Master dark being used over-scaled")
            img =  (img - super_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1]) \
                                ]*data_exposure_level)
            if not quick:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         
                if loud: print('QuickDark_1: ', imageStats(img, loud))
            cal_string += ', D'
        elif super_dark_2 is not None and binning == 2:
            if data_exposure_level > dark_2_exposure_level:
                if loud: print("WARNING:  Master dark being used over-scaled")
            img =  (img - super_dark_2[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1]) \
                                ]*data_exposure_level)
            if not quick:
                if loud: print('QuickDark_2: ', imageStats(img, loud))
            cal_string += ', D'
        else:
            if not quick: print('INFO:  Dark correction skipped.')
        img_filter = hdu.header['FILTER']
        if frame_type[-4:]  == 'flat':   #  Note frame type ends 'flat, e.g arc_flat, screen_flat, sky_flat
            break       #  Do not calibrate a flat.
        do_flat = True   #20210224@18:13

        if binning == 2 :
            if img_filter in ['w', 'W']:
                do_flat = True
                scr_flat = screen_flat_w
            elif img_filter in ['l', 'L', 'pl', 'PL', 'LUM']:
                do_flat = True
                scr_flat = screen_flat_PL
            elif img_filter in ['PR', 'R', 'RED']:
                do_flat = True
                scr_flat = screen_flat_PR
            elif img_filter in ['PG', 'G', 'GREEN']:
                do_flat = True
                scr_flat = screen_flat_PG
            elif img_filter in ['PB', 'B', 'BLUE']:
                do_flat = True
                scr_flat = screen_flat_PB
            elif img_filter in ['NIR', 'nir']:
                do_flat = True
                scr_flat = screen_flat_NIR
            elif img_filter in ['JU']:
                do_flat = True
                scr_flat = screen_flat_JU
            elif img_filter in ['JB']:
                do_flat = True
                scr_flat = screen_flat_JB
            elif img_filter in ['JV']:
                do_flat = True
                scr_flat = screen_flat_JV
            elif img_filter in ['JR', 'Rc', 'RC']:
                do_flat = True
                scr_flat = screen_flat_Rc
            elif img_filter in ['JI', 'Ic', 'IC']:
                do_flat = True
                scr_flat = screen_flat_Ic
            elif img_filter in ['up']:
                do_flat = True
                scr_flat = screen_flat_up
            elif img_filter in ['gp']:
                do_flat = True
                scr_flat = screen_flat_gp
            elif img_filter in ['rp']:
                do_flat = True
                scr_flat = screen_flat_rp
            elif img_filter in ['ip']:
                do_flat = True
                scr_flat = screen_flat_ip
            elif img_filter in ['zp']:
                do_flat = True
                scr_flat = screen_flat_zp
            elif img_filter in ['zs']:
                do_flat = True
                scr_flat = screen_flat_z
            elif img_filter in ['Y']:
                do_flat = True
                scr_flat = screen_flat_y
            elif img_filter in ['HA', 'Ha', 'ha']:
                do_flat = True
                scr_flat = screen_flat_HA
            elif img_filter in ['O3', 'OIII', 'O-III']:
                do_flat = True
                scr_flat = screen_flat_O3
            elif img_filter in ['S2', 'SII', 'S-II']:
                do_flat = True
                scr_flat = screen_flat_S2
            elif img_filter in ['N2', 'NII', 'N-II']:
                do_flat = True
                scr_flat = screen_flat_N2
            elif img_filter in ['CR']:
                do_flat = True
                scr_flat = screen_flat_CR
            elif img_filter in ['EXO', 'exo', 'Exo']:
                do_flat = True
                scr_flat = screen_flat_EXO
            elif img_filter in ['air', 'AIR', 'Air']:
                do_flat = True
                scr_flat = screen_flat_air
            elif img_filter in ['dif', 'DIF', 'Dif']:
                do_flat = True
                scr_flat = screen_flat_dif
            else:
                do_flat = False
        if do_flat and binning == 2: # and not g_dev['seq'].active_script == 'make_superscreenflats':
            try:

                img = img/scr_flat
                cal_string +=', SCF'
            except:
                if loud: print("Flat field math failed.")
            if not quick: 
                if loud:  print('QuickFlat result:  ', imageStats(img, loud))


        # if apply_hot and binning == 2:
        #     try:
        #         #hot_pix = np.where(super_dark_2 > super_dark_2.std()) #20210225 removed _long  #REmoved 20210821  
        #         median8(img, hot_pix)
        #         cal_string += ', H'

        #     except:
        #         print("Hot pixel correction failed.")
        #     if not quick: 
        #         if loud: print('Hot Pixel result:  ', imageStats(img, loud))
        #     try:
        #         cold_pix = np.where(img <= -img.std())
        #         median8(img, cold_pix)
        #     except:
        #         print("Cold pixel correction failed.")


        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')  #This is meant to catch an image cast to 'float64'
    fix = np.where(hdu.data < 0)
    if loud: print('# of < 0  pixels:  ', len(fix[0]))  #  Do not change values here.
    hdu.data[fix] = 0
    big_max = hdu.data.max()
    if loud: print("Max data value is:  ", big_max)
    fix = np.where(hdu.data > 65530)
    hdu.data[fix] = 65530.
    hdu.data = hdu.data.astype('uint16')  #NB NB NB Why this step??
    result = {}
    result['error'] = False
    result['mean_focus'] = None
    result['mean_rotation'] = None
    result['FWHM'] = None
    result['half_FD'] = None
    result['patch'] = round((hdu.data.mean() + np.median(hdu.data))/2, 1)
    result['temperature'] = None
    g_dev['obs'].send_to_user('Calibration complete.', p_level='INFO')
    return result


    '''
    Notes:

    Use a central patch to define the bi-mean value.
    Need to integrate overscan bias correct and trim.
    Expand to other binnings or design to cache 1 or 2 prior binnings,
    or build a special faster routine just for autofocus reduction.


    '''





if __name__ == '__main__':
    pass

