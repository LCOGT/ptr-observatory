"""
This is the smartstack process where stacks are .... stacked PURELY for the UI.

To make the stacking work, a lot of laziness is accepted to make it fast enough
to run faster than the exposures being taken.
"""

import pickle
import sys
from astropy.io import fits
import numpy as np
import os
import time
from astropy.table import Table
import astroalign as aa
from auto_stretch.stretch import Stretch
from PIL import Image, ImageEnhance
import subprocess
from math import sqrt
input_sstk_info=pickle.load(sys.stdin.buffer)
#input_sstk_info=pickle.load(open('testsmartstackpickle','rb'))

print ("HERE IS THE INCOMING. ")
print (input_sstk_info)


paths=input_sstk_info[0]
smartstackid=input_sstk_info[1]
is_osc=input_sstk_info[2]
obsid_path=input_sstk_info[3]
pixscale=input_sstk_info[4]
transpose_jpeg=input_sstk_info[5]
flipx_jpeg=input_sstk_info[6]
flipy_jpeg=input_sstk_info[7]
rotate180_jpeg=input_sstk_info[8]
rotate90_jpeg=input_sstk_info[9]
rotate270_jpeg=input_sstk_info[10]
pier_side=input_sstk_info[11]
squash_on_x_axis=input_sstk_info[12]
osc_bayer=input_sstk_info[13]
image_saturation_level=input_sstk_info[14]
# Deprecated - native bin not used in smartstacks
#nativebin=input_sstk_info[15]
nativebin=1
readnoise=input_sstk_info[16]
minimum_realistic_seeing=input_sstk_info[17]
osc_brightness_enhance=input_sstk_info[18]
osc_contrast_enhance=input_sstk_info[19]
osc_colour_enhance=input_sstk_info[20]
osc_saturation_enhance=input_sstk_info[21]
osc_sharpness_enhance=input_sstk_info[22]
crop_preview=input_sstk_info[23]
yb = input_sstk_info[24]
yt = input_sstk_info[25]
xl = input_sstk_info[26]
xr = input_sstk_info[27]
try:
    zoom_factor = input_sstk_info[28].lower()
    print("Mainjpeg received:", zoom_factor)
except:
    print("Zoom_factor paramater faulted.")
    zoom_factor=False

try:
    os.remove(paths["im_path"] + 'smartstack.pickle')
except:
    pass


img = fits.open(
    paths["red_path"] + paths["red_name01"].replace('.fits','.head'),
    ignore_missing_end=True,
)
imgdata = np.load(paths["red_path"] + paths["red_name01"].replace('.fits','.npy'))


# Check there are no nans in the image upon receipt
# This is necessary as nans aren't interpolated in the main thread.
# Fast next-door-neighbour in-fill algorithm
num_of_nans=np.count_nonzero(np.isnan(imgdata))
x_size=imgdata.shape[0]
y_size=imgdata.shape[1]
# this is actually faster than np.nanmean
edgefillvalue=np.divide(np.nansum(imgdata),(x_size*y_size)-num_of_nans)
#breakpoint()
while num_of_nans > 0:
    # List the coordinates that are nan in the array
    nan_coords=np.argwhere(np.isnan(imgdata))

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
            imgdata[x_nancoord,y_nancoord]=edgefillvalue
            done=True
        elif x_nancoord > (x_size-100):
            imgdata[x_nancoord,y_nancoord]=edgefillvalue

            done=True
        elif y_nancoord < 100:
            imgdata[x_nancoord,y_nancoord]=edgefillvalue

            done=True
        elif y_nancoord > (y_size-100):
            imgdata[x_nancoord,y_nancoord]=edgefillvalue
            done=True

        # left
        if not done:
            if x_nancoord != 0:
                value_here=imgdata[x_nancoord-1,y_nancoord]
                if not np.isnan(value_here):
                    imgdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # right
        if not done:
            if x_nancoord != (x_size-1):
                value_here=imgdata[x_nancoord+1,y_nancoord]
                if not np.isnan(value_here):
                    imgdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # below
        if not done:
            if y_nancoord != 0:
                value_here=imgdata[x_nancoord,y_nancoord-1]
                if not np.isnan(value_here):
                    imgdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # above
        if not done:
            if y_nancoord != (y_size-1):
                value_here=imgdata[x_nancoord,y_nancoord+1]
                if not np.isnan(value_here):
                    imgdata[x_nancoord,y_nancoord]=value_here
                    done=True

    num_of_nans=np.count_nonzero(np.isnan(imgdata))


