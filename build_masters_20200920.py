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
from pprint import pprint as pprint    #Note overload of a standard keyword.

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
    try:
        axis1 = img_img.meta['NAXIS1']
        axis2 = img_img.meta['NAXIS2']       
    except:
        axis1 = img_img.header['NAXIS1']
        axis2 = img_img.header['NAXIS2']
    subAxis1 = axis1/2
    patchHalf1 = axis1/10
    subAxis2 = axis2/2
    patchHalf2 = axis2/10
    sub_img = img_img.data[int(subAxis1 - patchHalf1):int(subAxis1 + patchHalf1), int(subAxis2 - patchHalf2):int(subAxis2 + patchHalf2) ]
    if p_median:
        img_mean = np.median(sub_img)
    else:
        img_mean = sub_img.mean()
    img_std = sub_img.std()
    #ADD Mode here someday.
    return round(img_mean, 2), round(img_std, 2)

def median8(img, hot_pix):
    #print('1: ',img_img.data)
    axis1 = img.shape[0]
    axis2 = img.shape[1]
    for pix in range(len(hot_pix[0])):
        iy = hot_pix[0][pix]
        ix = hot_pix[1][pix]
        med = []
        if (0 < iy < axis1 - 1) and (0 < ix < axis2 - 1):   #Needs fixing for boundary condtions.
                                                            #no changes to edge pixels as of 20200620 WER
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

def create_super_bias(input_images, out_path, lng_path, super_name):
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
            im =  ccdproc.CCDData.read(input_images[0][img])  #  , unit='adu')
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
    breakpoint()
    combiner = Combiner(super_image)
    combiner.sigma_clipping(low_thresh=2, high_thresh=3, func = np.ma.mean)
    super_img = combiner.average_combine()
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
    super_img.write(lng_path + str(super_name), overwrite=True)
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
    try:
        super_bias_img.data += super_bias_img.meta['PEDASTAL']
    except:
        pass
    while len(input_images) > 0:
        inputs = []
        print('SD chunk:  ', len(input_images[0]), input_images[0])
        len_input = len(input_images[0])
        for img in range(len_input):
            print(input_images[0][img])
            corr_dark = ccdproc.subtract_bias(
                       (ccdproc.CCDData.read(input_images[0][img])),
                        super_bias_img)
            corr_dark = corr_dark.add(corr_dark.meta['PEDASTAL']*u.adu)
            im = corr_dark
            im.data = im.data.astype(np.float32)
            inputs.append(im)
            print(im.data.mean())
            num += 1
        print(inputs[-1])
        combiner = Combiner(inputs)
        if len(inputs) > 9:
            im_temp= combiner.sigma_clipping(low_thresh=2, high_thresh=3, func=np.ma.median)
        else:
            im_temp = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func=np.ma.mean)
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
        super_img = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func=np.ma.median)
    else:
        super_img = combiner.sigma_clipping(low_thresh=2, high_thresh=3, func=np.ma.mean)
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

def organize_calib(alias, path, out_path, lng_path , selector_string, out_file):
    file_list = glob.glob(path + "*.f*t*")  # + selector_string)
    #shuffle(file_list)
    #file_list = file_list[:9*3]   #Temporarily limit size of reduction.
    print("Pre cull:  ", len(file_list))

    for item in range(len(file_list)):
        candidate = fits.open(file_list[item], ignore_missing_end=True)
        if candidate[0].header['IMAGETYP'].lower() in ['bias', 'zero', 'bias frame'] \
                and candidate[0].header['NOTE'] != 'Flush':
            if candidate[0].header['XBINING'] == 1:
                bin_str = '-b_1'
            else:
                bin_str = '-b_2'
            f_name = file_list[item].split('\\')[1]
            address = out_path + f_name[:-10] + bin_str + f_name[-10:]
            candidate.writeto(address, overwrite=True)
            candidate.close()
        #if imtype != "bias": pop it out of list
    file_list = new_list    
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

    
        # chunk = 5
        # chunked_list = chunkify(file_list, chunk)
        # print(chunked_list)
        #create_super_bias(chunked_list, lng_path, out_file )    
def linearize_unihedron(uni_value):
    #  Based on 20080811 data
    uni_value = float(uni_value)
    if uni_value < -1.9:
        uni_corr = 2.5**(-5.85 - uni_value)
    elif uni_value < -3.8:
        uni_corr = 2.5**(-5.15 - uni_value)
    elif uni_value <= -12:
        uni_corr = 2.5**(-4.88 - uni_value)
    else:
        uni_corr = 6000
    return uni_corr

