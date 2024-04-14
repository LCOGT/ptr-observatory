# -*- coding: utf-8 -*-
"""
Created on Sun Apr 23 04:37:30 2023

@author: observatory
"""

import numpy as np
import bottleneck as bn
# Need this line to output the full array to text for the json
np.set_printoptions(threshold=np.inf)

#import pandas as pd

import re
from astropy.stats import median_absolute_deviation
from astropy.nddata.utils import extract_array
import sys
import pickle
import time
#import sep
import traceback
import math
import json
import sep
import copy
# from scipy import ndimage as nd
from auto_stretch.stretch import Stretch
from astropy.io import fits
# from astropy.nddata import block_reduce
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
from PIL import Image, ImageDraw # ImageFont, ImageDraw#, ImageEnhance
#from astropy.table import Table
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)
import matplotlib.pyplot as plt

import math

from scipy.stats import binned_statistic

from scipy import optimize
googtime=time.time()
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

# The SEP code underestimates the moffat FWHM by some factor. This corrects for it.
sep_to_moffat_factor=1.45

input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testSEPpickle','rb'))

#print ("HERE IS THE INCOMING. ")
#print (input_sep_info)

hdufocusdata=input_sep_info[0]
pixscale=input_sep_info[1]
readnoise=input_sep_info[2]
avg_foc=input_sep_info[3]
focus_image=input_sep_info[4]
im_path=input_sep_info[5]
text_name=input_sep_info[6]
hduheader=input_sep_info[7]
cal_path=input_sep_info[8]
cal_name=input_sep_info[9]
frame_type=input_sep_info[10]
focus_position=input_sep_info[11]
gdevevents=input_sep_info[12]
ephemnow=input_sep_info[13]
focus_crop_width = input_sep_info[14]
focus_crop_height = input_sep_info[15]
is_osc= input_sep_info[16]
interpolate_for_focus= input_sep_info[17]
#bin_for_focus= input_sep_info[18]
#focus_bin_value= input_sep_info[19]
#bin_for_focus= False
#focus_bin_value= 1
interpolate_for_sep= input_sep_info[20]
# bin_for_sep= input_sep_info[21]
# sep_bin_value= input_sep_info[22]
#bin_for_sep= False
#sep_bin_value= 1
focus_jpeg_size= input_sep_info[23]
saturate= input_sep_info[24]
minimum_realistic_seeing=input_sep_info[25]
#nativebin=input_sep_info[26]
do_sep=input_sep_info[27]
exposure_time=input_sep_info[28]


# The photometry has a timelimit that is half of the exposure time
time_limit=min (float(hduheader['EXPTIME'])*0.5, 30, exposure_time*0.5)

minimum_exposure_for_extended_stuff = 10

print ("Time Limit: " + str(time_limit))
#breakpoint()

#frame_type='focus'

# https://stackoverflow.com/questions/9111711/get-coordinates-of-local-maxima-in-2d-array-above-certain-value
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


# For a QHY600, it takes a few seconds to calculate the mode. We don't need it for a focus frame.
# If the exposure time is short then just take the median
if not frame_type == 'focus' and float(hduheader['EXPTIME']) >= minimum_exposure_for_extended_stuff :
    googtime=time.time()
    int_array_flattened=hdufocusdata.astype(int).ravel()
    unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
    m=counts.argmax()
    imageMode=unique[m]
    print ("Calculating Mode: " +str(time.time()-googtime))


    # Zerothreshing image
    googtime=time.time()
    histogramdata=np.column_stack([unique,counts]).astype(np.int32)
    #Do some fiddle faddling to figure out the value that goes to zero less
    zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
    breaker=1
    counter=0
    while (breaker != 0):
        counter=counter+1
        if not (imageMode-counter) in zeroValueArray[:,0]:
            if not (imageMode-counter-counter) in zeroValueArray[:,0]:
                if not (imageMode-counter-counter-counter) in zeroValueArray[:,0]:
                    if not (imageMode-counter-counter-counter-counter) in zeroValueArray[:,0]:
                        if not (imageMode-counter-counter-counter-counter-counter) in zeroValueArray[:,0]:
                            zeroValue=(imageMode-counter)
                            breaker =0

    hdufocusdata[hdufocusdata < zeroValue] = np.nan

    print ("Zero Threshing Image: " +str(time.time()-googtime))

    real_mode=True
else:
    imageMode=bn.nanmedian(hdufocusdata)
    real_mode=False



googtime=time.time()
# Check there are no nans in the image upon receipt
# This is necessary as nans aren't interpolated in the main thread.
# Fast next-door-neighbour in-fill algorithm
#num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
x_size=hdufocusdata.shape[0]
y_size=hdufocusdata.shape[1]
# this is actually faster than np.nanmean
edgefillvalue=imageMode
# List the coordinates that are nan in the array
nan_coords=np.argwhere(np.isnan(hdufocusdata))

