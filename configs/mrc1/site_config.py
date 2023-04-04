# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20220107 20:01 WER

@author: wrosing
'''
import json


'''
                                                                                                   1         1         1       1
         1         2         3         4         5         6         7         8         9         0         1         2       2
12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
'''

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.
degree_symbol = "°"
site_name = 'mrc'
obs_id = 'mrc1'    #NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_config = {
    # THESE ARE TO BE DELETED VERY SOON!
    # THEY EXIST SOLELY SO AS TO NOT BREAK THE UI UNTIL 
    #THINGS ARE MOVED TO OBS_ID
    'site': 'mrc1',
    'site_id': 'mrc1',
    ####################################################
    ####################################################
    'obs_id': 'mrc1',
    'observatory_location': site_name.lower(),
    

    'debug_site_mode': False,
    
    'debug_mode': False,
    'admin_owner_commands_only': False,
    'debug_duration_sec': 3600,

    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne

    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],

    'client_hostname':  'MRC-0m35',  #This is also the long-name  Client is confusing!
                    # NB NB disk D at mrc may be faster for temp storage
    'client_path':  'Q:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'plog_path':  'Q:/ptr/mrc1/',  #place where night logs can be found.
    'save_to_alt_path' : 'no',
    'archive_path':  'Q:/ptr/',

    'archive_age' : -99.9, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'send_files_at_end_of_night' : 'no', # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    
    'save_raw_to_disk' : True, # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'keep_reduced_on_disk' : True, # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_focus_images_on_disk' : True, # To save space, the focus file can not be saved.
    
    
    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing' : 1.0,
    
    'aux_archive_path':  None,   #NB NB we might want to put Q: here for MRC
    'wema_is_active':  True,          # True if the split computers used at a site.  NB CHANGE THE DAMN NAME!
    'wema_hostname': 'MRC-WMS-ENC',   # Prefer the shorter version
    'wema_path':  'Q:/ptr/',  # '/wema_transfer/',
    'dome_on_wema':   True,
    'site_IPC_mechanism':  'redis',   # ['None', shares', 'shelves', 'redis']  Pick One
    'wema_write_share_path': 'Q:/ptr/',  # Meant to be where Wema puts status data.
    'client_read_share_path':  'Q:/ptr/', #NB these are all very confusing names.
    'client_write_share_path': 'Q:/ptr/',
    'redis_ip': '10.15.0.109',  #'127.0.0.1', None if no redis path present,
    'obsid_is_generic':  False,   # A simply  single computer ASCOM site.
    'obsid_is_specific':  False,  # Indicates some special code for this site, found at end of config.
    

    'host_wema_site_name':  'MRC',  #  The umbrella header for obsys in close geographic proximity,
                                    #  under the control of one wema
    'name': 'Mountain Ranch Camp Observatory 0m35f7.2',
    'airport_code': 'SBA',
    'location': 'Near Santa Barbara CA,  USA',
    'telescope_description': '0m35 f7.2 Planewave CDK',
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'observatory_logo': None,
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #i.e, a multi-line text block supplied by the owner.  Must be careful about the contents for now.
    'location_day_allsky':  None,  #  Thus ultimately should be a URL, probably a color camera.
    'location_night_allsky':  None,  #  Thus ultimately should be a URL, usually Mono camera with filters.
    'location _pole_monitor': None,  #This probably gets us to some sort of image (Polaris in the North)
    'location_seeing_report': None,  # Probably a path to a jpeg or png graph.
    'debug_flag': True,    #  Be careful about setting this flag True when pushing up to dev!
    'TZ_database_name': 'America/Los_Angeles',
    'mpc_code':  'ZZ23',    #This is made up for now.
    'time_offset':  -8,     # NB these two should be derived from Python libs so change is automatic
    'timezone': 'PST',
    'latitude': 34.459375,     #Decimal degrees, North is Positive
    'longitude': -119.681172,   #Decimal degrees, West is negative
    'elevation': 317.75,    # meters above sea level
    'reference_ambient':  10.0,  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  977.83,  #mbar Alternately 12 entries, one for every - mid month.

    'obsid_roof_control': False, #MTF entered this in to remove sro specific code  NB 'site_is_specifc' also deals with this
    'obsid_allowed_to_open_roof': False,
    'period_of_time_to_wait_for_roof_to_open' : 50, # seconds - needed to check if the roof ACTUALLY opens. 
    'only_scope_that_controls_the_roof': False, # If multiple scopes control the roof, set this to False
    

    'check_time': 300,   #MF's original setting.
    'maximum_roof_opens_per_evening' : 4,
    'roof_open_safety_base_time' : 15, # How many minutes to use as the default retry time to open roof. This will be progressively multiplied as a back-off function.
    

    'obsid_in_automatic_default': "Shutdown",   #"Manual", "Shutdown"
    'automatic_detail_default': "Enclosure is set to Shutdown mode.",

    
    'closest_distance_to_the_sun': 45, # Degrees. For normal pointing requests don't go this close to the sun. 
    
    'closest_distance_to_the_moon': 10, # Degrees. For normal pointing requests don't go this close to the moon. 
    
    'lowest_requestable_altitude': -5, # Degrees. For normal pointing requests don't allow requests to go this low. 

    'observing_check_period' : 5,    # How many minutes between weather checks
    'enclosure_check_period' : 5,    # How many minutes between enclosure checks

    'auto_eve_bias_dark': True,
    
    'auto_midnight_moonless_bias_dark': False,
    'auto_eve_sky_flat': False,

    'eve_sky_flat_sunset_offset': -60.,  # 40 before Minutes  neg means before, + after.

    'eve_cool_down_open' : -65.0,
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': False,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,  #MF I am leaving this alone.
    'periodic_focus_time' : 0.5, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm' : 0.5, # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_exposure_time': 10, # Exposure time in seconds for exposure image
    'pointing_exposure_time': 20, # Exposure time in seconds for exposure image
    'focus_trigger' : 0.75, # What FWHM increase is needed to trigger an autofocus
    'solve_nth_image' : 1, # Only solve every nth image
    'solve_timer' : 0.05, # Only solve every X minutes
    'threshold_mount_update' : 100, # only update mount when X arcseconds away

    'defaults': {
        'observing_conditions': 'observing_conditions1',
        'enclosure': 'enclosure1',
        'mount': 'mount1',
        'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector':  None,
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
            'observing_conditions',
            'enclosure',
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
     'wema_types': [
            'observing_conditions',
            'enclosure',
            ],
     'enc_types': [
            'enclosure'
            ],
     'short_status_devices':  [
            # 'observing_conditions',
            # 'enclosure',
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

    'observing_conditions': {
        'observing_conditions1': {
            'parent': 'site',
            'ocn_is_specific':  False,  # Indicates some special site code.
            # Intention it is found near bottom of this file.
            'name': 'Weather Station #1',
            'driver': 'ASCOM.SkyAlert.ObservingConditions',
            'share_path_name': None,
            'driver_2': 'ASCOM.SkyAlert.SafetyMonitor',
            'driver_3': None,
            'redis_ip': '10.15.0.109',   #None if no redis path present
            'has_unihedron': False,
            'ocn_has_unihedron':  False,
            'have_local_unihedron': False,     #  Need to add these to setups.
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  10    #  False, None or numeric of COM port..

            },
        },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'enc_is_specific':  False,  # Indicates some special site code.            
            'directly_connected': False, # For ECO and EC2, they connect directly to the enclosure, whereas WEMA are different.
            'name': 'Megawan',
            'hostIP':  '10.15.0.65',
            'driver': 'ASCOM.SkyRoofHub.Dome',    #  Not really a dome for Skyroof.
            'redis_ip': '10.15.0.109',   #None if no redis path present
            'enc_is_specific':  False,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'has_lights':  True,
            'controlled_by':  ['mnt1', 'mnt2'],
            'is_dome': False,
            'mode':  'Automatic',
            'cool_down': -65,    #  Minutes prior to sunset.
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],

                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
            },
            'eve_bias_dark_dur':  2.0,   #hours Duration, prior to next.
            'eve_screen_flat_dur': 1.0,   #hours Duration, prior to next.
            'operations_begin':  -1.0,   #  - hours from Sunset
            'eve_cooldown_offset': -.99,   #  - hours beforeSunset
            'eve_sky_flat_offset':  0.5,   #  - hours beforeSunset
            'morn_sky_flat_offset':  0.4,   #  + hours after Sunrise
            'morning_close_offset':  0.41,   #  + hours after Sunrise
            'operations_end':  0.42,
        },
    },



    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'tel_id': '0m35',
            'name': 'eastpier',
            'hostIP':  '10.15.0.30',
            'hostname':  'eastpier',
            'desc':  'Planewave L500 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',  # Was 'ASCOM.AltAzDS.Telescope' prior to 20210417 WER
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'alignment': 'Alt-Az',
            'default_zenith_avoid': 7.0,   #degrees floating
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction': 0.0,
            'east_flip_dec_correction': 0.0,  #
            'home_after_unpark' : False,
            'home_before_park' : False,
            'permissive_mount_reset' : 'yes', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly'home_after_unpark' : True,
            'lowest_acceptable_altitude' : -2, # Below this altitude, it will automatically try to home and park the scope to recover.
            
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            'has_paddle': False,
            'has_ascom_altaz': True,
            'pointing_tel': 'tel1',
            'Selector':{
                'available': False,         #If True add these lines;
                # 'positions': 4,
                # 'inst 1': 'camera_1_1',      #inst_1 is always the default until status reports different
                # 'inst 2': 'echelle1',     #These are all types od cameras.
                # 'inst 3': 'camera3',
                # 'inst 4': 'lowres1',
                },
            'settings': {
			    'latitude_offset': 0.0,     #Decimal degrees, North is Positive. These *could* be slightly different than site.
			    'longitude_offset': 0.0,    #Decimal degrees, West is negative
			    'elevation_offset': 0.0,    # meters above sea level
                'home_park_altitude': 0,    #Having these settings is important for PWI4 where it can easily be messed up.
                'home_park_azimuth': 180,                
                'home_altitude': 60,    #Having these settings is important for PWI4 where it can easily be messed up.
                'home_azimuth': 359,
                'fixed_screen_azimuth': 167.25,
                'fixed_screen _altitude': 0.54,
                'refraction_on': True,
                'model_on': True,
                'rates_on': True,
                'horizon':  20,
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
                     '360': 32,
                     },
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

    'telescope': {
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            #'desc':  'Planewave_CDK_14_F7.2',
            'telescop': 'mrc1',   #  The tenth telescope at mrc will be 'mrc10'. mrc2 already exists.
                                  # the important thing is sites contain only a to z, but the string may get longer.
                                  #  From the BZ perspective TELESCOP must be unique
            'ptrtel': 'Planewave CDK 0.35m f7.2',
            'driver': 'None',                     #Essentially this device is informational.  It is mostly about the optics.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'collecting_area':  76147,    #178*178*math.pi*0.765
            'obscuration':  23.5,
            'aperture': 356,
            'f-ratio':  7.2,   #This and focal_length can be refined after a solve.
            'focal_length': 2563,
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
            'has_cover': False,
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': 0.0,    #  If the mount model is current, these numbers are usually near 0.0
                                              #  for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  #  new terms.
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
            'driver': 'ASCOM.AltAzDS.Rotator',
            'com_port':  None,
            'minimum': -180.0,
            'maximum':360.0,
            'step_size':  0.0001,
            'backlash':  0.0,
            'unit':  'degree',
            'has_rotator': True   #Indicates to camera and Project to include rotation box.
            },

    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'Optec Alnitak 24"',
            'driver': 'COM13',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
            'com_port': 'COM10',
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
            'start_at_config_reference': False,
            'use_focuser_temperature': True,
            #*********Guesses   7379@10 7457@20  7497 @ 25
            #'reference': 7250, #20221103    #7418,    # Nominal at 15C Primary temperature, in microns not steps. Guess
            'reference': 7250, #20221103    #7418,    # Nominal at 15C Primary temperature, in microns not steps. Guess
            'ref_temp':  10,      # Update when pinning reference  Larger at lower temperatures.
            'coef_c': -8.583,    # Negative means focus moves out (larger numerically) as Primary gets colder
            #'coef_0': 7250,  #20221103# Nominal intercept when Primary is at 0.0 C.
            'coef_0': 7355,  #20221103# Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '20230220',   #A Guess as to coef_c
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20221002',   # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            'use_local_temp':  True,
            'minimum': 0,    # NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'step_size': 1,
            'backlash':  0,
            'throw' : 250,
            'unit': 'micron',
            'unit_conversion':  9.09090909091,  # Taken from Gemini at mid-range.
            'has_dial_indicator': False
            },


    },
    'selector': {
        'selector1': {
            'parent': 'telescope1',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': None,
            'com_port': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 1,
            'instruments':  ['Main_camera'], #, 'eShel_spect', 'planet_camera', 'UVEX_spect'],
            'cameras':  ['camera_1_1'], # , 'camera_1_2', None, 'camera_1_4'],
            'guiders':  [None], # , 'guider_1_2', None, 'guide_1_4'],
            'default': 0
            },

    },
    #Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": "Maxim.CCDCamera",  #'ASCOM.FLI.FilterWheel',   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],   #"Maxim",   #"Maxim.CCDCamera",  #
            #"driver":   'ASCOM.FLI.FilterWheel',   #  NB THIS IS THE NEW DRIVER FROM peter.oleynikov@gmail.com  Found in Kepler ASCOM section
            "dual_wheel": True,
            
            
            # WER - if there is no filter wheel, then these two are used, otherwise they are harmless
            "name" : "RGGB",
            #'flat_sky_gain' : 1148,
            #'driver' : None <------ set driver to None for no filter wheel
            
            
            
            
            
            # "parent": "telescope1",
            # "alias": "CWL2",
            # "desc":  'PTR Custom FLI dual wheel.',
            #"driver": ['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],   #  'ASCOM.QHYFWRS232.FilterWheel',  #"Maxim",   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],
            'ip_string': "",
            'settings': {
                #'filter_count': 23,
                #'home_filter':  2,
                'default_filter':  'w',
                
                'auto_color_options' : ['OSC'], # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
                'mono_RGB_colour_filters' : ['pb','pg','pr'], # B, G, R filter codes for this camera if it is a monochrome camera with filters
                'mono_RGB_relative_weights' : [1.2,1,0.8],
                'mono_Narrowband_colour_filters' : ['ha','o3','s2'], # ha, o3, s2 filter codes for this camera if it is a monochrome camera with filters
                'mono_Narrowband_relative_weights' : [1.0,2,2.5],
                
                #'filter_reference': 2,
                


                #'filter_list': ['PL','PR','PG','PB','HA','O3','S2', 'air','dif','w','CR','N2','up','gp','rp','ip','z', 'difup','difgp','difrp','difip','dark'], # A list of actual physical filters for the substitution function

                'filter_data': [['air',     [0, 0], -1000,  20.00, [2, 17], 'ai'], #  0 357
                                ['dif',     [4, 0],     0,  16.00, [2, 17], 'df'], #  1  330NB NB NB If this in series should change focus about 1mm more.
                                ['w',       [2, 0],     0,  17.468, [2, 17], 'w '], #  2 346
                                ['PL',      [0, 4],     0,  16.00, [2, 17], "PL"], #  3 317
                                ['gp',      [0, 6],     0,  14.87, [2, 17], 'gp'], #  4 
                                ['PB',      [0, 1],     0,  10.25, [2, 17], 'PB'], #  5
                                ['rp',      [0, 7],     0,  3.853,  [2, 17], 'rp'], #  6
                                ['PG',      [0, 2],     0,  11.048, [2, 17], 'PG'], #  7
                                ['PR',      [0, 3],     0,  1.336, [2, 17], 'PR'], #  8
                                ['ip',      [0, 8],     0,  4.741, [2, 17], 'ip'], #  9
                                ['z',       [5, 0],     0,  2.147,  [2, 17], 'z' ], # 10
                                ['O3',      [7, 0],     0,  1.151,  [2, 17], '03'], # 11
                                ['up',      [0, 5],     0,  1.506,  [1, 17], 'up'], # 12
                                ['N2',      [3, 0],     0,  0.126,  [2, 17], 'N2'], # 13
                                ['CR',      [1, 0],     0,  0.2,  [2, 17], 'CR'], # 14
                                ['S2',      [8, 0],     0,  0.137,  [2, 17], 'S2'], # 15   
                                ['HA',      [6, 0],     0,  0.124,  [2, 17], 'HA'], # 16  
                                ['focus',   [2, 0],     0,  16.0,  [2, 17], 'fo'], # 17
                                ['dark',    [8, 5],     0,   0.0,  [2, 17], 'dk']],# 18

                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  ['air','w','PL','gp','PB','rp','PG','PR','ip','O3','N2','CR','S2','HA'],   #  9, 21],  # 5, 17], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.

                #'filter_sky_sort':     ['HA', 'S2', 'CR', 'N2', 'O3', 'PR', 'PG', 'PB', 'w', 'air']  #Least to most throughput  \
                # Temporary MTF filter-sky-sort to get OSC flats ... if after March 23 return to above
                'filter_sky_sort':     [ 'S2', 'N2', 'O3', 'HA', 'z', 'PR', 'PG', 'PB', 'gp','rp','ip', 'w','PL', 'focus', 'air']  #Least to most throughput  \
                #'filter_sky_sort':     [  'PB', 'gp','rp','ip', 'w','PL', 'focus', 'air']  #Least to most throughput  \

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



    # A site may have many cameras registered (camera1, camera2, camera3, ...) each with unique aliases -- which are assumed
    # to be the name an owner has assigned and in principle that name "kb01" is labeled and found on the camera.  Between sites,
    # there can be overlap of camera names.  LCO convention is letter of cam manuf, letter of chip manuf, then 00, 01, 02, ...
    # However this code will treat the camera name/alias as a string of arbitrary length:  "saf_Neyle's favorite_camera" is
    # perfectly valid as an alias.


    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'sq001cs',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600C Pro',
            #'driver':  "ASCOM.QHYCCD_CAM2.Camera", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            
            
            
            'detector':  'Sony IMX455 Color',  #  It would be good to build out a table of chip characteristics
            'use_file_mode':  False,   # NB we should clean out all file mode stuff.
            'file_mode_path':  'Q:/archive/sq01/maxim/',   #NB NB all file_mode Maxim stuff should go!
            'manufacturer':  "QHY",
            'settings': {
                
                'hold_flats_in_memory': False, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.


                
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
                
                'is_osc' : True,
                

                
                'squash_on_x_axis' : True,
                
                
                
                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.                
                'interpolate_for_focus': False,
                'bin_for_focus' : True, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'interpolate_for_sep' : False,
                'bin_for_sep' : True, # This setting will bin the image for SEP photometry rather than interpolating.
                'bin_for_platesolve' : True, # This setting will bin the image for platesolving rather than interpolating.
                
                
                # 'osc_brightness_enhance' : 1.0,
                # 'osc_contrast_enhance' : 1.3,
                # 'osc_saturation_enhance' : 2.0,
                # 'osc_colour_enhance' : 1.5,
                # 'osc_sharpness_enhance' : 1.5,
                'osc_brightness_enhance' : 1.0,
                'osc_contrast_enhance' : 1.5,
                'osc_saturation_enhance' : 2.5,
                'osc_colour_enhance' : 1.7,
                'osc_sharpness_enhance' : 1.5,                
                'osc_background_cut' : 25.0,
                'bin_for_focus' : True, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                
                # ONLY TRANSFORM THE FITS IF YOU HAVE
                # A DATA-BASED REASON TO DO SO.....
                # USUALLY TO GET A BAYER GRID ORIENTATED CORRECTLY
                # ***** ONLY ONE OF THESE SHOULD BE ON! *********
                'transpose_fits' : False,
                'flipx_fits' : False,
                'flipy_fits' : False,
                'rotate180_fits' : False, # This also should be flipxy!
                'rotate90_fits' : False,
                'rotate270_fits' : False,
                
                # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
                # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
                # RECOMMENDED DEFAULT DESIRE OF PTR
                'transpose_jpeg' : False,
                'flipx_jpeg' : False,
                'flipy_jpeg' : False,
                'rotate180_jpeg' : False,
                'rotate90_jpeg' : False,
                'rotate270_jpeg' : False,
                
                
               # For large fields of view, crop the images down to solve faster.                 
               # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
               # Probably also similar for platesolving.
               # for either pointing or platesolving even on more modest size fields of view. 
               # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
               # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless 
               # you clearly need to. 
               'focus_image_crop_width': 0.0, # For excessive fields of view, to speed things up crop the image to a fraction of the full width    
               'focus_image_crop_height': 0.0, # For excessive fields of view, to speed things up crop the image to a fraction of the full height
               # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE                
               'platesolve_image_crop': 0.0, # Platesolve crops have to be symmetrical 
               # Really, the SEP image should not be cropped unless your field of view and number of sources
               # Are taking chunks out of the processing time. 
               'sep_image_crop_width': 0.0, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
               'sep_image_crop_height': 0.0, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
               
               
                
                'osc_bayer' : 'RGGB',
                'crop_preview': False,
                # 'crop_preview_ybottom': 2,  #  2 needed if Bayer array
                # 'crop_preview_ytop': 2,
                # 'crop_preview_xleft': 2,
                # 'crop_preview_xright': 2,
                'crop_preview_ybottom': 2,  #  2 needed if Bayer array
                'crop_preview_ytop': 2,
                'crop_preview_xleft': 2,
                'crop_preview_xright': 2,
                'temp_setpoint': -5,    #Verify we can go colder, this system has a chiller
                'has_chiller': True,
                'calib_setpoints': [-20, -20, -20, -20, -20, -20, \
                                    -20, -20, -20, -20, -20, -20],  #  Picked by month-of-year 
                'day_warm': False,
                'day_warm_degrees' : 8, # Number of degrees to warm during the daytime.
                'cooler_on': True,
                "cam_needs_NumXY_init": True,
                'x_start':  0,
                #'x_start':  24,
                'y_start':  0,
                'x_width':  9576,   #NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  6388,
                'x_chip':  9576,   #NB Should specify the active pixel area.   20200315 WER
                'y_chip':  6388,
                'x_trim_offset':  8,   #  NB these four entries are guesses.
                'y_trim_offset':  8,
                'pre_bias_available': False,  #if so need to specify as below for post_bias.
                'post_bias_available': True,  #if so need to specify as below for post_bias.
                'x_bias_start':  9577,
                'y_bias_start' : 6389,
                'x_bias_end':  None,       # Vert band self.img[-38:-18, 0]
                'y_bias_send': None,
                'corner_everlap': None,
                'x_bias_line': True,
                'y_bias_line': True,
                'x_active': 9576,
                'y_active': 6388,
                'det_size': '[1:9600, 1:6422]',  # Physical chip data size as returned from driver
                'ccd_sec': '[1:9600, 1:6422]',
                'bias_sec': ['[1:22, 1:6388]', '[1:11, 1:3194]', '[1:7, 1:2129]', '[1:5, 1:1597]'],
                'det_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                'pix_scale': 0.302597,    #   bin-2  2* math.degrees(math.atan(3.76/2563000))*3600

                'CameraXSize' : 9600,
                'CameraYSize' : 6422,
                'StartX' : 1,
                'StartY' : 1,


                'x_field_deg': 0.8042,  #  round(4784*0.605194/3600, 4),   #48 X 32 AMIN  3MIN X 0.5 DEG
                'y_field_deg': 0.5369,  #  round(3194*0.605194/3600, 4),
                'area_sq_deg':  0.4318, 
                'overscan_x': 24,
                'overscan_y': 34,
                'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.0001,
                'min_flat_exposure' : 3.0, # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'max_flat_exposure' : 20.0, # Realistically there should be a maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_exposure': 180.,
                'max_daytime_exposure': 0.0001,
                'can_subframe':  True,
                'min_subframe': [128,128],
                'bin_modes':  [['Optimal', 0.91], ['Fine', 0.61], ['Coarse', 1.2], ['Eng', 0.30]],     #Meaning fixed binning if list has only one entry
                'reference_gain': 1.3,     #  NB GUess One val for each binning. Assumed digitalsumming in camera???
                'reference_noise': 6,    #  NB Guess
                'reference_dark': 0.2,  #  NB  Guess
                'reference_offset': 611, #  NB Guess  ADU vaules not times in sec.
                'fullwell_capacity': 80000,   #  NB Guess
                'bin-desc':              ['1x1', '2x2', '3x3', '4x4' ],
                'chan_color':            ['col', 'gry', 'gry', 'gry' ],
                #'cycle_time':            [ 18,    13,    15,    12   ],   # NB somewhat a Guess.
                'cycle_time':            0,   # Meas 20230219  for a bias
                #'enable_bin':            [ True, False,  False,  False],
                #'bias_dark_bin_spec':    ['1,1', '2,2', '3,3', '4,4' ],    #Default binning for flats
                'number_of_bias_to_collect' : 63,
                'number_of_dark_to_collect' : 17,
                'number_of_flat_to_collect' : 10,
                'number_of_bias_to_store' : 128,
                'number_of_dark_to_store' : 128,
                'number_of_flat_to_store' : 128,
 
                'dark_exposure': 360,
                #'flat_bin_spec':         ['1,1', '2,2', '3,3', '4,4' ],   #Is this necessary?

                #'flat_count': 5,
                'optimal_bin': [1, 1],   #  This is the optimal bin for MRC
                'fine_bin':    [1, 1],   #  This is the fine bin for MRC
                'coarse_bin':  [2, 2],   #  This is the coarse bin for MRC
                'eng_bin':     [4, 4],   #  This is the eng-only bin for MRC, not useful for users?
                'bin_enable':  ['1 1'],  #  Always square and matched to seeing situation by owner  NB Obsolete? NO MF uses to load bias calib
                                         #  NB NB inconsistent use of bin string   '1 1', '1x1' , etc.
                'do_cosmics' : False,
                
                'rbi_delay':  0,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color': True,   #NB we also have a is_osc key.
                'can_set_gain':  True,
                'max_linearity':  60000,   # Guess

                'flat_count': 5,

                'saturate':   65535 ,    #[[1, 65000], [2,262000], [3,589815], [4, 1048560]] ,   # e-.  This is a close guess, not measured, but taken from data sheet.
                'fullwell_capacity':  80000,

                'read_mode':  'Normal',
                'readout_mode': 'Normal',
                'readout_speed':  50,
                'readout_seconds': 6,
                'smart_stack_exposure_time': 30,
                'square_detector': False,
                'square_pixels': True,
                'areas_implemented': ['Big sq.', 'Full', 'Small sq.', '70.7%', '50%', '35%', '25%', '18%' ],   #0.5*0.5°',  '0.7x0.7°', '1x1°', '1.4x1.4°', '2x2°', '2.8x2.8°', '4x4sq°', '5.6x5.6°'],
                'default_area':  "Full",
                'default_rotation': 0.0000,

                #'flat_bin_spec': ['1 1', '2 2'],    # List of binnings for flats.  NB NB NB Note inconsistent use of '1 1' and '1x1' and '1,1'

                'has_darkslide':  True,
                'darkslide_com':  'COM15',
                'shutter_type': "Electronic",
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #  'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
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
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
        },
    },
    #As aboove, need to get this sensibly suported on GUI and in fits headers.


    #Need to put switches here for above devices.

    #Need to build instrument selector and multi-OTA configurations.

    #AWS does not need this, but my configuration code might make use of it. VALENTINA this device will probably
    #alwys be custom per installation. In my case Q: points to a 40TB NAS server in the basement. WER
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
}    #This brace closes the while configuration dictionary. Match found up top at:  site_config = {

#def get_ocn_status():    #NB NB I think we should get rid of these two dummy methods. WER
#    pass
#def get_enc_status():
#    pass

'''
Here we create the basic directory structures needed for this respective 
site, telescope and instruments.
''' 


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