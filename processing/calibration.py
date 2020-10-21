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
hot_map = None
hot_pix = None
screen_flat_w = None
screen_flat_air = None
screen_flat_B= None
screen_flat_V = None
screen_flat_R = None
screen_flat_EXO = None
screen_flat_gp = None
screen_flat_rp = None
screen_flat_ip = None
screen_flat_O3 = None
screen_flat_HA = None
screen_flat_N2 = None
screen_flat_S2 = None
screen_flat_EXO = None
screen_flat_air = None
sky_flat_w = None
sky_flat_air = None
sky_flat_B= None
sky_flat_V = None
sky_flat_R = None
sky_flat_EXO = None
sky_flat_gp = None
sky_flat_rp = None
sky_flat_ip = None
sky_flat_O3 = None
sky_flat_HA = None
sky_flat_N2 = None
sky_flat_S2 = None
sky_flat_EXO = None
sky_flat_air = None
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
    global super_bias, super_bias_2, super_dark, super_dark_2, hot_map, hot_pix, screen_flat_air, screen_flat_w, \
        screen_flat_B, screen_flat_V, screen_flat_R, screen_flat_gp, screen_flat_rp, screen_flat_ip, \
        screen_flat_O3, screen_flat_HA, screen_flat_N2, screen_flat_S2, screen_flat_EXO, screen_flat_air, \
        dark_exposure_level
    loud = False

    #This needs to deal with caching different binnings as well.  And do we skip all this for a quick
    if not quick:
        if super_bias is None:
            try:
                sbHdu = fits.open(lng_path + 'fb_1-4.fits')
                super_bias = sbHdu[0].data#.astype('float32')
                pedastal = sbHdu[0].header['PEDASTAL']
                super_bias = super_bias + pedastal
                #Temp fix
                #fix = np.where(super_bias > 400)
                #super_bias[fix] = int(super_bias.mean())
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'fb_1-4.fits', 'Loaded')
            except:
                quick_bias = False
                print('WARN: No Bias_1 Loaded.')
                breakpoint()
        if super_bias_2 is None:
            try:
                sbHdu = fits.open(lng_path + 'fb_2-4.fits')
                super_bias_2 = sbHdu[0].data#.astype('float32')
                pedastal = sbHdu[0].header['PEDASTAL']
                super_bias_2 = super_bias_2 + pedastal
                sbHdu.close()
                quick_bias = True
                if loud: print(lng_path + 'fb_2-4.fits', 'Loaded')
            except:
                quick_bias = False
                print('WARN: No Bias_2 Loaded.')
                breakpoint()
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
                sdHdu = fits.open(lng_path + 'fd_1_120-4.fits')
                dark_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark = sdHdu[0].data/dark_exposure_level  #Convert to adu/sec
                super_dark = super_dark.astype('float32')
                if loud: print('sdark:  ', super_dark.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark= True
                dark_exposure_level = 360.
                if loud: print(lng_path + 'fd_1_120-4.fits', 'Loaded')
            except:
               quick_dark = False
               if loud: print('WARN: No dark_1 Loaded.')
        if super_dark_2 is None:
            try:
                sdHdu = fits.open(lng_path + 'fd_2_120-4.fits')
                dark_2_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_2  = sdHdu[0].data/dark_2_exposure_level  #Converto to ADU/sec
                super_dark_2 = super_dark_2.astype('float32')
                if loud: print('sdark_2:  ', super_dark_2.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_2 = True
                dark_exposure_level = 120.
                if loud: print(lng_path + 'fd_2_120-4.fits', 'Loaded')
            except:
                quick_dark_2 = False
                if loud: print('WARN: No dark_2 Loaded.')

        if screen_flat_w is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2w.fits')
                screen_flat_w = sfHdu[0].data.astype('float32')
                quick_flat_w = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2w.fits', 'Loaded')
            except:
                quick_flat_w = False
                if loud: print('WARN: No W Flat/Lum Loaded.')
        if screen_flat_B is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2B.fits')
                screen_flat_B = sfHdu[0].data.astype('float32')
                quick_flat_B = True
                sfHdu.close()
                if loud: print(lng_path + 'f1_2B.fits', 'Loaded')
            except:
                quick_flat_B = False
                if loud: print('WARN: No B Flat/Lum Loaded.')
        if screen_flat_V is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2V.fits')
                screen_flat_V = sfHdu[0].data.astype('float32')
                quick_flat_V = True
                sfHdu.close()
                if loud: print(lng_path + 'f1_2V.fits', 'Loaded')
            except:
                quick_flat_V = False
                if loud: print('WARN: No V Flat/Lum Loaded.')
        if screen_flat_R is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2R.fits')
                screen_flat_R = sfHdu[0].data.astype('float32')
                quick_flat_R = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2R.fits', 'Loaded')
            except:
                quick_flat_R = False
                if loud: print('WARN: No R Flat/Lum Loaded.')
        if screen_flat_gp is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2gp.fits')
                screen_flat_gp = sfHdu[0].data.astype('float32')
                quick_flat_gp = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2gp.fits', 'Loaded')
            except:
                quick_flat_gp = False
                if loud: print('WARN: No gp Flat/Lum Loaded.')
        if screen_flat_rp is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2rp.fits')
                screen_flat_rp = sfHdu[0].data.astype('float32')
                quick_flat_rp = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2rp.fits', 'Loaded')
            except:
                quick_flat_rp = False
                if loud: print('WARN: No rp Flat/Lum Loaded.')
        if screen_flat_ip is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2ip.fits')
                screen_flat_ip = sfHdu[0].data.astype('float32')
                quick_flat_ip = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2ip.fits', 'Loaded')
            except:
                quick_flat_ip = False
                if loud: print('WARN: No ip Flat/Lum Loaded.')
        if screen_flat_HA is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2HA.fits')
                screen_flat_HA = sfHdu[0].data.astype('float32')
                quick_flat_HA = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2HA.fits', 'Loaded')
            except:
                quick_flat_HA = False
                if loud: print('WARN: No HA Flat/Lum Loaded.')
        if screen_flat_O3:
            try:
                sfHdu = fits.open(lng_path + 'ff_2O3.fits')
                screen_flat_O3 = sfHdu[0].data.astype('float32')
                quick_flat_O3 = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2O3.fits', 'Loaded')
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
                sfHdu = fits.open(lng_path + 'ff_2S2.fits')
                screen_flat_S2 = sfHdu[0].data.astype('float32')
                quick_flat_S2 = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2S2.fits', 'Loaded')
            except:
                quick_flat_S2 = False
                if loud: print('WARN: No S2 Flat/Lum Loaded.')
        if screen_flat_EXO is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2EXO.fits')
                screen_flat_EXO = sfHdu[0].data.astype('float32')
                quick_flat_EXO = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2EXO.fits', 'Loaded')
            except:
                quick_flat_EXO = False
                if loud: print('WARN: No EXO Flat/Lum Loaded.')
        if screen_flat_air is None:
            try:
                sfHdu = fits.open(lng_path + 'ff_2air.fits')
                screen_flat_air = sfHdu[0].data.astype('float32')
                quick_flat_air = True
                sfHdu.close()
                if loud: print(lng_path + 'ff_2air.fits', 'Loaded')
            except:
                quick_flat_air = False
                if loud: print('WARN: No air Flat/Lum Loaded.')
        try:
            shHdu = fits.open(lng_path + 'fh_2-4.fits')
            hot_map = shHdu[0].data
            hot_pix = np.where(hot_map > 1)
            apply_hot = True
            if loud: print(lng_path + 'fh_2-4.fits', 'Loaded')
        except:
            apply_hot = False
            if loud: print('WARN: No Hot Map Loaded.')

    while True:   #Use break to drop through to exit.  i.e., do not calibrate frames we are acquring for calibration.
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
        if frame_type == 'bias':
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
            if data_exposure_level > dark_exposure_level:
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
            break       #  Do not fla calibrate a flat.
        do_flat = False
        if binning == 2:
            if img_filter in ['w', 'W']:
                do_flat = True
                scr_flat = screen_flat_w
            elif img_filter in ['B', 'BB']:
                do_flat = True
                scr_flat = screen_flat_B
            elif img_filter in ['V', 'VB']:
                do_flat = True
                scr_flat = screen_flat_V
            elif img_filter in ['R', 'RB', 'Rc', 'RC']:
                do_flat = True
                scr_flat = screen_flat_R
            elif img_filter in ['gp']:
                do_flat = True
                scr_flat = screen_flat_gp
            elif img_filter in ['rp']:
                do_flat = True
                scr_flat = screen_flat_rp
            elif img_filter in ['ip']:
                do_flat = True
                scr_flat = screen_flat_ip
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
            elif img_filter in ['EXO', 'exo']:
                do_flat = True
                scr_flat = screen_flat_EXO
            elif img_filter in ['air', 'AIR']:
                do_flat = True
                scr_flat = screen_flat_air
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
        if apply_hot and binning == 2:
            try:
                median8(img, hot_pix)
                cal_string += ', H'
            except:
                print("Hot pixel correction failed.")
            if not quick: 
                if loud: print('Hot Pixel result:  ', imageStats(img, loud))

        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')  #This is meant to catch an image cast to 'float64'
    fix = np.where(hdu.data < 0)
    if not quick: print('# of < 0  pixels:  ', len(fix[0]))  #  Do not change values here.
    hdu.data[fix] = 0
    big_max = hdu.data.max()
    if loud: print("Max data value is:  ", big_max)
    fix = np.where(hdu.data > 65530)
    hdu.data[fix] = 65530.
    hdu.data = hdu.data.astype('uint16')
    result = {}
    result['error'] = False
    result['mean_focus'] = None
    result['mean_rotation'] = None
    result['FWHM'] = None
    result['half_FD'] = None
    result['patch'] = round((hdu.data.mean() + np.median(hdu.data))/2, 1)
    result['temperature'] = None
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

