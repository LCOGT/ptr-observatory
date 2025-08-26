# -*- coding: utf-8 -*-
"""
Created on Wed Jul  2 19:03:33 2025

@author: WER
"""
import os
import glob
import pathlib
import shutil
import time
from astropy.io import fits
#from pprint import pprint as print

# =============================================================================
# fits_image_filename = fits.util.get_testdata_filepath('test0.fits')
# hdul = fits.open(fits_image_filename)
# hdul.info()
# hdul[0].header['DATE']
# =============================================================================

#no_names  ['lagoonnebula', 'm13', 'ngc6960', 'm3', 'm101', 'm61', 'explore', 'unknown', 'm64', 'm27', 'ngc3718', 'm51_simple', 'm51_3x', 'm81_aro2_2x', 'm51_aro2_3x', 'm51', 'm42_simple', 'm108', 'ic1805mosaic', 'bubble', 'm45', 'wasp-12b', 'kps-1b', 'm42', 'm31', 'jettn', 'm31mosaicii', 'm33', 'orionnebula', 'ngc869', 'm45stromgren']

eva = 'X:/PTRnames/*'
targets = 'X:/PTRtargets/' 

def main_routine(first_run=False):
    
    big_list = glob.glob(eva)   
    big_list.reverse()
    big_list = big_list
    print(big_list)
  
    moved = []
    no_name_list = []
    object_name_list = ['trifid', 'lagoon', 'ngc6960','m13', "m3", 'm101', 'm61', 'm42', 'm64', 'orion', 'horsehead', 'm31', 'm32', 'm33', 'flame', 'dumbbell', 'm27', 'm45', 'ic1805','ngc869', 'm108', 'm51', 'm81', 'ngc3718', 'bubble', 'unknown', 'explore']
    for index in range(len(object_name_list)):

        os.makedirs(targets + object_name_list[index] + "/", exist_ok=True)
    count = 0
    for day_dir in big_list:
        breakpoint()
        day_dir =day_dir.split('\\')       
        day_dir_list = glob.glob(day_dir[0]+ '/' + day_dir[1] + '/*.fits')
        for image_filename in day_dir_list:
            image_filename = image_filename.split("\\")
            image_filename = image_filename[0] + '/' + image_filename[1]
            with fits.open(image_filename) as hdu1:
                
                hdr = hdu1[0].header
                image_origin_name = hdr['ORIGNAME'].split('_expose_')
                ptr_name = image_origin_name[0]+ '-' + hdr['OBJECT'] + '-' + image_origin_name[1]
            hdu1.close()
            lower_obj = hdr['OBJECT'].lower()
            print(lower_obj)
            
            in_flag = False
            for index in range(len(object_name_list)):
                if object_name_list[index] in lower_obj:
                    print("Image is of:  ", object_name_list[index])
                    in_flag = True
                    try:
                        
                        shutil.move( image_filename, targets+object_name_list[index] + '/' + image_filename.split('/')[-1])
                        #os.symlink(ptr_name, targets + object_name_list[index])
                    except:
                        pass
                    if '-' in lower_obj:
                        lower_obj = lower_obj.split()[0]
                    break
            if in_flag is False:
                no_name_list.append(lower_obj)
                print("Appending:  ", lower_obj)
            
            
            
    breakpoint()
            
            
            
    print("Fini")
            
           
    
    
if __name__ == '__main__':
    main_routine(first_run=True)