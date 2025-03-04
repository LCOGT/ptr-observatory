# -*- coding: utf-8 -*-
"""
This is the main platesolve sub-process for solving frames for reduction purposes.

"""
import sys


import pickle
# import copy
# from astropy.nddata import block_reduce
import numpy as np
#import sep
#import glob
import shutil
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
#from math import cos, radians
# from colour_demosaicing import (
#     demosaicing_CFA_Bayer_bilinear,  # )#,
#     # demosaicing_CFA_Bayer_Malvar2004,
#     demosaicing_CFA_Bayer_Menon2007)
#import matplotlib.pyplot as plt
#import math
#from PIL import Image#, ImageOps
#from scipy.stats import binned_statistic
#from astropy.wcs import WCS
#from astropy import units as u
#from astropy.visualization.wcsaxes import Quadrangle
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)

import bottleneck as bn
from astropy.stats import sigma_clip

import subprocess
from astropy.table import Table

def save_xylist(astropy_table, output_filename="xylist.txt"):
    """
    Convert an Astropy Table with X_IMAGE, Y_IMAGE, and FLUX_AUTO columns
    into a whitespace-separated XY list file for Astrometry.net.
    
    Parameters:
    - astropy_table: Astropy Table containing 'X_IMAGE', 'Y_IMAGE', and 'FLUX_AUTO'.
    - output_filename: Name of the output file (default: xylist.txt).
    """
    # Extract relevant columns
    x = astropy_table['X_IMAGE']
    y = astropy_table['Y_IMAGE']
    flux = astropy_table['FLUX_AUTO']

    # Write to file
    with open(output_filename, "w") as f:
        for xi, yi, fi in zip(x, y, flux):
            f.write(f"{xi:.6f} {yi:.6f} {fi:.6f}\n")

    print(f"XY list saved as {output_filename}")

def save_sources_as_fits(astropy_table, output_filename="sources.fits"):
    """
    Convert an Astropy Table with X_IMAGE, Y_IMAGE, and FLUX_AUTO columns
    into a FITS binary table with proper data types for Astrometry.net.

    Parameters:
    - astropy_table: Astropy Table containing 'X_IMAGE', 'Y_IMAGE', 'FLUX_AUTO'.
    - output_filename: Name of the output FITS file (default: sources.fits).
    """
    # Ensure data types are compatible with FITS
    x = np.array(astropy_table['X_IMAGE'], dtype=np.float32)  # Convert to float32
    y = np.array(astropy_table['Y_IMAGE'], dtype=np.float32)  # Convert to float32
    flux = np.array(astropy_table['FLUX_AUTO'], dtype=np.float32)  # Convert to float32

    # Create FITS columns
    col_x = fits.Column(name='X_IMAGE', format='E', array=x)  # 'E' = float32
    col_y = fits.Column(name='Y_IMAGE', format='E', array=y)  # 'E' = float32
    col_flux = fits.Column(name='FLUX_AUTO', format='E', array=flux)  # 'E' = float32

    # Create a FITS binary table
    hdu = fits.BinTableHDU.from_columns([col_x, col_y, col_flux])

    # Save to file
    hdu.writeto(output_filename, overwrite=True)
    
    print(f"Sources saved as {output_filename}")

input_psolve_info=pickle.load(sys.stdin.buffer)
#input_psolve_info=pickle.load(open('testplatesolvepickle','rb'))

hdufocusdata=input_psolve_info[0]
pixscale=input_psolve_info[1]
is_osc=input_psolve_info[2]
filepath=input_psolve_info[3]
filebase=input_psolve_info[4]
RAest=input_psolve_info[5]
DECest=input_psolve_info[6]
nextseq=input_psolve_info[7]
cpu_limit=90

## Check we are working in unit16
#if not hdufocusdata.dtype == np.uint16:
#    raised_array=hdufocusdata - np.nanmin(hdufocusdata)
##    hdufocusdata = np.maximum(raised_array,0).astype(np.uint16)
#    del raised_array


googtime=time.time()

# If this is an osc image, then interpolate so it is just the green filter image of the same size.
if is_osc:
    ########## Need to split the file into four
    print ("do osc stuff")


