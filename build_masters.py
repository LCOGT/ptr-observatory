# -*- coding: utf-8 -*-
"""
Created on Sat Oct 26 16:35:36 2019

@author: obs
"""

"""
20200308 WER  THis is code to generate master frames.  It is far from complete but works for the JPEG level application.

Update 20200404 WER On saf.

This is a re-work of older code designed to build calibrations from Neyle's natural directory structure for
MAXIM DL, or from a sub-directory 'calibrations' found in the designated archive structure.
D:/04-01-2020 screen flats W Ha/

The output is destined for the LNG flash calibration directory.  LNG contains a sub-directory, 'priors.'  THe
idea is calibrations are gathered daily, reduced and put into prior.  then the priors are scanned and combined to
build more substantial lower noise masters.  Priors are aged and once too old are removed.  It may be the case that
we want to weight older priors lower than the current fresh one.

"""





import win32com.client
import pythoncom
import time
import datetime
import os
from os.path import join, dirname, abspath
import sys
import glob
import math
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
from PIL import Image

from skimage import data, io, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure
from skimage.io import imsave

from astropy.io import fits
from astropy.table import Table
from astropy.utils.data import get_pkg_data_filename
from astropy.io.fits import getheader
from astropy.modeling import models
from astropy import units as u
from astropy import nddata

import ccdproc
from ccdproc import ImageFileCollection
from ccdproc import CCDData, Combiner

import sep

# from ptr-observatory.global_yard import g_dev
import config
# import api_calls
# import requests





def fits_renamer(path):
    '''
#    Re-names in place *.fts, *.fit to *.fits.
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

def fits_remove_overscan(ipath, opath):
    '''
#    Note this is cameras ea03amd ea04 specific!
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

def chunkify(im_list, chunk_size):
    '''
    Accept a long list of images, for now a max of 225.  Create a new list of
    lists, as many 15's as possible and then one runt.  Intention is
    is len of runt < 11, it gets combined with sigma clip.   iF THE INPUT LIST
    is 15 items or less, it is unchanged.   For inputs < 30 should make two
    basically even split lists. (Not implementd yet.)

    Note this does not interleave frames just breaks them up into blocks.
    '''
    count = len(im_list)
    num = count//chunk_size
    rem = count%chunk_size
    index = 0
    out_list = []
    if num == 0 or num==1 and rem  == 0:
        out_list.append(im_list)
        return out_list       #Out put format is a list of lists.
    else:
        for cycle in range(num):
            sub_list = []
            for im in range(chunk_size):
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

