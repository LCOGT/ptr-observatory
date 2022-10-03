# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20220107 20:01 WER

@author: wrosing
'''
import json


'''
Ports.txt
Tested 202009
25
COM8    SkyRoof
COM9    PWI4
COM10   PWI4
COM11   Dew Heater
COM12   EFA
COM13   Alnitak Screen
COM14  	Gemini
COM15   Darkslide
COM16   Camera Peg
        Pwr 1  FLI unPlug
        Pwr 2
        Pwr 3
        Pwr 4   Cam and filters.
Com17   OTA Peg
        Pwr 1  Gemini
        Pwr 2 EFA

Located on CDK 14 OTA:

Pegasus Astro  COM17
PW EFA PWI3    COM12
PW DEW Heat    COM11
GEMINI         COM14

Located on Camera Assembly:

Pegasus Astro   COM16
Vincent Shutt   COM15   Darkslide
FlI FW 1     Closest to tel
FlI FW 2     closest to cam  flifil0
QHY600         AstroImaging Equipment


'''

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

site_name = 'mrc'    #NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_config = {
    'site': str(site_name).lower(),
    'site_id': 'mrc',
    'debug_site_mode': False,
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne

    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],

    'client_hostname':  'MRC-0m35',
    'client_path':  'Q:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'q:/ptr/',  # Generic place for this host to stash misc stuff
    'archive_path':  'Q:/ptr/',
    'archive_age' : -99.9, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'aux_archive_path':  None,
    'wema_is_active':  True,          # True if the split computers used at a site.
    'wema_hostname': 'MRC-WMS-ENC',   # Prefer the shorter version
    'wema_path':  'Q:/ptr/',  # '/wema_transfer/',
    'dome_on_wema':   True,
    'site_IPC_mechanism':  'redis',   # ['None', shares', 'shelves', 'redis']  Pick One
    'wema_write_share_path': 'Q:/ptr/',  # Meant to be where Wema puts status data.
    'client_read_share_path':  'Q:/ptr/',
    'client_write_share_path': 'Q:/ptr/',
    'redis_ip': '10.15.0.109',  #'127.0.0.1', None if no redis path present,
    'site_is_generic':  False,   # A simply  single computer ASCOM site.
    'site_is_specific':  False,  # Indicates some special code for this site, found at end of config.


    'host_wema_site_name':  'SRO',  #  The umbrella header for obsys in close geographic proximity.
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

    'TZ_database_name':  'America/Los_Angeles',
    'mpc_code':  'ZZ23',    #This is made up for now.
    'time_offset':  -7,
    'timezone': 'PDT',
    'latitude': 34.459375,     #Decimal degrees, North is Positive
    'longitude': -119.681172,   #Decimal degrees, West is negative
    'elevation': 317.75,    # meters above sea level
    'reference_ambient':  10.0,  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  977.83,  #mbar Alternately 12 entries, one for every - mid month.

    'site_roof_control': 'no', #MTF entered this in to remove sro specific code
    'site_in_automatic_default': "Automatic",   #"Manual", "Shutdown"
    'automatic_detail_default': "Enclosure is initially set to Automatic mode.",

    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': True,
    'eve_sky_flat_sunset_offset': -60.,  #  Minutes  neg means before, + after.
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': True,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,

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
            # Intention it is found in this file.
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
            'east_flip_dec_correction': 0.0,
            'has_paddle': False,
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
                'fixed_screen_azimuth': 167.25,
                'Fixed_screen _altitude': 0.54,
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
            'desc':  'Planewave CDK 14 F7.2',
            'telescop': 'mrc1',
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
            'unit':  'degree'
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
            #*********Guesses   7379@10 7457@20  7497 @ 25
            'reference': 6850, #20210710    #7418,    # Nominal at 15C Primary temperature, in microns not steps. Guess
            'ref_temp':  15,      # Update when pinning reference  Larger at lower temperatures.
            'coef_c': 7.895,    # Negative means focus moves out (larger numerically) as Primary gets colder
            'coef_0': 6850,  #20210710# Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '20210710',   #A Guess as to coef_c
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
            "driver": "Maxim.CCDCamera",  #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],   #"Maxim",   #
            #"driver":   'ASCOM.FLI.FilterWheel',   #  NB THIS IS THE NEW DRIVER FROM peter.oleynikov@gmail.com  Found in Kepler ASCOM section
            "dual_wheel": True,
            # "parent": "telescope1",
            # "alias": "CWL2",
            # "desc":  'PTR Custom FLI dual wheel.',
            #"driver": ['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],   #  'ASCOM.QHYFWRS232.FilterWheel',  #"Maxim",   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],
            'ip_string': "",
            'settings': {
                'filter_count': 23,
                'home_filter':  2,
                'default_filter':  'w',
                'filter_reference': 2,
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air',     [0, 0], -1000,  280,  [2, 17], 'ai'], # 0
                                ['dif',     [4, 0],     0,  260,  [2, 17], 'df'], # 1
                                ['w',       [2, 0],     0,  249,  [2, 17], 'w '], # 2
                                ['CR',      [1, 0],     0,  .8,   [2, 17], 'CR'], # 3
                                ['N2',      [3, 0],     0,  .7,   [2, 17], 'N2'], # 4
                                ['up',      [0, 5],     0,  .1,   [1, 17], 'up'], # 5
                                ['gp',      [0, 6],     0,  130,  [2, 17], 'gp'], # 6
                                ['rp',      [0, 7],     0,  45,   [2, 17], 'rp'], # 7
                                ['ip',      [0, 8],     0,  12,   [2, 17], 'ip'], # 8
                                ['z',       [5, 0],     0,  4,    [2, 17], 'z'], # 9
                                ['PL',      [0, 4],     0,  250,  [2, 17], "PL"], # 10
                                ['PR',      [0, 3],     0,  45,   [2, 17], 'PR'], # 11
                                ['PG',      [0, 2],     0,  40,   [2, 17], 'PG'], # 12
                                ['PB',      [0, 1],     0,  60,   [2, 17], 'PB'], # 13
                                ['O3',      [7, 0],     0,  2.6,  [2, 17], '03'], # 14
                                ['HA',      [6, 0],     0,  0.6,  [2, 17], 'HA'], # 15
                                ['S2',      [8, 0],     0,  0.6,  [2, 17], 'S2'], # 16
                                ['difup',   [4, 5],     0,  0.01, [2, 17], 'du'], # 17
                                ['difgp',   [4, 6],     0,  0.01, [2, 17], 'dg'], # 18
                                ['difrp',   [4, 7],     0,  0.01, [2, 17], 'dr'], # 19
                                ['difip',   [4, 8],     0,  0.01, [2, 17], 'di'], # 20
                                ['dark',   [10, 9],     0,  0.01, [2, 17], 'dk']],# 21
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  [0, 1, 2, 10, 7, 19, 6, 18, 12, 11, 13, 8, 20, 3, \
                                        14, 15, 4, 16],   #  9, 21],  # 5, 17], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.
                'filter_sky_sort':     [15, 3, 14,  8, 13, 11, 12, \
                                         6,  7, 10, 2, 1, 0]  #Least to most throughput  5, 9, 4, 16,

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
            'name': 'sq003ms',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600M Pro',
            'driver':  "ASCOM.QHYCCD.Camera", #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'D:/archive/sq01/maxim/',

            'settings': {
                'temp_setpoint': -25,
                'calib_setpoints': [-25, -22.5,- 20, -17.5 ],  #  Picked by day-of-year mod len(list)
                'day_warm': False,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4800,   #NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  3211,
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
                'ref_dark': 360.0,
                'long_dark': 600.0,
                'x_active': 4784,
                'y_active': 3194,
                'det_size': '[1:9600, 1:6422]',  # Physical chip data size as reutrned from driver
                'ccd_sec': '[1:9600, 1:6422]',
                'bias_sec': ['[1:22, 1:6388]', '[1:11, 1:3194]', '[1:7, 1:2129]', '[1:5, 1:1597]'],
                'det_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                'pix_scale': [0.302597, 0.605194, 0.907791, 1.210388],    #   bin-2  2* math.degrees(math.atan(3.76/2563000))*3600

                'CameraXSize' : 4784,
                'CameraYSize' : 3194,
                'MaxBinX' : 2,
                'MaxBinY' : 2,
                'StartX' : 1,
                'StartY' : 1,


                'x_field_deg': round(4784*0.605194/3600, 4),   #48 X 32 AMIN  3MIN X 0.5 DEG
                'y_field_deg': round(3194*0.605194/3600, 4),
                'overscan_x': 24,
                'overscan_y': 34,
                'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.0001,
                'max_exposure': 180.,
                'can_subframe':  True,
                'min_subframe': [128,128],
                'bin_modes':  [[1, 1, 0.303], [2, 2, 0.605],  [3, 3, 0.908], [4, 4, 1.21]],     #Meaning fixed binning if list has only one entry
                'default_bin':  [2, 2, 0.605],
                'bin_enable':  ['2 2'],  #  Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 15, 12],
                'rbi_delay':  0,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color': False,
                'can_set_gain':  True,
                'ref_dark': 360,
                'long_dark': 600,   #  s.
                'reference_gain': [1.3, 2.6, 3.9, 5.2],     #  One val for each binning. Assumed digitalsumming in camera???
                'reference_noise': [6, 6, 6, 6],    #  NB Guess
                'reference_dark': [.2, .8, 1.8, 3.2],  #  Guess
                'max_linearity':  60000,   # Guess
                'saturate':  65300,
                'fullwell_capacity': [80000, 320000, 720000, 1280000],
                'read_mode':  'Normal',
                'readout_mode': 'Normal',
                'readout_speed':  50,
                'square_detector': False,
                'square_pixels': True,
                'areas_implemented': ["600%", '4x4d', "450%", "300%", "250%", "150%", "133%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'default_rotation': 0.0000,
                'flat_bin_spec': '1,1',    #Default binning for flats
                'has_darkslide':  True,
                'darkslide_com':  'COM15',
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

def get_ocn_status():
    pass
def get_enc_status():
    pass
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