# -*- coding: utf-8 -*-
"""
photometry_process.py   photometry_process.py   photometry_process.py

Created on Sun Apr 23 04:37:30 2023

@author: observatory
"""

import numpy as np
import bottleneck as bn
# Need this line to output the full array to text for the json
np.set_printoptions(threshold=np.inf)
import re
from astropy.stats import median_absolute_deviation
from astropy.nddata.utils import extract_array
import pickle
import time
import traceback
import math
import os
import sys
import json
import sep
import copy
from auto_stretch.stretch import Stretch
from astropy.io import fits
#import sys
# from astropy.nddata import block_reduce
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
from PIL import Image, ImageDraw
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)
#import matplotlib.pyplot as plt
from scipy.stats import binned_statistic

# Add the parent directory to the Python path
# This allows importing modules from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ptr_utility import create_color_plog

log_color = (255, 130, 200) # pink
plog = create_color_plog('photometry', log_color)


plog("Starting photometry_process.py")


def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev)**2)

imageinspection_json_snippets={}
starinspection_json_snippets={}

def radial_profile(data, center):
    y, x = np.indices((data.shape))
    r = np.sqrt((x - center[0])**2 + (y - center[1])**2)
    r = r.astype(int)

    tbin = np.bincount(r.ravel(), data.ravel())
    nr = np.bincount(r.ravel())
    radialprofile = tbin / nr
    return radialprofile

use_test_inputs = False
if use_test_inputs:
    plog("Using test inputs for the photometry process")
    inputs = pickle.load(open('test_photometry_subprocess_pickle','rb'))
else:
    inputs = pickle.load(sys.stdin.buffer)


# Extract values from the structured dictionary
# File info
photometry_thread_filename = inputs["file_info"]["photometry_thread_filename"]
im_path = inputs["file_info"]["im_path"]
text_name = inputs["file_info"]["text_name"]
cal_path = inputs["file_info"]["cal_path"]
cal_name = inputs["file_info"]["cal_name"]

# Camera settings
pixscale = inputs["camera_settings"]["pixscale"]
readnoise = inputs["camera_settings"]["readnoise"]
native_bin = inputs["camera_settings"]["native_bin"]
saturate = inputs["camera_settings"]["saturate"]

# Processing options
is_osc = inputs["processing_options"]["is_osc"]
frame_type = inputs["processing_options"]["frame_type"]
minimum_realistic_seeing = inputs["processing_options"]["minimum_realistic_seeing"]

# Metadata
hduheader = inputs["metadata"]["hduheader"]
gdevevents = inputs["metadata"]["events"]
ephemnow = inputs["metadata"]["ephem_now"]
exposure_time = inputs["metadata"]["exposure_time"]


############ WAITER FOR
# the filename token to arrive to start processing
plog (photometry_thread_filename)

file_wait_timeout_timer=time.time()

while (not os.path.exists(photometry_thread_filename)) and (time.time()-file_wait_timeout_timer < 600):
    time.sleep(0.2)

if time.time()-file_wait_timeout_timer > 599:
    sys.exit()


(image_filename,imageMode, unique, counts)=pickle.load(open(photometry_thread_filename,'rb'))


hdufocusdata=np.load(image_filename)

#hduheader=fits.open(image_filename.replace('.npy','.head'))[0].header
with fits.open(image_filename.replace('.npy','.head')) as hdul:
    hduheader = hdul[0].header

# If there is no known pixelscale yet use a standard value just to get rough photometry
if pixscale == None:
    pixscale = 0.5

# The photometry has a timelimit that is half of the exposure time
time_limit=max(min (float(hduheader['EXPTIME'])*0.5, 20, exposure_time*0.5),5)

minimum_exposure_for_extended_stuff = 10

plog ("Time Limit: " + str(time_limit))

# https://stackoverflow.com/questions/9111711/get-coordinates-of-local-maxima \
    #-in-2d-array-above-certain-value
