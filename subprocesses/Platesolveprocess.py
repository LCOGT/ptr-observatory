# -*- coding: utf-8 -*-
"""
This is the main platesolve sub-process for solving frames.

Platesolving is relatively costly in time, so we don't solve each frame.
It is also not necessary - the platesolve we do is FAST (for windows)
but only spits out RA, Dec, Pixelscale and rotation. Which is actually all
we need to monitor pointing and keep scopes dead on target.

There is a windswept and interesting way that platesolve frames lead to
slight nudges during observing, but they are all triggered from values
from this subprocess... which actually sub-sub-processes the platesolve3 platesolver from planewave.

However, we have no control over the photometry within platesolve3, hence
part of the subprocess is to create a 'bullseye' image that is constructed
from our own SEP source process to present to the platesove3 so that whatever
photometric algorithm they are using they can't fail to accurately measure positions.
(The insinuation is that they have previously failed to measure accurate postions,
 this is true... there have been some crazy alarming false positives prior to the bullseye method.
 The bullseye method also works better in cloudy patchy conditions as well.)

"""

import sys
import pickle
from astropy.nddata import block_reduce
import numpy as np
import sep
#from astropy.table import Table
from astropy.nddata.utils import extract_array
from astropy.io import fits
from subprocess import Popen, PIPE
import os
from pathlib import Path
from os import getcwd
import time
from astropy.utils.exceptions import AstropyUserWarning
import warnings
# import requests
# from requests import ConnectionError, HTTPError
import traceback
import bottleneck as bn
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
import matplotlib.pyplot as plt
import math

from scipy.stats import binned_statistic

warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)


from scipy import optimize
googtime=time.time()
def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev)**2)

def parse_platesolve_output(output_file):
    f = open(output_file)

    results = {}

    for line in f.readlines():
        line = line.strip()
        if line == "":
            continue

        fields = line.split("=")
        if len(fields) != 2:
            continue

        keyword, value = fields

        results[keyword] = float(value)

    return results


input_psolve_info=pickle.load(sys.stdin.buffer)
#input_psolve_info=pickle.load(open('testplatesolvepickle','rb'))



hdufocusdata=input_psolve_info[0]
hduheader=input_psolve_info[1]
cal_path=input_psolve_info[2]
cal_name=input_psolve_info[3]
frame_type=input_psolve_info[4]
time_platesolve_requested=input_psolve_info[5]
pixscale=input_psolve_info[6]
pointing_ra=input_psolve_info[7]
pointing_dec=input_psolve_info[8]
platesolve_crop=input_psolve_info[9]
bin_for_platesolve=input_psolve_info[10]
platesolve_bin_factor=input_psolve_info[11]
image_saturation_level = input_psolve_info[12]
readnoise=input_psolve_info[13]
minimum_realistic_seeing=input_psolve_info[14]
is_osc=input_psolve_info[15]
useastrometrynet=input_psolve_info[16]
#useastrometrynet=True

try:
    os.remove(cal_path + 'platesolve.temppickle')
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass

#breakpoint()

# Really need to thresh the incoming image
googtime=time.time()
int_array_flattened=hdufocusdata.astype(int).ravel()
int_array_flattened=int_array_flattened[int_array_flattened > -10000]
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
m=counts.argmax()
imageMode=unique[m]
print ("Calculating Mode: " +str(time.time()-googtime))


# Zerothreshing image
googtime=time.time()
histogramdata=np.column_stack([unique,counts]).astype(np.int32)
histogramdata[histogramdata[:,0] > -10000]
#Do some fiddle faddling to figure out the value that goes to zero less
zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
breaker=1
counter=0
while (breaker != 0):
    counter=counter+1
    if not (imageMode-counter) in zeroValueArray[:,0]:
        if not (imageMode-counter-1) in zeroValueArray[:,0]:
            if not (imageMode-counter-2) in zeroValueArray[:,0]:
                if not (imageMode-counter-3) in zeroValueArray[:,0]:
                    if not (imageMode-counter-4) in zeroValueArray[:,0]:
                        if not (imageMode-counter-5) in zeroValueArray[:,0]:
                            if not (imageMode-counter-6) in zeroValueArray[:,0]:
                                if not (imageMode-counter-7) in zeroValueArray[:,0]:
                                    if not (imageMode-counter-8) in zeroValueArray[:,0]:
                                        if not (imageMode-counter-9) in zeroValueArray[:,0]:
                                            if not (imageMode-counter-10) in zeroValueArray[:,0]:
                                                if not (imageMode-counter-11) in zeroValueArray[:,0]:
                                                    if not (imageMode-counter-12) in zeroValueArray[:,0]:
                                                        zeroValue=(imageMode-counter)
                                                        breaker =0



