
"""
This is actually a sub-sub-process.
Each of the OSC colours needs to be SEParately SEP'ed so that
each can be astroaligned to their separate coloured smartstack image.
Say that three times fast.

This is called from SmartStackProcess.py when it is running an OSC stack.
As it is a relatively expensive (in time) operation, they need to run in parallel.
"""

import numpy as np
import sys
import pickle
import os
import time
#import traceback
from astropy.io import fits
from astropy.nddata import block_reduce
from astropy.utils.exceptions import AstropyUserWarning
import warnings
import datetime
warnings.simplefilter('ignore', category=AstropyUserWarning)

#input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testfz1714133591386061','rb'))
input_sep_info=pickle.load(open(sys.argv[1],'rb'))

print ("Starting fz_archive_file.py")
#print (input_sep_info)


temphduheader=input_sep_info[0]
selfconfig=input_sep_info[1]
camname=input_sep_info[2]
slow_process=input_sep_info[3]

googtime=time.time()

# This script assumes we're using the main camera
# TODO: The correct camera should be passed in as an argument to support multiple cameras
camera_name = selfconfig['device_roles']['main_cam']
camera_config = selfconfig["camera"][camera_name]


# Create the fz file ready for PTR Archive
# Note that even though the raw file is int16,
# The compression and a few pieces of software require float32
# BUT it actually compresses to the same size either way
temphduheader["BZERO"] = 0  # Make sure there is no integer scaling left over
temphduheader["BSCALE"] = 1  # Make sure there is no integer scaling left over
if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
    pipefolder = selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS'])
    if not os.path.exists(selfconfig['pipe_archive_folder_path']+'/'+ str(temphduheader['INSTRUME'])):
        os.umask(0)
        os.makedirs(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']))
    if not os.path.exists(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS'])):
        os.umask(0)
        os.makedirs(selfconfig['pipe_archive_folder_path'] +'/'+ str(temphduheader['INSTRUME']) +'/'+ str(temphduheader['DAY-OBS']))

if not camera_config["settings"]["is_osc"]:


    # This routine saves the file ready for uploading to AWS
    hdufz = fits.CompImageHDU(
        np.array(slow_process[2], dtype=np.float32), temphduheader
    )

    if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
        hdufz.writeto(
            pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'), overwrite=True
        )
        os.rename(pipefolder + '/' +str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz'),pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.tempfits.fz').replace('.tempfits.fz','.fits.fz'))

    if selfconfig['ingest_raws_directly_to_archive']:

        hdufz.writeto(
            slow_process[1].replace('.fits','.tempfits'), overwrite=True
        )  # Save full fz file locally

        del hdufz  # remove file from memory now that we are done with it

        os.rename(slow_process[1].replace('.fits','.tempfits'), slow_process[1])

else:  # Is an OSC

    # If it is an OSC, split out the components and save them individually.
    if camera_config["settings"]["osc_bayer"] == 'RGGB':

        newhdured = slow_process[2][::2, ::2]
        GTRonly = slow_process[2][::2, 1::2]
        GBLonly = slow_process[2][1::2, ::2]
        newhdublue = slow_process[2][1::2, 1::2]
        clearV = (block_reduce(slow_process[2],2))

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
        tempfilename = slow_process[1] + '.fz'

        # Save and send R1
        temphduheader['FILTER'] = tempfilter + '_R1'
        temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'R1-EX') + '.fz'

        hdufz = fits.CompImageHDU(
            np.array(newhdured, dtype=np.float32), temphduheader
        )

        if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True
            )
            os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

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
            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True
            )
            os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

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
            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME'].replace('.fits','.tempfits')), overwrite=True
            )
            os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

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

            hdufz.writeto(
                tempfilename.replace('-EX', 'B1-EX').replace('.fits','.tempfits'), overwrite=True#, output_verify='silentfix'
            )  # Save full fz file locally

            os.rename(tempfilename.replace('-EX', 'B1-EX').replace('.fits','.tempfits'),tempfilename.replace('-EX', 'B1-EX'))

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
            hdufz.writeto(
                pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'), overwrite=True
            )
            os.rename(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits','.tempfits'),pipefolder + '/' + str(temphduheader['ORIGNAME']))

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