def create_super_bias(input_images, out_path, super_name):
    first_image = ccdproc.CCDData.read(input_images[0][0], unit='adu')
    last_image = ccdproc.CCDData.read(input_images[-1][-1], unit='adu')
    super_image =[]
    super_image_sigma = []
    num = 0
    while len(input_images) > 0:  #I.e., there are chuncks to combine
        inputs = []
        print('SB chunk:  ', num+1, len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            im=  ccdproc.CCDData.read(input_images[0][img], unit='adu')
            im.data = im.data.astype(np.float32)
            inputs.append(im)
            num += 1
        print(inputs[-1])   #show the last one
        combiner = Combiner(inputs)
        combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
        im_temp = combiner.average_combine()
        print(im_temp.data[2][3])
        super_image.append(im_temp)
        combiner = None   #get rid of big data no longer needed.
        inputs = None
        input_images.pop(0)
    #print('SI:  ', super_image)
    #Now we combine the outer data to make the master
    #breakpoint()
    combiner = Combiner(super_image)
    combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
    super_img= combiner.average_combine()
    super_image = None    #Again get rid of big stale data
    combiner = None
    super_img.data = super_img.data.astype(np.float32)
    #Here we should clean up egregious pixels.
    super_img.meta = first_image.meta       #Just pick up first header
    first_image = None
    mn, std = image_stats(super_img)
    super_img.meta['COMBINE'] = (num, 'No of images combined')
    super_img.meta['BSCALE'] = 1.0
    super_img.meta['BZERO'] = 0.0         #NB This does not appear to go into headers.
    super_img.meta['BUNIT'] = 'adu'
    super_img.meta['CNTRMEAN'] = mn
    super_img.meta['CNTRSTD'] = std
    super_img.write(out_path + str(super_name), overwrite=True)
    super_img = None

##    s_name = str(super_name).split('\\')
##    print('s_name_split:  ', s_name)
#    s_name = super_name.split('.')
#    print('s_name_split:  ', s_name[0])
##    tstring = datetime.datetime.now().isoformat().split('.')[0].split(':')
#    wstring = str(out_path + super_name)
#    print('wstring:  ', str(super_name), wstring)
#    print('Size of final super meta:  ', get_size(super_img.meta))
#    super_img.write(wstring, overwrite=True)   #this is per day dir copy

#    #makeLng(path[:-9]+ '\\lng', s_name[0])


def create_super_dark(input_images, out_path, super_name, super_bias_name):
    first_image = ccdproc.CCDData.read(input_images[0][0], unit='adu')
    last_image = ccdproc.CCDData.read(input_images[-1][-1], unit='adu')
    super_image =[]
    super_image_sigma = []
    num = 0
    inputs = []
    print('SD:  ', len(input_images), input_images)
    try:
        super_bias_img = ccdproc.CCDData.read(out_path + super_bias_name, ignore_missing_end=True, unit='adu')
    except:
        print(out_path + super_bias_name, 'failed')
    while len(input_images) > 0:
        inputs = []
        print('SD chunk:  ', len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            corr_dark = ccdproc.subtract_bias(
                       (ccdproc.CCDData.read(input_images[0][img], unit='adu')),
                        super_bias_img)
            im = corr_dark
            im.data = im.data.astype(np.float32)
            inputs.append(im)
            num += 1
        combiner = Combiner(inputs)
        if len(inputs) > 9:
            im_temp= combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.median)
        else:
            im_temp = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
        im_temp = combiner.average_combine()
        im_temp.data = im_temp.data.astype(np.float32)
        print(im_temp.data[2][3])
        #breakpoint()
        super_image.append(im_temp)
        combiner = None   #get rid of big data no longer needed.
        inputs = None

        input_images.pop(0)
    #Now we combint the outer data to make the master
    combiner = Combiner(super_image)
    if len(super_image) > 9:
        super_img = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.median)
    else:
        super_img = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
    super_img = combiner.average_combine()
    combiner = None
    super_img.data = super_img.data.astype(np.float32)
    super_img.meta = first_image.meta
    mn, std = image_stats(super_img)
    super_img.meta = first_image.meta
    super_img.meta['NCOMBINE'] = num
    super_img.meta['BSCALE'] = 1.0
    super_img.meta['BZERO'] = 0.0         #NB This does not appear to go into headers.
    super_img.meta['BUNIT'] = 'adu'
    super_img.meta['CNTRMEAN'] = mn
    super_img.meta['CNTRSTD'] = std
    wstring = str(out_path + super_name)
    super_img.write(wstring, overwrite=True)
    super_image = None    #Again get rid of big stale data
    #hot and cold pix here.
    return

def make_master_bias (alias, path,  lng_path ,selector_string, out_file):

    file_list = glob.glob(path + selector_string)
    file_list.sort()
    print('# of files:  ', len(file_list))

    print(file_list)
    breakpoint()
    if len(file_list) == 0:
        print("Empty list, returning.")
        return
    if len(file_list) > 255:
        file_list = file_list[0:255]
    chunk = int(math.sqrt(len(file_list)))
    if chunk %2 == 0: chunk += 1
    if chunk > 31: chunk = 31
    print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunked_list = chunkify(file_list, chunk)
    print(chunked_list)
    create_super_bias(chunked_list, lng_path, out_file )

def make_master_dark (alias, path, lng_path, selector_string, out_file, super_bias_name):
    #breakpoint()
    file_list = glob.glob(path + selector_string)
    file_list.sort
    print('# of files:  ', len(file_list))
    print(file_list)
    if len(file_list) > 63:
        file_list = file_list[0:63]
    if len(file_list) == 0:
        print("Empty list, returning.")
        return
    chunk = int(math.sqrt(len(file_list)))
    if chunk %2 == 0: chunk += 1
    if chunk > 31: chunk = 31
    print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunked_list = chunkify(file_list, chunk)
    print(chunked_list)
    create_super_dark(chunked_list, lng_path, out_file, super_bias_name )