def compute_sky_gains(alias, path, out_path, lng_path , selector_string, out_file):
    file_list = glob.glob(path + "*.f*t*")  # + selector_string)
    #shuffle(file_list)
    #file_list = file_list[:9*3]   #Temporarily limit size of reduction.
    print("Pre cull:  ", len(file_list))
    for item in range(len(file_list)):
        candidate = fits.open(file_list[item], ignore_missing_end=True)

        '''
        exp_time = 40000/(float(g_dev['fil'].filter_data[current_filter][3])*g_dev['ocn'].meas_sky_lux)
        
        '''
        if candidate[0].header['IMAGETYP'].lower() in ['screen flat', 'sky flat', 'screen_flat', 'sky_flat' ]: 
            exp_time = candidate[0].header['EXPTIME']
            pedastal = candidate[0].header['PEDASTAL']
            patch = candidate[0].header['PATCH']
            if patch < 2500:
                continue
            calc_sky = candidate[0].header['CALC-LUX']
            sky_mag = linearize_unihedron(candidate[0].header['SKY-LUX'])
            coef_calc = (patch + pedastal)/(exp_time*calc_sky)
            coef_meas =  (patch + pedastal)/(exp_time*sky_mag)
            print(candidate[0].header['filter'], patch, coef_calc, coef_meas)

            #candidate.writeto(address, overwrite=True)
        candidate.close()

    breakpoint()


def make_master_bias (alias, path, out_path, lng_path, selector_string, out_file):
    file_list = glob.glob(path + selector_string)  # + selector_string)
    shuffle(file_list)
    #file_list = file_list[:9*3]   #Temporarily limit size of reduction.
    print("Pre cull:  ", len(file_list))
    # new_list = []
    # for item in range(len(file_list)):
    #     candidate = fits.open(file_list[item])
    #     if candidate[0].header['IMAGETYP'].lower() in ['bias', 'zero', 'bias frame'] \
    #         and candidate[0].header['XBINING'] == 1:
    #         new_list.append(file_list[item])
    #         candidate.close()
    #     #if imtype != "bias": pop it out of list
    # file_list = new_list    
    # print('# of files:  ', len(file_list))
    # print(file_list)
    # breakpoint
    # if len(file_list) == 0:
    #     print("Empty list, returning.")
    #     return
    # if len(file_list) > 255:
    #     file_list = file_list[0:255]
    # if len(file_list) > 32:
    #     chunk = int(math.sqrt(len(file_list)))
    #     if chunk %2 == 0: chunk += 1
    # else:
    #     chunk = len(file_list)
    # if chunk > 31: chunk = 31
    # print('Chunk size:  ', chunk, len(file_list)//chunk)
    chunk = 5
    chunked_list = chunkify(file_list, chunk)
    chunked_list = chunked_list[:5]
    print(chunked_list)
    create_super_bias(chunked_list, out_path, lng_path, out_file )
    
# def analyze_bias_stack(alias, path,  lng_path , selector_string, out_file):

#     file_list = glob.glob(path + selector_string)
#     #shuffle(file_list)
#     #file_list = file_list[:9*3]   #Temporarily limit size of reduction.
#     print("Pre cull:  ", len(file_list))
#     new_list = []
#     for item in range(len(file_list)):
#         candidate = fits.open(file_list[item])
#         if candidate[0].header['IMAGETYP'].lower() == 'bias':
#             new_list.append(file_list[item])
#             candidate.close()
#         #if imtype != "bias": pop it out of list
#     file_list = new_list    
#     print('# of files:  ', len(file_list))
#     print(file_list)
#     if len(file_list) == 0:
#         print("Empty list, returning.")
#         return
#     for frame in file_list:
#         image =  ccdproc.CCDData.read(frame, format='fits', ignore_missing_end=True)
#         image.data = image.data.astype('int32') + image.header['pedastal']
#         mean, std = image_stats(image)
#         cold = np.where(image.data < -2*std)
#         breakpoint()
#         print(image_stats(image))


def make_master_dark (alias, path, lng_path, selector_string, out_file, super_bias_name):
    #breakpoint()
    file_list = glob.glob(path + selector_string)
    shuffle(file_list)
    #file_list = file_list[:9*9]   #Temporarily limit size of reduction.
    print("Pre cull:  ", len(file_list))
    new_list = []
    for item in range(len(file_list)):
        candidate = fits.open(file_list[item])
        if candidate[0].header['IMAGETYP'].lower() == 'dark':
            new_list.append(file_list[item])
            candidate.close()
        #if imtype != "bias": pop it out of list
    file_list = new_list  
    print('# of files:  ', len(file_list))
    breakpoint
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


