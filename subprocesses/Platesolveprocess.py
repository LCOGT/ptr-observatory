# -*- coding: utf-8 -*-
"""
Created on Sun Apr 23 05:49:37 2023

@author: observatory
"""

import sys
import pickle
from astropy.nddata import block_reduce
import numpy as np
import sep
from astropy.table import Table
from astropy.io import fits
from planewave import platesolve
import os




input_psolve_info=pickle.load(sys.stdin.buffer)
#input_psolve_info=pickle.load(open('testplatesolvepickle','rb'))


hdufocusdata=input_psolve_info[0]
hduheader=input_psolve_info[1]
cal_path=input_psolve_info[2]
cal_name=input_psolve_info[3]
frame_type=input_psolve_info[4]
time_platesolve_requested=input_psolve_info[5]
pixscale=input_psolve_info[6]
pointing_ra=input_psolve_info[7]
pointing_dec=input_psolve_info[8]
platesolve_crop=input_psolve_info[9]
bin_for_platesolve=input_psolve_info[10]
platesolve_bin_factor=input_psolve_info[11]
image_saturation_level = input_psolve_info[12]



# focdate=time.time()

# Crop the image for platesolving

# breakpoint()

fx, fy = hdufocusdata.shape

crop_width = (fx * platesolve_crop) / 2
crop_height = (fy * platesolve_crop) / 2

# Make sure it is an even number for OSCs
if (crop_width % 2) != 0:
    crop_width = crop_width+1
if (crop_height % 2) != 0:
    crop_height = crop_height+1

crop_width = int(crop_width)
crop_height = int(crop_height)

# breakpoint()
if crop_width > 0 or crop_height > 0:
    hdufocusdata = hdufocusdata[crop_width:-crop_width, crop_height:-crop_height]
#plog("Platesolve image cropped to " + str(hdufocusdata.shape))

binfocus = 1
#if self.config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:
if bin_for_platesolve:
    #platesolve_bin_factor=self.config["camera"][g_dev['cam'].name]["settings"]['platesolve_bin_value']
    hdufocusdata=block_reduce(hdufocusdata,platesolve_bin_factor)
    binfocus=platesolve_bin_factor                    

#plog("platesolve construction time")
#plog(time.time() -focdate)

# actseptime=time.time()
focusimg = np.array(
    hdufocusdata, order="C"
)


# Some of these are liberated from BANZAI
bkg = sep.Background(focusimg)

#sepsky = ( np.nanmedian(bkg), "Sky background estimated by SEP" )

focusimg -= bkg
ix, iy = focusimg.shape
border_x = int(ix * 0.05)
border_y = int(iy * 0.05)
sep.set_extract_pixstack(int(ix*iy - 1))
#This minarea is totally fudgetastically emprical comparing a 0.138 pixelscale QHY Mono
# to a 1.25/2.15 QHY OSC. Seems to work, so thats good enough.
# Makes the minarea small enough for blocky pixels, makes it large enough for oversampling
minarea= -9.2421 * pixscale + 16.553
if minarea < 5:  # There has to be a min minarea though!
    minarea = 5

sources = sep.extract(
    focusimg, 5.0, err=bkg.globalrms, minarea=minarea
)
#plog ("min_area: " + str(minarea))
sources = Table(sources)
sources = sources[sources['flag'] < 8]

