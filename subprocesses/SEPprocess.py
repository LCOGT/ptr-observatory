# -*- coding: utf-8 -*-
"""
Created on Sun Apr 23 04:37:30 2023

@author: observatory
"""

import numpy as np
from astropy.stats import median_absolute_deviation
from astropy.nddata.utils import extract_array
import sys
import pickle
import time
import sep
import traceback
import math
from auto_stretch.stretch import Stretch
from astropy.nddata import block_reduce
from colour_demosaicing import (
    demosaicing_CFA_Bayer_bilinear,  # )#,
    # demosaicing_CFA_Bayer_Malvar2004,
    demosaicing_CFA_Bayer_Menon2007)
from PIL import Image, ImageDraw # ImageFont, ImageDraw#, ImageEnhance
from astropy.table import Table
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter("ignore", category=RuntimeWarning)
#import matplotlib.pyplot as plt


def radial_profile(data, center):
    y, x = np.indices((data.shape))
    r = np.sqrt((x - center[0])**2 + (y - center[1])**2)
    r = r.astype(int)

    tbin = np.bincount(r.ravel(), data.ravel())
    nr = np.bincount(r.ravel())
    radialprofile = tbin / nr
    return radialprofile



input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testSEPpickle','rb'))

#print ("HERE IS THE INCOMING. ")
#print (input_sep_info)

hdufocusdata=input_sep_info[0]
pixscale=input_sep_info[1]
readnoise=input_sep_info[2]
avg_foc=input_sep_info[3]
focus_image=input_sep_info[4]
im_path=input_sep_info[5]
text_name=input_sep_info[6]
hduheader=input_sep_info[7]
cal_path=input_sep_info[8]
cal_name=input_sep_info[9]
frame_type=input_sep_info[10]
focus_position=input_sep_info[11]
gdevevents=input_sep_info[12]
ephemnow=input_sep_info[13]
focus_crop_width = input_sep_info[14]
focus_crop_height = input_sep_info[15]
is_osc= input_sep_info[16]
interpolate_for_focus= input_sep_info[17]
bin_for_focus= input_sep_info[18]
focus_bin_value= input_sep_info[19]
interpolate_for_sep= input_sep_info[20]
bin_for_sep= input_sep_info[21]
sep_bin_value= input_sep_info[22]
focus_jpeg_size= input_sep_info[23]
saturate= input_sep_info[24]
minimum_realistic_seeing=input_sep_info[25]
nativebin=input_sep_info[26]
do_sep=input_sep_info[27]

nativebin=1
# Background clipped
hduheader["IMGMIN"] = ( np.nanmin(hdufocusdata), "Minimum Value of Image Array" )
hduheader["IMGMAX"] = ( np.nanmax(hdufocusdata), "Maximum Value of Image Array" )
hduheader["IMGMEAN"] = ( np.nanmean(hdufocusdata), "Mean Value of Image Array" )
hduheader["IMGMED"] = ( np.nanmedian(hdufocusdata), "Median Value of Image Array" )


hduheader["IMGSTDEV"] = ( np.nanstd(hdufocusdata), "Median Value of Image Array" )
hduheader["IMGMAD"] = ( median_absolute_deviation(hdufocusdata, ignore_nan=True), "Median Absolute Deviation of Image Array" )

#breakpoint()

# no zero values in readnoise.
if float(readnoise) < 0.1:
    readnoise = 0.1

# Get out raw histogram construction data
# Get a flattened array with all nans removed
int_array_flattened=hdufocusdata.astype(int).ravel()
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
m=counts.argmax()
imageMode=unique[m]

hduheader["IMGMODE"] = ( imageMode, "Mode Value of Image Array" )

# Collect unique values and counts

histogramdata=np.column_stack([unique,counts]).astype(np.int32)

#Do some fiddle faddling to figure out the value that goes to zero less
zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
breaker=1
counter=0
while (breaker != 0):
    counter=counter+1
    if not (imageMode-counter) in zeroValueArray[:,0]:

        zeroValue=(imageMode-counter)
        breaker =0