# For each coordinate try and find a non-nan-neighbour and steal its value
for nancoord in nan_coords:
    x_nancoord=nancoord[0]
    y_nancoord=nancoord[1]
    done=False

    # Because edge pixels can tend to form in big clumps
    # Masking the array just with the mean at the edges
    # makes this MUCH faster to no visible effect for humans.
    # Also removes overscan
    if x_nancoord < 100:
        hdufocusdata[x_nancoord,y_nancoord]=edgefillvalue
        done=True
    elif x_nancoord > (x_size-100):
        hdufocusdata[x_nancoord,y_nancoord]=edgefillvalue

        done=True
    elif y_nancoord < 100:
        hdufocusdata[x_nancoord,y_nancoord]=edgefillvalue

        done=True
    elif y_nancoord > (y_size-100):
        hdufocusdata[x_nancoord,y_nancoord]=edgefillvalue
        done=True

    # left
    if not done:
        if x_nancoord != 0:
            value_here=hdufocusdata[x_nancoord-1,y_nancoord]
            if not np.isnan(value_here):
                hdufocusdata[x_nancoord,y_nancoord]=value_here
                done=True
    # right
    if not done:
        if x_nancoord != (x_size-1):
            value_here=hdufocusdata[x_nancoord+1,y_nancoord]
            if not np.isnan(value_here):
                hdufocusdata[x_nancoord,y_nancoord]=value_here
                done=True
    # below
    if not done:
        if y_nancoord != 0:
            value_here=hdufocusdata[x_nancoord,y_nancoord-1]
            if not np.isnan(value_here):
                hdufocusdata[x_nancoord,y_nancoord]=value_here
                done=True
    # above
    if not done:
        if y_nancoord != (y_size-1):
            value_here=hdufocusdata[x_nancoord,y_nancoord+1]
            if not np.isnan(value_here):
                hdufocusdata[x_nancoord,y_nancoord]=value_here
                done=True

# Mop up any remaining nans
hdufocusdata[np.isnan(hdufocusdata)] =edgefillvalue

print ("De-nanning image initially: " +str(time.time()-googtime))



# no zero values in readnoise.
if float(readnoise) < 0.1:
    readnoise = 0.1





if not do_sep or (float(hduheader["EXPTIME"]) < 1.0):
    rfp = np.nan
    rfr = np.nan
    rfs = np.nan
    sepsky = np.nan
    pickle.dump([], open(im_path + text_name.replace('.txt', '.sep'),'wb'))

