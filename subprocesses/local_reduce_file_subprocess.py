
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
#import bottleneck as bn
#import sep
import traceback
#from astropy.table import Table
from astropy.io import fits
#from astropy.nddata import block_reduce
from astropy.utils.exceptions import AstropyUserWarning
import warnings
import datetime
warnings.simplefilter('ignore', category=AstropyUserWarning)

#input_sep_info=pickle.load(sys.stdin.buffer)
#input_sep_info=pickle.load(open('testfz17141141966139522','rb'))
input_sep_info=pickle.load(open(sys.argv[1],'rb'))

print ("HERE IS THE INCOMING. ")
#print (input_sep_info)
#breakpoint()


temphduheader=input_sep_info[0]
selfconfig=input_sep_info[1]
camname=input_sep_info[2]
slow_process=input_sep_info[3]

googtime=time.time()




    # altfolder = selfconfig['temporary_local_alt_archive_to_hold_files_while_copying']
    # if not os.path.exists(selfconfig['temporary_local_alt_archive_to_hold_files_while_copying']):
    #     os.makedirs(selfconfig['temporary_local_alt_archive_to_hold_files_while_copying'] )


hdureduced = fits.PrimaryHDU()
hdureduced.data = slow_process[2]
hdureduced.header = temphduheader
hdureduced.header["NAXIS1"] = hdureduced.data.shape[0]
hdureduced.header["NAXIS2"] = hdureduced.data.shape[1]
hdureduced.header["DATE"] = (
    datetime.date.strftime(
        datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
    ),
    "Date FITS file was written",
)
hdureduced.data = hdureduced.data.astype("float32")


int_array_flattened=hdureduced.data.astype(int).ravel()
int_array_flattened=int_array_flattened[int_array_flattened > -10000]
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
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
                                                        zeroValue=(imageMode-counter)
                                                        breaker =0

hdureduced.data[hdureduced.data < zeroValue] = np.nan


# Remove nans
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

hdureduced.writeto(
    slow_process[1], overwrite=True, output_verify='silentfix'
)  # Save flash reduced file locally


