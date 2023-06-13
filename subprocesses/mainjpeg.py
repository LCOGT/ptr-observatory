# -*- coding: utf-8 -*-
"""
The subprocess for jpeg construction
"""

import numpy as np
from auto_stretch.stretch import Stretch
from PIL import Image, ImageEnhance#, ImageFont, ImageDraw
import sys
import pickle

from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)

# Pick up the pickled array

input_jpeg_info=pickle.load(sys.stdin.buffer)
#input_jpeg_info=pickle.load(open('testjpegpickle','rb'))

print ("HERE IS THE INCOMING. ")
print (input_jpeg_info)


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

# If this a bayer image, then we need to make an appropriate image that is monochrome
# That gives the best chance of finding a focus AND for pointing while maintaining resolution.
# This is best done by taking the two "real" g pixels and interpolating in-between
# binfocus=1

if is_osc:
    #plog ("interpolating bayer grid for focusing purposes.")
    if osc_bayer == 'RGGB':
        # Only separate colours if needed for colour jpeg
        if smartstackid == 'no':
            
            hdured = hdusmalldata[::2, ::2]
            hdugreen = hdusmalldata[::2, 1::2]
            hdublue = hdusmalldata[1::2, 1::2]

    else:
        print("this bayer grid not implemented yet")



# This is holding the flash reduced fits file waiting to be saved
# AFTER the jpeg has been sent up to AWS.
#hdureduceddata = np.array(hdusmalldata)