else:

    # # Realistically we can figure out the focus stuff here from first principles.
    # if frame_type == 'focus':
    #     fx, fy = hdufocusdata.shape
    #     # We want a standard focus image size that represent 0.2 degrees - which is the size of the focus fields.
    #     # However we want some flexibility in the sense that the pointing could be off by half a degree or so...
    #     # So we chop the image down to a degree by a degree
    #     # This speeds up the focus software.... we don't need to solve for EVERY star in a widefield image.
    #     fx_degrees = (fx * pixscale) /3600
    #     fy_degrees = (fy * pixscale) /3600

    #     crop_x=0
    #     crop_y=0


    #     if fx_degrees > 1.0:
    #         ratio_crop= 1/fx_degrees
    #         crop_x = int((fx - (ratio_crop * fx))/2)
    #     if fy_degrees > 1.0:
    #         ratio_crop= 1/fy_degrees
    #         crop_y = int((fy - (ratio_crop * fy))/2)

    #     if crop_x > 0 or crop_y > 0:
    #         if crop_x == 0:
    #             crop_x = 2
    #         if crop_y == 0:
    #             crop_y = 2
    #         # Make sure it is an even number for OSCs
    #         if (crop_x % 2) != 0:
    #             crop_x = crop_x+1
    #         if (crop_y % 2) != 0:
    #             crop_y = crop_y+1
    #         hdufocusdata = hdufocusdata[crop_x:-crop_x, crop_y:-crop_y]

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
        #bilinearfill=np.mean( [ np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1)], axis=0 )
        #bilinearfill=np.divide(np.add( np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1),4))#, axis=0 )

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

        if real_mode:
            bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
            bkg.subfrom(hdufocusdata)
        else:
            hdufocusdata=hdufocusdata-imageMode

        # hdufocus = fits.PrimaryHDU()
        # hdufocus.data = hdufocusdata
        # hdufocus.header = hduheader
        # hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
        # hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
        # hdufocus.writeto('goop.fits', overwrite=True, output_verify='silentfix')



        #if frame_type == 'focus':       # This hasn't been calculated yet for focus, but already has for a normal image.
        tempstd=np.std(hdufocusdata)
        #hduheader["IMGSTDEV"]=tempstd
        hduheader["IMGSTDEV"] = ( tempstd, "Median Value of Image Array" )
        # else:
        #     tempstd=float(hduheader["IMGSTDEV"])
        threshold=max(3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)]),(200*pixscale)) # Don't bother with stars with peaks smaller than 100 counts per arcsecond
        googtime=time.time()
        list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
        print ("Finding Local Maxima: " + str(time.time()-googtime))

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
                    print(traceback.format_exc())
                    breakpoint()

                # Check it isn't just a dot
                if value_at_neighbours < (0.4*value_at_point):
                    #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
                    pointvalues[counter][2]=np.nan

                # If not saturated and far away from the edge
                elif value_at_point < 0.8*saturate:
                    pointvalues[counter][2]=value_at_point

                else:
                    pointvalues[counter][2]=np.nan

            counter=counter+1

        print ("Sorting out bad pixels from the mix: " + str(time.time()-googtime))


        # Trim list to remove things that have too many other things close to them.

        googtime=time.time()
        # remove nan rows
        pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

        # reverse sort by brightness
        pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]

        #From...... NOW
        timer_for_bailing=time.time()

        #breakpoint()


        # radial profile
        fwhmlist=[]
        sources=[]
        photometry=[]
        #radius_of_radialprofile=(30)
        # The radius should be related to arcseconds on sky
        # And a reasonable amount - 12'
        radius_of_radialprofile=int(12/pixscale)
        # Round up to nearest odd number to make a symmetrical array
        radius_of_radialprofile=int(radius_of_radialprofile // 2 *2 +1)
        halfradius_of_radialprofile=math.ceil(0.5*radius_of_radialprofile)
        centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        googtime=time.time()

        # if frame_type == 'focus': # Only bother with the first couple of hundred at most for focus
        #     amount=min(len(pointvalues),50)
        # else:
            #amount=min(len(pointvalues),800)

        number_of_good_radials_to_get = 50




        #print (amount)

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
        pixel_testvalues=np.array(testvalues) / pixscale


        for i in range(len(pointvalues)):

            # Don't take too long!
            if ((time.time() - timer_for_bailing) > time_limit) and good_radials > 20:
                print ("Time limit reached! Bailout!")
                break

            cx= int(pointvalues[i][0])
            cy= int(pointvalues[i][1])
            cvalue=hdufocusdata[int(cx)][int(cy)]
            try:
                #temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
                temp_array=hdufocusdata[cx-halfradius_of_radialprofile:cx+halfradius_of_radialprofile,cy-halfradius_of_radialprofile:cy+halfradius_of_radialprofile]
                #breakpoint()
                #temp_numpy=hdufocusdata[cx-radius_of_radialprofile:cx+radius_of_radialprofile,cy-radius_of_radialprofile:cy+radius_of_radialprofile]
            except:
                print(traceback.format_exc())
                breakpoint()
            #crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])

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
                    #breakpoint()
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
            if abs(brightest_pixel_rdist) < max(3, 3/pixscale):

                try:






                    # Reduce data down to make faster solvinging
                    upperbin=math.floor(max(radprofile[:,0]))
                    lowerbin=math.ceil(min(radprofile[:,0]))
                    #number_of_bins=int((upperbin-lowerbin)/0.25)
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

                        #popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1])
                        #popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1], p0=[cvalue,0,((2/pixscale) /2.355)], bounds=([cvalue/2,-10, 0],[cvalue*1.2,10,10]))#, xtol=0.005, ftol=0.005)

                        #print (popt)


                        # Different faster fitter to consider
                        peak_value_index=np.argmax(actualprofile[:,1])
                        peak_value=actualprofile[peak_value_index][1]
                        x_axis_of_peak_value=actualprofile[peak_value_index][0]

                        # middle_distribution= actualprofile[actualprofile[:,0] < 5]
                        # middle_distribution= middle_distribution[middle_distribution[:,0] > -5]

                        # Get the mean of the 5 pixels around the max
                        # and use the mean of those values and the peak value
                        # to use as the amplitude
                        temp_amplitude=actualprofile[peak_value_index-2][1]+actualprofile[peak_value_index-1][1]+actualprofile[peak_value_index][1]+actualprofile[peak_value_index+1][1]+actualprofile[peak_value_index+2][1]
                        temp_amplitude=temp_amplitude/5
                        # Check that the mean of the temp_amplitude here is at least 0.6 * cvalue
                        if temp_amplitude > 0.5*peak_value:

                            # DELETE THIS ONLY FOR TESTING
                            #temp_amplitude=peak_value

                            # Get the center of mass peak value
                            sum_of_positions_times_values=0
                            sum_of_values=0
                            number_of_positions_to_test=7 # odd value
                            poswidth=int(number_of_positions_to_test/2)

                            for spotty in range(number_of_positions_to_test):
                                sum_of_positions_times_values=sum_of_positions_times_values+(actualprofile[peak_value_index-poswidth+spotty][1]*actualprofile[peak_value_index-poswidth+spotty][0])
                                sum_of_values=sum_of_values+actualprofile[peak_value_index-poswidth+spotty][1]
                            peak_position=(sum_of_positions_times_values / sum_of_values)
                            # width checker
                            #print (2.355 * popt[2])
                            #print (0.8 / pixscale)
                            #breakpoint()
                            # Get a handwavey distance to the HWHM
                            # Whats the nearest point?
                            # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                            # plt.show()
                            # print (peak_position)
                            # print (actualprofile[peak_value_index][0])
                            #breakpoint()
                            temppos=abs(actualprofile[:,0] - peak_position).argmin()
                            # print (actualprofile[temppos,0])
                            #temppos=peak_value_index
                            tempvalue=actualprofile[temppos,1]
                            temppeakvalue=copy.deepcopy(tempvalue)
                            # Get lefthand quarter percentiles
                            #threequartertemp=actualprofile[temppos,1]

                            counter=1
                            while tempvalue > 0.25*temppeakvalue:

                                tempvalue=actualprofile[temppos-counter,1]
                                if tempvalue > 0.75:
                                    threequartertemp=temppos-counter
                                #print (tempvalue)
                                counter=counter+1

                            lefthand_quarter_spot=actualprofile[temppos-counter][0]
                            lefthand_threequarter_spot=actualprofile[threequartertemp][0]

                            # Get righthand quarter percentile
                            counter=1
                            while tempvalue > 0.25*temppeakvalue:
                                tempvalue=actualprofile[temppos+counter,1]
                                #print (tempvalue)
                                if tempvalue > 0.75:
                                    threequartertemp=temppos+counter
                                counter=counter+1

                            righthand_quarter_spot=actualprofile[temppos+counter][0]
                            righthand_threequarter_spot=actualprofile[threequartertemp][0]

                            largest_reasonable_position_deviation_in_pixels=1.25*max(abs(peak_position - righthand_quarter_spot),abs(peak_position - lefthand_quarter_spot))
                            largest_reasonable_position_deviation_in_arcseconds=largest_reasonable_position_deviation_in_pixels *pixscale

                            smallest_reasonable_position_deviation_in_pixels=0.7*min(abs(peak_position - righthand_threequarter_spot),abs(peak_position - lefthand_threequarter_spot))
                            smallest_reasonable_position_deviation_in_arcseconds=smallest_reasonable_position_deviation_in_pixels *pixscale

                            #breakpoint()

                            #print ("************************")
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

                                #breakpoint()

                                smallest_value=999999999999999.9
                                #smallest_index=0
                                for pixeltestvalue in pixel_testvalues:

                                    # googtime=time.time()
                                    #if pixeltestvalue*pixscale < largest_reasonable_position_deviation_in_arcseconds and pixeltestvalue*pixscale > smallest_reasonable_position_deviation_in_arcseconds:
                                    #est_fpopt= [peak_value, peak_position, pixeltestvalue]
                                    test_fpopt= [peak_value, peak_position, pixeltestvalue]

                                    #print (test_fpopt)

                                    # differences between gaussian and data
                                    difference=(np.sum(abs(actualprofile[:,1] - gaussian(actualprofile[:,0], *test_fpopt))))
                                    #print (difference)

                                    if difference < smallest_value:
                                        smallest_value=copy.deepcopy(difference)
                                        smallest_fpopt=copy.deepcopy(test_fpopt)

                                    if difference < 1.25 * smallest_value:
                                        # print (time.time()-googtime)
                                        # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                                        # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *test_fpopt),color = 'r')
                                        # # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                                        # plt.show()
                                        pass
                                    else:
                                        #print ("gone through and sampled range enough")
                                        break

                                # slow scipy way
                                #popt, _ = optimize.curve_fit(gaussian, actualprofile[:,0], actualprofile[:,1], p0=[cvalue,0,((2/pixscale) /2.355)], bounds=([cvalue/2,-10, 0],[cvalue*1.2,10,10]))#, xtol=0.005, ftol=0.005)



                                #fpopt=[temp_amplitude, peak_position, 0.2]


                                # Amplitude has to be a substantial fraction of the peak value
                                # and the center of the gaussian needs to be near the center
                                # and the FWHM has to be above 0.8 arcseconds.
                                #if popt[0] > (0.5 * cvalue) and abs(popt[1]) < max(3, 3/pixscale):# and (2.355 * popt[2]) > (0.8 / pixscale) :

                                # if it isn't a unreasonably small fwhm then measure it.
                                if (2.355 * smallest_fpopt[2]) > (0.8 / pixscale) :

                                    # print ("amplitude: " + str(popt[0]) + " center " + str(popt[1]) + " stdev? " +str(popt[2]))
                                    # print ("Brightest pixel at : " + str(brightest_pixel_rdist))
                                    # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                                    # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *smallest_fpopt),color = 'r')

                                    # #plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *popt),color = 'g')
                                    # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                                    # plt.show()
                                    #breakpoint()

                                    # FWHM is 2.355 * std for a gaussian
                                    fwhmlist.append(smallest_fpopt[2])
                                    # Area under a 1D gaussian is (amplitude * Stdev / 0.3989)

                                    # Volume under the 2D-Gaussian is computed as: 2 * pi * sqrt(abs(X_sig)) * sqrt(abs(Y_sig)) * amplitude
                                    # But our sigma in both dimensions are the same so sqrt times sqrt of something is equal to the something
                                    countsphot= 2 * math.pi * smallest_fpopt[2] * smallest_fpopt[0]


                                    #breakpoint()
                                    if good_radials < number_of_good_radials_to_get:
                                        #sources.append([cx,cy,radprofile,temp_array,cvalue, popt[0]*popt[2]/0.3989,popt[0],popt[1],popt[2],'r'])
                                        sources.append([cx,cy,radprofile,temp_array,cvalue, countsphot,smallest_fpopt[0],smallest_fpopt[1],smallest_fpopt[2],'r'])

                                        good_radials=good_radials+1
                                    else:
                                        sources.append([cx,cy,0,0,cvalue, countsphot,smallest_fpopt[0],smallest_fpopt[1],smallest_fpopt[2],'n'])
                                    photometry.append([cx,cy,cvalue,smallest_fpopt[0],smallest_fpopt[2]*4.710,countsphot])

                                    #breakpoint()
                                    # If we've got more than 50 for a focus
                                    # We only need some good ones.
                                    # if frame_type == 'focus':
                                    #     if len(fwhmlist) > 50:
                                    #         bailout=True
                                    #         break
                                    #     #If we've got more than ten and we are getting dim, bail out.
                                    #     if len(fwhmlist) > 10 and brightest_pixel_value < (0.2*saturate):
                                    #         bailout=True
                                    #         break
                except:
                    pass

        print ("Extracting and Gaussianingx: " + str(time.time()-googtime))
        print ("N of sources processed: " + str(len(sources)))
        #breakpoint()


        rfp = abs(bn.nanmedian(fwhmlist)) * 4.710
        rfr = rfp * pixscale
        rfs = bn.nanstd(fwhmlist) * pixscale
        if rfr < 1.0 or rfr > 6:
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
        with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
            json.dump(fwhm_file, f)

        # This pickled sep file is for internal use - usually used by the smartstack thread to align mono smartstacks.
        pickle.dump(photometry, open(im_path + text_name.replace('.txt', '.sep'),'wb'))


        # Grab the central arcminute out of the image.
        cx = int(fx/2)
        cy = int(fy/2)
        width = math.ceil(30 / pixscale)
        central_half_arcminute=copy.deepcopy(hdufocusdata[cx-width:cx+width,cy-width:cy+width])
        imageinspection_json_snippets['central_patch']= re.sub('\s+',' ',str(central_half_arcminute))



        #print (im_path + text_name.replace('.txt', '.sep'))


        #sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)

            # dump the settings files into the temp directory
            # with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
            #     json.dump(fwhm_file, f)

            #breakpoint()

            # for i in range(len(sources)):
            #     plt.imshow(sources[i][3])
            #     plt.show()
            #     time.sleep(0.05)


        # except:
        #     traceback.format_exc()
        #     sources = [0]
        #     rfp = np.nan
        #     rfr = np.nan
        #     rfs = np.nan
        #     sepsky = np.nan



        #breakpoint()






    # else:

    #     actseptime = time.time()
    #     focusimg = np.array(
    #         hdufocusdata, order="C"
    #     )

    #     try:
    #         # Some of these are liberated from BANZAI



    #         bkg = sep.Background(focusimg, bw=32, bh=32, fw=3, fh=3)
    #         bkg.subfrom(focusimg)

    #         sepsky = (bn.nanmedian(bkg), "Sky background estimated by SEP")

    #         ix, iy = focusimg.shape
    #         border_x = int(ix * 0.05)
    #         border_y = int(iy * 0.05)
    #         sep.set_extract_pixstack(int(ix*iy - 1))

    #         #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
    #         # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
    #         # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
    #         minarea= (-9.2421 * pixscale) + 16.553
    #         if minarea < 5:  # There has to be a min minarea though!
    #             minarea = 5

    #         sources = sep.extract(
    #             focusimg, 3.0, err=bkg.globalrms, minarea=minarea
    #         )
    #         sources = Table(sources)


    #         sources = sources[sources['flag'] < 8]
    #         image_saturation_level = saturate
    #         sources = sources[sources["peak"] < 0.8 * image_saturation_level]
    #         sources = sources[sources["cpeak"] < 0.8 * image_saturation_level]
    #         sources = sources[sources["flux"] > 1000]
    #         #sources = sources[sources["x"] < iy - border_y]
    #         #sources = sources[sources["x"] > border_y]
    #         #sources = sources[sources["y"] < ix - border_x]
    #         #sources = sources[sources["y"] > border_x]
    #         #breakpoint()
    #         # BANZAI prune nans from table





    #         nan_in_row = np.zeros(len(sources), dtype=bool)
    #         for col in sources.colnames:
    #             nan_in_row |= np.isnan(sources[col])
    #         sources = sources[~nan_in_row]

    #         #breakpoint()

    #         # Calculate the ellipticity (Thanks BANZAI)

    #         sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])

    #         # if frame_type == 'focus':
    #         #     sources = sources[sources['ellipticity'] < 0.4]  # Remove things that are not circular stars
    #         # else:
    #         #breakpoint()
    #         sources = sources[sources['ellipticity'] < 0.6]  # Remove things that are not circular stars

    #         # Calculate the kron radius (Thanks BANZAI)
    #         kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
    #                                           sources['a'], sources['b'],
    #                                           sources['theta'], 6.0)
    #         sources['flag'] |= krflag
    #         sources['kronrad'] = kronrad

    #         # Calculate uncertainty of image (thanks BANZAI)

    #         uncertainty = float(readnoise) * np.ones(focusimg.shape,
    #                                                  dtype=focusimg.dtype) / float(readnoise)


    #         # DONUT IMAGE DETECTOR.
    #         xdonut=np.median(pow(pow(sources['x'] - sources['xpeak'],2),0.5))*pixscale
    #         ydonut=np.median(pow(pow(sources['y'] - sources['ypeak'],2),0.5))*pixscale

    #         # Calcuate the equivilent of flux_auto (Thanks BANZAI)
    #         # This is the preferred best photometry SEP can do.
    #         # But sometimes it fails, so we try and except
    #         # try:
    #         #     flux, fluxerr, flag = sep.sum_ellipse(focusimg, sources['x'], sources['y'],
    #         #                                       sources['a'], sources['b'],
    #         #                                       np.pi / 2.0, 2.5 * kronrad,
    #         #                                       subpix=1, err=uncertainty)
    #         #     sources['flux'] = flux
    #         #     sources['fluxerr'] = fluxerr
    #         #     sources['flag'] |= flag
    #         # except:
    #         #     pass



    #         sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
    #                                               subpix=5)

    #         #breakpoint()
    #         # If image has been binned for focus we need to multiply some of these things by the binning
    #         # To represent the original image
    #         sources['FWHM'] = (sources['FWHM'] * 2)

    #         #sources['FWHM']=sources['kronrad'] * 2

    #         #print (sources)

    #         # Need to reject any stars that have FWHM that are less than a extremely
    #         # perfect night as artifacts
    #         # if frame_type == 'focus':
    #         #     sources = sources[sources['FWHM'] > (0.6 / (pixscale))]
    #         #     sources = sources[sources['FWHM'] > (minimum_realistic_seeing / pixscale)]
    #         #     sources = sources[sources['FWHM'] != 0]

    #         source_delete = ['thresh', 'npix', 'tnpix', 'xmin', 'xmax', 'ymin', 'ymax', 'x2', 'y2', 'xy', 'errx2',
    #                          'erry2', 'errxy', 'a', 'b', 'theta', 'cxx', 'cyy', 'cxy', 'cflux', 'cpeak', 'xcpeak', 'ycpeak']

    #         sources.remove_columns(source_delete)



    #         # BANZAI prune nans from table
    #         nan_in_row = np.zeros(len(sources), dtype=bool)
    #         for col in sources.colnames:
    #             nan_in_row |= np.isnan(sources[col])
    #         sources = sources[~nan_in_row]



    #         sources = sources[sources['FWHM'] != 0]
    #         #sources = sources[sources['FWHM'] > 0.6]
    #         sources = sources[sources['FWHM'] > (1/pixscale)]

    #         #breakpoint()

    #         sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)

    #         if (len(sources) < 2) or ( frame_type == 'focus' and (len(sources) < 10 or len(sources) == np.nan or str(len(sources)) =='nan' or xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut))):
    #             sources['FWHM'] = [np.nan] * len(sources)
    #             rfp = np.nan
    #             rfr = np.nan
    #             rfs = np.nan
    #             sources = sources

    #         else:
    #             # Get halflight radii

    #             fwhmcalc = sources['FWHM']
    #             fwhmcalc = fwhmcalc[fwhmcalc != 0]

    #             # sigma clipping iterator to reject large variations
    #             templen = len(fwhmcalc)
    #             while True:
    #                 fwhmcalc = fwhmcalc[fwhmcalc < np.median(fwhmcalc) + 3 * np.std(fwhmcalc)]
    #                 if len(fwhmcalc) == templen:
    #                     break
    #                 else:
    #                     templen = len(fwhmcalc)

    #             fwhmcalc = fwhmcalc[fwhmcalc > np.median(fwhmcalc) - 3 * np.std(fwhmcalc)]
    #             rfp = round(np.median(fwhmcalc), 3) * sep_to_moffat_factor
    # #            rfr = round(np.median(fwhmcalc) * pixscale * nativebin, 3)
    # #            rfs = round(np.std(fwhmcalc) * pixscale * nativebin, 3)
    #             rfr = round(np.median(fwhmcalc) * pixscale, 3) * sep_to_moffat_factor
    #             rfs = round(np.std(fwhmcalc) * pixscale, 3) * sep_to_moffat_factor


    #             #print (sources)
    #             #breakpoint()

    #         fwhm_file={}
    #         fwhm_file['rfp']=str(rfp)
    #         fwhm_file['rfr']=str(rfr)
    #         fwhm_file['rfs']=str(rfs)
    #         fwhm_file['sky']=str(sepsky)
    #         fwhm_file['sources']=str(len(sources))
    #         # dump the settings files into the temp directory
    #         # with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
    #         #     json.dump(fwhm_file, f)




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
        with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
            json.dump(fwhm_file, f)

        #json_snippets['fwhm']=fwhm_file
        imageinspection_json_snippets['fwhm']=fwhm_file
        starinspection_json_snippets['fwhm']=fwhm_file


        pickle.dump([], open(im_path + text_name.replace('.txt', '.sep'),'wb'))
# Value-added header items for the UI
#breakpoint()

# Save out the "sep" file
#breakpoint()

#with



# These broad image statistics also take a few seconds on a QHY600 image
# But are not needed for a focus image.
if not frame_type == 'focus':
    googtime=time.time()
    hduheader["IMGMIN"] = ( np.min(hdufocusdata), "Minimum Value of Image Array" )
    hduheader["IMGMAX"] = ( np.max(hdufocusdata), "Maximum Value of Image Array" )
    hduheader["IMGMEAN"] = ( np.mean(hdufocusdata), "Mean Value of Image Array" )
    hduheader["IMGMODE"] = ( imageMode, "Mode Value of Image Array" )
    hduheader["IMGMED"] = ( np.median(hdufocusdata), "Median Value of Image Array" )



    hduheader["IMGMAD"] = ( median_absolute_deviation(hdufocusdata), "Median Absolute Deviation of Image Array" )
    print ("Basic Image Stats: " +str(time.time()-googtime))


# We don't need to calculate the histogram
# If we aren't keeping the image.
if frame_type=='expose':

    googtime=time.time()


    #breakpoint()
    if float(hduheader['EXPTIME']) <= minimum_exposure_for_extended_stuff :
        int_array_flattened=hdufocusdata.astype(int).ravel()
        unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)

    #breakpoint()
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


    print ("Histogram: " + str(time.time()-googtime))

    imageinspection_json_snippets['histogram']= re.sub('\s+',' ',str(histogramdata))




