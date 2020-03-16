# -*- coding: utf-8 -*-
"""
Created on Sun Feb  4 16:59:15 2018

@author: WER
"""

"""

Goal here is a general purpose local site reduction module.  Ultimate
files are calibrated in units of e- and e-/s in the case
of darks.

"""

import datetime as datetime

from copy import copy, deepcopy
import math
import os
import glob
import sys
import time
from datetime import datetime, timedelta
import win32com.client
import os
import threading
import socket
import shutil as sh

import shelve
import numpy as np
import random
import matplotlib
import matplotlib.pyplot as plt
matplotlib.rcParams['font.size'] = 8

import random

from scipy import stats


from skimage import data, io #, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure

from astropy.modeling import models
from astropy import units as u
from astropy import nddata
from astropy.io import fits
from astropy.io.fits import getheader

import ccdproc
from ccdproc import ImageFileCollection
from astropy.io.fits import getheader

from ccdproc import CCDData, Combiner



def fits_renamer(path):
    '''
    Re-names in place *.fts, *.fit to *.fits.
    '''

    fit_file_list = glob.glob(path + '\\*.fts')
    fit_list_two = glob.glob(path + '\\*.fit')
    fit_file_list += fit_list_two
    num_renames = len(fit_file_list)
    if num_renames > 0:
        count = 0
        for fit_file in fit_file_list:
            fits_file = fit_file[:-3] + 'fits'
            count += 1
            os.replace(fit_file,fits_file)
        print(count, '   Files renamed.')
    else:
        print("No files needed renaming.")

def fits_remove_overscan(ipath, opath):
    '''
    Note this is cameras ea03amd ea04 specific!
    '''

    fits_file_list = glob.glob(ipath + '\\*.fits')
    print(str(len(fits_file_list)) + ' files found.')
    count = 0
    for fits_file in fits_file_list:
        img_hdu = fits.open(fits_file)
        file_name = fits_file.split('\\')[-1]
        meta = img_hdu[0].header
        if meta['NAXIS1'] == 2098 and meta['NAXIS2'] == 2048:
            img = img_hdu[0].data.astype('float32')
            overscan = img[:, 2050:]
            biasline = np.median(overscan, axis=1)
            biasmean = biasline.mean()
            biasline = biasline.reshape((2048,1))


            img_hdu[0].data = (img - biasline)[:2048,:2048].astype('uint16')
#            fimg = img2.flatten()
#            simg = fimg.copy()
#            simg.sort()
#            ftop = int(len(fimg)*0.995)
#            fmin = fimg.min()
#            fmax = simg[ftop]
#            fslope = 254./(fmax - fmin)
#            img2 -= fmin
#            img2 = img2*fslope
#            fix = np.where(img2 > 254)
#            img2[fix] = 255
#            img2 = img2/255.
#
#            small = resize(img2, (768, 768), mode='edge')
#            small_gamma_corrected = exposure.adjust_gamma(small, .15)
#            small = (small_gamma_corrected*255.).astype('uint16')
#
#
#            img_hdu[0].data = small
            meta['HISTORY'] = 'Median overscan subtracted and trimmed. Mean = ' + str(round(biasmean,2))

            img_hdu.writeto(opath + file_name, clobber=True)
            #Note this is equivalent to normal first time CCD wirte of a trimmed image
            count += 1
        else:
            continue
    print(count, '   Files overscan adjusted and trimmed.')