hdufocusdata[hdufocusdata < zeroValue] = imageMode
histogramdata=histogramdata[histogramdata[:,0] > zeroValue]

np.savetxt(
    im_path + text_name.replace('.txt', '.his'),
    histogramdata, delimiter=','
)


if not do_sep or (float(hduheader["EXPTIME"]) < 1.0):
    rfp = np.nan
    rfr = np.nan
    rfs = np.nan
    sepsky = np.nan
else:



    if frame_type == 'focus':

        fx, fy = hdufocusdata.shape

        crop_width = (fx * focus_crop_width) / 2
        crop_height = (fy * focus_crop_height) / 2

        # Make sure it is an even number for OSCs
        if (crop_width % 2) != 0:
            crop_width = crop_width+1
        if (crop_height % 2) != 0:
            crop_height = crop_height+1

        crop_width = int(crop_width)
        crop_height = int(crop_height)

        if crop_width > 0 or crop_height > 0:
            hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]

    binfocus = 1
    if is_osc:

        if frame_type == 'focus' and interpolate_for_focus:
            #hdufocusdata=demosaicing_CFA_Bayer_Menon2007(hdufocusdata, 'RGGB')[:,:,1]
            hdufocusdata=demosaicing_CFA_Bayer_bilinear(hdufocusdata, 'RGGB')[:,:,1]
            hdufocusdata=hdufocusdata.astype("float32")
            binfocus=1
        if frame_type == 'focus' and bin_for_focus:
            focus_bin_factor=focus_bin_value
            hdufocusdata=block_reduce(hdufocusdata,focus_bin_factor)
            binfocus=focus_bin_factor

        if frame_type != 'focus' and interpolate_for_sep:
            #hdufocusdata=demosaicing_CFA_Bayer_Menon2007(hdufocusdata, 'RGGB')[:,:,1]
            hdufocusdata=demosaicing_CFA_Bayer_bilinear(hdufocusdata, 'RGGB')[:,:,1]
            hdufocusdata=hdufocusdata.astype("float32")
            binfocus=1
        if frame_type != 'focus' and bin_for_sep:
            sep_bin_factor=sep_bin_value
            hdufocusdata=block_reduce(hdufocusdata,sep_bin_factor)
            binfocus=sep_bin_factor




    # If it is a focus image then it will get sent in a different manner to the UI for a jpeg
    if frame_type == 'focus':
        hdusmalldata = np.array(hdufocusdata)
        fx, fy = hdusmalldata.shape
        aspect_ratio= fx/fy
        crop_width = (fx - focus_jpeg_size) / 2
        crop_height = (fy - (focus_jpeg_size / aspect_ratio) ) / 2

        # Make sure it is an even number for OSCs
        if (crop_width % 2) != 0:
            crop_width = crop_width+1
        if (crop_height % 2) != 0:
            crop_height = crop_height+1

        crop_width = int(crop_width)
        crop_height = int(crop_height)

        if crop_width > 0 or crop_height > 0:
            hdusmalldata = hdusmalldata[crop_width:-crop_width, crop_height:-crop_height]

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
        draw = ImageDraw.Draw(final_image)

        draw.text((0, 0), str(focus_position), (255))

        final_image.save(im_path + text_name.replace('EX00.txt', 'EX10.jpg'))




    actseptime = time.time()
    focusimg = np.array(
        hdufocusdata, order="C"
    )

    try:
        # Some of these are liberated from BANZAI



        bkg = sep.Background(focusimg, bw=32, bh=32, fw=3, fh=3)
        bkg.subfrom(focusimg)

        sepsky = (np.nanmedian(bkg), "Sky background estimated by SEP")

        ix, iy = focusimg.shape
        border_x = int(ix * 0.05)
        border_y = int(iy * 0.05)
        sep.set_extract_pixstack(int(ix*iy - 1))

        #This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
        # to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
        # Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
        minarea= (-9.2421 * pixscale) + 16.553
        if minarea < 5:  # There has to be a min minarea though!
            minarea = 5

        sources = sep.extract(
            focusimg, 3.0, err=bkg.globalrms, minarea=minarea
        )
        sources = Table(sources)


        sources = sources[sources['flag'] < 8]
        image_saturation_level = saturate
        sources = sources[sources["peak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
        sources = sources[sources["cpeak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
        sources = sources[sources["flux"] > 1000]
        #sources = sources[sources["x"] < iy - border_y]
        #sources = sources[sources["x"] > border_y]
        #sources = sources[sources["y"] < ix - border_x]
        #sources = sources[sources["y"] > border_x]
        #breakpoint()
        # BANZAI prune nans from table





        nan_in_row = np.zeros(len(sources), dtype=bool)
        for col in sources.colnames:
            nan_in_row |= np.isnan(sources[col])
        sources = sources[~nan_in_row]



        # Calculate the ellipticity (Thanks BANZAI)

        sources['ellipticity'] = 1.0 - (sources['b'] / sources['a'])

        # if frame_type == 'focus':
        #     sources = sources[sources['ellipticity'] < 0.4]  # Remove things that are not circular stars
        # else:
        #breakpoint()
        sources = sources[sources['ellipticity'] < 0.6]  # Remove things that are not circular stars

        # Calculate the kron radius (Thanks BANZAI)
        kronrad, krflag = sep.kron_radius(focusimg, sources['x'], sources['y'],
                                          sources['a'], sources['b'],
                                          sources['theta'], 6.0)
        sources['flag'] |= krflag
        sources['kronrad'] = kronrad

        # Calculate uncertainty of image (thanks BANZAI)

        uncertainty = float(readnoise) * np.ones(focusimg.shape,
                                                 dtype=focusimg.dtype) / float(readnoise)


        # DONUT IMAGE DETECTOR.
        xdonut=np.median(pow(pow(sources['x'] - sources['xpeak'],2),0.5))*pixscale*binfocus
        ydonut=np.median(pow(pow(sources['y'] - sources['ypeak'],2),0.5))*pixscale*binfocus

        # Calcuate the equivilent of flux_auto (Thanks BANZAI)
        # This is the preferred best photometry SEP can do.
        # But sometimes it fails, so we try and except
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



        sources['FWHM'], _ = sep.flux_radius(focusimg, sources['x'], sources['y'], sources['a'], 0.5,
                                             subpix=5)
        # If image has been binned for focus we need to multiply some of these things by the binning
        # To represent the original image
        sources['FWHM'] = (sources['FWHM'] * 2) * binfocus
        sources['x'] = (sources['x']) * binfocus
        sources['y'] = (sources['y']) * binfocus
        sources['xpeak'] = (sources['xpeak']) * binfocus
        sources['ypeak'] = (sources['ypeak']) * binfocus
        sources['a'] = (sources['a']) * binfocus
        sources['b'] = (sources['b']) * binfocus
        sources['kronrad'] = (sources['kronrad']) * binfocus
        sources['peak'] = (sources['peak']) / pow(binfocus, 2)
        sources['cpeak'] = (sources['cpeak']) / pow(binfocus, 2)


        #print (sources)

        # Need to reject any stars that have FWHM that are less than a extremely
        # perfect night as artifacts
        if frame_type == 'focus':
            sources = sources[sources['FWHM'] > (0.6 / (pixscale))]
            sources = sources[sources['FWHM'] > (minimum_realistic_seeing / pixscale)]
            sources = sources[sources['FWHM'] != 0]

        source_delete = ['thresh', 'npix', 'tnpix', 'xmin', 'xmax', 'ymin', 'ymax', 'x2', 'y2', 'xy', 'errx2',
                         'erry2', 'errxy', 'a', 'b', 'theta', 'cxx', 'cyy', 'cxy', 'cflux', 'cpeak', 'xcpeak', 'ycpeak']

        sources.remove_columns(source_delete)

        #print (sources)

        # BANZAI prune nans from table
        nan_in_row = np.zeros(len(sources), dtype=bool)
        for col in sources.colnames:
            nan_in_row |= np.isnan(sources[col])
        sources = sources[~nan_in_row]

        #breakpoint()
        #print (sources)
        #breakpoint()

        sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)

        if (len(sources) < 2) or ( frame_type == 'focus' and (len(sources) < 10 or len(sources) == np.nan or str(len(sources)) =='nan' or xdonut > 3.0 or ydonut > 3.0 or np.isnan(xdonut) or np.isnan(ydonut))):
            sources['FWHM'] = [np.nan] * len(sources)
            rfp = np.nan
            rfr = np.nan
            rfs = np.nan
            sources = sources

        else:
            # Get halflight radii

            fwhmcalc = sources['FWHM']
            fwhmcalc = fwhmcalc[fwhmcalc != 0]

            # sigma clipping iterator to reject large variations
            templen = len(fwhmcalc)
            while True:
                fwhmcalc = fwhmcalc[fwhmcalc < np.median(fwhmcalc) + 3 * np.std(fwhmcalc)]
                if len(fwhmcalc) == templen:
                    break
                else:
                    templen = len(fwhmcalc)

            fwhmcalc = fwhmcalc[fwhmcalc > np.median(fwhmcalc) - 3 * np.std(fwhmcalc)]
            rfp = round(np.median(fwhmcalc), 3)
#            rfr = round(np.median(fwhmcalc) * pixscale * nativebin, 3)
#            rfs = round(np.std(fwhmcalc) * pixscale * nativebin, 3)
            rfr = round(np.median(fwhmcalc) * pixscale * binfocus * nativebin, 3)
            rfs = round(np.std(fwhmcalc) * pixscale * binfocus * nativebin, 3)






    except:
        traceback.format_exc()
        sources = [0]
        rfp = np.nan
        rfr = np.nan
        rfs = np.nan
        sepsky = np.nan


# Value-added header items for the UI


try:
    #hduheader["SEPSKY"] = str(sepsky)
    hduheader["SEPSKY"] = sepsky
except:
    hduheader["SEPSKY"] = -9999
try:
    hduheader["FWHM"] = (str(rfp), 'FWHM in pixels')
    hduheader["FWHMpix"] = (str(rfp), 'FWHM in pixels')
except:
    hduheader["FWHM"] = (-99, 'FWHM in pixels')
    hduheader["FWHMpix"] = (-99, 'FWHM in pixels')

try:
    hduheader["FWHMasec"] = (str(rfr), 'FWHM in arcseconds')
except:
    hduheader["FWHMasec"] = (-99, 'FWHM in arcseconds')
try:
    hduheader["FWHMstd"] = (str(rfs), 'FWHM standard deviation in arcseconds')
except:

    hduheader["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')

try:
    hduheader["NSTARS"] = ( len(sources), 'Number of star-like sources in image')
except:
    hduheader["NSTARS"] = ( -99, 'Number of star-like sources in image')

hduheader['PIXSCALE']=float(input_sep_info[1])
text = open(
    im_path + text_name, "w"
)
text.write(str(hduheader))
text.close()


# Create radial profiles for UI
# Determine radial profiles of top 20 star-ish sources
if do_sep:
    try:
        # Get rid of non-stars
        sources=sources[sources['FWHM'] < rfr + 2 * rfs]

        # Reverse sort sources on flux
        sources.sort('flux')
        sources.reverse()

        radtime=time.time()
        dodgylist=[]
        radius_of_radialprofile=(5*math.ceil(rfp))
        # Round up to nearest odd number to make a symmetrical array
        radius_of_radialprofile=(radius_of_radialprofile // 2 *2 +1)
        centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        for i in range(min(len(sources),200)):
            cx= (sources[i]['x'])
            cy= (sources[i]['y'])
            temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cy,cx))
            crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])
            dodgylist.append([cx,cy,crad,temp_array])


        pickle.dump(dodgylist, open(im_path + text_name.replace('.txt', '.rad'),'wb'))

    except:
        pass

# Constructing the slices and dices
try:
    slice_n_dice={}
    image_size_x, image_size_y = hdufocusdata.shape

    # row slices
    slicerow=int(image_size_x * 0.1)
    slice_n_dice['row10percent']=hdufocusdata[slicerow,:]
    slice_n_dice['row20percent']=hdufocusdata[slicerow*2,:]
    slice_n_dice['row30percent']=hdufocusdata[slicerow*3,:]
    slice_n_dice['row40percent']=hdufocusdata[slicerow*4,:]
    slice_n_dice['row50percent']=hdufocusdata[slicerow*5,:]
    slice_n_dice['row60percent']=hdufocusdata[slicerow*6,:]
    slice_n_dice['row70percent']=hdufocusdata[slicerow*7,:]
    slice_n_dice['row80percent']=hdufocusdata[slicerow*8,:]
    slice_n_dice['row90percent']=hdufocusdata[slicerow*9,:]

    # column slices
    slicecolumn=int(image_size_y * 0.1)
    slice_n_dice['column10percent']=hdufocusdata[:,slicecolumn]
    slice_n_dice['column20percent']=hdufocusdata[:,slicecolumn*2]
    slice_n_dice['column30percent']=hdufocusdata[:,slicecolumn*3]
    slice_n_dice['column40percent']=hdufocusdata[:,slicecolumn*4]
    slice_n_dice['column50percent']=hdufocusdata[:,slicecolumn*5]
    slice_n_dice['column60percent']=hdufocusdata[:,slicecolumn*6]
    slice_n_dice['column70percent']=hdufocusdata[:,slicecolumn*7]
    slice_n_dice['column80percent']=hdufocusdata[:,slicecolumn*8]
    slice_n_dice['column90percent']=hdufocusdata[:,slicecolumn*9]

    # diagonals... not so easy as you might think! Easy for square arrays.
    aspectratio=image_size_x/image_size_y

    #topleft to bottomright
    topleftdiag=[]
    for i in range(image_size_x):
        topleftdiag.append(hdufocusdata[i,int((image_size_y-i-1)*aspectratio)])
    slice_n_dice['topleftdiag']=topleftdiag

    #bottomleft to topright
    bottomleftdiag=[]
    for i in range(image_size_x):
        bottomleftdiag.append(hdufocusdata[i,int(i*aspectratio)])
    slice_n_dice['bottomleftdiag']=bottomleftdiag

    # ten percent box area statistics
    boxshape=(int(0.1*image_size_x),int(0.1*image_size_y))
    boxstats=[]
    for x_box in [0,.1,.2,.3,.4,.5,.6,.7,.8,.9]:
        for y_box in [0,.1,.2,.3,.4,.5,.6,.7,.8,.9]:
            xboxleft=x_box*image_size_x
            xboxright=(x_box+0.1) * image_size_x
            xboxmid=int((xboxleft+xboxright)/2)
            yboxup=y_box*image_size_y
            yboxdown=(y_box+0.1) * image_size_y
            yboxmid=int((yboxup+yboxdown)/2)
            statistic_area=extract_array(hdufocusdata, boxshape, (xboxmid,yboxmid))

            # Background clipped
            imgmin = ( np.nanmin(statistic_area), "Minimum Value of Image Array" )
            imgmax = ( np.nanmax(statistic_area), "Maximum Value of Image Array" )
            imgmean = ( np.nanmean(statistic_area), "Mean Value of Image Array" )
            imgmed = ( np.nanmedian(statistic_area), "Median Value of Image Array" )
            imgstdev = ( np.nanstd(statistic_area), "Median Value of Image Array" )
            imgmad = ( median_absolute_deviation(statistic_area, ignore_nan=True), "Median Absolute Deviation of Image Array" )

            # Get out raw histogram construction data
            # Get a flattened array with all nans removed
            int_array_flattened=statistic_area.astype(int).ravel()
            unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
            m=counts.argmax()
            imageMode=unique[m]

            imgmode = ( imageMode, "Mode Value of Image Array" )

            # Collect unique values and counts
            histogramdata=np.column_stack([unique,counts]).astype(np.int32)
            boxstats.append([x_box,y_box,imgmin,imgmax,imgmean,imgmed,imgstdev,imgmad,imgmode,histogramdata])

    slice_n_dice['boxstats']=boxstats

    pickle.dump(slice_n_dice, open(im_path + text_name.replace('.txt', '.box'),'wb'))
except:
    pass
