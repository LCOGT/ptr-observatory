# -*- coding: utf-8 -*-
"""
post_exposure_subprocess.py  post_exposure_subprocess.py

Created on Tue May  7 18:29:14 2024

@author: psyfi
"""


import sys
import time
import pickle
import shelve
from astropy.io import fits
import numpy as np
import bottleneck as bn
import datetime
from astropy.time import Time
import copy
import threading
from astropy.coordinates import SkyCoord
import os
from astropy.nddata import block_reduce
import subprocess
import traceback
#from image_registration import cross_correlation_shifts
#from astropy.stats import sigma_clip
from joblib import Parallel, delayed
from scipy.ndimage import convolve
#from astropy.convolution import interpolate_replace_nans, Gaussian2DKernel

# Add the parent directory to the Python path
# This allows importing modules from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ptr_utility import create_color_plog

log_color = (180, 100, 240) # bright purple
plog = create_color_plog('postexp', log_color)

plog('Starting post_exposure_subprocess.py')

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

def linear_interpolate(arr):
    nans = np.isnan(arr)
    x = np.arange(len(arr))
    arr[nans] = np.interp(x[nans], x[~nans], arr[~nans])
    return arr

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

# Note this is a thread!
def write_raw_file_out(packet):

    (raw, raw_name, hdudata, hduheader, frame_type, current_icrs_ra, current_icrs_dec, altpath, altfolder, dayobs, camera_path, altpath) = packet

    # Make sure normal paths exist
    os.makedirs(
        camera_path + dayobs, exist_ok=True
    )
    os.makedirs(
        camera_path + dayobs + "/raw/", exist_ok=True
    )
    os.makedirs(
        camera_path + dayobs + "/reduced/", exist_ok=True
    )
    os.makedirs(
        camera_path + dayobs + "/calib/", exist_ok=True)

    # Make  sure the alt paths exist
    if raw == 'raw_alt_path':
        os.makedirs(
            altpath + dayobs, exist_ok=True
        )
        os.makedirs(
            altpath + dayobs + "/raw/", exist_ok=True
        )
        os.makedirs(
            altpath + dayobs + "/reduced/", exist_ok=True
        )
        os.makedirs(
            altpath + dayobs + "/calib/", exist_ok=True)

    hdu = fits.PrimaryHDU()
    hdu.data = hdudata
    hdu.header = hduheader

    hdu.header["DATE"] = (
        datetime.date.strftime(
            datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
        ),
        "Date FITS file was written",
    )


    hdu.writeto( raw_name, overwrite=True, output_verify='silentfix')
    try:
        hdu.close()
    except:
        pass
    del hdu

# set this to True to set this subprocess to normal everyday mode
## set it to False if you are running straight from the pickle.
normal_operation=True

try:
    payload=pickle.load(sys.stdin.buffer)

except:
    try:
        payload=pickle.load(open('testpostprocess.pickle','rb'))
        plog ("ignoring exception")
    except:
        plog ("post_exposure couldn't get its' payload")
        sys.exit()
#expresult={}
#A long tuple unpack of the payload
(img, pier_side, is_osc, frame_type, reject_flat_by_known_gain, avg_mnt, avg_foc, avg_rot, \
 setpoint, tempccdtemp, ccd_humidity, ccd_pressure, darkslide_state, exposure_time, \
 this_exposure_filter, exposure_filter_offset, opt, observer_user_name, \
 azimuth_of_observation, altitude_of_observation, airmass_of_observation, pixscale, \
 smartstackid,sskcounter,Nsmartstack, longstackid, ra_at_time_of_exposure, \
 dec_at_time_of_exposure, manually_requested_calibration, object_name, object_specf, \
 ha_corr, dec_corr, focus_position, selfconfig, camera_device_name, camera_known_gain, \
 camera_known_readnoise, start_time_of_observation, observer_user_id, selfcamera_path, \
 solve_it, next_seq, zoom_factor, useastrometrynet, substack, expected_endpoint_of_substack_exposure, \
 substack_start_time,readout_estimate,readout_time, sub_stacker_midpoints,corrected_ra_for_header, \
 corrected_dec_for_header, substacker_filenames, dayobs, exposure_filter_offset,null_filterwheel, \
 wema_config, smartstackthread_filename, septhread_filename, mainjpegthread_filename,\
 platesolvethread_filename, number_of_exposures_requested, unique_batch_code,exposure_in_nighttime) = payload

pane = opt.get('pane')

a_timer=time.time()

cam_config = selfconfig['camera'][camera_device_name]
cam_settings = cam_config['settings']
cam_alias = cam_config["name"]
current_camera_name = cam_config["name"]

# init this value
selfalt_path = 'no'

# We are assuming that we should use the main rotator and focuser, but we should pass those in
# the payload rather than assuming.
rotator_name = selfconfig['device_roles']['main_rotator']
if selfconfig['device_roles']['main_rotator'] == None:
    rotator_alias = None
else:
    rotator_alias = selfconfig['rotator'][rotator_name]['name']
focuser_name = selfconfig['device_roles']['main_focuser']
focuser_alias = selfconfig['focuser'][focuser_name]['name']
if len(selfconfig['rotator']) > 1:
    plog('Warning: more than one rotator in config file, so post_exposure_subprocess.py is arbitrarily choosing to use main_rotator.')
    plog('Since there is more than one rotator configured, the script should be modified to pass the correct rotator name as an argument.')
if len(selfconfig['focuser']) > 1:
    plog('Warning: more than one focuser in config file, so post_exposure_subprocess.py is arbitrarily choosing to use main_focuser.')
    plog('Since there is more than one focuser configured, the script should be modified to pass the correct rotator name as an argument.')

# hack to get telescope working: choose the first one in the dict. This will probably work as expected
# unless there are ever more than one telescope in the config file, so we'll check for that and
# Send a warning if this happens.
telescope_name = list(selfconfig['telescope'].keys())[0]
telescope_config = selfconfig['telescope'][telescope_name]
if len(selfconfig['telescope']) > 1:
    plog('Warning: more than one telescope in config file, and post_exposure_subprocess.py is picking one at random.')
    plog('If there is more than one telescope configured, the correct one should be passed as an argument to this script.')

obsname=selfconfig['obs_id']
localcalibrationdirectory=selfconfig['local_calibration_path'] + selfconfig['obs_id'] + '/'
tempfrontcalib=obsname + '_' + cam_alias +'_'

localcalibmastersdirectory= localcalibrationdirectory+ "archive/" + cam_alias + "/calibmasters" + "/"

#plog (substack)

#breakpoint()

