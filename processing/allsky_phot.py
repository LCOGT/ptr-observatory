# -*- coding: utf-8 -*-
"""
Created on Mon Feb 22 16:20:58 2021

@author: ptr_obs
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

def sep_image(camera_name, archive_path, selector_string, lng_path, out_path):
    #sorted_list = open_ordered_file_list(archive_path, selector_string)
    sorted_list = glob.glob(archive_path + selector_string)
    sorted_list.sort()
    #print(file_list)
    print('# of files:  ', len(sorted_list))
    prior_img = None
    # final_jd = sorted_list[-1][0]
    # initial_jd = sorted_list[0][0]
    # dt_jd = (final_jd - initial_jd)  #seconds
    # dx = 136    # NB ultimately these should come from the data.
    # dy = 104
    # x_vel = dx/dt_jd
    # y_vel = dy/dt_jd
    # plot_x = []
    # plot_y = []
    # first_x = 0
    # first_y = 0
    # first_t = 0
    first = False
    items = 0            
    mean_ra = 0
    mean_dec = 0
    mean_rot = 0
    csv = []
    csvv = []
    for entry in sorted_list:
        #print('Cataloging:  ', entry)
        img = fits.open(entry)
        img_data = img[0].data.astype('float')
        date_obs = img[0].header['DATE-OBS']
        exp = img[0].header['EXPTIME']
        pfilter = img[0].header['FILTER']
        pier = img[0].header['PIERSIDE']
        air = img[0].header['AIRMASS']
        alt = img[0].header['ALTITUDE']
        az = img[0].header['AZIMUTH']
        mra = img[0].header['CRVAL1']/15.
        mdec = img[0].header['CRVAL2']
        
        mrot =  img[0].header['CROTA1']
        if items == 0:
            min_rot = mrot
            max_rot = mrot
        mzen =  img[0].header['ZENITH']
        mha =  img[0].header['MNT-HA']
        if pier in ['Undefined', 'Unknown'] or pier == 'Look East':
            pier = 0
        else:
            pier = 1
        img.close()
        csv.append(items)
        csv.append(entry)
        csv.append(date_obs)
        csv.append(exp)
        csv.append(pfilter)
        csv.append(pier)
        csv.append(mra)
        mean_ra += mra
        csv.append(mdec)
        mean_dec += mdec
        csv.append(mrot)
        min_rot = min(mrot, min_rot)
        max_rot = max(mrot, max_rot)
        mean_rot += mrot
        csv.append(mha)
        csv.append(mzen)
        csv.append(air)
        csv.append(alt)
        csv.append(az)
        items += 1
        csvv.append(csv)
        csv = []
 
    mean_ra /= items
    mean_dec /= items
    mean_rot /= items
    print(items, mean_ra, mean_dec, mean_rot, min_rot, max_rot)
    source_count = 0
    #now compute the pixel displacements
    for entry in range(len(csvv)):
        del_ra = (csvv[entry][6] - mean_ra)*15*3600/1.0552
        del_dec = (csvv[entry][7] - mean_dec)*3600/1.0552
        del_rot = (csvv[entry][8] - mean_rot)
        print(entry, del_ra, del_dec, del_rot)
        csvv[entry].append(int(del_ra))
        csvv[entry].append(int(del_dec))
        csvv[entry].append(del_rot)
        
        #Now we have gathered the alignment and flip data needed to offset
        #catalogs so they line up at least with rotation corrections.
        #So now we get the catalogs and append to csvv, and be sure to save

        entry2 = csvv[entry][1]
        img = fits.open(entry2)
        img_data = img[0].data.astype('float')
        date_obs = img[0].header['DATE-OBS']
        exp = img[0].header['EXPTIME']
        pfilter = img[0].header['FILTER']
        pier = img[0].header['PIERSIDE']
        air = img[0].header['AIRMASS']
        alt = img[0].header['ALTITUDE']
        az = img[0].header['AZIMUTH']
        mra = img[0].header['CRVAL1']/15.
        mdec = img[0].header['CRVAL2']
        
        mrot =  img[0].header['CROTA1']
        if items == 0:
            min_rot = mrot
            max_rot = mrot
        mzen =  img[0].header['ZENITH']
        mha =  img[0].header['MNT-HA']
        if pier in ['Undefined', 'Unknown'] or pier == 'Look East':
            pier = 0
        else:
            pier = 1       
        pedastal = img[0].header['PEDASTAL']
        img_data += pedastal

        # hh = int((img[0].header['DATE-OBS'][11:13]))
        # mm = int((img[0].header['DATE-OBS'][14:16]))
        # ss = float((img[0].header['DATE-OBS'][17:]))
        # jd = ss + 60*mm + 3600*hh
        bkg = sep.Background(img_data)
        #bkg_rms = bkg.rms()
        img_data -= bkg
        if True:  #bkg.globalrms > 1:  # and pfilter == 'B':
            sources = sep.extract(img_data, 4.5, err=bkg.globalrms, minarea=15)#, filter_kernel=kern)
            sources.sort(order = 'cflux')
            print(len(sources), len(csvv[entry]))
            source_count += len(sources)
            #print('RMS, No. of detections:  ', bkg.globalrms, len(sources), pfilter,  pier)
            #print(mra, mdec, mha, mzen, air, sources['cflux'][-1]/exposure)
            flux, fluxerr, flag = sep.sum_circle(img_data, sources['x'], sources['y'], 3.0, err=bkg.globalrms, gain=1.0)
            print(flux)
            csvv[entry].append(sources)
        else:
            pass#
            print("Low RMS, Skipped:  ", bkg.globalrms, len(sources), exposure)
    print(source_count, source_count/len(csvv))
    breakpoint()
            # spots = []
            # for sourcea in sources[-1:]:
            #     if not first:
            #         first_x = sourcea['x'] 
            #         first_y = sourcea['y']
            #         first_t = jd
            #         first = True
            #     a0 = sourcea['a']
            #     b0 = sourcea['b']
            #     del_t_now = (jd - first_t)
            #     #cx = 1064 + x_vel*del_t_now
            #     #cy = 3742 + y_vel*del_t_now
            #     #print("Shifts:  ", int(x_vel*del_t_now), int(y_vel*del_t_now), del_t_now)
            #     #if cx - 60 < source['x'] < cx + 60  and cy - 60 < source['y'] < cy + 60:
            #         #sep_result.append([round(r0, 1), round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), jd])
            #     print(del_t_now, del_t_now//239.346, del_t_now%239.346, sourcea['x']-first_x, sourcea['y'] - first_y, sourcea['cflux'],len(sources), entry[1].split('\\')[1])
            #     plot_x.append((sourcea['x'] - first_x)*0.26)
            #     plot_y.append((sourcea['y'] - first_y)*0.26)

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

            # try:
            #     spot = np.median(spot[-9:-2])   #  This grabs seven spots.
            #     print(sep_result,'Spot and flux:  ', spot, source['cflux'], len(sources), '\n')
            #     if len(sep_result) < 5:
            #         spot = None
            # except:
            #     spot = None
            #plt.scatter(plot_x, plot_y)

        # except:
        #     pass#print("Skipped entry:  ", entry)

if __name__ == '__main__':

    camera_name = 'sq01'  #  config.site_config['camera']['camera1']['name']
    #archive_path = "D:/000ptr_saf/archive/sq01/2020-06-13/"
    #archive_path = "D:/2020-06-19  Ha and O3 screen flats/"

    #archive_path = "Z:/wmd/saf_rosette_20/"
    #
    #out_path = 'C:/000ptr_saf/archive/sq01/fromMaxim/2020-12-20/trimmed/'
    #lng_path = "C:/000ptr_saf/archive/sq01/lng/"
    #APPM_prepare_TPOINT()
    #de_offset_and_trim(camera_name, archive_path, '*-00*.*', out_path, full=True, norm=False)
    #prepare_tpoint(camera_name, archive_path, '*.f*t*', lng_path, out_path)
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

    #archive_path = 'QC:/000ptr_saf/archive/sq01/20201207 HH/trimmed/'
    #out_path = "Q:/000ptr_saf/archive/sq01/20201207 HH/reduced/"
    #correct_image(camera_name, archive_path, '*H*H*.*', lng_path, out_path)
    archive_path = 'Z:/saf/20210306/'
    out_path = 'Z:/saf/20210306/analysis/'
    lng_path = "C:/000ptr_saf/archive/sq01/lng/"
    #annotate_image(camera_name, archive_path, '*-00*', lng_path, out_path)
    sep_image(camera_name, archive_path, '*.f*t*', lng_path, out_path)

    # mod_correct_image(camera_name, archive_path, '*EX00*', lng_path, out_path)
    #archive_path = 'Q:/000ptr_saf/archive/sq01/20201203/reduced/'
    #out_path ='Q:/000ptr_saf/archive/sq01/20201203/reduced/catalogs/'
    #sep_image(camera_name, archive_path, '*.*', lng_path, out_path)

    print('Fini')