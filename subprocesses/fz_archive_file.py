
"""
This creates an fz file for the archive
"""

import numpy as np
import sys
import pickle
import os
import time
import builtins
from astropy.io import fits
from astropy.nddata import block_reduce
from astropy.utils.exceptions import AstropyUserWarning
import warnings
import datetime
warnings.simplefilter('ignore', category=AstropyUserWarning)
#import bottleneck as bn

from astropy import wcs
from astropy.coordinates import SkyCoord
#input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testfz1714133591386061','rb'))
input_sep_info=pickle.load(open(sys.argv[1],'rb'))


#input_sep_info=pickle.load(open('C:\ptr\eco1\smartstacks/testlocalred17424062603143346','rb'))

def print(*args):
    rgb = lambda r, g, b: f'\033[38;2;{r};{g};{b}m'
    log_color = (240, 200, 90) # gold
    c = rgb(*log_color)
    r = '\033[0m' # reset
    builtins.print(f"{c}[fz_archive]{r} {' '.join([str(x) for x in args])}")

#print("Starting fz_archive_file.py")
# print(input_sep_info)


temphduheader=input_sep_info[0]
selfconfig=input_sep_info[1]
camname=input_sep_info[2]
slow_process=input_sep_info[3]
wcsfilename=slow_process[7]


#### FZ Compression can't handle NAN so we need to use a sentinal value
#### In our case, we use -512.3456789. This is low enough that it is highly
#### unlikely that a pixel would have this real value  in the history of the universe
#### But not so low it is impossible to use fits browsers
actual_data=np.array(slow_process[2],dtype=np.float32)
actual_data=np.nan_to_num(actual_data, nan=-251.2345733642578)

# Dump the original array from memory
tempfilename=slow_process[1]
del slow_process


googtime=time.time()

# This script assumes we're using the main camera
# TODO: The correct camera should be passed in as an argument to support multiple cameras
camera_name = selfconfig['device_roles']['main_cam']
camera_config = selfconfig["camera"][camera_name]


# This is the failsafe directory.... if it can't be written to the PIPE folder
# Which is usually a shared drive on the network, it gets saved here
failsafe_directory=selfconfig['archive_path'] + 'failsafe'

