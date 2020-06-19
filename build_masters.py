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


The output is destined for the LNG flash calibration directory.  LNG contains a sub-directory, 'priors.'  THe
idea is calibrations are gathered daily, reduced and put into prior.  then the priors are scanned and combined to
build more substantial lower noise masters.  Priors are aged and once too old are removed.  It may be the case that
we want to weight older priors lower than the current fresh one.

NB NB The chunking logic is flawed and needs a re-work, and always submit an
odd number of items to a median filter.  Use sigma-clipped mean id # of items
falls below 9.

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
from random import shuffle
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
#import config
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

def remove_overscan(image_raw):
    '''
#    Note this is camera QHY600 specific!
    '''


    breakpoint()
    if image_raw.meta['NAXIS1'] == 9600 and meta['NAXIS2'] == 6422:
        img = img_hdu[0].data.astype('float32')
        overscan_x = img[:, 2050:]
        biasline = np.median(overscan, axis=1)
        biasmean = biasline.mean()
        biasline = biasline.reshape((2048,1))
#over_2 = image_raw[-36:, :26]
#np.median(image_raw.data[:, :22])

        img_hdu[0].data = (img - biasline)[:2048,:2048].astype('uint16')

        meta['HISTORY'] = 'Median overscan subtracted and trimmed. Mean = ' + str(round(biasmean,2))

        img_hdu.writeto(opath + file_name, clobber=True)
        #Note this is equivalent to normal first time CCD wirte of a trimmed image
        count += 1
    else:
        pass
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
    first_image = ccdproc.CCDData.read(input_images[0][0])# , unit='adu')
    last_image = ccdproc.CCDData.read(input_images[-1][-1])# , unit='adu')
    super_image =[]
    super_image_sigma = []
    num = 0
    while len(input_images) > 0:  #I.e., there are chuncks to combine
        inputs = []
        print('SB chunk:  ', num+1, len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            im =  ccdproc.CCDData.read(input_images[0][img])# , unit='adu')
            im.data = im.data.astype(np.float32)
            print(im.data.mean())
            inputs.append(im)
            num += 1
        print(inputs[-1])   #show the last one
        combiner = Combiner(inputs)
        combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
        im_temp = combiner.average_combine()
        im_temp.data = im_temp.data.astype("float32")
        print(im_temp.data.mean())
        super_image.append(im_temp)
        combiner = None   #get rid of big data no longer needed.
        inputs = None
        input_images.pop(0)
    #print('SI:  ', super_image)
    print("Now we combine the outer data to make the master.")
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
    first_image = ccdproc.CCDData.read(input_images[0][0])
    last_image = ccdproc.CCDData.read(input_images[-1][-1])
    super_image =[]
    super_image_sigma = []
    num = 0
    inputs = []
    print('SD:  ', len(input_images), input_images)
    try:
        super_bias_img = ccdproc.CCDData.read(out_path + super_bias_name, ignore_missing_end=True)
    except:
        print(out_path + super_bias_name, 'failed')
    while len(input_images) > 0:
        inputs = []
        print('SD chunk:  ', len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            corr_dark = ccdproc.subtract_bias(
                       (ccdproc.CCDData.read(input_images[0][img])),
                        super_bias_img)
            im = corr_dark
            im.data = im.data.astype(np.float32)
            inputs.append(im)
            print(im.data.mean())
            num += 1
        print(inputs[-1])
        combiner = Combiner(inputs)
        if len(inputs) > 9:
            im_temp= combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.median)
        else:
            im_temp = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
        im_temp = combiner.average_combine()
        im_temp.data = im_temp.data.astype(np.float32)
        print(im_temp.data.mean())
        #breakpoint()
        super_image.append(im_temp)
        combiner = None   #get rid of big data no longer needed.
        inputs = None

        input_images.pop(0)
    print("Now we combine the outer data to make the master.")
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

def create_super_flat(input_images, lng_path, super_name, super_bias_name,
                      super_dark_name):

    #chunked_list, lng_path, out_name, super_bias_name, super_dark_name
    #super_dark = super_dark.subtract(super_dark.meta['PEDASTAL']*u.adu)
    first_image = ccdproc.CCDData.read(input_images[0][0], format='fits')
    #last_image = ccdproc.CCDData.read(input_images[-1][-1], format='fits')
    super_image =[]
    super_image_sigma = []
    num = 0
    inputs = []
    print('SD:  ', len(input_images), input_images)
    try:
        super_bias = ccdproc.CCDData.read(lng_path + super_bias_name, ignore_missing_end=True)
        super_bias = super_bias.add(super_bias.meta['PEDASTAL']*u.adu)
        super_dark = ccdproc.CCDData.read(lng_path + super_dark_name, ignore_missing_end=True)
        #super_dark = super_dark.subtract(super_dark.meta['PEDASTAL']*u.adu)   #SHOULD NOT BE NEEDED.
    except:
        print(out_path + super_bias_name, 'failed')
    while len(input_images) > 0:
        inputs = []
        print('SD chunk:  ', len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len(input_images)):
            img_in = ccdproc.CCDData.read(input_images[0][img],   format='fits', ignore_missing_end=True)
            bias_corr = ccdproc.subtract_bias(img_in, super_bias)
            #print('Dark:  ', super_dark.meta['EXPTIME'], img_in.meta['EXPTIME'], type(bias_corr), type(super_dark))
            corr_flat = ccdproc.subtract_dark(bias_corr, super_dark, scale=True, \
                        dark_exposure=super_dark.meta['EXPTIME']*u.s, \
                        data_exposure =img_in.meta['EXPTIME']*u.s)
            im = corr_flat
            im.data /= np.median(im.data)
            im.data = im.data.astype(np.float32)
            inputs.append(im)
            print(im.data.mean())
            num += 1
        print(inputs[-1])
        combiner = Combiner(inputs)
        if len(inputs) > 9:
            im_temp= combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.median)
        else:
            im_temp = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
        im_temp = combiner.average_combine()
        im_temp.data = im_temp.data.astype(np.float32)
        print(im_temp.data.mean())
        #breakpoint()
        super_image.append(im_temp)
        combiner = None   #get rid of big data no longer needed.
        inputs = None
        input_images.pop(0)
    print("Now we combine the outer data to make the master.")
    combiner = Combiner(super_image)
    if len(super_image) > 5:
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
    wstring = str(lng_path + super_name + '.fits')
    super_img.write(wstring, overwrite=True, format='fits')
    super_img = None    #Again get rid of big stale data
    #hot and cold pix here.inputs.append(corr_flat)
    return