if __name__ == '__main__':
    camera_name = config.site_config['camera']['camera1']['name']
    archive_path = "D:/04-01-2020 screen flats W Ha/"
    lng_path = "D:/archive/archive/kb01/lng/"
    make_master_bias(camera_name, archive_path, lng_path, '*b_1*', 'mb_1.fits')
    make_master_bias(camera_name, archive_path, lng_path, '*b_2*', 'mb_2.fits')
    make_master_bias(camera_name, archive_path, lng_path, '*b_3*', 'mb_3.fits')
    make_master_bias(camera_name, archive_path, lng_path, '*b_4*', 'mb_4.fits')
    make_master_dark(camera_name, archive_path, lng_path, '*d_1_120*', 'md_1_120.fits', 'mb_1.fits')
    make_master_dark(camera_name, archive_path, lng_path, '*d_1_360*', 'md_1_360.fits', 'mb_1.fits')
    make_master_dark(camera_name, archive_path, lng_path, '*b_2_120*', 'md_2_120.fits', 'mb_2.fits')   # Note error in first selector
    make_master_dark(camera_name, archive_path, lng_path, '*d_3_90*', 'md_3_90.fits', 'mb_3.fits')
    make_master_dark(camera_name, archive_path, lng_path, '*d_4_60*', 'md_4_60.fits', 'mb_4.fits')
    print('Fini')
    '''
    # -*- coding: utf-8 -*-
"""
Created on Sun Feb  4 16:59:15 2018

@author: WER
Q:\archive\gf03\raw_kepler\2020-01-21
"""

"""

Goal here is a general purpose reduction module.  Ultimate
files are calibrated in units of e- and e-/s in the case
of darks.

"""

import datetime as datetime

from copy import copy, deepcopy
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




simulate = True





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



    '''
#    Need to combine temperatures and keep track of them.
#    Need to form appropriate averages.
#
#    The above is a bit sloppy.  We should writ the per day dir version of the
#    superbias first, then based on if there exists a prior lng superbias that
#    a new combined weighted bias is created.  The prior N <=4 days biases are
#    kept then aged (1*5 + 2*4 + 3*3 + 4*2 + 5*1)/16
#
#    Need to examine for hot pixels and hot columns and make entries in the 1:!
#    resolution bad pixel mask.
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
#    Need to trim negatives, and find hot pixels to create map.
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


detectors = []


#
#if __name__ == '__main__':
#
#    img = ccdproc.CCDData.read(path + 'b11.fits')
#    print(img)
#    rows = np.median(img, axis=0)
#    row_med = np.median(rows)
#    row_avg = np.mean(rows)
#    row_diff = rows - row_med
#    row_std = row_diff.std()


# =============================================================================
#ic1 = ImageFileCollection(path,
#                           keywords=keys) # only keep track of keys
#ic2 = copy.deepcopy(ic1)
#ic1 = copy.deepcopy(ic2)
# biases_1 = ic1.files_filtered(imagetyp='BIAS FRAME', exposure=0.0, xbinning=1,
#                                ybinning=1)
# ic1 = copy.deepcopy(ic2)

#biases_2 = ic1.files_filtered(imagetyp='BIAS FRAME', exposure=0.0, xbinning=2,
#                              ybinning=2)
# ic1 = copy.deepcopy(ic2)
# biases_3 = ic1.files_filtered(imagetyp='BIAS FRAME', exposure=0.0, xbinning=3,
#                                ybinning=3)
# =============================================================================
#ic1 = copy.deepcopy(ic2)
#biases_4 = ic1.files_filtered(imagetyp='BIAS FRAME', exposure=0.0, xbinning=4,
#                               ybinning=4)
#ic1 = copy.deepcopy(ic2)
#biases_5 = ic1.files_filtered(imagetyp='BIAS FRAME', exposure=0.0, xbinning=5,
#                               ybinning=5)
#print('Biases:  ', len(biases_1), len(biases_2), len(biases_3), len(biases_4), \
#      len(biases_5))

#darks_2_30 = ic1.files_filtered(imagetyp='Dark Frame', exposure=30.0, xbinning=2,
#                              ybinning=2)