def de_offset_and_trim(camera_name, archive_path, selector_string, out_path, full=False, norm=False):
    #NB this needs to rename fit and fts files to fits
    file_list = glob.glob(archive_path + selector_string)
 #   file_list.sort
    print(file_list)
    print('# of files:  ', len(file_list))
    p22 = 0
    p30 = 0
    p_else = 0
    for image in file_list:
        print('Processing:  ', image)
        image_hdr = fits.open(image)
        img = image_hdr[0]
        #img = ccdproc.CCDData.read(image, unit='adu', format='fits')
        # Overscan remove and trim
        if  norm:
            pedastal = 0.0
        else:
            pedastal = 200    #I guess fox for a corrupt import here at this line.
        img.data = img.data.transpose()  #Do this for convenience of sorting trimming details.
        ix, iy = img.data.shape
        '''
        img.data[22:24,-35:]
        array([[  0,   0, 132, 132, 131, 122, 125, 127, 136, 135, 135, 123,         
        '''
        if ix == 9600:
            #  NB  The special casing is fixing a problem with WMD SQ01 camera.
            if img.data[22, -34] == 0:
                p22 += 1
                overscan = int((np.median(img.data[24:, -33:]) + np.median(img.data[0:21, :]))/2) - 1
                trimmed = img.data[24:-8, :-34].astype('int32') + pedastal - overscan
                square = trimmed
                shift_error = -8
            elif img.data[30, -34] == 0:
                p30 += 1
                overscan = int((np.median(img.data[32:, -33:]) + np.median(img.data[0:29, :]))/2) - 1
                trimmed = img.data[32:, :-34].astype('int32') + pedastal - overscan
                square = trimmed
                shift_error = 0
                p_else +=1
            else:
                p_else +=1
                breakpoint()

            if full:
                square = trimmed
            else:
                square = trimmed[1590:1590 + 6388, :]
        elif ix == 4800:

            if img.data[11, -18] == 0:
                p22 += 1
                overscan = int((np.median(img.data[12:, -17:]) + np.median(img.data[0:10, :]))/2) - 1 
                trimmed = img.data[12:-4, :-17].astype('int32') + pedastal - overscan
                shift_error = -4
                square = trimmed 
            elif img.data[15, -18] == 0:
                p30 += 1
                overscan = int((np.median(img.data[16:, -17:]) + np.median(img.data[0:14, :]))/2) -1 
                trimmed = img.data[16:, :-17].astype('int32') + pedastal - overscan
                square = trimmed
                shift_error = 0
            else:
                p_else +=1
                breakpoint()

            if full:
                square = trimmed
            else:
                square = trimmed[795:795 + 3194, :]
        else:
            print("Incorrect chip size or bin specified.")
        square = square.transpose()
        std = square.std()
        smin = np.where(square < (pedastal - 6*std))    #finds negative pixels
        shot = np.where(square > (pedastal + 5*std))
        print('Mean, min, max, std, overscan, # neg, hot pixels:  ', square.mean(), square.min(), square.max(), std, overscan, len(smin[0]), len(shot[0]))
        square[smin] = 0               #marks them as , note pedastal is 100
        if not norm:img.data = square.astype('uint16')
        img.header['NAXIS1'] = square.shape[0]
        img.header['NAXIS2'] = square.shape[1]
        img.header['BUNIT'] = 'adu'
        img.header['PEDASTAL'] = -pedastal
        img.header['ERRORVAL'] = 0
        img.header['OVERSCAN'] = overscan
        if shift_error:
            img.header['SHIFTERR'] = shift_error
            
        img.header['HISTORY'] = "Maxim image debiased and trimmed."
        #img.write(out_path + image.split('\\')[1], overwrite=True)

        if norm:
            img.data = square.astype('float32')
            med, std = image_stats(img, p_median=True)
            img.data = img.data/med
            img.header['HISTORY'] = "Normalized to median of central 10%"
            img.header['PATCH'] = med
        os.makedirs(archive_path + 'trimmed/', exist_ok=True)
        image_hdr.writeto(archive_path + 'trimmed/' + image.split('\\')[1], overwrite=True)
        image_hdr.close()
    print('Debias and trim Finished.')
    


def build_hot_map(camera_name, lng_path, in_image, out_name):
    img = ccdproc.CCDData.read(lng_path + in_image, format='fits')
    img_std = img.data.std()
    img_mean = img.data.mean()
    hot_pix = np.where(img.data > 2*img_std)
    # print(img_std, img_mean, len(hot_pix[0]), hot_pix)
    # median8(img.data, hot_pix)
    # img2_std = img.data.std()
    # img2_mean = img.data.mean()
    # hot2_pix = np.where(img.data > 1*img_std)
    # print(img2_std, img2_mean, len(hot2_pix[0]), hot2_pix) #interating on this does not improve
    return hot_pix

def build_hot_image(camera_name, lng_path, in_image, out_name):
    img = ccdproc.CCDData.read(lng_path + in_image, format='fits')
    img_std = img.data.std()
    #img_mean = img.data.mean()
    hot_pix = np.where(img.data > 2*img_std)
    saved = img.data.astype('int32')
    img.data -= img.data
    for pix in range(len(hot_pix[0])):
        iy = hot_pix[0][pix]
        ix = hot_pix[1][pix]
        img.data[iy][ix] = saved[iy][ix]
    img.write(lng_path + out_name, overwrite=True)

