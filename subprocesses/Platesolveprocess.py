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
import copy
from astropy.nddata import block_reduce
import numpy as np
import sep
import glob
from astropy.nddata.utils import extract_array
from astropy.io import fits
#from subprocess import Popen, PIPE
import os
from pathlib import Path
from os import getcwd
import time
from astropy.utils.exceptions import AstropyUserWarning
from astropy.table import Table
import warnings
import traceback
import bottleneck as bn
from math import cos, radians
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
import matplotlib.pyplot as plt
import math
from PIL import Image#, ImageOps
from scipy.stats import binned_statistic
from astropy.wcs import WCS
from astropy import units as u
from astropy.visualization.wcsaxes import Quadrangle
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
pointing_exposure=input_psolve_info[17]
jpeg_filename=input_psolve_info[18]
target_ra=input_psolve_info[19]
target_dec=input_psolve_info[20]

try:
    os.remove(cal_path + 'platesolve.temppickle')
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass

try:
    if np.isnan(pixscale):
        pixscale=None
except:
    pixscale=None

print ("Pixelscale")
print (pixscale)

# Keep a copy of the normal image if this is a pointing image
if pointing_exposure:
    pointing_image=copy.deepcopy(hdufocusdata)

googtime=time.time()
# If this is an osc image, then interpolate so it is just the green filter image of the same size.
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

    #Maybe just try this? #hdufocusdata=demosaicing_CFA_Bayer_bilinear(hdufocusdata, 'RGGB')[:,:,1]
    #hdufocusdata=hdufocusdata.astype("float32")

try:
    bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
    bkg.subfrom(hdufocusdata)
except:
    hdufocusdata=np.array(hdufocusdata, dtype=float)
    bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
    bkg.subfrom(hdufocusdata)


# If this is set to true, then it will output a sample of the background image.
if False:
    hdufocus = fits.PrimaryHDU()
    hdufocus.data = bkg
    hdufocus.header = hduheader
    hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
    hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
    hdufocus.writeto(cal_path + 'background.fits', overwrite=True, output_verify='silentfix')


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
    # Just bin the image unless the pixelscale is high
    if pixscale < 0.5 and pixscale > 0.3:

        hdufocusdata=np.divide(block_reduce(hdufocusdata,2,func=np.sum),2)
        pixscale=pixscale*2
        binnedtwo=True
    elif pixscale <= 0.3:
        hdufocusdata=np.divide(block_reduce(hdufocusdata,3,func=np.sum),2)
        pixscale=pixscale*3
        binnedthree=True


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


# This section crops down the image to a reasonable thing to solve
# The platesolver only provides the RA and Dec of the center of the frame
# So anything above about half a degree is largely useless
# and hampers speedy and successful solving.
# Also larger fields of view see twists and warps towards tehe edge of the images
if pixscale != None:
    x_size_degrees=hdufocusdata.shape[0] * (pixscale / 3600)
    x_size_pixel_needed= (hdufocusdata.shape[0] / (x_size_degrees)) / 2 # Size in pixels of a half degree sized image
    if x_size_degrees > 0.5:
        crop_width=int((hdufocusdata.shape[0] - x_size_pixel_needed)/2)
    else:
        crop_width=2

    y_size_degrees=hdufocusdata.shape[1] * (pixscale / 3600)
    y_size_pixel_needed= (hdufocusdata.shape[1] / (y_size_degrees)) / 2
    if y_size_degrees > 0.5:
        crop_height=int((hdufocusdata.shape[1] - y_size_pixel_needed)/2)
    else:
        crop_height=2

    #breakpoint()
    hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]


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
tempstd=bn.nanstd(hdufocusdata)
threshold=2.5* bn.nanstd(hdufocusdata[hdufocusdata < (5*tempstd)])
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

    if in_range:
        value_at_point=hdufocusdata[point[0],point[1]]
        try:
            value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
        except:
            print(traceback.format_exc())

        # Check it isn't just a dot
        if value_at_neighbours < (0.4*value_at_point):
            pointvalues[counter][2]=np.nan

        # # If not saturated and far away from the edge
        elif value_at_point < 0.9*image_saturation_level:
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
try:
    if np.isnan(pixscale):
        pixscale = None
