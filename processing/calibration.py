# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 20:08:38 2019
wer
"""

import numpy as np
from astropy.io import fits

'''
This is kludge code just to quickly partially calibrate images for the AWS 768^2 postage.
WE need to re-think how this will work, ie use BONSAI locally or not.

Name of module is a bit deceptive, this is more like 'create_postage'.
'''


def fit_quadratic(x, y):
    #From Meeus, works fine.
    #Abscissa arguments do not need to be ordered for this to work.
    #NB Single alpha variable names confict with debugger commands.
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
        try:
            return (a, b, c, -b/(2*a))
        except:
            return (a, b, c)
    else:
        return None

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


super_bias = None
super_bias_2 = None
super_bias_ldr = None
super_dark_90 = None
super_dark_90_ldr = None
super_dark_360 = None
super_dark_2_360 = None
super_dark_360_ldr = None
hotmap_360 = None
hotmap_360_ldr = None
hotpix_360 = None
hotpix_360_ldr = None
super_flat_w = None
super_flat_HA = None

#This is a brute force linear version. This needs to be more sophisticated and camera independent.

def calibrate (hdu, hdu_ldr, lng_path, frame_type='light', start_x=0, start_y=0, quick=False):
    #These variables are gloal in the sense they persist between calls (memoized so to speak, should use that facility.)
    global super_bias, super_bias_2, super_bias_ldr, super_dark_90, super_dark_90_ldr, super_dark_360, super_dark_2_360, \
           super_dark_360_ldr, super_flat_w, super_flat_HA, hotmap_360, hotpix_360, hotmap_360_ldr, hotpix_360_ldr
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
                print('WARN: No Bias Loaded.')
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
                print('WARN: No Bias Loaded.')
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
        if super_dark_360 is None:
            try:
                sdHdu = fits.open(lng_path + 'md_1_360.fits')
                dark_360_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_360  = sdHdu[0].data#.astype('float32')
                print('sdark_360:  ', super_dark_360.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_360 = True
                print(lng_path + 'md_1_360.fits', 'Loaded')
            except:
               quick_dark_360 = False
               print('WARN: No dark Loaded.')
        if super_dark_2_360 is None:
            try:
                sdHdu = fits.open(lng_path + 'md_2_360.fits')
                dark_2_360_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_2_360  = sdHdu[0].data#.astype('float32')
                print('sdark_2_360:  ', super_dark_2_360.mean())
                sdHdu.close()
                #fix = np.where(super_dark_360 < 0)
                #super_dark_360[fix] = 0
                quick_dark_2_360 = True
                print(lng_path + 'md_2_360.fits', 'Loaded')
            except:
               quick_dark_2_360 = False
               print('WARN: No dark Loaded.')
#Note on flats the case is carried through
#        if super_flat_w is None:
#            try:
#                sfHdu = fits.open(lng_path + 'ldr_mf_1_w.fits')
#                super_flat_w = sfHdu[0].data.astype('float32')
#                quick_flat_w = True
#                sfHdu.close()
#                if loud: print(lng_path + 'ldr_mf_1_w.fits', 'Loaded')
#            except:
            quick_flat_w = False
#                print('WARN: No W Flat/Lum Loaded.')
#        if super_flat_HA is None:
#            try:
#                sfHdu = fits.open(lng_path + 'ldr_mf_1_1_HA.fits')
#                super_flat_HA = sfHdu[0].data#.astype('float32')
#                quick_flat_HA = True
#                sfHdu.close()
#                if loud: print(lng_path + 'ldr_mf_1_HA.fits', 'Loaded')
#            except:
            quick_flat_HA = False
#                if not quick: print('WARN: No HA Flat/Lum Loaded.')

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
    while True:   #Use break to drop through to exit.  i.e., do not calibrte frames we are acquring for calibration.
        cal_string = ''
        if not quick:
            img = hdu.data.astype('float32')
            mn, std = imageStats(img, False)
            if loud: print('InputImage (high):  ', imageStats(img, False))
        else:
            img = hdu.data
        if frame_type == 'bias': break
        if super_bias is not None :   #NB Need to qualify with binning
            #if not quick: print(start_x, start_x + img.shape[0], start_y, start_y + img.shape[1])
            img = img - super_bias[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick:
                if loud: print('QuickBias result (high):  ', imageStats(img, False))
            cal_string += 'B'
        data_exposure_level = hdu.header['EXPTIME']
        if frame_type == 'dark':
            break
        do_dark = False
        # if data_exposure_level <= 90:
        #     s_dark = super_dark_90
        #     d_exp = 90.
        #     h_map = hotmap_360
        #     h_pix = hotpix_360
        #     do_dark = True

        # NB Qualify if dark exists and by binning
        if data_exposure_level <= 360:
            s_dark = super_dark_360
            d_exp = 360.0 #dark_360_exposure_level #hack to fix bad dark master.
            h_map = hotmap_360
            h_pix = hotpix_360
            do_dark = True
        else:
            do_dark = False
        if do_dark:  #  and mn < 3590:
        #Need to verify dark is not 0 seconds long!
            if d_exp >= data_exposure_level and d_exp >= 1:  #  and quick_dark_90:
                scale = data_exposure_level/d_exp
                img =  (img - s_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])])
                if not quick:
                    print('QuickDark  scale/result(high): ', round(scale, 4), imageStats(img, loud))
                cal_string += ', D'
            else:
                if not quick: print('INFO:  Light exposure too small, skipped this step.')

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
            if not quick: print('QuickFlat result (high):  ', imageStats(img, loud))

            cal_string +=', SCF'
        #median8(img, h_pix)
        #cal_string +=', HP'
        break    #If we get this far we are done.
    if cal_string == '':
        cal_string = 'Uncalibrated'
    hdu.header['CALHIST'] = cal_string
    hdu.data = img.astype('float32')  #This is meant to catch an image change to 'float64'
    fix = np.where(hdu.data < 0)
    if not quick: print('# of 0 fix pixels:  ', len(fix[0]))
    hdu.data[fix] = 0
    big_max = hdu.data.max()
    if big_max > 65535.:   #This scaling is probelmatic.
        hdu.data = hdu.data*(65530./big_max)
    return (hdu.data.mean() + np.median(hdu.data))/2

if __name__ == '__main__':
    pass