def correct_image(camera_name, archive_path, selector_string, lng_path, out_path):
    file_list = glob.glob(archive_path + selector_string)
    file_list.sort()   #replace with a fits extension mapper and a sort. based on creation date
    pprint(file_list)
    print('# of files:  ', len(file_list))
    #Get the master images:
    sbHdu = fits.open(lng_path + 'fb_2-4.fits')
    super_bias = sbHdu[0].data.astype('float32')
    pedastal = sbHdu[0].header['PEDASTAL']
    super_bias += pedastal
    sdHdu = fits.open(lng_path + 'fd_2_120-4.fits')
    super_dark = sdHdu[0].data.astype('float32')
    super_dark_exp = sdHdu[0].header['EXPOSURE']
    sBHdu = fits.open(lng_path + 'ff_2B.fits')
    super_B = sBHdu[0].data.astype('float32')
    sVHdu = fits.open(lng_path + 'ff_2V.fits')
    super_V = sVHdu[0].data.astype('float32')
    sRHdu = fits.open(lng_path + 'ff_2ip.fits')
    super_R = sRHdu[0].data.astype('float32')
    srHdu = fits.open(lng_path + 'ff_2R.fits')
    super_rp = srHdu[0].data.astype('float32')
    sgHdu = fits.open(lng_path + 'ff_2gp.fits')
    super_gp = sgHdu[0].data.astype('float32')
    siHdu = fits.open(lng_path + 'ff_2ip.fits')
    super_ip = siHdu[0].data.astype('float32')
    sHHdu = fits.open(lng_path + 'ff_2HA.fits')
    super_HA = sHHdu[0].data.astype('float32')
    sOHdu = fits.open(lng_path + 'ff_2O33.fits')
    super_O3 = sOHdu[0].data.astype('float32')
    sSHdu = fits.open(lng_path + 'ff_2S2.fits')
    super_S2 = sSHdu[0].data.astype('float32')
    sNHdu = fits.open(lng_path + 'ff_2N2.fits')
    super_N2 = sNHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2w.fits')
    super_w = swHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2EXO.fits')
    super_EXO = swHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2air.fits')
    super_air = swHdu[0].data.astype('float32')
    shHdu = fits.open(lng_path + 'fh_2-4.fits')
    hot_map = shHdu[0].data
    hot_pix = np.where(hot_map > 1)  #
    four_std = 4*super_dark.std()   #making this more adaptive 
    hot_pix = np.where(super_dark > four_std)
    for image in file_list:

        img = fits.open(image)

        img[0].data = img[0].data.astype('float32')
        try:
            pedastal = img[0].header['PEDASTAL']
            img[0].data = img[0].data + pedastal - super_bias
        except:
            img[0].data = img[0].data - super_bias
        img_dur = img[0].header['EXPOSURE']
        try:
            ratio = img_dur/abs(super_dark_exp)
        except:
            ratio = 0    #Do not correct for dark
            
        img[0].data -= super_dark*ratio
        # if image[-3:] in ['fit', 'fts']:   #Patch a short fits suffix
        #     image = image + ('s')
        fits_filter = img[0].header['FILTER']
        if image[-5] == 'B' or fits_filter == 'B':
            img[0].data /= super_B
        elif image[-5] == 'V' or fits_filter == 'V':
            img[0].data /= super_V
        elif image[-5] == 'R' or fits_filter == 'R':
            img[0].data /= super_R
        elif image[-6] == 'g' or fits_filter == 'gp':
            img[0].data /= super_gp
        elif image[-6] == 'r' or fits_filter == 'rp':
            img[0].data /= super_rp
        elif image[-6] == 'i' or fits_filter == 'ip':
            img[0].data /= super_ip
        elif image[-6] in ['H','h']  or fits_filter == 'HA':
            img[0].data /= super_HA
        elif image[-6] == 'O: or fits_filter == O3':
            img[0].data /= super_O3
        elif image[-6] == 'S' or fits_filter == 'S2':
          img[0].data /= super_S2
        elif image[-6] == 'N' or fits_filter == 'N2':
          img[0].data /= super_N2
        elif image[-5] in ['W', 'w'] or fits_filter == 'w':
          img[0].data /= super_w
        elif image[-7] in ['E', 'e'] or fits_filter == 'EXO':
          img[0].data /= super_EXO
        elif image[-7] in ['A', 'a'] or fits_filter == 'air':
          img[0].data /= super_air
        else:
            breakpoint()
            print("Incorrect filter suffix, no flat applied.")
        median8(img[0].data, hot_pix)
        #cold = np.where(img[0].data <= 0)
        #median8(img[0].data, cold)
        #cast_32 = img[0].data.astype('float32')
        #img[0].data = cast_32
        img[0].header['CALIBRAT'] = 'B D SKF H'  #SCF SKF
        file_name_split = image.split('\\')
        print('Writing:  ', file_name_split[1])
        #  img_bk_data = img[0].data
        #  img.writeto(out_path + file_name_split[1], overwrite=True)
        os.makedirs("Q" + archive_path[1:-1]+'_floating/', exist_ok=True)
        img.writeto("Q" + archive_path[1:-1]+'_floating/' + file_name_split[1], overwrite=True)
        #  img[0].data = img_bk_data.astype('uint16')
        #  img.writeto(out_path[:-1]+'_unsigned_16int/' + file_name_split[1], overwrite=True)
        #img[0].data = (img[0].data*10).astype('int32')
        #img.writeto(out_path[:-1]+'_scaled_10X_32int/' + file_name_split[1], overwrite=True)
        img.close()

