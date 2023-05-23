
# -*- coding: utf-8 -*-
'''
Created on Fri Feb 07,  11:57:41 2020
20220902  Update for status corruption incident.  This worked today.

@author: wrosing
'''
#                                                                                        1         1         1       1
#        1         2         3         4         6         7         8         9         0         1         2       2
#234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
#import json

#import time

#import ptr_events
#from pprint import pprint

#  NB NB  Json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.
#  NB NB  My convention is if a value is naturally a float I add a decimal point even to 0.


 # bolt = ['u', 'g', 'r', 'i', 'zs', 'B', 'V', 'EXO', 'w', 'O3', 'Ha', 'S', 'Cr', 'NIR']
 # print(len(bolt))

site_name = 'eco'
obs_id = 'eco2'
                    #\\192.168.1.57\SRO10-Roof  r:
                    #SRO-Weather (\\192.168.1.57) w:
                    #Username: wayne_rosingPW: 29yzpe

site_config = {
    # THESE ARE TO BE DELETED VERY SOON!
    # THEY EXIST SOLELY SO AS TO NOT BREAK THE UI UNTIL 
    #THINGS ARE MOVED TO OBS_ID
    'site': 'eco2', #TIM this may no longer be needed.
    'site_id': 'eco2',
    ####################################################
    'obs_id': 'eco2',
    'observatory_location': site_name.lower(),
    
    'debug_site_mode': False,
    

    'debug_mode': False,
    'admin_owner_commands_only': False,

    'debug_duration_sec': 7200,
    'owner':  ['google-oauth2|112401903840371673242'],  # WER,  Or this can be
                                                        # some aws handle.
    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "KVH", "TELOPS", "TB", "DH", 'KC'],

    'client_hostname':  'ECO-0m28-OSC',
    'client_path':  'C:/ptr/',  # Generic place for this host to stash misc stuff
    'alt_path':  'C:/ptr/',  # Generic place for this host to stash misc stuff
    'save_to_alt_path' : 'no',
    'archive_path':  'C:/ptr/',  # Meant to be where /archive/<camera_id> is added by camera.
    'local_calibration_path': 'C:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    
    'archive_age' : 2.0, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'send_files_at_end_of_night' : 'no', # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'save_raw_to_disk' : False, # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.    
    'keep_focus_images_on_disk' : False, # To save space, the focus file can not be saved.
    'keep_reduced_on_disk' : False, # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    
    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing' : 1.2,
    
    'aux_archive_path':  None, # '//house-computer/saf_archive_2/archive/',  #  Path to auxillary backup disk.
    'wema_is_active':  False,    #True if split computers used at a site.
    'wema_hostname':  [],  #  Prefer the shorter version
    'dome_on_wema': False, #  Implying enclosure controlled by client.
    'site_IPC_mechanism':  None,   # ['None', 'shares', 'redis']  Pick One
    'wema_write_share_path':  None,   # This and below provide two different ways to define
    'client_read_share_path':  None,  #     a path to a network share.
    'redis_ip': None,  #'127.0.0.1', None if no redis path present,
    'obsid_is_generic':  True,   # A simple single computer ASCOM site.
    'obsid_is_specific':  False,  # Indicates some special code for this site, found at end of config.
    'home_altitude' : 70,
    'home_azimuth' : 160,

    'host_wema_site_name':  'EC2',  #  The umbrella header for obsys in close geographic proximity.
    'name': 'Eltham College Observatory, 0m28',
    'airport_code':  'MEL: Melbourne Airport',
    'location': 'Eltham, Victoria, Australia',
    'telescope_description': 'n.a.',
    'observatory_url': 'https://elthamcollege.vic.edu.au/',   #  This is meant to be optional
    'observatory_logo': None,   # I expect these will ususally end up as .png format icons
    'description':  '''Eltham College is an independent, non-denominational, co-educational day school situated in Research, an outer suburb north east of Melbourne.
                    ''',    #  i.e, a multi-line text block supplied and eventually mark-up formatted by the owner.
    'location_day_allsky':  None,  #  Thus ultimately should be a URL, probably a color camera.
    'location_night_allsky':  None,  #  Thus ultimately should be a URL, usually Mono camera with filters.
    'location _pole_monitor': None,  #This probably gets us to some sort of image (Polaris in the North)
    'location_seeing_report': None,  # Probably a path to a jpeg or png graph.

    'TZ_database_name':  'Australia/Melbourne',
    'mpc_code':  'ZZ23',    #  This is made up for now.
    'time_offset':  11,   #  These two keys may be obsolete given the new TZ stuff
    'timezone': 'AEST',      #  This was meant to be coloquial Time zone abbreviation, alternate for "TX_data..."
    'latitude': -37.70097222,     #  Decimal degrees, North is Positive
    'longitude': 145.1918056,   #  Decimal degrees, West is negative
    'elevation': 150,    #  meters above sea level
    'reference_ambient':  10,  #  Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  867.254,    #mbar   A rough guess 20200315

    'obsid_roof_control': True, #MTF entered this in to remove sro specific code.... Basically do we have control of the roof or not see line 338 sequencer.py
    'obsid_allowed_to_open_roof': True,
    'period_of_time_to_wait_for_roof_to_open' : 100, # seconds - needed to check if the roof ACTUALLY opens. 
    'only_scope_that_controls_the_roof': False, # If multiple scopes control the roof, set this to False
    
    
    'check_time': 300,   #MF's original setting.
    
    'maximum_roof_opens_per_evening' : 4,
    
    'roof_open_safety_base_time' : 15, # How many minutes to use as the default retry time to open roof. This will be progressively multiplied as a back-off function.
    
    'closest_distance_to_the_sun': 45, # Degrees. For normal pointing requests don't go this close to the sun. 
    'closest_distance_to_the_moon': 10, # Degrees. For normal pointing requests don't go this close to the moon. 
    'lowest_requestable_altitude': -5, # Degrees. For normal pointing requests don't allow requests to go this low. 
    'obsid_in_automatic_default': "Automatic",   #  ["Manual", "Shutdown", "Automatic"]
    'automatic_detail_default': "Enclosure is initially set to Automatic mode.",
    'observing_check_period' : 5,    # How many minutes between weather checks
    'enclosure_check_period' : 5,    # How many minutes between enclosure checks
    'auto_eve_bias_dark': False,
    'auto_midnight_moonless_bias_dark': False,
    'auto_eve_sky_flat': True,

    'eve_sky_flat_sunset_offset': +20.0,  #  Minutes  neg means before, + after.
    'eve_cool_down_open' : -60.0,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': False,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,
    'periodic_focus_time' : 0.5, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm' : 0.5, # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'pointing_exposure_time': 20, # Exposure time in seconds for exposure image
    'focus_exposure_time': 15, # Exposure time in seconds for exposure image

    'focus_trigger' : 5.0, # What FWHM increase is needed to trigger an autofocus
    'solve_nth_image' : 1, # Only solve every nth image
    'solve_timer' : 5, # Only solve every X minutes
    'threshold_mount_update' : 50, # only update mount when X arcseconds away

    'defaults': {
        'observing_conditions': 'observing_conditions1',  #  These are used as keys, may go away.
        'enclosure': 'enclosure1',
        'screen': 'screen1',
        'mount': 'mount1',
        'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector': None,
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
            'observing_conditions',
            'enclosure',
            'mount',
            'telescope',
            #'screen',
            #'rotator',
            'focuser',
            'selector',
            'filter_wheel',
            'camera',
            'sequencer'
            ],
    'wema_types': [                                      # or site_specific types.
            'observing_conditions1',
            'enclosure1'
            ],
    'enc_types': [
            'enclosure'
            ],
    'short_status_devices': [
            'observing_conditions',
            'enclosure',
            'mount',
            'telescope',
            'screen',
            'rotator',
            'focuser',
            'selector',
            'filter_wheel',
            'camera',
            'sequencer'
            ],
    'observing_conditions' : {
        'observing_conditions1': {
            'parent': 'site',
            'ocn_is_specific':  False,  # Indicates some special site code.
            # Intention it is found in this file.
            'name': 'SRO File',
            'driver': None,  # Could be redis, ASCOM, ...
            'share_path_name': 'F:/ptr/',
            'driver_2':  None,   #' ASCOM.Boltwood.OkToOpen.SafetyMonitor',
            'driver_3':  None,    # 'ASCOM.Boltwood.OkToImage.SafetyMonitor'
            'ocn_has_unihedron':  False,
            'have_local_unihedron': False,     #  Need to add these to setups.
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  10    #  False, None or numeric of COM port.
        },
    },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'enc_is_specific':  False,  # Indicates some special site code.            
            'directly_connected': True, # For ECO and EC2, they connect directly to the enclosure, whereas WEMA are different.
            'name': 'Dragonfly Roof',
            'hostIP':  None,
            'driver': 'Dragonfly.Dome',  #'ASCOM.DigitalDomeWorks.Dome',  #  ASCOMDome.Dome',  #  ASCOM.DeviceHub.Dome',  #  ASCOM.DigitalDomeWorks.Dome',  #"  ASCOMDome.Dome',
            'has_lights':  False,
            'controlled_by': 'mount1',
            'is_dome': False,
            'mode': 'Automatic',
            #'cool_down': -90.0,    #  Minutes prior to sunset.
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
            },
            #'eve_bias_dark_dur':  2.0,   #  hours Duration, prior to next.
            #'eve_screen_flat_dur': 1.0,   #  hours Duration, prior to next.
            #'operations_begin':  -1.0,   #  - hours from Sunset
            #'eve_cooldown_offset': -.99,   #  - hours beforeSunset
            #'eve_sky_flat_offset':  0.5,   #  - hours beforeSunset
            #'morn_sky_flat_offset':  0.4,   #  + hours after Sunrise
            #'morning_close_offset':  0.41,   #  + hours after Sunrise
            #'operations_end':  0.42,
        },
    },



    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'tel_id': '0m40',
            'name': 'ecocdkpier',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'ecocdkpier',
            'desc':  'Paramount MX+',
            'driver': 'ASCOM.SoftwareBisque.Telescope',
            'alignment': 'Equatorial',
            'default_zenith_avoid': 0.0,   #degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            'has_ascom_altaz': False,
            'pointing_tel': 'tel1',     #This can be changed to 'tel2'... by user.  This establishes a default.
            'west_clutch_ra_correction':  0.0, #
            'west_clutch_dec_correction': 0.0, #
            'east_flip_ra_correction':  0.0, #
            'east_flip_dec_correction': 0.0,  #  #
            'home_after_unpark' : True,
            
            'home_before_park' : True,
            'permissive_mount_reset' : 'yes', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'lowest_acceptable_altitude' : -7.0, # Below this altitude, it will automatically try to home and park the scope to recover.
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            'settings': {
			    'latitude_offset': 0.0,     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': 0.0,   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': 0.0,    # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 270.,

                'home_altitude' : 70,
                'home_azimuth' : 160,

                'horizon':  15.,    #  Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  #  Meant to be something to draw on the Skymap with a spline fit.
                     '0.1': 10,
                     ' 90': 10,
                     '180': 10,
                     '270': 10,
                     '360': 10
                     },  #  We use a dict because of fragmented azimuth mesurements.
                'refraction_on': True,
                'model_on': True,
                'rates_on': True,
                'model': {
                    'IH': 0.0,
                    'ID': 0.0,
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

    'telescope': {                            #Note telescope == OTA  Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'telescop': 'eco2',
            'ptrtel': 'RASA11',
            'desc':  'RASA11',
            'driver': None,                     #  Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 55381,
            'obscuration':  23.7,   #  %
            'aperture': 432,
            'focal_length': 2939,
            'has_dew_heater':  True,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   #This is a default for a single instrument system
            'selector_positions': 1,            #Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['ASI071MCPro'],
            'configuration': {
                 "position1": ["darkslide1", "filter_wheel1", "camera1"]
                 },
            'camera_name':  'camera1',
            #'filter_wheel_name':  'filter_wheel1',
            'filter_wheel_name':  None,
            'has_fans':  False,
            'has_cover':  False,
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
            'desc':  False,
            'driver': None,
			'com_port':  False,
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
            'desc':  'No Screen',
            'driver': None,
            'com_port': 'COM10',  #  This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
            'minimum': 5,   #  This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 255,  #  Out of 0 - 255, this is the last value where the screen is linear with output.
                              #  These values have a minor temperature sensitivity yet to quantify.


        },
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Planewave Focuser',
            #'driver': 'ASCOM.SeletekFocuser.Focuser',
            'driver': 'SeletekFocuser.Focuser',
			'com_port':  'COM9',
            #F4.9 setup
            'start_at_config_reference': True,
            'use_focuser_temperature': False,
            'reference':12050,    #  20210313  Nominal at 10C Primary temperature
            'ref_temp':  12050.0,    #  Update when pinning reference
            'coef_c': 0,   #  Negative means focus moves out as Primary gets colder
            'coef_0': 12050,  #  Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '20220914',    #This appears to be sensible result 44 points -13 to 3C'reference':  6431,    #  Nominal at 10C Primary temperature
            # #F9 setup
            # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            # 'ref_temp':  27.,    #  Update when pinning reference
            # 'coef_c': -78.337,   #  negative means focus moves out as Primary gets colder
            # 'coef_0': 5969,  #  Nominal intercept when Primary is at 0.0 C.
            # 'coef_date':  '20210903',    #  SWAG  OLD: This appears to be sensible result 44 points -13 to 3C
            'minimum': 0,     #  NB this area is confusing steps and microns, and need fixing.
            'maximum': 18000,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'throw' : 200,
            'unit': 'micron',
            #'unit_conversion': 9.09090909091,
            'unit_conversion': 1.0,
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

    #'filter_wheel': {        
        # "filter_wheel1": {
        #     "parent": "telescope1",
        #     "name": "SBIG 8-position wheel" ,  #"LCO filter wheel FW50_001d",
        #     'service_date': '20180101',
        #     "driver":   "CCDSoft2XAdaptor.ccdsoft5Camera",   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
        #     #"driver":   "Maxim.Image",   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
        #     'ip_string': None,
        #     "dual_wheel": False,
        #     'settings': {
        #         'filter_count': 11,   #  This must be correct as to the number of filters
        #         'home_filter':  0,
        #         'default_filter': "PL",
        #         'filter_list': ['focus','PL','PR','PG','PB','HA','O3','S2', 'air'], # A list of actual physical filters for the substitution function
        #         'filter_reference': 0,   #  We choose to use W as the default filter.  Gains taken at F9, Ceravolo 300mm
        #         'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'alias'],  #NB NB NB add cwl & bw in nm.

        #                 #['w',     [0,  0],     0, 72.7, [1.00 ,  72], 'PL'],    #0.   For sequencer autofocus  consider foc or f filter
        #                 ['focus', [3,  3],     0, 72.7, [1.00 ,  72], 'focus'],    #0.
        #                 ['air',    [0,  0],     0, 620, [1.00 ,  72], 'PhLum'],    #1.
        #                 ['dark',    [1,  1],     0, 170, [1.00 , 119], 'PhRed'],    #2.
        #                 ['PB',    [2,  2],     0, 220, [1.00 , 113], 'PhGreen'],    #3.
        #                 ['PG',    [3,  3],     0, 300, [0.80 ,  97], 'PhBlue'],    #4.
        #                 ['PR',    [4,  4],     0, 300, [0.80 ,  97], 'PhBlue'],    #4.
        #                 #['PR',    [1,  1],     0, 170, [1.00 , 119], 'PhBlue'],    #2.
        #                 #['PG',    [2,  2],     0, 220, [1.00 , 113], 'PhGreen'],    #3.
        #                 #['PB',    [3,  3],     0, 300, [0.80 ,  97], 'PhRed'],    #4.
        #                 ['HA',    [5,  5],     0, .400, [5.00 , 200], 'Halpha'],    #5.
        #                 ['O3',    [6,  6],     0, 6, [4.00 , 200], 'OIII'],    #6.
        #                 ['S2',    [7,  7],     0, .221, [10.0,  200], 'SII']],    #7.
        #                 #['air',   [7,  7], -1000, 100., [1.00,   70], 'air'],    #8.
        #                 #['gooble',  [6,  6],     0, .221, [   0,    0], 'dark'],   #9.
        #                 #['LRGB',  [0,  0],     0, .221, [   0,    0], 'LRGB']],   #10.


        #         'filter_screen_sort':  [1, 4, 3, 2, 6, 5, 7],   #  don't use narrow yet,  8, 10, 9], useless to try.


        #         'filter_sky_sort': [6, 4, 5, 1, 2, 3,  0]    #No diffuser based filters
        #         #'filter_sky_sort': [7, 19, 2, 13, 18, 5, 15,\
        #         #                    12, 4, 11, 16, 10, 9, 17, 3, 14, 1, 0]    #basically no diffuser based filters
        #         #[32, 8, 22, 21, 20, 23, 31, 6, 7, 19, 27, 2, 37, 13, 18, 30, 5, 15, 36, 12,\
        #          #                   29, 4, 35, 34, 11, 16, 10, 33, 9, 17, 28, 3, 26, 14, 1, 0]


        #     },
        #},

    'filter_wheel': {        
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "RGGB" ,  # When there is no filter wheel, the filter will be named this.
            'service_date': '20180101',
            
            "filter_settle_time": 0, #how long to wait for the filter to settle after a filter change(seconds)

            'flat_sky_gain' : 900,

            "driver":   None,   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
            #"driver":   "Maxim.Image",   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
            'settings': {'auto_color_options' : ['none']}, # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
            'ip_string': None,
            "dual_wheel": False,
            #"default_flat_exposure" : 1.0,
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

    # 'camera': {
    #     'camera_1_1': {
    #         'parent': 'telescope1',
    #         'name': 'ec002ms',      #  Important because this points to a server file structure by that name.
    #         'desc':  'ZWOASI071MCPro',
    #         'service_date': '20211111',
    #         'driver': "CCDSoft2XAdaptor.ccdsoft5Camera",  # "ASCOM.QHYCCD.Camera", ##  'ASCOM.FLI.Kepler.Camera',
    #         'detector':  'ASI',
    #         'manufacturer':  'On-Semi',
    #         'use_file_mode':  False,
    #         'file_mode_path':  'G:/000ptr_saf/archive/sq01/autosaves/',   #NB Incorrect site, etc. Not used at SRO.  Please clean up.
            

    #         'settings': {
    #             'is_osc' : True,
                
    #             'squash_on_x_axis' : True,
    #             'osc_brightness_enhance' : 1.0,
    #             'osc_contrast_enhance' : 1.3,
    #             'osc_saturation_enhance' : 2.0,
    #             'osc_colour_enhance' : 1.5,
    #             'osc_sharpness_enhance' : 1.5,
    #             'osc_background_cut' : 25.0,
    #             'bin_for_focus' : False, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6. It is also a little faster. Not good for blockier pixel scales
                
    #             # ONLY TRANSFORM THE FITS IF YOU HAVE
    #             # A DATA-BASED REASON TO DO SO.....
    #             # USUALLY TO GET A BAYER GRID ORIENTATED CORRECTLY
    #             # ***** ONLY ONE OF THESE SHOULD BE ON! *********
    #             'transpose_fits' : False,
    #             'flipx_fits' : False,
    #             'flipy_fits' : False,
    #             'rotate180_fits' : False, # This also should be flipxy!
    #             'rotate90_fits' : False,
    #             'rotate270_fits' : False,
                
    #             # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
    #             # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
    #             # RECOMMENDED DEFAULT DESIRE OF PTR
    #             'transpose_jpeg' : False,
    #             'flipx_jpeg' : False,
    #             'flipy_jpeg' : False,
    #             'rotate180_jpeg' : False,
    #             'rotate90_jpeg' : False,
    #             'rotate270_jpeg' : False,
    #             'osc_bayer' : 'RGGB',
    #             'crop_preview': False,
    #             'crop_preview_ybottom': 1,
    #             'crop_preview_ytop': 1,
    #             'crop_preview_xleft': 1,
    #             'crop_preview_xright': 1,
    #             'temp_setpoint': -5,   #Updated from -18 WER 20220914 Afternoon
    #             'calib_setpoints': [-35,-30, -25, -20, -15, -10 ],  #  Should vary with season?
    #             'day_warm': False,
    #             'cooler_on': True,
                
                
    #             "cam_needs_NumXY_init": False,
    #             'x_start':  0,
    #             'y_start':  0,
    #             'x_width':  4500,   #  NB Should be set up with overscan, which this camera is!  20200315 WER
    #             'y_width':  3600,
    #             #Note please add 56 to SBIG Driver Checker 64 Update config for added overscan
    #             'x_chip':  4556,   #  NB Should specify the active pixel area.   20200315 WER
    #             'y_chip':  3656,
    #             'x_trim_offset':  0,   #  NB these four entries are guesses.
    #             'y_trim_offset':  0,
    #             'pre_bias_available': False,  #if so need to specify as below for post_bias.
    #             'post_bias_available': True,  #if so need to specify as below for post_bias.
    #             'x_bias_start':  4520,
    #             'y_bias_start': 3620,
    #             'x_bias_end':  4556,       # Vert band self.img[-38:-18, 0]
    #             'y_bias_send': 3643,
    #             'corner_everlap': True,
    #             'x_bias_line': True,
    #             'y_bias_line': True,
    #             'ref_dark': 60.0,
    #             'long_dark': 600.0,
    #             'x_active': 4500,
    #             'y_active': 3600,
    #             #THIS IS ALL WRONG!
    #             'det_size': '[1:4556, 1:3656]',  # Physical chip data size as returned from driver
    #             'ccd_sec': '[1:4556, 1:3656]',
    #             'bias_sec': ['[1:22, 1:6388]', '[1:11, 1:3194]', '[1:7, 1:2129]', '[1:5, 1:1597]'],
    #             'det_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
    #             'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
    #             'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
    #             'x_pixel':  6,
    #             'y_pixel':  6,
                
    #             'CameraXSize' : 4096,
    #             'CameraYSize' : 4096,
    #             #'MaxBinX' : 2,
    #             #'MaxBinY' : 2,
    #             'StartX' : 1,
    #             'StartY' : 1,

    #             'x_field_deg': 1.3333,   #   round(4784*1.0481/3600, 4),
    #             'y_field_deg': 1.0665,   #  round(3194*1.0481/3600, 4),
    #             'overscan_x': 24,
    #             'overscan_y': 3,
    #             'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
    #             'east_offset': 0.0,     #  Not sure why these three are even here.
    #             'rotation': 0.0,        #  Probably remove.
    #             'min_exposure': 0.02,
                
    #             'min_flat_exposure': 0.02,
    #             'max_exposure': 3600,
    #             'max_daytime_exposure': 0.0001,
    #             'can_subframe':  True,
    #             'min_subframe':  [128, 128],
    #             'bin_modes':  [[1, 1, 1.59]], #  , [2, 2, 2.13], [3, 3, 3.21], [4, 4, 4.27]],   #Meaning no binning choice if list has only one entry, default should be first.
    #             'optimal_bin':  [1, 1, 1.59],    #  Matched to seeing situation by owner
    #             'max_res_bin':  [1, 1, 1.59],    #  Matched to seeing situation by owner
    #             'do_cosmics' : 'no',
    #             'pix_scale': 1.569,
    #             'cycle_time':  2,
    #             'rbi_delay':  0.,      #  This being zero says RBI is not available, eg. for SBIG.
    #             'is_cmos':  True,
    #             'is_color':  True,
    #             'bayer_pattern':  'RGGB',    #  'RGGB" is a valid string in camera is color.
    #             'can_set_gain':  True,
    #             'reference_gain': 2.0,     #  One val for each binning. SWAG!
    #             'reference_noise': 10.0,    #  All SWAGs right now!

    #             'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?  NO!
    #                                 #hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
    #                 #hdu.header['RDOUTM'] = (self.config['camera'][self.name]['readout_mode'], 'Camera readout mode')
    #                 #hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
    #             'read_mode':  'Normal',
    #             'readout_mode':  'Normal',
    #             'readout_speed': 0.4,
    #             'readout_seconds': 2,
    #             'smart_stack_exposure_time' : 10,
    #             'saturate': 65000,    # e-.  This is a close guess, not measured, but taken from data sheet.
    #             'max_linearity': 65000,
    #             'fullwell_capacity': 65000,  #e-.   We need to sort out the units properly NB NB NB
    #             'areas_implemented': ["Full",'4x4d', "600%", "500%", "450%", "300%", "220%", "150%", "133%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
    #             'default_area':  "Full",
    #             'default_rotation': 0.0000,
    #             'has_darkslide':  False,
    #             'darkslide_com':  None,
    #             'flat_bin_spec': ['1,1'],    #Default binning for flats
    #             'bias_dark_bin_spec': ['1,1'],    #Default binning for flats
    #             'bin_enable': ['1 1'],
    #             'dark_length' : 900,
                
    #             'flat_count' : 10,
    #             'bias_count' : 10,
    #             'dark_count' : 10,
                
    #             'shutter_type': "Electronic",
    #             'has_screen': True,
    #             'screen_settings':  {
    #                 'screen_saturation':  157.0,   #  This reflects WMD setting and needs proper values.
    #                 'screen_x4':  -4E-12,  #  'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
    #                 'screen_x3':  3E-08,
    #                 'screen_x2':  -9E-05,
    #                 'screen_x1':  .1258,
    #                 'screen_x0':  8.683
    #             },
    #         },
    #     },

    # },

    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'ec002cs',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600C Pro',
            #'driver':  "ASCOM.QHYCCD_CAM2.Camera", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            
            
            
            
            
            'detector':  'Sony IMX455 Color',  #  It would be good to build out a table of chip characteristics
            'use_file_mode':  False,   # NB we should clean out all file mode stuff.
            'file_mode_path':  'Q:/archive/sq01/maxim/',   #NB NB all file_mode Maxim stuff should go!
            'manufacturer':  "QHY",
            'settings': {
                
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.

                
                
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
                
                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.                
                'interpolate_for_focus': True,
                'bin_for_focus' : False, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'focus_bin_value' : 1,
                'interpolate_for_sep' : False,
                'bin_for_sep' : True, # This setting will bin the image for SEP photometry.
                'sep_bin_value' : 1,
                'bin_for_platesolve' : True, # This setting will bin the image for platesolving.
                'platesolve_bin_value' : 2,
                
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
                # What number of pixels to crop around the edges of a REDUCED image
                # This is primarily to get rid of overscan areas and also all images
                # Do tend to be a bit dodgy around the edges, so perhaps a standard
                # value of 30 is good. Increase this if your camera has particularly bad
                # edges.
                'reduced_image_edge_crop': 30,
                
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
                'focus_image_crop_width': 0.5, # For excessive fields of view, to speed things up crop the image to a fraction of the full width    
                'focus_image_crop_height': 0.5, # For excessive fields of view, to speed things up crop the image to a fraction of the full height
                                
               'focus_jpeg_size': 500, # How many pixels square to crop the focus image for the UI Jpeg
                # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE                
                'platesolve_image_crop': 0.75, # Platesolve crops have to be symmetrical 
                # Really, the SEP image should not be cropped unless your field of view and number of sources
                # Are taking chunks out of the processing time. 
                'sep_image_crop_width': 0.1, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
                'sep_image_crop_height': 0.1, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
                
                'osc_bayer' : 'RGGB',
                'crop_preview': False,
                'crop_preview_ybottom': 2,  #  2 needed if Bayer array
                'crop_preview_ytop': 2,
                'crop_preview_xleft': 2,
                'crop_preview_xright': 2,
                'temp_setpoint': -4,    #Verify we can go colder, this system has a chiller
                'has_chiller': True,
                'calib_setpoints': [-20, -20, -20, -20, -20, -20, \
                                    -20, -20, -20, -20, -20, -20],  #  Picked by month-of-year 
                'day_warm': True,
                'day_warm_degrees' : 6, # Number of degrees to warm during the daytime.
                'cooler_on': True,
                "cam_needs_NumXY_init": True,
                'x_start':  24,
                'y_start':  0,
                'x_width':  9600,   #NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  6422,
                'x_chip':  9600,   #NB Should specify the active pixel area.   20200315 WER
                'y_chip':  6422,
                'x_trim_offset':  8,   #  NB these four entries are guesses.
                'y_trim_offset':  8,
                'pre_bias_available': False,  #if so need to specify as below for post_bias.
                'post_bias_available': True,  #if so need to specify as below for post_bias.
                'x_bias_start':  9600,
                'y_bias_start' : 6422,
                'x_bias_end':  None,       # Vert band self.img[-38:-18, 0]
                'y_bias_send': None,
                'corner_everlap': None,
                'x_bias_line': True,
                'y_bias_line': True,
                'x_active': 9600,
                'y_active': 6422,
                'det_size': '[1:9600, 1:6422]',  # Physical chip data size as returned from driver
                'ccd_sec': '[1:9600, 1:6422]',
                'bias_sec': ['[1:22, 1:6388]', '[1:11, 1:3194]', '[1:7, 1:2129]', '[1:5, 1:1597]'],
                'det_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
                'x_pixel':  3.76, # microns
                'y_pixel':  3.76, # microns
                'pix_scale': 1.25,    #   arcseconds per pixel
                
                '1x1_pix_scale': 1.25,    #  This is the 1x1 binning pixelscale
                'native_bin': 1, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                
                
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.                
                'drizzle_value_for_later_stacking': 0.5,
                

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
                #'bin_modes':  [['Optimal', 0.91], ['Fine', 0.61], ['Coarse', 1.2], ['Eng', 0.30]],     #Meaning fixed binning if list has only one entry
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

                'number_of_bias_to_collect' : 32,
                'number_of_dark_to_collect' : 32,
                'number_of_flat_to_collect' : 10,
                'number_of_bias_to_store' : 32,
                'number_of_dark_to_store' : 32,
                'number_of_flat_to_store' : 32,

 
                'dark_exposure': 20,
                #'flat_bin_spec':         ['1,1', '2,2', '3,3', '4,4' ],   #Is this necessary?

                #'flat_count': 5,
                #'optimal_bin': [1, 1],   #  This is the optimal bin for MRC
                #'fine_bin':    [1, 1],   #  This is the fine bin for MRC
                #'coarse_bin':  [2, 2],   #  This is the coarse bin for MRC
                #'eng_bin':     [4, 4],   #  This is the eng-only bin for MRC, not useful for users?
                'bin_enable':  ['1 1'],  #  Always square and matched to seeing situation by owner  NB Obsolete? NO MF uses to load bias calib
                                         #  NB NB inconsistent use of bin string   '1 1', '1x1' , etc.
                'do_cosmics' : False,
                
                'rbi_delay':  0,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color': True,   #NB we also have a is_osc key.
                'can_set_gain':  True,
                'max_linearity':  80000,   # Guess



                'saturate':   65535 ,    #[[1, 65000], [2,262000], [3,589815], [4, 1048560]] ,   # e-.  This is a close guess, not measured, but taken from data sheet.



                'read_mode':  'Normal',
                'readout_mode': 'Normal',
                'readout_speed':  0.4,
                'readout_seconds': 2.4,
                'smart_stack_exposure_time': 45,
                'square_detector': False,
                'square_pixels': True,
                'areas_implemented': ['Full', 'SQR', '0.5*0.5°',  '0.7x0.7°', '1x1°', '1.4x1.4°', '2x2°', '2.8x2.8°', '4x4sq°', '5.6x5.6°'],
                'default_area':  "Full",
                'default_rotation': 0.0000,

                #'flat_bin_spec': ['1 1', '2 2'],    # List of binnings for flats.  NB NB NB Note inconsistent use of '1 1' and '1x1' and '1,1'

                'has_darkslide':  False,
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


        },
    },

    #  I am not sure AWS needs this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': None,
            'win_url': None,
            'redis':  '(host=none, port=6379, db=0, decode_responses=True)'
        },
    },
}