# Get the calibrated image whether that is a substack or a normal image.
if substack:

    exp_of_substacks=int(exposure_time / len(substacker_filenames))
    # Get list of substack files needed and wait for them.
    waiting_for_substacker_filenames=copy.deepcopy(substacker_filenames)

    # This process is set to spin up early, so it loads
    # and waits for a filename token to get started.
    file_wait_timeout_timer=time.time()



    while ((len(waiting_for_substacker_filenames)) > 0) and (time.time()-file_wait_timeout_timer < 600):
        for tempfilename in waiting_for_substacker_filenames:
            if os.path.exists(tempfilename):
                waiting_for_substacker_filenames.remove(tempfilename)
        time.sleep(0.2)

    if time.time()-file_wait_timeout_timer > 599:
        sys.exit()

    temporary_substack_directory=localcalibrationdirectory + "substacks/" + str(time.time()).replace('.','')

    if not os.path.exists(localcalibrationdirectory + "substacks/"):
        os.makedirs(localcalibrationdirectory + "substacks/")
    if not os.path.exists(temporary_substack_directory):
        os.makedirs(temporary_substack_directory)


    counter=0

    crosscorrelation_subprocess_array=[]

    crosscorrel_filename_waiter=[]

    for substackfilename in substacker_filenames:

        substackimage=np.load(substackfilename).astype('float32')

        im_path_r = selfcamera_path
        raw_path = im_path_r + dayobs + "/raw/"
        raw_name00 = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name + '_' + str(frame_type) + '_' + str(this_exposure_filter)
            + "-"
            + dayobs
            + "-"
            + next_seq
            + "-EX"
            + "00ss"+str(counter+1)+".fits"
        )
        if selfconfig['save_substack_components_raws']:


            # Create a blank FITS header
            substackheader = fits.Header()

            # thread = threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_path', raw_path  + raw_name00, copy.deepcopy(substackimage),substackheader, \
            #                                    frame_type, ra_at_time_of_exposure, dec_at_time_of_exposure,'no','deprecated', dayobs, im_path_r, selfalt_path)),))
            # thread.daemon = False # These need to be daemons because this parent thread will end imminently
            # thread.start()

            payload = (
                'raw_path',
                raw_path + raw_name00,
                substackimage.copy(),          # a single array copy
                # if you mutate substackheader elsewhere too, do:
                # substackheader.copy()
                substackheader,
                frame_type,
                ra_at_time_of_exposure,
                dec_at_time_of_exposure,
                'no',
                'deprecated',
                dayobs,
                im_path_r,
                selfalt_path
            )

            thread = threading.Thread(
                target=write_raw_file_out,
                args=(payload,),
                daemon=False            # These need to be daemons because this parent thread will end imminently
            )
            thread.start()

        #plog (substackimage.shape)
        #notsubstackimage=np.load(substackfilename)
        #plog (notsubstackimage.shape)
        try:
            if exp_of_substacks == 10:
                #plog ("Dedarking 0")
                #loadbias=np.load(localcalibrationdirectory + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'tensecBIASDARK_master_bin1.npy')
                #plog (loadbias.shape)
                #substackimage=copy.deepcopy(substackimage - np.load(localcalibrationdirectory + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'tensecBIASDARK_master_bin1.npy'))# - g_dev['cam'].darkFiles['tensec_exposure_biasdark'])
                substackimage=substackimage - np.load(localcalibrationdirectory + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'tensecBIASDARK_master_bin1.npy')# - g_dev['cam'].darkFiles['tensec_exposure_biasdark'])
            else:
                #substackimage=copy.deepcopy(substackimage - np.load(localcalibrationdirectory + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'thirtysecBIASDARK_master_bin1.npy'))
                substackimage=substackimage - np.load(localcalibrationdirectory + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'thirtysecBIASDARK_master_bin1.npy')
        except:
            plog(traceback.format_exc())
            plog ("Couldn't biasdark substack")
            pass
        try:
            #substackimage = copy.deepcopy(np.divide(substackimage, np.load(localcalibrationdirectory  + 'archive/' + cam_alias + '/calibmasters/' + 'masterFlat_' + this_exposure_filter + "_bin" + str(1) +'.npy')))
            substackimage = np.divide(substackimage, np.load(localcalibrationdirectory  + 'archive/' + cam_alias + '/calibmasters/' + 'masterFlat_' + this_exposure_filter + "_bin" + str(1) +'.npy'))
        except:
            plog ("couldn't flat field substack")
            #breakpoint()
            pass
        # Bad pixel map sub stack array
        try:
            substackimage[np.load(localcalibrationdirectory  + 'archive/' + cam_alias + '/calibmasters/' + tempfrontcalib + 'badpixelmask_bin1.npy')] = np.nan
        except:
            plog ("Couldn't badpixel substack")
            pass



        # If it is the first image, just plonk it in the array.
        if counter == 0:
            # Set up the array
            sub_stacker_array = np.zeros((substackimage.shape[0],substackimage.shape[1],len(substacker_filenames)), dtype=np.float32)


            # Really need to thresh the image
            googtime=time.time()
            # # int_array_flattened=substackimage.astype(int).ravel()
            # # int_array_flattened=int_array_flattened[int_array_flattened > -10000]
            # # unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
            # unique,counts=np.unique(substackimage.ravel()[~np.isnan(substackimage.ravel())].astype(np.int32), return_counts=True)
            # m=counts.argmax()
            # imageMode=unique[m]

            # plog ("Calculating Mode: " +str(time.time()-googtime))

            # #Zerothreshing image
            # #googtime=time.time()
            # histogramdata=np.column_stack([unique,counts]).astype(np.int32)
            # histogramdata[histogramdata[:,0] > -10000]
            # #Do some fiddle faddling to figure out the value that goes to zero less
            # zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
            # breaker=1
            # zerocounter=0
            # while (breaker != 0):
            #     zerocounter=zerocounter+1
            #     if not (imageMode-zerocounter) in zeroValueArray[:,0]:
            #         if not (imageMode-zerocounter-1) in zeroValueArray[:,0]:
            #             if not (imageMode-zerocounter-2) in zeroValueArray[:,0]:
            #                 if not (imageMode-zerocounter-3) in zeroValueArray[:,0]:
            #                     if not (imageMode-zerocounter-4) in zeroValueArray[:,0]:
            #                         if not (imageMode-zerocounter-5) in zeroValueArray[:,0]:
            #                             if not (imageMode-zerocounter-6) in zeroValueArray[:,0]:
            #                                 if not (imageMode-zerocounter-7) in zeroValueArray[:,0]:
            #                                     if not (imageMode-zerocounter-8) in zeroValueArray[:,0]:
            #                                         if not (imageMode-zerocounter-9) in zeroValueArray[:,0]:
            #                                             if not (imageMode-zerocounter-10) in zeroValueArray[:,0]:
            #                                                 if not (imageMode-zerocounter-11) in zeroValueArray[:,0]:
            #                                                     if not (imageMode-zerocounter-12) in zeroValueArray[:,0]:
            #                                                         if not (imageMode-zerocounter-13) in zeroValueArray[:,0]:
            #                                                             if not (imageMode-zerocounter-14) in zeroValueArray[:,0]:
            #                                                                 if not (imageMode-zerocounter-15) in zeroValueArray[:,0]:
            #                                                                     if not (imageMode-zerocounter-16) in zeroValueArray[:,0]:
            #                                                                         zeroValue=(imageMode-zerocounter)
            #                                                                         breaker =0

            # substackimage[substackimage < zeroValue] = np.nan
            # del unique
            # del counts
            # Deband the image
            #plog (bn.nanmax(substackimage))
            #substackimage = debanding(substackimage)
            #plog (bn.nanmax(substackimage))

            #breakpoint()

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
            plog(f"Calculating Mode (subs={subs}): {time.time()-googtime:.3f} s")

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

            #sub_stacker_array[:,:,0] = copy.deepcopy(substackimage)
            sub_stacker_array[:,:,0] = substackimage.copy()

        else:


            output_filename='crosscorrel' + str(counter-1) + '.npy'
            pickler=[]
            pickler.append(sub_stacker_array[:,:,0])
            pickler.append(substackimage)
            pickler.append(temporary_substack_directory)
            pickler.append(output_filename)
            pickler.append(is_osc)

            crosscorrel_filename_waiter.append(temporary_substack_directory + output_filename)

            if normal_operation:
                # crosscorrelation_subprocess_array.append(subprocess.Popen(['python','subprocesses/crosscorrelation_subprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0))
                cross_proc=subprocess.Popen(['python','subprocesses/crosscorrelation_subprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
            else:
                cross_proc=subprocess.Popen(['python','crosscorrelation_subprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
            #plog (counter-1)

            if False:
                #NB set this path to create test pickle for makejpeg routine.
                pickle.dump(pickler, open('crosscorrelprocess.pickle','wb'))

            pickle.dump(pickler, cross_proc.stdin)
            cross_proc.stdin.close()
            cross_proc.stdout.close()
            crosscorrelation_subprocess_array.append(cross_proc)

        counter=counter+1


    counter=1

    for waitfile in crosscorrel_filename_waiter:

        file_wait_timeout_timer=time.time()
        while (not os.path.exists(waitfile)) and (time.time()-file_wait_timeout_timer < 600) :
            #plog ("waiting for " + str(waitfile))
            time.sleep(0.2)

        if time.time()-file_wait_timeout_timer > 599:
            sys.exit()



        sub_stacker_array[:,:,counter] = np.load(waitfile)
        counter=counter+1

    # Once collected and done, nanmedian the array into the single image

    img=bn.nanmedian(sub_stacker_array, axis=2) * len(substacker_filenames)

    #plog (bn.nanmax(img))

    # Once we've got the substack stacked, delete the original images
    for waitfile in crosscorrel_filename_waiter:
        try:
            os.remove(waitfile)
        except:
            pass


# Hold onto the absolutely raw frame for export to disk
# We don't actually send absolutely raw frames to s3 or the PIPE anymore
# As it adds unnecessary costs to s3 (multiple downloads) and is really sorta unnecessary just in general for the PIPE
# But we still dump out the absolutely raw frame for telops at the site.
# So this holds onto the original frame until the very end.
#absolutely_raw_frame=copy.deepcopy(np.asarray(img,dtype='np.float32'))
absolutely_raw_frame=copy.deepcopy(img)
img=np.asarray(img,dtype=np.float32)

obsid_path = str(selfconfig["archive_path"] + '/' + obsname + '/').replace('//','/')

post_exposure_process_timer=time.time()
ix, iy = img.shape

# Update readout time list
readout_shelf = shelve.open(obsid_path + 'ptr_night_shelf/' + 'readout' + cam_alias + str(obsname))
try:
    readout_list=readout_shelf['readout_list']
except:
    readout_list=[]

readout_list.append(readout_estimate)

too_long=True
while too_long:
    if len(readout_list) > 100:
        readout_list.pop(0)
    else:
        too_long = False

readout_shelf['readout_list'] = readout_list
readout_shelf.close()

image_saturation_level = cam_settings["saturate"]

try:
    # THIS IS THE SECTION WHERE THE ORIGINAL FITS IMAGES ARE ROTATED
    # OR TRANSPOSED. THESE ARE ONLY USED TO ORIENTATE THE FITS
    # IF THERE IS A MAJOR PROBLEM with the original orientation
    # If you want to change the display on the UI, use the jpeg
    # alterations later on.
    if cam_settings["transpose_fits"]:
        hdu = fits.PrimaryHDU(
            img.transpose().astype('float32'))
    elif cam_settings["flipx_fits"]:
        hdu = fits.PrimaryHDU(
            np.fliplr(img.astype('float32'))
        )
    elif cam_settings["flipy_fits"]:
        hdu = fits.PrimaryHDU(
            np.flipud(img.astype('float32'))
        )
    elif cam_settings["rotate90_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'))
        )
    elif cam_settings["rotate180_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'),2)
        )
    elif cam_settings["rotate270_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'),3)
        )
    else:
        hdu = fits.PrimaryHDU(
            img.astype('float32')
        )
    del img

    #selfnative_bin = cam_settings["native_bin"]
    selfnative_bin=1
    if not pixscale == None:
        if pixscale < 0.3:
            selfnative_bin=3
        elif pixscale < 0.6:
            selfnative_bin=2
    # else:


    broadband_ss_biasdark_exp_time = cam_config['settings']['smart_stack_exposure_time']
    narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * cam_config['settings']['smart_stack_exposure_NB_multiplier']
    dark_exp_time = cam_config['settings']['dark_exposure']
    do_bias_also=False

    #ALL images are calibrated at the site.... WHY WOULD YOU NOT?
    #The cost is largely I/O and to do that on multiple computers at multiple times
    #Is a large bottleneck and cost in time and, in s3, $
    if not manually_requested_calibration and not substack:

        try:
            # If not a smartstack use a scaled masterdark
            timetakenquickdark=time.time()
            try:
                if smartstackid == 'no':




                    # Variable to sort out an intermediate dark when between two scalable darks.
                    fraction_through_range=0

                    plog (exposure_time)
                    # If exactly the right exposure time, use the biasdark that exists
                    if exposure_time == 0.00004:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'fortymicrosecondBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.0004:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'fourhundredmicrosecondBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.0045:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'pointzerozerofourfiveBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.015:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'onepointfivepercentBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.05:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'fivepercentBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.1:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'tenpercentBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.25:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'quartersecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.5:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'halfsecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 0.75:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'onepointfivepercentBIASDARK_master_bin1.npy'))
                    elif exposure_time == 1.0:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'onesecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 1.5:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'oneandahalfsecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 2.0:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'twosecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 3.5:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'threepointfivesecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 5.0:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'fivesecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 7.5:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'sevenpointfivesecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 10:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'tensecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 15:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'fifteensecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 20:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'twentysecBIASDARK_master_bin1.npy'))
                    elif exposure_time == 30:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'thirtysecBIASDARK_master_bin1.npy'))
                    elif exposure_time == broadband_ss_biasdark_exp_time:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssBIASDARK_master_bin1.npy'))
                    elif exposure_time == narrowband_ss_biasdark_exp_time:
                        hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssBIASDARK_master_bin1.npy'))
                    elif exposure_time < 0.5:
                        hdu.data=hdu.data-np.load(localcalibmastersdirectory + tempfrontcalib + 'halfsecondDARK_master_bin1.npy')#np.load(g_dev['cam'].darkFiles['halfsec_exposure_dark']*exposure_time)
                        do_bias_also=True
                    elif exposure_time < 2.0:
                        fraction_through_range=(exposure_time-0.5)/(2.0-0.5)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + '2secondDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'halfsecondDARK_master_bin1.npy'))
                        hdu.data=hdu.data-(tempmasterDark*exposure_time)
                        do_bias_also=True
                        del tempmasterDark
                    elif exposure_time < 10.0:
                        fraction_through_range=(exposure_time-2)/(10.0-2.0)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + '10secondDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + '2secondDARK_master_bin1.npy'))
                        hdu.data=hdu.data-(tempmasterDark*exposure_time)
                        do_bias_also=True
                        del tempmasterDark
                    elif exposure_time < broadband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-10)/(broadband_ss_biasdark_exp_time-10.0)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + '10secondDARK_master_bin1.npy'))
                        hdu.data=hdu.data-(tempmasterDark*exposure_time)
                        do_bias_also=True
                        del tempmasterDark
                    elif exposure_time < narrowband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssDARK_master_bin1.npy'))
                        hdu.data=hdu.data-(tempmasterDark*exposure_time)
                        do_bias_also=True
                        del tempmasterDark
                    elif dark_exp_time > narrowband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy'))
                        hdu.data=hdu.data-(tempmasterDark*exposure_time)
                        do_bias_also=True
                        del tempmasterDark
                    else:
                        do_bias_also=True
                        hdu.data=hdu.data-(np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy')*exposure_time)
                elif exposure_time == broadband_ss_biasdark_exp_time:
                    hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssBIASDARK_master_bin1.npy'))
                elif exposure_time == narrowband_ss_biasdark_exp_time:
                    hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssBIASDARK_master_bin1.npy'))
                else:
                    plog ("DUNNO WHAT HAPPENED!")
                    hdu.data = hdu.data - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy')
                    hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy') * exposure_time)
            except:
                try:
                    hdu.data = hdu.data - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy')
                    hdu.data = hdu.data - (np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy') * exposure_time)
                except:
                    plog ("Could not bias or dark file.")
        except Exception as e:
            plog("debias/darking light frame failed: ", e)

        # If using a scaled dark remove the bias as well
        if do_bias_also:
            hdu.data = hdu.data - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy') #g_dev['cam'].biasFiles[str(1)]



        # Quick flat flat frame
        #breakpoint()
        #data_save = hdu.data
        try:
            hdu.data = np.divide(hdu.data, np.load(localcalibmastersdirectory + 'masterFlat_'+this_exposure_filter + "_bin" + str(1) +'.npy'))
        except Exception as e:
            plog("flatting light frame failed", e)
            #hdu.data = data_save


        try:
            hdu.data[np.load(localcalibmastersdirectory + tempfrontcalib + 'badpixelmask_bin1.npy')] = np.nan

        except Exception as e:
            plog("Bad Pixel Masking light frame failed: ", e)

        hdu.data = hdu.data.astype('float32')


    # DITTO HERE, this is a routine that rejects very low pixel counts
    # Based on expectations that the sky distribution drops to zero to the left of the mode value
    # Without doing it here, we end up doing it twice... we need to do it here anyway for local smartstacks
    # So we should just do it at site and save the PIPE some time.
    # Really need to thresh the image
    #
    # But for substacks, that would already have been done in the substack routine
    # This is just for single images.
    if not substack:
        googtime=time.time()


        # unique,counts=np.unique(hdu.data.ravel()[~np.isnan(hdu.data.ravel())].astype(np.int32), return_counts=True)
        # m=counts.argmax()
        # imageMode=unique[m]
        plog ("Calculated Mode: " + str(imageMode))
        plog ("Calculating Mode: " +str(time.time()-googtime))


        # # Zerothreshing image
        # googtime=time.time()
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

        # hdu.data[hdu.data < zeroValue] = np.nan
        
        # 1) pick your subsampling factor
        ny, nx = hdu.data.shape
        total_px = ny * nx
        if total_px > 100_000_000:
            subs = 10
        elif total_px >  50_000_000:
            subs = 5
        else:
            subs = 2

        # 2) grab the strided‐subsample
        sample = hdu.data[::subs, ::subs]

        # 3) compute mode on the sample
        vals = sample.ravel()
        vals = vals[np.isfinite(vals)].astype(np.int32)
        unique, counts = np.unique(vals, return_counts=True)
        m = counts.argmax()
        imageMode = unique[m]
        plog(f"Calculating Mode (subs={subs}): {time.time()-googtime:.3f} s")

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
        hdu.data[hdu.data < zeroValue] = np.nan

        plog ("Zero Threshing Image: " +str(time.time()-googtime))

        #hdu.data = debanding(hdu.data)

    googtime=time.time()
##########################################


    #################### HERE IS WHERE FULLY REDUCED PLATESOLVE IS SENT OFF
    ##### THIS IS CURRENTLY IN CONSTRUCTION, MOST SITES THIS IS NOT ENABLED.

    if not pixscale == None and selfconfig['fully_platesolve_images_at_site_rather_than_pipe']: # or np.isnan(pixscale):



        # hdufocusdata=input_psolve_info[0]
        # pixscale=input_psolve_info[2]
        # is_osc=input_psolve_info[3]
        # filepath=input_psolve_info[4]
        # filebase=input_psolve_info[5]
        # RAest=input_psolve_info[6]
        # DECest=input_psolve_info[7]

        # plog ("HERE IS THE FULL PLATESOLVE PICKLE")
        # plog (hdu.data)
        # plog (pixscale)
        # plog (is_osc)
        wcsfilepath=localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs +'/wcs/'+ str(int(next_seq))
        # plog (wcsfilepath)
        wcsfilebase=selfconfig["obs_id"]+ "-" + cam_alias + '_' + str(frame_type) + '_' + str(this_exposure_filter) + "-" + dayobs+ "-"+ next_seq+ "-" + 'EX'+ "00.fits"
        # plog (wcsfilebase)
        # plog (corrected_ra_for_header * 15 )
        # plog (corrected_dec_for_header)
        # plog (next_seq)

        # CHECK TEMP DIR ACTUALLY EXISTS
        if not os.path.exists(localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs):
            os.makedirs(localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs, mode=0o777)

        if not os.path.exists(localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs +'/wcs'):
            os.makedirs(localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs +'/wcs', mode=0o777)

        if not os.path.exists(wcsfilepath):
            os.makedirs(wcsfilepath, mode=0o777)


        # # yet another pickle debugger.
        # if True:
        #     pickle.dump(
        #         [
        #             np.asarray(hdu.data,dtype=np.float32),
        #             pixscale,
        #             is_osc,
        #             wcsfilepath,
        #             wcsfilebase,
        #             corrected_ra_for_header * 15,
        #             corrected_dec_for_header,
        #             next_seq
        #         ],
        #         open('subprocesses/testsingleimageplatesolvepickle','wb')
        #     )





        # try:
        #     platesolve_subprocess = subprocess.Popen(
        #         ["python", "subprocesses/Platesolver_SingleImageFullReduction.py"],
        #         stdin=subprocess.PIPE,
        #         stdout=subprocess.PIPE,
        #         bufsize=0,
        #     )
        # except OSError:
        #     plog(traceback.format_exc())
        #     pass

        # try:
        #     pickle.dump(
        #         [
        #             np.asarray(hdu.data,dtype=np.float32),
        #             pixscale,
        #             is_osc,
        #             wcsfilepath,
        #             wcsfilebase,
        #             corrected_ra_for_header * 15,
        #             corrected_dec_for_header,
        #             next_seq

        #         ],
        #         platesolve_subprocess.stdin,
        #     )
        # except:
        #     plog("Problem in the platesolve pickle dump")
        #     plog(traceback.format_exc())

        pickledata=pickle.dumps(
            [
                np.asarray(hdu.data,dtype=np.float32),
                pixscale,
                is_osc,
                wcsfilepath,
                wcsfilebase,
                corrected_ra_for_header * 15,
                corrected_dec_for_header,
                next_seq
            ]
        )

        # platesolve_subprocess = subprocess.run(
        #     ["python", "subprocesses/Platesolver_SingleImageFullReduction.py"],
        #     input=pickledata,
        #     stdout=subprocess.PIPE,
        #     stderr=subprocess.PIPE,
        #     text=False  # MUST be False for binary data
        # )

        # On Windows you can detach the child completely if you like:
        #DETACHED_PROCESS = 0x00000008  # from the Win32 API


        # Here is where we trigger off the single image platesolve.
        # Realistically we only need it for longer exposures and
        # exposures that are at nighttime.
        if exposure_time > 4.9 and exposure_in_nighttime:
            # If we don't want to solve a single image we just immediately dump a false report.
            wslfilename=wcsfilepath + '/' + wcsfilebase
            with open(wslfilename.replace('.fits','.failed'), 'w') as file:
                file.write('failed')
        else:

            p = subprocess.Popen(
                ["python", "subprocesses/Platesolver_SingleImageFullReduction.py"],
                stdin = subprocess.PIPE,             # so we can feed it our pickledata
                stdout = subprocess.DEVNULL,         # drop its stdout
                stderr = subprocess.DEVNULL,         # drop its stderr
                #creationflags = DETACHED_PROCESS     # optional: child won’t keep your console open
            )
    
            # send the pickle and close stdin so the child sees EOF
            p.stdin.write(pickledata)
            p.stdin.close()

        

    # While we wait for the platesolving to happen we do all the other stuff
    # And we will pick up the solution towards the end.



    # assign the keyword values and comment of the keyword as a tuple to write both to header.
    hdu.header["BUNIT"] = ("adu", "Unit of array values")
    hdu.header["CCDXPIXE"] = (
        cam_settings["x_pixel"],
        "[um] Size of unbinned pixel, in X",
    )
    hdu.header["CCDYPIXE"] = (
        cam_settings["y_pixel"],
        "[um] Size of unbinned pixel, in Y",
    )
    hdu.header["XPIXSZ"] = (
        round(float(hdu.header["CCDXPIXE"]), 3),
        "[um] Size of binned pixel",
    )
    hdu.header["YPIXSZ"] = (
        round(float(hdu.header["CCDYPIXE"]), 3),
        "[um] Size of binned pixel",
    )
    hdu.header["XBINING"] = (1, "Pixel binning in x direction")
    hdu.header["YBINING"] = (1, "Pixel binning in y direction")

    hdu.header['CONFMODE'] = ('default',  'LCO Configuration Mode')
    hdu.header["DOCOSMIC"] = (
        cam_settings["do_cosmics"],
        "Cosmic ray removal in EVA",
    )


    hdu.header["DOSNP"] = (
        cam_settings['do_saltandpepper'],
        "Salt and Pepper removal in EVA",
    )
    hdu.header["DODBND"] = (
        cam_settings['do_debanding'],
        "Debanding removal in EVA",
    )


    hdu.header["CCDSTEMP"] = (
        round(setpoint, 2),     #WER fixed.
        "[C] CCD set temperature",
    )
    #hdu.header["COOLERON"] = self._cooler_on()
    hdu.header["CCDATEMP"] = (
        round(tempccdtemp, 2),
        "[C] CCD actual temperature",
    )
    hdu.header["CCDHUMID"] = round(ccd_humidity, 1)
    hdu.header["CCDPRESS"] = round(ccd_pressure, 1)
    hdu.header["OBSID"] = (
        selfconfig["obs_id"].replace("-", "").replace("_", "")
    )
    hdu.header["SITEID"] = (
        selfconfig["wema_name"].replace("-", "").replace("_", "")
    )
    hdu.header["TELID"] =selfconfig["obs_id"].replace("-", "").replace("_", "")
    hdu.header["TELESCOP"] = selfconfig["obs_id"].replace("-", "").replace("_", "")
    hdu.header["PTRTEL"] = selfconfig["obs_id"].replace("-", "").replace("_", "")
    hdu.header["PROPID"] = "ptr-" + selfconfig["obs_id"] + "-001-0001"
    hdu.header["BLKUID"] = (
        "1234567890",
        "Just a placeholder right now. WER",
    )
    hdu.header["INSTRUME"] = (cam_config["name"], "Name of camera")
    hdu.header["CAMNAME"] = (cam_config["desc"], "Instrument used")
    hdu.header["DETECTOR"] = (
        cam_config["detector"],
        "Name of camera detector",
    )
    hdu.header["CAMMANUF"] = (
        cam_config["manufacturer"],
        "Name of camera manufacturer",
    )
    hdu.header["DARKSLID"] = (darkslide_state, "Darkslide state")
    hdu.header['SHUTTYPE'] = (cam_settings["shutter_type"],
                              'Type of shutter')
    try:
        hdu.header["GAIN"] = (
            round(camera_known_gain,3),
            "[e-/ADU] Pixel gain",
        )
    except:
        hdu.header["GAIN"] = (
            round(camera_known_gain,3),
            "[e-/ADU] Pixel gain",
        )

    hdu.header["ORIGGAIN"] = (
        round(camera_known_gain,3),
        "[e-/ADU] Original Pixel gain",
    )
    try:
        hdu.header["RDNOISE"] = (
            round(camera_known_readnoise,3),
            "[e-/pixel] Read noise",
        )
    except:
        hdu.header["RDNOISE"] = (
            'Unknown',
            "[e-/pixel] Read noise",
        )
    hdu.header["OSCCAM"] = (is_osc, "Is OSC camera")
    hdu.header["OSCMONO"] = (False, "If OSC,  a mono image or Bayer?")

    hdu.header["FULLWELL"] = (
        cam_settings[
            "fullwell_capacity"
        ],
        "Full well capacity",
    )

    is_cmos=cam_settings["is_cmos"]
    driver=cam_config["driver"]
    hdu.header["CMOSCAM"] = (is_cmos, "Is CMOS camera")

    if is_cmos and driver ==  "QHYCCD_Direct_Control":
        hdu.header["CMOSGAIN"] = (cam_config[
            "settings"
        ]['direct_qhy_gain'], "CMOS Camera System Gain")


        hdu.header["CMOSOFFS"] = (cam_config[
            "settings"
        ]['direct_qhy_offset'], "CMOS Camera System Offset")

        hdu.header["CAMUSBT"] = (cam_config[
            "settings"
        ]['direct_qhy_usb_traffic'], "Camera USB traffic")
        hdu.header["READMODE"] = (cam_config[
            "settings"
        ]['direct_qhy_readout_mode'], "QHY Readout Mode")



    hdu.header["READOUTE"]= (readout_estimate, "Readout time estimated from this exposure")
    hdu.header["READOUTU"] = (readout_time, "Readout time used for this exposure")
    hdu.header["OBSTYPE"] = (
        frame_type.upper(),
        "Observation type",
    )  # This report is fixed and it should vary...NEEDS FIXING!
    if frame_type.upper() == "SKY FLAT":
       frame_type =="skyflat"
    hdu.header["IMAGETYP"] = (frame_type.upper(), "Observation type")

    hdu.header["TIMESYS"] = ("UTC", "Time system used")


    hdu.header["DAY-OBS"] = (
        dayobs,
        "Date at start of observing night"
    )
    yesterday = datetime.datetime.now() - datetime.timedelta(1)
    hdu.header["L1PUBDAT"] = datetime.datetime.strftime(
        yesterday, "%Y-%m-%dT%H:%M:%S.%fZ"
    )  # IF THIS DOESN"T WORK, subtract the extra datetime ...

    # There is a significant difference between substack timing and "normal" exposure timing
    # Also it has impacts on the actual "exposure time" as well.... the exposure time is "longer" but has LESS effective exposure time
    if substack:

        hdu.header["SUBEXPT"] = (expected_endpoint_of_substack_exposure - substack_start_time, "Time between start and end of subexposure set")

        substack_midexposure=np.mean(np.array(sub_stacker_midpoints))

        hdu.header["DATE"] = (
            datetime.datetime.isoformat(
                datetime.datetime.utcfromtimestamp(substack_start_time)
            ),
            "Start date and time of observation"
        )

        hdu.header["DATE-OBS"] = (
            datetime.datetime.isoformat(
                datetime.datetime.utcfromtimestamp(substack_start_time)
            ),
            "Start date and time of observation"
        )

        hdu.header["MJD-OBS"] = (
            Time(substack_start_time, format="unix").mjd,
            "[UTC days] Modified Julian Date start date/time",
        )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
        hdu.header["JD-START"] = (
            Time(substack_start_time, format="unix").jd,
            "[UTC days] Julian Date at start of exposure",
        )

        hdu.header["MJD-MID"] = (
            Time(substack_midexposure, format="unix").mjd,
            "[UTC days] Modified Julian Date mid exposure date/time",
        )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
        hdu.header["JD-MID"] = (
            Time(substack_midexposure, format="unix").jd,
            "[UTC days] Julian Date at middle of exposure",
        )

        hdu.header["EXPTIME"] = (
            round(expected_endpoint_of_substack_exposure - substack_start_time,6),
            "[s] Actual exposure length",
        )  # This is the exposure in seconds specified by the user
        hdu.header["EFFEXPT"] = (
            round(exposure_time,6),
            "[s] Integrated exposure length",
        )

        if this_exposure_filter.lower() in ["u", "ju", "bu", "up","z", "zs", "zp","ha", "h", "o3", "o","s2", "s","cr", "c","n2", "n"]:
            hdu.header["EFFEXPN"] = (
                int(exposure_time / 30),
                " Number of integrated exposures",
            )
        else:

            hdu.header["EFFEXPN"] = (
                int(exposure_time / 10),
                " Number of integrated exposures",
            )

        hdu.header["EXPREQ"] = (
            exposure_time,
            "[s] Requested Total Exposure Time",
        )  # This is the exposure in seconds specified by the user






        if not smartstackid == 'no':
            hdu.header["EXPREQSE"] = (
                exposure_time,
                "[s] Open Shutter Time of this smartstack element",
            )  # This is the exposure in seconds specified by the user


        hdu.header[
            "EXPOSURE"
        ] = (
            expected_endpoint_of_substack_exposure - substack_start_time,
            "[s] Actual exposure length",
        )  # Ideally this needs to be calculated from actual times


    else:

        hdu.header["DATE"] = (
            datetime.datetime.isoformat(
                datetime.datetime.utcfromtimestamp(start_time_of_observation)
            ),
            "Start date and time of observation"
        )

        hdu.header["DATE-OBS"] = (
            datetime.datetime.isoformat(
                datetime.datetime.utcfromtimestamp(start_time_of_observation)
            ),
            "Start date and time of observation"
        )

        hdu.header["MJD-OBS"] = (
            Time(start_time_of_observation, format="unix").mjd,
            "[UTC days] Modified Julian Date start date/time",

        )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
        hdu.header["JD-START"] = (
            Time(start_time_of_observation, format="unix").jd,
            "Julian Date at start of exposure")

        hdu.header["MJD-MID"] = (
            Time(start_time_of_observation + (0.5 * exposure_time), format="unix").mjd,
            "Modified Julian Date mid exposure date/time",
        )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
        hdu.header["JD-MID"] = (
            Time(start_time_of_observation+ (0.5 * exposure_time), format="unix").jd,

            "Julian Date at middle of exposure",
        )

        hdu.header["EXPTIME"] = (
            round(exposure_time,6),
            "[s] Actual exposure length",
        )  # This is the exposure in seconds specified by the

        hdu.header["EXPREQ"] = (
            round(exposure_time,6),
            "[s] Requested Exposure Time",
        )  # This is the exposure in seconds specified by the user

        if not smartstackid == 'no':
            hdu.header["EXPREQSE"] = (
                round(exposure_time,6),
                "[s] Open Shutter Time of this smartstack element",
            )  # This is the exposure in seconds specified by the user

        hdu.header["EFFEXPT"] = (
            round(exposure_time,6),
            "[s] Integrated exposure length",
        )
        hdu.header["EFFEXPN"] = (
            1,
            "[s] Number of integrated exposures",
        )

        hdu.header[
            "EXPOSURE"
        ] = (
            round(exposure_time,6),
            "[s] Actual exposure length",
        )  # Ideally this needs to be calculated from actual times



    hdu.header["NEXPREQ"] = (
        number_of_exposures_requested,
        "Number of exposures requested",
    )  # This is the exposure in seconds specified by the user

    hdu.header["BATCHCDE"] = ( unique_batch_code, 'unique batch code for this set of images')

    hdu.header["BUNIT"] = "adu"

    hdu.header["FILTER"] = (
        this_exposure_filter,
        "Filter type")
    if null_filterwheel == False:
        hdu.header["FILTEROF"] = (exposure_filter_offset, "Filter offset")

        hdu.header["FILTRNUM"] = (
           "PTR_ADON_HA_0023",
           "An index into a DB",
           )
    else:
        hdu.header["FILTEROF"] = ("No Filter", "Filter offset")
        hdu.header["FILTRNUM"] = (
            "No Filter",
            "An index into a DB",
        )  # Get a number from the hardware or via Maxim.  NB NB why not cwl and BW instead, plus P

    # THESE ARE THE RELEVANT FITS HEADER KEYWORDS
    # FOR OSC MATCHING AT A LATER DATE.
    # THESE ARE SET TO DEFAULT VALUES FIRST AND
    # THINGS CHANGE LATER
    hdu.header["OSCMATCH"] = 'no'
    hdu.header['OSCSEP'] = 'no'

    hdu.header["SATURATE"] = (
        float(image_saturation_level),
        "[ADU] Saturation level",
    )
    hdu.header["MAXLIN"] = (
        float(
            cam_settings[
                "max_linearity"
            ]
        ),
        "[ADU] Non-linearity level",
    )
    if pane is not None:
        hdu.header["MOSAIC"] = (True, "Is mosaic")
        hdu.header["PANE"] = pane

    hdu.header["FOCAL"] = (
        round( float(telescope_config["focal_length"]), 2),
        "[mm] Telescope focal length",
    )
    hdu.header["APR-DIA"] = (
        round( float(telescope_config["aperture"]), 2),
        "[mm] Telescope aperture",
    )
    hdu.header["APR-AREA"] = (
        round( float(telescope_config["collecting_area"]), 1),
        "[mm^2] Telescope collecting area",
    )
    hdu.header["LATITUDE"] = (
        round(float(wema_config["latitude"]), 6),
        "[Deg N] Telescope Latitude",
    )
    hdu.header["LONGITUD"] = (
        round(float(wema_config["longitude"]), 6),
        "[Deg E] Telescope Longitude",
    )
    hdu.header["HEIGHT"] = (
        round(float(wema_config["elevation"]), 2),
        "[m] Altitude of Telescope above sea level",
    )
    hdu.header["MPC-CODE"] = (
        selfconfig["mpc_code"],
        "Site code",
    )  # This is made up for now.

    hdu.header["OBJECT"] =object_name
    hdu.header["OBJSPECF"] = object_specf

    if not any("OBJECT" in s for s in hdu.header.keys()):
        RAtemp = ra_at_time_of_exposure
        DECtemp = dec_at_time_of_exposure
        RAstring = f"{RAtemp:.1f}".replace(".", "h")
        DECstring = f"{DECtemp:.1f}".replace("-", "n").replace(".", "d")
        hdu.header["OBJECT"] = RAstring + "ra" + DECstring + "dec"
        hdu.header["OBJSPECF"] = "no"

    try:
        hdu.header["SID-TIME"] = (
            avg_mnt['sidereal_time'],
            "[deg] Sidereal time",
        )
        hdu.header["OBJCTRA"] = (
            float(avg_mnt['right_ascension']) * 15,
            "[deg] Object RA",
        )
        hdu.header["OBJCTDEC"] = (avg_mnt['declination'], "[deg] Object dec")
    except:
        # plog("problem with the premount?")
        # plog(traceback.format_exc())
        pass
    hdu.header["OBSERVER"] = (
        observer_user_name,
        "Observer name",
    )
    hdu.header["OBSNOTE"] = opt.get('hint', '')[0:54]  # Needs to be truncated.

    hdu.header["DITHER"] = (0, "[] Dither")  #This was intended to inform of a 5x5 pattern number
    hdu.header["OPERATOR"] = ("WER", "Site operator")

    hdu.header["ENCLIGHT"] = ("Off/White/Red/NIR", "Enclosure lights")
    hdu.header["ENCRLIGT"] = ("", "Enclosure red lights state")
    hdu.header["ENCWLIGT"] = ("", "Enclosure white lights state")

    hdu.header["MNT-SIDT"] = (
        avg_mnt["sidereal_time"],
        "[hrs] Mount sidereal time",
    )
    hdu.header["MNT-RA"] = (
        float(avg_mnt["right_ascension"]) * 15,
        "[deg] Mount RA",
    )
    ha = avg_mnt["sidereal_time"] - avg_mnt["right_ascension"]
    while ha >= 12:
        ha -= 24.0
    while ha < -12:
        ha += 24.0
    hdu.header["MNT-HA"] = (
        round(ha, 5),
        "[hrs] Average mount hour angle",
    )  # Note these are average mount observed values.

    hdu.header["MNT-DEC"] = (
        avg_mnt["declination"],
        "[deg] Average mount declination",
    )
    hdu.header["MNT-RAV"] = (
        avg_mnt["tracking_right_ascension_rate"],
        "[] Mount tracking RA rate",
    )
    hdu.header["MNT-DECV"] = (
        avg_mnt["tracking_declination_rate"],
        "[] Mount tracking dec rate",
    )
    hdu.header["AZIMUTH "] = (
        azimuth_of_observation,
        "[deg] Azimuth axis positions",
    )
    hdu.header["ALTITUDE"] = (
        altitude_of_observation,
        "[deg] Altitude axis position",
    )
    hdu.header["ZENITH"] = (90 - altitude_of_observation, "[deg] Zenith")
    hdu.header["AIRMASS"] = (
        airmass_of_observation,
        "Effective mean airmass",
    )
    # try:
    #     hdu.header["REFRACT"] = (
    #         round(g_dev["mnt"].refraction_rev, 3),
    #         "asec",
    #     )
    # except:
    #     pass
    hdu.header["MNTRDSYS"] = (
        avg_mnt["coordinate_system"],
        "Mount coordinate system",
    )
    hdu.header["POINTINS"] = (avg_mnt["instrument"], "")
    hdu.header["MNT-PARK"] = (avg_mnt["is_parked"], "Mount is parked")
    hdu.header["MNT-SLEW"] = (avg_mnt["is_slewing"], "Mount is slewing")
    hdu.header["MNT-TRAK"] = (
        avg_mnt["is_tracking"],
        "Mount is tracking",
    )
    try:
        if pier_side == 0:
            hdu.header["PIERSIDE"] = ("Look West", "Pier on  East side")
            hdu.header["IMGFLIP"] = (True, "Is flipped")
            pier_string = "lw-"
        elif pier_side == 1:
            hdu.header["PIERSIDE"] = ("Look East", "Pier on West side")
            hdu.header["IMGFLIP"] = (False, "Is flipped")
            pier_string = "le-"
    except:
        hdu.header["PIERSIDE"] = "Undefined"
        pier_string = ""

    try:
        hdu.header["HACORR"] = (
            ha_corr,
            "[deg] Hour angle correction",
        )
        hdu.header["DECCORR"] = (
            dec_corr,
            "[deg] Declination correction",
        )
    except:
        pass
    hdu.header["OTA"] = "Main"
    hdu.header["SELECTEL"] = ("tel1", "Nominted OTA for pointing")
    try:
        hdu.header["ROTATOR"] = (
            rotator_alias,
            "Rotator name",
        )
        hdu.header["ROTANGLE"] = (avg_rot[1], "[deg] Rotator angle")
        hdu.header["ROTMOVNG"] = (avg_rot[2], "Rotator is moving")
    except:
        pass

    try:
        hdu.header["FOCUS"] = (
            focuser_alias,
            "Focuser name",
        )
        hdu.header["FOCUSPOS"] = (avg_foc[1], "[um] Focuser position")
        hdu.header["FOCUSTMP"] = (avg_foc[2], "[C] Focuser temperature")
        hdu.header["FOCUSMOV"] = (avg_foc[3], "Focuser is moving")
    except:
        plog("There is something fishy in the focuser routine")


    #breakpoint()
    if pixscale == None: # or np.isnan(pixscale):
        hdu.header["PIXSCALE"] = (
            'Unknown',
            "[arcsec/pixel] Nominal pixel scale on sky",
        )
    else:
        hdu.header["PIXSCALE"] = (
            round(pixscale,3),
            "[arcsec/pixel] Nominal pixel scale on sky",
        )

    hdu.header["DRZPIXSC"] = (cam_settings['drizzle_value_for_later_stacking'], 'Target drizzle scale')

    hdu.header["REQNUM"] = ("00000001", "Request number")
    hdu.header["ISMASTER"] = (False, "Is master image")


    hdu.header["FRAMENUM"] = (int(next_seq), "Running frame number")
    hdu.header["SMARTSTK"] = smartstackid # ID code for an individual smart stack group
    hdu.header["SSTKNUM"] = sskcounter
    hdu.header['SSTKLEN'] = Nsmartstack

    hdu.header["SUBSTACK"] = substack
    hdu.header["PEDESTAL"] = (0.0, "This value has been added to the data")
    hdu.header["ERRORVAL"] = 0

    hdu.header["USERNAME"] = observer_user_name
    hdu.header["USERID"] = (
        str(observer_user_id).replace("-", "").replace("|", "").replace('@','at')
    )


    im_type = "EX"
    f_ext = ""

    cal_name = (
        selfconfig["obs_id"]
        + "-"
        + current_camera_name
        + "-"
        + dayobs
        + "-"
        + next_seq
        + f_ext
        + "-"
        + im_type
        + "00.fits"
    )
    raw_name00 = (
        selfconfig["obs_id"]
        + "-"
        + current_camera_name + '_' + str(frame_type) + '_' + str(this_exposure_filter)
        + "-"
        + dayobs
        + "-"
        + next_seq
        + "-"
        + im_type
        + "00.fits"
    )

    if selfconfig['save_reduced_file_numberid_first']:
        red_name01 = (next_seq + "-" +selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(this_exposure_filter) + "-" +  str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")
    else:
        red_name01 = (selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(this_exposure_filter) + "-" + next_seq+ "-" + str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")

    red_name01_lcl = (
        red_name01[:-9]
        + pier_string + '-'
        + this_exposure_filter
        + red_name01[-9:]
    )
    if pane is not None:
        red_name01_lcl = (
            red_name01_lcl[:-9]
            + pier_string
            + "p"
            + str(abs(pane))
            + "-"
            + red_name01_lcl[-9:]
        )
    i768sq_name = (
        selfconfig["obs_id"]
        + "-"
        + current_camera_name
        + "-"
        + dayobs
        + "-"
        + next_seq
        + "-"
        + im_type
        + "10.fits"
    )
    jpeg_name = (
        selfconfig["obs_id"]
        + "-"
        + current_camera_name
        + "-"
        + dayobs
        + "-"
        + next_seq
        + "-"
        + im_type
        + "10.jpg"
    )
    text_name = (
        selfconfig["obs_id"]
        + "-"
        + current_camera_name
        + "-"
        + dayobs
        + "-"
        + next_seq
        + "-"
        + im_type
        + "00.txt"
    )
    im_path_r = selfcamera_path

    hdu.header["FILEPATH"] = str(im_path_r) + "to_AWS/"
    hdu.header["ORIGNAME"] = str(raw_name00 + ".fz").replace('.fz.fz','.fz')

    # tempRAdeg = ra_at_time_of_exposure * 15
    # tempDECdeg = dec_at_time_of_exposure

    tempRAdeg = corrected_ra_for_header * 15
    tempDECdeg = corrected_dec_for_header

    tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
    tempointing=tempointing.to_string("hmsdms").split(' ')

    hdu.header["RA"] = (
        tempointing[0],
        "[hms] Telescope right ascension",
    )
    hdu.header["DEC"] = (
        tempointing[1],
        "[dms] Telescope declination",
    )
    hdu.header["ORIGRA"] = hdu.header["RA"]
    hdu.header["ORIGDEC"] = hdu.header["DEC"]
    hdu.header["RAhrs"] = (
        round(corrected_ra_for_header,8),
        "[hrs] Telescope right ascension",
    )
    hdu.header["RADEG"] = round(tempRAdeg,8)
    hdu.header["DECDEG"] = round(tempDECdeg,8)

    hdu.header["TARG-CHK"] = (
        (ra_at_time_of_exposure * 15)
        + dec_at_time_of_exposure,
        "[deg] Sum of RA and dec",
    )
    try:
        hdu.header["CATNAME"] = (object_name, "Catalog object name")
    except:
        hdu.header["CATNAME"] = ('Unknown', "Catalog object name")
    hdu.header["CAT-RA"] = (
        tempointing[0],
        "[hms] Catalog RA of object",
    )
    hdu.header["CAT-DEC"] = (
        tempointing[1],
        "[dms] Catalog Dec of object",
    )
    hdu.header["OFST-RA"] = (
        tempointing[0],
        "[hms] Catalog RA of object (for BANZAI only)",
    )
    hdu.header["OFST-DEC"] = (
        tempointing[1],
        "[dms] Catalog Dec of object",
    )


    hdu.header["TPT-RA"] = (
        tempointing[0],
        "[hms] Catalog RA of object (for BANZAI only",
    )
    hdu.header["TPT-DEC"] = (
        tempointing[1],
        "[dms] Catalog Dec of object",
    )

    hdu.header["RA-hms"] = tempointing[0]
    hdu.header["DEC-dms"] = tempointing[1]

    hdu.header["CTYPE1"] = 'RA---TAN'
    hdu.header["CTYPE2"] = 'DEC--TAN'
    try:
        hdu.header["CDELT1"] = pixscale / 3600
        hdu.header["CDELT2"] = pixscale / 3600
    except:
        hdu.header["CDELT1"] = 0.75 / 3600
        hdu.header["CDELT2"] = 0.75 / 3600

    hdu.header["CRVAL1"] = tempRAdeg
    hdu.header["CRVAL2"] = tempDECdeg
    hdu.header["CRPIX1"] = float(hdu.header["NAXIS1"])/2
    hdu.header["CRPIX2"] = float(hdu.header["NAXIS2"])/2

    # This is the header item that LCO uses
    hdu.header["SITERED"] = (True, 'Has this file been reduced at site')

    try:  #  NB relocate this to Expose entry area.  Fill out except.  Might want to check on available space.
        os.makedirs(
            im_path_r + dayobs + "/to_AWS/", exist_ok=True
        )
        os.makedirs(im_path_r + dayobs + "/raw/", exist_ok=True)
        os.makedirs(im_path_r + dayobs + "/calib/", exist_ok=True)
        os.makedirs(
            im_path_r + dayobs + "/reduced/", exist_ok=True
        )
        im_path = im_path_r + dayobs + "/to_AWS/"
        raw_path = im_path_r + dayobs + "/raw/"
        cal_path = im_path_r + dayobs + "/calib/"
        red_path = im_path_r + dayobs + "/reduced/"

    except:
        pass

    paths = {
        "im_path": im_path,
        "raw_path": raw_path,
        "cal_path": cal_path,
        "red_path": red_path,
        "red_path_aux": None,
        "cal_name": cal_name,
        "raw_name00": raw_name00,
        "red_name01": red_name01,
        "red_name01_lcl": red_name01_lcl,
        "i768sq_name10": i768sq_name,
        "i768sq_name11": i768sq_name,
        "jpeg_name10": jpeg_name,
        "jpeg_name11": jpeg_name,
        "text_name00": text_name,
        "text_name10": text_name,
        "text_name11": text_name,
        "frame_type": frame_type,
    }

    if frame_type[-5:] in ["focus", "probe", "ental"]:
        focus_image = True
    else:
        focus_image = False

    # Given that the datalab is our primary "customer" in the sense that we want the data to get to the datalab ASAP
    # Even though a live observer might be waiting in realtime, we dump out the creation of that file here
    # i.e. ASAP
    if frame_type.lower() in ['fivepercent_exposure_dark','tenpercent_exposure_dark', 'quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark', 'fivesec_exposure_dark', 'tensec_exposure_dark', 'fifteensec_exposure_dark', 'twentysec_exposure_dark', 'thirtysec_exposure_dark', 'broadband_ss_biasdark', 'narrowband_ss_biasdark']:
        a_dark_exposure=True
    else:
        a_dark_exposure=False
    if not ( frame_type.lower() in [
        "bias",
        "dark"
        "flat",
        "focus",
        "skyflat",
        "pointing"
        ]) and not a_dark_exposure:

        if selfconfig['fully_platesolve_images_at_site_rather_than_pipe']:
            wcsfilename=localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs +'/wcs/'+ str(int(next_seq)) +'/' + selfconfig["obs_id"]+ "-" + cam_alias + '_' + str(frame_type) + '_' + str(this_exposure_filter) + "-" + dayobs+ "-"+ next_seq+ "-" + 'EX'+ "00.fits"
        else:
            wcsfilename='none'

        picklepayload=(copy.deepcopy(hdu.header),copy.deepcopy(selfconfig),cam_alias, ('fz_and_send', (raw_path + raw_name00 + ".fz").replace('.fz.fz','.fz'), copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure, wcsfilename))

        #plog (bn.nanmin(hdu.data))

        picklefilename='testlocalred'+str(time.time()).replace('.','')
        pickle.dump(picklepayload, open(localcalibrationdirectory + 'smartstacks/'+picklefilename,'wb'))

        #sys.exit()

        fz_proc=subprocess.Popen(
            ['python','fz_archive_file.py',picklefilename],
            cwd=localcalibrationdirectory + 'smartstacks',
            stdin=subprocess.PIPE,
            stdout=None,
            stderr=None,
            bufsize=-1
        )
        fz_proc.stdin.close()


    # NOW THAT THE FILE HAS BEEN FZED AND SENT OFF TO THE PIPE,
    # WE CAN NOW DENAN THE IMAGE FOR THE JPEGS AND SUCH

    # If this is set to true, then it will output a sample of the image.
    if False:
        hdufocus = fits.PrimaryHDU()
        hdufocus.data = hdu.data
        hdufocus.header = hdu.header
        hdufocus.header["NAXIS1"] = hdu.data.shape[0]
        hdufocus.header["NAXIS2"] = hdu.data.shape[1]
        hdufocus.writeto(cal_path + 'prenan.fits', overwrite=True, output_verify='silentfix')


    # # Need to get rid of nans
    # # Interpolate image nans
    # kernel = Gaussian2DKernel(x_stddev=1)
    # hdu.data = interpolate_replace_nans(hdu.data, kernel)

    # # Fast next-door-neighbour in-fill algorithm to mop up any left over
    # x_size=hdu.data.shape[0]
    # y_size=hdu.data.shape[1]

    # nan_coords=np.argwhere(np.isnan(hdu.data))

    # # For each coordinate try and find a non-nan-neighbour and steal its value
    # for nancoord in nan_coords:
    #     x_nancoord=nancoord[0]
    #     y_nancoord=nancoord[1]
    #     done=False

    #     # Because edge pixels can tend to form in big clumps
    #     # Masking the array just with the mean at the edges
    #     # makes this MUCH faster to no visible effect for humans.
    #     # Also removes overscan
    #     if x_nancoord < 100:
    #         hdu.data[x_nancoord,y_nancoord]=imageMode
    #         done=True
    #     elif x_nancoord > (x_size-100):
    #         hdu.data[x_nancoord,y_nancoord]=imageMode

    #         done=True
    #     elif y_nancoord < 100:
    #         hdu.data[x_nancoord,y_nancoord]=imageMode

    #         done=True
    #     elif y_nancoord > (y_size-100):
    #         hdu.data[x_nancoord,y_nancoord]=imageMode
    #         done=True

    #     # left
    #     if not done:
    #         if x_nancoord != 0:
    #             value_here=hdu.data[x_nancoord-1,y_nancoord]
    #             if not np.isnan(value_here):
    #                 hdu.data[x_nancoord,y_nancoord]=value_here
    #                 done=True
    #     # right
    #     if not done:
    #         if x_nancoord != (x_size-1):
    #             value_here=hdu.data[x_nancoord+1,y_nancoord]
    #             if not np.isnan(value_here):
    #                 hdu.data[x_nancoord,y_nancoord]=value_here
    #                 done=True
    #     # below
    #     if not done:
    #         if y_nancoord != 0:
    #             value_here=hdu.data[x_nancoord,y_nancoord-1]
    #             if not np.isnan(value_here):
    #                 hdu.data[x_nancoord,y_nancoord]=value_here
    #                 done=True
    #     # above
    #     if not done:
    #         if y_nancoord != (y_size-1):
    #             value_here=hdu.data[x_nancoord,y_nancoord+1]
    #             if not np.isnan(value_here):
    #                 hdu.data[x_nancoord,y_nancoord]=value_here
    #                 done=True

    # hdu.data[np.isnan(hdu.data)] = imageMode
    #     #num_of_nans=np.count_nonzero(np.isnan(hdusmalldata))
    googtime=time.time()

    def fill_nans_with_local_mean(data, footprint=None):
        """
        Replace NaNs by the mean of their neighboring pixels.
        - data: 2D numpy array with NaNs.
        - footprint: kernel array of 0/1 defining neighborhood (default 3×3).
        """
        mask = np.isnan(data)
        # zero-fill NaNs for convolution
        filled = np.nan_to_num(data, copy=True)
        if footprint is None:
            footprint = np.ones((3,3), dtype=int)

        # sum of neighbors (NaNs contributed as 0)
        neighbor_sum   = convolve(filled,   footprint, mode='mirror')
        # count of valid neighbors
        neighbor_count = convolve(~mask,    footprint, mode='mirror')

        # only replace where count>0
        replace_idxs = mask & (neighbor_count>0)
        data_out = data.copy()
        data_out[replace_idxs] = neighbor_sum[replace_idxs] / neighbor_count[replace_idxs]
        return data_out

    hdu.data=fill_nans_with_local_mean(hdu.data)

    plog ("Denan Image: " +str(time.time()-googtime))

    # If this is set to true, then it will output a sample of the image.
    if False:
        hdufocus = fits.PrimaryHDU()
        hdufocus.data = hdu.data
        hdufocus.header = hdu.header
        hdufocus.header["NAXIS1"] = hdu.data.shape[0]
        hdufocus.header["NAXIS2"] = hdu.data.shape[1]
        hdufocus.writeto(cal_path + 'postnan.fits', overwrite=True, output_verify='silentfix')

    # This saves the REDUCED file to DISK
    # If this is for a smartstack, this happens immediately in the camera thread after we have a "reduced" file
    # So that the smartstack queue can start on it ASAP as smartstacks
    # are by far the longest task to undertake.
    # If it isn't a smartstack, it gets saved in the slow process queue.
    # if "hdusmalldata" in locals():
    # Set up reduced header
    hdusmalldata=copy.deepcopy(hdu.data)
    hdusmallheader=copy.deepcopy(hdu.header)
    if not manually_requested_calibration:
        #From the reduced data, crop around the edges of the
        #raw 1x1 image to get rid of overscan and crusty edge bits
        #edge_crop=selfconfig["camera"][selfname]["settings"]['reduced_image_edge_crop']
        # edge_crop=100
        # if edge_crop > 0:
        #     hdusmalldata=hdusmalldata[edge_crop:-edge_crop,edge_crop:-edge_crop]

        #     hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) - (edge_crop * 2)
        #     hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) - (edge_crop * 2)
        #     hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) - (edge_crop * 2)
        #     hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) - (edge_crop * 2)

        # bin to native binning
        if selfnative_bin != 1 and (not pixscale == None) and not hdu.header['PIXSCALE'] == 'Unknown':




            reduced_hdusmalldata=(block_reduce(hdusmalldata,selfnative_bin))
            reduced_hdusmallheader=copy.deepcopy(hdusmallheader)
            reduced_hdusmallheader['XBINING']=selfnative_bin
            reduced_hdusmallheader['YBINING']=selfnative_bin
            #breakpoint()
            reduced_hdusmallheader['PIXSCALE']=float(hdu.header['PIXSCALE']) * selfnative_bin
            reduced_pixscale=float(hdu.header['PIXSCALE'])
            reduced_hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) / selfnative_bin
            reduced_hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) / selfnative_bin
            reduced_hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) / selfnative_bin
            reduced_hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) / selfnative_bin
            reduced_hdusmallheader['CDELT1']=float(hdu.header['CDELT1']) * selfnative_bin
            reduced_hdusmallheader['CDELT2']=float(hdu.header['CDELT2']) * selfnative_bin
            reduced_hdusmallheader['CCDXPIXE']=float(hdu.header['CCDXPIXE']) * selfnative_bin
            reduced_hdusmallheader['CCDYPIXE']=float(hdu.header['CCDYPIXE']) * selfnative_bin
            reduced_hdusmallheader['XPIXSZ']=float(hdu.header['XPIXSZ']) * selfnative_bin
            reduced_hdusmallheader['YPIXSZ']=float(hdu.header['YPIXSZ']) * selfnative_bin

            reduced_hdusmallheader['SATURATE']=float(hdu.header['SATURATE']) * pow( selfnative_bin,2)
            reduced_hdusmallheader['FULLWELL']=float(hdu.header['FULLWELL']) * pow( selfnative_bin,2)
            reduced_hdusmallheader['MAXLIN']=float(hdu.header['MAXLIN']) * pow( selfnative_bin,2)

            reduced_hdusmalldata=reduced_hdusmalldata+200.0
            reduced_hdusmallheader['PEDESTAL']=200
        else:
            reduced_hdusmalldata=copy.deepcopy(hdusmalldata)
            reduced_hdusmallheader=copy.deepcopy(hdusmallheader)


        # Add a pedestal to the reduced data
        # This is important for a variety of reasons
        # Some functions don't work with arrays with negative values
        # 200 SHOULD be enough.
        hdusmalldata=hdusmalldata+200.0
        hdusmallheader['PEDESTAL']=200

        hdusmallheader["OBSID"] = (
            selfconfig["obs_id"].replace("-", "").replace("_", "")
        )

        hdusmallheader["DAY-OBS"] = (
            dayobs,
            "Date at start of observing night"
        )


        # If this is set to true, then it will output a sample of the image.
        if False:
            hdufocus = fits.PrimaryHDU()
            hdufocus.data = hdusmalldata
            hdufocus.header = hdu.header
            hdufocus.header["NAXIS1"] = hdu.data.shape[0]
            hdufocus.header["NAXIS2"] = hdu.data.shape[1]
            hdufocus.writeto(cal_path + 'posthdusmall.fits', overwrite=True, output_verify='silentfix')

        # Actually save out ONE reduced file for different threads to use.
        image_filename=localcalibrationdirectory + "smartstacks/reducedimage" + str(time.time()).replace('.','') + '.npy'

        # Save numpy array out.
        hdusmalldata=hdusmalldata.astype('float32')
        np.save(image_filename, hdusmalldata)

        # Just save astropy header
        cleanhdu=fits.PrimaryHDU()
        cleanhdu.data=np.asarray([0])
        cleanhdu.header=hdusmallheader
        cleanhdu.writeto(image_filename.replace('.npy','.head'))


        #g_dev['obs'].to_sep((hdusmalldata, pixscale, float(hdu.header["RDNOISE"]), avg_foc[1], focus_image, im_path, text_name, hdusmallheader, cal_path, cal_name, frame_type, focus_position, selfnative_bin, exposure_time))
        #np.save(hdusmalldata, septhread_filename)
        try:
            os.remove(septhread_filename+ '.temp')
        except:
            pass
        pickle.dump((image_filename,imageMode, unique, counts), open(septhread_filename+ '.temp', 'wb'))

        try:
            os.remove(septhread_filename)
        except:
            pass
        os.rename(septhread_filename + '.temp', septhread_filename)


        if smartstackid != 'no':
            try:
                np.save(red_path + red_name01.replace('.fits','.npy'), hdusmalldata)
                hdusstack=fits.PrimaryHDU()
                hdusstack.header=hdusmallheader
                hdusstack.header["NAXIS1"] = hdusmalldata.shape[0]
                hdusstack.header["NAXIS2"] = hdusmalldata.shape[1]
                hdusstack.writeto(red_path + red_name01.replace('.fits','.head'), overwrite=True, output_verify='silentfix')
                saver = 1
            except Exception as e:
                plog("Failed to write raw file: ", e)

        # This puts the file into the smartstack queue
        # And gets it underway ASAP.


        if ( not frame_type.lower() in [
            "bias",
            "dark",
            "flat",
            "solar",
            "lunar",
            "skyflat",
            "screen",
            "spectrum",
            "auto_focus",
            "focus",
            "pointing"
        ]) and smartstackid != 'no' and not a_dark_exposure :
            #g_dev['obs'].to_smartstack((paths, pixscale, smartstackid, sskcounter, Nsmartstack, pier_side, zoom_factor))
            #np.save(hdusmalldata, smartstackthread_filename)
            pickle.dump((image_filename,imageMode), open(smartstackthread_filename+ '.temp', 'wb'))


            os.rename(smartstackthread_filename + '.temp', smartstackthread_filename)

        else:
            if not selfconfig['keep_reduced_on_disk']:
                try:
                    os.remove(red_path + red_name01)
                except:
                    pass

        if selfconfig['keep_reduced_on_disk']:

            if selfconfig["save_to_alt_path"] == "yes":
                selfalt_path = selfconfig[
                    "alt_path"
                ]  +'/' + selfconfig['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.
            else:
                selfalt_path = 'no'

            slow_process=('reduced', red_path + red_name01, reduced_hdusmalldata, reduced_hdusmallheader, \
                                   frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure,selfalt_path)

            # Make  sure the alt paths exist
            if selfconfig["save_to_alt_path"] == "yes":
                #altpath=copy.deepcopy(g_dev['obs'].alt_path)
                altpath=selfconfig['alt_path'] + selfconfig['obs_id'] + '/'
            else:
                altpath='no'


            if selfconfig['fully_platesolve_images_at_site_rather_than_pipe']:
                wcsfilename=localcalibrationdirectory+ "archive/" + cam_alias + '/' + dayobs +'/wcs/'+ str(int(next_seq)) +'/' + selfconfig["obs_id"]+ "-" + cam_alias + '_' + str(frame_type) + '_' + str(this_exposure_filter) + "-" + dayobs+ "-"+ next_seq+ "-" + 'EX'+ "00.fits"
            else:
                wcsfilename='none'

            picklepayload=(reduced_hdusmallheader,copy.deepcopy(selfconfig),cam_alias, slow_process, altpath, wcsfilename)

            picklefilename='testred'+str(time.time()).replace('.','')
            pickle.dump(picklepayload, open(localcalibrationdirectory + 'smartstacks/'+picklefilename,'wb'))

            local_popen=subprocess.Popen(
                ['python','local_reduce_file_subprocess.py',picklefilename],
                cwd=localcalibrationdirectory + 'smartstacks',
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=None,
                bufsize=-1
            )
            local_popen.stdin.close()




        # Send data off to process jpeg if not a smartstack
        if smartstackid == 'no':
            #g_dev['obs'].to_mainjpeg((hdusmalldata, smartstackid, paths, pier_side, zoom_factor))
            # np.save(hdusmalldata, mainjpegthread_filename)
            try:
                os.remove(mainjpegthread_filename + '.temp')
            except:
                pass
            pickle.dump((image_filename,imageMode), open(mainjpegthread_filename + '.temp', 'wb'))
            try:
                os.remove(mainjpegthread_filename)
            except:
                pass
            os.rename(mainjpegthread_filename + '.temp', mainjpegthread_filename)



        if platesolvethread_filename !='no':
            # np.save(hdusmalldata, platesolvethread_filename)
            try:
                os.remove(platesolvethread_filename+ '.temp')
            except:
                pass
            pickle.dump((image_filename,imageMode), open(platesolvethread_filename+ '.temp', 'wb'))

            try:
                os.remove(platesolvethread_filename)
            except:
                pass
            os.rename(platesolvethread_filename + '.temp', platesolvethread_filename)

           #g_dev['obs'].to_platesolve((hdusmalldata, hdusmallheader, cal_path, cal_name, frame_type, time.time(), pixscale, ra_at_time_of_exposure,dec_at_time_of_exposure, firstframesmartstack, useastrometrynet, False, ''))
                    # If it is the last of a set of smartstacks, we actually want to
                    # wait for the platesolve and nudge before starting the next smartstack.







        # Similarly to the above. This saves the RAW file to disk
        # it works 99.9999% of the time.
        if selfconfig['save_raw_to_disk']:


            hdu.header["SITERED"] = (False, 'Has this file been reduced at site')


            os.makedirs(
                raw_path, exist_ok=True
            )

            if substack:
                os.makedirs(
                    raw_path + 'substacks', exist_ok=True
                )
                raw_path=raw_path+'/substacks/'

            thread = threading.Thread(target=write_raw_file_out, args=(('raw', raw_path + raw_name00, np.array(absolutely_raw_frame, dtype=np.float32), hdu.header, frame_type, ra_at_time_of_exposure, dec_at_time_of_exposure,'no','thisisdeprecated', dayobs, im_path_r, selfalt_path),))
            thread.daemon = False # These need to be daemons because this parent thread will end imminently
            thread.start()


            if selfconfig["save_to_alt_path"] == "yes":
                selfalt_path = selfconfig[
                    "alt_path"
                ]  +'/' + selfconfig['obs_id']+ '/'


                os.makedirs(
                    selfalt_path , exist_ok=True
                )

                os.makedirs(
                    selfalt_path + dayobs, exist_ok=True
                )

                os.makedirs(
                   selfalt_path + dayobs + "/raw/" , exist_ok=True
                )

                selfalt_path=selfalt_path + dayobs + "/raw/"

                if substack:
                    os.makedirs(
                        selfalt_path + dayobs + "/raw/substacks" , exist_ok=True
                    )
                    selfalt_path=selfalt_path + dayobs + "/raw/substacks/"


                thread = threading.Thread(target=write_raw_file_out, args=(('raw_alt_path', selfalt_path + dayobs + "/raw/" + raw_name00, absolutely_raw_frame, hdu.header, \
                                                   frame_type, ra_at_time_of_exposure, dec_at_time_of_exposure,'no','deprecated', dayobs, im_path_r, selfalt_path),))
                thread.daemon = False # These need to be daemons because this parent thread will end imminently
                thread.start()


        # remove file from memory
        try:
            hdu.close()
        except:
            pass
        del hdu  # remove file from memory now that we are doing with it

        if "hdusmalldata" in locals():
            try:
                hdusmalldata.close()
            except:
                pass
            del hdusmalldata  # remove file from memory now that we are doing with it
        if "reduced_hdusmalldata" in locals():
            try:
                del reduced_hdusmalldata
                del reduced_hdusmallheader
            except:
                pass


except:
    plog(traceback.format_exc())

plog ("FINISHED! in " + str(time.time()-a_timer))

#breakpoint()