def open_ordered_file_list(archive_path, selector_string):
    file_list = glob.glob(archive_path + selector_string)
    sorted_list = []
    for image in file_list:
        img = fits.open(image)
        sorted_list.append((img[0].header['JD'], image))
    sorted_list.sort()
    return sorted_list


def sep_image(camera_name, archive_path, selector_string, lng_path, out_path):
    sorted_list = open_ordered_file_list(archive_path, selector_string)
    #file_list.sort()
    #print(file_list)
    print('# of files:  ', len(sorted_list))
    prior_img = None
    final_jd = sorted_list[-1][0]
    initial_jd = sorted_list[0][0]
    dt_jd = (final_jd - initial_jd)*86400
    dx = 136    # NB ultimately these should come from the data.
    dy = 104
    x_vel = dx/dt_jd
    y_vel = dy/dt_jd

    for entry in sorted_list:
        #print('Cataloging:  ', image)
        img = fits.open(entry[1])
        try:
            img_data = img[0].data.astype('float')
            jd = img[0].header['JD']   #or entry[0]
            bkg = sep.Background(img_data)
            #bkg_rms = bkg.rms()
            img_data -= bkg
            sources = sep.extract(img_data, 4.5, err=bkg.globalrms, minarea=15)#, filter_kernel=kern)
            sources.sort(order = 'cflux')
            #print('No. of detections:  ', len(sources))
            sep_result = []
            spots = []
            plot_x = []
            plot_y = []
            for source in sources[-1:]:
                a0 = source['a']
                b0 =  source['b']
                del_t_now = (jd - initial_jd)*86400
                cx = 1064 + x_vel*del_t_now
                cy = 3742 + y_vel*del_t_now
                #print("Shifts:  ", int(x_vel*del_t_now), int(y_vel*del_t_now), del_t_now)
                #if cx - 60 < source['x'] < cx + 60  and cy - 60 < source['y'] < cy + 60:
                    #sep_result.append([round(r0, 1), round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), jd])
                print(source['x'], source['y'], source['cflux'], entry[1].split('\\')[1])
                plot_x.append(source['x'])
                plot_y.append(source['y'])

                    # now_img = [round(r0, 1), round((source['x']), 1), round((source['x'])), 1), round((source['cflux']), 1), jd]
                    # if prior_img is None:
                    #     prior_img = [round(r0, 1), round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), jd]
                    # else:
                    #     #Now we compute differences and velocities.
                    #     delta_t = (now_img[4] - prior_img[4])*86400   #seconds
                    #     delta_x = (now_img[1] - prior_img[1])*1
                    #     delta_y = (now_img[2] - prior_img[2])*1
                    #     print(delta_x/delta_t, delta_y/delta_t, delta_t)




            #pprint(sep_result)

            print('\n')
            # try:
            #     spot = np.median(spot[-9:-2])   #  This grabs seven spots.
            #     print(sep_result,'Spot and flux:  ', spot, source['cflux'], len(sources), '\n')
            #     if len(sep_result) < 5:
            #         spot = None
            # except:
            #     spot = None
            plt.scatter(plot_x, plot_y)
        except:
            spot = None
