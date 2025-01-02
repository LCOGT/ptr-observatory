# -*- coding: utf-8 -*-
"""
Created on Thu May  9 11:08:48 2024

@author: psyfi
"""

import pickle
import sys
from image_registration import cross_correlation_shifts
from astropy.nddata import block_reduce
import numpy as np
import traceback
import os
import copy
import bottleneck as bn
#from astropy.stats import sigma_clip

payload=pickle.load(sys.stdin.buffer)
#payload=pickle.load(open('crosscorrelprocess.pickle','rb'))


def sigma_clip_mad(data, sigma=2.5, maxiters=10):
    """
    Perform sigma clipping using MAD as a robust standard deviation estimate.
    
    Parameters:
        data (numpy.ndarray): Input array.
        sigma (float): Sigma threshold for clipping.
        maxiters (int): Maximum number of iterations.
    
    Returns:
        numpy.ndarray: Array with values outside the sigma range replaced by np.nan.
    """
    clipped_data = data.copy()  # Copy the data to avoid modifying the original array
    
    for iter in range(maxiters):

        if iter < (maxiters-1):
            # Compute the mean and standard deviation, ignoring NaN values
            median = bn.nanmedian(clipped_data)
            std = bn.nanstd(clipped_data)
            
            # Identify the mask of outliers
            mask = np.abs(clipped_data - median) > sigma * std
        else:
            # Compute the median of the current data
            median = bn.nanmedian(clipped_data)
            # Compute the MAD and scale it to approximate standard deviation
            mad = bn.nanmedian(np.abs(clipped_data - median))
            mad_std = mad * 1.4826
            
            # Identify the mask of outliers
            mask = np.abs(clipped_data - median) > sigma * mad_std
        
        # If no more values are being clipped, break the loop
        if not np.any(mask):
            break
        
        # Replace outliers with np.nan
        clipped_data[mask] = np.nan
    
    return clipped_data

def debanding (bandeddata):

    # Store the current nans as a mask to reapply later
    nan_mask=copy.deepcopy(np.isnan(bandeddata))    

    ysize=bandeddata.shape[1]

    sigma_clipped_array=copy.deepcopy(bandeddata)    
    sigma_clipped_array = sigma_clip_mad(sigma_clipped_array, sigma=2.5, maxiters=4)
    
    # Do rows
    rows_median = bn.nanmedian(sigma_clipped_array,axis=1)
    rows_median[np.isnan(rows_median)] = bn.nanmedian(rows_median)
    row_debanded_image=bandeddata-np.tile(rows_median[:,None],(1,ysize))
    row_debanded_image= np.subtract(bandeddata,rows_median[:,None])

    # Then run this on columns
    sigma_clipped_array=copy.deepcopy(row_debanded_image)
    sigma_clipped_array = sigma_clip_mad(sigma_clipped_array, sigma=2.5, maxiters=4)
    columns_median = bn.nanmedian(sigma_clipped_array,axis=0)
    columns_median[np.isnan(columns_median)] = bn.nanmedian(columns_median)
    both_debanded_image= row_debanded_image-columns_median[None,:]

    #Reapply the original nans after debanding
    both_debanded_image[nan_mask] = np.nan

    return both_debanded_image


reference_image=payload[0]
substackimage=payload[1]
temporary_substack_directory=payload[2]
output_filename=payload[3]
is_osc=payload[4]

# Really need to thresh the image
# int_array_flattened=substackimage.astype(int).ravel()
# int_array_flattened=int_array_flattened[int_array_flattened > -10000]
# unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
unique,counts=np.unique(substackimage.ravel()[~np.isnan(substackimage.ravel())].astype(int), return_counts=True)
m=counts.argmax()
imageMode=unique[m]

#Zerothreshing image
histogramdata=np.column_stack([unique,counts]).astype(np.int32)
histogramdata[histogramdata[:,0] > -10000]

#Do some fiddle faddling to figure out the value that goes to zero less
zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
breaker=1
counter=0
while (breaker != 0):
    counter=counter+1
    if not (imageMode-counter) in zeroValueArray[:,0]:
        if not (imageMode-counter-1) in zeroValueArray[:,0]:
            if not (imageMode-counter-2) in zeroValueArray[:,0]:
                if not (imageMode-counter-3) in zeroValueArray[:,0]:
                    if not (imageMode-counter-4) in zeroValueArray[:,0]:
                        if not (imageMode-counter-5) in zeroValueArray[:,0]:
                            if not (imageMode-counter-6) in zeroValueArray[:,0]:
                                if not (imageMode-counter-7) in zeroValueArray[:,0]:
                                    if not (imageMode-counter-8) in zeroValueArray[:,0]:
                                        if not (imageMode-counter-9) in zeroValueArray[:,0]:
                                            if not (imageMode-counter-10) in zeroValueArray[:,0]:
                                                if not (imageMode-counter-11) in zeroValueArray[:,0]:
                                                    if not (imageMode-counter-12) in zeroValueArray[:,0]:                                                        
                                                        if not (imageMode-counter-13) in zeroValueArray[:,0]:
                                                            if not (imageMode-counter-14) in zeroValueArray[:,0]:
                                                                if not (imageMode-counter-15) in zeroValueArray[:,0]:
                                                                    if not (imageMode-counter-16) in zeroValueArray[:,0]: 
                                                                        zeroValue=(imageMode-counter)
                                                                        breaker =0
                                                        
substackimage[substackimage < zeroValue] = np.nan

substackimage = debanding(substackimage)

edge_crop=100
xoff, yoff = cross_correlation_shifts(block_reduce(reference_image[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=np.nanmean), block_reduce(substackimage[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=np.nanmean),zeromean=False)  
imageshift=[round(-yoff*3),round(-xoff*3)]

if imageshift[0] > 100 or imageshift[1] > 100:
    imageshift = [0,0]

try:
    if abs(imageshift[0]) > 0:
        imageshiftabs=int(abs(imageshift[0]))
        # If it is an OSC, it needs to be an even number
        if is_osc:
            if (imageshiftabs & 0x1) == 1:
                imageshiftabs=imageshiftabs+1
        if imageshift[0] > 0:
            imageshiftsign = 1
        else:
            imageshiftsign = -1

        substackimage=np.roll(substackimage, imageshiftabs*imageshiftsign, axis=0)

    if abs(imageshift[1]) > 0:
        imageshiftabs=int(abs(imageshift[1]))
        # If it is an OSC, it needs to be an even number
        if is_osc:
            if (imageshiftabs & 0x1) == 1:
                imageshiftabs=imageshiftabs+1
        if imageshift[1] > 0:
            imageshiftsign = 1
        else:
            imageshiftsign = -1
        substackimage=np.roll(substackimage, imageshiftabs*imageshiftsign, axis=1)
except:
    print(traceback.format_exc())
    
np.save( temporary_substack_directory + output_filename +'temp', substackimage )
os.rename(temporary_substack_directory + output_filename +'temp.npy' ,temporary_substack_directory + output_filename)