try:
    #hduheader["SEPSKY"] = str(sepsky)
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


if input_sep_info[1] == None:
    hduheader['PIXSCALE']='Unknown'
else:
    hduheader['PIXSCALE']=float(input_sep_info[1])


# parse header to a json-y type thing
headerdict={}
counter = 0
for line in hduheader:
    #print (line)
    #print (hduheader[counter])
    counter=counter+1
    try:
        headerdict[line]=str(hduheader[counter])
    except:
        pass

#breakpoint()
try:
    text = open(
        im_path + text_name, "w"
    )
    text.write(str(hduheader))
    text.close()
except:
    pass

#googtime=time.time()
imageinspection_json_snippets['header']=headerdict
#print ("Writing out image inspection: " + str(time.time()-googtime))
#googtime=time.time()
starinspection_json_snippets['header']=headerdict
#print ("Writing out star inspection: " + str(time.time()-googtime))
#json_snippets['header']=headerdict
#breakpoint()
# # Create radial profiles for UI
# # Determine radial profiles of top 20 star-ish sources
# if do_sep and (not frame_type=='focus'):
#     try:
#         # Get rid of non-stars
#         sources=sources[sources['FWHM'] < rfr + 2 * rfs]

#         # Reverse sort sources on flux
#         sources.sort('flux')
#         sources.reverse()