def make_master_bias (alias, path,  lng_path ,selector_string, out_file):

    file_list = glob.glob(path + selector_string)
    shuffle(file_list)
    file_list = file_list[:9*9]   #Temporarily limit size of reduction.
    print('# of files:  ', len(file_list))

    print(file_list)

    if len(file_list) == 0:
        print("Empty list, returning.")
        return
    if len(file_list) > 255:
        file_list = file_list[0:255]
    if len(file_list) > 32:
        chunk = int(math.sqrt(len(file_list)))
        if chunk %2 == 0: chunk += 1
    else:
        chunk = len(file_list)
    if chunk > 31: chunk = 31
    print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunk = 9
    chunked_list = chunkify(file_list, chunk)
    print(chunked_list)
    create_super_bias(chunked_list, lng_path, out_file )

def make_master_dark (alias, path, lng_path, selector_string, out_file, super_bias_name):
    #breakpoint()
    file_list = glob.glob(path + selector_string)
    shuffle(file_list)
    file_list = file_list[:9*9]   #Temporarily limit size of reduction.

    print('# of files:  ', len(file_list))
    print(file_list)
    if len(file_list) > 63:
        file_list = file_list[0:63]
    if len(file_list) > 32:
        chunk = int(math.sqrt(len(file_list)))
        if chunk %2 == 0: chunk += 1
    else:
        chunk = len(file_list)
    if chunk > 31: chunk = 31
    print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunk = 9
    chunked_list = chunkify(file_list, chunk)
    print(chunked_list)

    create_super_dark(chunked_list, lng_path, out_file, super_bias_name )

