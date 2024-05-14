# -*- coding: utf-8 -*-
"""
Created on Sun May  5 09:00:18 2024

@author: psyfi
"""

import matplotlib.pyplot as plt

from astropy.wcs import WCS
from astropy.io import fits

import numpy as np
#from matplotlib.patches import Rectangle
# from astropy.wcs import WCS
# from astropy.io import fits
from astropy import units as u
from astropy.visualization.wcsaxes import Quadrangle

from math import cos, radians
from PIL import Image


def add_margin(pil_img, top, right, bottom, left, color):
    width, height = pil_img.size
    new_width = width + right + left
    new_height = height + top + bottom
    result = Image.new(pil_img.mode, (new_width, new_height), color)
    result.paste(pil_img, (left, top))
    return result

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

filename='testimage.fits'
hdu = fits.open(filename)[0]


imagedata = np.asarray(hdu.data)


pixscale=0.5

err_ha=0.1
err_dec=0.5

#202.47031
#47.19476

RA_where_it_thinks_it_is=13.49802 - err_ha
DEC_where_it_thinks_it_is=47.19476 - err_dec




#(imagedata,pixscale,err_ha,err_dec,RA_where_it_thinks_it_is, DEC_where_it_thinks_it_is) = package


imagedata = mid_stretch_jpeg(imagedata)

RA_where_it_actually_is=RA_where_it_thinks_it_is + err_ha
DEC_where_it_actually_is=DEC_where_it_thinks_it_is + err_dec

#make a fake header to create the WCS object
tempheader = fits.PrimaryHDU()
tempheader=tempheader.header
tempheader['CTYPE1'] = 'RA---TAN'
tempheader['CTYPE2'] = 'DEC--TAN'
tempheader['CUNIT1'] = 'deg'
tempheader['CUNIT2'] = 'deg'
tempheader['CRVAL1'] = RA_where_it_actually_is * 15.0
tempheader['CRVAL2'] = DEC_where_it_actually_is 
#breakpoint()
tempheader['CRPIX1'] = int(imagedata.shape[0] / 2)
tempheader['CRPIX2'] = int(imagedata.shape[1] / 2)
tempheader['NAXIS'] = 2
tempheader['CDELT1'] = float(pixscale) / 3600
tempheader['CDELT2'] = float(pixscale) / 3600


# Size of field in degrees
x_deg_field_size=(float(pixscale) / (3600)) * imagedata.shape[0]
y_deg_field_size=(float(pixscale) / (3600)) * imagedata.shape[1] / cos(radians(DEC_where_it_actually_is ))

print (x_deg_field_size)
print (y_deg_field_size)

xfig=9
yfig=9*(imagedata.shape[0]/imagedata.shape[1])
aspect=1/(imagedata.shape[0]/imagedata.shape[1])
print (imagedata.shape[0]/imagedata.shape[1])

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
ax.imshow(imagedata, origin='lower', cmap='gray')
ax.grid(color='yellow', ls='solid')
ax.set_xlabel('Right Ascension')
ax.set_ylabel('Declination')


print ([RA_where_it_thinks_it_is * 15,RA_where_it_actually_is * 15],[ DEC_where_it_thinks_it_is, DEC_where_it_actually_is])

ax.plot([RA_where_it_thinks_it_is * 15,RA_where_it_actually_is * 15],[ DEC_where_it_thinks_it_is, DEC_where_it_actually_is],  linestyle='dashed',color='green',
      linewidth=2, markersize=12,transform=ax.get_transform('fk5'))
#ax.set_autoscale_on(False)

# This should point to the center of the box. 
ax.scatter(RA_where_it_thinks_it_is * 15, DEC_where_it_thinks_it_is, transform=ax.get_transform('icrs'), s=300,
            edgecolor='red', facecolor='none')


# This should point to the center of the current image
ax.scatter(RA_where_it_actually_is * 15, DEC_where_it_actually_is, transform=ax.get_transform('icrs'), s=300,
            edgecolor='white', facecolor='none')

r = Quadrangle((RA_where_it_thinks_it_is * 15 - 0.5 * y_deg_field_size, DEC_where_it_thinks_it_is - 0.5 * x_deg_field_size)*u.deg, y_deg_field_size*u.deg, x_deg_field_size*u.deg,
                edgecolor='red', facecolor='none',
                transform=ax.get_transform('icrs'))
ax.add_patch(r)
# ax.axes.set_aspect(aspect)
# plt.axis('scaled')
# plt.gca().set_aspect(aspect)
plt.savefig('matplotlib.jpg', dpi=100, bbox_inches='tight', pad_inches=0)


im = Image.open('matplotlib.jpg') 

# Get amount of padding to add
fraction_of_padding=(im.size[0]/im.size[1])/aspect
padding_added_pixels=int(((fraction_of_padding * im.size[1])- im.size[1])/2)
im=add_margin(im,padding_added_pixels,0,padding_added_pixels,0,(0,0,0))

im.save('add_margin.jpg', quality=95)




breakpoint()

#r = Rectangle((30., 50.), 60., 50., edgecolor='green', facecolor='none')
# https://docs.astropy.org/en/stable/visualization/wcsaxes/overlays.html

# fig.canvas.draw()
# temp_canvas = fig.canvas
# plt.close()
# pil_image=Image.frombytes('RGB', temp_canvas.get_width_height(),  temp_canvas.tostring_rgb())


#breakpoint()