#         # radtime=time.time()
#         # dodgylist=[]
#         # radius_of_radialprofile=(5*math.ceil(rfp))
#         # # Round up to nearest odd number to make a symmetrical array
#         # radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
#         # centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
#         # for i in range(min(len(sources),200)):
#         #     cx= (sources[i]['x'])
#         #     cy= (sources[i]['y'])
#         #     temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cy,cx))
#         #     crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])
#         #     dodgylist.append([cx,cy,crad,temp_array])




#         # radial profile
#         fwhmlist=[]
#         radials=[]
#         #radius_of_radialprofile=(30)
#         radius_of_radialprofile=(5*math.ceil(rfp))
#         # Round up to nearest odd number to make a symmetrical array
#         radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
#         centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
#         # for i in range(min(len(pointvalues),200)):
#         #     cx= (pointvalues[i][0])
#         #     cy= (pointvalues[i][1])
#         #     cvalue=hdufocusdata[int(cx)][int(cy)]
#         for i in range(min(len(sources),200)):
#             cx= (sources[i]['y'])
#             cy= (sources[i]['x'])
#             cvalue=(sources[i]['peak'])
#             try:
#                 temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
#             except:
#                 print(traceback.format_exc())
#                 #breakpoint()
#             #crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])

