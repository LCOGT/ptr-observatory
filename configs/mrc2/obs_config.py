# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20220604 WER

@author: wrosing
'''
#                                                                                        1         1         1       1
#        1         2         3         4         6         7         8         9         0         1         2       2
#234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
#import json
#import time

#  NB NB  Json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.
#  NB NB  My convention is if a value is naturally a float I add a decimal point even to 0.
#g_dev = None

'''
COM1
COM2
COM3
COM4
COM5   Intel

COM14  Arduino SkyRoof         USB-2 *

?????  USB3 Camera Blue Cable  USB-3
COM24  Planewave Mount Axis 2  USB-1 Shared *
COM25  Planewave Mount Axis 1  USB-1 Shared *

COM26  Ultimate Backplate      USB-6*

   COM  PW Mirror Cover
   COM29  PW Dew Heater*
   COM28  Optec Gemini*
   COM30  PW EFA*

COM27  Ultimate Instrument     USB-4*

   COM31  Optec Perseus*
   Not COM    Apogee Wheel Front*
   Not COM   Apogee Wheel Back*
   COM

COM07 or 06  Numato Hand Paddle      USB-5 *
COM10  Alnitak *

Paddle is a HID, not a COM or USB port. *

Park 207.3, 5.285.
'''

obs_id = 'mrc2'

site_config = {
    
    # Instance type specifies whether this is an obs or a wema
    'instance_type' : 'obs',
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name' : 'mrc',
    # The unique identifier for this obs
    'obs_id': 'mrc2',
    
    
    # Name, local and owner stuff
    'name': 'Mountain Ranch Camp Observatory  0m61 f6.8',
    'location': 'Santa Barbara, California,  USA',
    'airport_code': 'SBA',
    'telescope_description':  '0m61 f6.8 Planewave CDK',
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'mpc_code':  'ZZ23',    #This is made up for now.
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #  i.e, a multi-line text block supplied and formatted by the owner.
     'owner':  ['google-oauth2|112401903840371673242'],  # Wayne
     'owner_alias': ['WER', 'TELOPS'],
     'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],
     
   
    # Default safety settings
    'safety_check_period': 45,  # MF's original setting.
    'closest_distance_to_the_sun': 45,  # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_moon': 3,  # Degrees. For normal pointing requests don't go this close to the moon.
    'minimum_distance_from_the_moon_when_taking_flats': 10,
    'lowest_requestable_altitude': 15,  # Degrees. For normal pointing requests don't allow requests to go this low.
    'degrees_to_avoid_zenith_area_for_calibrations': 5, 
    'degrees_to_avoid_zenith_area_in_general' : 0,
    'maximum_hour_angle_requestable' : 12,
    'temperature_at_which_obs_too_hot_for_camera_cooling' : 28,   #10C higher than chiller water

    # These are the default values that will be set for the obs
    # on a reboot of obs.py. They are safety checks that 
    # can be toggled by an admin in the Observe tab.
    'scope_in_manual_mode': False,
    'mount_reference_model_off': True,
    'sun_checks_on': True,
    'moon_checks_on': True,
    'altitude_checks_on': True,    
    'daytime_exposure_time_safety_on': True,
    
    
    
    # Setup of folders on local and network drives.
    'ingest_raws_directly_to_archive': True,
    # LINKS TO PIPE FOLDER
    'save_raws_to_pipe_folder_for_nightly_processing': False,
    'pipe_archive_folder_path': 'X:/localptrarchive/',  #WER changed Z to X 20231113 @1:16 UTC
    'temporary_local_pipe_archive_to_hold_files_while_copying' : 'F:/tempfolderforpipeline',
    'temporary_local_alt_archive_to_hold_files_while_copying' : 'F:/tempfolderforaltpath',

    # Setup of folders on local and network drives.
    'client_hostname':  'mr2-0m60',
    'archive_path':  'C:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'save_to_alt_path':  'yes',
    'local_calibration_path': 'C:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'archive_age' : 7, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'send_files_at_end_of_night' : 'no', # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    
    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus file can not be saved.   
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : False,   
   # Number of files to send up to the ptrarchive simultaneously.
   'number_of_simultaneous_ptrarchive_streams' : 4,
   # Number of files to send over to the pipearchive simultaneously.
   'number_of_simultaneous_pipearchive_streams' : 4,
   # Number of files to send over to the altarchive simultaneously.
   'number_of_simultaneous_altarchive_streams' : 4,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.0,
     

    
    # TIMING FOR CALENDAR EVENTS
    
    # How many minutes with respect to eve sunset start flats
    
    'bias_dark interval':  105.,   #minutes
    'eve_sky_flat_sunset_offset': -45.,  # 40 before Minutes  neg means before, + after.
    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 5 , 
    'clock_and_auto_focus_offset': 8,
    
    'astro_dark_buffer': 30,   #Min before and after AD to extend observing window
    'morn_flat_start_offset': -10,       #min from Sunrise
    'morn_flat_end_offset':  +45,        #min from Sunrise
    'end_night_processing_time':  90,   #  A guess
    'observing_begins_offset': 18,    
    # How many minutes before civilDawn to do ....
    'observing_ends_offset': 18,   
    
    
    # Exposure times for standard system exposures
    'focus_exposure_time': 15,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 20,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 1,    # How many minutes between weather checks
    'enclosure_check_period': 1,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': True,
    
     'time_to_wait_after_roof_opens_to_take_flats': 120,   #Just imposing a minimum in case of a restart.
    'auto_midnight_moonless_bias_dark': True,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': True,
    
    # FOCUS OPTIONS
    'periodic_focus_time': 3, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.75,  # What FWHM increase is needed to trigger an autofocus
    
    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 45,  # only update mount when X arcseconds away
    

    'defaults': {
        'mount': 'mount1',
        #'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector':  'selector1',
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
        'mount',
        #'telescope',
        #'screen',
        'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',
        'sequencer',
        ],
     'short_status_devices':  [
        'mount',
        #'telescope',
        # 'screen',
        'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',
        'sequencer',
        ],  



    'mount': {
        'mount1': {      #NB NB There can only be one mounting given the new model.
            'parent': 'enclosure1',
            'tel_id': '0m35',
            'name': 'westpier',
            'hostIP':  '10.15.0.40',     #Can be a name if local DNS recognizes it.
            'hostname':  'westpier',
            'desc':  'Planewave L600 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',  #This picks up signals to the rotator from the mount.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'alignment': 'Alt-Az',
            'default_zenith_avoid': 5.0,   #degrees floating
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            #'has_ascom_altaz': False,
            'pointing_tel': 'tel1',  
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0, 
            'east_flip_ra_correction': 0.0,
            'east_flip_dec_correction': 0.0,
            'home_after_unpark' : True,
            'home_before_park' : True,
            
            'settle_time_after_unpark' : 0,
            'settle_time_after_park' : 0,
            'permissive_mount_reset' : 'yes', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            #'home_after_unpark' : False,
            'home_altitude':  0.0,
            'home_azimuth':  210.0,
            'has_paddle': False,    #or a string that permits proper configuration.
            'has_ascom_altaz': True,
            'pointing_tel': 'tel1',     #This can be changed to 'tel2' by user.  This establishes a default.
            'Selector':{
                'available': False,         #If True add these lines;
                # 'positions': 4,
                # 'inst 1': 'camera_1_1',      #inst_1 is always the default until status reports different
                # 'inst 2': 'echelle1',     #These are all types od cameras.
                # 'inst 3': 'camera3',
                # 'inst 4': 'lowres1',
                },

            'settings': {
 			    'latitude_offset': 0.025,     #Meters North is Positive   These *could* be slightly different than site.
 			    'longitude_offset': 0.25,   #meters West is negative  #NB This could be an eval( <<site config data>>))
 			    'elevation_offset': 0.5,    # meters above sea level
                'fixed_screen _altitude': 0.54,
                'horizon':  15.,    #  Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {
                      '0': 32,
                      '30': 35,
                      '36.5': 39,
                      '43': 28.6,
                      '59': 32.7,
                      '62': 28.6,
                      '65': 25.2,
                      '74': 22.6,
                      '82': 20,
                      '95.5': 20,
                      '101.5': 14,
                      '107.5': 12,
                      '130': 12,
                      '150': 20,
                      '172': 28,
                      '191': 25,
                      '213': 20,
                      '235': 15.3,
                      '260': 11,
                      '272': 17,
                      '294': 16.5,
                      '298.5': 18.6,
                      '303': 20.6,
                      '309': 27,
                      '315': 32,
                      '360': 32,  #  We use a dict because of fragmented azimuth mesurements.
                      },
                'refraction_on': True,
                'model_on': True,
                'rates_on': True,
                'model': {
                    'IH': 0,
                    'ID': 0.,
                    'WH': 0.,
                    'WD': 0.,
                    'MA': 0.,
                    'ME': 0.,
                    'CH': 0.,
                    'NP': 0.,
                    'TF': 0.,
                    'TX': 0.,
                    'HCES': 0.,
                    'HCEC': 0.,
                    'DCES': 0.,
                    'DCEC': 0.,
                    'IA': 0.0,
                    'IE': 0.0,
                    'CA': 0.0,
                    'NPAE': 0.0,
                    'AN': 0.0,
                    'AE': 0.0,     #AW?
                    'ACES': 0.0,
                    'ACEC': 0.0,
                    'ECES': 0.0,
                    'ECEC': 0.0,
                    }
            },
        },

    },


    'telescope': {                 #Better called OTA or "Optics
        'telescope1': {
            'parent': 'mount2',
            'name': 'Main OTA',
            'desc':  'Planewave CDK 600 F6.8',   #i seem to use desc, an alias more or less for the same thing.
            'telescop': 'mrc2',
            'ptrtel': 'mrc2',
            'driver': None,                     #Essentially this device is informational.  It is mostly about the optics.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'collecting_area':  154891,
            'obscuration':  47,
            'aperture': 610,
            'f-ratio':  6.8,   #This and focal_length can be refined after a solve.
            'focal_length': 3962,
            'has_dew_heater':  True,
            #'screen_name': 'screen2',   #The enclosure has two screens in the WMD case, one for each mount.
            # NB NB All the below need some checking
            'tel_has_unihedron': False,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   #This is a default for a single instrument system
            'selector_positions': 1,            #Note starts with 1
            'instrument names':  ['camera_1_1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                 "position1": ["darkslide1", "filter_wheel1", "filter_wheel2", "camera1"]
                 },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'filter_wheel1',

            'has_fans':  True,
            'has_cover':  True,
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': 0.0,    #If the mount model is current, these numbers are usually near 0.0
                                                #for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  #  new terms.
                'west_flip_ca_offset': 0.0,
                'west_flip_dec_offset': 0.0
                },

        },
        #'ota2':{    #NB NB second OTA here   >>>>
            
        #}
        

    },

    'rotator': {
        'rotator1': {
            'parent': 'telescope1',
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.AltAzDS.Rotator',
			'com_port':  'COM9',
            'startup_script':  'None',
            'recover_script':  'None',
            'shutdown_script':  'None',
            'minimum': -180.,
            'maximum': 360.0,
            'step_size':  0.0001,     #Is this correct?
            'backlash':  0.0,
            'unit':  'degree'    #  'steps'
        },
    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'Optec Alnitak 30"',
            'driver': 'COM6',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'minimum': 5.0,   #This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 170,  #Out of 0.0 - 255, this is the last value where the screen is linear with output.
                                #These values have a minor temperature sensitivity yet to quantify.
            },

    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
            'com_port': None,
            'start_at_config_reference': False,
            'correct_focus_for_temperature' : True,
            'maximum_good_focus_in_arcsecond': 2.5, # highest value to consider as being in "good focus". Used to select last good focus value

            'reference':  5870,    #Nominal at 20C Primary temperature, in microns not steps.            
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20221002',   # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            'use_local_temp':  False,
            'minimum': 0,    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'throw': 400,
            'step_size': 1,
            'backlash':  0,
            'unit': 'steps',
            'unit_conversion':  9.090909090909091,
            'has_dial_indicator': False
            },

    },

    'selector': {
        'selector1': {
            'parent': 'telescope1',
            'name': 'Selector',
            'desc':  'Optec Perseus',
            'driver': 'ASCOM.PerseusServer.Switch',
            'com_port': 'COM31',
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 4,
            'default': 0,
            'instruments':  ['Main_camera', 'eShell_spect', 'Planet_camera', 'UVEX_spect'],
            'cameras':      ['camera_1_1',  'camera_1_2',    None,           'camera_1_4'],
            'guiders':      [None,          'ag_1_2',        None,           'ag_1_4'],
            },
    },



    'lamp_box': {
        'lamp_box1': {
            'parent': 'camera_1',  # Parent is camera for the spectrograph
            'name': 'None',  # "UVEX Calibration Unit", 'None'
            'desc': 'None', #'eshel',  # "uvex", 'None'
            'spectrograph': 'None', #'echelle', 'uvex'; 'None'
            'driver': 'None', # ASCOM.Spox.Switch; 'None'; Note change to correct COM port used for the eShel calibration unit at mrc2
            'switches': "None"  # A string of switches/lamps the box has for the FITS header. # 'None'; "Off,Mirr,Tung,NeAr" for UVEX
        },
    },



    #Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    #FW's may need selector-like treatment
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "tel1",
            "alias": "Dual filter wheel",
            'service_date': '20180101',
            'driver': 'Maxim.CCDcamera', 
            'dual_wheel':  True,
            'override_automatic_filter_throughputs': False, # This ignores the automatically estimated filter gains and starts with the values from the config file
             
            "filter_settle_time": 8, #how long to wait for the filter to settle after a filter change(seconds)

            'ip_string': 'http://127.0.0.1',
            "desc":  'Dual Apogee custom Dual 50mm sq.',
            #"driver": ['ASCOM.Apogee.FilterWheel', 'ASCOM.Apogee2.FilterWheel'],
            #'driver': 'Maxim.CCDcamera',  #'startup_script':  None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            

            'settings': {
               
                'default_filter':  'w',
                
                'auto_color_options' : ['manual','RGB','NB','RGBHA','RGBNB'], # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
                'mono_RGB_colour_filters' : ['jb','jv','r'], # B, G, R filter codes for this camera if it is a monochrome camera with filters
                'mono_RGB_relative_weights' : [1.2,1,0.8],
                'mono_Narrowband_colour_filters' : ['ha','o3','s2'], # ha, o3, s2 filter codes for this camera if it is a monochrome camera with filters
                'mono_Narrowband_relative_weights' : [1.0,2,2.5],
                
                
                'filter_data': [
                                ['air',     [0, 0], -1000, 582,    [2, 17], 'ai'],   # 0
                                ['Lum',     [0, 1],     0, 544,   [2, 17], 'w '],   # 20
                                #['Red',     [4, 0],     0, 15,   [2, 17], 'r '],  # 21                                ['JV (Grn)',      [0, 3],     0, 1 [2, 17], 'V '],   # 9
                                #['Green',   [3, 0],     0, 21,   [2, 17], 'V '],   # 22
                                #['Blue',    [1, 0],     0, 18,   [2, 17], 'B '],   # 23
                                ['w',       [0, 1],     0, 544,  [2, 17], 'w '],   # 1
                                #['dif',    [0, 2],     0, 34,    [2, 17], 'df'],   # 2
                                ['O3',      [0, 3],     0, 7.75,    [2, 17], 'O3'],   # 3
                                ['HA',      [0, 4],     0, 2.76,    [2, 17], 'HA'],   # 4
                                ['N2',      [0, 5],     0, 3.39,     [2, 17], 'S2'],   # 5
                                ['S2',      [0, 6],     0, 3.51,    [2, 17], 'N2'],   # 6
                                ['JB',      [1, 0],     0, 104,    [2, 17], 'B '],   # 7
                                ['gp',      [2, 0],     0, 271,    [2, 17], 'g '],   # 8
                                ['JV',      [3, 0],     0, 178,   [2, 17], 'V '],   # 9
                                ['rp',      [4, 0],     0, 152,   [2, 17], 'r '],  # 10
                                ['ip',      [5, 0],     0, 59.5,   [2, 17], 'i '],  # 11
                                ['EXO',     [6, 0],     0, 392,  [2, 17], 'EX'],  # 12
                                ['dark',    [1, 6],     0, 0.0,   [2, 17], 'dk']], # 19
                
                
                'focus_filter' : 'Lum',

                
                
                'filter_screen_sort':  ['0', '1', '2', '10', '7', '6', '18', '12', '11', '13', '8',  '3', \
                                        '14', '15', '4', '16'],   #  '9', '21'],  # '5', '17'], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.
                #'filter_sky_sort':     ['S2', 'HA', 'N2', 'O3', 'ip', 'rp', 'Red', 'JV',\
                #                        'Green','JB', 'gp',   'Blue', 'EXO',  'w','Lum',  'air']  #Least to most throughput
                'filter_sky_sort':     ['S2', 'HA', 'N2', 'O3', 'ip', 'rp', 'JV',\
                                        'JB', 'gp', 'EXO', 'Lum', 'w', 'air'],
                 #Least to most throughput

            },
        },
    },

    # A site may have many cameras registered (camera_1_1, camera_1_2, _2_3, ...) each with unique aliases -- which are assumed
    # to be the name an owner has assigned and in principle that name "kb01" is labeled and found on the camera.  Between sites,
    # there can be overlap of camera names.  LCO convention is letter of cam manuf, letter of chip manuf, then 00, 01, 02, ...
    # However this code will treat the camera name/alias as a string of arbitrary length:  "saf_Neyle's favorite_camera" is
    # perfectly valid as an alias.

    #Ultimately every camera needs a specific configuration file, and associated with each camera or guider there may be a
    #darslide, filter wheel, and aux_focus.
    #We preseve the idea camera_1 refers to the first camera on the first ota so camera_2 is first camera on OTA 2

#







    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'sq005ms',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro Monochrome',
            'service_date': '20230301',
            #'driver':  'ASCOM.QHYCCD.Camera',   #  Maxim.CCDCamera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            
           

            
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'Q:/000ptr_saf/archive/kf01/autosaves/',
            'settings': {
                
                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                                

                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.

                # Simple Camera Properties
                'is_cmos':  True,
                'is_osc': False,
                'is_color': False,  # NB we also have a is_osc key.
                'osc_bayer': 'RGGB',


                # For direct QHY usage we need to set the appropriate gain.
                # This changes from site to site. "Fast" scopes like the RASA need lower gain then "slow".
                # Sky quality is also important, the worse the sky quality, the higher tha gain needs to be
                # Default for QHY600 is GAIN: 26, OFFSET: 60, readout mode 3. 
                # Random tips from the internet:
                # After the exposure, the background in the image should not be above 10% saturation of 16Bit while the brightest bits of the image should not be overexposed
                # The offset should be set so that there is at least 300ADU for the background
                # I guess try this out on the standard smartstack exposure time.        
                # https://www.baader-planetarium.com/en/blog/gain-and-offset-darks-flats-and-bias-at-cooled-cmos-cameras/
                #
                # Also the "Readout Mode" is really important also
                # Readout Mode #0 (Photographic DSO Mode)
                # Readout Mode #1 (High Gain Mode)
                # Readout Mode #2 (Extended Fullwell Mode)
                # Readout Mode #3 (Extended Fullwell Mode-2CMS)
                #
                # With the powers invested in me, I have decided that readout mode 3 is the best. We can only pick one standard one
                # and 0 is also debatably better for colour images, but 3 is way better for dynamic range....
                # We can't swip and swap because the biases and darks and flats will change, so we are sticking with 3 until
                # something bad happens with 3 for some reason
                #
                # In that sense, QHY600 NEEDS to be set at GAIN 26 and the only thing to adjust is the offset.....
                # USB Speed is a tradeoff between speed and banding, min 0, max 60. 60 is least banding. Most of the 
                # readout seems to be dominated by the slow driver (difference is a small fraction of a second), so I've left it at 60 - least banding.
                'direct_qhy_readout_mode' : 3,        
                'direct_qhy_gain' : 26,
                'direct_qhy_offset' : 60,
                
                'direct_qhy_usb_traffic' : 50,
                
                'set_qhy_usb_speed': False,
                'direct_qhy_usb_speed' : 0,
                
                
                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                'interpolate_for_focus': False,
                # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'bin_for_focus': False,
                'focus_bin_value' : 1,
                'interpolate_for_sep': False,
                'bin_for_sep': False,  # This setting will bin the image for SEP photometry rather than interpolating.
                'sep_bin_value' : 1,
                # This setting will bin the image for platesolving rather than interpolating.
                'bin_for_platesolve': True,
                'platesolve_bin_value' : 2,
                
                
                # Colour image tweaks.
                'osc_brightness_enhance': 1.0,
                'osc_contrast_enhance': 1.2,
                'osc_saturation_enhance': 1.5,
                'osc_colour_enhance': 1.2,
                'osc_sharpness_enhance': 1.2,
                'osc_background_cut': 15.0,
                
                # ONLY TRANSFORM THE FITS IF YOU HAVE
                # A DATA-BASED REASON TO DO SO.....
                # USUALLY TO GET A BAYER GRID ORIENTATED CORRECTLY
                # ***** ONLY ONE OF THESE SHOULD BE ON! *********
                'transpose_fits': False,
                'flipx_fits': False,
                'flipy_fits': False,
                'rotate180_fits': False,  # This also should be flipxy!
                'rotate90_fits': False,
                'rotate270_fits': False,
                'squash_on_x_axis': False,
                
                
                # What number of pixels to crop around the edges of a REDUCED image
                # This is primarily to get rid of overscan areas and also all images
                # Do tend to be a bit dodgy around the edges, so perhaps a standard
                # value of 30 is good. Increase this if your camera has particularly bad
                # edges.
                'reduced_image_edge_crop': 50,

                # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
                # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
                # RECOMMENDED DEFAULT DESIRE OF PTR
                'transpose_jpeg': False,
                'flipx_jpeg': False,
                'flipy_jpeg': False,
                'rotate180_jpeg': False,
                'rotate90_jpeg': False,
                'rotate270_jpeg': False,

                # This is purely to crop the preview jpeg for the UI                
                'crop_preview': True,
                'crop_preview_ybottom': 20,  # 2 needed if Bayer array
                'crop_preview_ytop': 20,
                'crop_preview_xleft': 20,
                'crop_preview_xright': 20,
                

                
               # For large fields of view, crop the images down to solve faster.
               # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
               # Probably also similar for platesolving.
               # for either pointing or platesolving even on more modest size fields of view.
               # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
               # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless
               # you clearly need to.
               'focus_image_crop_width': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full width
               'focus_image_crop_height': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full height                
               'focus_jpeg_size': 1500, # How many pixels square to crop the focus image for the UI Jpeg

               # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE
               'platesolve_image_crop': 0.0,  # Platesolve crops have to be symmetrical
               
               # Really, the SEP image should not be cropped unless your field of view and number of sources
               # Are taking chunks out of the processing time.
               # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
               'sep_image_crop_width': 0.0,
               # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
               'sep_image_crop_height': 0.0,


                # This is the area for cooling related settings
                'cooler_on': True,
                'temp_setpoint': -3,  # Verify we can go colder
                'has_chiller': True,                
                'chiller_com_port': 'COM1',
                'chiller_ref_temp':  15.0,  # C
                'day_warm': False,
                'day_warm_degrees': 8,  # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : False,

                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.
                'onebyone_pix_scale': 0.198,    #  This is the 1x1 binning pixelscale
                'native_bin': 2, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                'x_pixel':  3.76, # pixel size in microns
                'y_pixel':  3.76, # pixel size in microns
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.                
                'drizzle_value_for_later_stacking': 0.5,

                # This is the absolute minimum and maximum exposure for the camera
                'min_exposure': 0.0001,
                'max_exposure': 600.,
                # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'min_flat_exposure': 0.0001,                
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 0.5,

                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain' : True,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.
                'camera_gain':   2.48, #[10., 10., 10., 10.],     #  One val for each binning.
                'camera_gain_stdev':   0.04, #[10., 10., 10., 10.],     #  One val for each binning.
                'read_noise':  10.615, #[9, 9, 9, 9],    #  All SWAGs right now
                'read_noise_stdev':   0.012, #[10., 10., 10., 10.],     #  One val for each binning.              
                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 80000,  # NB Guess
                'saturate':   65535,
                'max_linearity':  60000,   # Guess
                # How long does it take to readout an image after exposure
                'cycle_time':            0.5,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 30,
                

                # As simple as it states, how many calibration frames to collect and how many to store.                
                'number_of_bias_to_collect': 33,
                'number_of_dark_to_collect': 17,
                'number_of_flat_to_collect': 11,
                'number_of_bias_to_store': 63,
                'number_of_dark_to_store': 33,
                'number_of_flat_to_store': 31,
                # Default dark exposure time.
                'dark_exposure': 180,
               
                
                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  False,
                'darkslide_com':  'COM15',
                'shutter_type': "Electronic",
               
                # 'has_screen': True,
                # 'screen_settings':  {
                #     'screen_saturation':  157.0,
                #     'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                #     'screen_x3':  3E-08,
                #     'screen_x2':  -9E-05,
                #     'screen_x1':  .1258,
                #     'screen_x0':  8.683,
                #     },
                },

            },
        },


        # 'camera_2': {
        #     'parent': 'telescope1',
        #     'name': 'sq02',      #Important because this points to a server file structure by that name.
        #     'desc':  'QHY 268M',
        #     'driver':  'ASCOM.QHYCCD.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
        #     'startup_script':  None,
        #     'recover_script':  None,
        #     'shutdown_script':  None,
        #     'detector':  'Sony IMX571',
        #     'manufacturer':  'QHY -- http://QHYCCD.COM',
        #     'use_file_mode':  False,
        #     'file_mode_path':  'D:/000ptr_saf/archive/sq02/autosaves/',
        #     'settings': {    #NB Need to add specification for chiller and its control
        #         'temp_setpoint': -10,
        #         'cooler_on': True,
        #         'darkslide_com': None,
        #         'north_offset': 0.0,
        #         'east_offset': 0.0,
        #         'rotation': 0.0,
        #         'min_exposure': 0.00003,  #Need to check this setting out
        #         'max_exposure': 3600.0,
        #         'can_subframe':  True,
        #         'min_subframe':  '16:16',
        #         'is_cmos':  False,
        #         'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
        #         'can_set_gain':  False,
        #         'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
        #         'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
        #         'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
        #         'saturate':  55000,
        #         'max_linearity':  55000.,
        #         'fullwell_capacity': 85000,
        #         'read_mode':  'Normal',
        #         'readout_mode': 'Normal',
        #         'readout_speed':  0.4,
        #         'square_detector': True,
        #         'areas_implemented': [ "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
        #         'default_area':  "Full",
        #         'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],     #Meaning no binning if list has only one entry
        #         'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
        #         'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
        #         'has_darkslide':  False,
        #         'has_screen': True,
        #         'screen_settings':  {
        #             'screen_saturation':  157.0,
        #             'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
        #             'screen_x3':  3E-08,
        #             'screen_x2':  -9E-05,
        #             'screen_x1':  .1258,
        #             'screen_x0':  8.683
        #         },
        #     },
        # },




        # 'ag_1_2': {
        #     'parent': 'telescope1',
        #     'name': 'ag02',      #Important because this points to a server file structure by that name.
        #     'desc':  'QHY Uncooled Guider',
        #     'driver':  'ASCOM.QHYCCD_GUIDER.Camera',   #'OM.FLI.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
        #     'startup_script':  None,
        #     'recover_script':  None,
        #     'shutdown_script':  None,
        #     'detector':  'Sony',
        #     'manufacturer':  'QHY -- Finger Lakes Instrumentation',
        #     'use_file_mode':  False,
        #     'file_mode_path':  'D:/000ptr_saf/archive/ag02/autosaves/',
        #     'settings': {
        #         'temp_setpoint': 10,
        #         'cooler_on': False,
        #         'x_start':  0,
        #         'y_start':  0,
        #         'x_width':  4096,
        #         'y_width':  4096,
        #         'x_chip':   4096,
        #         'y_chip':   4096,
        #         'x_pixel':  9,
        #         'y_pixel':  9,
        #         'overscan_x': 0,
        #         'overscan_y': 0,
        #         'north_offset': 0.0,
        #         'east_offset': 0.0,
        #         'rotation': 0.0,
        #         'min_exposure': 0.001,  #Need to check this setting out
        #         'max_exposure': 360.0,
        #         'can_subframe':  True,
        #         'min_subframe':  '16:16',
        #         'is_cmos':  True,
        #         'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
        #         'can_set_gain':  False,
        #         'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
        #         'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
        #         'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
        #         'saturate':  55000,
        #         'max_linearity':  55000.,
        #         'fullwell_capacity': 85000,
        #         'read_mode':  'Normal',
        #         'readout_mode': 'Normal',
        #         'readout_speed':  0.4,
        #         'square_detector': False,
        #         'areas_implemented': ["Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
        #         'default_area':  "Full",
        #         'bin_modes':  [[1, 1], [2, 2]],     #Meaning no binning if list has only one entry
        #         'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
        #         'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
        #         'has_darkslide':  False,
        #         'has_screen': True,
        #         'screen_settings':  {
        #             'screen_saturation':  157.0,
        #             'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
        #             'screen_x3':  3E-08,
        #             'screen_x2':  -9E-05,
        #             'screen_x1':  .1258,
        #             'screen_x0':  8.683
        #         },
        #     },
        # },

        # 'ag_1_4': {
        #     'parent': 'telescope1',
        #     'name': 'ag04',      #Important because this points to a server file structure by that name.
        #     'desc':  'QHY 174M',
        #     'driver':  'ASCOM.QHYCCD_CAM2.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
        #     'startup_script':  None,
        #     'recover_script':  None,
        #     'shutdown_script':  None,
        #     'detector':  'Sony',
        #     'manufacturer':  'QHY --  ',
        #     'use_file_mode':  False,
        #     'file_mode_path':  'D:/000ptr_saf/archive/ag04/autosaves/',
        #     'settings': {
        #         'temp_setpoint': -15,
        #         'cooler_on': True,
        #         'x_start':  0,
        #         'y_start':  0,
        #         'x_width':  4096,
        #         'y_width':  4096,
        #         'x_chip':   4096,
        #         'y_chip':   4096,
        #         'x_pixel':  9,
        #         'y_pixel':  9,
        #         'overscan_x': 0,
        #         'overscan_y': 0,
        #         'north_offset': 0.0,
        #         'east_offset': 0.0,
        #         'rotation': 0.0,
        #         'min_exposure': 0.25,  #Need to check this setting out
        #         'max_exposure': 360.0,
        #         'can_subframe':  True,
        #         'min_subframe':  '16:16',
        #         'is_cmos':  True,
        #         'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
        #         'can_set_gain':  True,
        #         'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
        #         'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
        #         'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
        #         'saturate':  55000,
        #         'max_linearity':  55000.,
        #         'fullwell_capacity': 85000,
        #         'read_mode':  'Normal',
        #         'readout_mode': 'Normal',
        #         'readout_speed':  0.4,
        #         'square_detector': False,
        #         'areas_implemented': [ "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
        #         'default_area':  "Full",
        #         'bin_modes':  [[1, 1], [2, 2]],     #Meaning no binning if list has only one entry
        #         'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
        #         'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
        #         'has_darkslide':  False,
        #         'has_screen': True,
        #         'screen_settings':  {
        #             'screen_saturation':  157.0,
        #             'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
        #             'screen_x3':  3E-08,
        #             'screen_x2':  -9E-05,
        #             'screen_x1':  .1258,
        #             'screen_x0':  8.683
        #         },
        #     },
        # },


    'sequencer': {
        'sequencer1': {
            'parent': 'site',
            'name': 'Sequencer',
            'desc':  'Automation Control',
            'driver': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,

            },
        },

    #  I am not sure AWS needs this, but my configuration code might make use of it.

    'server': {
        'server1': {
            'name': 'QNAP',
            'win_url': 'archive (\\10.15.0.82) (Q:)',
            'redis':  '(host=10.15.0.15, port=6379, db=0, decode_responses=True)',
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
        },
    },
}

# if __name__ == '__main__':
#     '''
#     This is a simple test to send and receive via json.
#     '''

#     j_dump = json.dumps(site_config)
#     site_unjasoned = json.loads(j_dump)
#     if str(site_config)  == str(site_unjasoned):
#         print('Strings matched.')
#     if site_config == site_unjasoned:
#         print('Dictionaries matched.')