#Make sure there is a smartstack directory!
if not os.path.exists(obsid_path+ "smartstacks/"):
            os.makedirs(obsid_path+ "smartstacks/")
reprojection_failed = False

# Pick up some header items for smartstacking later
ssfilter = str(img[0].header["FILTER"]).replace('@','at').replace('.','d').replace(' ','')
ssobject = str(img[0].header["OBJECT"]).replace('@','at').replace(':','d').replace('.','d').replace(' ','').replace('-','')
ssexptime = str(img[0].header["EXPTIME"]).replace('.','d').replace(' ','')
sspedestal = str(img[0].header["PEDESTAL"]).replace('.','d').replace(' ','')
imgdata=imgdata-float(sspedestal)

img.close()
del img

smartStackFilename = (
    str(ssobject)
    + "_"
    + str(ssfilter)
    + "_"
    + str(ssexptime)
    + "_"
    + str(smartstackid)
    + ".npy"
)

# For OSC, we need to smartstack individual frames.
if not is_osc:   #This is the monochrome camera processing path.

    while not os.path.exists(paths["im_path"] + paths["text_name00"].replace('.txt','.sep')):
        time.sleep(1)

    #plog("Now to figure out how to get sep into a csv.")
    sstack_process_timer = time.time()
    sources = Table.read(paths["im_path"] + paths["text_name00"].replace('.txt', '.sep'), format='csv')

    # IF SMARSTACK NPY FILE EXISTS ADD next image to the stack, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
    reprojection_failed = False
    if not os.path.exists(
        obsid_path + "smartstacks/" + smartStackFilename
    ):
        if len(sources) >= 5:    #IF image has at least five sources
            # Store original image
            np.save(
                obsid_path
                + "smartstacks/"
                + smartStackFilename,
                imgdata ,
            )
            sources.write(obsid_path
            + "smartstacks/"
            + smartStackFilename.replace('.npy','.sep'), format='csv', overwrite=True)

        else:
            reprojection_failed = True
        storedsStack = imgdata
    else:
        # Collect stored SmartStack
        storedsStack = np.load(
            obsid_path + "smartstacks/" + smartStackFilename
        )
        # Collect stored SEP for first smartstack image
        ref_sources = Table.read(obsid_path
        + "smartstacks/"
        + smartStackFilename.replace('.npy','.sep'), format='csv')

        #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
        # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
        # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
        minarea= -9.2421 * pixscale + 16.553
        if minarea < 5:  # There has to be a min minarea though!
            minarea = 5

        if len(sources) > 5:
            try:
                sources=np.column_stack((sources['x'],sources['y']))
                ref_sources=np.column_stack((ref_sources['x'],ref_sources['y']))
                transf, (source_list, target_list) = aa.find_transform(sources, ref_sources)
                reprojectedimage= aa.apply_transform(transf, imgdata, storedsStack)[0]
                storedsStack += reprojectedimage  # + storedsStack   A WER experiment!

                # Save new stack to disk
                np.save(
                    obsid_path
                    + "smartstacks/"
                    + smartStackFilename,
                    storedsStack,
                )
                reprojection_failed = False
            except aa.MaxIterError:
                reprojection_failed = True
            except Exception:
                reprojection_failed = True
        else:
            reprojection_failed = True

    if reprojection_failed == True:  # If we couldn't make a stack send a jpeg of the original image.
        storedsStack = imgdata

     # Resizing the array to an appropriate shape for the jpg and the small fits

    # Code to stretch the image to fit into the 256 levels of grey for a jpeg
    stretched_data_float = Stretch().stretch(storedsStack + 1000)
    del storedsStack
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

    # Save BIG version of JPEG.
    final_image.save(
        paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
    )
    # Resizing the array to an appropriate shape for the jpg and the small fits
    #insert Debify routine here.  NB NB Note LCO '30-amin Sq field not implemented.'
    print('Zoom factor is:  ', zoom_factor)
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