#             #construct radial profile
#             cut_x,cut_y=temp_array.shape
#             cut_x_center=(cut_x/2)-1
#             cut_y_center=(cut_y/2)-1
#             radprofile=np.zeros([cut_x*cut_y,2],dtype=float)
#             counter=0
#             brightest_pixel_rdist=0
#             brightest_pixel_value=0
#             bailout=False
#             for q in range(cut_x):
#                 # if bailout==True:
#                 #     break
#                 for t in range(cut_y):
#                     #breakpoint()
#                     r_dist=pow(pow((q-cut_x_center),2) + pow((t-cut_y_center),2),0.5)
#                     if q-cut_x_center < 0:# or t-cut_y_center < 0:
#                         r_dist=r_dist*-1
#                     radprofile[counter][0]=r_dist
#                     radprofile[counter][1]=temp_array[q][t]
#                     if temp_array[q][t] > brightest_pixel_value:
#                         brightest_pixel_rdist=r_dist
#                         brightest_pixel_value=temp_array[q][t]
#                     counter=counter+1




#             # If the brightest pixel is in the center-ish
#             # then attempt a fit
#             if abs(brightest_pixel_rdist) < 4:

#                 try:
#                     popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1])

#                     # Amplitude has to be a substantial fraction of the peak value
#                     # and the center of the gaussian needs to be near the center
#                     if popt[0] > (0.5 * cvalue) and abs(popt[1]) < 3 :
#                         # print ("amplitude: " + str(popt[0]) + " center " + str(popt[1]) + " stdev? " +str(popt[2]))
#                         # print ("Brightest pixel at : " + str(brightest_pixel_rdist))
#                         # plt.scatter(radprofile[:,0],radprofile[:,1])
#                         # plt.plot(radprofile[:,0], gaussian(radprofile[:,0], *popt),color = 'r')
#                         # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
#                         # plt.show()