except:
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

    if len(sources) > 2000:
        break

    cx= (pointvalues[i][0])
    cy= (pointvalues[i][1])
    cvalue=hdufocusdata[int(cx)][int(cy)]
    try:
        temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
    except:
        print(traceback.format_exc())

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
    if pixscale == None:
        largest_deviation_from_center=12
    else:
        largest_deviation_from_center=3/pixscale

    if abs(brightest_pixel_rdist) <  max(3, largest_deviation_from_center):

        try:
            # Reduce data down to make faster solvinging
            upperbin=math.floor(max(radprofile[:,0]))
            lowerbin=math.ceil(min(radprofile[:,0]))
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

                popt, _ = optimize.curve_fit(gaussian, actualprofile[:,0], actualprofile[:,1], p0=[cvalue,0,((stdevstart) /2.355)], bounds=([cvalue/2,-10, 0],[cvalue*1.2,10,10]))#, xtol=0.005, ftol=0.005)

                # Amplitude has to be a substantial fraction of the peak value
                # and the center of the gaussian needs to be near the center
                if popt[0] > (0.5 * cvalue) and abs(popt[1]) < max(3, largest_deviation_from_center) :
                    if False:
                        plt.scatter(actualprofile[:,0],actualprofile[:,1])
                        plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *popt),color = 'r')
                        plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                        plt.show()

                    sources.append([cx,cy,cvalue])
        except:
            pass

# Keep top 200
sources=np.asarray(sources)
if len(sources) > 200:
    sources=sources[:200,:]

print ("Constructor " + str(time.time()-googtime))
googtime=time.time()
failed=True