if selfconfig["save_to_alt_path"] == "yes":
    #breakpoint()
    
    
    # altfolder +'/' + g_dev["day"] + "/raw/" + raw_name00
    
    
    hdureduced.writeto( selfconfig['alt_path'] +'/' +temphduheader['OBSID'] +'/' +temphduheader['DAY-OBS'] + "/reduced/" + slow_process[1].split('/')[-1].replace('EX00','EX00-'+temphduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    )  # Save full raw file locally


try:
    os.remove(sys.argv[1])
except:
    pass

sys.exit()












































# # Create the fz file ready for PTR Archive
# # Note that even though the raw file is int16,
# # The compression and a few pieces of software require float32
# # BUT it actually compresses to the same size either way
# temphduheader["BZERO"] = 0  # Make sure there is no integer scaling left over
# temphduheader["BSCALE"] = 1  # Make sure there is no integer scaling left over
# if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:


#     pipefolder = selfconfig['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME'])
#     if not os.path.exists(selfconfig['temporary_local_pipe_archive_to_hold_files_while_copying']+'/'+ str(temphduheader['DAY-OBS'])):
#         os.makedirs(selfconfig['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']))

#     if not os.path.exists(selfconfig['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME'])):
#         os.makedirs(selfconfig['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(temphduheader['DAY-OBS']) +'/'+ str(temphduheader['INSTRUME']))



# if not selfconfig["camera"][camname]["settings"]["is_osc"]:


#     # This routine saves the file ready for uploading to AWS
#     # It usually works perfectly 99.9999% of the time except
#     # when there is an astropy cache error. It is likely that
#     # the cache will need to be cleared when it fails, but
#     # I am still waiting for it to fail again (rare)
#     saver = 0
#     saverretries = 0
#     while saver == 0 and saverretries < 10:
#         try:
#             if selfconfig['ingest_raws_directly_to_archive']:
#                 hdufz = fits.CompImageHDU(
#                     np.array(slow_process[2], dtype=np.float32), temphduheader
#                 )
#                 hdufz.writeto(
#                     slow_process[1], overwrite=True
#                 )  # Save full fz file locally
#                 try:
#                     hdufz.close()
#                 except:
#                     pass
#                 del hdufz  # remove file from memory now that we are doing with it

#             if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:

#                 hdu = fits.PrimaryHDU(np.array(slow_process[2], dtype=np.float32), temphduheader)


#                 #print ("gonna pipe folder")
#                 #print (pipefolder + '/' + str(temphduheader['ORIGNAME']))
#                 hdu.writeto(
#                     pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.fits'), overwrite=True
#                 )
#                 try:
#                     hdu.close()
#                 except:
#                     pass
#                 del hdu  # remove file from memory now that we are doing with it

#                 #(filename,dayobs,instrume) = fileinfo
#                 #self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME']).replace('.fits.fz','.fits')),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
#                 #hdufz.writeto(
#                 #    slow_process[1], overwrite=True
#                 #)  # Save full fz file locally
#             saver = 1
#         except Exception as e:
#             print("Failed to write raw fz file: ", e)
#             # if "requested" in e and "written" in e:
#             #     print(check_download_cache())
#             print(traceback.format_exc())
#             time.sleep(10)
#             saverretries = saverretries + 1


#     # # Send this file up to ptrarchive
#     # if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#     #     self.enqueue_for_PTRarchive(
#     #         26000000, '', slow_process[1]
#     #     )

# else:  # Is an OSC

#     if selfconfig["camera"][camname]["settings"]["osc_bayer"] == 'RGGB':

#         newhdured = slow_process[2][::2, ::2]
#         GTRonly = slow_process[2][::2, 1::2]
#         GBLonly = slow_process[2][1::2, ::2]
#         newhdublue = slow_process[2][1::2, 1::2]
#         clearV = (block_reduce(slow_process[2],2))

#         oscmatchcode = (datetime.datetime.now().strftime("%d%m%y%H%M%S"))

#         temphduheader["OSCMATCH"] = oscmatchcode
#         temphduheader['OSCSEP'] = 'yes'
#         temphduheader['NAXIS1'] = float(temphduheader['NAXIS1'])/2
#         temphduheader['NAXIS2'] = float(temphduheader['NAXIS2'])/2
#         temphduheader['CRPIX1'] = float(temphduheader['CRPIX1'])/2
#         temphduheader['CRPIX2'] = float(temphduheader['CRPIX2'])/2
#         try:
#             temphduheader['PIXSCALE'] = float(temphduheader['PIXSCALE'])*2
#         except:
#             pass
#         temphduheader['CDELT1'] = float(temphduheader['CDELT1'])*2
#         temphduheader['CDELT2'] = float(temphduheader['CDELT2'])*2
#         tempfilter = temphduheader['FILTER']
#         tempfilename = slow_process[1]



#         # Save and send R1
#         temphduheader['FILTER'] = tempfilter + '_R1'
#         temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('-EX', 'R1-EX')



#         if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#             hdufz = fits.CompImageHDU(
#                 np.array(newhdured, dtype=np.float32), temphduheader
#             )
#             hdufz.writeto(
#                 tempfilename.replace('-EX', 'R1-EX'), overwrite=True#, output_verify='silentfix'
#             )  # Save full fz file locally
#             # self.enqueue_for_PTRarchive(
#             #     26000000, '', tempfilename.replace('-EX', 'R1-EX')
#             # )

#         if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
#             hdu = fits.PrimaryHDU(np.array(newhdured, dtype=np.float32), temphduheader)
#             temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')
#             hdu.writeto(
#                 pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
#             )
#             # self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)

#         del newhdured

#         # Save and send G1
#         temphduheader['FILTER'] = tempfilter + '_G1'
#         temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('R1-EX', 'G1-EX')



#         if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#             hdufz = fits.CompImageHDU(
#                 np.array(GTRonly, dtype=np.float32), temphduheader
#             )
#             hdufz.writeto(
#                 tempfilename.replace('-EX', 'G1-EX'), overwrite=True#, output_verify='silentfix'
#             )  # Save full fz file locally
#             # self.enqueue_for_PTRarchive(
#             #     26000000, '', tempfilename.replace('-EX', 'G1-EX')
#             # )
#         if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
#             hdu = fits.PrimaryHDU(np.array(GTRonly, dtype=np.float32), temphduheader)
#             temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

#             hdu.writeto(
#                 pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
#             )
#             # self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
#         del GTRonly

#         # Save and send G2
#         temphduheader['FILTER'] = tempfilter + '_G2'
#         temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('G1-EX', 'G2-EX')




#         if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#             hdufz = fits.CompImageHDU(
#                 np.array(GBLonly, dtype=np.float32), temphduheader
#             )
#             hdufz.writeto(
#                 tempfilename.replace('-EX', 'G2-EX'), overwrite=True#, output_verify='silentfix'
#             )  # Save full fz file locally
#             # self.enqueue_for_PTRarchive(
#             #     26000000, '', tempfilename.replace('-EX', 'G2-EX')
#             # )
#         if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
#             hdu = fits.PrimaryHDU(np.array(GBLonly, dtype=np.float32), temphduheader)
#             temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

#             hdu.writeto(
#                 pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
#             )
#             # self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)

#         del GBLonly

#         # Save and send B1
#         temphduheader['FILTER'] = tempfilter + '_B1'
#         temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('G2-EX', 'B1-EX')




#         if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#             hdufz = fits.CompImageHDU(
#                 np.array(newhdublue, dtype=np.float32), temphduheader
#             )
#             hdufz.writeto(
#                 tempfilename.replace('-EX', 'B1-EX'), overwrite=True#, output_verify='silentfix'
#             )  # Save full fz file locally
#             # self.enqueue_for_PTRarchive(
#             #     26000000, '', tempfilename.replace('-EX', 'B1-EX')
#             # )
#         if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
#             hdu = fits.PrimaryHDU(np.array(newhdublue, dtype=np.float32), temphduheader)
#             temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

#             hdu.writeto(
#                 pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
#             )
#             # self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
#         del newhdublue

#         # Save and send clearV
#         temphduheader['FILTER'] = tempfilter + '_clearV'
#         temphduheader['ORIGNAME'] = temphduheader['ORIGNAME'].replace('B1-EX', 'CV-EX')

#         temphduheader['SATURATE']=float(temphduheader['SATURATE']) * 4
#         temphduheader['FULLWELL']=float(temphduheader['FULLWELL']) * 4
#         temphduheader['MAXLIN']=float(temphduheader['MAXLIN']) * 4





#         if selfconfig['send_files_at_end_of_night'] == 'no' and selfconfig['ingest_raws_directly_to_archive']:
#             hdufz = fits.CompImageHDU(
#                 np.array(clearV, dtype=np.float32), temphduheader
#             )
#             hdufz.writeto(
#                 tempfilename.replace('-EX', 'CV-EX'), overwrite=True#, output_verify='silentfix'
#             )
#             # self.enqueue_for_PTRarchive(
#             #     26000000, '', tempfilename.replace('-EX', 'CV-EX')
#             # )
#         if selfconfig['save_raws_to_pipe_folder_for_nightly_processing']:
#             hdu = fits.PrimaryHDU(np.array(clearV, dtype=np.float32), temphduheader)
#             temphduheader['ORIGNAME']=temphduheader['ORIGNAME'].replace('.fits.fz','.fits')

#             hdu.writeto(
#                 pipefolder + '/' + str(temphduheader['ORIGNAME']), overwrite=True
#             )
#             # self.pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(temphduheader['ORIGNAME'])),copy.deepcopy(temphduheader['DAY-OBS']),copy.deepcopy(temphduheader['INSTRUME'])), block=False)
#         del clearV


#     else:
#         print("this bayer grid not implemented yet")



# print ("TIME: " + str(time.time()-googtime))


# try:
#     os.remove(sys.argv[1])
# except:
#     pass

# sys.exit()

# # hdufocusdata=input_sep_info[0]
# # pixscale=input_sep_info[1]
# # image_saturation_level= input_sep_info[2]
# # nativebin= input_sep_info[3]
# # readnoise= input_sep_info[4]
# # minimum_realistic_seeing= input_sep_info[5]
# # im_path=input_sep_info[6]
# # text_name=input_sep_info[7]
# # channel=input_sep_info[8]


# # # Really need to thresh the incoming image
# # googtime=time.time()
# # int_array_flattened=hdufocusdata.astype(int).ravel()
# # unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
# # m=counts.argmax()
# # imageMode=unique[m]
# # print ("Calculating Mode: " +str(time.time()-googtime))

# # # Zerothreshing image
# # googtime=time.time()
# # histogramdata=np.column_stack([unique,counts]).astype(np.int32)
# # #Do some fiddle faddling to figure out the value that goes to zero less
# # zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
# # breaker=1
# # counter=0
# # while (breaker != 0):
# #     counter=counter+1
# #     if not (imageMode-counter) in zeroValueArray[:,0]:
# #         if not (imageMode-counter-1) in zeroValueArray[:,0]:
# #             if not (imageMode-counter-2) in zeroValueArray[:,0]:
# #                 if not (imageMode-counter-3) in zeroValueArray[:,0]:
# #                     if not (imageMode-counter-4) in zeroValueArray[:,0]:
# #                         if not (imageMode-counter-5) in zeroValueArray[:,0]:
# #                             if not (imageMode-counter-6) in zeroValueArray[:,0]:
# #                                 if not (imageMode-counter-7) in zeroValueArray[:,0]:
# #                                     if not (imageMode-counter-8) in zeroValueArray[:,0]:
# #                                         if not (imageMode-counter-9) in zeroValueArray[:,0]:
# #                                             if not (imageMode-counter-10) in zeroValueArray[:,0]:
# #                                                 if not (imageMode-counter-11) in zeroValueArray[:,0]:
# #                                                     if not (imageMode-counter-12) in zeroValueArray[:,0]:
# #                                                         zeroValue=(imageMode-counter)
# #                                                         breaker =0

# # hdufocusdata[hdufocusdata < zeroValue] = np.nan

# # print ("Zero Threshing Image: " +str(time.time()-googtime))





# # # Check there are no nans in the image upon receipt
# # # This is necessary as nans aren't interpolated in the main thread.
# # # Fast next-door-neighbour in-fill algorithm
# # num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
# # x_size=hdufocusdata.shape[0]
# # y_size=hdufocusdata.shape[1]
# # # this is actually faster than np.nanmean
# # #edgefillvalue=np.divide(bn.nansum(hdufocusdata),(x_size*y_size)-num_of_nans)
# # #breakpoint()
# # while num_of_nans > 0:
# #     # List the coordinates that are nan in the array
# #     nan_coords=np.argwhere(np.isnan(hdufocusdata))

# #     # For each coordinate try and find a non-nan-neighbour and steal its value
# #     for nancoord in nan_coords:
# #         x_nancoord=nancoord[0]
# #         y_nancoord=nancoord[1]
# #         done=False

# #         # Because edge pixels can tend to form in big clumps
# #         # Masking the array just with the mean at the edges
# #         # makes this MUCH faster to no visible effect for humans.
# #         # Also removes overscan
# #         if x_nancoord < 100:
# #             hdufocusdata[x_nancoord,y_nancoord]=imageMode
# #             done=True
# #         elif x_nancoord > (x_size-100):
# #             hdufocusdata[x_nancoord,y_nancoord]=imageMode

# #             done=True
# #         elif y_nancoord < 100:
# #             hdufocusdata[x_nancoord,y_nancoord]=imageMode

# #             done=True
# #         elif y_nancoord > (y_size-100):
# #             hdufocusdata[x_nancoord,y_nancoord]=imageMode
# #             done=True

# #         # left
# #         if not done:
# #             if x_nancoord != 0:
# #                 value_here=hdufocusdata[x_nancoord-1,y_nancoord]
# #                 if not np.isnan(value_here):
# #                     hdufocusdata[x_nancoord,y_nancoord]=value_here
# #                     done=True
# #         # right
# #         if not done:
# #             if x_nancoord != (x_size-1):
# #                 value_here=hdufocusdata[x_nancoord+1,y_nancoord]
# #                 if not np.isnan(value_here):
# #                     hdufocusdata[x_nancoord,y_nancoord]=value_here
# #                     done=True
# #         # below
# #         if not done:
# #             if y_nancoord != 0:
# #                 value_here=hdufocusdata[x_nancoord,y_nancoord-1]
# #                 if not np.isnan(value_here):
# #                     hdufocusdata[x_nancoord,y_nancoord]=value_here
# #                     done=True
# #         # above
# #         if not done:
# #             if y_nancoord != (y_size-1):
# #                 value_here=hdufocusdata[x_nancoord,y_nancoord+1]
# #                 if not np.isnan(value_here):
# #                     hdufocusdata[x_nancoord,y_nancoord]=value_here
# #                     done=True

# #     num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))






# # # https://stackoverflow.com/questions/9111711/get-coordinates-of-local-maxima-in-2d-array-above-certain-value
# # def localMax(a, include_diagonal=True, threshold=-np.inf) :
# #     # Pad array so we can handle edges
# #     ap = np.pad(a, ((1,1),(1,1)), constant_values=-np.inf )

# #     # Determines if each location is bigger than adjacent neighbors
# #     adjacentmax =(
# #     (ap[1:-1,1:-1] > threshold) &
# #     (ap[0:-2,1:-1] <= ap[1:-1,1:-1]) &
# #     (ap[2:,  1:-1] <= ap[1:-1,1:-1]) &
# #     (ap[1:-1,0:-2] <= ap[1:-1,1:-1]) &
# #     (ap[1:-1,2:  ] <= ap[1:-1,1:-1])
# #     )
# #     if not include_diagonal :
# #         return np.argwhere(adjacentmax)

# #     # Determines if each location is bigger than diagonal neighbors
# #     diagonalmax =(
# #     (ap[0:-2,0:-2] <= ap[1:-1,1:-1]) &
# #     (ap[2:  ,2:  ] <= ap[1:-1,1:-1]) &
# #     (ap[0:-2,2:  ] <= ap[1:-1,1:-1]) &
# #     (ap[2:  ,0:-2] <= ap[1:-1,1:-1])
# #     )

# #     return np.argwhere(adjacentmax & diagonalmax)



# # fx, fy = hdufocusdata.shape
# # #hdufocusdata[np.isnan(hdufocusdata)] = imageMode



# # #hdufocusdata=hdufocusdata-bn.nanmedian(hdufocusdata)
# # bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
# # bkg.subfrom(hdufocusdata)


# # tempstd=np.std(hdufocusdata)
# # threshold=3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)])
# # list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
# # # Assess each point
# # pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
# # counter=0
# # for point in list_of_local_maxima:
    
# #     pointvalues[counter][0]=point[0]
# #     pointvalues[counter][1]=point[1]
# #     pointvalues[counter][2]=np.nan
# #     in_range=False
# #     if (point[0] > fx*0.1) and (point[1] > fy*0.1) and (point[0] < fx*0.9) and (point[1] < fy*0.9):
# #         in_range=True
    
# #     if in_range:                
# #         value_at_point=hdufocusdata[point[0],point[1]]
# #         try:
# #             value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
# #         except:
# #             print(traceback.format_exc())
# #             breakpoint()
            
# #         # Check it isn't just a dot
# #         if value_at_neighbours < (0.6*value_at_point):
# #             #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
# #             pointvalues[counter][2]=np.nan                       
        
# #         # If not saturated and far away from the edge
# #         elif value_at_point < 0.8*image_saturation_level:
# #             pointvalues[counter][2]=value_at_point
        
# #         else:
# #             pointvalues[counter][2]=np.nan
            
# #     counter=counter+1
    


# # # Trim list to remove things that have too many other things close to them.

# # # remove nan rows
# # pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

# # # reverse sort by brightness
# # pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]


# # # Keep top 200
# # if len(pointvalues) > 200:
# #     pointvalues=pointvalues[:200,:]


# # print ("Constructor " + str(time.time()-googtime))
# # sources = Table()
# # sources['x']=pointvalues[:,1]
# # sources['y']=pointvalues[:,0]


# # sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)


# # pickle.dump(sources, open(im_path + 'oscaasep.pickle' + channel, 'wb'))


