# -*- coding: utf-8 -*-
'''

Created on Fri Feb 07,  11:57:41 2020
Updated 20220601 WER   This version does not support color camera channel.

@author: wrosing

NB NB NB  If we have one config file then paths need to change depending upon which host does what job.
'''

#                                                                                        1         1         1       1
#        1         2         3         4         6         7         8         9         0         1         2       2
#234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
import json
import time
#import ptr_events
from pprint import pprint

#  NB NB  Json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.
#  NB NB  My convention is if a value is naturally a float I add a decimal point even to 0.
g_dev = None

 # bolt = ['u', 'g', 'r', 'i', 'zs', 'B', 'V', 'EXO', 'w', 'O3', 'Ha', 'S', 'Cr', 'NIR']
 # print(len(bolt))
 
site_name = 'saf'

site_config = {
    'site': str(site_name.lower()),
    'site_id': 'ARO',
    "version_date": "20220611.0_wer",
    'site_desc': "Apache Ridge Observatory, Santa Fe, NM, USA. 2194m",
    'airport_code':  'SAF',
    'obsy_id': 'SAF1',
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
    'client_hostname':"SAF-WEMA",     # Generic place for this host to stash.
    'client_path': 'F:/ptr/',
    'archive_path': 'F:/ptr/',       # Where images are kept.
    'aux_archive_path':  None,
    'wema_is_active':  True,     # True if an agent (ie a wema) is used at a site.   # Wemas are split sites -- at least two CPS's sharing the control.                          
    'wema_hostname':  'SAF-WEMA',
    'wema_path': 'C:/ptr/',      #Local storage on Wems disk.
    'dome_on_wema':  True,       #NB NB NB CHange this confusing name. 'dome_controlled_by_wema'
    'site_IPC_mechanism':  'shares',   # ['None', shares', 'shelves', 'redis']
    'wema_write_share_path':  'C:/ptr/wema_transfer/',  # Meant to be where Wema puts status data.
    'client_write_share_path':  '//saf-wema/wema_transfer/',
    'redis_ip': None,   # None if no redis path present, localhost if redis iself-contained
    'site_is_generic':  False,   # A simple single computer ASCOM site.
    'site_is_specific':  False,  #  Meaning like SRO with site specific methods to read weatehr and roof status
    
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
    
    'TZ_database_name':  'America/Denver',
    'mpc_code':  'ZZ24',    # This is made up for now.
    'time_offset':  -6.0,   # These two keys may be obsolete give the new TZ stuff 
    'timezone': 'MDT',      # This was meant to be coloquial Time zone abbreviation, alternate for "TX_data..."
    'latitude': 35.554298,     # Decimal degrees, North is Positive
    'longitude': -105.870197,   # Decimal degrees, West is negative
    'elevation': 2194,    # meters above sea level
    'reference_ambient':  10.0,  # Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  794.0,    #mbar   A rough guess 20200315
    
    'site_in_automatic_default': "Manual",   # ["Manual", "Shutdown", "Automatic"]
    'automatic_detail_default': "Enclosure is initially set to Manual by SAF config.",
    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': False,
    'eve_sky_flat_sunset_offset': -60.0,  # Minutes  neg means before, + after.
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': False,
    're-calibrate_on_solve': True, 
    'get_ocn_status': None,
    'get_enc_status': None,
    'not_used_variabl': None,
    'observing_conditions' : {     #for SAF
        'observing_conditions1': {
            'parent': 'site',
            'name': 'Boltwood',
            'driver': 'ASCOM.Boltwood.ObservingConditions',
            'driver_2':  'ASCOM.Boltwood.OkToOpen.SafetyMonitor',
            'driver_3':  'ASCOM.Boltwood.OkToImage.SafetyMonitor',
            'redis_ip': '127.0.0.1',   #None if no redis path present
            'has_unihedron':  True,
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  10    # False, None or numeric of COM port.
        },
    },
    
    'defaults': {
        'observing_conditions': 'observing_conditions1',  # These are used as keys, may go away.
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
    
    'enclosure': {
        'enclosure1': {
            'parent': 'site',

            'name': 'HomeDome',
            'enc_is_specific':  False, 
            'hostIP':  '10.0.0.10',
            'driver': 'ASCOM.DigitalDomeWorks.Dome',  #  'ASCOMDome.Dome',  #ASCOMDome.Dome',  # ASCOM.DeviceHub.Dome',  # ASCOM.DigitalDomeWorks.Dome',  #"  ASCOMDome.Dome',

            'has_lights':  True,
            'controlled_by': 'mount1',
			'is_dome': True,
            'mode': 'Automatic',
            'enc_radius':  70,  #  inches Ok for now.
            'common_offset_east': -19.5,  # East is negative.  These will vary per telescope.
            'common_offset_south': -8,  # South is negative.   So think of these as default.
            
            'cool_down': 89.0,     # Minutes prior to sunset.
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
            },
            'eve_bias_dark_dur':  2.0,   # hours Duration, prior to next.
            'eve_screen_flat_dur': 1.0,   # hours Duration, prior to next.
            'operations_begin':  -1.0,   # - hours from Sunset
            'eve_cooldown_offset': -.99,   # - hours beforeSunset
            'eve_sky_flat_offset':  0.5,   # - hours beforeSunset 
            'morn_sky_flat_offset':  0.4,   # + hours after Sunrise
            'morning_close_offset':  0.41,   # + hours after Sunrise
            'operations_end':  0.42,
        },
    },



    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'name': 'safpier',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'safpier',
            'desc':  'AP 1600 GoTo',
            'driver': 'AstroPhysicsV2.Telescope',
            'alignment': 'Equatorial',
            'default_zenith_avoid': 0.0,   # degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,       # paddle refers to something supported by the Python code, not the AP paddle.
            'pointing_tel': 'tel1',     # This can be changed to 'tel2'... by user.  This establishes a default.
            
            'west_clutch_ra_correction': -0.05323724387608619,  #final:   0.0035776615398219747 -0.1450812805892454
            'west_clutch_dec_correction': 0.3251459235809251,
            'east_flip_ra_correction':   -0.040505313212952586, # Initially -0.039505313212952586, 
            'east_flip_dec_correction':  -0.54607711292257797,  #initially  -0.39607711292257797,
            
                'latitude_offset': 0.0,     # Decimal degrees, North is Positive   These *could* be slightly different than site.
                'longitude_offset': 0.0,   # Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
                'elevation_offset': 0.0,  # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 180.,
                'horizon':  20.,    # Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  # Meant to be something to draw on the Skymap with a spline fit.
                    '0.0': 10,
                    '90' : 10,
                    '180': 10,
                    '270': 10,
                    '359': 10
                    },  # We use a dict because of fragmented azimuth mesurements.
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

 

    'telescope': {                            # OTA = Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'desc':  'Ceravolo 300mm F4.9/F9 convertable',
            'telescop': 'cvagr-0m30-f9-f4p9-001',
            'driver': None,                     # Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 31808,
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
        
        # 'telescope2': {
        #     'parent': 'mount1',
        #     'name': 'Main OTA',
        #     'desc':  'Astro-Physics Starfire 180mmF8',
        #     'telescop': 'apref-0m180-f8-=-001',
        #     'driver': None,                     # Essentially this device is informational.  It is mostly about the optics.
        #     'collecting_area': 25466, 
        #     'obscuration':  0.0,  # Informatinal, already included in collecting_area.
        #     'aperture': 180,
        #     'focal_length': 1440,  # 1470,   #2697,   # Converted to F9, measured 20200905  11.1C
        #     'has_dew_heater':  False,
        #     'screen_name': 'screen2',
        #     'focuser_name':  'focuser2',
        #     'rotator_name':  'rotator2',
        #     'has_instrument_selector': False,   # This is a default for a single instrument system
        #     'selector_positions': 1,            # Note starts with 1
        #     'instrument names':  ['camera_2_2'],
        #     'instrument aliases':  ['QHY376Color'],
        #     'configuration': {
        #           "position1": ["darkslide1", "filter_wheel1", "camera1"]
        #           },
        #     'camera_name':  'camera_1_2',
        #     'filter_wheel_name':  'filter_wheel2',
        #     'has_fans':  True,
        #     'has_cover':  True,
        #     'axis_offset_east': 0, #19.5,  # East is negative  THese will vary per telescope.
        #     'axis_offset_south': 0, #-8,  # South is negative

        #     'settings': {
        #         'fans': ['Auto', 'High', 'Low', 'Off'],
        #         'offset_collimation': 0.0,    # If the mount model is current, these numbers are usually near 0.0
        #                                       # for tel1.  Units are arcseconds.
        #         'offset_declination': 0.0,
        #         'offset_flexure': 0.0,
        #         'west_flip_ha_offset': 0.0,  # new terms.
        #         'west_flip_ca_offset': 0.0,
        #         'west_flip_dec_offset': 0.0
        #     },
    
    
    
        # }
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
            'unit':  'degree'    # 'steps'
        },
        # 'rotator2': {
        #     'parent': 'telescope1',
        #     'name': 'rotator',
        #     'desc':  'Opetc Gemini',
        #     'driver': 'ASCOM.OptecGemini.Rotator',
        #     'com_port':  'COM10',
        #     'minimum': -180.,
        #     'maximum': 360.0,
        #     'step_size':  0.0001,     # Is this correct?
        #     'backlash':  0.0,
        #     'unit':  'degree'    # 'steps'
        # },
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
        # 'screen2': {
        #     'parent': 'telescope2',
        #     'name': 'screen',
        #     'desc':  'Optec Alnitak Flip-Flat"',
        #     'driver': 'COM14',  # This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
        #     'minimum': 5,   # This is the % of light emitted when Screen is on and nominally at 0% bright.
        #     'saturate': 255,  # Out of 0 - 255, this is the last value where the screen is linear with output.
        #                       # These values have a minor temperature sensitivity yet to quantify.


        # },
    
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
		    'com_port': 'COM13',    #AP 'COM5'  No Temp Probe.
            # # F4.9 setup
            # 'reference': 5800,    # 20210313  Nominal at 10C Primary temperature
            # 'ref_temp':  5.1,    # Update when pinning reference
            # 'coef_c': 0,  # 26.055,   # Negative means focus moves out as Primary gets colder
            # 'coef_0': 5800,  # Nominal intercept when Primary is at 0.0 C. 
            # 'coef_date':  '20220301',    # This appears to be sensible result 44 points -13 to 3C'reference':  6431,    # Nominal at 10C Primary temperature
            #F9 setup
            'reference': 5743, #5743,    #  Meas   Nominal at 10C Primary temperature
            'ref_temp':  4.8,    # Update when pinning reference
            'coef_c': 0.0, #-77.57,   # negative means focus moves out/in as Primary gets colder/warmer.
            'coef_0': 5775, #6155,   #5675,  20220502 Nominal intercept when Primary is at 0.0 C. 
            'coef_date':  '20220901?',    # SWAG 
            'minimum': 0,     # NB this area is confusing steps and microns, and need fixing.
            'maximum': 12600,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'unit': 'micron',
            'unit_conversion': 9.09090909091,
            'has_dial_indicator': False
        },