#                         # FWHM is 2.355 * std for a gaussian
#                         #fwhmlist.append(popt[2])
#                         radials.append([cx,cy,radprofile,temp_array,popt])
#                         # If we've got more than 50, good
#                         # if len(fwhmlist) > 50:
#                         #     bailout=True
#                         #     break
#                         # #If we've got more than ten and we are getting dim, bail out.
#                         # if len(fwhmlist) > 10 and brightest_pixel_value < (0.2*saturate):
#                         #     bailout=True
#                         #     break
#                 except:
#                     pass


        # pickle.dump(radials, open(im_path + text_name.replace('.txt', '.rad'),'wb'))
        #json_snippets['radialprofiles']=str(radials)
        #imageinspection_json_snippets['header']=headerdict

        #print (radials)
        #breakpoint()
googtime=time.time()
try:
    imageinspection_json_snippets['photometry']=re.sub('\s+',' ',str(photometry))
    #starinspection_json_snippets['photometry']=re.sub('\s+',' ',str(sources))
    print ("Writing out Photometry: " + str(time.time()-googtime))
except:
    pass
    # except:
    #     pass
if do_sep and (not frame_type=='focus'):

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
                int_array_flattened=statistic_area.astype(int).ravel()
                unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
                m=counts.argmax()
                imageMode=unique[m]

                imgmode = ( imageMode, "Mode Value of Image Array" )

                # Collect unique values and counts
                histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                boxstats.append([x_box,y_box,imgmin,imgmax,imgmean,imgmed,imgstdev,imgmad,imgmode,histogramdata])

        slice_n_dice['boxstats']=boxstats

        # pickle.dump(slice_n_dice, open(im_path + text_name.replace('.txt', '.box'),'wb'))
        print ("Slices and Dices: " + str(time.time()-googtime))
        #json_snippets['sliceanddice']=str(slice_n_dice)
        imageinspection_json_snippets['sliceanddice']=re.sub('\s+',' ',str(slice_n_dice)).replace('dtype=float32','').replace('array','')
        #starinspection_json_snippets['radialprofiles']=str(radials)
    except:
        pass