def localMax(a, include_diagonal=True, threshold=-np.inf) :
    # Pad array so we can handle edges
    ap = np.pad(a, ((1,1),(1,1)), constant_values=-np.inf )

    # Determines if each location is bigger than adjacent neighbors
    adjacentmax =(
    (ap[1:-1,1:-1] > threshold) &
    (ap[0:-2,1:-1] <= ap[1:-1,1:-1]) &
    (ap[2:,  1:-1] <= ap[1:-1,1:-1]) &
    (ap[1:-1,0:-2] <= ap[1:-1,1:-1]) &
    (ap[1:-1,2:  ] <= ap[1:-1,1:-1])
    )
    if not include_diagonal :
        return np.argwhere(adjacentmax)

    # Determines if each location is bigger than diagonal neighbors
    diagonalmax =(
    (ap[0:-2,0:-2] <= ap[1:-1,1:-1]) &
    (ap[2:  ,2:  ] <= ap[1:-1,1:-1]) &
    (ap[0:-2,2:  ] <= ap[1:-1,1:-1]) &
    (ap[2:  ,0:-2] <= ap[1:-1,1:-1])
    )

    return np.argwhere(adjacentmax & diagonalmax)

# no zero values in readnoise.
if float(readnoise) < 0.1:
    readnoise = 0.1

if float(hduheader["EXPTIME"]) < 1.0:
    rfp = np.nan
    rfr = np.nan
    rfs = np.nan
    sepsky = np.nan
    pickle.dump([], open(im_path + text_name.replace('.txt', '.tempsep'),'wb'))
    os.rename(im_path + text_name.replace('.txt', '.tempsep'),im_path + text_name.replace('.txt', '.sep'))

    sources = [0]
    rfp = np.nan
    rfr = np.nan
    rfs = np.nan
    sepsky = np.nan
    fwhm_file={}
    fwhm_file['rfp']=str(rfp)
    fwhm_file['rfr']=str(rfr)
    fwhm_file['rfs']=str(rfs)
    fwhm_file['sky']=str(sepsky)
    fwhm_file['sources']=str(len(sources))
    # dump the settings files into the temp directory
    with open(im_path + text_name.replace('.txt', '.tempfwhm'), 'w') as f:
        json.dump(fwhm_file, f)
    os.rename(im_path + text_name.replace('.txt', '.tempfwhm'),im_path + text_name.replace('.txt', '.fwhm'))

