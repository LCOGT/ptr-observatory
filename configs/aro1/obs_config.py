# -*- coding: utf-8 -*-
'''

Created on Fri Feb 07,  11:57:41 2020
Updated 20220914 WER   This version does not support color camera channel.

@author: wrosing

NB NB NB  If we have one config file then paths need to change depending upon which host does what job.

aro-0m35   10.0.0.73
aro_wema   10.0.0.50
Dragonfly  
'''

#                                                                                                  1         1         1
#        1         2         3         4         5         6         7         8         9         0         1         2
#23456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
import json
import time
#import ptr_events
from pprint import pprint


g_dev = None


#THis is branch wer-mrc first entered here 20221029:21:40 on WEMA
instance_type = 'obs' # This is the type of site this is.
wema_name = 'aro'
obs_id = 'aro1'

site_config = {
    'instance_type' : 'obs',
    'wema_name' : 'aro',
    'obs_id' : 'aro1',
    
    
    # Manual mode turns all automation off. 
    # The scope will only do what you tell it
    # This DOESN'T turn some safetys off 
    'scope_in_manual_mode' : False,
    'mount_reference_model_off': False,
    'sun_checks_off': False,
    'altitude_checks_off': False,    
    'daytime_exposure_time_safety_off': False,
    # Auto-centering is great.... unless you are polar aligning 
    'turn_auto_centering_off': False,
    #'observatory_location': site_name.lower(),
    'degrees_to_avoid_zenith_area_for_calibrations': 0, 
    
    'debug_site_mode': False,
    

    'debug_mode': False,
    
    
    
    
    'admin_owner_commands_only': False,

    'debug_duration_sec': 70200,
    
    "version_date": "20230606.wer",
    'site_desc': "Apache Ridge Observatory, Santa Fe, NM, USA. 2194m",
    'airport_codes':  ['SAF', 'ABQ', 'LSN'],
    'obsy_id': 'aro1',
    'obs_desc': "0m3f4.9/9 Ceravolo Astrograph, AP1600",
    'debug_site_mode': False,
    'debug_obsy_mode': False,
    'owner':  ['google-oauth2|102124071738955888216', \
               'google-oauth2|112401903840371673242'],  # Neyle,
    'owner_alias': ['ANS', 'WER'],
    'admin_aliases': ["ANS", "WER", 'KVH', "TELOPS", "TB", "DH", "KVH", 'KC'],

      # Indicates some special code for a single site.
                                 # Intention it is found in this file.
                                 # Fat is intended to be simple since
                                 # there is so little to control.
    'client_hostname':"ARO-0m30",     # Generic place for this host to stash.
    #'client_path': 'Q:/ptr/',
    'client_path': 'F:/ptr/',
    #'alt_path': '//house-computer/saf_archive_2/archive/sq01/',
    #'alt_path': 'Q:/ptraltpath',
    'alt_path': 'F:/ptraltpath',
    
    'save_to_alt_path' : 'no',
    #'archive_path': 'Q:/ptr/',       # Where images are kept.
    'archive_path': 'F:/ptr/',       # Where images are kept.
    
    'local_calibration_path': 'F:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    
    'archive_age' : -99.9, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'send_files_at_end_of_night' : 'no', # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'save_raw_to_disk' : True, # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'keep_reduced_on_disk' : True, # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_focus_images_on_disk' : True, # To save space, the focus file can not be saved.
    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing' : 1.0,
    'aux_archive_path':  None,
    'wema_is_active':  True,     # True if an agent (ie a wema) is used at a site.   # Wemas are split sites -- at least two CPS's sharing the control.
    'wema_hostname':  'ARO-WEMA',
    'wema_path': 'C:/ptr/',      #Local storage on Wema disk.
    'dome_on_wema':  True,       #NB NB NB CHange this confusing name. 'dome_controlled_by_wema'
    #'site_IPC_mechanism':  'shares',   # ['None', shares', 'shelves', 'redis']
    'site_IPC_mechanism':  'None',   # ['None', shares', 'shelves', 'redis']
    'wema_write_share_path':  'C:/ptr/wema_transfer/',  # Meant to be where Wema puts status data.
    'client_write_share_path':  '//aro-wema/wema_transfer/', #Meant to be a share written to by the TCS computer
    'redis_ip': None,   # None if no redis path present, localhost if redis iself-contained
    'obsid_is_generic':  True,   # A simple single computer ASCOM site.
    'obsid_is_specific':  False,  # Indicates some special code for this site, found at end of config.
#   'host_wema_site_name':  'ARO',
    'name': 'Apache Ridge Observatory 0m3f4.9/9',

    'location': 'Santa Fe, New Mexico,  USA',
    'observatory_url': 'https://starz-r-us.sky/clearskies2',   # This is meant to be optional
    'observatory_logo': None,   # I expect
    'dedication':   '''
                    Now is the time for all good persons
                    to get out and vote, lest we lose
                    charge of our democracy.
                    ''',    # i.e, a multi-line text block supplied and formatted by the owner.
    'location_day_allsky':  None,  #  Thus ultimately should be a URL, probably a color camera.
    'location_night_allsky':  None,  #  Thus ultimately should be a URL, usually Mono camera with filters.
    'location _pole_monitor': None,  #This probably gets us to some sort of image (Polaris in the North)
    'location_seeing_report': None,  # Probably a path to

    #'TZ_database_name':  'America/Denver',
    'mpc_code':  'ZZ24',    # This is made up for now.
    #'time_offset':  -6.0,   # These two keys may be obsolete give the new TZ stuff
    #'timezone': 'MDT',      # This was meant to be coloquial Time zone abbreviation, alternate for "TX_data..."
    #'latitude': 35.554298,     # ARo 35d33m15.472s Decimal degrees, North is Positive
    #'longitude': -105.870197,   #ARO -105d52m12.7092s Decimal degrees, West is negative
    #'elevation': 2194,    # meters above sea level
    #'reference_ambient':  10.0,  # Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    #'reference_pressure':  794.0,    #mbar   A rough guess 20200315
    
    'safety_check_period': 45,   #MF's original setting.
    
    'closest_distance_to_the_sun': 45, # Degrees. For normal pointing requests don't go this close to the sun. 
    'closest_distance_to_the_moon': 10, # Degrees. For normal pointing requests don't go this close to the moon. 
    'lowest_requestable_altitude': -5, # Degrees. For normal pointing requests don't allow requests to go this low. 

    'site_roof_control': 'yes', #MTF entered this in to remove sro specific code.... Basically do we have control of the roof or not see line 338 sequencer.py
    'site_allowed_to_open_roof': 'yes',
    
    'maximum_roof_opens_per_evening' : 4,
    'site_in_automatic_default': "Automatic",   # ["Manual", "Shutdown", "Automatic"]
    
    'automatic_detail_default': "Enclosure is initially set to Automatic by ARO site_config.",
    'observing_check_period' : 1,    # How many minutes between weather checks
    'enclosure_check_period' : 1,    # How many minutes between enclosure checks
    'auto_eve_bias_dark': True,
    
    'auto_midnight_moonless_bias_dark': False,
    'auto_eve_sky_flat': True,
    'eve_sky_flat_sunset_offset': -45.0,  # Minutes  neg means before, + after.
    #'eve_cool_down_open' : -56.0,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': True,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,
    'periodic_focus_time' : 2.0, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm' : 0.5, # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_exposure_time': 10,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 10,  # Exposure time in seconds for pointing run image
    'pointing_correction_dec_multiplier' : 1,
    'pointing_correction_ra_multiplier' : 1,
    
    
    'focus_trigger' : 0.5, # What FWHM increase is needed to trigger an autofocus
    'solve_nth_image' : 1, # Only solve every nth image
    'solve_timer' : 0.1, # Only solve every X minutes
    'threshold_mount_update' : 10, # only update mount when X arcseconds away
    'get_ocn_status': None,
    'get_enc_status': None,
    'not_used_variable': None,



    'defaults': {
        #'observing_conditions': 'observing_conditions1',  # These are used as keys, may go away.
        #'enclosure': 'enclosure1',
        'screen': 'screen1',
        'mount': 'mount1',
        'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        #'rotator': 'rotator1',
        'selector': None,
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
        #'observing_conditions',
        #'enclosure',
        'mount',
        'telescope',
        # 'screen',
        #'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',
        'sequencer',
        ],
    'wema_types': [
       'observing_conditions',
       'enclosure',
       ],
    'short_status_devices':  [
       # 'observing_conditions',
       #'enclosure',
       'mount',
       'telescope',
       # 'screen',
       'rotator',
       'focuser',
       'selector',
       'filter_wheel',
       'camera',
       'sequencer',
       ],

    'wema_status_span':  ['aro'],

#     'observing_conditions' : {     #for SAF
#         'observing_conditions1': {
#             'parent': 'site',
#             'name': 'Boltwood',
#             'driver': 'ASCOM.Boltwood.ObservingConditions',
#             'driver_2':  'ASCOM.Boltwood.OkToOpen.SafetyMonitor',
#             'driver_3':  'ASCOM.Boltwood.OkToImage.SafetyMonitor',
#             'redis_ip': '127.0.0.1',   #None if no redis path present
#             'has_unihedron':  True,
#             'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
#             'unihedron_port':  10    # False, None or numeric of COM port.
#         },
#     },

#     'enclosure': {
#         'enclosure1': {
#             'parent': 'site',

#             'name': 'HomeDome',
#             'enc_is_specific':  False,
#             'hostIP':  '10.0.0.10',
#             'driver': 'ASCOM.DigitalDomeWorks.Dome',  #  'ASCOMDome.Dome',  #ASCOMDome.Dome',  # ASCOM.DeviceHub.Dome',  # ASCOM.DigitalDomeWorks.Dome',  #"  ASCOMDome.Dome',

#             'has_lights':  True,
#             'controlled_by': 'mount1',
# 			'is_dome': True,
#             'mode': 'Automatic',
#             'enc_radius':  70,  #  inches Ok for now.
#             'common_offset_east': -19.5,  # East is negative.  These will vary per telescope.
#             'common_offset_south': -8,  # South is negative.   So think of these as default.

#             'cool_down': 89.0,     # Minutes prior to sunset.
#             'settings': {
#                 'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
#                                                                         #First Entry is always default condition.
#                 'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
#             },
#             'eve_bias_dark_dur':  1.5,   # hours Duration, prior to next.
#             'eve_screen_flat_dur': 0.0,   # hours Duration, prior to next.
#             'operations_begin':  -1.0,   # - hours from Sunset
#             'eve_cooldown_offset': -.99,   # - hours beforeSunset
#             'eve_sky_flat_offset':  1,   # - hours beforeSunset   Only THis is used in PTR events
#             'morn_sky_flat_offset':  0.4,   # + hours after Sunrise
#             'morning_close_offset':  0.41,   # + hours after Sunrise
#             'operations_end':  0.42,
#         },
#     },



    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'name': 'aropier1',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'safpier',
            'desc':  'AP 1600 GoTo',
            'driver': 'AstroPhysicsV2.Telescope',
            'alignment': 'Equatorial',
            'default_zenith_avoid': 0.0,   # degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            'has_ascom_altaz': False,
            'pointing_tel': 'tel1',     # This can be changed to 'tel2'... by user.  This establishes a default.
            
            'home_after_unpark' : False,
            'home_before_park' : False,
            
            'settle_time_after_unpark' : 10,
            'settle_time_after_park' : 10,
  #
            'permissive_mount_reset' : 'no', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'lowest_acceptable_altitude' : -1.0, # Below this altitude, it will automatically try to home and park the scope to recover.
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            'west_clutch_ra_correction': 0.0,  #final:   0.0035776615398219747 -0.1450812805892454
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction':   0.0, # Initially -0.039505313212952586,
            'east_flip_dec_correction':  0.0,  #initially  -0.39607711292257797,
            'settings': {
                'latitude_offset': 0.0,     # Decimal degrees, North is Positive   These *could* be slightly different than site.
                'longitude_offset': 0.0,   # Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
                'elevation_offset': 0.0,  # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 0.0,
                'horizon':  25.,    # Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  # Meant to be something to draw on the Skymap with a spline fit.
                    '0.0': 25.,
                    '90' : 25.,
                    '180': 25.,
                    '270': 25.,
                    '359': 25.
                    },  # We use a dict because of fragmented azimuth measurements.
                'refraction_on': True,
                'model_on': True,
                'rates_on': True,
                'model': {
                    'IH': 0.00, #-0.04386235467059052 ,  #new 20220201    ###-0.04372704281702999,  #20211203
                    'ID': 0.00, #-0.2099090362415872,  # -0.5326099734267764,
                    'WIH': 0.0,
                    'WID': 0.0,
                    'CH': 0.0,
                    'NP': 0.0,
                    'MA': 0.0,
                    'ME': 0.0,
                    'TF': 0.0,
                    'TX': 0.0,
                    'HCES': 0.0,
                    'HCEC': 0.0,
                    'DCES': 0.0,
                    'DCEC': 0.0,
                    }
                },
            },

    },



    'telescope': {                            # OTA = Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            #'ptrtel':  "saf1",
            'telescop': 'aro1',
            'desc':  'Ceravolo 300mm F4.9/F9 convertable',
            #'telescop': 'cvagr-0m30-f9-f4p9-001',
            'ptrtel': 'cvagr-0m30-f9-f4p9-001',
            'driver': None,                     # Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 31808,   #This is correct as of 20230420 WER
            'obscuration':  0.55,  # Informatinal, already included in collecting_area.
            'aperture': 30,
            'focal_length': 1470,  # 1470,   #2697,   # Converted to F9, measured 20200905  11.1C
            'has_dew_heater':  False,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   # This is a default for a single instrument system
            'selector_positions': 1,            # Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                 'f-ratio':  'f4.9',     #  This needs expanding into something easy for the owner to change.
                 "position1": ["darkslide1", "filter_wheel1", "camera1"]
                 },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  True,
            'has_cover':  False,
            'axis_offset_east': -19.5,  # East is negative  THese will vary per telescope.
            'axis_offset_south': -8,  # South is negative

            'settings': {
                'fans': ['Auto', 'High', 'Low', 'Off'],
                'offset_collimation': 0.0,    # If the mount model is current, these numbers are usually near 0.0
                                              # for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  # new terms.
                'west_flip_ca_offset': 0.0,
                'west_flip_dec_offset': 0.0
            },



        },

    },

    'rotator': {
        'rotator1': {
            'parent': 'telescope1',
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.OptecGemini.Rotator',
            'com_port':  'COM10',
            'minimum': -180.,
            'maximum': 360.0,
            'step_size':  0.0001,     # Is this correct?
            'backlash':  0.0,
            'throw': 300,
            'unit':  'degree'    # 'steps'
        },

    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'Optec Alnitak 16"',
            'driver': 'COM14',  # This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
            'minimum': 5,   # This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 255,  # Out of 0 - 255, this is the last value where the screen is linear with output.
                              # These values have a minor temperature sensitivity yet to quantify.


        },


    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
		    'com_port': 'COM13',    #AP 'COM5'  No Temp Probe on SRO AO Honders
            'start_at_config_reference': False,
            'correct_focus_for_temperature' : False,
            'maximum_good_focus_in_arcsecond': 2.5, # highest value to consider as being in "good focus". Used to select last good focus value
            
            # # F4.9 setup
            # 'reference': 5800,    # 20210313  Nominal at 10C Primary temperature
            # 'ref_temp':  5.1,    # Update when pinning reference
            # 'coef_c': 0,  # 26.055,   # Negative means focus moves out as Primary gets colder
            # 'coef_0': 5800,  # Nominal intercept when Primary is at 0.0 C.
            # 'coef_date':  '20220301',    # This appears to be sensible result 44 points -13 to 3C'reference':  6431,    # Nominal at 10C Primary temperature
            #F9 setup
            'reference': 5050, #5743,    #  Meas   Nominal at 10C Primary temperature
            #'ref_temp':  1.6,    # Update when pinning reference
            #'coef_c': -62.708,  #-77.57,   # negative means focus moves out/in as Primary gets colder/warmer.
            'coef_c': 0,  #-77.57,   # negative means focus moves out/in as Primary gets colder/warmer.
            'coef_0': 5050, #6155,   #5675,  20220502 Nominal intercept when Primary is at 0.0 C. f4.9 cONFIGURATION
            'coef_date':  '20221030',    # TEMP RANGE 12 TO 19, 6 MEASUREMENTS
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20221002',
            'minimum': 0,     # NB this area is confusing steps and microns, and need fixing.
            'maximum': 12600,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'throw': 125,
            'unit': 'micron',
            'unit_conversion': 9.09090909091,
            'has_dial_indicator': False
        },

    },

    'selector': {
        'selector1': {
            'parent': 'telescope2',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': None,
            'com_port': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 1,
            'instruments':  ['Aux_camera'],  # 'eShel_spect', 'planet_camera', 'UVEX_spect'],

            'cameras':  ['camera_1_1'],  # 'camera_1_2', None, 'camera_1_4'],

            'guiders':  [None], # 'guider_1_2', None, 'guide_1_4'],
            'default': 0
            },

    },

    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "LCO FW50_001d",
            'service_date': '20210716',
            
            
            "filter_settle_time": 0, #how long to wait for the filter to settle after a filter change(seconds)
            'override_automatic_filter_throughputs': False, # This ignores the automatically estimated filter gains and starts with the values from the config file
            
            "driver": "LCO.dual",  # 'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'ip_string': 'http://10.0.0.110',
            "dual_wheel": True,
            'filter_reference': 'PL',
            'settings': {
                'filter_count': 43,
                "filter_type": "50mm_sq.",
                "filter_manuf": "Astrodon",
                'home_filter':  1,
                'default_filter': "PL",
                'focus_filter' : 'PL',
                'filter_reference': 1,   # We choose to use W as the default filter.  Gains taken at F9, Ceravolo 300mm
                # Columns for filter data are : ['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'alias']
                #NB NB Note to WER please add cwl, bw and 'shape'
                'filter_data': [
                        ['Air',  [0,  0], -800, 1050., [2   ,  20], 'AIR'],    #0  Gains 20230703 
                        ['Exo',  [8,  0],    0, 1015., [360 , 170], 'Exoplanet - yellow, no UV or NIR'],     #1
                        
                        ['PL',   [7,  0],    0, 988.,  [360 , 170], 'Photo Luminance - does not pass NIR'],     #2
                        ['PR',   [0,  8],    0, 437.,  [.32 ,  20], 'Photo Blue'],     #3
                        ['PG',   [0,  7],    0, 487.,  [30  , 170], 'Photo Green'],     #4
                        ['PB',   [0,  6],    0, 844,   [360 , 170], 'Photo Blue'],     #5
                        ['NIR',  [0, 10],    0, 614.,  [0.65,  20], 'Near IR - redward of PR'],     #6
                        
                        ['O3',   [0,  2],    0, 80.0,  [360 , 170], 'Oxygen III'],     #7    #guess
                        ['HA',   [0,  3],    0, 41.7,  [360 , 170], 'Hydrogen Alpha - aka II'],     #8
                        ['N2',   [13, 0],    0, 20.67, [360 , 170], 'Nitrogen II'],     #9
                        ['S2',   [0,  4],    0, 20.11, [0.65,  20], 'Sulphur II'],     #10
                        ['CR',   [0,  5],    0, 45.0,  [360 , 170], 'Continuum Red - for Star subtraction'],     #11
                        
                        ['up',   [1,  0],    0, 25.61, [2   ,  20], "Sloan u'"],     #12
                        ['BB',   [9,  0],    0, 469.,  [0.65,  20], 'Bessell B'],     #13
                        ['gp',   [2,  0],    0, 913.,  [.77 ,  20], "Sloan g'"],     #14
                        ['BV',   [10, 0],    0, 613.,  [.32 ,  20], 'Bessell V'],     #15
                        ['BR',   [11, 0],    0, 609.,  [10  , 170], 'Bessell R'],     #16
                        ['rp',   [3,  0],    0, 469.,  [1.2 ,  20], "Sloan r'"],     #17
                        ['ip',   [4,  0],    0, 491.,  [.65 ,  20], "Sloan i'"],     #18
                        ['BI',   [12, 0],    0, 415.,  [360 , 170], 'Bessell I'],     #19
                        ['zp',   [0,  9],    0, 107.6, [360 , 170], "Sloan z'"],     #20    # NB I think these may be backward labeled,
                        ['zs',   [5,  0],    0, 107.4, [1.0 ,  20], "Sloan z-short"],     #21    # NB ZP is a broader filter than zs.
                        ['Y',    [6,  0],    0, 7.28,  [360 , 170], "Rubin Y - low throughput "],     #22
                        
  
                        ['dark', [5,  6],    0, 0.00,  [360 , 170], 'dk']],    #23     #Not a real filter.

                

                'filter_screen_sort':  [1],   # don't use narrow yet,  8, 10, 9], useless to try.
                'filter_sky_sort': ['S2','N2','up','HA','CR','O3','zs','zp','Ic','PR','rp','JB','PG', \
                                    'ip','Rc','JV','NIR','PB','gp','PL','EXO','air'],
                
                
                #'filter_sky_sort': [ 27, 26, 25, 28, 12, 7, 24, 18, 23, 10, 20, 17, 9,\
                #                    21 ,16, 15, 14, 22, 8, 30, 19, 6, 0]    #  No diffuser based filters



            },




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

    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'sq002ms',      # Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro',
            'service_date': '20211111',
            #'driver': "ASCOM.QHYCCD.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ## 'ASCOM.FLI.Kepler.Camera',
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
                      
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'G:/000ptr_saf/archive/sq01/autosaves/',


            'settings': {
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'min_flat_exposure': 0.01,
                'max_flat_exposure' : 20,
                'reject_new_flat_by_known_gain' : True,
                
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
                'direct_qhy_usb_speed' : 60,
                'is_osc' : False,
                
                #These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.                
                'interpolate_for_focus': False,
                'bin_for_focus' : True, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'focus_bin_value' : 2,
                'interpolate_for_sep' : False,
                'bin_for_sep' : True, # This setting will bin the image for SEP photometry.
                'sep_bin_value' : 2,
                'bin_for_platesolve' : True, # This setting will bin the image for platesolving.
                'platesolve_bin_value' : 2,
                
                'transpose_fits' : False,
                'flipx_fits': False,
                'flipy_fits': False,
                'rotate90_fits': False,
                'rotate180_fits': False,
                'rotate270_fits': False,
                'transpose_jpeg' : False,
                'squash_on_x_axis': False,
                'flipx_jpeg': False,
                'flipy_jpeg': False,
                'rotate90_jpeg': False,
                'rotate180_jpeg': False,
                'rotate270_jpeg': False,
                'reduced_image_edge_crop': 30,
                'focus_image_crop_width': 0.0,
                'focus_image_crop_height': 0.0,
                'focus_jpeg_size': 1500,
                'platesolve_image_crop': 0.0,
                'sep_image_crop_width': 0.0,
                'sep_image_crop_Height': 0.0,
                'do_cosmics':  False,
                
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.                
                'drizzle_value_for_later_stacking': 0.5,
               
               
                'do_cosmics' : False,
                #'dark_length' : 1,
                
                
                
                'osc_bayer' : 'RGGB',
                'crop_preview': False,
                'crop_preview_ybottom': 1,
                'crop_preview_ytop': 1,
                'crop_preview_xleft': 1,
                'crop_preview_xright': 1,
                'temp_setpoint': -5,
                'calib_setpoints': [-7.5, -5, 0],  # Should vary with season? by day-of-year mod len(list)
                'day_warm': False,
                'day_warm_degrees' : 6, # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : False,
                'cooler_on': True,
                
                "cam_needs_NumXY_init": True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4800,   # NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  3211,
                'x_chip':  9576,   # NB Should specify the active pixel area.   20200315 WER
                'y_chip':  6388,
                'x_trim_offset':  8,   # NB these four entries are guesses.
                'y_trim_offset':  8,
                'x_bias_start':  9577,
                'y_bias_start' : 6389,
                'x_active': 4784,
                'y_active': 3194,
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                
                'CameraXSize' : 9600,
                'CameraYSize' : 6422,
                #'MaxBinX' : 2,
                #'MaxBinY' : 2,
                'StartX' : 1,
                'StartY' : 1,

                'x_field_deg': 1.042,   #  round(4784*1.055/3600, 4),
                'y_field_deg': 0.7044,   # round(3194*1.055/3600, 4),
                'detsize': '[1:9600, 1:6422]',  # QHY600Pro Physical chip data size as returned from driver
                'ccd_sec': '[1:9600, 1:6422]',
                'bias_sec': ['[1:24, 1:6388]', '[1:12, 1:3194]', '[1:8, 1:2129]', '[1:6, 1:1597]'],
                'det_sec':  ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
                'overscan_x': 24,
                'overscan_y': 3,
                'north_offset': 0.0,    # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,     # Not sure why these three are even here.
                'rotation': 0.0,        # Probably remove.
                'min_exposure': 0.00001,
                'max_exposure': 360,
                'max_daytime_exposure': 0.5,
                'can_subframe':  True,
                'min_subframe':  [128, 128],
                
                'cosmics_at_default' : 'yes',
                'cosmics_at_maximum' : 'yes',
                'cycle_time':  0.5,  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'rbi_delay':  0.,      # This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color':  False,
                'can_set_gain':  False,
                'bayer_pattern':  None,    # Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'camera_gain':   1.97, #[10., 10., 10., 10.],     #  One val for each binning.
                'camera_gain_stdev':   0.15, #[10., 10., 10., 10.],     #  One val for each binning.
                'read_noise':  1.92, #[9, 9, 9, 9],    #  All SWAGs right now
                'read_noise_stdev':   0.003, #[10., 10., 10., 10.],     #  One val for each binning.
                
                'reference_dark': 0.1, #, .8, 1.8, 3.2],  #  Guess
                
                
                
                
                
                'ref_dark': 360.0,    #  this needs fixing.
                'long_dark':600.0,
                'max_linearity':  60000,   # Guess  60% of this is max counts for skyflats.  75% rejects the skyflat
                'saturate':   60000,  #  [2,262000], [3,589815], [4, 1048560]] ,   # e-.  This is a close guess, not measured, but taken from data sheet.
                'fullwell_capacity': 80000, #  320000, 720000, 1280000],
                                    #hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
                    #hdu.header['RDOUTM'] = (self.config['camera'][self.name]['readout_mode'], 'Camera readout mode')
                    #hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
                'read_mode':  'Normal',
                'readout_mode':  'Normal',
                'readout_speed': 0.6,
                'readout_seconds': 12,
                'smart_stack_exposure_time': 30,
                'areas_implemented': ["Full", '2x2', '4x4',"600%", "500%", "450%", "300%", "220%", "150%", "133%", "100%", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'has_darkslide':  True,
                'darkslide_com': 'COM10',  #old controller COM10, new one 9a COM17
                'shutter_type': "Electronic",
                'number_of_bias_to_collect': 31,
                'number_of_dark_to_collect': 15,
                'number_of_bias_to_store': 45,   #SWAGS by Wayne 20230613
                'number_of_dark_to_store': 45,                
                'number_of_flat_to_collect': 7,                
                'number_of_flat_to_store' : 21,
                
                'dark_exposure': 360,
                'flat_bin_spec': '1,1', #'2,2'],    #Default binning for flats
                'bias_dark_bin_spec': '1,1', #'2,2'],    #Default binning for flats
                'bin_enable': '1,1', #'2,2'],
                'dark_length' : 360,
                #'bias_count' : 10,
                #'dark_count' : 10,
                'bin_modes':  [[1, 1, 0.528], [2, 2, 1.055], [3, 3, 1.583], [4, 4, 2.110]],   #Meaning no binning choice if list has only one entry, default should be first.
                'optimal_bin':  [2, 2, 1.055],
                'max_res_bin':  [1, 1, 0.528],
                #'pix_scale': [0.528, 1.055, 1.583, 2.110],    #  1.4506,  bin-2  2* math.degrees(math.atan(9/3962000))*3600
                
                
                
                '1x1_pix_scale': 0.528,    #  This is the 1x1 binning pixelscale
                'native_bin': 2, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.                
                'drizzle_value_for_later_stacking': 0.5,
                
                'has_screen': False,
                'screen_settings':  {
                    'screen_saturation':  157.0,   # This reflects WMD setting and needs proper values.
                    'screen_x4':  -4E-12,  # 'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                },
            },
        },


    },

    'sequencer': {
        'sequencer1': {
            'parent': 'site',
            'name': 'Sequencer',
            'desc':  'Automation Control',
            'driver': None,


        },
    },

    # I am not sure AWS needs this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': None,
            'win_url': None,
            'redis':  '(host=none, port=6379, db=0, decode_responses=True)'
        },
    },
}
get_ocn_status = None   # NB these are placeholders for site specific routines for in a config file
get_enc_status = None

if __name__ == '__main__':
    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')