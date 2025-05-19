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
from joblib import Parallel, delayed

# Add the parent directory to the Python path
# This allows importing modules from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ptr_utility import create_color_plog

log_color = (0,180, 160) # teal
plog = create_color_plog('crosscor', log_color)

plog("Starting crosscorrelation_subprocess.py")

payload=pickle.load(sys.stdin.buffer)
#payload=pickle.load(open('crosscorrelprocess.pickle','rb'))

def deviation_from_surroundings(data, window_size=20, weight_type="gaussian"):
    """
    Computes the deviation of each entry from its surrounding ±window_size pixels,
    weighted more heavily to nearby pixels.

    Parameters:
        data (np.ndarray): The 1D input array.
        window_size (int): The range around each pixel to consider (default is 20).
        weight_type (str): Type of weighting ('gaussian' or 'triangular').

    Returns:
        np.ndarray: The array of deviations.
    """
    # Create weights
    if weight_type == "gaussian":
        sigma = window_size / 2.0
        weights = np.exp(-0.5 * (np.arange(-window_size, window_size + 1) / sigma) ** 2)
    elif weight_type == "triangular":
        weights = 1 - (np.abs(np.arange(-window_size, window_size + 1)) / (window_size + 1))
    else:
        raise ValueError("Unsupported weight_type. Use 'gaussian' or 'triangular'.")

    # Normalize weights to sum to 1
    weights /= weights.sum()

    # Convolve the data with the weights to get the weighted moving average
    padded_data = np.pad(data, (window_size, window_size), mode="reflect")
    weighted_avg = np.convolve(padded_data, weights, mode="valid")

    # Calculate deviations
    deviations = data - weighted_avg

    return deviations

def sigma_clip_mad_chunk(data_chunk, sigma=2.5, maxiters=10):
    """
    Perform sigma clipping on a chunk of data using MAD as a robust standard deviation estimate.
    """
    if data_chunk.size == 0:
        return data_chunk

    clipped_data = data_chunk.copy()
    mad_scale = 1.4826  # Scaling factor for MAD to approximate standard deviation

    for iter in range(maxiters):
        median = bn.nanmedian(clipped_data)

        if iter < (maxiters - 1):
            std = bn.nanstd(clipped_data)
        else:
            mad = bn.nanmedian(np.abs(clipped_data - median))
            std = mad * mad_scale

        mask = np.abs(clipped_data - median) > sigma * std

        if not np.any(mask):
            break

        clipped_data[mask] = np.nan

    return clipped_data

