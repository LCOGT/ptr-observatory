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
import bottlenck as bn
payload=pickle.load(sys.stdin.buffer)

reference_image=payload[0]
substackimage=payload[1]
temporary_substack_directory=payload[2]
output_filename=payload[3]
is_osc=payload[4]





# Really need to thresh the image
#googtime=time.time()
int_array_flattened=substackimage.astype(int).ravel()
int_array_flattened=int_array_flattened[int_array_flattened > -10000]
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
m=counts.argmax()
imageMode=unique[m]
#print ("Calculating Mode: " +str(time.time()-googtime))

#Zerothreshing image
#googtime=time.time()
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
                                                        
substackimage[substackimage < zeroValue] = np.nan

edge_crop=100
xoff, yoff = cross_correlation_shifts(block_reduce(reference_image[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=bn.nanmean), block_reduce(substackimage[edge_crop:-edge_crop,edge_crop:-edge_crop],3, func=bn.nanmean),zeromean=False)  
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