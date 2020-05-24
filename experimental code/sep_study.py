# -*- coding: utf-8 -*-
"""
Created on Wed May 20 00:17:59 2020

@author: obs
"""

# -*- coding: utf-8 -*-
"""
Created on Sun Oct 23 17:28:22 2016

@author: wrosing


"""

from ccdproc import ImageFileCollection
from astropy import units as u
from ccdproc import CCDData, Combiner
from math import *
import numpy as np
import ccdproc
import glob
import os
import shutil
import time
import shelve
import datetime
from datetime import timedelta
import sep
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import Ellipse
from scipy import stats
#from ptr_neb_qhy import *

'''

('thresh',
 'npix',
 'tnpix',
 'xmin',
 'xmax',
 'ymin',
 'ymax',
 'x',
 'y',
 'x2',
 'y2',
 'xy',
 'errx2',
 'erry2',
 'errxy',
 'a',
 'b',
 'theta',
 'cxx',
 'cyy',
 'cxy',
 'cflux',
 'flux',
 'cpeak',
 'peak',
 'xcpeak',
 'ycpeak',
 'xpeak',
 'ypeak',
 'flag')


And NOTE:  >>> data = data.byteswap(inplace=True).newbyteorder()

]:
flux, fluxerr, flag = sep.sum_circle(data_sub, objects['x'], objects['y'],
                                     3.0, err=bkg.globalrms, gain=1.0)

Equivalent of FLUX_RADIUS in Source Extractor
In Source Extractor, the FLUX_RADIUS parameter gives the radius of a circle enclosing a desired fraction of the total flux. For example, with the setting PHOT_FLUXFRAC 0.5, FLUX_RADIUS will give the radius of a circle containing half the “total flux” of the object. For the definition of “total flux”, Source Extractor uses its measurement of FLUX_AUTO, which is taken through an elliptical aperture (see above). Thus, with the setting PHOT_FLUXFRAC 1.0, you would find the circle containing the same flux as whatever ellipse Source Extractor used for FLUX_AUTO.

Given a previous calculation of flux as above, calculate the radius for a flux fraction of 0.5:

r, flag = sep.flux_radius(data, objs['x'], objs['y'], 6.*objs['a'], 0.5,
                          normflux=flux, subpix=5)
And for multiple flux fractions:

r, flag = sep.flux_radius(data, objs['x'], objs['y'], 6.*objs['a'],
                          [0.5, 0.6], normflux=flux, subpix=5)
Equivalent of XWIN_IMAGE, YWIN_IMAGE in Source Extractor
Source Extractor’s XWIN_IMAGE, YWIN_IMAGE parameters can be used for more accurate object centroids than the default X_IMAGE, Y_IMAGE. Here, the winpos function provides this behavior. To match Source Extractor exactly, the right sig parameter (giving a description of the effective width) must be used for each object. Source Extractor uses 2.  / 2.35 * (half-light radius) where the half-light radius is calculated using flux_radius with a fraction of 0.5 and a normalizing flux of FLUX_AUTO. The equivalent here is:

sig = 2. / 2.35 * r  # r from sep.flux_radius() above, with fluxfrac = 0.5
xwin, ywin, flag = sep.winpos(data, objs['x'], objs['y'], sig)


'''
def r1(inflt):
    return round(float(inflt), 1)

def r2(inflt):
    return round(float(inflt), 2)

def r3(inflt):
    return round(float(inflt), 3)

def median8(img, hotPix, pLoud=False):
    if pLoud:  print(img.shape, len(hotPix[0]))
    for pix in range(len(hotPix[0])):
        iy = hotPix[0][pix]
        ix = hotPix[1][pix]
        if (0 < iy < img.shape[0] - 2) and (0 < ix < img.shape[1] - 2):
            med = []
            med.append(img[iy-1][ix-1])
            med.append(img[iy-1][ix])
            med.append(img[iy-1][ix+1])
            med.append(img[iy+1][ix-1])
            med.append(img[iy+1][ix])
            med.append(img[iy+1][ix+1])
            med.append(img[iy][ix-1])
            med.append(img[iy][ix+1])
            med2 = np.median(np.array(med))
            if pLoud: print('fixing y, x, z: ', iy, ix, img[iy][ix], med, med2)
            img[iy][ix] = med2
        #This can be slightly improved by edge and corner treatments.
        #There may be an OOB condition.
    return img

# =============================================================================
# hot = ccdproc.CCDData.read('Q:/archive/kq01/lng/md_2_30.fits', unit="adu")
# hotstd = 5*hot.data.std()
# hotmean = hot.data.mean()
# print('Hot mean:  ', hotmean)
# hotpix = np.where(hot.data >= hotstd)  #Do not pick up cold pixels
# print(len(hotpix[0]),' pixels found  >= ', hotstd, ' 5*std.')
# hotest = hot.data[hotpix].max()
# hotestpix =np.where(hot.data >= hotest)
# print(hotestpix, hotest)
# clean = median8(hot.data, hotpix, pLoud=False)
# =============================================================================
    #img = file_list[img]

