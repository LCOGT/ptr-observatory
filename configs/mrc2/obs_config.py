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
import json

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
    'lowest_requestable_altitude': 10,  # Degrees. For normal pointing requests don't allow requests to go this low.
    'lowest_acceptable_altitude' : 0.0, # Below this altitude, it will automatically try to home and park the scope to recover.
    'degrees_to_avoid_zenith_area_for_calibrations': 5,
    'degrees_to_avoid_zenith_area_in_general' : 0,
    'maximum_hour_angle_requestable' : 12,
    'temperature_at_which_obs_too_hot_for_camera_cooling' : 28,   #10C higher than chiller water

    # These are the default values that will be set for the obs
    # on a reboot of obs.py. They are safety checks that
    # can be toggled by an admin in the Observe tab.
    'scope_in_manual_mode': False,    #20231222 This makes things easier for heavy debugging
    'mount_reference_model_off': False,
    'sun_checks_on': True,
    'moon_checks_on': True,
    'altitude_checks_on': True,
    'daytime_exposure_time_safety_on': False,

    # Depending on the pointing capacity of the scope OR the field of view OR both
    # The pointing may never be quite good enough to center the object without
    # a centering exposure. On initial commissioning, it should be set to always autocenter
    # until you are convinced the natural pointing with empirical corrections is "good enough"
    'always_do_a_centering_exposure_regardless_of_nearby_reference': True,

    # Setup of folders on local and network drives.
    'ingest_raws_directly_to_archive': True,
    # LINKS TO PIPE FOLDER
    'save_raws_to_pipe_folder_for_nightly_processing': False,
    'pipe_archive_folder_path': 'X:/localptrarchive/',  #WER changed Z to X 20231113 @1:16 UTC
    'temporary_local_pipe_archive_to_hold_files_while_copying' : 'D:/local_ptr_temp/tempfolderforpipeline',
    'temporary_local_alt_archive_to_hold_files_while_copying' : 'D:/local_ptr_temp/tempfolderforaltpath',

    # Setup of folders on local and network drives.
    'client_hostname':  'mr2-0m60',
    'archive_path':  'C:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'save_to_alt_path':  'yes',
    'local_calibration_path': 'C:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'archive_age' : 2, # Number of days to keep files in the local archive before deletion. Negative means never delete

    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    'save_substack_components_raws': False, # this setting saves the component 10s/30s completely raw files out as well during a substack

    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus files may not be saved.
    # These are options to minimise diskspace for calibrations
    'produce_fits_file_for_final_calibrations': True,
    'save_archive_versions_of_final_calibrations' : False,
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : False,
   # Number of files to send up to the ptrarchive simultaneously.
   'number_of_simultaneous_ptrarchive_streams' : 4,
   # Number of files to send over to the pipearchive simultaneously.
   'number_of_simultaneous_pipearchive_streams' : 4,
   # Number of files to send over to the altarchive simultaneously.
   'number_of_simultaneous_altarchive_streams' : 4,


   # Bisque mounts can't run updates in a thread ... yet... until I figure it out,
   # So this is False for Bisques and true for everyone else.
   'run_main_update_in_a_thread': True,
   'run_status_update_in_a_thread' : True,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.5,





    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats

    'bias_dark interval':  120.,   #minutes
    'eve_sky_flat_sunset_offset': -45.,  # 40 before Minutes  neg means before, + after.

    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 15 ,
    'clock_and_auto_focus_offset': -10,

    'astro_dark_buffer': 10,   #Min before and after AD to extend observing window
    #'morn_flat_start_offset': -5,       #min from Sunrise
    'morn_flat_start_offset': -10,       #min from Sunrise
    'morn_flat_end_offset':  +40,        #min from Sunrise
    'end_night_processing_time':  90,   #  A guess
    'observing_begins_offset': 18,
    # How many minutes before Nautical Dawn to observe ....
    'observing_ends_offset': 18,


    # Exposure times for standard system exposures
    'focus_exposure_time': 45,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 20,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 1,    # How many minutes between weather checks
    'enclosure_check_period': 1,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': False, # DO NOT MAKE TRUE!!!
    'auto_eve_sky_flat':True,

    'time_to_wait_after_roof_opens_to_take_flats': 30,   #sec Just imposing a minimum in case of a restart.
    'auto_midnight_moonless_bias_dark': True,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': False, # DO NOT MAKE TRUE!!!

    # FOCUS OPTIONS
    'periodic_focus_time': 2, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.75,  # What FWHM increase is needed to trigger an autofocus

    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 45,  # only update mount when X arcseconds away
    'push_file_list_to_pipe_queue': False,

   # The site can fully platesolve each image before it is sent off to s3 or a PIPE
   # If there are spare enough cycles at the site, this saves time for the PIPE
   # to concentrate on more resource heavy reductions.
   # Also leads to fully platesolved reduced images on the local site computer
   # Usually set this to True
   # if the scope has a decent NUC.... CURRENTLY LEAVE AS IS UNTIL MTF HAS FINISHED TESTING THIS.
   'fully_platesolve_images_at_site_rather_than_pipe' :True,  #TEMP for mrc2 for bringup WER 20250408



   "platesolve_timeout": 45, # Default should be about 45 seconds, but slower computers will take longer

    'defaults': {
        'mount': 'mount1',
        'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector':  'selector1',
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    # Initial roles are assigned here. These may change during runtime.
    # Value is the device display name
    # This is where to configure a second device of the same type if you want to control it in the site code.
    # Devices are referenced in obs with self.devices['device_role']
    # Also important to note: these must match the roles in obs.py create_devices().
    # Roles are standardized across all sites even if not all roles are used at each site.
    'device_roles': {
        'mount': 'mount1',
        'main_rotator': 'rotator1',
        'main_focuser': 'focuser1',
        'main_fw': 'filter_wheel1',

        # Cameras
        'main_cam': 'camera_1_1',
        # Cameras below aren't currently used, but here as an example.
        'guide_cam': None,
        'widefield_cam': None,
        'allsky_cam': None,
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
            'wait_after_slew_time': 0.0, # Some mounts report they have finished slewing but are still vibrating. This adds in some buffer time to a wait for slew.
            'needs_to_wait_for_dome' : False,
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
            #'permissive_mount_reset' : 'yes', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            #'home_after_unpark' : False,
            'home_altitude':  0.0,   #overloaded term these are not the coordinates for a PW home. Meant now to be park position. Due South.
            'home_azimuth':  180.0,
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
                'model_on': False,
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
        'telescope_1': {
            'parent': 'mount2',
            'name': 'Main OTA',
            'desc':  'Planewave CDK 600 F6.8',   #i seem to use desc, an alias more or less for the same thing.
            'telescop': 'mrc2',
            'ptrtel': 'mrc2',
            'driver': None,                     #Essentially this device is informational.  It is mostly about the optics.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'collecting_area':  154891,    #This is the correct area 20250514 WER
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

            'focuser_movement_settle_time': 0,
            'start_at_config_reference': False,
            'correct_focus_for_temperature' : True,
            'maximum_good_focus_in_arcsecond': 5.0, # highest value to consider as being in "good focus". Used to select last good focus value

            'reference':  6300,    #Nominal at 20C Primary temperature, in microns not steps.
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20240210',   # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            'use_local_temp':  False,
            'relative_focuser': False,   #MFITZ added this for ECO
            'minimum': 0,    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'throw': 64,
            'depth_of_focus': 102.7, # +/- 2*focal-ratio^2(0.555) -- unit is microns, result is +/-2 = 4x or 0.1 mm for this telescope
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

            "filter_settle_time": 2, #how long to wait for the filter to settle after a filter change(seconds)

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


                # 'filter_data': [
                #                 ['air',     [0, 0], -1000, 582,    [2, 17], 'ai'],   # 0
                #                 ['Lum',     [0, 1],     0, 544,   [2, 17], 'w '],   # 20
                #                 #['Red',     [4, 0],     0, 15,   [2, 17], 'r '],  # 21                                ['JV (Grn)',      [0, 3],     0, 1 [2, 17], 'V '],   # 9
                #                 #['Green',   [3, 0],     0, 21,   [2, 17], 'V '],   # 22
                #                 #['Blue',    [1, 0],     0, 18,   [2, 17], 'B '],   # 23
                #                 ['w',       [0, 1],     0, 544,[2, 17], 'w '],
                #                 ['EXO',     [6, 0],     0, 392,[2, 17], 'EX'],  # 12 ,   # 1
                #                 #['dif',    [0, 2],
                #                 ['JB',      [1, 0],     0, 104,    [2, 17], 'B '],   # 7
                #                 ['gp',      [2, 0],     0, 271,    [2, 17], 'g '],   # 8
                #                 ['JV',      [3, 0],     0, 178,   [2, 17], 'V '],   # 9
                #                 ['rp',      [4, 0],     0, 152,   [2, 17], 'r '],  # 10
                #                 ['JB',      [1, 0],     0, 104,    [2, 17], 'B '],
                #                 ['ip',      [5, 0],     0, 59.5,   [2, 17], 'i '],  # 11
                #                 ['O3',      [0, 3],     0, 7.75,    [2, 17], 'O3'],   # 3
                #                 ['HA',      [0, 4],     0, 2.76,    [2, 17], 'HA'],   # 4
                #                 ['N2',      [0, 5],     0, 3.39,    [2, 17], 'N2'],
                #                 ['S2',      [0, 6],     0, 3.51,  [2, 17], 'S2'],   # 5
                #                 ['dark',    [1, 6],     0, 0.0,   [2, 17], 'dk']], # 19

                # 'filter_data': [
                #                 ['air',     [0, 0], 'ai'],   # 0
                #                 ['Lum',     [0, 1],  'w '],   # 20
                #                 #['Red',     [4, 0],     0, 15,   [2, 17], 'r '],  # 21                                ['JV (Grn)',      [0, 3],     0, 1 [2, 17], 'V '],   # 9
                #                 #['Green',   [3, 0],     0, 21,   [2, 17], 'V '],   # 22
                #                 #['Blue',    [1, 0],     0, 18,   [2, 17], 'B '],   # 23
                #                 ['w',       [0, 1],   'w '],
                #                 ['EXO',     [6, 0],    'EX'],  # 12 ,   # 1
                #                 ['dif',    [0, 2],       'dif'],
                #                 ['JB',      [1, 0],    'B '],   # 7
                #                 ['gp',      [2, 0],    'g '],   # 8
                #                 ['JV',      [3, 0],    'V '],   # 9
                #                 ['rp',      [4, 0],     'r '],  # 10
                #                 ['JB',      [1, 0],    'B '],
                #                 ['ip',      [5, 0],     'i '],  # 11
                #                 ['O3',      [0, 3],   'O3'],   # 3
                #                 ['HA',      [0, 4],     'HA'],   # 4
                #                 ['N2',      [0, 5],     'N2'],
                #                 ['S2',      [0, 6],    'S2'],   # 5
                #                 ['dark',    [1, 6],     'dk']], # 19

                'filter_data': [

                                ['air',     [0, 0],  'ai'],   # 1
                                ['w',       [1, 0],  'w '],   # 2
                                ['EXO',     [0, 6],  'EX'],   # 3
                                ['BU',      [2, 0],  'BU'],   # 4
                                ['BB',      [0, 1],  'BB'],   # 5
                                ['gp',      [0, 2],  'gp'],   # 6
                                ['BV',      [0, 3],  'Bv'],   # 7
                                ['rp',      [0, 4],  'rp'],   # 8
                                ['ip',      [0, 5],  'ip'],   # 9
                                ['O3',      [3, 0],  'O3'],   # 10
                                ['HA',      [4, 0],  'HA'],   # 11
                                ['N2',      [5, 0],  'N2'],   # 12
                                ['S2',      [6, 0],  'S2'],   # 13
                                ['dk',      [6, 1],  'dk']],  # 14
                'focus_filter' : 'w',




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

            'name': 'SQ007',# 'OF01', #'KF04',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600 Pro Mono',  #'FLI On-semi 50100',

            'overscan_trim' : 'QHY600',
            'service_date': '20240210',  #'20231222'
            #'driver':  'ASCOM.QHYCCD.Camera',   #  Maxim.CCDCamera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'driver':  'QHYCCD_Direct_Control',   #'ASCOM.FLI.Kepler.Camera',  #"QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'switch_driver':  'ASCOM.Device1.Switch',


            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,


            'detector':  'Sony IMX-455',

            'manufacturer':  'QHY',
            'use_file_mode':  False,
            #'file_mode_path':  'Q:/000ptr_saf/archive/of01/autosaves/',
            'settings': {

                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,


                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.

                # Simple Camera Properties

                'is_cmos':   True,
                'is_ccd':    False,
                'is_osc':    False,
                'is_color':  False,  # NB we also have a is_osc key.

                'osc_bayer': 'RGGB',

                # There are some infuriating popups on theskyx that manually
                # need to be dealt with when doing darks and lights.
                # This setting uses a workaround for that. This is just for CMOS
                # CCDs are fine.
                'cmos_on_theskyx': False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  False,           #was False until WER put in FLI ascom shutter mod

                'darkslide_type': None, #'ASCOM_FLI_SHUTTER', # dunno what the other one is yet.
                'darkslide_com':  None, #  'ASCOM.FLI',    # Was "COM15" before changing to FLI.ASCOM
                'shutter_type':   None,  # "Leaf",

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
                # 'direct_qhy_readout_mode' : 0,
                # 'direct_qhy_gain' : 26,
                # 'direct_qhy_offset' : 60,

                # 'direct_qhy_usb_traffic' : 45,

                # 'set_qhy_usb_speed': True,

                # #'direct_qhy_usb_speed' : 45,


                #HERE IS THE POTENTIAL MODE 1 SETTINGS
                'direct_qhy_readout_mode' : 1,
                'direct_qhy_gain' : 60,
                'direct_qhy_offset' : 30,
                #'direct_qhy_usb_speed' : 50,
                'set_qhy_usb_speed': True,
                'direct_qhy_usb_traffic' : 50,


                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                # 'interpolate_for_focus': False,
                # # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                # 'bin_for_focus': True,
                # 'focus_bin_value' : 2,
                # 'interpolate_for_sep': False,
                # 'bin_for_sep': True,  # This setting will bin the image for SEP photometry rather than interpolating.
                # 'sep_bin_value' : 2,
                # # This setting will bin the image for platesolving rather than interpolating.
                # 'bin_for_platesolve': True,
                # 'platesolve_bin_value' : 2,


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
                'reduced_image_edge_crop': 0,

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



               # # For large fields of view, crop the images down to solve faster.
               # # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
               # # Probably also similar for platesolving.
               # # for either pointing or platesolving even on more modest size fields of view.
               # # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
               # # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless
               # # you clearly need to.
               # 'focus_image_crop_width': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full width
               # 'focus_image_crop_height': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full height
               # 'focus_jpeg_size': 1500, # How many pixels square to crop the focus image for the UI Jpeg

               # # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE
               # 'platesolve_image_crop': 0.0,  # Platesolve crops have to be symmetrical

               # # Really, the SEP image should not be cropped unless your field of view and number of sources
               # # Are taking chunks out of the processing time.
               # # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
               # 'sep_image_crop_width': 0.0,
               # # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
               # 'sep_image_crop_height': 0.0,


                # This is the area for cooling related settings
                'cooler_on': True,

                'temp_setpoint': 2,  # Verify we can go colder
                'rated_max_delta': -20, # Rated capacity for TEC to go below ambient.
                "temp_setpoint_tolarance": 2.0,   # Centigrade
                "temp_setpoint_tolerance": 2.5,
                'has_chiller': True,
                'ambient_water_cooler':  False,  #QHY sells these.
                'chiller_com_port': 'COM1',
                'chiller_ref_temp':  15,  # C
                'day_warm': False,
                'day_warm_degrees': 0,  # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : False,


                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.

                #NB WER 20231223  FLI 50100  This does not make a lot of sense for a a 6 micron
                #CCD with 0.312 asec pixels @ MRC  So we might run 2x2 binned all the time
                #esentially redefine the 1x1 binned pixel as seen by the SS annd downstream
                #calibration and pipe system.  Readout speeds up.  The binning arithmetic
                #appears to be a sum  However the simplicity of treating all cameras the same
                #is compelling.  This camera has two channels so we need to look at crosstalk.


                #'onebyone_pix_scale': 0.15874,    #  This is the 1x1 binning pixelscale

                'native_bin': 2, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                'x_pixel':  3.76, # pixel size in microns
                'y_pixel':  3.76, # pixel size in microns

                #NB 43 x 32 amin field.  FLI 50100
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.
                'drizzle_value_for_later_stacking': 0.5,
                'dither_enabled':  True,      #Set this way for tracking testing

                # This is the absolute minimum and maximum exposure for the camera

                'min_exposure': 0.001,
                'max_exposure': 360.,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 2,
                # For certain shutters, short exposures aren't good for flats.  Largely applies to ccds though.
                'min_flat_exposure': 0.00001, # WER 20240111 changed from 0.4   #just for now for CCD camera testing
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,



                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain' : True,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.

                # 'camera_gain':   2.48, #[10., 10., 10., 10.],     #  One val for each binning.
                # 'camera_gain_stdev':   0.04, #[10., 10., 10., 10.],     #  One val for each binning.
                # 'read_noise':  10.615, #[9, 9, 9, 9],    #  All SWAGs right now
                # 'read_noise_stdev':   0.012, #[10., 10., 10., 10.],     #  One val for each binning.
                'dark_lim_adu': 3,   #adu/s of dark 20231229 moved down from 0.5
                'dark_lim_std': 15,  #first guess. See above.

                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 85000,  # e- NB Guess
                'saturate':   62000,
                'max_linearity':  60000,   # Guess
                # How long does it take to readout an image after exposure
                'cycle_time':            2,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 30,

                'substack': True, # Substack with this camera

                'smart_stack_exposure_NB_multiplier':  3,   #Michael's setting


                # As simple as it states, how many calibration frames to collect and how many to store.
                'number_of_bias_to_collect': 13,
                'number_of_dark_to_collect': 13,

                'number_of_flat_to_collect': 10,   #just for now for CCD camera testing wer 20240113 (friday!)
                'number_of_bias_to_store': 53,
                'number_of_dark_to_store': 31,
                'number_of_flat_to_store': 32,

                # Default dark exposure time.
                'dark_exposure': 360,


                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': True,
                # Simialrly for Salt and Pepper
                'do_saltandpepper' : True,
                # And debanding
                'do_debanding' : False,



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

if __name__ == '__main__':
    '''
    This is a simple test to send and receive via json.
    '''

    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')