# def linearize_unihedron(uni_value):
#     #  Based on 20180811 data   --- Highly suspect.  Need to re-do 20210807
#     uni_value = float(uni_value)
#     if uni_value < -1.9:
#         uni_corr = 2.5**(-5.85 - uni_value)
#     elif uni_value < -3.8:
#         uni_corr = 2.5**(-5.15 - uni_value)
#     elif uni_value <= -12:
#         uni_corr = 2.5**(-4.88 - uni_value)
#     else:
#         uni_corr = 6000
#     return uni_corr

# def f_to_c(f):
#     return round(5*(f - 32)/9, 2)
# last_good_wx_fields = 'n.a'
# last_good_daily_lines = 'n.a'
# def get_ocn_status(g_dev=None):
#     global last_good_wx_fields, last_good_daily_lines   # NB NB NB Perhaps memo-ize these instead?
#     if site_config['site'] == 'sro':   #  Belts and suspenders.
#         try:
#             wx = open('W:/sroweather.txt', 'r')
#             wx_line = wx.readline()
#             wx.close
#             #print(wx_line)
#             wx_fields = wx_line.split()
#             skyTemperature = f_to_c(float( wx_fields[4]))
#             temperature = f_to_c(float(wx_fields[5]))
#             windspeed = round(float(wx_fields[7])/2.237, 2)
#             humidity =  float(wx_fields[8])
#             dewpoint = f_to_c(float(wx_fields[9]))
#             #timeSinceLastUpdate = wx_fields[13]
#             open_ok = wx_fields[19]
#             #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
#             #self.focus_temp = temperature
#             last_good_wx_fields = wx_fields
#         except:
#             time.sleep(5)
#             try:

#                 wx = open('W:/sroweather.txt', 'r')
#                 wx_line = wx.readline()
#                 wx.close
#                 #print(wx_line)
#                 wx_fields = wx_line.split()
#                 skyTemperature = f_to_c(float( wx_fields[4]))
#                 temperature = f_to_c(float(wx_fields[5]))
#                 windspeed = round(float(wx_fields[7])/2.237, 2)
#                 humidity =  float(wx_fields[8])
#                 dewpoint = f_to_c(float(wx_fields[9]))
#                 #timeSinceLastUpdate = wx_fields[13]
#                 open_ok = wx_fields[19]
#                 #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
#                 #self.focus_temp = temperature
#                 last_good_wx_fields = wx_fields
#             except:
#                 print('SRO Weather source problem, 2nd try.')
#                 time.sleep(5)
#                 try:
#                     wx = open('W:/sroweather.txt', 'r')
#                     wx_line = wx.readline()
#                     wx.close
#                     #print(wx_line)
#                     wx_fields = wx_line.split()
#                     skyTemperature = f_to_c(float( wx_fields[4]))
#                     temperature = f_to_c(float(wx_fields[5]))
#                     windspeed = round(float(wx_fields[7])/2.237, 2)
#                     humidity =  float(wx_fields[8])
#                     dewpoint = f_to_c(float(wx_fields[9]))
#                     #timeSinceLastUpdate = wx_fields[13]
#                     open_ok = wx_fields[19]
#                     #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
#                     #self.focus_temp = temperature
#                     last_good_wx_fields = wx_fields
#                 except:
#                     try:

#                         wx = open('W:/sroweather.txt', 'r')
#                         wx_line = wx.readline()
#                         wx.close
#                         #print(wx_line)
#                         wx_fields = wx_line.split()
#                         skyTemperature = f_to_c(float( wx_fields[4]))
#                         temperature = f_to_c(float(wx_fields[5]))
#                         windspeed = round(float(wx_fields[7])/2.237, 2)
#                         humidity =  float(wx_fields[8])
#                         dewpoint = f_to_c(float(wx_fields[9]))
#                         #timeSinceLastUpdate = wx_fields[13]
#                         open_ok = wx_fields[19]
#                         #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
#                         #self.focus_temp = temperature
#                         last_good_wx_fields = wx_fields
#                     except:
#                         print('SRO Weather source problem, using last known good report.')
#                         # NB NB NB we need to shelve the last know good so this does not fail on startup.
#                         wx_fields = last_good_wx_fields
#                         #wx_fields = wx_line.split()   This cause a fault. Wx line not available.
#                         skyTemperature = f_to_c(float( wx_fields[4]))
#                         temperature = f_to_c(float(wx_fields[5]))
#                         windspeed = round(float(wx_fields[7])/2.237, 2)
#                         humidity =  float(wx_fields[8])
#                         dewpoint = f_to_c(float(wx_fields[9]))
#                         #timeSinceLastUpdate = wx_fields[13]
#                         open_ok = wx_fields[19]
#         #self.last_weather =   NB found this fragment
#         open_ok = open_ok
#         try:
#             daily= open('W:/daily.txt', 'r')
#             daily_lines = daily.readlines()

