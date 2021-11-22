# -*- coding: utf-8 -*-
"""
Created on Wed Nov 10 00:51:14 2021

@author: obs
"""
import obs.py
import time
from glob import glob
from concurrent.futures import ProcessPoolExecutor
import sep
from astropy.io import fits
from planewave import platesolve

def solve (file_name):
    #Load the filename
    print("Entering")
    time. sleep(15)
    print("Leaving")
    #be happy.
    return "Solved:  " + file_name


file_name ='Dummy file name'
futures_list = []
with ProcessPoolExecutor(max_workers=2) as executor:
    futures = executor.submit(solve, file_name)
    futures_list.append(futures)
    print(futures_list)
    time.sleep(10)
    for future in futures_list:
        try:
            result = future.result(timeout=120)
            print(result)
        except:
            print("No result")
    
    

    
    