# Code to stretch the image to fit into the 256 levels of grey for a jpeg
# But only if it isn't a smartstack, if so wait for the reduce queue
if smartstackid == 'no':

    if is_osc:
        xshape = hdugreen.shape[0]
        yshape = hdugreen.shape[1]

        # histogram matching

        #plog (np.median(hdublue))
        #plog (np.median(hdugreen))
        #plog (np.median(hdured))

        # breakpoint()
        
        # The integer mode of an image is typically the sky value, so squish anything below that
        #bluemode = stats.mode((hdublue.astype('int16').flatten()), keepdims=True)[0] - 25
        #redmode = stats.mode((hdured.astype('int16').flatten()), keepdims=True)[0] - 25
        #greenmode = stats.mode((hdugreen.astype('int16').flatten()), keepdims=True)[0] - 25
        #hdublue[hdublue < bluemode] = bluemode
        #hdugreen[hdugreen < greenmode] = greenmode
        #hdured[hdured < redmode] = redmode

        # Then bring the background level up a little from there
        # blueperc=np.nanpercentile(hdublue,0.75)
        # greenperc=np.nanpercentile(hdugreen,0.75)
        # redperc=np.nanpercentile(hdured,0.75)
        # hdublue[hdublue < blueperc] = blueperc
        # hdugreen[hdugreen < greenperc] = greenperc
        # hdured[hdured < redperc] = redperc

        #hdublue = hdublue * (np.median(hdugreen) / np.median(hdublue))
        #hdured = hdured * (np.median(hdugreen) / np.median(hdured))

        blue_stretched_data_float = Stretch().stretch(hdublue)*256
        ceil = np.percentile(blue_stretched_data_float, 100)  # 5% of pixels will be white
        # 5% of pixels will be black
        floor = np.percentile(blue_stretched_data_float,
                              osc_background_cut)
        #a = 255/(ceil-floor)
        #b = floor*255/(floor-ceil)
        blue_stretched_data_float[blue_stretched_data_float < floor] = floor
        blue_stretched_data_float = blue_stretched_data_float-floor
        blue_stretched_data_float = blue_stretched_data_float * (255/np.max(blue_stretched_data_float))

        #blue_stretched_data_float = np.maximum(0,np.minimum(255,blue_stretched_data_float*a+b)).astype(np.uint8)
        #blue_stretched_data_float[blue_stretched_data_float < floor] = floor
        del hdublue

        green_stretched_data_float = Stretch().stretch(hdugreen)*256
        ceil = np.percentile(green_stretched_data_float, 100)  # 5% of pixels will be white
        # 5% of pixels will be black
        floor = np.percentile(green_stretched_data_float,
                              osc_background_cut)
        #a = 255/(ceil-floor)
        green_stretched_data_float[green_stretched_data_float < floor] = floor
        green_stretched_data_float = green_stretched_data_float-floor
        green_stretched_data_float = green_stretched_data_float * \
            (255/np.max(green_stretched_data_float))

        #b = floor*255/(floor-ceil)

        #green_stretched_data_float[green_stretched_data_float < floor] = floor
        #green_stretched_data_float = np.maximum(0,np.minimum(255,green_stretched_data_float*a+b)).astype(np.uint8)
        del hdugreen

        red_stretched_data_float = Stretch().stretch(hdured)*256
        ceil = np.percentile(red_stretched_data_float, 100)  # 5% of pixels will be white
        # 5% of pixels will be black
        floor = np.percentile(red_stretched_data_float,
                              osc_background_cut)
        #a = 255/(ceil-floor)
        #b = floor*255/(floor-ceil)
        # breakpoint()

        red_stretched_data_float[red_stretched_data_float < floor] = floor
        red_stretched_data_float = red_stretched_data_float-floor
        red_stretched_data_float = red_stretched_data_float * (255/np.max(red_stretched_data_float))

        #red_stretched_data_float[red_stretched_data_float < floor] = floor
        #red_stretched_data_float = np.maximum(0,np.minimum(255,red_stretched_data_float*a+b)).astype(np.uint8)
        del hdured

       

        rgbArray = np.empty((xshape, yshape, 3), 'uint8')
        rgbArray[..., 0] = red_stretched_data_float  # *256
        rgbArray[..., 1] = green_stretched_data_float  # *256
        rgbArray[..., 2] = blue_stretched_data_float  # *256

        del red_stretched_data_float
        del blue_stretched_data_float
        del green_stretched_data_float
        colour_img = Image.fromarray(rgbArray, mode="RGB")

        
        #googtime=time.time()
        # adjust brightness
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
        #plog ("time: " + str(time.time()-googtime))
        

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


        # if (
        #     self.config["camera"][self.name]["settings"]["crop_preview"]
        #     == True
        # ):
        #     yb = self.config["camera"][self.name]["settings"][
        #         "crop_preview_ybottom"
        #     ]
        #     yt = self.config["camera"][self.name]["settings"][
        #         "crop_preview_ytop"
        #     ]
        #     xl = self.config["camera"][self.name]["settings"][
        #         "crop_preview_xleft"
        #     ]
        #     xr = self.config["camera"][self.name]["settings"][
        #         "crop_preview_xright"
        #     ]
        #     hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]

        # breakpoint()
        # Save BIG version of JPEG.
        final_image.save(
            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
        )

        # Resizing the array to an appropriate shape for the small jpg
        iy, ix = final_image.size
        if (
            crop_preview
            == True
        ):
            # yb = self.config["camera"][g_dev['cam'].name]["settings"][
            #     "crop_preview_ybottom"
            # ]
            # yt = self.config["camera"][g_dev['cam'].name]["settings"][
            #     "crop_preview_ytop"
            # ]
            # xl = self.config["camera"][g_dev['cam'].name]["settings"][
            #     "crop_preview_xleft"
            # ]
            # xr = self.config["camera"][g_dev['cam'].name]["settings"][
            #     "crop_preview_xright"
            # ]
            #hdusmalldata = hdusmalldata[yb:-yt, xl:-xr]
            final_image=final_image.crop((xl,yt,xr,yb))
            iy, ix = final_image.size
        
        if iy == ix:
            #final_image.resize((1280, 1280))
            final_image = final_image.resize((900, 900))
        else:
            #final_image.resize((int(1536 * iy / ix), 1536))
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
        # breakpoint()

        #hdusmalldata = np.asarray(hdusmalldata)

        # breakpoint()
        # hdusmalldata[
        #     hdusmalldata
        #     > image_saturation_level
        # ] = image_saturation_level
        # #hdusmalldata[hdusmalldata < -100] = -100
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
        #stretched_data_uint8 = Image.fromarray(stretched_data_uint8)
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
            final_image = final_image.transpose(Image.ROTATE_180)

        # Save BIG version of JPEG.
        final_image.save(
            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
        )

        # Resizing the array to an appropriate shape for the jpg and the small fits

        if iy == ix:
            # hdusmalldata = resize(
            #     hdusmalldata, (1280, 1280), preserve_range=True
            # )
            final_image = final_image.resize(
                (900, 900)
            )
        else:
            # stretched_data_uint8 = resize(
            #     stretched_data_uint8,
            #     (int(1536 * iy / ix), 1536),
            #     preserve_range=True,
            # )
            # stretched_data_uint8 = resize(
            #     stretched_data_uint8,
            #     (int(900 * iy / ix), 900),
            #     preserve_range=True,
            # )
            if squash_on_x_axis:
                final_image = final_image.resize(

                    (int(900 * iy / ix), 900)

                )
            else:
                final_image = final_image.resize(

                    (900, int(900 * iy / ix))

                )
        # stretched_data_uint8=stretched_data_uint8.transpose(Image.TRANSPOSE) # Not sure why it transposes on array creation ... but it does!
        final_image.save(
            paths["im_path"] + paths["jpeg_name10"]
        )
        del final_image

del hdusmalldata

# Try saving the jpeg to disk and quickly send up to AWS to present for the user
# GUI
# if smartstackid == 'no':
#     try:

#         # if not no_AWS:
#         g_dev["cam"].enqueue_for_fastAWS(
#             100, paths["im_path"], paths["jpeg_name10"]
#         )
#         g_dev["cam"].enqueue_for_fastAWS(
#             1000, paths["im_path"], paths["jpeg_name10"].replace('EX10', 'EX20')
#         )
#         # g_dev["obs"].send_to_user(
#         #    "A preview image of the single image has been sent to the GUI.",
#         #    p_level="INFO",
#         # )
#     except:
#         plog(
#             "there was an issue saving the preview jpg. Pushing on though"
#         )
        