hdufocusdata[hdufocusdata < zeroValue] = np.nan

print ("Zero Threshing Image: " +str(time.time()-googtime))

#breakpoint()

googtime=time.time()

#Check there are no nans in the image upon receipt
# This is necessary as nans aren't interpolated in the main thread.
# Fast next-door-neighbour in-fill algorithm
#num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
x_size=hdufocusdata.shape[0]
y_size=hdufocusdata.shape[1]
# this is actually faster than np.nanmean
#edgefillvalue=np.divide(np.nansum(hdufocusdata),(x_size*y_size)-num_of_nans)
edgefillvalue=imageMode
#breakpoint()
# while num_of_nans > 0:
#     # List the coordinates that are nan in the array
#
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

hdufocusdata[np.isnan(hdufocusdata)] = edgefillvalue
    #num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))

print ("Denan Image: " +str(time.time()-googtime))
googtime=time.time()
#if not is_osc:
bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
bkg.subfrom(hdufocusdata)


# hdufocus = fits.PrimaryHDU()
# hdufocus.data = bkg
# hdufocus.header = hduheader
# hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
# hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
# hdufocus.writeto(cal_path + 'background.fits', overwrite=True, output_verify='silentfix')


parentPath = Path(getcwd())
PS3CLI_EXE = str(parentPath).replace('\subprocesses','') +'/subprocesses/ps3cli/ps3cli.exe'

output_file_path = os.path.join(cal_path + "ps3cli_results.txt")
try:
    os.remove(output_file_path)
except:
    pass
try:
    os.remove(cal_path + 'platesolvetemp.fits')
except:
    pass
catalog_path = os.path.expanduser("~\\Documents\\Kepler")

if pixscale != None:
    binnedtwo=False
    binnedthree=False
    # If OSC, just bin the image. Also if the pixelscale is unnecessarily high
    if is_osc or (pixscale < 0.5 and pixscale > 0.3):
        #hdufocusdata=demosaicing_CFA_Bayer_bilinear(hdufocusdata, 'RGGB')[:,:,1]
        #hdufocusdata=hdufocusdata.astype("float32")
        hdufocusdata=np.divide(block_reduce(hdufocusdata,2,func=np.sum),2)
        pixscale=pixscale*2
        binnedtwo=True
    elif pixscale <= 0.3:
        hdufocusdata=np.divide(block_reduce(hdufocusdata,3,func=np.sum),2)
        pixscale=pixscale*3
        binnedthree=True

# else:
#     hdufocusdata=block_reduce(hdufocusdata,2,func=np.nanmean)
#     #pixscale=pixscale*2
#     binnedtwo=True

# At least chop the edges off the image
if platesolve_crop==0:
    platesolve_crop=0.15

# Crop the image for platesolving
fx, fy = hdufocusdata.shape

crop_width = (fx * platesolve_crop) / 2
crop_height = (fy * platesolve_crop) / 2

# Make sure it is an even number for OSCs
if (crop_width % 2) != 0:
    crop_width = crop_width+1
if (crop_height % 2) != 0:
    crop_height = crop_height+1

crop_width = int(crop_width)
crop_height = int(crop_height)

if crop_width > 0 or crop_height > 0:
    hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]



# binfocus = 1
# if bin_for_platesolve:
#     hdufocusdata=block_reduce(hdufocusdata,platesolve_bin_factor)
#     binfocus=platesolve_bin_factor

# focusimg = np.array(
#     hdufocusdata, order="C"
# )


# # Some of these are liberated from BANZAI
# bkg = sep.Background(focusimg, bw=32, bh=32, fw=3, fh=3)
# bkg.subfrom(focusimg)
# ix, iy = focusimg.shape

# sep.set_extract_pixstack(int(ix*iy - 1))

# #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
# # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
# # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
# if pixscale != None:
#     minarea= -9.2421 * (pixscale*platesolve_bin_factor) + 16.553
#     if minarea < 5:  # There has to be a min minarea though!
#         minarea = 5
# else:
#     minarea=5



# sources = sep.extract(
#     focusimg, 3, err=bkg.globalrms, minarea=minarea
# )

