
"""
This is actually a sub-sub-process.
Each of the OSC colours needs to be SEParately SEP'ed so that
each can be astroaligned to their separate coloured smartstack image.
Say that three times fast.

This is called from SmartStackProcess.py when it is running an OSC stack.
As it is a relatively expensive (in time) operation, they need to run in parallel.
"""

import builtins
import numpy as np
import sys
import pickle
import os
import time
from astropy.io import fits
from astropy.utils.exceptions import AstropyUserWarning
import warnings
import datetime
warnings.simplefilter('ignore', category=AstropyUserWarning)
from astropy import wcs
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from astropy.convolution import interpolate_replace_nans, Gaussian2DKernel

def print(*args):
    rgb = lambda r, g, b: f'\033[38;2;{r};{g};{b}m'
    log_color = (0, 210, 210) # cyan
    c = rgb(*log_color)
    r = '\033[0m' # reset
    builtins.print(f"{c}[sep]{r} {' '.join([str(x) for x in args])}")

#input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testfz17141141966139522','rb'))
input_sep_info=pickle.load(open(sys.argv[1],'rb'))

#print("Starting local_reduce_file_subprocess.py")
#print(input_sep_info)

temphduheader=input_sep_info[0]
selfconfig=input_sep_info[1]
camname=input_sep_info[2]
slow_process=input_sep_info[3]
wcsfilename=input_sep_info[5]

googtime=time.time()

hdureduced = fits.PrimaryHDU()
hdureduced.data = slow_process[2]
hdureduced.header = temphduheader
hdureduced.data = hdureduced.data.astype("float32")

out_file_name=slow_process[1]
del slow_process

unique,counts=np.unique(hdureduced.data.ravel()[~np.isnan(hdureduced.data.ravel())].astype(int), return_counts=True)
m=counts.argmax()
imageMode=unique[m]

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

hdureduced.data[hdureduced.data < zeroValue] = np.nan

# Interpolate image nans
kernel = Gaussian2DKernel(x_stddev=1)
hdureduced.data = interpolate_replace_nans(hdureduced.data, kernel)



# Remove remaining nans
x_size=hdureduced.data.shape[0]
y_size=hdureduced.data.shape[1]
# this is actually faster than np.nanmean
edgefillvalue=imageMode
# List the coordinates that are nan in the array
nan_coords=np.argwhere(np.isnan(hdureduced.data))

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
        hdureduced.data[x_nancoord,y_nancoord]=edgefillvalue
        done=True
    elif x_nancoord > (x_size-100):
        hdureduced.data[x_nancoord,y_nancoord]=edgefillvalue

        done=True
    elif y_nancoord < 100:
        hdureduced.data[x_nancoord,y_nancoord]=edgefillvalue

        done=True
    elif y_nancoord > (y_size-100):
        hdureduced.data[x_nancoord,y_nancoord]=edgefillvalue
        done=True

    # left
    if not done:
        if x_nancoord != 0:
            value_here=hdureduced.data[x_nancoord-1,y_nancoord]
            if not np.isnan(value_here):
                hdureduced.data[x_nancoord,y_nancoord]=value_here
                done=True
    # right
    if not done:
        if x_nancoord != (x_size-1):
            value_here=hdureduced.data[x_nancoord+1,y_nancoord]
            if not np.isnan(value_here):
                hdureduced.data[x_nancoord,y_nancoord]=value_here
                done=True
    # below
    if not done:
        if y_nancoord != 0:
            value_here=hdureduced.data[x_nancoord,y_nancoord-1]
            if not np.isnan(value_here):
                hdureduced.data[x_nancoord,y_nancoord]=value_here
                done=True
    # above
    if not done:
        if y_nancoord != (y_size-1):
            value_here=hdureduced.data[x_nancoord,y_nancoord+1]
            if not np.isnan(value_here):
                hdureduced.data[x_nancoord,y_nancoord]=value_here
                done=True

# Mop up any remaining nans
hdureduced.data[np.isnan(hdureduced.data)] =edgefillvalue


# Wait here for potential wcs solution

print ("Waiting for: " +wcsfilename.replace('.fits','.wcs'))

wcs_timeout_timer=time.time()
while True:
    if os.path.exists (wcsfilename.replace('.fits','.wcs')):
        print ("success!")

        #if os.path.exists(wcsname):
        print ("wcs exists: " + str(wcsfilename.replace('.fits','.wcs')))
        wcsheader = fits.open(wcsfilename.replace('.fits','.wcs'))[0].header
        temphduheader.update(wcs.WCS(wcsheader).to_header(relax=True))

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

        # Alter header appropriately if the image has been binned.
        binning= hdureduced.header["XBINING"]
        if binning > 1:
            w_orig = WCS(temphduheader)
            w_binned = w_orig.slice((slice(None, None, binning), slice(None, None, binning)))

            temphduheader.update(w_binned.to_header(relax=True))

        break
    if os.path.exists (wcsfilename.replace('.fits','.failed')):
        print ("failure!")
        break
    if (time.time() - wcs_timeout_timer) > 240:
        print ("took too long")
        break
    time.sleep(2)

hdureduced.header["DATE"] = (
    datetime.date.strftime(
        datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
    ),
    "Date FITS file was written",
)

hdureduced.writeto(
    out_file_name, overwrite=True, output_verify='silentfix'
)  # Save flash reduced file locally

if selfconfig["save_to_alt_path"] == "yes":
    hdureduced.writeto( selfconfig['alt_path'] +'/' +temphduheader['OBSID'] +'/' +temphduheader['DAY-OBS'] + "/reduced/" + out_file_name.split('/')[-1].replace('EX00','EX00-'+temphduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    )  # Save full raw file locally

try:
    os.remove(sys.argv[1])
except:
    pass

sys.exit()