else:


    if is_osc:
        # Rapidly interpolate so that it is all one channel

        # Wipe out red channel
        hdufocusdata[::2, ::2]=np.nan
        # Wipe out blue channel
        hdufocusdata[1::2, 1::2]=np.nan

        # To fill the checker board, roll the array in all four directions and take the average
        # Which is essentially the bilinear fill without excessive math or not using numpy
        # It moves true values onto nans and vice versa, so makes an array of true values
        # where the original has nans and we use that as the fill
        bilinearfill=np.roll(hdufocusdata,1,axis=0)
        bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=0))
        bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,1,axis=1))
        bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=1))
        bilinearfill=np.divide(bilinearfill,4)
        hdufocusdata[np.isnan(hdufocusdata)]=0
        bilinearfill[np.isnan(bilinearfill)]=0
        hdufocusdata=hdufocusdata+bilinearfill
        del bilinearfill

    try:

        fx, fy = hdufocusdata.shape        #

        bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
        bkg.subfrom(hdufocusdata)

        tempstd=np.std(hdufocusdata)
        hduheader["IMGSTDEV"] = ( tempstd, "Median Value of Image Array" )
        try:
            threshold=max(3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)]),(200*pixscale)) # Don't bother with stars with peaks smaller than 100 counts per arcsecond
        except:
            threshold=max(3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)]),(200*0.1)) # Don't bother with stars with peaks smaller than 100 counts per arcsecond

        googtime=time.time()
        list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
        plog ("Finding Local Maxima: " + str(time.time()-googtime))

        # Assess each point
        pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
        counter=0
        googtime=time.time()
        for point in list_of_local_maxima:

            pointvalues[counter][0]=point[0]
            pointvalues[counter][1]=point[1]
            pointvalues[counter][2]=np.nan
            in_range=False
            if (point[0] > fx*0.1) and (point[1] > fy*0.1) and (point[0] < fx*0.9) and (point[1] < fy*0.9):
                in_range=True

            if in_range:
                value_at_point=hdufocusdata[point[0],point[1]]
                try:
                    value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
                except:
                    plog(traceback.format_exc())
                    #breakpoint()

                # Check it isn't just a dot
                if value_at_neighbours < (0.4*value_at_point):
                    #plog ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
                    pointvalues[counter][2]=np.nan

                # If not saturated and far away from the edge
                elif value_at_point < 0.8*saturate:
                    pointvalues[counter][2]=value_at_point

                else:
                    pointvalues[counter][2]=np.nan

            counter=counter+1

        plog ("Sorting out bad pixels from the mix: " + str(time.time()-googtime))


        # Trim list to remove things that have too many other things close to them.

        googtime=time.time()
        # remove nan rows
        pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

        # reverse sort by brightness
        pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]

        #From...... NOW
        timer_for_bailing=time.time()

        # radial profile
        fwhmlist=[]
        sources=[]
        photometry=[]

        # The radius should be related to arcseconds on sky
        # And a reasonable amount - 12'
        try:
            radius_of_radialprofile=int(24/pixscale)
        except:
            radius_of_radialprofile=int(24/0.1)
        # Round up to nearest odd number to make a symmetrical array
        radius_of_radialprofile=int(radius_of_radialprofile // 2 *2 +1)
        halfradius_of_radialprofile=math.ceil(0.5*radius_of_radialprofile)
        centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        googtime=time.time()

        number_of_good_radials_to_get = 50
        good_radials=0

        # Construct testing array
        # Initially on pixelscale then convert to pixels
        testvalue=0.1
        testvalues=[]
        while testvalue < 12:
            if testvalue > 1 and testvalue < 6:
                testvalues.append(testvalue)
                testvalues.append(testvalue+0.05)
            elif testvalue > 6:
                if (int(testvalue * 10) % 3) == 0 :
                    testvalues.append(testvalue)
            else:
                testvalues.append(testvalue)
            testvalue=testvalue+0.1
        # convert pixelscales into pixels
        try:
            pixel_testvalues=np.array(testvalues) / pixscale
        except:
            pixel_testvalues=np.array(testvalues) / 0.5

        for i in range(len(pointvalues)):
            # Don't take too long!
            if ((time.time() - timer_for_bailing) > time_limit):# and good_radials > 20:
                plog ("Time limit reached! Bailout!")
                break

            cx= int(pointvalues[i][0])
            cy= int(pointvalues[i][1])
            cvalue=hdufocusdata[int(cx)][int(cy)]
            try:
                temp_array=hdufocusdata[cx-halfradius_of_radialprofile:cx+halfradius_of_radialprofile,cy-halfradius_of_radialprofile:cy+halfradius_of_radialprofile]

            except:
                plog(traceback.format_exc())

            #construct radial profile
            cut_x,cut_y=temp_array.shape
            cut_x_center=(cut_x/2)-1
            cut_y_center=(cut_y/2)-1
            radprofile=np.zeros([cut_x*cut_y,2],dtype=float)
            counter=0
            brightest_pixel_rdist=0
            brightest_pixel_value=0
            bailout=False
            for q in range(cut_x):
                if bailout==True:
                    break
                for t in range(cut_y):
                    r_dist=pow(pow((q-cut_x_center),2) + pow((t-cut_y_center),2),0.5)
                    if q-cut_x_center < 0:# or t-cut_y_center < 0:
                        r_dist=r_dist*-1
                    radprofile[counter][0]=r_dist
                    radprofile[counter][1]=temp_array[q][t]
                    if temp_array[q][t] > brightest_pixel_value:
                        brightest_pixel_rdist=r_dist
                        brightest_pixel_value=temp_array[q][t]
                    counter=counter+1

            # If the brightest pixel is in the center-ish
            # then attempt a fit
            try:
                maxvalue=max(3, 3/pixscale)
            except:
                maxvalue=20
            if abs(brightest_pixel_rdist) < max(3, maxvalue):
                try:
                    # Reduce data down to make faster solvinging
                    upperbin=math.floor(max(radprofile[:,0]))
                    lowerbin=math.ceil(min(radprofile[:,0]))
                    # Only need a quarter of an arcsecond bin.
                    arcsecond_length_radial_profile = (upperbin-lowerbin)*pixscale
                    number_of_bins=int(arcsecond_length_radial_profile/0.25)
                    s, edges, _ = binned_statistic(radprofile[:,0],radprofile[:,1], statistic='mean', bins=np.linspace(lowerbin,upperbin,number_of_bins))

                    max_value=np.nanmax(s)
                    min_value=np.nanmin(s)
                    threshold_value=(0.05*(max_value-min_value)) + min_value

                    actualprofile=[]
                    for q in range(len(s)):
                        if not np.isnan(s[q]):
                            if s[q] > threshold_value:
                                actualprofile.append([(edges[q]+edges[q+1])/2,s[q]])

                    actualprofile=np.asarray(actualprofile)

                    edgevalue_left=actualprofile[0][1]
                    edgevalue_right=actualprofile[-1][1]

                    # Also remove any things that don't have many pixels above 20
                    # DO THIS SOON
                    if edgevalue_left < 0.6*cvalue and  edgevalue_right < 0.6*cvalue:

                        # Different faster fitter to consider
                        peak_value_index=np.argmax(actualprofile[:,1])
                        peak_value=actualprofile[peak_value_index][1]
                        x_axis_of_peak_value=actualprofile[peak_value_index][0]

                        # Get the mean of the 5 pixels around the max
                        # and use the mean of those values and the peak value
                        # to use as the amplitude
                        temp_amplitude=actualprofile[peak_value_index-2][1]+actualprofile[peak_value_index-1][1]+actualprofile[peak_value_index][1]+actualprofile[peak_value_index+1][1]+actualprofile[peak_value_index+2][1]
                        temp_amplitude=temp_amplitude/5
                        # Check that the mean of the temp_amplitude here is at least 0.6 * cvalue
                        if temp_amplitude > 0.5*peak_value:

                            # Get the center of mass peak value
                            sum_of_positions_times_values=0
                            sum_of_values=0
                            number_of_positions_to_test=7 # odd value
                            poswidth=int(number_of_positions_to_test/2)

                            for spotty in range(number_of_positions_to_test):
                                sum_of_positions_times_values=sum_of_positions_times_values+(actualprofile[peak_value_index-poswidth+spotty][1]*actualprofile[peak_value_index-poswidth+spotty][0])
                                sum_of_values=sum_of_values+actualprofile[peak_value_index-poswidth+spotty][1]
                            peak_position=(sum_of_positions_times_values / sum_of_values)
                            temppos=abs(actualprofile[:,0] - peak_position).argmin()
                            tempvalue=actualprofile[temppos,1]
                            temppeakvalue=copy.deepcopy(tempvalue)
                            # Get lefthand quarter percentiles
                            counter=1
                            while tempvalue > 0.25*temppeakvalue:
                                tempvalue=actualprofile[temppos-counter,1]
                                if tempvalue > 0.75:
                                    threequartertemp=temppos-counter
                                counter=counter+1

                            lefthand_quarter_spot=actualprofile[temppos-counter][0]
                            lefthand_threequarter_spot=actualprofile[threequartertemp][0]

                            # Get righthand quarter percentile
                            counter=1
                            while tempvalue > 0.25*temppeakvalue:
                                tempvalue=actualprofile[temppos+counter,1]
                                #plog (tempvalue)
                                if tempvalue > 0.75:
                                    threequartertemp=temppos+counter
                                counter=counter+1

                            righthand_quarter_spot=actualprofile[temppos+counter][0]
                            righthand_threequarter_spot=actualprofile[threequartertemp][0]

                            largest_reasonable_position_deviation_in_pixels=1.25*max(abs(peak_position - righthand_quarter_spot),abs(peak_position - lefthand_quarter_spot))
                            largest_reasonable_position_deviation_in_arcseconds=largest_reasonable_position_deviation_in_pixels *pixscale

                            smallest_reasonable_position_deviation_in_pixels=0.7*min(abs(peak_position - righthand_threequarter_spot),abs(peak_position - lefthand_threequarter_spot))
                            smallest_reasonable_position_deviation_in_arcseconds=smallest_reasonable_position_deviation_in_pixels *pixscale

                            # If peak reasonably in the center
                            # And the largest reasonable position deviation isn't absurdly small
                            if abs(peak_position) < max(3, 3/pixscale) and largest_reasonable_position_deviation_in_arcseconds > 1.0:
                                # Construct testing array
                                # Initially on pixelscale then convert to pixels
                                testvalue=0.1
                                testvalues=[]
                                while testvalue < 12:
                                    if testvalue > smallest_reasonable_position_deviation_in_arcseconds and testvalue < largest_reasonable_position_deviation_in_arcseconds:
                                        if testvalue > 1 and testvalue <= 7:
                                            testvalues.append(testvalue)
                                            testvalues.append(testvalue+0.05)
                                        elif testvalue > 7:
                                            if (int(testvalue * 10) % 3) == 0 :
                                                testvalues.append(testvalue)
                                        else:
                                            testvalues.append(testvalue)
                                    testvalue=testvalue+0.1
                                # convert pixelscales into pixels
                                pixel_testvalues=np.array(testvalues) / pixscale
                                # convert fwhm into appropriate stdev
                                pixel_testvalues=(pixel_testvalues/2.355) /2

                                smallest_value=999999999999999.9
                                for pixeltestvalue in pixel_testvalues:

                                    test_fpopt= [peak_value, peak_position, pixeltestvalue]

                                    # differences between gaussian and data
                                    difference=(np.sum(abs(actualprofile[:,1] - gaussian(actualprofile[:,0], *test_fpopt))))

                                    if difference < smallest_value:
                                        smallest_value=copy.deepcopy(difference)
                                        smallest_fpopt=copy.deepcopy(test_fpopt)

                                    if difference < 1.25 * smallest_value:
                                        if False:
                                            # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                                            # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *test_fpopt),color = 'r')
                                            # # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                                            # plt.show()
                                            pass
                                        pass
                                    else:
                                        #plog ("gone through and sampled range enough")
                                        break


                                # if it isn't a unreasonably small fwhm then measure it.
                                if (2.355 * smallest_fpopt[2]) > (0.8 / pixscale) :

                                    # FWHM is 2.355 * std for a gaussian
                                    fwhmlist.append(smallest_fpopt[2])
                                    # Area under a 1D gaussian is (amplitude * Stdev / 0.3989)

                                    # Volume under the 2D-Gaussian is computed as: 2 * pi * sqrt(abs(X_sig)) * sqrt(abs(Y_sig)) * amplitude
                                    # But our sigma in both dimensions are the same so sqrt times sqrt of something is equal to the something
                                    countsphot= 2 * math.pi * smallest_fpopt[2] * smallest_fpopt[0]

                                    if good_radials < number_of_good_radials_to_get:
                                        sources.append([cx,cy,radprofile,temp_array,cvalue, countsphot,smallest_fpopt[0],smallest_fpopt[1],smallest_fpopt[2],'r'])
                                        good_radials=good_radials+1
                                    else:
                                        sources.append([cx,cy,0,0,cvalue, countsphot,smallest_fpopt[0],smallest_fpopt[1],smallest_fpopt[2],'n'])
                                    photometry.append([cx,cy,cvalue,smallest_fpopt[0],smallest_fpopt[2]*4.710,countsphot])
                except:
                    pass

        plog ("Extracting and Gaussianingx: " + str(time.time()-googtime))
        plog ("N of sources processed: " + str(len(sources)))

        rfp = abs(bn.nanmedian(fwhmlist)) * 4.710
        rfr = rfp * pixscale
        rfs = bn.nanstd(fwhmlist) * pixscale
        if rfr < 1.0 or rfr > 12:
            rfr= np.nan
            rfp= np.nan
            rfs= np.nan

        sepsky = imageMode
        fwhm_file={}
        fwhm_file['rfp']=str(rfp)
        fwhm_file['rfr']=str(rfr)
        fwhm_file['rfs']=str(rfs)
        fwhm_file['sky']=str(imageMode)
        fwhm_file['sources']=str(len(fwhmlist))
        with open(im_path + text_name.replace('.txt', '.tempfwhm'), 'w') as f:
            json.dump(fwhm_file, f)
        try:
            os.rename(im_path + text_name.replace('.txt', '.tempfwhm'),im_path + text_name.replace('.txt', '.fwhm'))
        except:
            plog ("tried to save fwhm file but it was already there.")

        # This pickled sep file is for internal use - usually used by the smartstack thread to align mono smartstacks.
        pickle.dump(photometry, open(im_path + text_name.replace('.txt', '.tempsep'),'wb'))
        try:
            os.rename(im_path + text_name.replace('.txt', '.tempsep'),im_path + text_name.replace('.txt', '.sep'))
        except:
            plog ("tried to save sep file but it was already there.")

        # Grab the central arcminute out of the image.
        cx = int(fx/2)
        cy = int(fy/2)
        width = math.ceil(30 / pixscale)
        central_half_arcminute=copy.deepcopy(hdufocusdata[cx-width:cx+width,cy-width:cy+width])
        imageinspection_json_snippets['central_patch']= re.sub('\s+',' ',str(central_half_arcminute))

    except:
        traceback.format_exc()
        sources = [0]
        rfp = np.nan
        rfr = np.nan
        rfs = np.nan
        sepsky = np.nan
        fwhm_file={}
        fwhm_file['rfp']=str(rfp)
        fwhm_file['rfr']=str(rfr)
        fwhm_file['rfs']=str(rfs)
        fwhm_file['sky']=str(sepsky)
        fwhm_file['sources']=str(len(sources))
        # dump the settings files into the temp directory
        with open(im_path + text_name.replace('.txt', '.tempfwhm'), 'w') as f:
            json.dump(fwhm_file, f)
        os.rename(im_path + text_name.replace('.txt', '.tempfwhm'),im_path + text_name.replace('.txt', '.fwhm'))
        imageinspection_json_snippets['fwhm']=fwhm_file
        starinspection_json_snippets['fwhm']=fwhm_file

        pickle.dump([], open(im_path + text_name.replace('.txt', '.tempsep'),'wb'))
        os.rename(im_path + text_name.replace('.txt', '.tempsep'),im_path + text_name.replace('.txt', '.sep'))

# These broad image statistics also take a few seconds on a QHY600 image
# But are not needed for a focus image.
if not frame_type == 'focus' and False: # The False is here because we don't actually use this yet, but it is working
    googtime=time.time()
    hduheader["IMGMIN"] = ( np.min(hdufocusdata), "Minimum Value of Image Array" )
    hduheader["IMGMAX"] = ( np.max(hdufocusdata), "Maximum Value of Image Array" )
    hduheader["IMGMEAN"] = ( np.mean(hdufocusdata), "Mean Value of Image Array" )
    hduheader["IMGMODE"] = ( imageMode, "Mode Value of Image Array" )
    hduheader["IMGMED"] = ( np.median(hdufocusdata), "Median Value of Image Array" )
    hduheader["IMGMAD"] = ( median_absolute_deviation(hdufocusdata), "Median Absolute Deviation of Image Array" )
    plog ("Basic Image Stats: " +str(time.time()-googtime))

# We don't need to calculate the histogram
# If we aren't keeping the image.
if frame_type=='expose' and False: # The False is here because we don't actually use this yet, but it is working

    googtime=time.time()
    # Collect unique values and counts
    histogramdata=np.column_stack([unique,counts]).astype(np.int32)

    #Do some fiddle faddling to figure out the value that goes to zero less
    zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
    breaker=1
    counter=0
    while (breaker != 0):
        counter=counter+1
        if not (imageMode-counter) in zeroValueArray[:,0]:

            zeroValue=(imageMode-counter)
            breaker =0
    hdufocusdata[hdufocusdata < zeroValue] = imageMode
    histogramdata=histogramdata[histogramdata[:,0] > zeroValue]
    plog ("Histogram: " + str(time.time()-googtime))
    imageinspection_json_snippets['histogram']= re.sub('\s+',' ',str(histogramdata))

try:
    hduheader["SEPSKY"] = sepsky
except:
    hduheader["SEPSKY"] = -9999
try:
    hduheader["FWHM"] = (str(rfp), 'FWHM in pixels')
    hduheader["FWHMpix"] = (str(rfp), 'FWHM in pixels')
except:
    hduheader["FWHM"] = (-99, 'FWHM in pixels')
    hduheader["FWHMpix"] = (-99, 'FWHM in pixels')

try:
    hduheader["FWHMasec"] = (str(rfr), 'FWHM in arcseconds')
except:
    hduheader["FWHMasec"] = (-99, 'FWHM in arcseconds')
try:
    hduheader["FWHMstd"] = (str(rfs), 'FWHM standard deviation in arcseconds')
except:

    hduheader["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')

try:
    hduheader["NSTARS"] = ( len(sources), 'Number of star-like sources in image')
except:
    hduheader["NSTARS"] = ( -99, 'Number of star-like sources in image')


if pixscale == None:
    hduheader['PIXSCALE']='Unknown'
else:
    hduheader['PIXSCALE']=float(pixscale)

# parse header to a json-y type thing
headerdict={}
counter = 0
for line in hduheader:
    counter=counter+1
    try:
        headerdict[line]=str(hduheader[counter])
    except:
        pass

try:
    text = open(
        im_path + text_name.replace('.txt','.temptxt'), "w"
    )
    text.write(str(hduheader))
    text.close()
    os.rename(im_path + text_name.replace('.txt','.temptxt'),im_path + text_name)
except:
    pass

imageinspection_json_snippets['header']=headerdict
starinspection_json_snippets['header']=headerdict

googtime=time.time()
try:
    imageinspection_json_snippets['photometry']=re.sub('\s+',' ',str(photometry))
    plog ("Writing out Photometry: " + str(time.time()-googtime))
except:
    pass

if not frame_type=='focus':
    # Constructing the slices and dices
    try:
        googtime=time.time()
        slice_n_dice={}
        image_size_x, image_size_y = hdufocusdata.shape

        # row slices
        slicerow=int(image_size_x * 0.1)
        slice_n_dice['row10percent']=hdufocusdata[slicerow,:].astype(int)
        slice_n_dice['row20percent']=hdufocusdata[slicerow*2,:].astype(int)
        slice_n_dice['row30percent']=hdufocusdata[slicerow*3,:].astype(int)
        slice_n_dice['row40percent']=hdufocusdata[slicerow*4,:].astype(int)
        slice_n_dice['row50percent']=hdufocusdata[slicerow*5,:].astype(int)
        slice_n_dice['row60percent']=hdufocusdata[slicerow*6,:].astype(int)
        slice_n_dice['row70percent']=hdufocusdata[slicerow*7,:].astype(int)
        slice_n_dice['row80percent']=hdufocusdata[slicerow*8,:].astype(int)
        slice_n_dice['row90percent']=hdufocusdata[slicerow*9,:].astype(int)

        # column slices
        slicecolumn=int(image_size_y * 0.1)
        slice_n_dice['column10percent']=hdufocusdata[:,slicecolumn].astype(int)
        slice_n_dice['column20percent']=hdufocusdata[:,slicecolumn*2].astype(int)
        slice_n_dice['column30percent']=hdufocusdata[:,slicecolumn*3].astype(int)
        slice_n_dice['column40percent']=hdufocusdata[:,slicecolumn*4].astype(int)
        slice_n_dice['column50percent']=hdufocusdata[:,slicecolumn*5].astype(int)
        slice_n_dice['column60percent']=hdufocusdata[:,slicecolumn*6].astype(int)
        slice_n_dice['column70percent']=hdufocusdata[:,slicecolumn*7].astype(int)
        slice_n_dice['column80percent']=hdufocusdata[:,slicecolumn*8].astype(int)
        slice_n_dice['column90percent']=hdufocusdata[:,slicecolumn*9].astype(int)

        # diagonals... not so easy as you might think! Easy for square arrays.
        aspectratio=image_size_x/image_size_y

        #topleft to bottomright
        topleftdiag=[]
        for i in range(image_size_x):
            topleftdiag.append(hdufocusdata[i,int((image_size_y-i-1)*aspectratio)])
        slice_n_dice['topleftdiag']=topleftdiag

        #bottomleft to topright
        bottomleftdiag=[]
        for i in range(image_size_x):
            bottomleftdiag.append(hdufocusdata[i,int(i*aspectratio)])
        slice_n_dice['bottomleftdiag']=bottomleftdiag

        # ten percent box area statistics
        boxshape=(int(0.1*image_size_x),int(0.1*image_size_y))
        boxstats=[]
        for x_box in [0,.1,.2,.3,.4,.5,.6,.7,.8,.9]:
            for y_box in [0,.1,.2,.3,.4,.5,.6,.7,.8,.9]:
                xboxleft=x_box*image_size_x
                xboxright=(x_box+0.1) * image_size_x
                xboxmid=int((xboxleft+xboxright)/2)
                yboxup=y_box*image_size_y
                yboxdown=(y_box+0.1) * image_size_y
                yboxmid=int((yboxup+yboxdown)/2)
                statistic_area=extract_array(hdufocusdata, boxshape, (xboxmid,yboxmid))

                # Background clipped
                imgmin = ( np.min(statistic_area), "Minimum Value of Image Array" )
                imgmax = ( np.max(statistic_area), "Maximum Value of Image Array" )
                imgmean = ( np.mean(statistic_area), "Mean Value of Image Array" )
                imgmed = ( np.median(statistic_area), "Median Value of Image Array" )
                imgstdev = ( np.std(statistic_area), "Median Value of Image Array" )
                imgmad = ( median_absolute_deviation(statistic_area, ignore_nan=True), "Median Absolute Deviation of Image Array" )

                # Get out raw histogram construction data
                # Get a flattened array with all nans removed
                unique,counts=np.unique(statistic_area.ravel()[~np.isnan(statistic_area.ravel())].astype(int), return_counts=True)
                # int_array_flattened=statistic_area.astype(int).ravel()
                # unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
                m=counts.argmax()
                imageMode=unique[m]

                imgmode = ( imageMode, "Mode Value of Image Array" )

                # Collect unique values and counts
                histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                boxstats.append([x_box,y_box,imgmin,imgmax,imgmean,imgmed,imgstdev,imgmad,imgmode,histogramdata])

        slice_n_dice['boxstats']=boxstats

        plog ("Slices and Dices: " + str(time.time()-googtime))
        imageinspection_json_snippets['sliceanddice']=re.sub('\s+',' ',str(slice_n_dice)).replace('dtype=float32','').replace('array','')

    except:
        pass


if not frame_type == 'focus' and False: # The False is here because we don't actually use this yet, but it is working
    googtime=time.time()
    with open(im_path + 'image_' + text_name.replace('.txt', '.json'), 'w') as f:
        json.dump(imageinspection_json_snippets, f)
    plog ("Writing out image inspection: " + str(time.time()-googtime))

    try:
        # Writing out the radial profile snippets
        # This seems to take the longest time, so down here it goes
        googtime=time.time()
        starinspection_json_snippets['radialprofiles']=re.sub('\s+',' ',str(sources))
        plog ("ASCIIing Radial Profiles: " + str(time.time()-googtime))
        googtime=time.time()

    except:
        pass

    with open(im_path + 'star_' + text_name.replace('.txt', '.json'), 'w') as f:
        json.dump(starinspection_json_snippets, f)
    plog ("Writing out star inspection: " + str(time.time()-googtime))
