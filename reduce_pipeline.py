# -*- coding: utf-8 -*-
"""
Created on Mon Jun 7 11:36:45 2021

@author: dhunt

This is a script to run the BANZAI and BANZAI-NRES pipelines with Photon Ranch
sites and instruments. BANZAI-NRES specifically processes echelle spectra. 
camera.py will pass the names of the files to be reduced on site. BANZAI will 
automatically create master calibrations and process science frames.

The BANZAI pipeline has the ability to schedule a specific time to create master calibration
frames.

"""

import win32com.client
import os
import numpy as np
from astropy.io import fits
import glob
import shelve
import sep
from global_yard import g_dev
import ptr_utility

from banzai.dbs import create_db
# Other banzai imports go here.

# DEH: Should this eventually be written as a class?

def site_setup():
    """
    Create local database in working directory for the banzai pipeline.
    Run when setting up at a new site.
    """
    create_db('.', db_address='sqlite:///banzai.db')
    # TODO Finish the setup to run BANZAI here.
        # Add instruments and sites to the banzai.db database before running the pipeline. 
        # banzai_add_instrument()
    
def make_bpm(input_dir, output_dir):
    """
    Run the LCO Bad Pixel Mask maker tool to generate BPM.
    """
    # DEH: The input_dir should be ~/archive/cameraname/latestdate
    os.system('lco_bpm_maker input_dir output_dir')
    