#             daily.close()
#             pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
#             #bright_percent_string = daily_lines[-4].split()[1]  #NB needs to be incorporated
#             last_good_daily_lines = daily_lines
#         except:
#             time.sleep(5)
#             try:
#                 daily= open('W:/daily.txt', 'r')
#                 daily_lines = daily.readlines()
#                 daily.close()
#                 pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
#                 last_good_daily_lines = daily_lines
#             except:
#                 try:
#                     daily= open('W:/daily.txt', 'r')
#                     daily_lines = daily.readlines()
#                     daily.close()
#                     pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
#                     last_good_daily_lines = daily_lines
#                 except:
#                     print('SRO Daily source problem, using last known good pressure.')
#                     daily_lines = last_good_daily_lines
#                     pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
#                    # pressure = round(33.846*float(self.last_good_daily_lines[-3].split()[1]), 2)
#         try:   # 20220105 Experienced a glitch, probably the first try faulted in the code above.
#             pressure = float(pressure)
#         except:
#             pressure = site_config['reference_pressure']
#         illum, mag = g_dev['evnt'].illuminationNow()

#         if illum > 100:
#             illum = int(illum)
#         calc_HSI_lux = illum
#         calc_HSI_lux = calc_HSI_lux
#         # NOte criterian below can now vary with the site config file.
#         dew_point_gap = not (temperature  - dewpoint) < 2
#         temp_bounds = not (temperature < -10) or (temperature > 40)
#         # NB NB NB Thiseeds to go into a config entry.
#         wind_limit = windspeed < 60/2.235   #sky_monitor reports m/s, Clarity may report in MPH
#         sky_amb_limit  = skyTemperature < -20
#         humidity_limit =humidity < 85
#         rain_limit = True # Rain Rate <= 0.001
#         wx_is_ok = dew_point_gap and temp_bounds and wind_limit and sky_amb_limit and \
#                         humidity_limit and rain_limit
#         #  NB  wx_is_ok does not include ambient light or altitude of the Sun
#         try:
#             enc_stat =g_dev['enc'].stat_string
#             if enc_stat in ['Open', 'OPEN', 'Open']:
#                 wx_str = "Yes"
#                 wx_is_ok = True
#             else:
#                 wx_str = 'No'
#                 wx_is_ok = False
#         except:

#             if wx_is_ok:
#                 wx_str = "Yes"
#             else:
#                 wx_str = "No"   #Ideally we add the dominant reason in priority order.
#         # Now assemble the status dictionary.
#         status = {"temperature_C": round(temperature, 2),
#                       "pressure_mbar": pressure,
#                       "humidity_%": humidity,
#                       "dewpoint_C": dewpoint,
#                       "sky_temp_C": round(skyTemperature,2),
#                       "last_sky_update_s":  round(10, 2),
#                       "wind_m/s": abs(round(windspeed, 2)),
#                       'rain_rate': 0.0, # rainRate,
#                       'solar_flux_w/m^2': None,
#                       'cloud_cover_%': 0.0, #str(cloudCover),
#                       "calc_HSI_lux": illum,
#                       "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
#                       "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
#                       "open_ok": wx_str,  #T his is the special bit in the
#                                            # Boltwood for a roof close relay
#                       'wx_hold': False,  # THis is usually added by the OCN Manager
#                       'hold_duration': 0.0,
#                       'meas_sky_mpsas': 22   # THis is a plug.  NB NB NB
#                       #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
#                       }
#         return status
#     else:
#         pass#breakpoint()       #  Debug bad place.

# def get_enc_status(g_dev=None):
#     if site_config['site'] == 'sro':   #  Belts and suspenders.
#         try:
#             enc = open('R:/Roof_Status.txt')
#             enc_text = enc.readline()
#             enc.close
#             enc_list = enc_text.split()