sources = sources[sources["peak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
sources = sources[sources["cpeak"] < 0.8 * image_saturation_level * pow(binfocus, 2)]
#sources = sources[sources["peak"] > 150 * pow(binfocus,2)]
#sources = sources[sources["cpeak"] > 150 * pow(binfocus,2)]
sources = sources[sources["flux"] > 2000]
sources = sources[sources["x"] < ix - border_x]
sources = sources[sources["x"] > border_x]
sources = sources[sources["y"] < iy - border_y]
sources = sources[sources["y"] > border_y]

# BANZAI prune nans from table
nan_in_row = np.zeros(len(sources), dtype=bool)
for col in sources.colnames:
    nan_in_row |= np.isnan(sources[col])
sources = sources[~nan_in_row]
    #plog("Actual Platesolve SEP time: " + str(time.time()-actseptime))
#except:
#    plog("Something went wrong with platesolve SEP")

# # Fast checking of the NUMBER of sources
# # No reason to run a computationally intensive
# # SEP routine for that, just photutils will do.
# psource_timer_begin=time.time()
# plog ("quick image stats from photutils")
# tempmean, tempmedian, tempstd = sigma_clipped_stats(hdufocusdata, sigma=3.0)
# plog((tempmean, tempmedian, tempstd))
# #daofind = DAOStarFinder(fwhm=(2.2 / pixscale), threshold=5.*tempstd)  #estimate fwhm in pixels by reasonable focus level.

# if g_dev['foc'].last_focus_fwhm == None:
#     tempfwhm=2.2/(pixscale*binfocus)
# else:
#     tempfwhm=g_dev['foc'].last_focus_fwhm/(pixscale*binfocus)
# daofind = DAOStarFinder(fwhm=tempfwhm , threshold=5.*tempstd)

# plog ("Used fwhm is " + str(tempfwhm) + " pixels")
# sources = daofind(hdufocusdata - tempmedian)
# plog (sources)
# plog("Photutils time to process: " + str(time.time() -psource_timer_begin ))

# We only need to save the focus image immediately if there is enough sources to
#  rationalise that.  It only needs to be on the disk immediately now if platesolve
#  is going to attempt to pick it up.  Otherwise it goes to the slow queue.
# Also, too many sources and it will take an unuseful amount of time to solve
# Too many sources mean a globular or a crowded field where we aren't going to be
# able to solve too well easily OR it is such a wide field of view that who cares
# if we are off by 10 arcseconds?
#plog("Number of sources for Platesolve: " + str(len(sources)))

if len(sources) >= 15:
    hdufocus = fits.PrimaryHDU()
    hdufocus.data = hdufocusdata
    hdufocus.header = hduheader
    hdufocus.header["NAXIS1"] = hdufocusdata.shape[0]
    hdufocus.header["NAXIS2"] = hdufocusdata.shape[1]
    hdufocus.writeto(cal_path + 'platesolvetemp.fits', overwrite=True, output_verify='silentfix')
    pixscale = hdufocus.header['PIXSCALE']
    # if self.config["save_to_alt_path"] == "yes":
    #    self.to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, hdufocus.data, hdufocus.header, \
    #                                   frame_type))

    try:
        hdufocus.close()
    except:
        pass
    del hdufocusdata
    del hdufocus

    # Test here that there has not been a slew, if there has been a slew, cancel out!
    #if self.time_of_last_slew > time_platesolve_requested:
    #    plog("detected a slew since beginning platesolve... bailing out of platesolve.")
        # if not self.config['keep_focus_images_on_disk']:
        #    os.remove(cal_path + cal_name)
        #one_at_a_time = 0
        # self.platesolve_queue.task_done()
        # break
    #else:

    try:
        # time.sleep(1) # A simple wait to make sure file is saved
        solve = platesolve.platesolve(
            cal_path + 'platesolvetemp.fits', pixscale
        )
    except:
        solve = 'error'
    
    pickle.dump(solve, open(cal_path + 'platesolve.pickle', 'wb'))
    
    #breakpoint()
    #     #plog("Platesolve time to process: " + str(time.time() - psolve_timer_begin))

    #     plog(
    #         "PW Solves: ",
    #         solve["ra_j2000_hours"],
    #         solve["dec_j2000_degrees"],
    #     )
    #     # breakpoint()
    #     #pointing_ra = g_dev['mnt'].mount.RightAscension
    #     #pointing_dec = g_dev['mnt'].mount.Declination
    #     #icrs_ra, icrs_dec = g_dev['mnt'].get_mount_coordinates()
    #     #target_ra = g_dev["mnt"].current_icrs_ra
    #     #target_dec = g_dev["mnt"].current_icrs_dec
    #     target_ra = g_dev["mnt"].last_ra
    #     target_dec = g_dev["mnt"].last_dec
    #     solved_ra = solve["ra_j2000_hours"]
    #     solved_dec = solve["dec_j2000_degrees"]
    #     solved_arcsecperpixel = solve["arcsec_per_pixel"]
    #     solved_rotangledegs = solve["rot_angle_degs"]
    #     err_ha = target_ra - solved_ra
    #     err_dec = target_dec - solved_dec
    #     solved_arcsecperpixel = solve["arcsec_per_pixel"]
    #     solved_rotangledegs = solve["rot_angle_degs"]
    #     plog("Deviation from plate solution in ra: " + str(round(err_ha * 15 * 3600, 2)) + " & dec: " + str (round(err_dec * 3600, 2)) + " asec")

    #     # breakpoint()
    #     # Reset Solve timers
    #     g_dev['obs'].last_solve_time = datetime.datetime.now()
    #     g_dev['obs'].images_since_last_solve = 0

    #     # Test here that there has not been a slew, if there has been a slew, cancel out!
    #     if self.time_of_last_slew > time_platesolve_requested:
    #         plog("detected a slew since beginning platesolve... bailing out of platesolve.")
    #         # if not self.config['keep_focus_images_on_disk']:
    #         #    os.remove(cal_path + cal_name)
    #        # one_at_a_time = 0
    #         # self.platesolve_queue.task_done()
    #         # break

    #     # If we are WAY out of range, then reset the mount reference and attempt moving back there.
    #     elif (
    #         err_ha * 15 * 3600 > 1200
    #         or err_dec * 3600 > 1200
    #         or err_ha * 15 * 3600 < -1200
    #         or err_dec * 3600 < -1200
    #     ) and self.config["mount"]["mount1"][
    #         "permissive_mount_reset"
    #     ] == "yes":
    #         g_dev["mnt"].reset_mount_reference()
    #         plog("I've  reset the mount_reference 1")
    #         g_dev["mnt"].current_icrs_ra = solved_ra
    #         #    "ra_j2000_hours"
    #         # ]
    #         g_dev["mnt"].current_icrs_dec = solved_dec
    #         #    "dec_j2000_hours"
    #         # ]
    #         err_ha = 0
    #         err_dec = 0

    #         plog("Platesolve is requesting to move back on target!")
    #         #g_dev['mnt'].mount.SlewToCoordinatesAsync(target_ra, target_dec)

    #         self.pointing_correction_requested_by_platesolve_thread = True
    #         self.pointing_correction_request_time = time.time()
    #         self.pointing_correction_request_ra = target_ra
    #         self.pointing_correction_request_dec = target_dec

    #         # wait_for_slew()

    #     else:

    #         # If the mount has updatable RA and Dec coordinates, then sync that
    #         # But if not, update the mount reference
    #         # try:
    #         #     # If mount has Syncable coordinates
    #         #     g_dev['mnt'].mount.SyncToCoordinates(solved_ra, solved_dec)
    #         #     # Reset the mount reference because if the mount has
    #         #     # syncable coordinates, the mount should already be corrected
    #         #     g_dev["mnt"].reset_mount_reference()

    #         #     if (
    #         #          abs(err_ha * 15 * 3600)
    #         #          > self.config["threshold_mount_update"]
    #         #          or abs(err_dec * 3600)
    #         #          > self.config["threshold_mount_update"]
    #         #      ):
    #         #         #plog ("I am nudging the telescope slightly!")
    #         #         #g_dev['mnt'].mount.SlewToCoordinatesAsync(target_ra, target_dec)
    #         #         #wait_for_slew()
    #         #         plog ("Platesolve is requesting to move back on target!")
    #         #         self.pointing_correction_requested_by_platesolve_thread = True
    #         #         self.pointing_correction_request_time = time.time()
    #         #         self.pointing_correction_request_ra = target_ra
    #         #         self.pointing_correction_request_dec = target_dec

    #         # except:
    #         # If mount doesn't have Syncable coordinates

    #         if (
    #             abs(err_ha * 15 * 3600)
    #             > self.config["threshold_mount_update"]
    #             or abs(err_dec * 3600)
    #             > self.config["threshold_mount_update"]
    #         ):

    #             #plog ("I am nudging the telescope slightly!")
    #             #g_dev['mnt'].mount.SlewToCoordinatesAsync(pointing_ra + err_ha, pointing_dec + err_dec)
    #             # wait_for_slew()
    #             #plog("Platesolve is requesting to move back on target!")
    #             self.pointing_correction_requested_by_platesolve_thread = True
    #             self.pointing_correction_request_time = time.time()
    #             self.pointing_correction_request_ra = pointing_ra + err_ha
    #             self.pointing_correction_request_dec = pointing_dec + err_dec

    #             try:
    #                 # if g_dev["mnt"].pier_side_str == "Looking West":
    #                 if g_dev["mnt"].pier_side == 0:
    #                     try:
    #                         g_dev["mnt"].adjust_mount_reference(
    #                             -err_ha, -err_dec
    #                         )
    #                     except Exception as e:
    #                         plog("Something is up in the mount reference adjustment code ", e)
    #                 else:
    #                     try:
    #                         g_dev["mnt"].adjust_flip_reference(
    #                             -err_ha, -err_dec
    #                         )  # Need to verify signs
    #                     except Exception as e:
    #                         plog("Something is up in the mount reference adjustment code ", e)

    #             except:
    #                 plog("This mount doesn't report pierside")
    #                 plog(traceback.format_exc())
    #     self.platesolve_is_processing = False
    # except Exception as e:
    #     plog(
    #         "Image: did not platesolve; this is usually OK. ", e
    #     )
    #     plog(traceback.format_exc())

    try:
        os.remove(cal_path + 'platesolvetemp.fits')
    except:
        pass