#flats_2_4  = ic1.files_filtered(imagetyp='Light Frame', exposure=4.0, xbinning=2,
#                               ybinning=2)
#ic1 = copy.deepcopy(ic2)
#darks_1_120  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=120.0, xbinning=1,
#                               ybinning=1)
#ic1 = copy.deepcopy(ic2)
#darks_2_600 = ic1.files_filtered(imagetyp='DARK FRAME', exposure=600.0, xbinning=2,
#                               ybinning=1)
#ic1 = copy.deepcopy(ic2)
#darks_2_120  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=120.0, xbinning=2,
#                               ybinning=1)
#ic1 = copy.deepcopy(ic2)
#darks_3_600 = ic1.files_filtered(imagetyp='DARK FRAME', exposure=600.0, xbinning=3,
#                               ybinning=2)
#ic1 = copy.deepcopy(ic2)
#darks_3_120  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=120.0, xbinning=3,
#                               ybinning=2)
#ic1 = copy.deepcopy(ic2)
#darks_2_360 = ic1.files_filtered(imagetyp='DARK FRAME', exposure=360.0, xbinning=2,
#                               ybinning=2)
#ic1 = copy.deepcopy(ic2)
#darks_2_720  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=720.0, xbinning=2,
#                               ybinning=2)
#ic1 = copy.deepcopy(ic2)
#darks_3_120  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=120.0, xbinning=3,
#                               ybinning=3)
#ic1 = copy.deepcopy(ic2)
#darks_4_60  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=60.0, xbinning=4,
#                               ybinning=4)
#ic1 = copy.deepcopy(ic2)
#darks_5_60  = ic1.files_filtered(imagetyp='DARK FRAME', exposure=60.0, xbinning=5,
#                               ybinning=5)
#print(len(darks_1_60), len(darks_1_180), len(darks_1_360), len(darks_1_720),
#      len(darks_2_60), len(darks_2_180), len(darks_2_360), len(darks_2_720),
#      len(darks_3_120), len(darks_4_60), len(darks_5_60))
#flats_1_air = ic1.files_filtered(imagetyp='FLAT FRAME', filter='air', \
#                                 xbinning=1, ybinning=1)
#flats_1_W = ic1.files_filtered(imagetyp='FLAT FRAME', filter='W', \
#                                 xbinning=1, ybinning=1)
#flats_1_B = ic1.files_filtered(imagetyp='FLAT FRAME', filter='B', xbinning=1,
#                               ybinning=1)
#flats_1_g = ic1.files_filtered(imagetyp='FLAT FRAME', filter='g', xbinning=1,
#                               ybinning=1)
#flats_1_V = ic1.files_filtered(imagetyp='FLAT FRAME', filter='V', xbinning=1,
#                               ybinning=1)
#flats_1_r = ic1.files_filtered(imagetyp='FLAT FRAME', filter='r', xbinning=1,
#                               ybinning=1)
#flats_1_i = ic1.files_filtered(imagetyp='FLAT FRAME', filter='i', xbinning=1,
#                               ybinning=2)
#flats_1_zs = ic1.files_filtered(imagetyp='FLAT FRAME', filter='zs', xbinning=1,
#                               ybinning=1)
#flats_1_PL = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PL', xbinning=1,
#                               ybinning=1)
#flats_1_PR = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PR', xbinning=1,
#                               ybinning=1)
#flats_1_PG = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PG', xbinning=1,
#                               ybinning=1)
#flats_1_PB = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PB', xbinning=1,
#                               ybinning=1)
#flats_1_RC = ic1.files_filtered(imagetyp='FLAT FRAME', filter='RC', xbinning=1,
#                               ybinning=1)
#flats_1_NIR = ic1.files_filtered(imagetyp='FLAT FRAME', filter='NIR', xbinning=1,
#                               ybinning=1)
#flats_1_EXO = ic1.files_filtered(imagetyp='FLAT FRAME', filter='EXO', \
#                                 xbinning=1, ybinning=1)
#flats_1_Ha = ic1.files_filtered(imagetyp='FLAT FRAME', filter='Ha', xbinning=1,
#                               ybinning=1)
#flats_1_O3 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='O3', xbinning=1,
#                               ybinning=1)
#flats_1_S2 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='S2', xbinning=1,
#                               ybinning=1)
#flats_1_N2 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='N2', xbinning=1,
#                               ybinning=1)
#flats_1_dark = ic1.files_filtered(imagetyp='FLAT FRAME', filter='dark', \
#                                 binning=1, ybinning=1)
#flats_2_air = ic1.files_filtered(imagetyp='FLAT FRAME', filter='air', \
#                                 xbinning=1, ybinning=1)
#flats_2_W = ic1.files_filtered(imagetyp='FLAT FRAME', filter='W', \
#                                 xbinning=1, ybinning=1)
#flats_2_B = ic1.files_filtered(imagetyp='FLAT FRAME', filter='B', xbinning=1,
#                               ybinning=1)
#flats_2_g = ic1.files_filtered(imagetyp='FLAT FRAME', filter='g', xbinning=1,
#                               ybinning=1)
#flats_2_V = ic1.files_filtered(imagetyp='FLAT FRAME', filter='V', xbinning=1,
#                               ybinning=1)
#flats_2_r = ic1.files_filtered(imagetyp='FLAT FRAME', filter='r', xbinning=1,
#                               ybinning=1)
#flats_2_i = ic1.files_filtered(imagetyp='FLAT FRAME', filter='i', xbinning=1,
#                               ybinning=2)
#flats_2_zs = ic1.files_filtered(imagetyp='FLAT FRAME', filter='zs', xbinning=1,
#                               ybinning=1)
#flats_2_PL = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PL', xbinning=1,
#                               ybinning=1)
#flats_2_PR = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PR', xbinning=1,
#                               ybinning=1)
#flats_2_PG = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PG', xbinning=1,
#                               ybinning=1)
#flats_2_PB = ic1.files_filtered(imagetyp='FLAT FRAME', filter='PB', xbinning=1,
#                               ybinning=1)
#flats_2_RC = ic1.files_filtered(imagetyp='FLAT FRAME', filter='RC', xbinning=1,
#                               ybinning=1)
#flats_2_NIR = ic1.files_filtered(imagetyp='FLAT FRAME', filter='NIR', xbinning=1,
#                               ybinning=1)
#flats_2_EXO = ic1.files_filtered(imagetyp='FLAT FRAME', filter='EXO', \
#                                 xbinning=1, ybinning=1)
#flats_2_Ha = ic1.files_filtered(imagetyp='FLAT FRAME', filter='Ha', xbinning=1,
#                               ybinning=1)
#flats_2_O3 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='O3', xbinning=1,
#                               ybinning=1)
#flats_2_S2 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='S2', xbinning=1,
#                               ybinning=1)
#flats_2_N2 = ic1.files_filtered(imagetyp='FLAT FRAME', filter='N2', xbinning=1,
#                               ybinning=1)
#flats_2_dark = ic1.files_filtered(imagetyp='FLAT FRAME', filter='dark', \
#                                 binning=1, ybinning=1)
#print(len(flats_1_air), len(flats_1_B), len(flats_1_g), len(flats_1_V), \
#      len(flats_1_r), len(flats_1_i), len(flats_1_zs), len(flats_1_W), \
#      len(flats_1_EXO), len(flats_1_Ha), len(flats_1_O3), len(flats_1_S2), \
#      len(flats_1_N2), len(flats_1_dark))
#os.chdir(path)
#try:
#    os.mkdir('calibs')
#except:
#    pass