if len(sources) >= 5:




    print ("Attempting WSL astrometry.net fit")

    wslfilename=cal_path + 'wsltemp' + str(time.time()).replace('.','') +'.fits'



    # save out the source list to a textfile for wsl fit
    sources={'x': sources[:,0],'y': sources[:,1],'flux': sources[:,2]}

    sources=Table(sources)

    sources.write(wslfilename)

    # recombobulate to access through the wsl filesystem
    realwslfilename=wslfilename.split(':')
    realwslfilename[0]=realwslfilename[0].lower()
    realwslfilename='/mnt/'+ realwslfilename[0] + realwslfilename[1]


    # Pick pixel scale range
    if pixscale == None:
        low_pixscale= 0.05
        high_pixscale=10.0
    else:
        low_pixscale = 0.9 * pixscale
        high_pixscale = 1.1 * pixscale


    astoptions = '--crpix-center --tweak-order 2 --x-column y --y-column x --width ' + str(hdufocusdata.shape[0]) +' --height ' + str(hdufocusdata.shape[1]) + ' --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius 20 --cpulimit 30 --overwrite --no-verify --no-plots'

    print (astoptions)

    os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))


    # If successful, then a file of the same name but ending in solved exists.
    if os.path.exists(wslfilename):
        print ("IT EXISTS! WCS SUCCESSFUL!")
        wcs_header=fits.open(wslfilename.replace('.fits','.wcs'))[0].header
        # wcsheader[0].header['CRVAL1']/15
        # wcsheader[0].header['CRVAL2']
        # wcsheader[0].header['CD1_2'] * 3600
        solve={}
        solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
        solve["dec_j2000_degrees"] = wcs_header['CRVAL2']
        solve["arcsec_per_pixel"] = abs(wcs_header['CD1_2'] *3600)

        if binnedtwo:
            solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
        elif binnedthree:
            solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/3
        print (solve)

    else:
        solve = 'error'


    temp_files_to_remove=glob.glob(cal_path + 'wsltemp*')
    for f in temp_files_to_remove:
        try:
            os.remove(f)
        except:
            pass


    #breakpoint()

        # if not pixscale == None:# or np.isnan(pixscale):
        #     # Get size of original image
        #     xpixelsize = hdufocusdata.shape[0]
        #     ypixelsize = hdufocusdata.shape[1]
        #     shape = (xpixelsize, ypixelsize)

        #     # Make blank synthetic image with a sky background
        #     synthetic_image = np.zeros([xpixelsize, ypixelsize])
        #     synthetic_image = synthetic_image + 200

        #     #Bullseye Star Shape
        #     modelstar = [
        #                 [ .01 , .05 , 0.1 , 0.2,  0.1, .05, .01],
        #                 [ .05 , 0.1 , 0.2 , 0.4,  0.2, 0.1, .05],
        #                 [ 0.1 , 0.2 , 0.4 , 0.8,  0.4, 0.2, 0.1],
        #                 [ 0.2 , 0.4 , 0.8 , 1.2,  0.8, 0.4, 0.2],
        #                 [ 0.1 , 0.2 , 0.4 , 0.8,  0.4, 0.2, 0.1],
        #                 [ .05 , 0.1 , 0.2 , 0.4,  0.2, 0.1, .05],
        #                 [ .01 , .05 , 0.1 , 0.2,  0.1, .05, .01]

        #                 ]

        #     modelstar=np.array(modelstar)

        #     # Add bullseye stars to blank image
        #     for addingstar in sources:
        #         x = round(addingstar[1] -1)
        #         y = round(addingstar[0] -1)
        #         peak = int(addingstar[2])
        #         # Add star to numpy array as a slice
        #         try:
        #             synthetic_image[y-3:y+4,x-3:x+4] += peak*modelstar
        #         except Exception as e:
        #             print (e)

        #     # Make an int16 image for planewave solver
        #     hdufocusdata = np.array(synthetic_image, dtype=np.int32)
        #     hdufocusdata[hdufocusdata < 0] = 200
        #     hdufocus = fits.PrimaryHDU()
        #     hdufocus.data = hdufocusdata
        #     hdufocus.header = hduheader
        #     hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
        #     hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
        #     hdufocus.writeto(cal_path + 'platesolvetemp.fits', overwrite=True, output_verify='silentfix')

        #     try:
        #         hdufocus.close()
        #     except:
        #         pass
        #     del hdufocusdata
        #     del hdufocus

        #     # First try with normal pixscale
        #     failed = False
        #     args = [
        #         PS3CLI_EXE,
        #         cal_path + 'platesolvetemp.fits',
        #         str(pixscale),
        #         output_file_path,
        #         catalog_path
        #     ]

        #     process = Popen(
        #             args,
        #             stdout=None,
        #             stderr=PIPE
        #             )
        #     (stdout, stderr) = process.communicate()  # Obtain stdout and stderr output from the wcs tool
        #     exit_code = process.wait() # Wait for process to complete and obtain the exit code

        #     time.sleep(1)
        #     process.kill()

        #     try:
        #         solve = parse_platesolve_output(output_file_path)
        #         print (solve['arcsec_per_pixel'])
        #         if binnedtwo:
        #             solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/2
        #         elif binnedthree:
        #             solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/3
        #     except:
        #         failed=True


        #     if failed:
        #         failed=False

        #         # Try again with a lower pixelscale... yes it makes no sense
        #         # But I didn't write PS3.exe ..... but it works (MTF)
        #         args = [
        #             PS3CLI_EXE,
        #             cal_path + 'platesolvetemp.fits',
        #             str(float(pixscale)/2.0),
        #             output_file_path,
        #             catalog_path
        #         ]

        #         process = Popen(
        #                 args,
        #                 stdout=None,
        #                 stderr=PIPE
        #                 )
        #         (stdout, stderr) = process.communicate()  # Obtain stdout and stderr output from the wcs tool
        #         exit_code = process.wait() # Wait for process to complete and obtain the exit code
        #         time.sleep(1)
        #         process.kill()

        #         print (stdout)
        #         print (stderr)

        #         try:
        #             solve = parse_platesolve_output(output_file_path)
        #             print (solve['arcsec_per_pixel'])
        #             if binnedtwo:
        #                 solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/2
        #             elif binnedthree:
        #                 solve['arcsec_per_pixel']=float(solve['arcsec_per_pixel'])/3
        #         except:
        #             failed=True

        # # if unknown pixelscale do a search
        # print ("failed?")
        # print (failed)
        # if failed or pixscale == None:

        #     #from astropy.table import Table
        #     from astroquery.astrometry_net import AstrometryNet
        #     AstrometryNet().api_key = 'pdxlsqwookogoivt'
        #     AstrometryNet().key = 'pdxlsqwookogoivt'
        #     ast = AstrometryNet()
        #     ast.api_key = 'pdxlsqwookogoivt'
        #     ast.key = 'pdxlsqwookogoivt'

        #     if pixscale == None:
        #         scale_lower=0.04
        #         scale_upper=8.0
        #     elif binnedtwo:
        #         scale_lower=0.9* pixscale*2
        #         scale_upper=1.1* pixscale*2
        #     elif binnedthree:
        #         scale_lower=0.9* pixscale*3
        #         scale_upper=1.1* pixscale*3
        #     else:
        #         scale_lower=0.9* pixscale
        #         scale_upper=1.1* pixscale

        #     image_width = fx
        #     image_height = fy

        #     # If searching for the first pixelscale,
        #     # Then wait for a LONG time to get it.
        #     # with a wider range
        #     try:
        #         if pixscale == None:# or np.isnan(pixscale):
        #             wcs_header = ast.solve_from_source_list(pointvalues[:,0], pointvalues[:,1],
        #                                                     image_width, image_height, crpix_center=True, center_dec= pointing_dec, scale_lower=scale_lower, scale_upper=scale_upper, scale_units='arcsecperpix', center_ra = pointing_ra*15,radius=30.0,
        #                                                     solve_timeout=1200)
        #         else:
        #             wcs_header = ast.solve_from_source_list(pointvalues[:,0], pointvalues[:,1],
        #                                                     image_width, image_height, crpix_center=True, center_dec= pointing_dec, scale_lower=scale_lower, scale_upper=scale_upper, scale_units='arcsecperpix', center_ra = pointing_ra*15,radius=12.0,
        #                                                     solve_timeout=60)
        #     except:
        #         print ("a.net timed out or failed")
        #         wcs_header={}

        #     print (wcs_header)
        #     print (len(wcs_header))

        #     if wcs_header=={}:
        #         solve = 'error'
        #     else:
        #         solve={}
        #         solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
        #         solve["dec_j2000_degrees"] = wcs_header['CRVAL2']
        #         solve["arcsec_per_pixel"] = wcs_header['CD1_2'] *3600

        #         if binnedtwo:
        #             solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
        #         elif binnedthree:
        #             solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/3