# This is where the OSC smartstack stuff is.
else:

    # img is the image coming in
    if is_osc:
        sstack_process_timer = time.time()
        if osc_bayer == 'RGGB':

            newhdured = imgdata[::2, ::2]
            newhdugreen = imgdata[::2, 1::2]
            newhdublue = imgdata[1::2, 1::2]

        else:
            pass

        # HERE is where to do a simultaneous red, green, blue
        # multithreaded sep.
        pixscale=pixscale

        im_path=paths["im_path"]
        text_name=paths["text_name00"]

        pickler=[newhdured,pixscale,image_saturation_level,nativebin,readnoise,minimum_realistic_seeing,im_path,text_name,'red']
        red_sep_subprocess=subprocess.Popen(['python','subprocesses/OSC_AA_SEPprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        pickle.dump(pickler, red_sep_subprocess.stdin)

        pickler[0]=newhdugreen
        pickler[8]='green'
        green_sep_subprocess=subprocess.Popen(['python','subprocesses/OSC_AA_SEPprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        pickle.dump(pickler, green_sep_subprocess.stdin)

        pickler[0]=newhdublue
        pickler[8]='blue'
        blue_sep_subprocess=subprocess.Popen(['python','subprocesses/OSC_AA_SEPprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        pickle.dump(pickler, blue_sep_subprocess.stdin)

        # Essentially wait until each subprocess is complete
        red_sep_subprocess.communicate()
        green_sep_subprocess.communicate()
        blue_sep_subprocess.communicate()

        redsources=pickle.load(open(im_path + 'oscaasep.picklered', 'rb'))
        greensources=pickle.load(open(im_path + 'oscaasep.picklegreen', 'rb'))
        bluesources=pickle.load(open(im_path + 'oscaasep.pickleblue', 'rb'))

        if len(greensources) > 5:
        # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
            reprojection_failed = False
            for colstack in ['blue', 'green', 'red']:
                if not os.path.exists(
                    obsid_path + "smartstacks/" +
                        smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                ):
                    if len(greensources) >= 5:
                        # Store original image

                        if colstack == 'blue':
                            np.save(
                                obsid_path
                                + "smartstacks/"
                                + smartStackFilename.replace(smartstackid,
                                                             smartstackid + str(colstack)),
                                newhdublue,
                            )

                            bluesources.write(obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace('.npy','blue.sep'), format='csv', overwrite=True)


                        if colstack == 'green':
                            np.save(
                                obsid_path
                                + "smartstacks/"
                                + smartStackFilename.replace(smartstackid,
                                                             smartstackid + str(colstack)),
                                newhdugreen,
                            )
                            greensources.write(obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace('.npy','green.sep'), format='csv', overwrite=True)
                        if colstack == 'red':
                            np.save(
                                obsid_path
                                + "smartstacks/"
                                + smartStackFilename.replace(smartstackid,
                                                             smartstackid + str(colstack)),
                                newhdured,
                            )
                            redsources.write(obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace('.npy','red.sep'), format='csv', overwrite=True)

                    else:
                        reprojection_failed = True

                else:
                    # Collect stored SmartStack
                    storedsStack = np.load(
                        obsid_path + "smartstacks/" +
                        smartStackFilename.replace(smartstackid, smartstackid + str(colstack))
                    )

                    ref_sources=ref_sources = Table.read(obsid_path
                    + "smartstacks/"
                    + smartStackFilename.replace('.npy',str(colstack)+'.sep'), format='csv')

                    if colstack == 'blue':
                        sources=bluesources
                        imgdata=newhdublue
                    if colstack == 'red':
                        sources=redsources
                        imgdata=newhdured
                    if colstack == 'green':
                        sources=greensources
                        imgdata=newhdugreen


                    sources=np.column_stack((sources['x'],sources['y']))
                    ref_sources=np.column_stack((ref_sources['x'],ref_sources['y']))

                    if len(greensources) > 5:

                        try:
                            transf, (source_list, target_list) = aa.find_transform(sources, ref_sources)

                            reprojectedimage= aa.apply_transform(transf, imgdata, storedsStack)[0]

                            storedsStack = reprojectedimage + storedsStack

                            # Save new stack to disk
                            np.save(
                                obsid_path
                                + "smartstacks/"
                                + smartStackFilename.replace(smartstackid,
                                                             smartstackid + str(colstack)),
                                storedsStack,
                            )


                            if colstack == 'green':
                                newhdugreen = storedsStack
                            if colstack == 'red':
                                newhdured = storedsStack
                            if colstack == 'blue':
                                newhdublue = storedsStack
                            del storedsStack
                            reprojection_failed = False
                        except aa.MaxIterError:
                            reprojection_failed = True
                        except Exception:
                            reprojection_failed = True
                    else:
                        reprojection_failed = True

        # NOW THAT WE HAVE THE INDIVIDUAL IMAGES THEN PUT THEM TOGETHER
        xshape = newhdugreen.shape[0]
        yshape = newhdugreen.shape[1]

        blue_stretched_data_float = Stretch().stretch(newhdublue)*256
        del newhdublue

        green_stretched_data_float = Stretch().stretch(newhdugreen)*256
        del newhdugreen

        red_stretched_data_float = Stretch().stretch(newhdured)*256
        del newhdured

        rgbArray = np.empty((xshape, yshape, 3), 'uint8')
        rgbArray[..., 0] = red_stretched_data_float  # *256
        rgbArray[..., 1] = green_stretched_data_float  # *256
        rgbArray[..., 2] = blue_stretched_data_float  # *256

        del red_stretched_data_float
        del blue_stretched_data_float
        del green_stretched_data_float
        colour_img = Image.fromarray(rgbArray, mode="RGB")

        # adjust brightness
        brightness = ImageEnhance.Brightness(colour_img)
        brightness_image = brightness.enhance(
            osc_brightness_enhance)
        del colour_img
        del brightness

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
        satur_image = satur.enhance(
            osc_saturation_enhance)
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

        # Save BIG version of JPEG.
        final_image.save(
            paths["im_path"] + paths['jpeg_name10'].replace('EX10', 'EX20')
        )

        # Resizing the array to an appropriate shape for the jpg and the small fits
        iy, ix = final_image.size
        #insert Debify routine here.  NB NB Note LCO '30-amin Sq field not implemented.'
        print('Zoom factor is:  ', zoom_factor)
        if zoom_factor is not False:
            if not (zoom_factor in ['full', 'Full', '100%']):
            #     zoom = (0.0, 0.0, 0.0, 0.0)   #  Trim nothing
            # el
                if zoom_factor in ['square', 'Sqr.', 'small sq.']:
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

        if (
            crop_preview
            == True
        ):
            final_image=final_image.crop((xl,yt,xr,yb))
            iy, ix = final_image.size

        if iy == ix:
            final_image = final_image.resize((900, 900))
        else:
            if squash_on_x_axis:
                final_image = final_image.resize((int(900 * iy / ix), 900))
            else:
                final_image = final_image.resize(900, (int(900 * iy / ix)))

        final_image.save(
            paths["im_path"] + paths["jpeg_name10"]
        )
        del final_image

try:
    imgdata.close()
    # Just in case
except:
    pass
del imgdata

pickle.dump(reprojection_failed, open(paths["im_path"] + 'smartstack.pickle', 'wb'))


try:
    os.remove(paths["red_path"] + paths["red_name01"].replace('.fits','.head'))
except:
    pass

try:
    os.remove(paths["red_path"] + paths["red_name01"].replace('.fits','.npy'))
except:
    pass