print('starting reductions.')
#if len(biases_5) >= 3:
#    create_super_bias(biases_5, path, oPath, "b5.fits")
#if len(biases_4) >= 3:
#    create_super_bias(biases_4, path, oPath, "b4.fits")

if __name__ == '__main__':
    path = 'Q:\\archive\\gf01\\20190914\\calib\\'
    opath = 'Q:/archive/ea03/20190503/'

    print('Finding images in:  ', path)
    imgs = glob.glob(path + '*-w-*.*')
    p = []
    q=[]
    for i in range(len(imgs)//2):
        print(imgs[i*2], imgs[i*2 + 1])
        a = ccdproc.CCDData.read(imgs[i*2])
        b = ccdproc.CCDData.read(imgs[i*2 + 1])
        ma, sa = image_stats(a)
        mb, ss = image_stats(b)
        mc = (ma + mb)/2
        r = ma/mb
        b.data *= r
        a.data = a.data - b.data
        m2a, s2a = image_stats(a)
        var = s2a*s2a/2
        p.append(ma)
        q.append(var)
    out_slope, out_intercept, out_r_value, p_value, std_err = stats.linregress(p, q)
           #out_slope, out_intercept, out_r_value, p_value, std_err = stats.linregress(v_outx, v_outy)
    plt.scatter(p,q)
    print(out_slope, out_intercept, out_r_value, p_value, std_err )

#    os.chdir(path)
#    #rename to *.fits
#    try:
#        os.mkdir(opath +'calibs')
#    except:
#        print('mkdir \'calibs\' creation faile)d at:  ', path)
#    fits_renamer(path)

#    ic1 = ImageFileCollection(path,
#                               keywords=keys) # only keep track of keys
#    ic2 = deepcopy(ic1)
#    biases_1 = ic1.files_filtered(imagetyp='Light Frame', exposure=0.0)

    print('Fini')

#    img = ccdproc.CCDData.read(path + 'bd-0034_d1_360', unit="adu")
#    print(img)

# =============================================================================
#    if len(biases_2) >= 7:
#        create_super_bias(biases_2,  oPath, "mb_2.fits")
#     if len(biases_1) >= 5:
#         create_super_bias(biases_1, path, oPath, "b1.fits")
# =============================================================================

#    create_super_dark(darks_2_30, oPath, 'md_2_30.fits', oPath +'mb_2_2018-10-16T210946.fits')

#   create_super_flat(flats_2_4, oPath, 'sc_2_30_air', oPath +'mb_2_2018-10-16T210946.fits', oPath + 'md_2_30_2018-10-16T220839.fits')

 '''