else:
    solve = 'error'


print (cal_path+ 'platesolve.pickle')


#sys.exit()

pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))


try:
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass

os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

time.sleep(1)


try:
    os.remove(cal_path + 'platesolvetemp.fits')
except:
    pass
try:
    os.remove(output_file_path)
except:
    pass


print (solve)
print ("solver: " +str(time.time()-googtime))


def add_margin(pil_img, top, right, bottom, left, color):
    width, height = pil_img.size
    new_width = width + right + left
    new_height = height + top + bottom
    result = Image.new(pil_img.mode, (new_width, new_height), color)
    result.paste(pil_img, (left, top))
    return result

def mid_stretch_jpeg(data):
    """
    This product is based on software from the PixInsight project, developed by
    Pleiades Astrophoto and its contributors (http://pixinsight.com/).

    And also Tim Beccue with a minor flourishing/speedup by Michael Fitzgerald.
    """
    target_bkg=0.25
    shadows_clip=-1.25

    """ Stretch the image.

    Args:
        data (np.array): the original image data array.

    Returns:
        np.array: the stretched image data
    """

    try:
        data = data / np.max(data)
    except:
        data = data    #NB this avoids div by 0 is image is a very flat bias


    """Return the average deviation from the median.

    Args:
        data (np.array): array of floats, presumably the image data
    """
    median = np.median(data.ravel())
    n = data.size
    avg_dev = np.sum( np.absolute(data-median) / n )
    c0 = np.clip(median + (shadows_clip * avg_dev), 0, 1)
    x= median - c0

    """Midtones Transfer Function

    MTF(m, x) = {
        0                for x == 0,
        1/2              for x == m,
        1                for x == 1,

        (m - 1)x
        --------------   otherwise.
        (2m - 1)x - m
    }

    See the section "Midtones Balance" from
    https://pixinsight.com/doc/tools/HistogramTransformation/HistogramTransformation.html

    Args:
        m (float): midtones balance parameter
                   a value below 0.5 darkens the midtones
                   a value above 0.5 lightens the midtones
        x (np.array): the data that we want to copy and transform.
    """
    shape = x.shape
    x = x.ravel()
    zeros = x==0
    halfs = x==target_bkg
    ones = x==1
    others = np.logical_xor((x==x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (target_bkg - 1) * x[others] / ((((2 * target_bkg) - 1) * x[others]) - target_bkg)
    m= x.reshape(shape)

    stretch_params = {
        "c0": c0,
        #"c1": 1,
        "m": m
    }

    m = stretch_params["m"]
    c0 = stretch_params["c0"]
    above = data >= c0

    # Clip everything below the shadows clipping point
    data[data < c0] = 0
    # For the rest of the pixels: apply the midtones transfer function
    x=(data[above] - c0)/(1 - c0)

    """Midtones Transfer Function

    MTF(m, x) = {
        0                for x == 0,
        1/2              for x == m,
        1                for x == 1,

        (m - 1)x
        --------------   otherwise.
        (2m - 1)x - m
    }

    See the section "Midtones Balance" from
    https://pixinsight.com/doc/tools/HistogramTransformation/HistogramTransformation.html

    Args:
        m (float): midtones balance parameter
                   a value below 0.5 darkens the midtones
                   a value above 0.5 lightens the midtones
        x (np.array): the data that we want to copy and transform.
    """
    shape = x.shape
    x = x.ravel()
    zeros = x==0
    halfs = x==m
    ones = x==1
    others = np.logical_xor((x==x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (m - 1) * x[others] / ((((2 * m) - 1) * x[others]) - m)
    data[above]= x.reshape(shape)

    return data



if solve == 'error':
    pointing_image = mid_stretch_jpeg(pointing_image)
    final_image = Image.fromarray(pointing_image)

    ix, iy = final_image.size
    if iy == ix:
        final_image = final_image.resize(
            (900, 900)
        )
    else:
        if False:
            final_image = final_image.resize(

                (int(900 * iy / ix), 900)

            )
        else:
            final_image = final_image.resize(

                (900, int(900 * iy / ix))

            )

    final_image.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
    os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)



if solve != 'error' and pointing_exposure and not pixscale == None:


    pointing_image = mid_stretch_jpeg(pointing_image)

    solved_ra = solve["ra_j2000_hours"]
    solved_dec = solve["dec_j2000_degrees"]
    solved_arcsecperpixel = solve["arcsec_per_pixel"]



    RA_where_it_actually_is=solved_ra
    DEC_where_it_actually_is=solved_dec

    #make a fake header to create the WCS object
    tempheader = fits.PrimaryHDU()
    tempheader=tempheader.header
    tempheader['CTYPE1'] = 'RA---TAN'
    tempheader['CTYPE2'] = 'DEC--TAN'
    tempheader['CUNIT1'] = 'deg'
    tempheader['CUNIT2'] = 'deg'
    tempheader['CRVAL1'] = RA_where_it_actually_is * 15.0
    tempheader['CRVAL2'] = DEC_where_it_actually_is
    tempheader['CRPIX1'] = int(pointing_image.shape[0] / 2)
    tempheader['CRPIX2'] = int(pointing_image.shape[1] / 2)
    tempheader['NAXIS'] = 2
    tempheader['CDELT1'] = float(pixscale) / 3600
    tempheader['CDELT2'] = float(pixscale) / 3600


    # Size of field in degrees
    x_deg_field_size=(float(pixscale) / (3600)) * pointing_image.shape[0]
    y_deg_field_size=(float(pixscale) / (3600)) * pointing_image.shape[1] / cos(radians(DEC_where_it_actually_is ))

    print (x_deg_field_size)
    print (y_deg_field_size)

    xfig=9
    yfig=9*(pointing_image.shape[0]/pointing_image.shape[1])
    aspect=1/(pointing_image.shape[0]/pointing_image.shape[1])
    print (pointing_image.shape[0]/pointing_image.shape[1])

    # Create a temporary WCS
    # Representing where it actually is.
    wcs=WCS(header=tempheader)

    plt.rcParams["figure.facecolor"] = 'black'
    plt.rcParams["text.color"] = 'yellow'
    plt.rcParams["xtick.color"] = 'yellow'
    plt.rcParams["ytick.color"] = 'yellow'
    plt.rcParams["axes.labelcolor"] = 'yellow'
    plt.rcParams["axes.titlecolor"] = 'yellow'

    plt.rcParams['figure.figsize'] = [xfig, yfig]
    ax = plt.subplot(projection=wcs, facecolor='black')

    #fig.set_facecolor('black')
    ax.set_facecolor('black')
    ax.imshow(pointing_image, origin='lower', cmap='gray')
    ax.grid(color='yellow', ls='solid')
    ax.set_xlabel('Right Ascension')
    ax.set_ylabel('Declination')


    print ([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is])

    ax.plot([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is],  linestyle='dashed',color='green',
          linewidth=2, markersize=12,transform=ax.get_transform('fk5'))
    # #ax.set_autoscale_on(False)

    # ax.plot([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is],  linestyle='dashed',color='white',
    #       linewidth=2, markersize=12,transform=ax.get_transform('fk5'))


    # This should point to the center of the box.
    ax.scatter(target_ra * 15, target_dec, transform=ax.get_transform('icrs'), s=300,
                edgecolor='red', facecolor='none')

    # ax.scatter(target_ra * 15, target_dec, transform=ax.get_transform('icrs'), s=300,
    #             edgecolor='white', facecolor='none')


    # This should point to the center of the current image
    ax.scatter(RA_where_it_actually_is * 15, DEC_where_it_actually_is, transform=ax.get_transform('icrs'), s=300,
                edgecolor='white', facecolor='none')

    # This should point to the where the telescope is reporting it is positioned.
    ax.scatter(pointing_ra * 15, pointing_dec, transform=ax.get_transform('icrs'), s=300,
                edgecolor='lime', facecolor='none')

    # r = Quadrangle((target_ra * 15 - 0.5 * y_deg_field_size, target_dec - 0.5 * x_deg_field_size)*u.deg, y_deg_field_size*u.deg, x_deg_field_size*u.deg,
    #                 edgecolor='red', facecolor='none',
    #                 transform=ax.get_transform('icrs'))

    r = Quadrangle((target_ra * 15 - 0.5 * y_deg_field_size, target_dec - 0.5 * x_deg_field_size)*u.deg, y_deg_field_size*u.deg, x_deg_field_size*u.deg,
                    edgecolor='red', facecolor='none',
                    transform=ax.get_transform('icrs'))


    ax.add_patch(r)
    # ax.axes.set_aspect(aspect)
    # plt.axis('scaled')
    # plt.gca().set_aspect(aspect)

    # breakpoint()
    # plt.canvas.draw()
    # temp_canvas = plt.canvas
    # plt.close()
    # pil_image=Image.frombytes('RGB', temp_canvas.get_width_height(),  temp_canvas.tostring_rgb())

    # pil_image.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
    # os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)

    plt.savefig(jpeg_filename.replace('.jpg','matplotlib.png'), dpi=100, bbox_inches='tight', pad_inches=0)


    im = Image.open(jpeg_filename.replace('.jpg','matplotlib.png'))

    # Get amount of padding to add
    fraction_of_padding=(im.size[0]/im.size[1])/aspect
    padding_added_pixels=int(((fraction_of_padding * im.size[1])- im.size[1])/2)
    if padding_added_pixels > 0:
        im=add_margin(im,padding_added_pixels,0,padding_added_pixels,0,(0,0,0))

    im=im.convert('RGB')

    im.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
    os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)
    try:
        os.remove(jpeg_filename.replace('.jpg','matplotlib.jpg'))
    except:
        pass

    try:
        os.remove(jpeg_filename.replace('.jpg','matplotlib.png'))
    except:
        pass


