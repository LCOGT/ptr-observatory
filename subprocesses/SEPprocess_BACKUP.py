# -*- coding: utf-8 -*-
"""
Created on Sun Apr 23 04:37:30 2023

@author: observatory
"""

import numpy as np
# Need this line to output the full array to text for the json
np.set_printoptions(threshold=np.inf)

import re
from astropy.stats import median_absolute_deviation
from astropy.nddata.utils import extract_array
import sys
import pickle
import time
import sep
import traceback
import math
import json
# from scipy import ndimage as nd
from auto_stretch.stretch import Stretch
# from astropy.nddata import block_reduce
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
from PIL import Image, ImageDraw # ImageFont, ImageDraw#, ImageEnhance
from astropy.table import Table
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)
#import matplotlib.pyplot as plt


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

#frame_type='expose'

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

# Check there are no nans in the image upon receipt
# This is necessary as nans aren't interpolated in the main thread.
# Fast next-door-neighbour in-fill algorithm
num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
x_size=hdufocusdata.shape[0]
y_size=hdufocusdata.shape[1]
# this is actually faster than np.nanmean
edgefillvalue=np.divide(np.nansum(hdufocusdata),(x_size*y_size)-num_of_nans)
#breakpoint()
while num_of_nans > 0:
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

    num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))

#nativebin=1
# Background clipped
hduheader["IMGMIN"] = ( np.nanmin(hdufocusdata), "Minimum Value of Image Array" )
hduheader["IMGMAX"] = ( np.nanmax(hdufocusdata), "Maximum Value of Image Array" )
hduheader["IMGMEAN"] = ( np.nanmean(hdufocusdata), "Mean Value of Image Array" )
hduheader["IMGMED"] = ( np.nanmedian(hdufocusdata), "Median Value of Image Array" )


hduheader["IMGSTDEV"] = ( np.nanstd(hdufocusdata), "Median Value of Image Array" )
hduheader["IMGMAD"] = ( median_absolute_deviation(hdufocusdata, ignore_nan=True), "Median Absolute Deviation of Image Array" )

#breakpoint()

# no zero values in readnoise.
if float(readnoise) < 0.1:
    readnoise = 0.1

# Get out raw histogram construction data
# Get a flattened array with all nans removed
int_array_flattened=hdufocusdata.astype(int).ravel()
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
m=counts.argmax()
imageMode=unique[m]

hduheader["IMGMODE"] = ( imageMode, "Mode Value of Image Array" )



#####
# HACK TO EXPERIMENT
#####
#frame_type='focus'



#breakpoint()

# Don't need this bit for images we aren't keeping
if frame_type=='expose':

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

    np.savetxt(
        im_path + text_name.replace('.txt', '.his'),
        histogramdata, delimiter=','
    )

    imageinspection_json_snippets['histogram']= re.sub('\s+',' ',str(histogramdata))
    #starinspection_json_snippets={}
   # json_snippets

if not do_sep or (float(hduheader["EXPTIME"]) < 1.0):
    rfp = np.nan
    rfr = np.nan
    rfs = np.nan
    sepsky = np.nan