# Check that the wcs directory is constructed
#print ("HERE WE ARE")
tempwcsdir=filepath.split('wcs')[0] + 'wcs'
#print (filepath)
#print (tempwcsdir)

if not os.path.exists(tempwcsdir):
    os.makedirs(tempwcsdir, mode=0o777)

# then Check that the individual sequence directory is constructed
if not os.path.exists(filepath):
    os.makedirs(filepath, mode=0o777)
    
# then Check that the individual sequence directory is constructed
tempdir=filepath + '/temp'
if not os.path.exists(tempdir):
    os.makedirs(tempdir, mode=0o777)


wslfilename=filepath + '/' + filebase
# recombobulate to access through the wsl filesystem
realwslfilename=wslfilename.split(':')
realwslfilename[0]=realwslfilename[0].lower()
realwslfilename='/mnt/'+ realwslfilename[0] + realwslfilename[1]


print (realwslfilename)

pixlow = 0.97 * pixscale
pixhigh = 1.03 * pixscale
initial_radius=2

print ("Just before solving: " +str(time.time()-googtime))

# Save an image to the disk to use with source-extractor
# We don't need accurate photometry, so integer is fine.
hdufocus = fits.PrimaryHDU()
hdufocus.data = hdufocusdata#.astype(np.uint16)#.astype(np.float32)
#hdufocus.header = hduheader
hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
hdufocus.writeto(wslfilename, overwrite=True, output_verify='silentfix')


########## SETUP TEMPDIR AND CODEDIR HERE
#tempdir='temporary'
#codedir='temporary'
fwhmfilename=filepath + '/' + filebase.replace('.fits','.fwhm')


# This is the full routine from the pipeline

# # run source extractor on image
# tempprocess = subprocess.Popen(
#     ['source-extractor', wslfilename, '-c', 'photometryparams/default.sexfull', '-PARAMETERS_NAME', str('photometryparams/default.paramastrom'),
#      '-CATALOG_NAME', str(tempdir + '/test.cat'), '-SATUR_LEVEL', str(65535), '-GAIN', str(1), '-BACKPHOTO_TYPE','LOCAL', '-DETECT_THRESH', str(1.0), '-ANALYSIS_THRESH',str(1.0),
#      '-SEEING_FWHM', str(2.0), '-FILTER_NAME', str('photometryparams/sourceex_convs/gauss_2.0_5x5.conv')], stdin=subprocess.PIPE,
#     stdout=subprocess.PIPE, bufsize=0)
# tempprocess.wait() 

current_working_directory=os.getcwd()
cwd_in_wsl=current_working_directory.split(':')
cwd_in_wsl[0]=cwd_in_wsl[0].lower()
cwd_in_wsl='/mnt/'+ cwd_in_wsl[0] + cwd_in_wsl[1]
cwd_in_wsl=cwd_in_wsl.replace('\\','/')

tempdir_in_wsl=tempdir.split(':')
tempdir_in_wsl[0]=tempdir_in_wsl[0].lower()
tempdir_in_wsl='/mnt/'+ tempdir_in_wsl[0] + tempdir_in_wsl[1]
tempdir_in_wsl=tempdir_in_wsl.replace('\\','/')



astoptions = '-c '+str(cwd_in_wsl)+'/subprocesses/photometryparams/default.sexfull -PARAMETERS_NAME ' + str(cwd_in_wsl)+'/subprocesses/photometryparams/default.paramastrom -CATALOG_NAME '+ str(tempdir_in_wsl + '/test.cat') + ' -SATUR_LEVEL 65535 -GAIN 1 -BACKPHOTO_TYPE LOCAL -DETECT_THRESH 1.5 -ANALYSIS_THRESH 1.5 -SEEING_FWHM 2.0 -FILTER_NAME ' + str(cwd_in_wsl)+'/subprocesses/photometryparams/sourceex_convs/gauss_2.0_5x5.conv'

os.system('wsl --exec source-extractor ' + str(realwslfilename) + ' ' + astoptions  )




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


save_sources_as_fits(acatalog,tempdir+ "/test.fits")

#acatalog.write(tempdir+ "/test.fits", format="fits", overwrite=True)



fwhm_values = acatalog['FWHM_IMAGE']  # Extract FWHM values