if not frame_type == 'focus':
    #breakpoint()
    googtime=time.time()
    with open(im_path + 'image_' + text_name.replace('.txt', '.json'), 'w') as f:
        json.dump(imageinspection_json_snippets, f)
    print ("Writing out image inspection: " + str(time.time()-googtime))

    try:
        # Writing out the radial profile snippets
        # This seems to take the longest time, so down here it goes
        googtime=time.time()
        starinspection_json_snippets['radialprofiles']=re.sub('\s+',' ',str(sources))
        print ("ASCIIing Radial Profiles: " + str(time.time()-googtime))
        googtime=time.time()

    except:
        pass

    with open(im_path + 'star_' + text_name.replace('.txt', '.json'), 'w') as f:
        json.dump(starinspection_json_snippets, f)
    print ("Writing out star inspection: " + str(time.time()-googtime))



# If it is a focus image then it will get sent in a different manner to the UI for a jpeg
# In this case, the image needs to be the 0.2 degree field that the focus field is made up of

if frame_type == 'focus':
    hdusmalldata = np.array(hdufocusdata)
    fx, fy = hdusmalldata.shape
    aspect_ratio= fx/fy

    focus_jpeg_size=0.2/(pixscale/3600)

    if focus_jpeg_size < fx:
        crop_width = (fx - focus_jpeg_size) / 2
    else:
        crop_width =2

    if focus_jpeg_size < fy:
        crop_height = (fy - (focus_jpeg_size / aspect_ratio) ) / 2
    else:
        crop_height = 2

    # Make sure it is an even number for OSCs
    if (crop_width % 2) != 0:
        crop_width = crop_width+1
    if (crop_height % 2) != 0:
        crop_height = crop_height+1

    crop_width = int(crop_width)
    crop_height = int(crop_height)

    if crop_width > 0 or crop_height > 0:
        hdusmalldata = hdusmalldata[crop_width:-crop_width, crop_height:-crop_height]

    hdusmalldata = hdusmalldata - np.min(hdusmalldata)

    stretched_data_float = Stretch().stretch(hdusmalldata+1000)
    stretched_256 = 255 * stretched_data_float
    hot = np.where(stretched_256 > 255)
    cold = np.where(stretched_256 < 0)
    stretched_256[hot] = 255
    stretched_256[cold] = 0
    stretched_data_uint8 = stretched_256.astype("uint8")
    hot = np.where(stretched_data_uint8 > 255)
    cold = np.where(stretched_data_uint8 < 0)
    stretched_data_uint8[hot] = 255
    stretched_data_uint8[cold] = 0

    iy, ix = stretched_data_uint8.shape
    final_image = Image.fromarray(stretched_data_uint8)
    draw = ImageDraw.Draw(final_image)

    draw.text((0, 0), str(focus_position), (255))
    try:
        final_image.save(im_path + text_name.replace('EX00.txt', 'EX10.jpg'))
    except:
        pass

    del hdusmalldata
    del stretched_data_float
    del final_image





#print (time.time()-googtime)

#breakpoint()