else:

    # Realistically we can figure out the focus stuff here from first principles.

    if frame_type == 'focus':
        #breakpoint()
        fx, fy = hdufocusdata.shape
        # We want a standard focus image size that represent 0.2 degrees - which is the size of the focus fields.
        # However we want some flexibility in the sense that the pointing could be off by half a degree or so...
        # So we chop the image down to a degree by a degree
        # This speeds up the focus software.... we don't need to solve for EVERY star in a widefield image.
        fx_degrees = (fx * pixscale) /3600
        fy_degrees = (fy * pixscale) /3600

        crop_x=0
        crop_y=0


        if fx_degrees > 1.0:
            ratio_crop= 1/fx_degrees
            crop_x = int((fx - (ratio_crop * fx))/2)
        if fy_degrees > 1.0:
            ratio_crop= 1/fy_degrees
            crop_y = int((fy - (ratio_crop * fy))/2)

        if crop_x > 0 or crop_y > 0:
            if crop_x == 0:
                crop_x = 2
            if crop_y == 0:
                crop_y = 2
            # Make sure it is an even number for OSCs
            if (crop_x % 2) != 0:
                crop_x = crop_x+1
            if (crop_y % 2) != 0:
                crop_y = crop_y+1

            #breakpoint()

            hdufocusdata = hdufocusdata[crop_x:-crop_x, crop_y:-crop_y]

    if is_osc:

        # Rapidly interpolate so that it is all one channel
        #timegoog=time.time()
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



    if frame_type=='focus':
        try:

            fx, fy = hdufocusdata.shape
            hdufocusdata[np.isnan(hdufocusdata)] = imageMode
            hdufocusdata=hdufocusdata-imageMode
            tempstd=np.std(hdufocusdata)
            threshold=3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)])
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

                if in_range:
                    value_at_point=hdufocusdata[point[0],point[1]]
                    try:
                        value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
                    except:
                        print(traceback.format_exc())
                        breakpoint()

                    # Check it isn't just a dot
                    if value_at_neighbours < (0.6*value_at_point):
                        #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
                        pointvalues[counter][2]=np.nan

                    # If not saturated and far away from the edge
                    elif value_at_point < 0.8*saturate:
                        pointvalues[counter][2]=value_at_point

                    else:
                        pointvalues[counter][2]=np.nan

                counter=counter+1


            # Trim list to remove things that have too many other things close to them.

            # remove nan rows
            pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

            # reverse sort by brightness
            pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]

            # radial profile
            fwhmlist=[]
            sources=[]
            radius_of_radialprofile=(30)
            # Round up to nearest odd number to make a symmetrical array
            radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
            centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
            for i in range(min(len(pointvalues),200)):
                cx= (pointvalues[i][0])
                cy= (pointvalues[i][1])
                cvalue=hdufocusdata[int(cx)][int(cy)]
                try:
                    temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
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
                if abs(brightest_pixel_rdist) < 4:

                    try:
                        popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1])

                        # Amplitude has to be a substantial fraction of the peak value
                        # and the center of the gaussian needs to be near the center
                        if popt[0] > (0.5 * cvalue) and abs(popt[1]) < 3 :
                            # print ("amplitude: " + str(popt[0]) + " center " + str(popt[1]) + " stdev? " +str(popt[2]))
                            # print ("Brightest pixel at : " + str(brightest_pixel_rdist))
                            # plt.scatter(radprofile[:,0],radprofile[:,1])
                            # plt.plot(radprofile[:,0], gaussian(radprofile[:,0], *popt),color = 'r')
                            # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                            # plt.show()

                            # FWHM is 2.355 * std for a gaussian
                            fwhmlist.append(popt[2])
                            sources.append([cx,cy,radprofile,temp_array])
                            # If we've got more than 50, good
                            if len(fwhmlist) > 50:
                                bailout=True
                                break
                            #If we've got more than ten and we are getting dim, bail out.
                            if len(fwhmlist) > 10 and brightest_pixel_value < (0.2*saturate):
                                bailout=True
                                break
                    except:
                        pass


            rfp = abs(np.nanmedian(fwhmlist)) * 4.710
            rfr = rfp * pixscale
            rfs = np.nanstd(fwhmlist) * pixscale
            sepsky = imageMode
            fwhm_file={}
            fwhm_file['rfp']=str(rfp)
            fwhm_file['rfr']=str(rfr)
            fwhm_file['rfs']=str(rfs)
            fwhm_file['sky']=str(imageMode)
            fwhm_file['sources']=str(len(fwhmlist))
            # dump the settings files into the temp directory
            with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
                json.dump(fwhm_file, f)

            #breakpoint()

            # for i in range(len(sources)):
            #     plt.imshow(sources[i][3])
            #     plt.show()
            #     time.sleep(0.05)


        except:
            traceback.format_exc()
            sources = [0]
            rfp = np.nan
            rfr = np.nan
            rfs = np.nan
            sepsky = np.nan



        #breakpoint()






    else:

        actseptime = time.time()
        focusimg = np.array(
            hdufocusdata, order="C"
        )

        try:
            # Some of these are liberated from BANZAI



            bkg = sep.Background(focusimg, bw=32, bh=32, fw=3, fh=3)
            bkg.subfrom(focusimg)

            sepsky = (np.nanmedian(bkg), "Sky background estimated by SEP")

            ix, iy = focusimg.shape
            border_x = int(ix * 0.05)
            border_y = int(iy * 0.05)
            sep.set_extract_pixstack(int(ix*iy - 1))

            #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
            # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
            # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
            minarea= (-9.2421 * pixscale) + 16.553
            if minarea < 5:  # There has to be a min minarea though!
                minarea = 5

            sources = sep.extract(
                focusimg, 3.0, err=bkg.globalrms, minarea=minarea
            )
            sources = Table(sources)


            sources = sources[sources['flag'] < 8]
            image_saturation_level = saturate
            sources = sources[sources["peak"] < 0.8 * image_saturation_level]
            sources = sources[sources["cpeak"] < 0.8 * image_saturation_level]
            sources = sources[sources["flux"] > 1000]
            #sources = sources[sources["x"] < iy - border_y]
            #sources = sources[sources["x"] > border_y]
            #sources = sources[sources["y"] < ix - border_x]
            #sources = sources[sources["y"] > border_x]
            #breakpoint()
            # BANZAI prune nans from table





            nan_in_row = np.zeros(len(sources), dtype=bool)
            for col in sources.colnames:
                nan_in_row |= np.isnan(sources[col])
            sources = sources[~nan_in_row]

            #breakpoint()

            # Calculate the ellipticity (Thanks BANZAI)

            sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])

            # if frame_type == 'focus':
            #     sources = sources[sources['ellipticity'] < 0.4]  # Remove things that are not circular stars
            # else:
            #breakpoint()
            sources = sources[sources['ellipticity'] < 0.6]  # Remove things that are not circular stars

            # Calculate the kron radius (Thanks BANZAI)
            kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
                                              sources['a'], sources['b'],
                                              sources['theta'], 6.0)
            sources['flag'] |= krflag
            sources['kronrad'] = kronrad

            # Calculate uncertainty of image (thanks BANZAI)

            uncertainty = float(readnoise) * np.ones(focusimg.shape,
                                                     dtype=focusimg.dtype) / float(readnoise)


            # DONUT IMAGE DETECTOR.
            xdonut=np.median(pow(pow(sources['x'] - sources['xpeak'],2),0.5))*pixscale
            ydonut=np.median(pow(pow(sources['y'] - sources['ypeak'],2),0.5))*pixscale

            # Calcuate the equivilent of flux_auto (Thanks BANZAI)
            # This is the preferred best photometry SEP can do.
            # But sometimes it fails, so we try and except
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



            sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
                                                  subpix=5)

            #breakpoint()
            # If image has been binned for focus we need to multiply some of these things by the binning
            # To represent the original image
            sources['FWHM'] = (sources['FWHM'] * 2)

            #sources['FWHM']=sources['kronrad'] * 2

            #print (sources)

            # Need to reject any stars that have FWHM that are less than a extremely
            # perfect night as artifacts
            # if frame_type == 'focus':
            #     sources = sources[sources['FWHM'] > (0.6 / (pixscale))]
            #     sources = sources[sources['FWHM'] > (minimum_realistic_seeing / pixscale)]
            #     sources = sources[sources['FWHM'] != 0]

            source_delete = ['thresh', 'npix', 'tnpix', 'xmin', 'xmax', 'ymin', 'ymax', 'x2', 'y2', 'xy', 'errx2',
                             'erry2', 'errxy', 'a', 'b', 'theta', 'cxx', 'cyy', 'cxy', 'cflux', 'cpeak', 'xcpeak', 'ycpeak']

            sources.remove_columns(source_delete)



            # BANZAI prune nans from table
            nan_in_row = np.zeros(len(sources), dtype=bool)
            for col in sources.colnames:
                nan_in_row |= np.isnan(sources[col])
            sources = sources[~nan_in_row]



            sources = sources[sources['FWHM'] != 0]
            #sources = sources[sources['FWHM'] > 0.6]
            sources = sources[sources['FWHM'] > (1/pixscale)]

            #breakpoint()

            sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)

            if (len(sources) < 2) or ( frame_type == 'focus' and (len(sources) < 10 or len(sources) == np.nan or str(len(sources)) =='nan' or xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut))):
                sources['FWHM'] = [np.nan] * len(sources)
                rfp = np.nan
                rfr = np.nan
                rfs = np.nan
                sources = sources

            else:
                # Get halflight radii

                fwhmcalc = sources['FWHM']
                fwhmcalc = fwhmcalc[fwhmcalc != 0]

                # sigma clipping iterator to reject large variations
                templen = len(fwhmcalc)
                while True:
                    fwhmcalc = fwhmcalc[fwhmcalc < np.median(fwhmcalc) + 3 * np.std(fwhmcalc)]
                    if len(fwhmcalc) == templen:
                        break
                    else:
                        templen = len(fwhmcalc)

                fwhmcalc = fwhmcalc[fwhmcalc > np.median(fwhmcalc) - 3 * np.std(fwhmcalc)]
                rfp = round(np.median(fwhmcalc), 3) * sep_to_moffat_factor
    #            rfr = round(np.median(fwhmcalc) * pixscale * nativebin, 3)
    #            rfs = round(np.std(fwhmcalc) * pixscale * nativebin, 3)
                rfr = round(np.median(fwhmcalc) * pixscale, 3) * sep_to_moffat_factor
                rfs = round(np.std(fwhmcalc) * pixscale, 3) * sep_to_moffat_factor


                #print (sources)
                #breakpoint()

            fwhm_file={}
            fwhm_file['rfp']=str(rfp)
            fwhm_file['rfr']=str(rfr)
            fwhm_file['rfs']=str(rfs)
            fwhm_file['sky']=str(sepsky)
            fwhm_file['sources']=str(len(sources))
            # dump the settings files into the temp directory
            with open(im_path + text_name.replace('.txt', '.fwhm'), 'w') as f:
                json.dump(fwhm_file, f)




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
# Value-added header items for the UI


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

