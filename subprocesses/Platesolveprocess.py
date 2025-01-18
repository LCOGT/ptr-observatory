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
import copy
from astropy.nddata import block_reduce
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


#from scipy import optimize

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


def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev)**2)


"""
Here is the start of the subprocessing

"""


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
    os.remove(cal_path + 'platesolve.pickle')
except:
    pass

try:
    os.remove(cal_path + 'platesolve.temppickle')
except:
    pass

try:
    if np.isnan(pixscale):
        pixscale=None
except:
    pixscale=None


# init
binnedtwo=False
binnedthree=False


if pixscale == None:
    cpu_limit = 180
else:
    cpu_limit = 30

print ("Pixelscale")
print (pixscale)


# Keep a copy of the normal image if this is a pointing image
# This is needed to make the plot right at the end if successful
pointing_image=copy.deepcopy(hdufocusdata).astype(np.uint16)

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


# This section crops down the image to a reasonable thing to solve
# The platesolver only provides the RA and Dec of the center of the frame
# So anything above about half a degree is largely useless
# and hampers speedy and successful solving.
# Also larger fields of view see twists and warps towards the edge of the images
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
    hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]

if pixscale != None:
    binnedtwo=False
    binnedthree=False
    # Just bin the image unless the pixelscale is high
    if pixscale < 0.5 and pixscale > 0.3:

        hdufocusdata=np.divide(block_reduce(hdufocusdata,2,func=np.sum),2)
        pixscale=pixscale*2
        binnedtwo=True
    elif pixscale <= 0.3:
        hdufocusdata=np.divide(block_reduce(hdufocusdata,3,func=np.sum),3)
        pixscale=pixscale*3
        binnedthree=True
else:
    # If there is no pixelscale at least make sure the image is
    # not unnecessarily big

    max_dim=3000

    # Get the current dimensions of the array
    height, width = hdufocusdata.shape[:2]

    # Calculate the crop limits
    new_height = min(height, max_dim)
    new_width = min(width, max_dim)

    # Crop the array
    hdufocusdata = hdufocusdata[:new_height, :new_width]


hdufocusdata=hdufocusdata.astype(np.uint16)#.astype(np.float32)

# # Store the unaltered image for a last ditch attempt
# hail_mary_image= copy.deepcopy(hdufocusdata)


# If this is set to true, then it will output a sample of the background image.
if False:
    hdufocus = fits.PrimaryHDU()
    hdufocus.data = hdufocusdata
    hdufocus.header = hduheader
    hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
    hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
    hdufocus.writeto(cal_path + 'pssignal.fits', overwrite=True, output_verify='silentfix')



wslfilename=cal_path + 'wsltemp' + str(time.time()).replace('.','') +'.fits'
# recombobulate to access through the wsl filesystem
realwslfilename=wslfilename.split(':')
realwslfilename[0]=realwslfilename[0].lower()
realwslfilename='/mnt/'+ realwslfilename[0] + realwslfilename[1]

# Pick pixel scale range
if pixscale == None:
    low_pixscale= 0.05
    high_pixscale=10.0
else:
    low_pixscale = 0.97 * pixscale
    high_pixscale = 1.03 * pixscale

print ("Just before solving: " +str(time.time()-googtime))

# Save an image to the disk to use with source-extractor
# We don't need accurate photometry, so integer is fine.
hdufocus = fits.PrimaryHDU()
hdufocus.data = hdufocusdata#.astype(np.uint16)#.astype(np.float32)
hdufocus.header = hduheader
hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
hdufocus.writeto(wslfilename, overwrite=True, output_verify='silentfix')

# run again

astoptions = '--crpix-center --tweak-order 2 --use-source-extractor --scale-units arcsecperpix --scale-low ' + str(low_pixscale) + ' --scale-high ' + str(high_pixscale) + ' --ra ' + str(pointing_ra * 15) + ' --dec ' + str(pointing_dec) + ' --radius 2 --cpulimit ' +str(cpu_limit) + ' --overwrite --no-verify --no-plots'

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
        final_image.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
        os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)
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

    try:
        im.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
        os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)
    except:
        print ("tried to save a jpeg when there is already a jpge")
        print(traceback.format_exc())

    try:
        os.remove(jpeg_filename.replace('.jpg','matplotlib.jpg'))
    except:
        pass

    try:
        os.remove(jpeg_filename.replace('.jpg','matplotlib.png'))
    except:
        pass