def make_master_flat (alias, path, lng_path, selector_string, out_name, super_bias_name, \

                      super_dark_name):
    #breakpoint()
    file_list = glob.glob(path + selector_string)
    if len(file_list) < 3:
        return

    shuffle(file_list)
    file_list = file_list[:9*9]   #Temporarily limit size of reduction.

    print('# of files:  ', len(file_list))
    print(file_list)
    if len(file_list) > 63:
        file_list = file_list[0:63]
    if len(file_list) > 32:
        chunk = int(math.sqrt(len(file_list)))
        if chunk %2 == 0: chunk += 1
    else:
        chunk = len(file_list)
    if chunk > 31: chunk = 31
    print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunk = 9
    chunked_list = chunkify(file_list, chunk)
    print(chunked_list)

    create_super_flat(chunked_list, lng_path, out_name, super_bias_name, super_dark_name)


def debias_and_trim(camera_name, archive_path, out_path):
    #NB this needs to rename fit and fts files to fits
    file_list = glob.glob(archive_path + "*m8*")
    file_list.sort
    print(file_list)
    print('# of files:  ', len(file_list))
    for image in file_list:
        print('Processing:  ', image)
        #breakpoint()
        img = ccdproc.CCDData.read(image, unit='adu', format='fits')
        # Overscan remove and trim
        pedastal = 200
        iy, ix = img.data.shape
        if ix == 9600:
            overscan = int(np.median(img.data[33:, -22:]))
            trimed = img.data[36:,:-26].astype('int32') + pedastal - overscan
            square = trimed[121:121+6144,1715:1715+6144]
        elif ix == 4800:
            overscan = int(np.median(img.data[17:, -11:]))
            trimed = img.data[18:,:-13].astype('int32') + pedastal - overscan
            square = trimed[61:61+3072,857:857+3072]
        else:
            print("Incorrect chip size or bin specified.")
        smin = np.where(square < 0)    #finds negative pixels
        std = square.std()
        shot = np.where(square > (pedastal + 3*std))
        print('Mean, std, overscan, # neg, hot pixels:  ', square.mean(), std, overscan, len(smin[0]), len(shot[0]))
        square[smin] = 0               #marks them as 0
        img.data = square.astype('uint16')
        img.meta['PEDASTAL'] = -pedastal
        img.meta['ERRORVAL'] = 0
        img.meta['OVERSCAN'] = overscan
        img.meta['HISTORY'] = "Maxim image debiased and trimmed."
        img.write(out_path + image.split('\\')[1], overwrite=True)
    print('Debias and trim Finished.')

if __name__ == '__main__':
    camera_name = 'sq01'  #  config.site_config['camera']['camera1']['name']
    #archive_path = "D:/000ptr_saf/archive/sq01/2020-06-13/"
    #archive_path = "D:/2020-06-19  Ha and O3 screen flats/"
    archive_path = "D:/2020-06-19 qhy600 hA AND O3 LAGOON IMAGES/"
    out_path = "D:/000ptr_saf/archive/sq01/20200618/lagoon/"
    lng_path = "D:/000ptr_saf/archive/sq01/lng/"
    # debias_and_trim(camera_name, archive_path, out_path)
    # make_master_bias(camera_name, archive_path, lng_path, '*b_1*', 'mb_1.fits')
    # make_master_bias(camera_name, archive_path, lng_path, '*b_2*', 'mb_2.fits')
    # #make_master_bias(camera_name, archive_path, lng_path, '*b_3*', 'mb_3.fits')
    # #make_master_bias(camera_name, archive_path, lng_path, '*b_4*', 'mb_4.fits')
    # #make_master_dark(camera_name, archive_path, lng_path, '*d_1_120*', 'md_1_120.fits', 'mb_1.fits')
    # make_master_dark(camera_name, archive_path, lng_path, '*d_1_360*', 'md_1.fits', 'mb_1.fits')
    # make_master_dark(camera_name, archive_path, lng_path, '*d_2_90*', 'md_2.fits', 'mb_2.fits')
    # #make_master_dark(camera_name, archive_path, lng_path, '*d_3_90*', 'md_3.fits', 'mb_3.fits')
    # #make_master_dark(camera_name, archive_path, lng_path, '*d_4_60*', 'md_4.fits', 'mb_4.fits')
#make_master_flat(camera_name, archive_path, lng_path, filt, out_name, 'mb_1.fits', 'md_1.fits')
    print('Fini')
    # NB Here we would logcially go on to get screen flats.