def get_size(obj, seen=None):    #purloined from WWW  SHIPPO
    """Recursively finds size of objects"""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) for v in obj.values()])
        size += sum([get_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size

def chunkify(im_list):
    '''
    Accept a long list of images, for now a max of 225.  Create a new list of
    lists, as many 15's as possible and then one runt.  Intention is
    is len of runt < 11, it gets combined with sigma clip.   iF THE INPUT LIST
    is 15 items or less, it is unchanged.   For inputs < 30 should make two
    basically even split lists. (Not implementd yet.)
    '''
    chunk = 15
    count = len(im_list)
    num = count//chunk
    rem = count%chunk
    index = 0
    out_list = []
    if num == 0 or num==1 and rem  == 0:
        out_list.append(im_list)
        return out_list       #Out put format is a list of lists.
    else:
        for cycle in range(num):
            sub_list = []
            for im in range(chunk):
                sub_list.append(im_list[index])
                index += 1
            out_list.append(sub_list)
        sub_list = []
        for cycle in range(rem):
            sub_list.append(im_list[index])
            index += 1
        if len(sub_list) > 0:
            out_list.append(sub_list)
        return out_list

def image_stats(img_img, p_median=False):
    axis1 = img_img.meta['NAXIS1']
    axis2 = img_img.meta['NAXIS2']
    subAxis1 = axis1/2
    patchHalf1 = axis1/5
    subAxis2 = axis2/2
    patchHalf2 = axis2/5
    sub_img = img_img.data[int(subAxis1 - patchHalf1):int(subAxis1 + patchHalf1), int(subAxis2 - patchHalf2):int(subAxis2 + patchHalf2) ]
    if p_median:
        img_mean = np.median(sub_img)
    else:
        img_mean = sub_img.mean()
    img_std = sub_img.std()
    #ADD Mode here someday.
    return round(img_mean, 2), round(img_std, 2)

def imageOffset(img_img, p_median=False):
    axis1 = img_img.meta['NAXIS1']
    axis2 = img_img.meta['NAXIS2']
    subAxis1 = axis1/2
    patchHalf1 = axis1*0.45
    subAxis2 = axis2/2
    patchHalf2 = axis2*0.45
    sub_img = img_img.data[int(subAxis1 - patchHalf1):int(subAxis1 + patchHalf1), int(subAxis2 - patchHalf2):int(subAxis2 + patchHalf2) ]
    if p_median:
        img_offset= np.median(sub_img)
    else:
        img_offset= sub_img.mean()
    #ADD Mode here someday.
    return img_offset

def column_stats(img_img):
    pass
    return

def hot_pixels(img_img, sigma=6):
    mn = img_img.data.mean()
    sd = img_img.data.std()
    print(mn, sd)
    hots = np.where(img_img.data > (mn + sigma*sd))
    return hots

def median8(img_img, hotPix):
    img_img = img_img[0]
    #print('1: ',img_img.data)
    axis1 = img_img.header['NAXIS1']
    axis2 = img_img.header['NAXIS2']

    img = img_img.data
    for pix in range(len(hot[0])):
        iy = hot[0][pix]
        ix = hot[1][pix]
        if (0 < iy < axis1 - 2) and (0 < ix < axis2 - 2):
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


def create_super_bias(input_images, oPath, super_name):
    num = len(input_images)
    first_image = ccdproc.CCDData.read(input_images[0])
    input_images = chunkify(input_images)
    super_image =[]
    while len(input_images) > 0:
        inputs = []
        print('SB:  ', len(input_images[0]), input_images[0], super_name)
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            im=  ccdproc.CCDData.read(input_images[0][img])
            im.data = im.data.astype(np.float32)
            im_offset= imageOffset(im, p_median=True)
            im_offset = float(im_offset)
            im.data -= im_offset
            inputs.append(im)# - im_offset)  #, unit="adu"))
            print('Size of inputs:  ', get_size(inputs), im_offset)
        print(inputs)
        combiner = Combiner(inputs)
        im_temp = combiner.median_combine()

        im_temp.data = im_temp.data.astype(np.float32)

        if len_input > 9:
            super_image.append(im_temp)
        else:
            super_image.append(im_temp)     #Change to sigma-clip
        combiner = None
        inputs = None
        print('Size of inputs:  ', get_size(inputs))
        print('Size of super:  ', get_size(super_image))
        input_images.pop(0)
    print('SI:  ', super_image)
    combiner = Combiner(super_image)
    super_img = combiner.median_combine()
    super_image = None
    combiner = None
    super_img.data = super_img.data.astype(np.float32)
    print('Size of final super data:  ', get_size(super_img.data))
#    try:
#        os.mkdir(path[:-9]+ '\\lng\\')
#
#    except:
#        pass
    super_img.meta = first_image.meta       #Just pick up forst header
    first_image = None
    mn, std = imageStats(super_img)
    super_img.meta['COMBINE'] = (num, 'No of images ussed')
    super_img.meta['BSCALE'] = 1.0
    super_img.meta['BZERO'] = 0.0         #NB This does not appear to go into headers.
    super_img.meta['CNTRMEAN'] = mn
    super_img.meta['CNTRSTD'] = std
    super_img.write(oPath + str(super_name), overwrite=True)

#    s_name = str(super_name).split('\\')
#    print('s_name_split:  ', s_name)
    s_name = super_name.split('.')
    print('s_name_split:  ', s_name[0])
    tstring = datetime.datetime.now().isoformat().split('.')[0].split(':')
    wstring = str(oPath + '\\' + s_name[0] + '_' + \
                        tstring[0]+tstring[1]+tstring[2] + \
                        '.fits')
    print('wstring:  ', str(super_name), wstring)
    print('Size of final super mata:  ', get_size(super_img.meta))
    super_img.write(wstring, overwrite=True)   #this is per day dir copy
    super_img = None
    #makeLng(path[:-9]+ '\\lng', s_name[0])
    '''
    Need to combine temperatures and keep track of them.
    Need to form appropriate averages.

    The above is a bit sloppy.  We should writ the per day dir version of the
    superbias first, then based on if there exists a prior lng superbias that
    a new combined weighted bias is created.  The prior N <=4 days biases are
    kept then aged (1*5 + 2*4 + 3*3 + 4*2 + 5*1)/16

    Need to examine for hot pixels and hot columns and make entries in the 1:!
    resolution bad pixel mask.
    '''
    return

def create_super_dark( input_images, oPath, super_name, super_bias_name):
    inputs = []
    print('SD:  ', len(input_images), input_images, super_bias_name)
    super_bias_img = ccdproc.CCDData.read(super_bias_name, ignore_missing_end=True)
    for img in range(len(input_images)):
        corr_dark = ccdproc.subtract_bias(
                   (ccdproc.CCDData.read(input_images[img], unit='adu')),
                    super_bias_img)
        im = corr_dark
        im.data = im.data.astype(np.float32)
        im_offset= imageOffset(im, p_median=True)
        im_offset = float(im_offset)
        im.data -= im_offset
        inputs.append(im)
    combiner = Combiner(inputs)
    super_img = combiner.median_combine()
    #mn, std = imageStats(super_img)

    #super_img = super_img.add(100*u.adu)
    super_img.meta = inputs[0].meta
    #super_img.meta['PEDESTAL'] = -100
    super_img.meta['NCOMBINE'] = len(inputs)
    #super_img.meta['CNTRMEAN'] = mn
    #super_img.meta['CNTRSTD'] = std
    s_name = super_name.split('.')
    print('s_name_split:  ', s_name[0])
    tstring = datetime.datetime.now().isoformat().split('.')[0].split(':')
    wstring = str(oPath + '\\' + s_name[0] + '_' + \
                        tstring[0]+tstring[1]+tstring[2] + \
                        '.fits')
    super_img.write(wstring, overwrite=True)

    hots = hot_pixels(super_img)
    print (len(hots), hots)
    '''
    Need to trim negatives, and find hot pixels to create map.
    '''
    return

def create_super_flat(input_images, oPath, super_name, super_bias_name,
                      super_dark_name):
    #NB Should cull low count input frames.
    inputs = []
    print('SF:  ', len(input_images))
    super_bias = ccdproc.CCDData.read(super_bias_name, ignore_missing_end=True)
    super_dark = ccdproc.CCDData.read(super_dark_name, ignore_missing_end=True)
    #super_dark = super_dark.subtract(super_dark.meta['PEDASTAL']*u.adu)

    for img in range(len(input_images)):
        img_in = ccdproc.CCDData.read(input_images[img], unit='adu', ignore_missing_end=True)
        bias_corr = ccdproc.subtract_bias(img_in, super_bias)
        print('Hello:  ', super_dark.meta['EXPTIME'], img_in.meta['EXPTIME'], type(bias_corr), type(super_dark), img_in.meta)
        corr_flat = ccdproc.subtract_dark(bias_corr, super_dark, scale=True, \
                    dark_exposure=super_dark.meta['EXPTIME']*u.s, \
                    data_exposure =img_in.meta['EXPTIME']*u.s)

        #corr_flat = ccdproc.
        inputs.append(corr_flat)
    combiner = Combiner(inputs)
    super_img = combiner.median_combine()
    super_img.meta = inputs[0].meta

    super_img.meta['NCOMBINE'] = len(inputs)
    s_name = super_name.split('.')
    print('s_name_split:  ', s_name[0])
    tstring = datetime.datetime.now().isoformat().split('.')[0].split(':')
    wstring = str(oPath + '\\' + s_name[0] + '_' + \
                        tstring[0]+tstring[1]+tstring[2] + \
                        '.fits')
    super_img.write(wstring, overwrite=True)

          #Turn the above into a circle region.
    return


keys = ['imagetyp', 'filter',  'exposure']#, 'xbinning', 'ybinning']

filters = ['PL', 'PR', 'PG', 'PB', 'HA', 'O3',  'S2', 'N2', 'ContR', 'u', \
           'g', 'r', 'i', 'zs', 'dif', 'air', 'dif-u', 'dif-g', 'dif-r', 'dif-i', 'dif-zs']

detectors = ['gf03']

print('starting reductions.')

# This code prototypes the gain calculation, following Newberry.  Correctd for
# flast-field effects
if __name__ == '__main__':
    path = 'Q:/archive/gf03/2019-12-28/'
    lng_path =  'Q:/archive/gf03/lng/'
    low_path_1 = 'Q:/archive/gf03/raw_kepler/2019-12-28/'
    low_path_2 = 'Q:/archive/gf03/raw_kepler?2019-12-28/'
    out_path = 'Q:/archive/gf03/2019-12-28/reduced/'

    image_list = glob.glob(path + 'gain_scrn*.f*t*')
    image_list_low =  glob.glob(low_path_1 + 'gf03*low.fits')
    # We should make sure to have right number of images in each list -- they should equal.
    
#    image_list_2 = glob.glob(out_path + '*.fits')
#    if len(image_list_2) != 0:
  
    #Next we need to subract the bias signature for evertyhing.
    bias_image_1x1 = fits.open(lng_path +'mb_1_hdr.fits')
    bias_high_1x1 = bias_image_1x1[0].data
    bias_image_low_1x1 = fits.open(lng_path +'mb_1_ldr.fits')
    bias_low_1x1 = bias_image_low_1x1[0].data
    bias_image_2x2 = fits.open(lng_path +'mb_2_hdr.fits')
    bias_high_2x2 = bias_image_2x2[0].data
    bias_image_low_2x2 = fits.open(lng_path +'mb_2_ldr.fits')
    bias_low_2x2 = bias_image_low_2x2[0].data
    carry_name = []
    carry_name_low = []
    for image in image_list:
        new_image = fits.open(image)
        new_frame = new_image[0]
        if new_frame.header['XBINNING'] == 1:
            new_frame.data = new_frame.data.astype('float32')
            new_frame.data -= bias_high_1x1
            new_frame.header["HISTORY"] = "Master Bias removed."
        if new_frame.header['XBINNING'] == 2:
           new_frame.data = new_frame.data.astype('float32')
           new_frame.data -= bias_high_2x2
           new_frame.header["HISTORY"] = "Master Bias removed."
        file_name = image.split('\\')[1]
        print(file_name)
        new_frame.writeto(out_path + file_name + "s", overwrite=True)
        carry_name.append(file_name[:-4] + '.fits')
        carry_name_low.append(file_name[:-4]+ '_low.fits')
        new_image.close()
    carry_index = 0
    for image in image_list_low:
        new_image = fits.open(image)
        new_frame = new_image[0]
        if new_frame.header['XBINNING'] == 1:
            new_frame.data = new_frame.data.astype('float32')
            new_frame.data -= bias_high_1x1
            new_frame.header["HISTORY"] = "Master Bias removed."
        if new_frame.header['XBINNING'] == 2:
           new_frame.data = new_frame.data.astype('float32')
           new_frame.data -= bias_high_2x2
           new_frame.header["HISTORY"] = "Master Bias removed."
        print(carry_name_low[carry_index])
        new_frame.writeto(out_path + carry_name_low[carry_index], overwrite=True)
        carry_index += 1
        new_image.close()
        #We have now bias corrected the inputs, renamed them and next pass we
        #Will osrt and compute gains.
        
    #Get rid of the header images.
    carry_name.pop(0)
    carry_name_low.pop(0)
    name_split = []
    for item in carry_name:
        name_split.append( (item.split('_')))
    name_split_low = []
    for item in carry_name_low:
        name_split_low.append( (item.split('_')))
        
    
    for item in name_split:
        if len(item) == 5:
            item_bin = item[3]
            item_name = item[4]
            print(item)
                    
b1 = fits.open(out_path + 'gain_scrn_92-0011gb_1_low.fits')
b2 = fits.open(out_path + 'gain_scrn_92-0012gb_1_low.fits')

b_1 = b1[0].data
b_2 = b2[0].data

rn =  (b_1 - b_2).std()/math.sqrt(2)
print('Calulate mean bias frame noise.')
print('Average bias read noise:  ', round(rn ,3))


l1 = fits.open(out_path + 'gain_scrn_92-0011gl_1_18_low.fits')
l2 = fits.open(out_path + 'gain_scrn_92-0012gl_1_18_low.fits')

l_1 = l1[0].data
l_2 = l2[0].data
r = l_1/l_2
d = l_1 - l_2*r
print('Correct for flat field effect in lights. Ratio is:  ', round(r.mean(), 5))
l_2 = l_2*r
print('Remove bias noise contribution from lights.')

#l_1.std() = sqrt((l_1n).std()**2 + rn**2)
l_1n_std = math.sqrt(l_1.std()**2 -rn**2)
l_2n_std = math.sqrt(l_2.std()**2 -rn**2)
print('stds of lights:  ', l_1n_std, l_2n_std)
print('variance of lights:  ', round(l_1n_std**2, 4), round(l_2n_std**2, 4) )

l_1_gain= math.sqrt(l_1.mean())/l_1n_std
l_2_gain = math.sqrt(l_2.mean())/l_2n_std
print('Gains:  : ', l_1_gain, l_2_gain)
