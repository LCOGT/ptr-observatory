# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 20:08:38 2019
wer
"""

import numpy as np
from astropy.io import fits

'''
Quick images store little, and are mainly for focus exploration.
Thoughts on how to merge CMOS images.

The detector in question is:  G-Sense 4040. The camera is a FLI Kepler.

Pick a setpoint temperature you can maintain over a period of time,
or build a bank of calibrations are various temperatures.  Since we 
are able to hold -20C year-round we have no experience with scaling 
combining calibrations from various temperatures. Dark current 
declines exponentially by a factor of two for every -7C, so correction
to an intermediate temperature requires some care.

Start with taking 511 bHDR and LDR biases then a large number of 
darks (I use 127) of a duration longer than what you plan for any
given actual exposure.  I use 90 and 300 seconds.  

Bins of 1x1 and 2x2

Median combine them in the usual way, of course subtracting the superbias
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


def fit_quadratic(x, y):     
    #From Meeus, works fine.
    #Abscissa arguments do not need to be ordered for this to work.
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
        if super_dark_90 is None:
            try:
                sdHdu = fits.open(lng_path + 'md_1_90.fits')
                dark_90_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_90  = sdHdu[0].data.astype('float32')
                print('sdark_90:  ', super_dark_90.mean())
                sdHdu.close()
                #fix = np.where(super_dark_90 < 0)
                #super_dark_90[fix] = 0
                quick_dark_90 = True
                print(lng_path + 'md_1_90.fits', 'Loaded')
            except:
                quick_dark_90 = False
                print('WARN: No dark Loaded.')
        if super_dark_300 is None:
            try:
                sdHdu = fits.open(lng_path + 'md_1_300.fits')
                dark_300_exposure_level = sdHdu[0].header['EXPTIME']
                super_dark_300  = sdHdu[0].data#.astype('float32')
                print('sdark_300:  ', super_dark_300.mean())
                sdHdu.close()
                #fix = np.where(super_dark_300 < 0)
                #super_dark_300[fix] = 0
                quick_dark_300 = True
                print(lng_path + 'md_1_300.fits', 'Loaded')
            except:
               quick_dark_300 = False
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

#        if hotmap_300 is None:
#            try:
#                shHdu = fits.open(lng_path + 'hdr_hotmap_300.fits')
#                hotmap_300 = shHdu[0].data#.astype('uint16')
#                shHdu.close()
#                quick_hotmap_300 = True
#                hotpix_300 = np.where(hotmap_300 > 60)  #This is a temp simplifcation
#                print(lng_path + 'hdr_hotmap_300.fits', 'Loaded, Length = ', len(hotpix_300[0]))
#            except:
            quick_hotmap_300= False
#                if not quick: print('Hotmap_300 failed to load.')


    while True:   #Use break to drop through to exit.  i.e., do not calibrte frames we are acquring for calibration.
        cal_string = ''
        if not quick:
            img = hdu.data.astype('float32')
            mn, std = imageStats(img, False)
            if loud: print('InputImage (high):  ', imageStats(img, False))
        else:
            img = hdu.data
        if frame_type == 'bias': break
        if super_bias is not None :
            #if not quick: print(start_x, start_x + img.shape[0], start_y, start_y + img.shape[1])
            img = img - super_bias[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])]  #hdu.header['NAXIS2, NAXIS1']
            if not quick: 
                if loud: print('QuickBias result (high):  ', imageStats(img, False))
            cal_string += 'B'
        data_exposure_level = hdu.header['EXPTIME']
        if frame_type == 'dark': 
            break
        do_dark = False
        if data_exposure_level <= 90:
            s_dark = super_dark_90
            d_exp = 90.
            h_map = hotmap_300
            h_pix = hotpix_300
            do_dark = True
        elif data_exposure_level <= 300:
            s_dark = super_dark_300
            d_exp = 300.0 #dark_300_exposure_level #hack to fix bad dark master.
            h_map = hotmap_300
            h_pix = hotpix_300
        else:
            do_dark = False  
        if do_dark and mn < 3590:
        #Need to verify dark is not 0 seconds long!
            if d_exp >= data_exposure_level and d_exp >= 1  and quick_dark_90:
                scale = data_exposure_level/d_exp
                img =  (img - s_dark[start_x:(start_x + img.shape[0]), start_y:(start_y + img.shape[1])])
                if not quick:
                    print('QuickDark  scale/result(high): ', round(scale, 4), imageStats(img, loud))
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
    return

if __name__ == '__main__':
    pass                          

    