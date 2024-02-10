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
from astropy.table import Table
from astropy.io import fits
from subprocess import Popen, PIPE
import os
from pathlib import Path
from os import getcwd
import time
from astropy.utils.exceptions import AstropyUserWarning
import warnings
from colour_demosaicing import (
    demosaicing_CFA_Bayer_bilinear,  # )#,
    # demosaicing_CFA_Bayer_Malvar2004,
    demosaicing_CFA_Bayer_Menon2007)
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)

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

# If OSC, fill in quickly bilinearly
if is_osc:
    #hdufocusdata=demosaicing_CFA_Bayer_bilinear(hdufocusdata, 'RGGB')[:,:,1]
    #hdufocusdata=hdufocusdata.astype("float32")
    hdufocusdata=block_reduce(hdufocusdata,2,func=np.nanmean)
    pixscale=pixscale*2

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

focusimg = np.array(
    hdufocusdata, order="C"
)


# Some of these are liberated from BANZAI
bkg = sep.Background(focusimg, bw=32, bh=32, fw=3, fh=3)
bkg.subfrom(focusimg)
ix, iy = focusimg.shape

sep.set_extract_pixstack(int(ix*iy - 1))

#This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
# to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
# Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
minarea= -9.2421 * (pixscale*platesolve_bin_factor) + 16.553
if minarea < 5:  # There has to be a min minarea though!
    minarea = 5

sources = sep.extract(
    focusimg, 3, err=bkg.globalrms, minarea=minarea
)

sources = Table(sources)
sources = sources[sources['flag'] < 8]
sources = sources[sources["peak"] < 0.8 * image_saturation_level]
sources = sources[sources["cpeak"] < 0.8 * image_saturation_level]
sources = sources[sources["flux"] > 1000]
sources = sources[sources["x"] < iy -50]
sources = sources[sources["x"] > 50]
sources = sources[sources["y"] < ix - 50]
sources = sources[sources["y"] > 50]

# BANZAI prune nans from table
nan_in_row = np.zeros(len(sources), dtype=bool)
for col in sources.colnames:
    nan_in_row |= np.isnan(sources[col])
sources = sources[~nan_in_row]

# Calculate the ellipticity (Thanks BANZAI)

sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])
sources = sources[sources['ellipticity'] < 0.4]  # Remove things that are not circular stars

# Calculate the kron radius (Thanks BANZAI)
kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
                                  sources['a'], sources['b'],
                                  sources['theta'], 6.0)
sources['flag'] |= krflag
sources['kronrad'] = kronrad

# Calculate uncertainty of image (thanks BANZAI)
uncertainty = float(readnoise) * np.ones(focusimg.shape,
                                         dtype=focusimg.dtype) / float(readnoise)

try:
    flux, fluxerr, flag = sep.sum_ellipse(focusimg, sources['x'], sources['y'],
                                      sources['a'], sources['b'],
                                      np.pi / 2.0, 2.5 * kronrad,
                                      subpix=1, err=uncertainty)
    sources['flux'] = flux
    sources['fluxerr'] = fluxerr
    sources['flag'] |= flag
    
except:
    pass



# sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
#                                      subpix=5)

sources['FWHM']=sources['kronrad'] * 2

#sources['FWHM'] = 2 * sources['FWHM']
# BANZAI prune nans from table
# nan_in_row = np.zeros(len(sources), dtype=bool)
# for col in sources.colnames:
#     nan_in_row |= np.isnan(sources[col])
# sources = sources[~nan_in_row]

sources = sources[sources['FWHM'] != 0]
#sources = sources[sources['FWHM'] > 0.5]
sources = sources[sources['FWHM'] > (1/pixscale)]
sources = sources[sources['FWHM'] < (np.nanmedian(sources['FWHM']) + (3 * np.nanstd(sources['FWHM'])))]

sources = sources[sources['flux'] > 0]
sources = sources[sources['flux'] < 1000000]




#breakpoint()
#breakpoint()

if len(sources) >= 5:


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

    # Add bullseye stars to blank image
    for addingstar in sources:
        x = round(addingstar['x'] -1)
        y = round(addingstar['y'] -1)
        peak = int(addingstar['peak'])
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

    try:
        hdufocus.close()
    except:
        pass
    del hdufocusdata
    del hdufocus


    try:
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
        failed = False
        time.sleep(1)
        process.kill()

        solve = parse_platesolve_output(output_file_path)
        if is_osc:
            solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2
        #breakpoint()

    except:
        failed = True
        process.kill()

    if failed:
        try:
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

            solve = parse_platesolve_output(output_file_path)
            if is_osc:
                solve['arcsec_per_pixel']=solve['arcsec_per_pixel']/2

        except:
            process.kill()
            solve = 'error'
    pickle.dump(solve, open(cal_path + 'platesolve.pickle', 'wb'))

    try:
        os.remove(cal_path + 'platesolvetemp.fits')
    except:
        pass
    try:
        os.remove(output_file_path)
    except:
        pass
else:
    solve = 'error'
    pickle.dump(solve, open(cal_path + 'platesolve.pickle', 'wb'))
    try:
        os.remove(cal_path + 'platesolvetemp.fits')
    except:
        pass
    try:
        os.remove(output_file_path)
    except:
        pass
    