#         'focuser2': {
#             'parent': 'telescope2',
#             'name': 'focuser',
#             'desc':  'Optec Gemini',
#             'driver': 'ASCOM.OptecGemini.Focuser',
# 		      'com_port':  None,
#             # # F4.9 setup
#             # 'reference': 5800,    # 20210313  Nominal at 10C Primary temperature
#             # 'ref_temp':  5.1,    # Update when pinning reference
#             # 'coef_c': 0,  # 26.055,   # Negative means focus moves out as Primary gets colder
#             # 'coef_0': 5800,  # Nominal intercept when Primary is at 0.0 C. 
#             # 'coef_date':  '20220301',    # This appears to be sensible result 44 points -13 to 3C'reference':  6431,    # Nominal at 10C Primary temperature
#             #F9 setup
#             'reference': 6000,    #  Meas   Nominal at 10C Primary temperature
#             'ref_temp':  20,    # Update when pinning reference
#             'coef_c': 0,   # negative means focus moves out as Primary gets colder
#             'coef_0': 6000,  # Nominal intercept when Primary is at 0.0 C. 
#             'coef_date':  '20220502',    # SWAG 
#             'minimum': 0,     # NB this area is confusing steps and microns, and need fixing.
#             'maximum': 12600,   #12672 actually
#             'step_size': 1,
#             'backlash': 0,
#             'unit': 'micron',
#             'unit_conversion': 9.09090909091,
#             'has_dial_indicator': False
#         },
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
            "driver": "LCO.dual",  # 'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'ip_string': 'http://10.0.0.110',
            "dual_wheel": True,
            'settings': {
                'filter_count': 42,
                'home_filter':  1,
                'default_filter': "w",
                'filter_reference': 1,   # We choose to use W as the default filter.  Gains taken at F9, Ceravolo 300mm
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'generic'],
                        
                        ['air',  [0,  0], -800, 81.6, [2   ,  20], 'ai'],    # 0.  Gains 20211020 Clear NE sky
                        ['focus',[7,  0],    0, 72.8, [360 , 170], 'w '],    # 1.
                        ['Lum',  [7,  0],    0, 72.8, [360 , 170], 'w '],    # 2.
                        ['Red',  [0,  8],    0, 11.0, [360 , 170], 'w '],    # 3.
                        ['Green',[0 , 7],    0, 18.6, [360 , 170], 'w '],    # 4.
                        ['Blue', [0,  6],    0, 42.3, [360 , 170], 'w '],    # 5.
                        ['w',    [7,  0],    0, 74.5, [360 , 170], 'w '],    # 6.
                        ['up',   [1,  0],    0, 1.39, [2   ,  20], 'up'],    # 7.
                        ['gp',   [2,  0],    0, 49.4, [.77 ,  20], 'gp'],    # 8.
                        ['rp',   [3,  0],    0, 17.5, [1.2 ,  20], 'rp'],    # 9.
                        ['ip',   [4,  0],    0, 5.15, [.65 ,  20], 'ip'],    #10.
                        ['z',    [5,  0],    0, .855, [1.0 ,  20], 'zs'],    #11.
                        ['zp',   [0,  9],    0, 1.08, [360 , 170], 'zp'],    #12.
                        ['y',    [6,  0],    0, .500, [360 , 170], 'y '],    #13.
                        ['EXO',  [8,  0],    0, 39.7, [360 , 170], 'ex'],    #14.
                        ['JB',   [9,  0],    0, 28.0, [0.65,  20], 'BB'],    #15.
                        ['JV',   [10, 0],    0, 24.4, [.32 ,  20], 'BV'],    #16.
                        ['Rc',   [11, 0],    0, 17.2, [10  , 170], 'BR'],    #17.
                        ['Ic',   [12, 0],    0, 3.66, [360 , 170], 'BI'],    #18.
                        ['PL (Lum)',[7,  0], 0, 74.34,[360 , 170], 'PL'],    #19.
                        ['PR (Red)',[0,  8], 0, 13.7, [.32 ,  20], 'PB'],    #20.
                        ['PG (Grn)',[0,  7], 0, 24.0, [30  , 170], 'PG'],    #21.
                        ['PB (Blu)',[0,  6], 0, 37.4, [360 , 170], 'PR'],    #22.
                        ['NIR',  [0, 10],    0, 5.11, [0.65,  20], 'ni'],    #23.
                        ['O3',   [0,  2],    0, 1.79, [360 , 170], 'O3'],    #24.
                        ['HA',   [0,  3],    0, .537, [360 , 170], 'HA'],    #25.
                        ['N2',   [13, 0],    0, 0.32, [360 , 170], 'N2'],    #26.
                        ['S2',   [0,  4],    0, .302, [0.65,  20], 'S2'],    #27.
                        ['CR',   [0,  5],    0, .556, [360 , 170], 'Rc'],    #28.
                        ['dark', [5,  6],    0, 0.20, [360 , 170], 'dk'],    #29                       ['dif',  [0,  1],    0, 0.21, [360 , 170], 'df'],    #25
                        ['difw',   [7,  1],  0, 72.6, [0.65,  20], 'dw'],    #30.
                        ['difup',  [1,  1],  0, 10.5, [0.65,  20], 'du'],    #31.   #NONE OF THESE OR BELOW ARE ACCURATE.
                        ['difgp',  [2,  1],  0, 234,  [0.65,  20], 'dg'],    #32.
                        ['difrp',  [3,  1],  0, 70.0, [0.65,  20], 'dr'],    #33.
                        ['difip',  [4,  1],  0, 150., [0.65,  20], 'di'],    #34.
                        ['difz',   [5,  1],  0, 0.73, [0.65,  20], 'ds'],    #35.
                        ['dify',   [6,  1],  0, 0.15, [0.65,  20], 'dY'],    #36.
                        ['difEXO', [8,  1],  0, 161., [0.65,  20], 'dx'],    #37.
                        ['difJB',  [9,  1],  0, 42.5, [0.65,  20], 'dB'],    #38.
                        ['difJV',  [10, 1],  0, 33.0, [0.65,  20], 'dV'],    #39.
                        ['difRc',  [11, 1],  0, 22.2, [0.65,  20], 'dR'],    #40.
                        ['difIc',  [12, 1],  0, 10. , [0.65,  20], 'dI']],   #41.
                        #['LRGB',   [7,  0],  0, 72.8, [360 , 170], 'LRGB']],#42. valid entries, only 36 useable.
                'filter_screen_sort':  [12, 0, 11, 2, 3, 5, 4, 1, 6],   # don't use narrow yet,  8, 10, 9], useless to try.
                
                
                'filter_sky_sort': [13, 27, 26, 25, 28, 11, 12, 7, 24, 18, 23, 10, 20, 17, 9,\
                                    21 ,16, 15, 14, 22, 8, 30, 19, 6, 0]    #  No diffuser based filters 


                                    
            },
                # "filter_wheel2": {
                #     "parent": "telescope2",
                #     "alias": "CWL2",
                #     "desc":  'QHYRS232 5 Position COM22',
                #     "driver": 'ASCOM.QHYFWRS232.FilterWheel',  #"Maxim",   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],
                #     'startup_script':  'None',
                #     'recover_script':  'None',
                #     'shutdown_script':  'None',  
                #     'settings': {
                #         'filter_count': '5',
                #         'filter_reference': '0',
                #         'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                #                         ['lpr',   '(0,  0)', '0.000', '0.01', ['2', '17'], 'lp'],  # 0
                #                         ['tri',   '(1,  0)', '0.000', '0.01', ['2', '17'], 'tr'],  # 1
                #                         ['air',   '(2,  0)', '-0.779', '0.01', ['2', '17'], 'ai'],  #  2
                #                         ['dark1', '(3,  0)', '0.000', '0.00', ['2', '17'], 'dk'],  # 4
                #                         ['dark2', '(4,  0)', '-0.779', '0.00', ['2', '17'], 'dk']],  # 5
         
                #         'filter_screen_sort':  ['2', '0', '1'],
                #         'filter_sky_sort':     ['1', '0', '2']  #

                #     },
                # },

                                        

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
            'driver': "ASCOM.QHYCCD_CAM2.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ## 'ASCOM.FLI.Kepler.Camera',
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'G:/000ptr_saf/archive/sq01/autosaves/',
            'detsize': '[1:9600, 1:6422]',  # QHY600Pro Physical chip data size as returned from driver
            'ccdsec': '[1:9600, 1:6422]',
            'biassec': ['[1:24, 1:6388]', '[1:12, 1:3194]', '[1:8, 1:2129]', '[1:6, 1:1597]'],
            'datasec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
            'trimsec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],

            'settings': {
                'temp_setpoint': -12.5,
                'calib_setpoints': [-12.5, -10, -7.5, -5],  # Should vary with season? by day-of-year mod len(list)
                'day_warm': False,
                'cooler_on': True,
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
                'pix_scale': [0.528, 1.055, 1.583, 2.110],  # VErified for saf 20220903 WER [0.2876, 0.575, 0.863, 1.15], #F9        [0.528, 1.055, 1.583, 2.110] F4.9
                'x_field_deg': 1.042,   #  round(4784*1.055/3600, 4),
                'y_field_deg': 0.7044,   # round(3194*1.055/3600, 4),
                'overscan_x': 24,
                'overscan_y': 3,
                'north_offset': 0.0,    # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,     # Not sure why these three are even here.
                'rotation': 0.0,        # Probably remove.
                'min_exposure': 0.00001,
                'max_exposure': 360.0,
                'can_subframe':  True,
                'min_subframe':  [128, 128],       
                'bin_modes':  [[2, 2, 1.06], [1, 1, 0.53], [3, 3, 1.58], [4, 4,2.11]],   #Meaning no binning choice if list has only one entry, default should be first.
                'default_bin':  [2, 2, 1.06],    # Matched to seeing situation by owner
                'cycle_time':  [18, 15, 15, 12],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'rbi_delay':  0.,      # This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color':  False,
                'can_set_gain':  False,
                'bayer_pattern':  None,    # Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'reference_gain': [1.3, 2.6, 3.9, 5.2],     #One val for each binning.
                'reference_noise': [6, 6, 6, 6],    #  NB Guess
                'reference_dark': [.2, .8, 1.8, 3.2],  #  Guess
                'max_linearity':  60000,   # Guess  60% of this is max counts for skyflats.  75% rejects the skyflat
                'saturate':  65300,
                'fullwell_capacity': [80000, 320000, 720000, 1280000],
                                    #hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
                    #hdu.header['RDOUTM'] = (self.config['camera'][self.name]['readout_mode'], 'Camera readout mode')
                    #hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
                'read_mode':  'Normal',
                'readout_mode':  'Normal',
                'readout_speed': 0.6,
                'areas_implemented': ["Full", '2x2', '4x4',"600%", "500%", "450%", "300%", "220%", "150%", "133%", "100%", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'has_darkslide':  True,
                'darkslide_com':  'COM17',
                'has_screen': True,
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
        # 'camera_2_2': {
        #     'parent': 'telescope2',
        #     'name': 'sq001c',      # Important because this points to a server file structure by that name.
        #     'desc':  'QHY 286C',
        #     'service_date': '20220501',
        #     'driver': "ASCOM.QHYCCD_GUIDER.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ## 'ASCOM.FLI.Kepler.Camera',
        #     'detector':  'Sony IMX571',
        #     'manufacturer':  'QHY',
        #     'use_file_mode':  False,
        #     'file_mode_path':  'G:/000ptr_saf/archive/ssq001c/autosaves/',
        #     'detsize': '[1:6280, 1:4210]',  # QHY286Physical chip data size as returned from driver
        #     'ccdsec': '[1:6280, 1:4210]',
        #     'biassec': ['[1:24, 1:6388]', '[1:12, 1:3194]', '[1:8, 1:2129]', '[1:6, 1:1597]'],
        #     'datasec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
        #     'trimsec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],

        #     'settings': {
        #         'temp_setpoint': -10.0,
        #         'calib_setpoints': [-12.5, -10, -7.5, -5],  # Should vary with season? by day-of-year mod len(list)
        #         'day_warm': False,
        #         'cooler_on': True,
        #         'x_start':  0,
        #         'y_start':  0,
        #         'x_width':  6280,   # NB Should be set up with overscan, which this camera is!  20200315 WER
        #         'y_width':  4210,
        #         'x_chip':  6280,   # NB Should specify the active pixel area.   20200315 WER
        #         'y_chip':  4210,
        #         'x_trim_offset':  8,   # NB these four entries are guesses.
        #         'y_trim_offset':  8,
        #         'x_bias_start':  6280,
        #         'y_bias_start' : 4210,
        #         'x_active': 6252,
        #         'y_active': 4176,
        #         'x_pixel':  3.76,
        #         'y_pixel':  3.76,
        #         'pix_scale': [0.539, 1.077, 1.616, 2.154],  #[0.2876, 0.575, 0.863, 1.15], #F9        [0.528, 1.055, 1.583, 2.110] F4.9
        #         'x_field_deg': 0.9652,   #  round(4784*1.055/3600, 4),
        #         'y_field_deg': 0.6447,   # round(3194*1.055/3600, 4),
        #         'overscan_x': 24,
        #         'overscan_y': 3,
        #         'north_offset': 0.0,    # These three are normally 0.0 for the primary telescope
        #         'east_offset': 0.0,     # Not sure why these three are even here.
        #         'rotation': 0.0,        # Probably remove.
        #         'min_exposure': 0.0001,
        #         'max_exposure': 300.0,
        #         'can_subframe':  True,
        #         'min_subframe':  [128, 128],       
        #         'bin_modes':  [[2, 2, 1.06], [1, 1, 0.53], [3, 3, 1.58], [4, 4, 2.11]],   #Meaning no binning choice if list has only one entry, default should be first.
        #         'default_bin':  [2, 2, 1.06],    # Matched to seeing situation by owner   # Matched to seeing situation by owner
        #         'cycle_time':  [18, 15, 15, 12],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
        #         'rbi_delay':  0.,      # This being zero says RBI is not available, eg. for SBIG.
        #         'is_cmos':  True,
        #         'is_color':  False,
        #         'can_set_gain':  False,
        #         'bayer_pattern':  'RGGB',    # Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
        #         'reference_gain': [1.3, 2.6, 3.9, 5.2],     #One val for each binning.
        #         'reference_noise': [6, 6, 6, 6],    #  NB Guess
        #         'reference_dark': [.2, .8, 1.8, 3.2],  #  Guess
        #         'max_linearity':  60000,   # Guess  60% of this is max counts for skyflats.  75% rejects the skyflat
        #         'saturate':  65300,
        #         'fullwell_capacity': [90000, 360000, 7810000, 1144000],
        #                             #hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
        #             #hdu.header['RDOUTM'] = (self.config['camera'][self.name]['readout_mode'], 'Camera readout mode')
        #             #hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
        #         'read_mode':  'Normal',
        #         'readout_mode':  'Normal',
        #         'readout_speed': 0.6,
        #         'areas_implemented': ["Full", "600%", "500%", "450%", "300%", "220%", "150%", "133%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
        #         'default_area':  "Full",
        #         'has_darkslide':  False,
        #         'has_flip_flat':  True,
        #         'darkslide_com':  'COM17',
        #         'has_screen': True,
        #         'screen_settings':  {
        #             'screen_saturation':  157.0,   # This reflects WMD setting and needs proper values.
        #             'screen_x4':  -4E-12,  # 'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
        #             'screen_x3':  3E-08,
        #             'screen_x2':  -9E-05,
        #             'screen_x1':  .1258,
        #             'screen_x0':  8.683
        #         },
        #     },
        # },

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
        
        


