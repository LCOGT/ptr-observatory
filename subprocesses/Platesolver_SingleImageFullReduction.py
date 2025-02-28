# -*- coding: utf-8 -*-
"""
This is the main platesolve sub-process for solving frames.

Platesolving is relatively costly in time, so we don't solve each frame.
It is also not necessary - the platesolve we do is FAST (for windows)
but only spits out RA, Dec, Pixelscale and rotation. Which is actually all
we need to monitor pointing and keep scopes dead on target.

There is a windswept and interesting way that platesolve frames lead to
slight nudges during observing, but they are all triggered from values
from this subprocess...

"""
import sys


import pickle
# import copy
# from astropy.nddata import block_reduce
import numpy as np
#import sep
import glob
#from astropy.nddata.utils import extract_array
from astropy.io import fits
#from subprocess import Popen, PIPE
import os
#from pathlib import Path
#from os import getcwd
import time
from astropy.utils.exceptions import AstropyUserWarning
#from astropy.table import Table
import warnings
import traceback
#import bottleneck as bn
from math import cos, radians
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
import matplotlib.pyplot as plt
#import math
from PIL import Image#, ImageOps
#from scipy.stats import binned_statistic
from astropy.wcs import WCS
from astropy import units as u
from astropy.visualization.wcsaxes import Quadrangle
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)

import subprocess



input_psolve_info=pickle.load(sys.stdin.buffer)
#input_psolve_info=pickle.load(open('testplatesolvepickle','rb'))

hdufocusdata=input_psolve_info[0]
hduheader=input_psolve_info[1]
pixscale=input_psolve_info[2]
is_osc=input_psolve_info[3]
filepath=input_psolve_info[4]
filebase=input_psolve_info[5]
pointing_ra=input_psolve_info[6]
pointing_dec=input_psolve_info[7]
cpu_limit=90
# cal_path=input_psolve_info[2]
# cal_name=input_psolve_info[3]
# frame_type=input_psolve_info[4]
# time_platesolve_requested=input_psolve_info[5]
# 
# pointing_ra=input_psolve_info[7]
# pointing_dec=input_psolve_info[8]
# platesolve_crop=input_psolve_info[9]
# bin_for_platesolve=input_psolve_info[10]
# platesolve_bin_factor=input_psolve_info[11]
# image_saturation_level = input_psolve_info[12]
# readnoise=input_psolve_info[13]
# minimum_realistic_seeing=input_psolve_info[14]
# is_osc=input_psolve_info[15]
# useastrometrynet=input_psolve_info[16]
# pointing_exposure=input_psolve_info[17]
# jpeg_filename_with_full_path=input_psolve_info[18]
# target_ra=input_psolve_info[19]
# target_dec=input_psolve_info[20]

# try:
#     os.remove(cal_path + 'platesolve.pickle')
# except:
#     pass

# try:
#     os.remove(cal_path + 'platesolve.temppickle')
# except:
#     pass

# try:
#     if np.isnan(pixscale):
#         pixscale=None
# except:
#     pixscale=None


# # init
# binnedtwo=False
# binnedthree=False

# print ("Pixelscale")
# print (pixscale)


# Check we are working in unit16
if not hdufocusdata.dtype == np.uint16:
    raised_array=hdufocusdata - np.nanmin(hdufocusdata)
    hdufocusdata = np.maximum(raised_array,0).astype(np.uint16)
    del raised_array



# # Keep a copy of the normal image if this is a pointing image
# # This is needed to make the plot right at the end if successful
# pointing_image=copy.deepcopy(hdufocusdata)

googtime=time.time()

# If this is an osc image, then interpolate so it is just the green filter image of the same size.
if is_osc:
    ########## Need to split the file into four
    print ("do osc stuff")



wslfilename=filepath + filebase
# recombobulate to access through the wsl filesystem
realwslfilename=wslfilename.split(':')
realwslfilename[0]=realwslfilename[0].lower()
realwslfilename='/mnt/'+ realwslfilename[0] + realwslfilename[1]