# Remove NaN and zero values
fwhm_values = fwhm_values[~np.isnan(fwhm_values)]  # Remove NaN
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
    picklefwhm["SKYLEVEL"] = (bn.nanmedian(hdufocusdata), "Sky Level without pedestal")
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

    with open(fwhmfilename, 'wb') as fp:
        pickle.dump(picklefwhm, fp)
        #print('dictionary saved successfully to file')

except:
    print(traceback.format_exc())
    
    picklefwhm["SKYLEVEL"] = (bn.nanmedian(hdufocusdata), "Sky Level without pedestal")

    picklefwhm["FWHM"] = (-99, 'FWHM in pixels')
    picklefwhm["FWHMpix"] = (-99, 'FWHM in pixels')
    picklefwhm["FWHMasec"] = (-99, 'FWHM in arcseconds')
    picklefwhm["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')
    picklefwhm["NSTARS"] = ( len(filtered_fwhm ), 'Number of star-like sources in image')
    


with open(fwhmfilename, 'wb') as fp: # os.getcwd() + '/' + file.replace('.fits', '.wcs').replace('.fit', '.fwhm')
    pickle.dump(picklefwhm, fp)

imageh=hdufocusdata.shape[0]
imagew=hdufocusdata.shape[1]

# Use tweak order 2 in smaller fields of view and tweak order 3 in larger fields.
sizewidest= max(imageh*pixscale, imagew*pixscale) / 3600

if sizewidest > 1.0:
    tweakorder=[3,2]
else:
    tweakorder=[2,3]
    

#os.system('wsl --exec mkdir /home/obs/wcstempfiles')
#os.system('ls ' + str(tempdir_in_wsl))
#os.system('wsl --exec cp ' + str(tempdir_in_wsl + '/test.fits /home/obs/wcstempfiles/test' + str(nextseq) + '.fits'))

#save_xylist(acatalog, tempdir + '/test' + str(nextseq) + '.txt')

#print ('cp ' + str(tempdir_in_wsl + '/test.fits /home/obs/wcstempfiles/test' + str(nextseq) + '.fits'))

#astoptions = 
#print ("wsl --exec solve-field /home/obs/wcstempfiles/test" + str(nextseq) + '.fits' +" -D /home/obs/wcstempfiles --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )

# Try once with tweak-order 2   
#os.system("/usr/local/astrometry/bin/solve-field -D " + str(tempdir) + " --use-source-extractor --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 90 --depth 1-100 --overwrite --no-verify --no-plots " + str(wslfilename))
#os.system("wsl --exec solve-field  /home/obs/wcstempfiles/test" + str(nextseq) + '.fits' +" -D /home/obs/wcstempfiles --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots --skip-solve" )
#os.system("/usr/bin/astrometry-engine /home/obs/wcstempfiles/test" + str(nextseq) + '.axy')


#os.system("wsl --exec build-xylist -i " + tempdir_in_wsl + '/test' + str(nextseq) + '.txt -o ' + tempdir_in_wsl + '/test' + str(nextseq) + '.axy')

#os.system("wsl --exec solve-field  " + tempdir_in_wsl + '/test.fits' +" -D /home/obs/wcstempfiles --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[0]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots --skip-solve" )

if len(acatalog) > 5:
    astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(pixlow) + ' --scale-high ' + str(pixhigh) + ' --ra ' + str(RAest) + ' --dec ' + str(DECest) + ' --radius 20 --cpulimit ' +str(cpu_limit * 3) + ' --overwrite --no-verify --no-plots'

    print (astoptions)

    os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))


# Remove temporary fits file
try:
    os.remove(wslfilename)
except:
    pass

sys.exit()
#breakpoint()

if os.path.exists(tempdir + '/test.wcs'):
    print("A successful solve for " + wslfilename)
    # os.remove(wslfilename)
    # shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + wslfilename.replace('.fits', '.wcs').replace('.fit', '.wcs'))
