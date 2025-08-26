# -*- coding: utf-8 -*-
"""
Created on Sat Jun 21 20:29:20 2025

@author: WER
"""
import os
import glob
import pathlib
import shutil
import time
from astropy.io import fits

# =============================================================================
# fits_image_filename = fits.util.get_testdata_filepath('test0.fits')
# hdul = fits.open(fits_image_filename)
# hdul.info()
# hdul[0].header['DATE']
# =============================================================================


eva = 'X://EVAreducedfiles//*'

def main_routine(first_run=False):
    
    big_list = glob.glob(eva)[:-3]
    
    big_list.reverse()
    #big_list = big_list[40:]
    print(big_list)

    moved = []
    count = 0
    for directory in big_list:
        # print("Globbing:  "+ directory)
        if count == 1: 
            break

        stack_list = glob.glob(directory + '//fits//SmStack-*.fits')
        print(stack_list)

        target = 'X://PTRnames//'+ directory.split('\\')[1]
        os.makedirs(target ,  exist_ok=True)
        for image_filename in stack_list:
            with fits.open(image_filename) as hdu1:
                
                hdr = hdu1[0].header
                origin_name = hdr['ORIGNAME'].split('_expose_')
                ptr_name = origin_name[0]+ '-' + hdr['OBJECT'] + '-' + origin_name[1]
            hdu1.close()
            
            
            shutil.copy(image_filename, target + "//" + ptr_name)
            print("Copied:  ", target + "//" + ptr_name)
            moved.append(image_filename)
        count += 1
    print ("DONE")
        
            
            
            
        




if __name__ == '__main__':
    print('bingo')
    main_routine(first_run=True)
