
# -*- coding: utf-8 -*-
"""
The subprocess for jpeg construction to be sent up to the UI
"""

import numpy as np
from auto_stretch.stretch import Stretch
from PIL import Image, ImageEnhance
import sys
import pickle
from math import sqrt

from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)

warnings.simplefilter("ignore", category=RuntimeWarning)
#from ptr_utility import plog
# Pick up the pickled array
debug = True
if not debug:
    input_jpeg_info=pickle.load(sys.stdin.buffer)
else:
    #breakpoint()
    #NB Use this input file for debugging this code.
    input_jpeg_info=pickle.load(open('C:\\Users\\user\\Documents\\GitHub\\ptr-observatory\\testjpegpickle','rb'))
    print("HERE IS THE INCOMING: ")
    print(input_jpeg_info)


hdusmalldata=input_jpeg_info[0]
smartstackid=input_jpeg_info[1]
paths=input_jpeg_info[2]
pier_side=input_jpeg_info[3]
is_osc=input_jpeg_info[4]
osc_bayer=input_jpeg_info[5]
osc_background_cut=input_jpeg_info[6]
osc_brightness_enhance=input_jpeg_info[7]
osc_contrast_enhance=input_jpeg_info[8]
osc_colour_enhance=input_jpeg_info[9]
osc_saturation_enhance=input_jpeg_info[10]
osc_sharpness_enhance=input_jpeg_info[11]
transpose_jpeg=input_jpeg_info[12]
flipx_jpeg=input_jpeg_info[13]
flipy_jpeg=input_jpeg_info[14]
rotate180_jpeg=input_jpeg_info[15]
rotate90_jpeg=input_jpeg_info[16]
rotate270_jpeg=input_jpeg_info[17]
crop_preview=input_jpeg_info[18]
yb=input_jpeg_info[19]
yt=input_jpeg_info[20]
xl=input_jpeg_info[21]
xr=input_jpeg_info[22]
squash_on_x_axis=input_jpeg_info[23]
try:
    zoom_factor = input_jpeg_info[24]
    print("Mainjpeg received:", zoom_factor)
except:
    print("Zoom_factor paramater faulted.")

# If this a bayer image, then we need to make an appropriate image that is monochrome
# That gives the best chance of finding a focus AND for pointing while maintaining resolution.
# This is best done by taking the two "real" g pixels and interpolating in-between

if is_osc:
    if osc_bayer == 'RGGB':
        # Only separate colours if needed for colour jpeg
        # Only use one green channel, otherwise the green channel will have half the noise of other channels
        # and won't make a relatively balanced image (in terms of noise anyway)
        if smartstackid == 'no':
            hdured = hdusmalldata[::2, ::2]
            hdugreen = hdusmalldata[::2, 1::2]
            hdublue = hdusmalldata[1::2, 1::2]

    else:
        print("this bayer grid not implemented yet")

# Code to stretch the image to fit into the 256 levels of grey for a jpeg
# But only if it isn't a smartstack, if so wait for the reduce queue
if smartstackid == 'no':

    if is_osc:
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
            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
        )

        # Resizing the array to an appropriate shape for the small jpg
        iy, ix = final_image.size
        if (crop_preview == True):
            final_image=final_image.crop((xl,yt,xr,yb))
            iy, ix = final_image.size
            #insert Debify routine here.  NB NB Note LCO '30-amin Sq field not implemented.'
            print('Zoom factor is:  ', zoom_factor)
            if zoom_factor is not False:
                if zoom_factor in ['full', 'Full', '100%']:
                    zoom = (0.0, 0.0, 0.0, 0.0)   #  Trim nothing
                elif zoom_factor in ['square', 'Sqr.', 'small sq.']:
                    zoom = ((ix/iy -1)/2, 0.0, (ix/iy -1)/2, 0.00,)    #  3:2 ->> 2:2, QHY600 sides trim.
                elif zoom_factor in ['71%', '70.7%', '1.4X', '1.5X']:
                    r_sq2 = (1 - 1/sqrt(2))/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['50%', '2X']:
                    r_sq2 = (1 - 0.5)/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['35%', '2.8X', '3X']:
                    r_sq2 = (1 - 0.5/sqrt(2))/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['25%', '4X']:
                    r_sq2 = (1 - 0.25)/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['18%', '5.7X', '6X']:
                    r_sq2 = (1 - 0.25/sqrt(2))/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['12.5%', '13%', '12%', '8X']:
                    r_sq2 = (1 - 0.125)/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['9%', '11.3X', '11X', '12X']:
                    r_sq2 = (1 - 0.125/sqrt(2))/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
                elif zoom_factor in ['6%', '6.3%', '16X']:
                    r_sq2 = (1 - 0.0625)/2
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                else:
                    zoom = (1.0, 1.0, 1.0, 1.0)
                #breakpoint()
                xl, yt, xr, yb = zoom
                xl *= ix
                yt *= iy
                xr *= ix
                yb *= iy
                trial_image=final_image.crop((int(xl),int(yt),int(ix-xr),int(iy-yb)))
                ix, iy = trial_image.size
                print("Zoomed Image size:", ix, iy)
                final_image = trial_image


        if ix == iy:
            final_image = final_image.resize((900, 900))
        else:
            if squash_on_x_axis:
                final_image = final_image.resize((int(900 * iy / ix), 900))
            else:
                final_image = final_image.resize((900, int(900 * iy / ix)))

        final_image.save(
            paths["im_path"] + paths["jpeg_name10"]
        )
        del final_image

    else:
        # Making cosmetic adjustments to the image array ready for jpg stretching

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
            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
        )

        # Resizing the array to an appropriate shape for the jpg and the small fits
        ix, iy = final_image.size
        print('Zoom factor is:  ', zoom_factor)
        if zoom_factor is not False:
            if zoom_factor in ['full', 'Full', '100%']:
                zoom = (0.0, 0.0, 0.0, 0.0)   #  Trim nothing
            elif zoom_factor in ['square', 'Sqr.', 'small sq.']:
                zoom = ((ix/iy -1)/2, 0.0, (ix/iy -1)/2, 0.00,)    #  3:2 ->> 2:2, QHY600 sides trim.
            elif zoom_factor in ['71%', '70.7%', '1.4X', '1.5X']:
                r_sq2 = (1 - 1/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['50%', '2X']:
                r_sq2 = (1 - 0.5)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['35%', '2.8X', '3X']:
                r_sq2 = (1 - 0.5/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['25%', '4X']:
                r_sq2 = (1 - 0.25)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['18%', '5.7X', '6X']:
                r_sq2 = (1 - 0.25/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['12.5%', '13%', '12%', '8X']:
                r_sq2 = (1 - 0.125)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['9%', '11.3X', '11X', '12X']:
                r_sq2 = (1 - 0.125/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)    #  0.14644, sides trim.
            elif zoom_factor in ['6%', '6.3%', '16X']:
                r_sq2 = (1 - 0.0625)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
            else:
                zoom = (1.0, 1.0, 1.0, 1.0)



            #breakpoint()
            xl, yt, xr, yb = zoom
            xl *= ix
            yt *= iy
            xr *= ix
            yb *= iy
            trial_image=final_image.crop((int(xl),int(yt),int(ix-xr),int(iy-yb)))
            ix, iy = trial_image.size
            print("Zoomed Image size:", ix, iy)
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
            paths["im_path"] + paths["jpeg_name10"]
        )
        del final_image

del hdusmalldata
