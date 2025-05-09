# -*- coding: utf-8 -*-
"""
The subprocess for jpeg construction to be sent up to the UI
"""
import numpy as np
from auto_stretch.stretch import Stretch
from PIL import Image, ImageEnhance
Image.MAX_IMAGE_PIXELS = None
import sys
import pickle
from math import sqrt
import time
import os
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)

# Add the parent directory to the Python path
# This allows importing modules from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ptr_utility import create_color_plog

log_color = (120, 220, 170) # mint
plog = create_color_plog('mainjpg', log_color)

# Pick up the pickled array
debug = False
if not debug:
    inputs = pickle.load(sys.stdin.buffer)
else:
    #NB Use this input file for debugging this code.
    inputs = pickle.load(open('C:\\Users\\user\\Documents\\GitHub\\ptr-observatory\\testjpegpickle','rb'))
    plog("Starting mainjpeg.py in debug mode")
    plog(inputs)
    breakpoint()

# Extract input values
mainjpegthread_filename = inputs["mainjpegthread_filename"]
output_dir = inputs["output_dir"]
jpeg_filename = inputs["jpeg_filename"]

# OSC settings
is_osc = inputs["osc_settings"]["is_osc"]
osc_bayer = inputs["osc_settings"]["bayer"]
osc_background_cut = inputs["osc_settings"]["background_cut"]
osc_brightness_enhance = inputs["osc_settings"]["brightness_enhance"]
osc_contrast_enhance = inputs["osc_settings"]["contrast_enhance"]
osc_colour_enhance = inputs["osc_settings"]["colour_enhance"]
osc_saturation_enhance = inputs["osc_settings"]["saturation_enhance"]
osc_sharpness_enhance = inputs["osc_settings"]["sharpness_enhance"]

# JPEG transformation settings
pier_side = inputs["jpeg_transforms"]["pier_side"]
transpose_jpeg = inputs["jpeg_transforms"]["transpose"]
flipx_jpeg = inputs["jpeg_transforms"]["flipx"]
flipy_jpeg = inputs["jpeg_transforms"]["flipy"]
rotate180_jpeg = inputs["jpeg_transforms"]["rotate180"]
rotate90_jpeg = inputs["jpeg_transforms"]["rotate90"]
rotate270_jpeg = inputs["jpeg_transforms"]["rotate270"]
squash_on_x_axis = inputs["jpeg_transforms"]["squash_on_x_axis"]
zoom_factor = inputs["jpeg_transforms"]["zoom_factor"].lower()



# This process is set to spin up early, so it loads
# and waits for a filename token to get started.
file_wait_timeout_timer=time.time()
while (not os.path.exists(mainjpegthread_filename)) and (time.time()-file_wait_timeout_timer < 600):
    time.sleep(0.2)
if time.time()-file_wait_timeout_timer > 599:
    sys.exit()


(image_filename,edgefillvalue)=pickle.load(open(mainjpegthread_filename,'rb'))
hdusmalldata=np.load(image_filename)