# sources = Table(sources)
# sources = sources[sources['flag'] < 8]
# sources = sources[sources["peak"] < 0.8 * image_saturation_level]
# sources = sources[sources["cpeak"] < 0.8 * image_saturation_level]
# sources = sources[sources["flux"] > 1000]
# sources = sources[sources["x"] < iy -50]
# sources = sources[sources["x"] > 50]
# sources = sources[sources["y"] < ix - 50]
# sources = sources[sources["y"] > 50]

# # BANZAI prune nans from table
# nan_in_row = np.zeros(len(sources), dtype=bool)
# for col in sources.colnames:
#     nan_in_row |= np.isnan(sources[col])
# sources = sources[~nan_in_row]

# # Calculate the ellipticity (Thanks BANZAI)

# sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])
# sources = sources[sources['ellipticity'] < 0.4]  # Remove things that are not circular stars

# # Calculate the kron radius (Thanks BANZAI)
# kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
#                                   sources['a'], sources['b'],
#                                   sources['theta'], 6.0)
# sources['flag'] |= krflag
# sources['kronrad'] = kronrad

# # Calculate uncertainty of image (thanks BANZAI)
# uncertainty = float(readnoise) * np.ones(focusimg.shape,
#                                          dtype=focusimg.dtype) / float(readnoise)

# try:
#     flux, fluxerr, flag = sep.sum_ellipse(focusimg, sources['x'], sources['y'],
#                                       sources['a'], sources['b'],
#                                       np.pi / 2.0, 2.5 * kronrad,
#                                       subpix=1, err=uncertainty)
#     sources['flux'] = flux
#     sources['fluxerr'] = fluxerr
#     sources['flag'] |= flag

# except:
#     pass



# sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
#                                       subpix=5)

# #sources['FWHM']=sources['kronrad'] * 2

# sources['FWHM'] = 2 * sources['FWHM']
# # BANZAI prune nans from table
# # nan_in_row = np.zeros(len(sources), dtype=bool)
# # for col in sources.colnames:
# #     nan_in_row |= np.isnan(sources[col])
# # sources = sources[~nan_in_row]

# sources = sources[sources['FWHM'] != 0]
# #sources = sources[sources['FWHM'] > 0.5]
# if pixscale != None:
#     sources = sources[sources['FWHM'] > (1/pixscale)]
# sources = sources[sources['FWHM'] < (np.nanmedian(sources['FWHM']) + (3 * np.nanstd(sources['FWHM'])))]

# sources = sources[sources['flux'] > 0]
# sources = sources[sources['flux'] < 1000000]




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


print ("Just before fake Image: " +str(time.time()-googtime))
googtime=time.time()

fx, fy = hdufocusdata.shape
#hdufocusdata[np.isnan(hdufocusdata)] = imageMode
#hdufocusdata=hdufocusdata-np.nanmedian(hdufocusdata)
#hdufocusdata=hdufocusdata-



#hdufocusdata=hdufocusdata-bn.nanmedian(hdufocusdata)
tempstd=np.std(hdufocusdata)
threshold=2.5* np.std(hdufocusdata[hdufocusdata < (5*tempstd)])
threshold=max(threshold,100)
list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
# Assess each point
pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
counter=0
for point in list_of_local_maxima:


    pointvalues[counter][0]=point[0]
    pointvalues[counter][1]=point[1]
    pointvalues[counter][2]=np.nan
    in_range=False
    if (point[0] > fx*0.1) and (point[1] > fy*0.1) and (point[0] < fx*0.9) and (point[1] < fy*0.9):
        in_range=True
    # else:
    #     print (point)
    #     print(hdufocusdata[point[0],point[1]])

    if in_range:
        value_at_point=hdufocusdata[point[0],point[1]]
        try:
            value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
        except:
            print(traceback.format_exc())
            #breakpoint()

        # Check it isn't just a dot
        if value_at_neighbours < (0.4*value_at_point):
            # print(hdufocusdata[point[0]-1,point[1]])
            # print(hdufocusdata[point[0]+1,point[1]])
            # print(hdufocusdata[point[0],point[1]-1])
            # print(hdufocusdata[point[0],point[1]+1])
            # print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
            #breakpoint()
            pointvalues[counter][2]=np.nan

        # # If not saturated and far away from the edge
        elif value_at_point < 0.9*image_saturation_level:
            pointvalues[counter][2]=value_at_point

        else:
            pointvalues[counter][2]=np.nan

    counter=counter+1