# Create the fz file ready for PTR Archive
# Note that even though the raw file is int16,
# The compression and a few pieces of software require float32
# BUT it actually compresses to the same size either way
temphduheader["BZERO"] = 0  # Make sure there is no integer scaling left over
temphduheader["BSCALE"] = 1  # Make sure there is no integer scaling left over
if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
    
    if not os.path.exists(failsafe_directory):
        os.umask(0)
        os.makedirs(failsafe_directory)
    try:
        pipefolder = selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS'])
        if not os.path.exists(selfconfig['pipe_archive_folder_path']+'/'+ str(temphduheader['INSTRUME'])):
            os.umask(0)
            os.makedirs(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']))
        if not os.path.exists(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS'])):
            os.umask(0)
            os.makedirs(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS']))
    except:
        print ("looks like an error making the pipe archive folder path")
    

# Wait here for potential wcs solution

print ("Waiting for: " +wcsfilename.replace('.fits','.wcs'))

# While waiting, dump out image to disk temporarily to be picked up later.
np.save(tempfilename.replace('.fits.fz','.tempnpy'), actual_data)
#temphduheader=copy.deepcopy(hdureduced.header)
del actual_data


wcs_timeout_timer=time.time()
while True:
    if os.path.exists (wcsfilename.replace('.fits','.wcs')):
        print ("success!")
        
        
        #if os.path.exists(wcsname):
        print ("wcs exists: " + str(wcsfilename.replace('.fits','.wcs')))
        wcsheader = fits.open(wcsfilename.replace('.fits','.wcs'))[0].header
        temphduheader.update(wcs.WCS(wcsheader).to_header(relax=True))
        
        # # Create a WCS instance from your header
        # wcstrue = wcs.WCS(temphduheader)
        
        # Get the RA/DEC at the reference pixel (CRPIX1, CRPIX2)
        ra_ref = temphduheader['CRVAL1']
        dec_ref = temphduheader['CRVAL2']
        
        tempointing = SkyCoord(ra_ref, dec_ref, unit='deg')
        tempointing=tempointing.to_string("hmsdms").split(' ')

        temphduheader["RA"] = (
            tempointing[0],
            "[hms] Telescope right ascension",
        )
        temphduheader["DEC"] = (
            tempointing[1],
            "[dms] Telescope declination",
        )
        
        temphduheader["RA-HMS"] = temphduheader["RA"]
        temphduheader["DEC-DMS"] = temphduheader["DEC"]
        
        temphduheader["ORIGRA"] = temphduheader["RA"]
        temphduheader["ORIGDEC"] = temphduheader["DEC"]
        temphduheader["RAhrs"] = (
            round(ra_ref / 15,8),
            "[hrs] Telescope right ascension",
        )
        temphduheader["RADEG"] = round(ra_ref,8)
        temphduheader["DECDEG"] = round(dec_ref,8)

        temphduheader["TARG-CHK"] = (
            (ra_ref)
            + dec_ref,
            "[deg] Sum of RA and dec",
        )
       
        
        del wcsheader
        
        break
    if os.path.exists (wcsfilename.replace('.fits','.failed')):
        print ("failure!")
        break
    if (time.time() - wcs_timeout_timer) > 120:
        print ("took too long")
        break
    time.sleep(2)
    

actual_data=np.load(tempfilename.replace('.fits.fz','.tempnpy.npy'))

try:
    os.remove(tempfilename.replace('.fits.fz','.tempnpy.npy'))
except:
    pass

if not camera_config["settings"]["is_osc"]:


    # This routine saves the file ready for uploading to AWS
    hdufz = fits.CompImageHDU(
        np.array(actual_data, dtype=np.float32), temphduheader
    )
    del actual_data

    if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
        try:
            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
            )
            os.rename(pipefolder + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))

        except:
            print ("Failed to save file to pipe folder, saving to storage area for later upload")
            hdufz.writeto(
                failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
            )
            os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),failsafe_directory  + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))

    

    if selfconfig['ingest_raws_directly_to_archive']:

        hdufz.writeto(
            tempfilename.replace('.fits','.tempfits'), overwrite=True
        )  # Save full fz file locally

        del hdufz  # remove file from memory now that we are done with it

        os.rename(tempfilename.replace('.fits','.tempfits'), tempfilename)