def sigma_clip_mad_parallel(data, sigma=2.5, maxiters=10, n_jobs=-1, chunk_size=None):
    """
    Perform sigma clipping using MAD in parallel.

    Parameters:
        data (numpy.ndarray): Input array.
        sigma (float): Sigma threshold for clipping.
        maxiters (int): Maximum number of iterations.
        n_jobs (int): Number of parallel jobs (-1 for all CPUs).
        chunk_size (int): Size of each chunk for processing.

    Returns:
        numpy.ndarray: Array with values outside the sigma range replaced by np.nan.
    """
    if data.size == 0:
        return data  # Handle empty input

    if chunk_size is None or chunk_size > len(data):
        chunk_size = max(1, len(data) // (n_jobs * 4))

    # Split data into chunks
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    # Process each chunk in parallel with error handling
    try:
        results = Parallel(n_jobs=n_jobs)(delayed(sigma_clip_mad_chunk)(chunk, sigma, maxiters) for chunk in chunks)
    except Exception as e:
        raise RuntimeError(f"Error during parallel processing: {e}")

    if not results:
        raise ValueError("No results were returned from the parallel processing.")

    # Concatenate results
    return np.concatenate(results)

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

def linear_interpolate(arr):
    nans = np.isnan(arr)
    x = np.arange(len(arr))
    arr[nans] = np.interp(x[nans], x[~nans], arr[~nans])
    return arr

def debanding (bandeddata):

    # Store the current nans as a mask to reapply later
    nan_mask=copy.deepcopy(np.isnan(bandeddata))

    ysize=bandeddata.shape[1]

    sigma_clipped_array=copy.deepcopy(bandeddata)
    sigma_clipped_array = sigma_clip_mad_parallel(sigma_clipped_array, sigma=2.5, maxiters=4)

    # Do rows
    rows_median = bn.nanmedian(sigma_clipped_array,axis=1)
    rows_deviations=deviation_from_surroundings(rows_median, window_size=20, weight_type="gaussian")

    #remove nans
    rows_deviations=linear_interpolate(rows_deviations)

    row_debanded_image=bandeddata-np.tile(rows_deviations[:,None],(1,ysize))
    row_debanded_image= np.subtract(bandeddata,rows_deviations[:,None])

    # Then run this on columns
    # sigma_clipped_array=copy.deepcopy(row_debanded_image)
    # sigma_clipped_array = sigma_clip_mad(sigma_clipped_array, sigma=2.5, maxiters=4)
    columns_median = bn.nanmedian(sigma_clipped_array,axis=0)
    columns_deviations=deviation_from_surroundings(columns_median, window_size=20, weight_type="gaussian")

    #remove nans
    columns_deviations=linear_interpolate(columns_deviations)

    both_debanded_image= row_debanded_image-columns_deviations[None,:]

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
# unique,counts=np.unique(substackimage.ravel()[~np.isnan(substackimage.ravel())].astype(int), return_counts=True)
# m=counts.argmax()
# imageMode=unique[m]

# #Zerothreshing image
# histogramdata=np.column_stack([unique,counts]).astype(np.int32)
# histogramdata[histogramdata[:,0] > -10000]

# #Do some fiddle faddling to figure out the value that goes to zero less
# zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
# breaker=1
# counter=0
# while (breaker != 0):
#     counter=counter+1
#     if not (imageMode-counter) in zeroValueArray[:,0]:
#         if not (imageMode-counter-1) in zeroValueArray[:,0]:
#             if not (imageMode-counter-2) in zeroValueArray[:,0]:
#                 if not (imageMode-counter-3) in zeroValueArray[:,0]:
#                     if not (imageMode-counter-4) in zeroValueArray[:,0]:
#                         if not (imageMode-counter-5) in zeroValueArray[:,0]:
#                             if not (imageMode-counter-6) in zeroValueArray[:,0]:
#                                 if not (imageMode-counter-7) in zeroValueArray[:,0]:
#                                     if not (imageMode-counter-8) in zeroValueArray[:,0]:
#                                         if not (imageMode-counter-9) in zeroValueArray[:,0]:
#                                             if not (imageMode-counter-10) in zeroValueArray[:,0]:
#                                                 if not (imageMode-counter-11) in zeroValueArray[:,0]:
#                                                     if not (imageMode-counter-12) in zeroValueArray[:,0]:
#                                                         if not (imageMode-counter-13) in zeroValueArray[:,0]:
#                                                             if not (imageMode-counter-14) in zeroValueArray[:,0]:
#                                                                 if not (imageMode-counter-15) in zeroValueArray[:,0]:
#                                                                     if not (imageMode-counter-16) in zeroValueArray[:,0]:
#                                                                         zeroValue=(imageMode-counter)
#                                                                         breaker =0

# substackimage[substackimage < zeroValue] = np.nan

# 1) pick your subsampling factor
ny, nx = substackimage.shape
total_px = ny * nx
if total_px > 100_000_000:
    subs = 10
elif total_px >  50_000_000:
    subs = 5
else:
    subs = 2

# 2) grab the strided‐subsample
sample = substackimage[::subs, ::subs]

# 3) compute mode on the sample
vals = sample.ravel()
vals = vals[np.isfinite(vals)].astype(np.int32)
unique, counts = np.unique(vals, return_counts=True)
m = counts.argmax()
imageMode = unique[m]
#plog(f"Calculating Mode (subs={subs}): {time.time()-googtime:.3f} s")

# 4) now build the histogramdata (so we still have unique & counts)
histogramdata = np.column_stack([unique, counts]).astype(np.int32)
# optional filter your histogram (you had this line, though it doesn't assign)
histogramdata = histogramdata[histogramdata[:,0] > -10000]

# 5) find the highest “gap” below imageMode
zeroValueArray = histogramdata[histogramdata[:,0] < imageMode, 0]
zerocounter = 0
while True:
    zerocounter += 1
    test = imageMode - zerocounter
    # look for a run of 17 empty bins below the mode
    if all(((test - offset) not in zeroValueArray) for offset in range(17)):
        zeroValue = test
        break

# 6) apply your zero‐threshold
substackimage[substackimage < zeroValue] = np.nan

#substackimage = debanding(substackimage)

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
    plog(traceback.format_exc())

try:
    os.remove(temporary_substack_directory + output_filename +'temp')
except:
    pass

try:
    os.remove(temporary_substack_directory + output_filename +'temp.npy')
except:
    pass

try:
    os.remove(temporary_substack_directory + output_filename)
except:
    pass

np.save( temporary_substack_directory + output_filename +'temp', substackimage )
os.rename(temporary_substack_directory + output_filename +'temp.npy' ,temporary_substack_directory + output_filename)