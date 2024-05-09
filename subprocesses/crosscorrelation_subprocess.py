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

payload=pickle.load(sys.stdin.buffer)

reference_image=payload[0]
substackimage=payload[1]
temporary_substack_directory=payload[2]
output_filename=payload[3]
is_osc=payload[4]

xoff, yoff = cross_correlation_shifts(block_reduce(reference_image,3), block_reduce(substackimage,3),zeromean=False)  
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
    
np.save(substackimage, temporary_substack_directory + output_filename )