def APPM_prepare_TPOINT():   #   'C:/ProgramData/Astro-Physics/APCC/Models/APPM-2020-08-07-031103 Trimmed.csv'
    try:
        img.close()
    except:
        pass
    img = open('C:/ProgramData/Astro-Physics/APCC/Models/APPM-2020-08-07-031103 Trimmed.csv', 'r')
    out_f = open('C:/ProgramData/Astro-Physics/APCC/Models/' + "saf_model.dat", 'w')
    out_f.write('0.3m Ceravolo, AP1600, Apache Ridge Observatory\n')
    out_f.write(':NODA\n')
    out_f.write(':EQUAT\n')
    out_f.write('35 33 16\n') #35.554444
    out_f.write('\n')
    count = 0
    for group in range(34):
        count +=1
        l1 = img.readline().split(',')
        l2 = img.readline().split(',')
        l3 = img.readline().split(',')
        l4 = img.readline().split(',')
        l5 = img.readline().split(',')
        l6 = img.readline().split(',')
        l7 = img.readline().split(',')
        l8 = img.readline().split(',')
        l9 = img.readline().split(',')
        tgt = [l6[5][:2], l6[6][:2], l6[7][:4], l6[9][:3], l6[10][:2], l6[11][1:3]]
        if tgt[3][0] != '-':
            tgt[3] = '+'+ tgt[3][:2]
        act = [l7[5][:2], l7[6][:2], l7[7][:4], l7[9][:3], l7[10][:2], l7[11][1:3], l7[12][:9]]
        if act[3][0] != '-':
            act[3] = '+'+ act[3][:2]
            if act[6][-1] == ')':
                act[6] = act[6][:-1]
        sid = [l3[4][6:13]]
        flip = [l1[2][5:6]]  #  , l1[3], l1[4]]
        act1 = act.copy()
        if flip[0] == 'F':
            #  TEl points West so flip.
            ra =int(act[0]) + 12
            if ra >= 24:
                ra -= 24
            act[0] = str(ra)
            dec = float(act[6])
            dec = 180 - dec
            deg = int(dec)
            min_sec = (dec - deg)*60
            mins = int(min_sec)
            sec = round(((min_sec) - mins)*60, 2)
            act[3] = str(deg)
            act[4] = str(mins)
            act[5] = str(sec)
            
        # print(count, tgt, act1, sid, flip)
        # print(count, tgt, act, sid, flip, '\n\n')
        
        pre_ra = tgt[0]
        pre_ram = tgt[1]
        pre_ras = tgt[2]
        pre_dec = tgt[3]
        pre_decm = tgt[4]
        pre_decs = tgt[5]
        post_ra = act[0]
        post_ram = act[1]
        post_ras = tgt[2]
        post_dec = act[3]
        post_decm = tgt[4]
        post_decs = tgt[5]
        sid_h = int(float(sid[0]))
        sid_m = round((float(sid[0]) - sid_h)*60, 3)
        sid_h_st = str(sid_h)
        sid_m_st = str(sid_m)
        
        if flip[0] == 'T':
            pier = 'EAST'
        else:
            pier = 'WEST'
        pre_ras = pre_ra + ' ' + pre_ram + ' ' + pre_ras + " "
        pre_decst = pre_dec + ' ' + pre_decm + ' ' + pre_decs + " "
        post_ras = post_ra + ' ' + post_ram + ' ' + post_ras + " "
        post_decst = post_dec + ' ' + post_decm + ' ' + post_decs + " "
        out_f.write(pre_ras  + pre_decst + post_ras + post_decst  + sid_h_st + ' ' + sid_m_st + ' ' + pier + '\n')
        print(pre_ras  + pre_decst + post_ras + post_decst  + sid_h_st + ' ' + sid_m_st + ' ' + pier)
    out_f.write('END\n')
    out_f.close()

        
        

def prepare_tpoint(camera_name, archive_path, selector_string, lng_path, out_path):
    file_list = glob.glob(archive_path + selector_string)
    file_list.sort
    print(file_list)
    print('# of files:  ', len(file_list))
    out_f = open(out_path + "tpoint_input.dat", 'w')
    out_f.write('0.3m Ceravolo, AP1600, Apache Ridge Observatory\n')
    out_f.write(':NODA\n')
    out_f.write(':EQUAT\n')
    out_f.write('35 33 15.84\n') #35.554444
    for image in file_list:
        img = fits.open(image)
        try:
            breakpoint()
            if img[0].header['PLTSOLVD'] == True:
                pre_ra = img[0].header['PRE-RA']
                pre_dec = img[0].header['PRE-DEC']
                meas_ha = img[0].header['OBJCTHA']  #Unit is hours
                meas_ra = img[0].header['OBJCTRA']
                meas_dec = img[0].header['OBJCTDEC']
                pier = img[0].header['PIERSIDE']
                m_ra = meas_ra.split()
                m_dec = meas_dec.split()
                ra = float(m_ra[0]) + (float(m_ra[2])/60. + float(m_ra[1]))/60.
                if float(m_dec[0]) < 0:
                    sgn_dec = -1
                else:
                    sgn_dec = 1
                dec = sgn_dec*(abs(float(m_dec[0])) + (float(m_dec[2])/60 + float(m_dec[2]))/60.)
                sid = round(ra + float(meas_ha), 4)
                if sid >= 24:
                    sid -= 24.
                if sid < 0: 
                    sid += 24.
                sid_h = int(sid)
                sid_m = round(((sid - sid_h)*60), 2)
                sid_str = str(sid_h) + " " + str(sid_m)
                if pier == "EAST":
                    ra -= 12
                    dec = 180 - dec
                    if ra < 0:
                        ra += 24
                    if dec < 0:
                        sign_dec = -1
                    else:
                        sign_dec = 1
                        dec = abs(dec)
                    dec_d = int(dec) 
                    dec_md = (dec - dec_d)*60
                    dec_m = int(dec_md)
                    dec_s = round(((dec_md - dec_m)*60), 1)
                    if dec >= 0:
                        dec_str = "+" + str(dec_d) + " " + str(dec_m) + " " + str(dec_s)
                    else:    
                        dec_str = "-" + str(dec_d) + " " + str(dec_m) + " " + str(dec_s)
                    ra_h = int(ra) 
                    ra_mh = (ra - ra_h)*60
                    ra_m = int(ra_mh)
                    ra_s = round(((ra_mh - ra_m)*60), 2)
                    
                    ra_str = str(ra_h) + " " + str(ra_m) + " " + str(ra_s)
                    
                    out_f.write(pre_ra + "  " + pre_dec + "  " + ra_str + "  " + dec_str + "  " + sid_str + "  " + pier + '\n')
                else:
                    pier = 'WEST'
                    out_f.write(pre_ra + "  " + pre_dec + "  " + meas_ra + "  " + meas_dec + "  " + sid_str + "  " + pier +'\n')
        except:
            continue
    out_f.write('END\n')
    out_f.close()