if is_osc:
    # Only separate colours if needed for colour jpeg
    # Only use one green channel, otherwise the green channel will have half the noise of other channels
    # and won't make a relatively balanced image (in terms of noise anyway)
    if osc_bayer == 'RGGB':
        hdured = np.array(hdusmalldata[::2, ::2])
        hdugreen = np.array(hdusmalldata[::2, 1::2])
        hdublue = np.array(hdusmalldata[1::2, 1::2])
        del hdusmalldata
    else:
        plog("this bayer grid not implemented yet")

    # Code to stretch the image to fit into the 256 levels of grey for a jpeg
    xshape = hdugreen.shape[0]
    yshape = hdugreen.shape[1]

    blue_stretched_data_float = Stretch().stretch(hdublue)*256
    ceil = np.percentile(blue_stretched_data_float, 100)
    floor = np.percentile(blue_stretched_data_float,
                            osc_background_cut)
    blue_stretched_data_float[blue_stretched_data_float < floor] = floor
    blue_stretched_data_float = blue_stretched_data_float-floor
    blue_stretched_data_float = blue_stretched_data_float * (255/np.max(blue_stretched_data_float))
    del hdublue

    green_stretched_data_float = Stretch().stretch(hdugreen)*256
    ceil = np.percentile(green_stretched_data_float, 100)
    floor = np.percentile(green_stretched_data_float,
                            osc_background_cut)
    green_stretched_data_float[green_stretched_data_float < floor] = floor
    green_stretched_data_float = green_stretched_data_float-floor
    green_stretched_data_float = green_stretched_data_float * \
        (255/np.max(green_stretched_data_float))
    del hdugreen

    red_stretched_data_float = Stretch().stretch(hdured)*256
    ceil = np.percentile(red_stretched_data_float, 100)
    floor = np.percentile(red_stretched_data_float,
                            osc_background_cut)
    red_stretched_data_float[red_stretched_data_float < floor] = floor
    red_stretched_data_float = red_stretched_data_float-floor
    red_stretched_data_float = red_stretched_data_float * (255/np.max(red_stretched_data_float))
    del hdured

    rgbArray = np.empty((xshape, yshape, 3), 'uint8')
    rgbArray[..., 0] = red_stretched_data_float  # *256
    rgbArray[..., 1] = green_stretched_data_float  # *256
    rgbArray[..., 2] = blue_stretched_data_float  # *256

    del red_stretched_data_float
    del blue_stretched_data_float
    del green_stretched_data_float
    colour_img = Image.fromarray(rgbArray, mode="RGB")

    if osc_brightness_enhance != 1.0:
        brightness = ImageEnhance.Brightness(colour_img)
        brightness_image = brightness.enhance(
            osc_brightness_enhance)
        del colour_img
        del brightness
    else:
        brightness_image = colour_img
        del colour_img

    # adjust contrast
    contrast = ImageEnhance.Contrast(brightness_image)
    contrast_image = contrast.enhance(
        osc_contrast_enhance)
    del brightness_image
    del contrast

    # adjust colour
    colouradj = ImageEnhance.Color(contrast_image)
    colour_image = colouradj.enhance(
        osc_colour_enhance)
    del contrast_image
    del colouradj

    # adjust saturation
    satur = ImageEnhance.Color(colour_image)
    satur_image = satur.enhance(osc_saturation_enhance)
    del colour_image
    del satur

    # adjust sharpness
    sharpness = ImageEnhance.Sharpness(satur_image)
    final_image = sharpness.enhance(
        osc_sharpness_enhance)
    del satur_image
    del sharpness


    # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
    if transpose_jpeg:
        final_image = final_image.transpose(Image.Transpose.TRANSPOSE)
    if flipx_jpeg:
        final_image = final_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flipy_jpeg:
        final_image = final_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if rotate180_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_180)
    if rotate90_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_90)
    if rotate270_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_270)

    # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
    # to maintain the orientation. whether it is 1 or 0 that is flipped
    # is sorta arbitrary... you'd use the site-config settings above to
    # set it appropriately and leave this alone.
    if pier_side == 1:
        final_image = final_image.transpose(Image.Transpose.ROTATE_180)

    # Save high-res version of JPEG.
    final_image.save(
        output_dir + jpeg_filename.replace('EX10', 'EX20')
    )

    # Resizing the array to an appropriate shape for the small jpg
    #iy, ix = final_image.size
    ix, iy = final_image.size
    plog('Zoom factor is:  ', zoom_factor)
    if zoom_factor is not False:
        if zoom_factor in ['full', 'Full', '100%']:
            zoom = (0.0, 0.0, 0.0, 0.0)   #  Trim nothing
        elif zoom_factor in ['square', 'sqr.', 'small sq.']:
            zoom = ((ix/iy -1)/2, 0.0, (ix/iy -1)/2, 0.00,)    #  3:2 ->> 2:2, QHY600 sides trim.
        elif zoom_factor in ['71%', '70.7%', '1.4x', '1.5x']:
            r_sq2 = (1 - 1/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['50%', '2x']:
            r_sq2 = (1 - 0.5)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['35%', '2.8x', '3x']:
            r_sq2 = (1 - 0.5/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['25%', '4x']:
            r_sq2 = (1 - 0.25)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['18%', '5.7x', '6x']:
            r_sq2 = (1 - 0.25/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['12.5%', '13%', '12%', '8x']:
            r_sq2 = (1 - 0.125)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['9%', '11.3x', '11x', '12x']:
            r_sq2 = (1 - 0.125/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['6%', '6.3%', '16x']:
            r_sq2 = (1 - 0.0625)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
        else:
            zoom = (0.0, 0.0, 0.0, 0.0)
        xl, yt, xr, yb = zoom
        xl *= ix
        yt *= iy
        xr *= ix
        yb *= iy
        trial_image=final_image.crop((int(xl),int(yt),int(ix-xr),int(iy-yb)))
        ix, iy = trial_image.size
        plog("Zoomed Image size:", ix, iy)
        final_image = trial_image

    iy, ix = final_image.size
    if ix == iy:
        final_image = final_image.resize((900, 900))
    else:
        if squash_on_x_axis:
            final_image = final_image.resize((int(900 * iy / ix), 900))
        else:
            final_image = final_image.resize((900, int(900 * iy / ix)))

    final_image.save(
        output_dir + jpeg_filename
    )
    del final_image

else:
    # Making cosmetic adjustments to the image array ready for jpg stretching
    hdusmalldata = hdusmalldata - np.min(hdusmalldata)

    stretched_data_float = Stretch().stretch(hdusmalldata+1000)
    del hdusmalldata
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
    # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
    if transpose_jpeg:
        final_image = final_image.transpose(Image.Transpose.TRANSPOSE)
    if flipx_jpeg:
        final_image = final_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flipy_jpeg:
        final_image = final_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if rotate180_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_180)
    if rotate90_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_90)
    if rotate270_jpeg:
        final_image = final_image.transpose(Image.Transpose.ROTATE_270)

    # Detect the pierside and if it is one way, rotate the jpeg 180 degrees
    # to maintain the orientation. whether it is 1 or 0 that is flipped
    # is sorta arbitrary... you'd use the site-config settings above to
    # set it appropriately and leave this alone.
    if pier_side == 1:
        final_image = final_image.transpose(Image.Transpose.ROTATE_180)

    # Save high-res version of JPEG.
    final_image.save(
        output_dir + jpeg_filename.replace('EX10', 'EX20')
    )

    # Resizing the array to an appropriate shape for the jpg and the small fits
    ix, iy = final_image.size
    plog('Zoom factor is:  ', zoom_factor)
    if zoom_factor is not False:
        if zoom_factor in ['full', 'Full', '100%']:
            zoom = (0.0, 0.0, 0.0, 0.0)   #  Trim nothing
        elif zoom_factor in ['square', 'sqr.', 'small sq.']:
            zoom = ((ix/iy -1)/2, 0.0, (ix/iy -1)/2, 0.00,)    #  3:2 ->> 2:2, QHY600 sides trim.
        elif zoom_factor in ['71%', '70.7%', '1.4x', '1.5x']:
            r_sq2 = (1 - 1/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['50%', '2x']:
            r_sq2 = (1 - 0.5)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['35%', '2.8x', '3x']:
            r_sq2 = (1 - 0.5/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['25%', '4x']:
            r_sq2 = (1 - 0.25)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['18%', '5.7x', '6x']:
            r_sq2 = (1 - 0.25/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['12.5%', '13%', '12%', '8x']:
            r_sq2 = (1 - 0.125)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['9%', '11.3x', '11x', '12x']:
            r_sq2 = (1 - 0.125/sqrt(2))/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
        elif zoom_factor in ['6%', '6.3%', '16x']:
            r_sq2 = (1 - 0.0625)/2
            zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
        else:
            zoom = (0.0, 0.0, 0.0, 0.0)
        xl, yt, xr, yb = zoom
        xl *= ix
        yt *= iy
        xr *= ix
        yb *= iy
        trial_image=final_image.crop((int(xl),int(yt),int(ix-xr),int(iy-yb)))
        ix, iy = trial_image.size
        plog("Zoomed Image size:", ix, iy)
        final_image = trial_image

    if iy == ix:
        final_image = final_image.resize(
            (900, 900)
        )
    else:
        if squash_on_x_axis:
            final_image = final_image.resize(

                (int(900 * iy / ix), 900)

            )
        else:
            final_image = final_image.resize(

                (900, int(900 * iy / ix))

            )
    final_image.save(
        output_dir + jpeg_filename
    )
    del final_image