# os.remove(file)
else:
    # Try once with tweak-order 3    
    os.system("wsl --exec solve-field /home/obs/wcstempfiles/test" + str(nextseq) + '.fits' +" -D /home/obs/wcstempfiles --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (tweakorder[1]) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )
    os.system("/usr/bin/astrometry-engine /home/obs/wcstempfiles/test" + str(nextseq) + '.axy')

    if os.path.exists(tempdir + '/test.wcs'):
        print("A successful solve for " + wslfilename)
        # os.remove(wslfilename)
        # shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + wslfilename.replace('.fits', '.wcs').replace('.fit', '.wcs'))
    # os.remove(file)
    else:
        # Try once with tweak-order 4    
        os.system("wsl --exec solve-field /home/obs/wcstempfiles/test" + str(nextseq) + '.fits' +" -D /home/obs/wcstempfiles --x-column X_IMAGE --y-column Y_IMAGE --sort-column FLUX_AUTO --crpix-center --tweak-order " +str (4) + " --width " +str(imagew) +" --height " +str(imageh) +" --scale-units arcsecperpix --scale-low " + str(pixlow) + " --scale-high " + str(pixhigh) + " --scale-units arcsecperpix --ra " + str(RAest) + " --dec " + str(DECest) + " --radius 10 --cpulimit 300 --depth 1-100 --overwrite --no-verify --no-plots " )
        os.system("/usr/bin/astrometry-engine /home/obs/wcstempfiles/test" + str(nextseq) + '.axy')

        if os.path.exists(tempdir + '/test.wcs'):
            print("A successful solve for " + wslfilename)
            # os.remove(wslfilename)
            # shutil.move(tempdir + '/test.wcs', os.getcwd() + '/' + wslfilename.replace('.fits', '.wcs').replace('.fit', '.wcs'))
        # os.remove(file)
        else:
            
                       
            print("A failed solve for " + wslfilename)
            # os.remove(wslfilename)
                



















# # run again

# #astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius ' + str(initial_radius) + ' --cpulimit ' +str(cpu_limit) + ' --overwrite --no-verify --no-plots'

# print (astoptions)

# os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))

# # If successful, then a file of the same name but ending in solved exists.
# if os.path.exists(wslfilename.replace('.fits','.wcs')):
#     print ("IT EXISTS! WCS SUCCESSFUL!")
#     wcs_header=fits.open(wslfilename.replace('.fits','.wcs'))[0].header
#     solve={}
#     solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
#     solve["dec_j2000_degrees"] = wcs_header['CRVAL2']

#     wcs = WCS(wcs_header)

#     # Get the CD matrix or CDELT values
#     cd = wcs.pixel_scale_matrix
#     pixel_scale_deg = np.sqrt(np.sum(cd**2, axis=0))  # in degrees per pixel
#     solve["arcsec_per_pixel"]  = pixel_scale_deg * 3600  # Convert to arcseconds per pixel

#     solve["arcsec_per_pixel"]  = solve["arcsec_per_pixel"][0]

# else:

#     print ("FAILED NORMAL, TRYING HAIL MARY ATTEMPT")
#     # Remove the previous attempt which was just a table fits
#     temp_files_to_remove=glob.glob(cal_path + 'wsltemp*')
#     for f in temp_files_to_remove:
#         try:
#             os.remove(f)
#         except:
#             pass

#     # run for the first time

#     astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius 20 --cpulimit ' +str(cpu_limit * 3) + ' --overwrite --no-verify --no-plots'

#     print (astoptions)

#     os.system('wsl --exec solve-field ' + astoptions + ' ' + str(realwslfilename))

#     # If successful, then a file of the same name but ending in solved exists.
#     if os.path.exists(wslfilename.replace('.fits','.wcs')):
#         print ("IT EXISTS! WCS SUCCESSFUL!")
#         wcs_header=fits.open(wslfilename.replace('.fits','.wcs'))[0].header
#         solve={}
#         solve["ra_j2000_hours"] = wcs_header['CRVAL1']/15
#         solve["dec_j2000_degrees"] = wcs_header['CRVAL2']

#         wcs = WCS(wcs_header)

#         # Get the CD matrix or CDELT values
#         cd = wcs.pixel_scale_matrix
#         pixel_scale_deg = np.sqrt(np.sum(cd**2, axis=0))  # in degrees per pixel
#         solve["arcsec_per_pixel"]  = pixel_scale_deg * 3600  # Convert to arcseconds per pixel

#         solve["arcsec_per_pixel"]  = solve["arcsec_per_pixel"][0]

        
#     else:
#         solve = 'error'







# print (solve)
# print ("solver: " +str(time.time()-googtime))