def annotate_image(camera_name, archive_path, selector_string, lng_path, out_path):
    file_list = glob.glob(archive_path + selector_string)
    file_list.sort()   #replace with a fits extension mapper and a sort. based on creation date
    pprint(file_list)
    print('# of files:  ', len(file_list))
    #Get the master images:
    sbHdu = fits.open(lng_path + 'fb_2-4.fits')
    super_bias = sbHdu[0].data.astype('float32')
    pedastal = sbHdu[0].header['PEDASTAL']
    super_bias += pedastal
    sdHdu = fits.open(lng_path + 'fd_2_120-4.fits')
    super_dark = sdHdu[0].data.astype('float32')
    super_dark_exp = sdHdu[0].header['EXPOSURE']
    sBHdu = fits.open(lng_path + 'ff_2B.fits')
    super_B = sBHdu[0].data.astype('float32')
    sVHdu = fits.open(lng_path + 'ff_2V.fits')
    super_V = sVHdu[0].data.astype('float32')
    sRHdu = fits.open(lng_path + 'ff_2ip.fits')
    super_R = sRHdu[0].data.astype('float32')
    srHdu = fits.open(lng_path + 'ff_2R.fits')
    super_rp = srHdu[0].data.astype('float32')
    sgHdu = fits.open(lng_path + 'ff_2gp.fits')
    super_gp = sgHdu[0].data.astype('float32')
    siHdu = fits.open(lng_path + 'ff_2ip.fits')
    super_ip = siHdu[0].data.astype('float32')
    sHHdu = fits.open(lng_path + 'ff_2HA.fits')
    super_HA = sHHdu[0].data.astype('float32')
    sOHdu = fits.open(lng_path + 'ff_2O33.fits')
    super_O3 = sOHdu[0].data.astype('float32')
    sSHdu = fits.open(lng_path + 'ff_2S2.fits')
    super_S2 = sSHdu[0].data.astype('float32')
    sNHdu = fits.open(lng_path + 'ff_2N2.fits')
    super_N2 = sNHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2w.fits')
    super_w = swHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2EXO.fits')
    super_EXO = swHdu[0].data.astype('float32')
    swHdu = fits.open(lng_path + 'ff_2air.fits')
    super_air = swHdu[0].data.astype('float32')
    shHdu = fits.open(lng_path + 'fh_2-4.fits')
    hot_map = shHdu[0].data
    hot_pix = np.where(hot_map > 1)  #
    four_std = 4*super_dark.std()   #making this more adaptive 
    hot_pix = np.where(super_dark > four_std)
    for image in file_list:

        img = fits.open(image)

        img[0].data = img[0].data.astype('float32')
        try:
            pedastal = img[0].header['PEDASTAL']
            img[0].data = img[0].data + pedastal - super_bias
        except:
            img[0].data = img[0].data - super_bias
        img_dur = img[0].header['EXPOSURE']
        try:
            ratio = img_dur/abs(super_dark_exp)
        except:
            ratio = 0    #Do not correct for dark
            
        img[0].data -= super_dark*ratio
        # if image[-3:] in ['fit', 'fts']:   #Patch a short fits suffix
        #     image = image + ('s')
        fits_filter = img[0].header['FILTER']
        if image[-5] == 'B' or fits_filter == 'B':
            img[0].data /= super_B
        elif image[-5] == 'V' or fits_filter == 'V':
            img[0].data /= super_V
        elif image[-5] == 'R' or fits_filter == 'R':
            img[0].data /= super_R
        elif image[-6] == 'g' or fits_filter == 'gp':
            img[0].data /= super_gp
        elif image[-6] == 'r' or fits_filter == 'rp':
            img[0].data /= super_rp
        elif image[-6] == 'i' or fits_filter == 'ip':
            img[0].data /= super_ip
        elif image[-6] in ['H','h']  or fits_filter == 'HA':
            img[0].data /= super_HA
        elif image[-6] == 'O: or fits_filter == O3':
            img[0].data /= super_O3
        elif image[-6] == 'S' or fits_filter == 'S2':
          img[0].data /= super_S2
        elif image[-6] == 'N' or fits_filter == 'N2':
          img[0].data /= super_N2
        elif image[-5] in ['W', 'w'] or fits_filter == 'w':
          img[0].data /= super_w
        elif image[-7] in ['E', 'e'] or fits_filter == 'EXO':
          img[0].data /= super_EXO
        elif image[-7] in ['A', 'a'] or fits_filter == 'air':
          img[0].data /= super_air
        else:
            breakpoint()
            print("Incorrect filter suffix, no flat applied.")
        median8(img[0].data, hot_pix)
        #cold = np.where(img[0].data <= 0)
        #median8(img[0].data, cold)
        #cast_32 = img[0].data.astype('float32')
        #img[0].data = cast_32
        img[0].header['CALIBRAT'] = 'B D SKF H'  #SCF SKF
        file_name_split = image.split('\\')
        #  img_bk_data = img[0].data
        #  img.writeto(out_path + file_name_split[1], overwrite=True)
        #os.makedirs("Q" + archive_path[1:-1]+'_floating/', exist_ok=True)
        file_name = file_name_split[1]
        new_file = file_name[:-9] + fits_filter +"-" +file_name[-9:]
        print("Writing:  ", new_file)
        img.writeto("Q" + archive_path[1:-4] + new_file, overwrite=True)
        #  img[0].data = img_bk_data.astype('uint16')
        #  img.writeto(out_path[:-1]+'_unsigned_16int/' + file_name_split[1], overwrite=True)
        #img[0].data = (img[0].data*10).astype('int32')
        #img.writeto(out_path[:-1]+'_scaled_10X_32int/' + file_name_split[1], overwrite=True)
        img.close()