low_pixscale = 0.97 * pixscale
high_pixscale = 1.03 * pixscale
initial_radius=2

print ("Just before solving: " +str(time.time()-googtime))

# Save an image to the disk to use with source-extractor
# We don't need accurate photometry, so integer is fine.
hdufocus = fits.PrimaryHDU()
hdufocus.data = hdufocusdata#.astype(np.uint16)#.astype(np.float32)
hdufocus.header = hduheader
hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
hdufocus.writeto(wslfilename, overwrite=True, output_verify='silentfix')




# This is the full routine from the pipeline

# run source extractor on image
tempprocess = subprocess.Popen(
    ['source-extractor', astromfitsfile, '-c', codedir +'/photometryparams/default.sexfull', '-PARAMETERS_NAME', str(codedir +'/photometryparams/default.paramastrom'),
     '-CATALOG_NAME', str(tempdir + '/test.cat'), '-SATUR_LEVEL', str(65535), '-GAIN', str(1), '-BACKPHOTO_TYPE','LOCAL', '-DETECT_THRESH', str(1.0), '-ANALYSIS_THRESH',str(1.0),
     '-SEEING_FWHM', str(2.0), '-FILTER_NAME', str(codedir +'/photometryparams/sourceex_convs/gauss_2.0_5x5.conv')], stdin=subprocess.PIPE,
    stdout=subprocess.PIPE, bufsize=0)
tempprocess.wait() 
    
# Read the ASCII catalog
#ascii_catalog = ascii.read(tempdir+ "/test.cat", comment="#")
acatalog = Table.read(tempdir+"/test.cat", format='ascii')
# #Reject wacky values
# acatalog=acatalog[acatalog['FWHM_IMAGE'] > fwhmlimit]
# Reject poor  ( <10 SNR) sources
acatalog=acatalog[acatalog['FLUX_AUTO']/acatalog['FLUXERR_AUTO'] > 10]

#breakpoint()
# Write out to fits
#ascii_catalog.write(tempdir+ "/test.fits", format="fits", overwrite=True)
acatalog.write(tempdir+ "/test.fits", format="fits", overwrite=True)

fwhm_values = acatalog['FWHM_IMAGE']  # Extract FWHM values

# Remove NaN and zero values
fwhm_values = fwhm_values[~numpy.isnan(fwhm_values)]  # Remove NaN
fwhm_values = fwhm_values[fwhm_values > 0]  # Remove zero values

# Apply sigma clipping with a 3-sigma threshold
clipped_fwhm = sigma_clip(fwhm_values, sigma=3, maxiters=5, cenfunc='median', stdfunc='std')

# Get the clipped values (remove masked elements)
filtered_fwhm = clipped_fwhm[~clipped_fwhm.mask]

fwhmpix=bn.nanmedian(filtered_fwhm)
fwhmstd=bn.nanstd(filtered_fwhm)


picklefwhm={}
try:



    # try:
    picklefwhm["SKYLEVEL"] = (bn.nanmedian(cleanhdu.data), "Sky Level without pedestal")
    # except:
    #     picklefwhm["SKYLEVEL"] = -9999
    # try:
    picklefwhm["FWHM"] = (fwhmpix, 'FWHM in pixels')
    picklefwhm["FWHMpix"] = (fwhmpix, 'FWHM in pixels')
    # except:
    #     picklefwhm["FWHM"] = (-99, 'FWHM in pixels')
    #     picklefwhm["FWHMpix"] = (-99, 'FWHM in pixels')

    # try:
    picklefwhm["FWHMasec"] = (pixscale*fwhmpix, 'FWHM in arcseconds')
    # except:
    #     picklefwhm["FWHMasec"] = (-99, 'FWHM in arcseconds')
    # try:
    picklefwhm["FWHMstd"] = (pixscale*fwhmstd, 'FWHM standard deviation in arcseconds')
    # except:

    # picklefwhm["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')

    # try:
    picklefwhm["NSTARS"] = ( len(filtered_fwhm), 'Number of star-like sources in image')
    # except:
    #     picklefwhm["NSTARS"] = ( -99, 'Number of star-like sources in image')

    with open(file.split('/')[-1].split('PIXSCALE')[-1].replace('.npy','.fwhm'), 'wb') as fp:
        pickle.dump(picklefwhm, fp)
        #print('dictionary saved successfully to file')