#print (pointvalues)

# Trim list to remove things that have too many other things close to them.

# remove nan rows
pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

# reverse sort by brightness
pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]


# reject things that are X times dimmer than the brightest source
# hdufocus = fits.PrimaryHDU()
# hdufocus.data = hdufocusdata
# hdufocus.header = hduheader
# hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
# hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
# hdufocus.writeto(cal_path + 'goop.fits', overwrite=True, output_verify='silentfix')


#breakpoint()

#breakpoint()


#breakpoint()
# radial profile
fwhmlist=[]
sources=[]
#radius_of_radialprofile=(20)
#breakpoint()

if np.isnan(pixscale):
    pixscale = None

if pixscale == None:
    radius_of_radialprofile=50
else:
    radius_of_radialprofile=int(24/pixscale)
# Round up to nearest odd number to make a symmetrical array
radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
centre_of_radialprofile=int((radius_of_radialprofile /2)+1)

sources=[]

for i in range(len(pointvalues)):

    # cx= (pointvalues[i][0])
    # cy= (pointvalues[i][1])
    # cvalue=hdufocusdata[int(cx)][int(cy)]
    #sources.append([cx,cy,cvalue])

    if len(sources) > 200:
        break

    cx= (pointvalues[i][0])
    cy= (pointvalues[i][1])
    cvalue=hdufocusdata[int(cx)][int(cy)]
    try:
        temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
    except:
        print(traceback.format_exc())
        #breakpoint()
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
    # print (abs(brightest_pixel_rdist))

    #breakpoint()

    if pixscale == None:
        largest_deviation_from_center=12
    else:
        largest_deviation_from_center=3/pixscale

    if abs(brightest_pixel_rdist) <  max(3, largest_deviation_from_center):

        try:




            # Reduce data down to make faster solvinging
            upperbin=math.floor(max(radprofile[:,0]))
            lowerbin=math.ceil(min(radprofile[:,0]))
            #number_of_bins=int((upperbin-lowerbin)/0.25)
            # Only need a quarter of an arcsecond bin.
            arcsecond_length_radial_profile = int((upperbin-lowerbin)/0.25)
            number_of_bins=int(arcsecond_length_radial_profile/0.25)
            s, edges, _ = binned_statistic(radprofile[:,0],radprofile[:,1], statistic='mean', bins=np.linspace(lowerbin,upperbin,number_of_bins))

            max_value=bn.nanmax(s)
            min_value=bn.nanmin(s)
            threshold_value=(0.05*(max_value-min_value)) + min_value

            actualprofile=[]
            for q in range(len(s)):
                if not np.isnan(s[q]):
                    if s[q] > threshold_value:
                        actualprofile.append([(edges[q]+edges[q+1])/2,s[q]])

            actualprofile=np.asarray(actualprofile)




            edgevalue_left=actualprofile[0][1]
            edgevalue_right=actualprofile[-1][1]

            if edgevalue_left < 0.6*cvalue and  edgevalue_right < 0.6*cvalue:

                if pixscale == None:
                    stdevstart= 4
                else:
                    stdevstart=2/pixscale

                #popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1])
                #popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1], p0=[cvalue,0,((2/pixscale) /2.355)], bounds=([cvalue/2,-10, 0],[cvalue*1.2,10,10]), xtol=0.05, ftol=0.05)
                popt, _ = optimize.curve_fit(gaussian, actualprofile[:,0], actualprofile[:,1], p0=[cvalue,0,((stdevstart) /2.355)], bounds=([cvalue/2,-10, 0],[cvalue*1.2,10,10]))#, xtol=0.005, ftol=0.005)


                # Amplitude has to be a substantial fraction of the peak value
                # and the center of the gaussian needs to be near the center
                if popt[0] > (0.5 * cvalue) and abs(popt[1]) < max(3, largest_deviation_from_center) :
                    # print ("amplitude: " + str(popt[0]) + " center " + str(popt[1]) + " stdev? " +str(popt[2]))
                    # print ("Brightest pixel at : " + str(brightest_pixel_rdist))
                    #plt.scatter(radprofile[:,0],radprofile[:,1])
                    #plt.plot(radprofile[:,0], gaussian(radprofile[:,0], *popt),color = 'r')



                    # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                    # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *popt),color = 'r')
                    # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                    # plt.show()

                    #breakpoint()

                    sources.append([cx,cy,cvalue])

                    # FWHM is 2.355 * std for a gaussian
                    #fwhmlist.append(popt[2])
                    #sources.append([cx,cy,radprofile,temp_array])
                    # If we've got more than 50, good
                    #if len(fwhmlist) > 50:
                    #    bailout=True
                    #    break
                    # #If we've got more than ten and we are getting dim, bail out.
                    # if len(fwhmlist) > 10 and brightest_pixel_value < (0.2*saturate):
                    #     bailout=True
                    #     break
        except:
            pass