def fit_quadratic(x, y):
#From Meeus, works fine.
#Abscissa arguments do not need to be ordered for this to work.
#NB Single alpha variable names confict with debugger commands.
    if len(x) == len(y):
        p = 0
        q = 0
        r = 0
        s = 0
        t = 0
        u = 0
        v = 0
        for i in range(len(x)):
            p += x[i]
            q += x[i]**2
            r += x[i]**3
            s += x[i]**4
            t += y[i]
            u += x[i]*y[i]
            v += x[i]**2*y[i]
        n = len(x)
        d = n*q*s +2*p*q*r - q*q*q - p*p*s - n*r*r
        a = (n*q*v + p*r*t + p*q*u - q*q*t - p*p*v - n*r*u)/d
        b = (n*s*u + p*q*v + q*r*t - q*q*u - p*s*t - n*r*v)/d
        c = (q*s*t + q*r*u + p*r*v - q*q*v - p*s*u - r*r*t)/d
        print('Quad;  ', a, b, c)
        try:
            return (a, b, c, -b/(2*a))
        except:
            return (a, b, c)
    else:
        return None

def get_sources(img, bright_limit=2, display=False):
    #print('Incoming image:  ', img)
    data = ccdproc.CCDData.read(img)#, unit='adu')
#    data.data = data.data[252:2163,277:2400]
#    #in-place fix hot pixels
#    data.data = median8(data.data, hotpix)
#    data.write(img[:-4] + 'hpc.fits', overwrite=True)
    xc = data.meta['naxis1']//2
    yc = data.meta['naxis2']//2
#    print (xc,yc)
    focus =data.meta['FOCUSPOS']
    temp = data.meta['FOCUSTEM']



    data2 = data.data
    data3 = data2.astype(np.float32)
    m, s = np.median(data3), np.std(data3)
    #s *= 2


    # plt.imshow(data3, interpolation='nearest', cmap='gray', vmin=m-s, vmax=m+s,\
    #            origin='lower')
    # plt.colorbar()

    bkg = sep.Background(data3)
    mb = np.median(bkg)
    #print('Center pixels:  ', xc, yc, 'Data mean:  ', m, 'Backgrnd mean/std:  ', r2(mb), r2(s))
    #print('Background, rms:  ', r1(bkg.globalback), r1(bkg.globalrms))
    bkg_image = bkg.back()
    #plt.imshow(bkg_image, interpolation='nearest', cmap='gray', origin='lower')
    #plt.colorbar()
    bkg_rms = bkg.rms()
    #plt.imshow(bkg_rms, interpolation='nearest', cmap='gray', origin='lower')
    #plt.colorbar()

    kern = np.ones((5,5))

    img_sub = data3# - bkg
    m, s = np.median(img_sub), np.std(img_sub)
    #print('Data mean:  ', r2(m), 'Focus steps:  ', focus)
    display = False
    if display:
        #plt.imshow(img_sub, interpolation='nearest', cmap='gray', vmin=m-s, vmax=m+s, origin='lower')
        #plt.tight_layout()

        fig, ax = plt.subplots()
        mngr = plt.get_current_fig_manager()
        # to put it into the upper left corner for example:
        mngr.window.setGeometry(50,50,1024, 1024)
        #mngr.window.tight_layout()
        plt.imshow(img_sub, interpolation='nearest', cmap='gray', vmin=m-s, vmax=m+s, origin='lower')
        plt.tight_layout()

    objects = sep.extract(img_sub, 4.5, err=bkg.globalrms, minarea=30)#, filter_kernel=kern)
    objects.sort(order = 'cflux')
    #print('No. of detections:  ', len(objects))


    counter = 1
    elapsed = 0
    result = []
    spots = []
    for frame in objects:
        a0 = frame['a']
        b0 =  frame['b']
        #print (a0, b0, (a0 - b0)/(a0 + b0)/2)
#        if (a0 - b0)/(a0 + b0)/2 > 0.1:
#            continue
        r0 = 2*round(sqrt(a0**2 +b0**2), 2)
        #print(r1(frame['x']), r1(frame['y']), r1(frame['cflux']), r2(r0))
        # if r1(frame['x']) == 1111.0:
        #     #print(frame)
        #     pass
        result.append((r1(frame['x']), r1(frame['y']), r1(frame['cflux']), r2(r0), focus, temp))
        spots.append(r2(r0))
        spot = np.array(spots)
    spot = np.median(spot[-10:])
    print(spot, focus)



#from matplotlib.patches import Ellipse
#
## plot background-subtracted image
#fig, ax = plt.subplots()
#m, s = np.mean(data_sub), np.std(data_sub)
#im = ax.imshow(data_sub, interpolation='nearest', cmap='gray',
#               vmin=m-s, vmax=m+s, origin='lower')
#
## plot an ellipse for each object
#for i in range(len(objects)):
#    e = Ellipse(xy=(objects['x'][i], objects['y'][i]),
#                width=6*objects['a'][i],
#                height=6*objects['b'][i],
#                angle=objects['theta'][i] * 180. / np.pi)
#    e.set_facecolor('none')
#    e.set_edgecolor('red')
#    ax.add_artist(e)

if __name__ == '__main__':
    print('sep is starting')
    path = 'D:/archive/archive/kb01/20200522/to_AWS/'
    #path = 'C:\\Users\\obs\\Documents\\PlaneWave Instruments\\Images\\Focus\\2019-02-20\\New folder\\'
    fits_file_list = glob.glob(path + '*EX01*.f*t*')

    print('Num files found:  ', len(fits_file_list))

    for image in fits_file_list:
        focus = get_sources(image, bright_limit=3, display=False)
    print(focus)






