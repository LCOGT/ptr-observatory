import sys
import pickle
from astropy.nddata import block_reduce
import numpy as np
import sep
from astropy.table import Table
from astropy.io import fits
from planewave import platesolve
import os
#from astropy.table import QTable
#from astropy.modeling import models
#from astropy.modeling.models import Moffat2D
#from astropy.convolution import discretize_model
#from astropy.utils.exceptions import AstropyUserWarning
#import warnings
import time

#sources = Table.read(im_path + text_name.replace('.txt', '.sep'), format='csv')
sources = Table.read('eco1-ec002c-20230721-00006962-EX00.sep', format='csv')

xpixelsize = 4096
ypixelsize = 4096


# Make blank synthetic image
synthetic_image = np.zeros([xpixelsize, ypixelsize])
# Add a sky background
synthetic_image = synthetic_image + 200

shape = (xpixelsize, ypixelsize)

modelstar = [[ 0.1 , 0.2 , 0.4,  0.2, 0.1], 
            [ 0.2 , 0.4 , 0.8,  0.4, 0.2],
            [ 0.4 , 0.8 , 1,  0.8, 0.4],
            [ 0.2 , 0.4 , 0.8,  0.4, 0.2],
            [ 0.1 , 0.2 , 0.4,  0.2, 0.1]]

#print (np.array(modelstar[0]))

modelstar=np.array(modelstar)

tie=time.time()
for addingstar in sources:
    #print (addingstar)
    x = round(addingstar['x'] -1)
    y = round(addingstar['y'] -1)
    peak = int(addingstar['peak'])
    
    # Add star to numpy array as a slice
    synthetic_image[x-2:x+3,y-2:y+3] += peak*modelstar
    
print ( time.time() - tie)


hdufocus = fits.PrimaryHDU()
hdufocus.data = np.array(synthetic_image, dtype=np.int16)
#hdufocus.header = hduheader
#hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
#hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
#hdufocus.writeto(cal_path + 'platesolvetemp.fits', overwrite=True, output_verify='silentfix')
hdufocus.writeto('platesolvetemp.fits', overwrite=True, output_verify='silentfix')
#pixscale = hdufocus.header['PIXSCALE']

#breakpoint()


breakpoint()