except:
    print(traceback.format_exc())
    
    picklefwhm["SKYLEVEL"] = (bn.nanmedian(cleanhdu.data), "Sky Level without pedestal")

    picklefwhm["FWHM"] = (-99, 'FWHM in pixels')
    picklefwhm["FWHMpix"] = (-99, 'FWHM in pixels')
    picklefwhm["FWHMasec"] = (-99, 'FWHM in arcseconds')
    picklefwhm["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')
    picklefwhm["NSTARS"] = ( len(filtered_fwhm ), 'Number of star-like sources in image')
    


with open(file.split('/')[-1].split('PIXSCALE')[-1].replace('.npy','.fwhm'), 'wb') as fp: # os.getcwd() + '/' + file.replace('.fits', '.wcs').replace('.fit', '.fwhm')
    pickle.dump(picklefwhm, fp)



# Use tweak order 2 in smaller fields of view and tweak order 3 in larger fields.
sizewidest= max(imageh*pixscale, imagew*pixscale) / 3600

if sizewidest > 1.0:
    tweakorder=[3,2]
else:
    tweakorder=[2,3]

# Try once with tweak-order 2   
#os.system("/usr/local/astrometry/bin/solve-field -D " + str(tempdir) + " --use-source-extractor --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 90 --depth 1-100 --overwrite --no-verify --no-plots " + str(astromfitsfile))
os.system("/usr/local/astrometry/bin/solve-field " + str(tempdir + '/' 'test.fits') +" -D " + str(tempdir) + " --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )

#breakpoint()

if os.path.exists(tempdir + '/test.wcs'):
    print("A successful solve for " + astromfitsfile)
    os.remove(astromfitsfile)
    shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + astromfitsfile.replace('.fits', '.wcs').replace('.fit', '.wcs'))
# os.remove(file)
else:
    wait_for_resources()
    # Try once with tweak-order 3    
    os.system("/usr/local/astrometry/bin/solve-field " + str(tempdir + '/' 'test.fits') +" -D " + str(tempdir) + " --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[1]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )
    
    if os.path.exists(tempdir + '/test.wcs'):
        print("A successful solve for " + astromfitsfile)
        os.remove(astromfitsfile)
        shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + astromfitsfile.replace('.fits', '.wcs').replace('.fit', '.wcs'))
    # os.remove(file)
    else:
        wait_for_resources()
        # Try once with tweak-order 4    
        os.system("/usr/local/astrometry/bin/solve-field " + str(tempdir + '/' 'test.fits') +" -D " + str(tempdir) + " --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (4) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )
        
        if os.path.exists(tempdir + '/test.wcs'):
            print("A successful solve for " + astromfitsfile)
            os.remove(astromfitsfile)
            shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + astromfitsfile.replace('.fits', '.wcs').replace('.fit', '.wcs'))
        # os.remove(file)
        else:
            
            ### HERE WE TRY WITH THE SIMPLER PHOTOMETRY
            
            
            # Try once with tweak-order 4
            os.system("/usr/local/astrometry/bin/solve-field -D " + str(
                tempdir) + " --crpix-center --tweak-order " +str (tweakorder[0]) + "  --x-column y --y-column x --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(
                pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(
                RAest) + "   --dec " + str(
                DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " + str(file))

            if os.path.exists(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs')):
                print("A successful solve for " + file)
                os.remove(file)
                shutil.move(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'), os.getcwd() + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'))

            # If fail use tweak-order 3
            else:
                wait_for_resources()
                os.system("/usr/local/astrometry/bin/solve-field -D " + str(
                    tempdir) + " --crpix-center --tweak-order " +str (tweakorder[1]) + "  --x-column y --y-column x --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(
                    pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(
                    RAest) + "   --dec " + str(
                    DECest) + " --radius 10 --cpulimit 300  --depth 1-100 --overwrite --no-verify --no-plots " + str(file))

                if os.path.exists(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs')):
                    print("A successful solve for " + file)
                    os.remove(file)
                    shutil.move(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'), os.getcwd() + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'))

                # If fail use tweak-order 2
                else:
                    wait_for_resources()
                    os.system("/usr/local/astrometry/bin/solve-field -D " + str(
                        tempdir) + " --crpix-center --tweak-order 4 --x-column y --y-column x --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(
                        pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(
                        RAest) + "   --dec " + str(
                        DECest) + " --radius 10 --cpulimit 300  --depth 1-100 --overwrite --no-verify --no-plots " + str(file))

                    if os.path.exists(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs')):
                        print("A successful solve for " + file)
                        os.remove(file)
                        shutil.move(tempdir + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'), os.getcwd() + '/' + file.replace('.fits', '.wcs').replace('.fit', '.wcs'))

                    # If fail use tweak-order 0
                    else:
                        
                        print("A failed solve for " + file)
                        os.remove(file)
                



















# run again

astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius ' + str(initial_radius) + ' --cpulimit ' +str(cpu_limit) + ' --overwrite --no-verify --no-plots'

print (astoptions)

os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))

# If successful, then a file of the same name but ending in solved exists.
if os.path.exists(wslfilename.replace('.fits','.wcs')):
    print ("IT EXISTS! WCS SUCCESSFUL!")
    wcs_header=fits.open(wslfilename.replace('.fits','.wcs'))[0].header
    solve={}
    solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
    solve["dec_j2000_degrees"] = wcs_header['CRVAL2']

    wcs = WCS(wcs_header)

    # Get the CD matrix or CDELT values
    cd = wcs.pixel_scale_matrix
    pixel_scale_deg = np.sqrt(np.sum(cd**2, axis=0))  # in degrees per pixel
    solve["arcsec_per_pixel"]  = pixel_scale_deg * 3600  # Convert to arcseconds per pixel

    solve["arcsec_per_pixel"]  = solve["arcsec_per_pixel"][0]

else:

    print ("FAILED NORMAL, TRYING HAIL MARY ATTEMPT")
    # Remove the previous attempt which was just a table fits
    temp_files_to_remove=glob.glob(cal_path + 'wsltemp*')
    for f in temp_files_to_remove:
        try:
            os.remove(f)
        except:
            pass

    # run for the first time

    astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius 20 --cpulimit ' +str(cpu_limit * 3) + ' --overwrite --no-verify --no-plots'

    print (astoptions)

    os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))

    # If successful, then a file of the same name but ending in solved exists.
    if os.path.exists(wslfilename.replace('.fits','.wcs')):
        print ("IT EXISTS! WCS SUCCESSFUL!")
        wcs_header=fits.open(wslfilename.replace('.fits','.wcs'))[0].header
        solve={}
        solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
        solve["dec_j2000_degrees"] = wcs_header['CRVAL2']

        wcs = WCS(wcs_header)

        # Get the CD matrix or CDELT values
        cd = wcs.pixel_scale_matrix
        pixel_scale_deg = np.sqrt(np.sum(cd**2, axis=0))  # in degrees per pixel
        solve["arcsec_per_pixel"]  = pixel_scale_deg * 3600  # Convert to arcseconds per pixel

        solve["arcsec_per_pixel"]  = solve["arcsec_per_pixel"][0]

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



##################################

print (cal_path+ 'platesolve.pickle')


#sys.exit()

try:
    os.remove(cal_path + 'platesolve.temppickle')
except:
    pass

pickle.dump(solve, open(cal_path + 'platesolve.temppickle', 'wb'))


try:
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass

os.rename(cal_path + 'platesolve.temppickle',cal_path + 'platesolve.pickle')

time.sleep(0.25)

try:
    os.remove(cal_path + 'platesolve.temppickle')
except:
    pass

time.sleep(1)


print (solve)
print ("solver: " +str(time.time()-googtime))


def add_margin(pil_img, top, right, bottom, left, color):
    width, height = pil_img.size
    new_width = width + right + left
    new_height = height + top + bottom
    result = Image.new(pil_img.mode, (new_width, new_height), color)
    result.paste(pil_img, (left, top))
    return result


def resize_array(arr, max_size):
    # Calculate the downscaling factor for each axis
    scale = min(max_size / arr.shape[0], max_size / arr.shape[1])
    new_shape = (int(arr.shape[0] * scale), int(arr.shape[1] * scale))

    # Calculate the step size for downsampling
    row_step = arr.shape[0] // new_shape[0]
    col_step = arr.shape[1] // new_shape[1]

    # Downsample by taking the mean over blocks
    resized_array = arr[:row_step * new_shape[0], :col_step * new_shape[1]].reshape(
        new_shape[0], row_step, new_shape[1], col_step
    ).mean(axis=(1, 3))

    return resized_array


if solve == 'error':

    max_size=1000
    pointing_image  = resize_array(pointing_image , max_size)

    pointing_image = mid_stretch_jpeg(pointing_image)
    final_image = Image.fromarray(pointing_image).convert("L")

    # Convert grayscale to RGB
    red_image = Image.new("RGB", final_image.size)
    for x in range(final_image.width):
        for y in range(final_image.height):
            grayscale_value = final_image.getpixel((x, y))
            red_image.putpixel((x, y), (grayscale_value, 0, 0))  # Map grayscale to red

    final_image=red_image

    # ix, iy = final_image.size
    # if iy == ix:
    #     final_image = final_image.resize(
    #         (900, 900)
    #     )
    # else:
    #     if False:
    #         final_image = final_image.resize(

    #             (int(900 * iy / ix), 900)

    #         )
    #     else:
    #         final_image = final_image.resize(

    #             (900, int(900 * iy / ix))

    #         )

    final_image = final_image.convert('RGB')

    try:
        final_image.save(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
        os.rename(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'),jpeg_filename_with_full_path)
    except:
        print ("problem in saving, likely trying to overwrite an existing file.")
        print(traceback.format_exc())


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

    # pil_image.save(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
    # os.rename(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'),jpeg_filename_with_full_path)

    plt.savefig(jpeg_filename_with_full_path.replace('.jpg','matplotlib.png'), dpi=100, bbox_inches='tight', pad_inches=0)


    im = Image.open(jpeg_filename_with_full_path.replace('.jpg','matplotlib.png'))

    # Get amount of padding to add
    fraction_of_padding=(im.size[0]/im.size[1])/aspect
    padding_added_pixels=int(((fraction_of_padding * im.size[1])- im.size[1])/2)
    if padding_added_pixels > 0:
        im=add_margin(im,padding_added_pixels,0,padding_added_pixels,0,(0,0,0))

    im=im.convert('RGB')

    try:
        im.save(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
        os.rename(jpeg_filename_with_full_path.replace('.jpg','temp.jpg'),jpeg_filename_with_full_path)
    except:
        print ("tried to save a jpeg when there is already a jpge")
        print(traceback.format_exc())

    try:
        os.remove(jpeg_filename_with_full_path.replace('.jpg','matplotlib.jpg'))
    except:
        pass

    try:
        os.remove(jpeg_filename_with_full_path.replace('.jpg','matplotlib.png'))
    except:
        pass


