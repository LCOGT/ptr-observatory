# -*- coding: utf-8 -*-
"""
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

# Note this is a thread!
def write_raw_file_out(packet):

    (raw, raw_name, hdudata, hduheader, frame_type, current_icrs_ra, current_icrs_dec,altpath,altfolder, dayobs, camera_path, altpath) = packet

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

payload=pickle.load(sys.stdin.buffer)
#payload=pickle.load(open('testpostprocess.pickle','rb'))

#expresult={}
#A long tuple unpack of the payload
(img, pier_side, is_osc, frame_type, reject_flat_by_known_gain, avg_mnt, avg_foc, avg_rot, \
 setpoint, tempccdtemp, ccd_humidity, ccd_pressure, darkslide_state, exposure_time, \
 this_exposure_filter, exposure_filter_offset, pane,opt, observer_user_name, hint, \
 azimuth_of_observation, altitude_of_observation, airmass_of_observation, pixscale, \
 smartstackid,sskcounter,Nsmartstack, longstackid, ra_at_time_of_exposure, \
 dec_at_time_of_exposure, manually_requested_calibration, object_name, object_specf, \
 ha_corr, dec_corr, focus_position, selfconfig, selfname, camera_known_gain, \
 camera_known_readnoise, start_time_of_observation, observer_user_id, selfcamera_path, \
 solve_it, next_seq, zoom_factor, useastrometrynet, substack, expected_endpoint_of_substack_exposure, \
 substack_start_time,readout_estimate,readout_time, sub_stacker_midpoints,corrected_ra_for_header,corrected_dec_for_header, substacker_filenames, dayobs, exposure_filter_offset,null_filterwheel, wema_config, smartstackthread_filename, septhread_filename, mainjpegthread_filename, platesolvethread_filename) = payload

#breakpoint()

a_timer=time.time()

camalias=selfconfig["camera"][selfname]["name"]
obsname=selfconfig['obs_id']
localcalibrationdirectory=selfconfig['local_calibration_path'] + selfconfig['obs_id'] + '/'
tempfrontcalib=obsname + '_' + camalias +'_'

localcalibmastersdirectory= localcalibrationdirectory+ "archive/" + camalias + "/calibmasters" \
                          + "/"



#breakpoint()

# Get the calibrated image whether that is a substack or a normal image. 
if substack:
    exp_of_substacks=int(exposure_time / len(substacker_filenames))
    # Get list of substack files needed and wait for them.
    waiting_for_substacker_filenames=copy.deepcopy(substacker_filenames)
    while len(waiting_for_substacker_filenames) > 0:
        for tempfilename in waiting_for_substacker_filenames:
            if os.path.exists(tempfilename):
                waiting_for_substacker_filenames.remove(tempfilename)
        time.sleep(0.2)
    
    temporary_substack_directory=localcalibrationdirectory + "substacks/" + str(time.time()).replace('.','')
    
    if not os.path.exists(localcalibrationdirectory + "substacks/"):
        os.makedirs(localcalibrationdirectory + "substacks/")
    if not os.path.exists(temporary_substack_directory):
        os.makedirs(temporary_substack_directory)
    
    
    counter=0
    
    crosscorrelation_subprocess_array=[]
    
    crosscorrel_filename_waiter=[]
    
    for substackfilename in substacker_filenames:
    
        substackimage=np.load(substackfilename)
        try:
            if exp_of_substacks == 10:
                print ("Dedarking 0")
                substackimage=copy.deepcopy(substackimage - np.load(localcalibrationdirectory + 'archive/' + camalias + '/calibmasters/' + tempfrontcalib + 'tensecBIASDARK_master_bin1.npy'))# - g_dev['cam'].darkFiles['tensec_exposure_biasdark'])
            else:
                substackimage=copy.deepcopy(substackimage - np.load(localcalibrationdirectory + 'archive/' + camalias + '/calibmasters/' + tempfrontcalib + 'thirtysecBIASDARK_master_bin1.npy'))
        except:
            breakpoint()
            print ("Couldn't biasdark substack")
            pass
        try:
            substackimage = copy.deepcopy(np.divide(substackimage, np.load(localcalibrationdirectory  + 'archive/' + camalias + '/calibmasters/' + 'masterFlat_'+this_exposure_filter + "_bin" + str(1) +'.npy')))
        except:
            print ("couldn't flat field substack")
            breakpoint()
            pass
        # Bad pixel map sub stack array
        try:
            substackimage[np.load(localcalibrationdirectory  + 'archive/' + camalias + '/calibmasters/' + tempfrontcalib + 'badpixelmask_bin1.npy')] = np.nan
        except:
            print ("Couldn't badpixel substack")
            pass
        
        
        
        # If it is the first image, just plonk it in the array.
        if counter == 0:
            # Set up the array
            sub_stacker_array = np.zeros((substackimage.shape[0],substackimage.shape[1],len(substacker_filenames)), dtype=np.float32)
            
            
            # Really need to thresh the image
            googtime=time.time()
            int_array_flattened=substackimage.astype(int).ravel()
            int_array_flattened=int_array_flattened[int_array_flattened > -10000]
            unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
            m=counts.argmax()
            imageMode=unique[m]
            print ("Calculating Mode: " +str(time.time()-googtime))
            
            #Zerothreshing image
            #googtime=time.time()
            histogramdata=np.column_stack([unique,counts]).astype(np.int32)
            histogramdata[histogramdata[:,0] > -10000]
            #Do some fiddle faddling to figure out the value that goes to zero less
            zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
            breaker=1
            zerocounter=0
            while (breaker != 0):
                zerocounter=zerocounter+1
                if not (imageMode-zerocounter) in zeroValueArray[:,0]:
                    if not (imageMode-zerocounter-1) in zeroValueArray[:,0]:
                        if not (imageMode-zerocounter-2) in zeroValueArray[:,0]:
                            if not (imageMode-zerocounter-3) in zeroValueArray[:,0]:
                                if not (imageMode-zerocounter-4) in zeroValueArray[:,0]:
                                    if not (imageMode-zerocounter-5) in zeroValueArray[:,0]:
                                        if not (imageMode-zerocounter-6) in zeroValueArray[:,0]:
                                            if not (imageMode-zerocounter-7) in zeroValueArray[:,0]:
                                                if not (imageMode-zerocounter-8) in zeroValueArray[:,0]:
                                                    if not (imageMode-zerocounter-9) in zeroValueArray[:,0]:
                                                        if not (imageMode-zerocounter-10) in zeroValueArray[:,0]:
                                                            if not (imageMode-zerocounter-11) in zeroValueArray[:,0]:
                                                                if not (imageMode-zerocounter-12) in zeroValueArray[:,0]:
                                                                    zeroValue=(imageMode-zerocounter)
                                                                    breaker =0
                                                                    
            substackimage[substackimage < zeroValue] = np.nan
            
            
            sub_stacker_array[:,:,0] = copy.deepcopy(substackimage)
            
        else:
            
            
            output_filename='crosscorrel' + str(counter-1) + '.npy'
            pickler=[]
            pickler.append(sub_stacker_array[:,:,0])
            pickler.append(substackimage)
            pickler.append(temporary_substack_directory)
            pickler.append(output_filename)
            pickler.append(is_osc)
            
            crosscorrel_filename_waiter.append(temporary_substack_directory + output_filename)
            
            crosscorrelation_subprocess_array.append(subprocess.Popen(['python','crosscorrelation_subprocess.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0))
            print (counter-1)
            pickle.dump(pickler, crosscorrelation_subprocess_array[counter-1].stdin)
        
        counter=counter+1
        
    
   # breakpoint()
    
    counter=1
    
    for waitfile in crosscorrel_filename_waiter:
        while not os.path.exists(waitfile):
            #print ("waiting for " + str(waitfile))
            time.sleep(0.2)
        
        sub_stacker_array[:,:,counter] = np.load(waitfile)
        counter=counter+1
    
    
    # for waiting_for_subprocesses in crosscorrelation_subprocess_array:
    #     waiting_for_subprocesses.communicate()
        
    #     sub_stacker_array[:,:,counter] = copy.deepcopy(np.load(temporary_substack_directory + output_filename))
    #     counter=counter+1    
    
    # Once collected and done, nanmedian the array into the single image
    img=bn.nanmedian(sub_stacker_array, axis=2) * len(substacker_filenames)
    

        
        



obsid_path = str(selfconfig["archive_path"] + '/' + obsname + '/').replace('//','/')

post_exposure_process_timer=time.time()
ix, iy = img.shape

# Update readout time list
readout_shelf = shelve.open(obsid_path + 'ptr_night_shelf/' + 'readout' + camalias + str(obsname))
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

image_saturation_level = selfconfig["camera"][selfname]["settings"]["saturate"]

try:
    # THIS IS THE SECTION WHERE THE ORIGINAL FITS IMAGES ARE ROTATED
    # OR TRANSPOSED. THESE ARE ONLY USED TO ORIENTATE THE FITS
    # IF THERE IS A MAJOR PROBLEM with the original orientation
    # If you want to change the display on the UI, use the jpeg
    # alterations later on.
    if selfconfig["camera"][selfname]["settings"]["transpose_fits"]:
        hdu = fits.PrimaryHDU(
            img.transpose().astype('float32'))
    elif selfconfig["camera"][selfname]["settings"]["flipx_fits"]:
        hdu = fits.PrimaryHDU(
            np.fliplr(img.astype('float32'))
        )
    elif selfconfig["camera"][selfname]["settings"]["flipy_fits"]:
        hdu = fits.PrimaryHDU(
            np.flipud(img.astype('float32'))
        )
    elif selfconfig["camera"][selfname]["settings"]["rotate90_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'))
        )
    elif selfconfig["camera"][selfname]["settings"]["rotate180_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'),2)
        )
    elif selfconfig["camera"][selfname]["settings"]["rotate270_fits"]:
        hdu = fits.PrimaryHDU(
            np.rot90(img.astype('float32'),3)
        )
    else:
        hdu = fits.PrimaryHDU(
            img.astype('float32')
        )
    del img

    # assign the keyword values and comment of the keyword as a tuple to write both to header.
    hdu.header["BUNIT"] = ("adu", "Unit of array values")
    hdu.header["CCDXPIXE"] = (
        selfconfig["camera"][selfname]["settings"]["x_pixel"],
        "[um] Size of unbinned pixel, in X",
    )
    hdu.header["CCDYPIXE"] = (
        selfconfig["camera"][selfname]["settings"]["y_pixel"],
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
        selfconfig["camera"][selfname]["settings"]["do_cosmics"],
        "Header item to indicate whether to do cosmic ray removal",
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
    hdu.header["TELID"] = selfconfig["telescope"]["telescope1"][
        "telescop"
    ][:4]
    hdu.header["TELESCOP"] = selfconfig["telescope"]["telescope1"][
        "telescop"
    ][:4]
    hdu.header["PTRTEL"] = selfconfig["telescope"]["telescope1"][
        "ptrtel"
    ]
    hdu.header["PROPID"] = "ptr-" + selfconfig["obs_id"] + "-001-0001"
    hdu.header["BLKUID"] = (
        "1234567890",
        "Just a placeholder right now. WER",
    )
    hdu.header["INSTRUME"] = (selfconfig["camera"][selfname]["name"], "Name of camera")
    hdu.header["CAMNAME"] = (selfconfig["camera"][selfname]["desc"], "Instrument used")
    hdu.header["DETECTOR"] = (
        selfconfig["camera"][selfname]["detector"],
        "Name of camera detector",
    )
    hdu.header["CAMMANUF"] = (
        selfconfig["camera"][selfname]["manufacturer"],
        "Name of camera manufacturer",
    )
    hdu.header["DARKSLID"] = (darkslide_state, "Darkslide state")
    hdu.header['SHUTTYPE'] = (selfconfig["camera"][selfname]["settings"]["shutter_type"],
                              'Type of shutter')
    hdu.header["GAIN"] = (
        camera_known_gain,
        "[e-/ADU] Pixel gain",
    )
    hdu.header["ORIGGAIN"] = (
        camera_known_gain,
        "[e-/ADU] Original Pixel gain",
    )
    hdu.header["RDNOISE"] = (
        camera_known_readnoise,
        "[e-/pixel] Read noise",
    )
    hdu.header["OSCCAM"] = (is_osc, "Is OSC camera")
    hdu.header["OSCMONO"] = (False, "If OSC, is this a mono image or a bayer colour image.")

    hdu.header["FULLWELL"] = (
        selfconfig["camera"][selfname]["settings"][
            "fullwell_capacity"
        ],
        "Full well capacity",
    )

    is_cmos=selfconfig["camera"][selfname]["settings"]["is_cmos"]
    driver=selfconfig["camera"][selfname]["driver"]
    hdu.header["CMOSCAM"] = (is_cmos, "Is CMOS camera")

    if is_cmos and driver ==  "QHYCCD_Direct_Control":
        hdu.header["CMOSGAIN"] = (selfconfig["camera"][selfname][
            "settings"
        ]['direct_qhy_gain'], "CMOS Camera System Gain")


        hdu.header["CMOSOFFS"] = (selfconfig["camera"][selfname][
            "settings"
        ]['direct_qhy_offset'], "CMOS Camera System Offset")

        hdu.header["CAMUSBT"] = (selfconfig["camera"][selfname][
            "settings"
        ]['direct_qhy_usb_traffic'], "Camera USB traffic")
        hdu.header["READMODE"] = (selfconfig["camera"][selfname][
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
            expected_endpoint_of_substack_exposure - substack_start_time,
            "[s] Actual exposure length",
        )  # This is the exposure in seconds specified by the user
        hdu.header["EFFEXPT"] = (
            exposure_time,
            "[s] Integrated exposure length",
        )
        hdu.header["EFFEXPN"] = (
            int(exposure_time / 10),
            "[s] Number of integrated exposures",
        )

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
            "[UTC days] Julian Date at start of exposure")

        hdu.header["MJD-MID"] = (
            Time(start_time_of_observation + (0.5 * exposure_time), format="unix").mjd,
            "[UTC days] Modified Julian Date mid exposure date/time",
        )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
        hdu.header["JD-MID"] = (
            Time(start_time_of_observation+ (0.5 * exposure_time), format="unix").jd,

            "[UTC days] Julian Date at middle of exposure",
        )

        hdu.header["EXPTIME"] = (
            exposure_time,
            "[s] Actual exposure length",
        )  # This is the exposure in seconds specified by the user
        hdu.header["EFFEXPT"] = (
            exposure_time,
            "[s] Integrated exposure length",
        )
        hdu.header["EFFEXPN"] = (
            1,
            "[s] Number of integrated exposures",
        )

        hdu.header[
            "EXPOSURE"
        ] = (
            exposure_time,
            "[s] Actual exposure length",
        )  # Ideally this needs to be calculated from actual times

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
            selfconfig["camera"][selfname]["settings"][
                "max_linearity"
            ]
        ),
        "[ADU] Non-linearity level",
    )
    if pane is not None:
        hdu.header["MOSAIC"] = (True, "Is mosaic")
        hdu.header["PANE"] = pane

    hdu.header["FOCAL"] = (
        round(
            float(
                selfconfig["telescope"]["telescope1"]["focal_length"]
            ),
            2,
        ),
        "[mm] Telescope focal length",
    )
    hdu.header["APR-DIA"] = (
        round(
            float(selfconfig["telescope"]["telescope1"]["aperture"]), 2
        ),
        "[mm] Telescope aperture",
    )
    hdu.header["APR-AREA"] = (
        round(
            float(
                selfconfig["telescope"]["telescope1"][
                    "collecting_area"
                ]
            ),
            1,
        ),
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
        # print("problem with the premount?")
        # print(traceback.format_exc())
        pass
    hdu.header["OBSERVER"] = (
        observer_user_name,
        "Observer name",
    )
    hdu.header["OBSNOTE"] = hint[0:54]  # Needs to be truncated.

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
            selfconfig["rotator"]["rotator1"]["name"],
            "Rotator name",
        )
        hdu.header["ROTANGLE"] = (avg_rot[1], "[deg] Rotator angle")
        hdu.header["ROTMOVNG"] = (avg_rot[2], "Rotator is moving")
    except:
        pass

    try:
        hdu.header["FOCUS"] = (
            selfconfig["focuser"]["focuser1"]["name"],
            "Focuser name",
        )
        hdu.header["FOCUSPOS"] = (avg_foc[1], "[um] Focuser position")
        hdu.header["FOCUSTMP"] = (avg_foc[2], "[C] Focuser temperature")
        hdu.header["FOCUSMOV"] = (avg_foc[3], "Focuser is moving")
    except:
        print("There is something fishy in the focuser routine")
    
    if pixscale == None:
        hdu.header["PIXSCALE"] = (
            'Unknown',
            "[arcsec/pixel] Nominal pixel scale on sky",
        )
    else:
        hdu.header["PIXSCALE"] = (
            float(pixscale),
            "[arcsec/pixel] Nominal pixel scale on sky",
        )

    hdu.header["DRZPIXSC"] = (selfconfig["camera"][selfname]["settings"]['drizzle_value_for_later_stacking'], 'Target pixel scale for drizzling')

    hdu.header["REQNUM"] = ("00000001", "Request number")
    hdu.header["ISMASTER"] = (False, "Is master image")
    current_camera_name = selfconfig["camera"][selfname]["name"]

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
        red_name01 = (next_seq + "-" +selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" +  str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")
    else:
        red_name01 = (selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" + next_seq+ "-" + str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")

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
    hdu.header["ORIGNAME"] = str(raw_name00 + ".fz")

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
        corrected_ra_for_header,
        "[hrs] Telescope right ascension",
    )
    hdu.header["RADEG"] = tempRAdeg
    hdu.header["DECDEG"] = tempDECdeg

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

    hdusmalldata=copy.deepcopy(hdu.data)
    # Quick flash bias and dark frame
    selfnative_bin = selfconfig["camera"][selfname]["settings"]["native_bin"]

    broadband_ss_biasdark_exp_time = selfconfig['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
    narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * selfconfig['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']
    dark_exp_time = selfconfig['camera']['camera_1_1']['settings']['dark_exposure']

    

    if not manually_requested_calibration and not substack:
        
        
        
        
        #breakpoint()
        
        
        try:
            # If not a smartstack use a scaled masterdark
            timetakenquickdark=time.time()
            try:
                if smartstackid == 'no':
                    # Initially debias the image
                    hdusmalldata = hdusmalldata - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy') #g_dev['cam'].biasFiles[str(1)]
                    # Sort out an intermediate dark
                    fraction_through_range=0
                    if exposure_time < 0.5:
                        hdusmalldata=hdusmalldata-np.load(localcalibmastersdirectory + tempfrontcalib + 'halfsecondDARK_master_bin1.npy')#np.load(g_dev['cam'].darkFiles['halfsec_exposure_dark']*exposure_time)
                    elif exposure_time < 2.0:
                        fraction_through_range=(exposure_time-0.5)/(2.0-0.5)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + '2secondDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'halfsecondDARK_master_bin1.npy'))
                        hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                        del tempmasterDark
                    elif exposure_time < 10.0:
                        fraction_through_range=(exposure_time-2)/(10.0-2.0)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + '10secondDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + '2secondDARK_master_bin1.npy'))
                        hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                        del tempmasterDark
                    elif exposure_time < broadband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-10)/(broadband_ss_biasdark_exp_time-10.0)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + '10secondDARK_master_bin1.npy'))
                        hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                        del tempmasterDark
                    elif exposure_time < narrowband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssDARK_master_bin1.npy'))
                        hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                        del tempmasterDark
                    elif dark_exp_time > narrowband_ss_biasdark_exp_time:
                        fraction_through_range=(exposure_time-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                        tempmasterDark=(fraction_through_range * np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy')) + ((1-fraction_through_range) * np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy'))
                        hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                        del tempmasterDark
                    else:
                        hdusmalldata=hdusmalldata-(np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssDARK_master_bin1.npy')*exposure_time)
                elif exposure_time == broadband_ss_biasdark_exp_time:
                    hdusmalldata = hdusmalldata - (np.load(localcalibmastersdirectory + tempfrontcalib + 'broadbandssBIASDARK_master_bin1.npy'))
                elif exposure_time == narrowband_ss_biasdark_exp_time:
                    hdusmalldata = hdusmalldata - (np.load(localcalibmastersdirectory + tempfrontcalib + 'narrowbandssBIASDARK_master_bin1.npy'))
                else:
                    print ("DUNNO WHAT HAPPENED!")
                    hdusmalldata = hdusmalldata - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy')
                    hdusmalldata = hdusmalldata - (np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy') * exposure_time)
            except:
                try:
                    hdusmalldata = hdusmalldata - np.load(localcalibmastersdirectory + tempfrontcalib + 'BIAS_master_bin1.npy')
                    hdusmalldata = hdusmalldata - (np.load(localcalibmastersdirectory + tempfrontcalib + 'DARK_master_bin1.npy') * exposure_time)
                except:
                    print ("Could not bias or dark file.")
        except Exception as e:
            print("debias/darking light frame failed: ", e)

        # Quick flat flat frame
        try:                
            hdusmalldata = np.divide(hdusmalldata, np.load(localcalibmastersdirectory + 'masterFlat_'+this_exposure_filter + "_bin" + str(1) +'.npy'))
        except Exception as e:
            print("flatting light frame failed", e)

        try:
            hdusmalldata[np.load(localcalibmastersdirectory + tempfrontcalib + 'badpixelmask_bin1.npy')] = np.nan

        except Exception as e:
            print("Bad Pixel Masking light frame failed: ", e)
    
    # else:
    #     hdusmalldata

    # This saves the REDUCED file to disk
    # If this is for a smartstack, this happens immediately in the camera thread after we have a "reduced" file
    # So that the smartstack queue can start on it ASAP as smartstacks
    # are by far the longest task to undertake.
    # If it isn't a smartstack, it gets saved in the slow process queue.
    # if "hdusmalldata" in locals():
    # Set up reduced header
    hdusmallheader=copy.deepcopy(hdu.header)
    if not manually_requested_calibration:
        #From the reduced data, crop around the edges of the
        #raw 1x1 image to get rid of overscan and crusty edge bits
        #edge_crop=selfconfig["camera"][selfname]["settings"]['reduced_image_edge_crop']
        edge_crop=100
        if edge_crop > 0:
            hdusmalldata=hdusmalldata[edge_crop:-edge_crop,edge_crop:-edge_crop]

            hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) - (edge_crop * 2)
            hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) - (edge_crop * 2)
            hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) - (edge_crop * 2)
            hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) - (edge_crop * 2)

        # bin to native binning
        if selfnative_bin != 1 and (not pixscale == None):
            reduced_hdusmalldata=(block_reduce(hdusmalldata,selfnative_bin))
            reduced_hdusmallheader=copy.deepcopy(hdusmallheader)
            reduced_hdusmallheader['XBINING']=selfnative_bin
            reduced_hdusmallheader['YBINING']=selfnative_bin
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

            reduced_hdusmalldata=hdusmalldata+200.0
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
        
        
        # Really need to thresh the image
        googtime=time.time()
        int_array_flattened=hdusmalldata.astype(int).ravel()
        int_array_flattened=int_array_flattened[int_array_flattened > -10000]
        unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
        m=counts.argmax()
        imageMode=unique[m]
        print ("Calculating Mode: " +str(time.time()-googtime))


        # Zerothreshing image
        googtime=time.time()
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
                                                                zeroValue=(imageMode-counter)
                                                                breaker =0

        hdusmalldata[hdusmalldata < zeroValue] = np.nan

        print ("Zero Threshing Image: " +str(time.time()-googtime))
        
        
        googtime=time.time()

        #Check there are no nans in the image upon receipt
        # This is necessary as nans aren't interpolated in the main thread.
        # Fast next-door-neighbour in-fill algorithm
        #num_of_nans=np.count_nonzero(np.isnan(hdusmalldata))
        x_size=hdusmalldata.shape[0]
        y_size=hdusmalldata.shape[1]
        # this is actually faster than np.nanmean
        #imageMode=bn.nanmedian(hdusmalldata)

        #np.divide(np.nansum(hdusmalldata),(x_size*y_size)-num_of_nans)
        #imageMode=imageMode
        #breakpoint()
        # while num_of_nans > 0:
        #     # List the coordinates that are nan in the array
        #
        nan_coords=np.argwhere(np.isnan(hdusmalldata))

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
                hdusmalldata[x_nancoord,y_nancoord]=imageMode
                done=True
            elif x_nancoord > (x_size-100):
                hdusmalldata[x_nancoord,y_nancoord]=imageMode

                done=True
            elif y_nancoord < 100:
                hdusmalldata[x_nancoord,y_nancoord]=imageMode

                done=True
            elif y_nancoord > (y_size-100):
                hdusmalldata[x_nancoord,y_nancoord]=imageMode
                done=True

            # left
            if not done:
                if x_nancoord != 0:
                    value_here=hdusmalldata[x_nancoord-1,y_nancoord]
                    if not np.isnan(value_here):
                        hdusmalldata[x_nancoord,y_nancoord]=value_here
                        done=True
            # right
            if not done:
                if x_nancoord != (x_size-1):
                    value_here=hdusmalldata[x_nancoord+1,y_nancoord]
                    if not np.isnan(value_here):
                        hdusmalldata[x_nancoord,y_nancoord]=value_here
                        done=True
            # below
            if not done:
                if y_nancoord != 0:
                    value_here=hdusmalldata[x_nancoord,y_nancoord-1]
                    if not np.isnan(value_here):
                        hdusmalldata[x_nancoord,y_nancoord]=value_here
                        done=True
            # above
            if not done:
                if y_nancoord != (y_size-1):
                    value_here=hdusmalldata[x_nancoord,y_nancoord+1]
                    if not np.isnan(value_here):
                        hdusmalldata[x_nancoord,y_nancoord]=value_here
                        done=True

        hdusmalldata[np.isnan(hdusmalldata)] = imageMode
            #num_of_nans=np.count_nonzero(np.isnan(hdusmalldata))

        print ("Denan Image: " +str(time.time()-googtime))
        
        # Actually save out ONE reduced file for different threads to use.
        image_filename=localcalibrationdirectory + "smartstacks/reducedimage" + str(time.time()).replace('.','') + '.npy'
        
        # Save numpy array out.
        np.save(image_filename, hdusmalldata)
        
        # Just save astropy header
        cleanhdu=fits.PrimaryHDU()
        cleanhdu.data=np.asarray([0])
        cleanhdu.header=hdusmallheader
        cleanhdu.writeto(image_filename.replace('.npy','.head'))
        
        
        
        
        
        
        
        #g_dev['obs'].to_sep((hdusmalldata, pixscale, float(hdu.header["RDNOISE"]), avg_foc[1], focus_image, im_path, text_name, hdusmallheader, cal_path, cal_name, frame_type, focus_position, selfnative_bin, exposure_time))
        #np.save(hdusmalldata, septhread_filename)
        pickle.dump((image_filename,imageMode), open(septhread_filename+ '.temp', 'wb'))
        
            
            
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
                print("Failed to write raw file: ", e)
                
        # This puts the file into the smartstack queue
        # And gets it underway ASAP.
        if frame_type.lower() in ['fivepercent_exposure_dark','tenpercent_exposure_dark', 'quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark', 'fivesec_exposure_dark', 'tensec_exposure_dark', 'fifteensec_exposure_dark', 'twentysec_exposure_dark', 'thirtysec_exposure_dark', 'broadband_ss_biasdark', 'narrowband_ss_biasdark']:
            a_dark_exposure=True
        else:
            a_dark_exposure=False

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


            picklepayload=(reduced_hdusmallheader,copy.deepcopy(selfconfig),camalias, slow_process, altpath)

            picklefilename='testred'+str(time.time()).replace('.','')
            pickle.dump(picklepayload, open(localcalibrationdirectory + 'smartstacks/'+picklefilename,'wb'))
           
            subprocess.Popen(['python','local_reduce_file_subprocess.py',picklefilename],cwd=localcalibrationdirectory + 'smartstacks',stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)


                          

        # Send data off to process jpeg if not a smartstack
        if smartstackid == 'no':
            #g_dev['obs'].to_mainjpeg((hdusmalldata, smartstackid, paths, pier_side, zoom_factor))
            # np.save(hdusmalldata, mainjpegthread_filename)
            pickle.dump((image_filename,imageMode), open(mainjpegthread_filename + '.temp', 'wb'))
            os.rename(mainjpegthread_filename + '.temp', mainjpegthread_filename)

        

        if platesolvethread_filename !='no':
            # np.save(hdusmalldata, platesolvethread_filename)
            pickle.dump((image_filename,imageMode), open(platesolvethread_filename+ '.temp', 'wb'))
            
            os.rename(platesolvethread_filename + '.temp', platesolvethread_filename)
            
           #g_dev['obs'].to_platesolve((hdusmalldata, hdusmallheader, cal_path, cal_name, frame_type, time.time(), pixscale, ra_at_time_of_exposure,dec_at_time_of_exposure, firstframesmartstack, useastrometrynet, False, ''))
                    # If it is the last of a set of smartstacks, we actually want to
                    # wait for the platesolve and nudge before starting the next smartstack.
    

        # Now that the jpeg, sep and platesolve has been sent up pronto,
        # We turn back to getting the bigger raw, reduced and fz files dealt with
        if not ( frame_type.lower() in [
            "bias",
            "dark"
            "flat",
            "focus",
            "skyflat",
            "pointing"
            ]) and not a_dark_exposure:
            picklepayload=(copy.deepcopy(hdu.header),copy.deepcopy(selfconfig),camalias, ('fz_and_send', raw_path + raw_name00 + ".fz", copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure))

            picklefilename='testlocalred'+str(time.time()).replace('.','')
            pickle.dump(picklepayload, open(localcalibrationdirectory + 'smartstacks/'+picklefilename,'wb'))
            
            subprocess.Popen(['python','fz_archive_file.py',picklefilename],cwd=localcalibrationdirectory + 'smartstacks',stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)


            



        # Similarly to the above. This saves the RAW file to disk
        # it works 99.9999% of the time.
        if selfconfig['save_raw_to_disk']:
            os.makedirs(
                raw_path, exist_ok=True
            )
            threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, ra_at_time_of_exposure, dec_at_time_of_exposure,'no','thisisdeprecated', dayobs, im_path_r, selfalt_path)),)).start()


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
                threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', selfalt_path + dayobs + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                   frame_type, ra_at_time_of_exposure, dec_at_time_of_exposure,'no','deprecated', dayobs, im_path_r, selfalt_path)),)).start()
                

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
    print(traceback.format_exc())
    
print ("FINISHED! in " + str(time.time()-a_timer))