#         except:
#             try:
#                 enc = open('R:/Roof_Status.txt')
#                 enc_text = enc.readline()
#                 enc.close
#                 enc_list = enc_text.split()
#             except:
#                 print("Second read of roof status file failed")
#                 try:
#                     enc = open('R:/Roof_Status.txt')
#                     enc_text = enc.readline()
#                     enc.close
#                     enc_list = enc_text.split()
#                 except:
#                     print("Third read of roof status file failed")
#                     enc_list = [1, 2, 3, 4, 'Error']
#         if len(enc_list) == 5:
#             if enc_list[4] in ['OPEN', 'Open', 'open', 'OPEN\n']:
#                 shutter_status = 0  #Numbering is correct
#                 stat_string = "Open"
#             elif enc_list[4] in ['OPENING']:  #SRO Does not report this.
#                 shutter_status = 2
#                 stat_string = "Open"
#             elif enc_list[4] in ['CLOSED', 'Closed', 'closed', "CLOSED\n"]:
#                 shutter_status = 1
#                 stat_string = "Closed"
#             elif enc_list[4] in ['CLOSING']:  # SRO Does not report this.
#                 shutter_status = 3
#                 stat_string = "Closed"
#             elif enc_list[4] in ['Error']:  # SRO Does not report this.
#                 shutter_status = 4
#                 stat_string = "Fault"  #Do not know if SRO supports this.
#         else:
#             shutter_status = 4
#             stat_string = "Fault"
#         #g_dev['enc'].status = shutter_status   # NB NB THIS was a nasty bug
#         g_dev['enc'].stat_string = stat_string
#         if shutter_status in [2, 3]:
#             g_dev['enc'].moving = True
#         else:
#             g_dev['enc'].moving = False
#         if g_dev['enc'].mode == 'Automatic':
#             e_mode = "Autonomous!"
#         else:
#             e_mode = g_dev['enc'].mode
#         status = {'shutter_status': stat_string,   # NB NB NB "Roof is open|closed' is more inforative for FAT, but we make boolean decsions on 'Open'
#                   'enclosure_synchronized': True,
#                   'dome_azimuth': 0.0,
#                   'dome_slewing': False,
#                   'enclosure_mode': e_mode,
#                   'enclosure_message':  ''
#                  }
#         return status
#     else:
#         pass
    #breakpoint()     #  Debug bad place.
# if __name__ == '__main__':
#     j_dump = json.dumps(site_config)
#     site_unjasoned = json.loads(j_dump)
#     if str(site_config)  == str(site_unjasoned):
#         print('Strings matched.')
#     if site_config == site_unjasoned:
#         print('Dictionaries matched.')

#get_ocn_status = None   # NB these are placeholders for site specific routines for in a config file
# def get_enc_status(g_dev=None):
#     pass
# def get_ocn_status(g_dev=None):
#     #print ("no encolsure control")
#     pass

def get_ocn_status():
    pass
def get_enc_status():
    pass