if __name__ == '__main__':

    camera_name = 'sq01'  #  config.site_config['camera']['camera1']['name']
    #archive_path = "D:/000ptr_saf/archive/sq01/2020-06-13/"
    #archive_path = "D:/2020-06-19  Ha and O3 screen flats/"

    archive_path = "D:/000ptr_saf/archive/sq01/20201022/raw/"
    #
    out_path = 'D:/000ptr_saf/archive/sq01/20201022/tpoint/'
    lng_path = "D:/000ptr_saf/archive/sq01/lng/"
    #APPM_prepare_TPOINT()
    #de_offset_and_trim(camera_name, archive_path, '**f*t*', out_path, full=True, norm=False)
    prepare_tpoint(camera_name, archive_path, '*.fits',lng_path, out_path)
    #organize_calib(camera_name, archive_path, out_path, lng_path, '1', 'fb_1-4.fits')
    #compute_sky_gains(camera_name, archive_path, out_path, lng_path, '1', 'fb_1-4.fits')
    #make_master_bias(camera_name, archive_path, out_path, lng_path, '*b_1*', 'fb_1-4.fits')

    # make_master_bias(camera_name, archive_path, lng_path, '*EX*', 'mb_2.fits')
    # ###  analyze_bias_stack(camera_name, archive_path, lng_path, '*EX*', 'mb_2.fits')
    # #make_master_bias(camera_name, archive_path, lng_path, '*b_3*', 'mb_3.fits')
    # #make_master_bias(camera_name, archive_path, lng_path, '*b_4*', 'mb_4.fits')
    # make_master_dark(camera_name, out_path, lng_path, '*d_1*', 'md_1.fits', 'mb_1.fits')
    # make_master_dark(camera_name, out_path, lng_path, '*d_1_360*', 'md_1b.fits', 'mb_1b.fits')
    # make_master_bias(camera_name, out_path, lng_path, '*b_2*', 'mb_2.fits')
    # make_master_dark(camera_name, archive_path, lng_path, '*EX*', 'md_2_180.fits', 'mb_2.fits')
    # #make_master_dark(camera_name, archive_path, lng_path, '*d_3_90*', 'md_3.fits', 'mb_3.fits')
    # #make_master_dark(camera_name, archive_path, lng_path, '*d_4_60*', 'md_4.fits', 'mb_4.fits')
    # make_master_flat(camera_name, archive_path, lng_path, filt, out_name, 'mb_1.fits', 'md_1.fits')
    # build_hot_map(camera_name, lng_path, "md_1_1080.fits", "hm_1")
    # build_hot_image(camera_name, lng_path, "md_1_1080.fits", "hm_1.fits")

    archive_path = 'D:/000ptr_saf/archive/sq01/20201010/raw/'
    # archive_path = "D:/20200914 M33 second try/trimmed/"
    #out_path = 'Q:/M31 Moasic/20201002_BDH'
    #correct_image(camera_name, archive_path, '**f*t*', lng_path, out_path)
    #annotate_image(camera_name, archive_path, '**f*t*', lng_path, out_path)

    # mod_correct_image(camera_name, archive_path, '*EX00*', lng_path, out_path)
    # archive_path = out_path
    # out_path =":D:/20200707 Bubble Neb NGC7635  Ha O3 S2/catalogs/"
    # sep_image(camera_name, archive_path, '*7635*', lng_path, out_path)

    print('Fini')
    # NB Here we would logcially go on to get screen flats.