# Keep top 200
sources=np.asarray(sources)
if len(sources) > 200:
    sources=sources[:200,:]

# hdufocus = fits.PrimaryHDU()
# hdufocus.data = hdufocusdata
# hdufocus.header = hduheader
# hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
# hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
# hdufocus.writeto(cal_path + 'goop.fits', overwrite=True, output_verify='silentfix')


# breakpoint()


print ("Constructor " + str(time.time()-googtime))
googtime=time.time()
#breakpoint()
#breakpoint()
#breakpoint()
#breakpoint()
failed=True

#breakpoint()
if len(sources) >= 5:

    if not pixscale == None or np.isnan(pixscale):
        # Get size of original image
        xpixelsize = hdufocusdata.shape[0]
        ypixelsize = hdufocusdata.shape[1]
        shape = (xpixelsize, ypixelsize)

        # Make blank synthetic image with a sky background
        synthetic_image = np.zeros([xpixelsize, ypixelsize])
        synthetic_image = synthetic_image + 200

        #Bullseye Star Shape
        modelstar = [
                    [ .01 , .05 , 0.1 , 0.2,  0.1, .05, .01],
                    [ .05 , 0.1 , 0.2 , 0.4,  0.2, 0.1, .05],
                    [ 0.1 , 0.2 , 0.4 , 0.8,  0.4, 0.2, 0.1],
                    [ 0.2 , 0.4 , 0.8 , 1.2,  0.8, 0.4, 0.2],
                    [ 0.1 , 0.2 , 0.4 , 0.8,  0.4, 0.2, 0.1],
                    [ .05 , 0.1 , 0.2 , 0.4,  0.2, 0.1, .05],
                    [ .01 , .05 , 0.1 , 0.2,  0.1, .05, .01]

                    ]


        modelstar=np.array(modelstar)

        # # Add bullseye stars to blank image
        # for addingstar in sources:
        #     x = round(addingstar['x'] -1)
        #     y = round(addingstar['y'] -1)
        #     peak = int(addingstar['peak'])
        #     # Add star to numpy array as a slice
        #     try:
        #         synthetic_image[y-3:y+4,x-3:x+4] += peak*modelstar
        #     except Exception as e:
        #         print (e)
        #         #breakpoint()



        # Add bullseye stars to blank image
        for addingstar in sources:
            x = round(addingstar[1] -1)
            y = round(addingstar[0] -1)
            peak = int(addingstar[2])
            # Add star to numpy array as a slice
            try:
                synthetic_image[y-3:y+4,x-3:x+4] += peak*modelstar
            except Exception as e:
                print (e)
                #breakpoint()

        # Make an int16 image for planewave solver
        hdufocusdata = np.array(synthetic_image, dtype=np.int32)
        hdufocusdata[hdufocusdata < 0] = 200
        hdufocus = fits.PrimaryHDU()
        hdufocus.data = hdufocusdata
        hdufocus.header = hduheader
        hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
        hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
        hdufocus.writeto(cal_path + 'platesolvetemp.fits', overwrite=True, output_verify='silentfix')
        #pixscale = (hdufocus.header['PIXSCALE'])

        #breakpoint()

        try:
            hdufocus.close()
        except:
            pass
        del hdufocusdata
        del hdufocus




        # First try with normal pixscale
        failed = False
        args = [
            PS3CLI_EXE,
            cal_path + 'platesolvetemp.fits',
            str(pixscale),
            output_file_path,
            catalog_path
        ]

        process = Popen(
                args,
                stdout=None,
                stderr=PIPE
                )
        (stdout, stderr) = process.communicate()  # Obtain stdout and stderr output from the wcs tool
        exit_code = process.wait() # Wait for process to complete and obtain the exit code

        time.sleep(1)
        process.kill()

        # print (stdout)
        # print (stderr)



        #breakpoint()
        try:
            solve = parse_platesolve_output(output_file_path)
            print (solve['arcsec_per_pixel'])
            if binnedtwo:
                solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/2
            elif binnedthree:
                solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/3
        except:
            failed=True

        # pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
        # try:
        #     os.remove(cal_path + 'platesolve.pickle')
        # except:
        #     pass
        # os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

        # try:
        #     os.remove(cal_path + 'platesolvetemp.fits')
        # except:
        #     pass
        # try:
        #     os.remove(output_file_path)
        # except:
        #     pass
        # failed=False

        #breakpoint()()
        #sys.exit()


        # except:
        #     print(traceback.format_exc())
        #     #breakpoint()
        #     failed = True
        #     process.kill()

        if failed:
            failed=False

            # Try again with a lower pixelscale... yes it makes no sense
            # But I didn't write PS3.exe ..... but it works (MTF)
            args = [
                PS3CLI_EXE,
                cal_path + 'platesolvetemp.fits',
                str(float(pixscale)/2.0),
                output_file_path,
                catalog_path
            ]

            process = Popen(
                    args,
                    stdout=None,
                    stderr=PIPE
                    )
            (stdout, stderr) = process.communicate()  # Obtain stdout and stderr output from the wcs tool
            exit_code = process.wait() # Wait for process to complete and obtain the exit code
            time.sleep(1)
            process.kill()

            print (stdout)
            print (stderr)


            try:
                solve = parse_platesolve_output(output_file_path)
                print (solve['arcsec_per_pixel'])
                if binnedtwo:
                    solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/2
                elif binnedthree:
                    solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/3
            except:
                failed=True

            # pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
            # try:
            #     os.remove(cal_path + 'platesolve.pickle')
            # except:
            #     pass
            # os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

            # # pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
            # # os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

            # try:
            #     os.remove(cal_path + 'platesolvetemp.fits')
            # except:
            #     pass
            # try:
            #     os.remove(output_file_path)
            # except:
            #     pass
            # sys.exit()

                # try:
                #     os.remove(cal_path + 'platesolvetemp.fits')
                # except:
                #     pass
                # try:
                #     os.remove(output_file_path)
                # except:
                #     pass

                # sys.exit()

            # except:
            #     print(traceback.format_exc())
            #     failed=True
            #     process.kill()
            #     #solve = 'error'

    # if unknown pixelscale do a search
    print ("failed?")
    print (failed)
    if failed or pixscale == None or np.isnan(pixscale):#) and useastrometrynet:


        #from astropy.table import Table
        from astroquery.astrometry_net import AstrometryNet

        ast = AstrometryNet()
        ast.api_key = 'pdxlsqwookogoivt'
        ast.key = 'pdxlsqwookogoivt'

        #sources = Table.read('catalog.fits')
        # Sort sources in ascending order
        #sources.sort('FLUX')
        # Reverse to get descending order
        #sources.reverse()

        #breakpoint()

        #sources.sort('flux')
        #sources.reverse()
        #sources=sources[:,200]


        if pixscale == None or np.isnan(pixscale):
            scale_lower=0.04
            scale_upper=8.0
        elif binnedtwo:
            scale_lower=0.9* pixscale*2
            scale_upper=1.1* pixscale*2

        elif binnedthree:
            scale_lower=0.9* pixscale*3
            scale_upper=1.1* pixscale*3

        else:
            scale_lower=0.9* pixscale
            scale_upper=1.1* pixscale

        image_width = fx
        image_height = fy

        # If searching for the first pixelscale,
        # Then wait for a LONG time to get it.
        # with a wider range
        if pixscale == None or np.isnan(pixscale):
            wcs_header = ast.solve_from_source_list(pointvalues[:,0], pointvalues[:,1],
                                                    image_width, image_height, crpix_center=True, center_dec= pointing_dec, scale_lower=scale_lower, scale_upper=scale_upper, scale_units='arcsecperpix', center_ra = pointing_ra*15,radius=15.0,
                                                    solve_timeout=1200)
        else:
            wcs_header = ast.solve_from_source_list(pointvalues[:,0], pointvalues[:,1],
                                                    image_width, image_height, crpix_center=True, center_dec= pointing_dec, scale_lower=scale_lower, scale_upper=scale_upper, scale_units='arcsecperpix', center_ra = pointing_ra*15,radius=5.0,
                                                    solve_timeout=60)


        print (wcs_header)
        print (len(wcs_header))

        if wcs_header=={}:
            solve = 'error'
            # pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
            # try:
            #     os.remove(cal_path + 'platesolve.pickle')
            # except:
            #     pass
            # os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

            # try:
            #     os.remove(cal_path + 'platesolvetemp.fits')
            # except:
            #     pass
            # try:
            #     os.remove(output_file_path)
            # except:
            #     pass
            # sys.exit()
        else:


            solve={}
            solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
            solve["dec_j2000_degrees"] = wcs_header['CRVAL2']
            solve["arcsec_per_pixel"] = wcs_header['CD1_2'] *3600

            if binnedtwo:
                solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
            elif binnedthree:
                solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/3


        # pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
        # try:
        #     os.remove(cal_path + 'platesolve.pickle')
        # except:
        #     pass
        # os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

        # try:
        #     os.remove(cal_path + 'platesolvetemp.fits')
        # except:
        #     pass
        # try:
        #     os.remove(output_file_path)
        # except:
        #     pass
        # sys.exit()

        # except:
        #     print(traceback.format_exc())

        #     solve = 'error'
        #     pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
        #     try:
        #         os.remove(cal_path + 'platesolve.pickle')
        #     except:
        #         pass
        #     os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

        #     try:
        #         os.remove(cal_path + 'platesolvetemp.fits')
        #     except:
        #         pass
        #     try:
        #         os.remove(output_file_path)
        #     except:
        #         pass
        #     sys.exit()
        #     #breakpoint()

        #breakpoint()




        # This section is lifted from the BANZAI code


        # image_catalog=sources
        # image_catalog.sort('flux')
        # image_catalog.reverse()

        # catalog_payload = {'X': list(image_catalog['x'])[:200],
        #                    'Y': list(image_catalog['y'])[:200],
        #                    'FLUX': list(image_catalog['flux'])[:200],
        #                    'pixel_scale': 0.5,
        #                    'naxis': 2,
        #                    'naxis1':  fx,
        #                    'naxis2':  fy,
        #                    'ra': pointing_ra,
        #                    'dec': pointing_dec,
        #                    'statistics': False,
        #                    'filename': cal_path + 'platesolvetemp.fits'}

        # ASTROMETRY_SERVICE_URL =  'http://astrometry.lco.gtn/catalog/'

        # astrometry_response = requests.post(ASTROMETRY_SERVICE_URL, json=catalog_payload)
        # astrometry_response.raise_for_status()

        # breakpoint()

        # pixscale = 0.05
        # while pixscale < 10:
        #     pixscale=pixscale + 0.05

        #     print ("Attempting " + str(pixscale))
        #     try:
        #         # Try again with a lower pixelscale... yes it makes no sense
        #         # But I didn't write PS3.exe ..... but it works (MTF)
        #         args = [
        #             PS3CLI_EXE,
        #             cal_path + 'platesolvetemp.fits',
        #             str(float(pixscale/2)),
        #             output_file_path,
        #             catalog_path
        #         ]

        #         process = Popen(
        #                 args,
        #                 stdout=PIPE,
        #                 stderr=PIPE
        #                 )
        #         (stdout, stderr) = process.communicate()  # Obtain stdout and stderr output from the wcs tool
        #         exit_code = process.wait() # Wait for process to complete and obtain the exit code

        #         print (stdout)
        #         print (exit_code)
        #         time.sleep(1)
        #         process.kill()
        #         #breakpoint()



        #         solve = parse_platesolve_output(output_file_path)
        #         if binnedtwo:
        #             solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
        #         elif binnedthree:
        #             solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/3

        #         print (solve)
        #         break
        #         # if binnedtwo:
        #         #     solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
        #         # elif binnedthree:
        #         #     solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/3

        #     except:
        #         process.kill()
        #         solve = 'error'
        #         tryagain=True

        #     if pixscale==9.0:
        #         process.kill()
        #         solve = 'error'
        #         break





else:
    solve = 'error'






pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))

try:
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass
os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

try:
    os.remove(cal_path + 'platesolvetemp.fits')
except:
    pass
try:
    os.remove(output_file_path)
except:
    pass


# pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))
# os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')


print (solve)
print ("solver: " +str(time.time()-googtime))

# try:
#     os.remove(cal_path + 'platesolvetemp.fits')
# except:
#     pass
# try:
#     os.remove(output_file_path)
# except:
#     pass
# sys.exit()

#breakpoint()