else:  # Is an OSC

    # If it is an OSC, split out the components and save them individually.
    if camera_config["settings"]["osc_bayer"] == 'RGGB':

        newhdured = np.array(actual_data[::2, ::2])
        GTRonly = np.array(actual_data[::2, 1::2])
        GBLonly = np.array(actual_data[1::2, ::2])
        newhdublue = np.array(actual_data[1::2, 1::2])
        clearV = (block_reduce(actual_data,2))
        
        del actual_data

        oscmatchcode = (datetime.datetime.now().strftime("%d%m%y%H%M%S"))

        temphduheader["OSCMATCH"] = oscmatchcode
        temphduheader['OSCSEP'] = 'yes'
        temphduheader['NAXIS1'] = float(temphduheader['NAXIS1'])/2
        temphduheader['NAXIS2'] = float(temphduheader['NAXIS2'])/2
        temphduheader['CRPIX1'] = float(temphduheader['CRPIX1'])/2
        temphduheader['CRPIX2'] = float(temphduheader['CRPIX2'])/2
        try:
            temphduheader['PIXSCALE'] = float(temphduheader['PIXSCALE'])*2
        except:
            pass
        temphduheader['CDELT1'] = float(temphduheader['CDELT1'])*2
        temphduheader['CDELT2'] = float(temphduheader['CDELT2'])*2
        tempfilter = temphduheader['FILTER']
        #tempfilename = slow_process[1]

        # Save and send R1
        temphduheader['FILTER'] = tempfilter + '_R1'
        temphduheader['ORIGNAME'] = (temphduheader['ORIGNAME'].replace('-EX', 'R1-EX') + '.fz').replace('.fz.fz','.fz')

        hdufz = fits.CompImageHDU(
            np.array(newhdured, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
            
            try:
            
                hdufz.writeto(
                    pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True
                )
                os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))
            
            except:
                print ("Failed to save file to pipe folder, saving to storage area for later upload")
                hdufz.writeto(
                    failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
                )
                os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),failsafe_directory  + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))


        if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:

            hdufz.writeto(
                tempfilename.replace('-EX', 'R1-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'
            )  # Save full fz file locally
            os.rename(tempfilename.replace('-EX', 'R1-EX').replace('.fits','.tempfits'), tempfilename.replace('-EX', 'R1-EX') )


        del newhdured

        # Save and send G1
        temphduheader['FILTER'] = tempfilter + '_G1'
        temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('R1-EX', 'G1-EX')

        hdufz = fits.CompImageHDU(
            np.array(GTRonly, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
            try:
                hdufz.writeto(pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True)
                os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))
            
            except:
                print ("Failed to save file to pipe folder, saving to storage area for later upload")
                hdufz.writeto(
                    failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
                )
                os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),failsafe_directory  + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))


        if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:

            hdufz.writeto(
                tempfilename.replace('-EX', 'G1-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'
            )  # Save full fz file locally
            os.rename(tempfilename.replace('-EX', 'G1-EX').replace('.fits','.tempfits'),tempfilename.replace('-EX', 'G1-EX'))

        del GTRonly

        # Save and send G2
        temphduheader['FILTER'] = tempfilter + '_G2'
        temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('G1-EX', 'G2-EX')

        hdufz = fits.CompImageHDU(
            np.array(GBLonly, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
            try:
                hdufz.writeto(
                    pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True
                )
                os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

            except:
                print ("Failed to save file to pipe folder, saving to storage area for later upload")
                hdufz.writeto(
                    failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
                )
                os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),failsafe_directory  + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))


        if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:

            hdufz.writeto(
                tempfilename.replace('-EX', 'G2-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'

            )  # Save full fz file locally

            os.rename(tempfilename.replace('-EX', 'G2-EX').replace('.fits','.tempfits'),tempfilename.replace('-EX', 'G2-EX'))

        del GBLonly

        # Save and send B1
        temphduheader['FILTER'] = tempfilter + '_B1'
        temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('G2-EX', 'B1-EX')

        hdufz = fits.CompImageHDU(
            np.array(newhdublue, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:

            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'), overwrite=True
            )
            os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

        if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
            try:
                hdufz.writeto(
                    tempfilename.replace('-EX', 'B1-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'
                )  # Save full fz file locally
    
                os.rename(tempfilename.replace('-EX', 'B1-EX').replace('.fits','.tempfits'),tempfilename.replace('-EX', 'B1-EX'))
            
            except:
                print ("Failed to save file to pipe folder, saving to storage area for later upload")
                hdufz.writeto(
                    failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
                )
                os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))


        del newhdublue

        # Save and send clearV
        temphduheader['FILTER'] = tempfilter + '_clearV'
        temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('B1-EX', 'CV-EX')
        temphduheader['SATURATE']=float(temphduheader['SATURATE']) * 4
        temphduheader['FULLWELL']=float(temphduheader['FULLWELL']) * 4
        temphduheader['MAXLIN']=float(temphduheader['MAXLIN']) * 4

        hdufz = fits.CompImageHDU(
            np.array(clearV, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
            try:
                hdufz.writeto(
                    pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'), overwrite=True
                )
                os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))
            
            except:
                print ("Failed to save file to pipe folder, saving to storage area for later upload")
                hdufz.writeto(
                    failsafe_directory + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
                )
                os.rename(failsafe_directory + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),failsafe_directory  + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))


        if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:

            hdufz.writeto(
                tempfilename.replace('-EX', 'CV-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'
            )
            os.rename(tempfilename.replace('-EX', 'CV-EX').replace('.fits','.tempfits'),tempfilename.replace('-EX', 'CV-EX'))

        del clearV

    else:
        print("this bayer grid not implemented yet")

print (" FZ_archive took:   " + str(time.time()-googtime))

try:
    os.remove(sys.argv[1])
except:
    pass

sys.exit()