"""
SmartStackprocess.py  SmartStackprocess.py  SmartStackprocess.py

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
from astropy.nddata import block_reduce
from image_registration import cross_correlation_shifts  # chi2_shift,

from auto_stretch.stretch import Stretch
from PIL import Image, ImageEnhance
import subprocess
from math import sqrt
import traceback
import copy

input_sstk_info = pickle.load(sys.stdin.buffer)
# input_sstk_info=pickle.load(open('testsmartstackpickle','rb'))

print("Starting SmartStackprocess.py")
print(input_sstk_info)


smartstackthread_filename=input_sstk_info[0]
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
zoom_factor = input_sstk_info[28].lower()
jpeg_path=input_sstk_info[29]
jpeg_name=input_sstk_info[30]
red_path=input_sstk_info[31]
red_name01=input_sstk_info[32]



file_wait_timeout_timer=time.time()

# So wait for the image to be available in this smartstack run
while (not os.path.exists(smartstackthread_filename)) and (time.time()-file_wait_timeout_timer < 600):
    time.sleep(0.2)

if time.time()-file_wait_timeout_timer > 599:
    sys.exit()
    
(image_filename, imageMode) = pickle.load(
    open(smartstackthread_filename, 'rb'))

# If the busy indicator for this smartstack is not laid down, then we go
# Otherwise we skip this smartstack because the last one hasn't finished yet.
if not os.path.exists(jpeg_path + smartstackid + '.busy'):
    # Lay down the smartstack busy token
    pickle.dump('googleplex', open(jpeg_path + smartstackid + '.busy', 'wb'))

    try:
        os.remove(jpeg_path + 'smartstack.pickle')
    except:
        pass

    img = fits.open(
        red_path + red_name01.replace('.fits', '.head'),
        ignore_missing_end=True,
    )

    imgdata = copy.deepcopy(np.load(red_path + red_name01.replace('.fits','.npy')))

    #Make sure there is a smartstack directory!
    if not os.path.exists(obsid_path+ "smartstacks/"):
                os.makedirs(obsid_path+ "smartstacks/")
    reprojection_failed = False

    # Pick up some header items for smartstacking later
    ssfilter = str(img[0].header["FILTER"]).replace(
        '@', 'at').replace('.', 'd').replace(' ', '')
    ssobject = str(img[0].header["OBJECT"]).replace(
        '@', 'at').replace(':', 'd').replace('.', 'd').replace(' ', '').replace('-', '')
    ssexptime = str(img[0].header["EXPTIME"]).replace(
        '.', 'd').replace(' ', '')
    sspedestal = str(img[0].header["PEDESTAL"]).replace(
        '.', 'd').replace(' ', '')
    imgdata = imgdata-float(sspedestal)

    img[0].header["PEDESTAL"] = 0

    hold_header = copy.deepcopy(img[0].header)

    img.close()
    del img

    smartStackFilename = (
        str(ssobject)
        + "_"
        + str(ssfilter)
        # + "_"
        # + str(ssexptime)
        + "_"
        + str(smartstackid)
        + ".npy"
    )

    # For OSC, we need to smartstack individual frames.
    if not is_osc:   #This is the monochrome camera processing path.
        if True:

            sstack_process_timer = time.time()

            # IF SMARSTACK NPY FILE EXISTS ADD next image to the stack, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
            reprojection_failed = False


            if not os.path.exists(
                obsid_path + "smartstacks/" + smartStackFilename
            ):
                if True:

                    print ("Storing single original image")

                    # Store original image
                    np.save(
                        obsid_path
                        + "smartstacks/"
                        + smartStackFilename,
                        imgdata)
                    # As soon as there is a reference image, delete the busy token
                    try:
                        os.remove(jpeg_path + smartstackid + '.busy')
                    except:
                        print ("COULDNT DELETE BUSY TOKEN! ALERT!")

                else:
                    reprojection_failed = True
                storedsStack = imgdata
            else:
                # Collect stored SmartStack
                storedsStack = np.load(
                    obsid_path + "smartstacks/" + smartStackFilename
                )

                # Grab the two arrays
                de_nanned_reference_frame=copy.deepcopy(storedsStack)
                tempnan=copy.deepcopy(imgdata)

                googtime=time.time()
                edge_crop=100
                xoff, yoff = cross_correlation_shifts(block_reduce(de_nanned_reference_frame[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=np.nanmean), block_reduce(tempnan[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=np.nanmean),zeromean=False)
                print (time.time()-googtime)
                print ("3x")
                print (str(-yoff*3) + " " + str(-xoff*3))
                print (str(round(-yoff*3)) + " " + str(round(-xoff*3)))
                imageshift=[round(-yoff*3),round(-xoff*3)]

                if abs(imageshift[0]) > 0:
                    imageshiftabs=int(abs(imageshift[0]))
                    if imageshift[0] > 0:
                        imageshiftsign = 1
                    else:
                        imageshiftsign = -1
                    imgdata=np.roll(imgdata, imageshiftabs*imageshiftsign, axis=0)

                if abs(imageshift[1]) > 0:
                    imageshiftabs=int(abs(imageshift[1]))
                    if imageshift[1] > 0:
                        imageshiftsign = 1
                    else:
                        imageshiftsign = -1
                    imgdata=np.roll(imgdata, imageshiftabs*imageshiftsign, axis=1)

                storedsStack += imgdata  # + storedsStack   A WER experiment!

                # Save new stack to disk
                np.save(
                    obsid_path
                    + "smartstacks/"
                    + smartStackFilename,
                    storedsStack,
                )

                # As soon as there is a reference image, delete the busy token
                try:
                    os.remove(jpeg_path + smartstackid + '.busy')
                except:
                    print("COULDNT DELETE BUSY TOKEN! ALERT!")

        if reprojection_failed == True:  # If we couldn't make a stack send a jpeg of the original image.
            storedsStack = imgdata

        pickle.dump(reprojection_failed, open(
            jpeg_path + 'smartstack.pickle', 'wb'))

         # Resizing the array to an appropriate shape for the jpg and the small fits

        # Code to stretch the image to fit into the 256 levels of grey for a jpeg
        stretched_data_float = Stretch().stretch(storedsStack) # + 1000)  WER 20240622
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
            final_image = final_image.transpose(
                Image.Transpose.FLIP_LEFT_RIGHT)
        if flipy_jpeg:
            final_image = final_image.transpose(
                Image.Transpose.FLIP_TOP_BOTTOM)
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
            jpeg_path + jpeg_name.replace('EX10',
                                          'EX20').replace('.jpg', 'temp.jpg')
        )
        os.rename(jpeg_path + jpeg_name.replace('EX10', 'EX20').replace('.jpg',
                  'temp.jpg'), jpeg_path + jpeg_name.replace('EX10', 'EX20'))
        # Resizing the array to an appropriate shape for the jpg and the small fits
        # insert Debify routine here.  NB NB Note LCO '30-amin Sq field not implemented.'
        print('Zoom factor is:  ', zoom_factor)
        if zoom_factor is not False:
            if zoom_factor in ['full', 'Full', '100%']:
                zoom = (0.0, 0.0, 0.0, 0.0)  # Trim nothing
            elif zoom_factor in ['square', 'sqr.', 'small sq.']:
                # 3:2 ->> 2:2, QHY600 sides trim.
                zoom = ((ix/iy - 1)/2, 0.0, (ix/iy - 1)/2, 0.00,)
            elif zoom_factor in ['71%', '70.7%', '1.4x', '1.5x']:
                r_sq2 = (1 - 1/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['50%', '2x']:
                r_sq2 = (1 - 0.5)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['35%', '2.8x', '3x']:
                r_sq2 = (1 - 0.5/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['25%', '4x']:
                r_sq2 = (1 - 0.25)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['18%', '5.7x', '6x']:
                r_sq2 = (1 - 0.25/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['12.5%', '13%', '12%', '8x']:
                r_sq2 = (1 - 0.125)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['9%', '11.3x', '11x', '12x']:
                r_sq2 = (1 - 0.125/sqrt(2))/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)  # 0.14644, sides trim.
            elif zoom_factor in ['6%', '6.3%', '16x']:
                r_sq2 = (1 - 0.0625)/2
                zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
            else:
                zoom = (0.0, 0.0, 0.0, 0.0)   #for other cases treat the image as full-size no ZOOM.
            xl, yt, xr, yb = zoom
            xl *= ix
            yt *= iy
            xr *= ix
            yb *= iy
            try:
                trial_image = final_image.crop(
                    (int(xl), int(yt), int(ix-xr), int(iy-yb)))
            except:
                try:
                    print("excepted 1")
                    ix, iy = trial_image.size
                    xl, yt, xr, yb = zoom
                    xl *= ix
                    yt *= iy
                    xr *= ix
                    yb *= iy
                    trial_image = final_image.crop(
                        (int(xl), int(yt), int(ix-xr), int(iy-yb)))
                except:
                    print("SMstack process second exception... pushing on though")
                    print(zoom)
                    print(ix)
                    print(iy)
                    print(traceback.format_exc())

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
            jpeg_path + jpeg_name.replace('.jpg', 'temp.jpg')
        )
        del final_image
        os.rename(jpeg_path + jpeg_name.replace('.jpg',
                  'temp.jpg'), jpeg_path + jpeg_name)

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
            pixscale = pixscale

            im_path=jpeg_path
            text_name=jpeg_name.replace('.jpg','.txt')

            # IF SMARSTACK NPY FILE EXISTS DO STUFF, OTHERWISE THIS IMAGE IS THE START OF A SMARTSTACK
            reprojection_failed = False
            crosscorrel_filename_waiter = []
            crosscorrelation_subprocess_array = []
            counter = 0
            for colstack in ['blue', 'green', 'red']:
                if not os.path.exists(
                    obsid_path + "smartstacks/" +
                        smartStackFilename.replace(
                            smartstackid, smartstackid + str(colstack))
                ):
                    if colstack == 'blue':
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + str(colstack)),
                            newhdublue,
                        )

                    if colstack == 'green':
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + str(colstack)),
                            newhdugreen,
                        )

                    if colstack == 'red':
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + str(colstack)),
                            newhdured,
                        )

                else:
                    # Collect stored SmartStack
                    storedsStack = np.load(
                        obsid_path + "smartstacks/" +
                        smartStackFilename.replace(
                            smartstackid, smartstackid + str(colstack))
                    )

                    if colstack == 'blue':
                        imgdata=newhdublue
                    if colstack == 'red':
                        imgdata=newhdured
                    if colstack == 'green':
                        imgdata=newhdugreen

                    # Send out each colstack to a subprocess to wait.
                    output_filename='crosscorrel' + str(colstack) + str(smartstackid) + '.npy'
                    pickler=[]
                    pickler.append(storedsStack)
                    pickler.append(imgdata)
                    pickler.append(obsid_path + "smartstacks/")
                    pickler.append(output_filename)
                    pickler.append(is_osc)

                    crosscorrel_filename_waiter.append(
                        obsid_path + "smartstacks/" + output_filename)

                    crosscorrelation_subprocess_array.append(
                        subprocess.Popen(
                            ['python', 'crosscorrelation_subprocess.py'], 
                            stdin=subprocess.PIPE, 
                            stdout=None, 
                            bufsize=-1
                        )
                    )
                    print(counter)
                    pickle.dump(
                        pickler, crosscorrelation_subprocess_array[counter].stdin)

            # Wait for the three crosscorrels to happen
            for waitfile in crosscorrel_filename_waiter:
                
                file_wait_timeout_timer=time.time()                
                    
                while (not os.path.exists(waitfile)) and (time.time()-file_wait_timeout_timer < 600):
                    time.sleep(0.2)
                    
                if time.time()-file_wait_timeout_timer > 599:
                    sys.exit()
                    
            if len(crosscorrel_filename_waiter) > 0:
                for waitfile in crosscorrel_filename_waiter:

                    storedsStack = np.load(waitfile)

                    if 'blue' in waitfile:
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + 'blue'),
                            storedsStack,
                        )
                    if 'green' in waitfile:
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + 'green'),
                            storedsStack,
                        )
                    if 'red' in waitfile:
                        np.save(
                            obsid_path
                            + "smartstacks/"
                            + smartStackFilename.replace(smartstackid,
                                                         smartstackid + 'red'),
                            storedsStack,
                        )

                    if colstack == 'green':
                        newhdugreen = storedsStack
                    if colstack == 'red':
                        newhdured = storedsStack
                    if colstack == 'blue':
                        newhdublue = storedsStack
                    del storedsStack

            # As soon as there is a reference image, delete the busy token
            try:
                os.remove(jpeg_path + smartstackid + '.busy')
            except:
                print("COULDNT DELETE BUSY TOKEN! ALERT!")

            pickle.dump(reprojection_failed, open(jpeg_path + 'smartstack.pickle', 'wb'))

            newhdugreen[np.isnan(newhdugreen)] =imageMode
            newhdured[np.isnan(newhdured)] =imageMode
            newhdublue[np.isnan(newhdublue)] =imageMode

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
                final_image = final_image.transpose(
                    Image.Transpose.FLIP_LEFT_RIGHT)
            if flipy_jpeg:
                final_image = final_image.transpose(
                    Image.Transpose.FLIP_TOP_BOTTOM)
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
                jpeg_path +
                jpeg_name.replace('EX10', 'EX20').replace('.jpg', 'temp.jpg')
            )
            os.rename(jpeg_path + jpeg_name.replace('EX10', 'EX20').replace('.jpg','temp.jpg'),jpeg_path + jpeg_name.replace('EX10', 'EX20'))

            # Resizing the array to an appropriate shape for the small jpg
            ix, iy = final_image.size
            print('Zoom factor is:  ', zoom_factor)
            if zoom_factor is not False:
                if zoom_factor in ['full', 'Full', '100%']:
                    zoom = (0.0, 0.0, 0.0, 0.0)  # Trim nothing
                elif zoom_factor in ['square', 'sqr.', 'small sq.']:
                    # 3:2 ->> 2:2, QHY600 sides trim.
                    zoom = ((ix/iy - 1)/2, 0.0, (ix/iy - 1)/2, 0.00,)
                elif zoom_factor in ['71%', '70.7%', '1.4x', '1.5x']:
                    r_sq2 = (1 - 1/sqrt(2))/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['50%', '2x']:
                    r_sq2 = (1 - 0.5)/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['35%', '2.8x', '3x']:
                    r_sq2 = (1 - 0.5/sqrt(2))/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['25%', '4x']:
                    r_sq2 = (1 - 0.25)/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['18%', '5.7x', '6x']:
                    r_sq2 = (1 - 0.25/sqrt(2))/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['12.5%', '13%', '12%', '8x']:
                    r_sq2 = (1 - 0.125)/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
                elif zoom_factor in ['9%', '11.3x', '11x', '12x']:
                    r_sq2 = (1 - 0.125/sqrt(2))/2
                    # 0.14644, sides trim.
                    zoom = (r_sq2, r_sq2, r_sq2, r_sq2,)
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
                print("Zoomed Image size:", ix, iy)
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
                jpeg_path + jpeg_name.replace('.jpg', 'temp.jpg')
            )
            del final_image
            os.rename(jpeg_path + jpeg_name.replace('.jpg','temp.jpg'),jpeg_path + jpeg_name)

    try:
        os.remove(red_path + red_name01.replace('.fits', '.head'))
    except:
        pass

    try:
        os.remove(red_path + red_name01.replace('.fits', '.npy'))
    except:
        pass

    try:
        imgdata.close()
        # Just in case
    except:
        pass
    del imgdata