imageinspection_json_snippets['header']=headerdict
starinspection_json_snippets['header']=headerdict
#json_snippets['header']=headerdict
#breakpoint()
# Create radial profiles for UI
# Determine radial profiles of top 20 star-ish sources
if do_sep and (not frame_type=='focus'):
    try:
        # Get rid of non-stars
        sources=sources[sources['FWHM'] < rfr + 2 * rfs]

        # Reverse sort sources on flux
        sources.sort('flux')
        sources.reverse()

        # radtime=time.time()
        # dodgylist=[]
        # radius_of_radialprofile=(5*math.ceil(rfp))
        # # Round up to nearest odd number to make a symmetrical array
        # radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
        # centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        # for i in range(min(len(sources),200)):
        #     cx= (sources[i]['x'])
        #     cy= (sources[i]['y'])
        #     temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cy,cx))
        #     crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])
        #     dodgylist.append([cx,cy,crad,temp_array])




        # radial profile
        fwhmlist=[]
        radials=[]
        #radius_of_radialprofile=(30)
        radius_of_radialprofile=(5*math.ceil(rfp))
        # Round up to nearest odd number to make a symmetrical array
        radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
        centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        # for i in range(min(len(pointvalues),200)):
        #     cx= (pointvalues[i][0])
        #     cy= (pointvalues[i][1])
        #     cvalue=hdufocusdata[int(cx)][int(cy)]
        for i in range(min(len(sources),200)):
            cx= (sources[i]['y'])
            cy= (sources[i]['x'])
            cvalue=(sources[i]['peak'])
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
                # if bailout==True:
                #     break
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
            if abs(brightest_pixel_rdist) < 4:

                try:
                    popt, _ = optimize.curve_fit(gaussian, radprofile[:,0], radprofile[:,1])

                    # Amplitude has to be a substantial fraction of the peak value
                    # and the center of the gaussian needs to be near the center
                    if popt[0] > (0.5 * cvalue) and abs(popt[1]) < 3 :
                        # print ("amplitude: " + str(popt[0]) + " center " + str(popt[1]) + " stdev? " +str(popt[2]))
                        # print ("Brightest pixel at : " + str(brightest_pixel_rdist))
                        # plt.scatter(radprofile[:,0],radprofile[:,1])
                        # plt.plot(radprofile[:,0], gaussian(radprofile[:,0], *popt),color = 'r')
                        # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                        # plt.show()

                        # FWHM is 2.355 * std for a gaussian
                        #fwhmlist.append(popt[2])
                        radials.append([cx,cy,radprofile,temp_array,popt])
                        # If we've got more than 50, good
                        # if len(fwhmlist) > 50:
                        #     bailout=True
                        #     break
                        # #If we've got more than ten and we are getting dim, bail out.
                        # if len(fwhmlist) > 10 and brightest_pixel_value < (0.2*saturate):
                        #     bailout=True
                        #     break
                except:
                    pass


        pickle.dump(radials, open(im_path + text_name.replace('.txt', '.rad'),'wb'))
        #json_snippets['radialprofiles']=str(radials)
        #imageinspection_json_snippets['header']=headerdict
        starinspection_json_snippets['radialprofiles']=re.sub('\s+',' ',str(radials))
        #print (radials)
        #breakpoint()
        
        imageinspection_json_snippets['photometry']=re.sub('\s+',' ',str(sources))
        starinspection_json_snippets['photometry']=re.sub('\s+',' ',str(sources))


    except:
        pass

    # Constructing the slices and dices
    try:
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
                imgmin = ( np.nanmin(statistic_area), "Minimum Value of Image Array" )
                imgmax = ( np.nanmax(statistic_area), "Maximum Value of Image Array" )
                imgmean = ( np.nanmean(statistic_area), "Mean Value of Image Array" )
                imgmed = ( np.nanmedian(statistic_area), "Median Value of Image Array" )
                imgstdev = ( np.nanstd(statistic_area), "Median Value of Image Array" )
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

        pickle.dump(slice_n_dice, open(im_path + text_name.replace('.txt', '.box'),'wb'))

        #json_snippets['sliceanddice']=str(slice_n_dice)
        imageinspection_json_snippets['sliceanddice']=re.sub('\s+',' ',str(slice_n_dice)).replace('dtype=float32','').replace('array','')
        #starinspection_json_snippets['radialprofiles']=str(radials)
    except:
        pass



#breakpoint()

with open(im_path + 'image_' + text_name.replace('.txt', '.json'), 'w') as f:
    json.dump(imageinspection_json_snippets, f)

with open(im_path + 'star_' + text_name.replace('.txt', '.json'), 'w') as f:
    json.dump(starinspection_json_snippets, f)

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