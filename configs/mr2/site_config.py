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
import json


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

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

# TIM  I have tried to follow "Photon travel order"

#@@@@


site_name = 'mrc2'    #NB These must be unique across all of PTR.

site_config = {
    'site': site_name.lower(), #TIM this may no longer be needed.
    'site_id': 'mrc2',
    'debug_site_mode': False,
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne

    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],

    'client_hostname':  'mr2-0m60',

    'client_path':  'Q:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'save_to_alt_path':  'no',
    'archive_path':  'Q:/ptr/',

    'archive_age' : -99.9, # Number of days to keep files in the local archive before deletion. Negative means never delete
    'send_files_at_end_of_night' : 'no', # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
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


    'host_wema_site_name':  'mrc',  #  The umbrella header for obsys in close geographic proximity.

    'name': 'Mountain Ranch Camp Observatory 0m6f6.8',
    'location': 'Santa Barbara, California,  USA',
    'airport_code': 'SBA',
    'telescope_description':  '0m61 f6.8 Planewave CDK',
    'site_path': 'Q:/',     #Really important, this is where state and results are stored.
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #  i.e, a multi-line text block supplied and formatted by the owner.

    'mpc_code':  'ZZ23',    #This is made up for now.
    'time_offset':  -8,
    'TZ_database_name':  'America/Los_Angeles',
    'timezone': 'PST',
    'latitude': 34.34595969,     #Decimal degrees, North is Positive
    'longitude': -119.6811323955,   #Decimal degrees, West is negative
    'elevation': 317.75,    # meters above sea level
    'reference_ambient':  15.0,  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  977.83,  #mbar Alternately 12 entries, one for every - mid month.
    'site_in_automatic_default': "Automatic",   #"Manual", "Shutdown"
    'automatic_detail_default': "Enclosure is set to Automatic mode.",
    'observing_check_period' : 2,    # How many minutes between weather checks
    'enclosure_check_period' : 2,    # How many minutes between enclosure checks

    'auto_eve_bias_dark': False,
    
    'auto_midnight_moonless_bias_dark': False,
    'auto_eve_sky_flat': False,
    'eve_sky_flat_sunset_offset': -60.,  #  Minutes  neg means before, + after.
    'eve_cool_down_open' : -60.0,
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': True,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,
    'periodic_focus_time' : 0.5, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm' : 1.0, # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_exposure_time': 15, # Exposure time in seconds for exposure image
    'solve_nth_image' : 10, # Only solve every nth image
    'solve_timer' : 5, # Only solve every X minutes
    'threshold_mount_update' : 10, # only update mount when X arcseconds away

    'defaults': {
        'observing_conditions': 'observing_conditions1',
        'enclosure': 'enclosure1',
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
    'device_types': [
        'observing_conditions',
        'enclosure',
        'mount',
        'telescope',
        #'screen',
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

    'observing_conditions' : {
        'observing_conditions1': {
            'parent': 'site',
            'ocn_is_specific':  True,  # Indicates some special site code.
            # Intention it is found in this file.
            'name': 'SRO File',
            'driver': 'Windows.Share',  # Could be redis, ASCOM, ...
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
            'name': 'Megawan',
            'hostIP':  '10.15.0.30',
            'driver': 'Windows_share',
            'shutdown_script':  None,
            'has_lights':  True,
            'controlled_by':  ['mount1', 'mount2'],
            'is_dome': False,
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
            }
        },

    'mount': {
        'mount1': {
            'name': 'westpier',
            'hostIP':  '10.15.0.40',     #Can be a name if local DNS recognizes it.
            'hostname':  'westpier',
            'desc':  'Planewave L600 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',  #This picks up signals to the rotator from the mount.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'alignment': 'Alt-Az',
            'default_zenith_avoid': 7.0,   #degrees floating
            'east_flip_ra_correction': 0.0,
            'east_flip_dec_correction': 0.0,
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0,
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
 			    'longitude_offset': 0-2.5,   #meters West is negative  #NB This could be an eval( <<site config data>>))
 			    'elevation_offset': 0.5,    # meters above sea level
                'home_park_altitude': 0,   #Having this setting is important for PWI4 where it can easily be messed up.
                'home_park_azimuth': 195.0,
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


    'telescope': {
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
            'collecting_area':  128039.0,
            'obscuration':  47,
            'aperture': 610,
            'f-ratio':  6.8,   #This and focal_lenght can be refined after a solve.
            'focal_length': 3962,
            'has_dew_heater':  True,
            'screen_name': 'screen2',   #The enclosure has two screens in the WMD case, one for each mount.
            # NB NB All the blow need some checking
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
            'rotator_name':  'rotator1',
            'focuser_name':  'focuser1',
                # 'camera_name':  'camera_1_1',
                # 'filter_wheel_name':  'filter_wheel1',
            'has_instrument_selelector': True,
            'selector_positions':  4,
            'instrument names':  ['main camera', 'echelle', 'camera_2', 'low-res spect'],
            'instrument aliases':  ['QHY600Mone', 'eShel', 'FLI 16803', 'UVEX'],
            # 'configuration: {
            #      "position1": {
            #          'darkslide1',
            },


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
            'shutdown_script':  'None' ,
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
            'start_at_config_reference': False,
            'use_focuser_temperature': True,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'reference':  6500,    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   22.5,      #Update when pinning reference  Larger at lower temperatures.
            'coef_c': -0.0,   #negative means focus moves out as Primary gets colder
            'coef_0': 6000,  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '202004501',
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20221002',   # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            'use_local_temp':  True,
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
            'dual_wheel':  True,
            'ip_string': 'http://127.0.0.1',
            "desc":  'Dual Apogee custom Dual 50mm sq.',
            #"driver": ['ASCOM.Apogee.FilterWheel', 'ASCOM.Apogee2.FilterWheel'],
            'driver': 'Maxim.CCDcamera',  #'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            

            'settings': {
                'filter_count': '24',
                'home_filter': 1,
                'filter_reference': 1,
                'default_filter':  'w',
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air',     [0, 0], -1000, 0.01, [2, 17], 'ai'],   # 0
                                ['Lum',     [1, 0],     0, 0.01, [2, 17], 'w '],   # 20
                                ['Red',     [0, 4],     0, 0.01, [2, 17], 'r '],  # 21                                ['JV (Grn)',      [0, 3],     0, 0.01, [2, 17], 'V '],   # 9
                                ['Green',   [0, 3],     0, 0.01, [2, 17], 'V '],   # 22
                                ['Blue',    [0, 1],     0, 0.01, [2, 17], 'B '],   # 23
                                ['w',       [1, 0],     0, 0.01, [2, 17], 'w '],   # 1
                                ['dif',     [2, 0],     0, 0.01, [2, 17], 'df'],   # 2
                                ['O3',      [3, 0],     0, 0.01, [2, 17], 'O3'],   # 3
                                ['HA',      [4, 0],     0, 0.01, [2, 17], 'HA'],   # 4
                                ['N2',      [5, 5],     0, 0.01, [2, 17], 'S2'],   # 5
                                ['S2',      [6, 6],     0, 0.01, [2, 17], 'N2'],   # 6
                                ['JB',      [0, 1],     0, 0.01, [2, 17], 'B '],   # 7
                                ['g',       [0, 2],     0, 0.01, [2, 17], 'g '],   # 8
                                ['JV',      [0, 3],     0, 0.01, [2, 17], 'V '],   # 9
                                ['r',       [0, 4],     0, 0.01, [2, 17], 'r '],  # 10
                                ['i',       [0, 5],     0, 0.01, [2, 17], 'i '],  # 11
                                ['EXO',     [0, 6],     0, 0.01, [2, 17], 'EX'],  # 12
                                ['dif-JB',  [2, 1],     0, 0.01, [2, 17], 'Ha'],  # 13
                                ['dif-g',   [2, 2],     0, 0.01, [2, 17], 'dg'],  # 14
                                ['dif-JV',  [2, 3],     0, 0.01, [2, 17], 'dV'],  # 15
                                ['dif-r',   [2, 5],     0, 0.01, [2, 17], 'dr'],  # 16
                                ['dif-i',   [2, 6],     0, 0.01, [2, 17], 'di'],  # 17
                                ['dif-exo', [2, 0],     0, 0.01, [2, 17], 'dE'],  # 18
                                ['dark',    [4, 1],     0, 0.01, [2, 17], 'dk']], # 19
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  ['0', '1', '2', '10', '7', '6', '18', '12', '11', '13', '8',  '3', \
                                        '14', '15', '4', '16'],   #  '9', '21'],  # '5', '17'], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.
                'filter_sky_sort':     ['17', '5', '9', '16', '4', '15', '14', '3',  '8', '13', '11', '12', \
                                        '18', '6', '7', '10', '2', '1', '0']  #Least to most throughput

            },
        },
    },

    # A site may have many cameras registered (camera_1_11, camera_1_2, _2_3, ...) each with unique aliases -- which are assumed
    # to be the name an owner has assigned and in principle that name "kb01" is labeled and found on the camera.  Between sites,
    # there can be overlap of camera names.  LCO convention is letter of cam manuf, letter of chip manuf, then 00, 01, 02, ...
    # However this code will treat the camera name/alias as a string of arbitrary length:  "saf_Neyle's favorite_camera" is
    # perfectly valid as an alias.

    #Ultimately every camera needs a specific configuration file, and associated with each camera or guider there may be a
    #darslide, filter wheel, and aux_focus.
    #We preseve the idea camera_1 refers to the first camera on the first ota so camera_2 is first camera on OTA 2

#
    'camera': {
        #'cameras': ['camera_1', 'camera_1_2'],
        #'autoguiders': ['ag_1_2', 'ag _1_4'],
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'kf01',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Microline OnSemi 16803',
            'driver':  'ASCOM.FLI.Camera',   #  Maxim.CCDCamera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'detector':  'OnSemi 162803',
            'manufacturer':  'FLI -- Finger Lakes Instrumentation',
            'use_file_mode':  False,
            'file_mode_path':  'Q:/000ptr_saf/archive/kf01/autosaves/',
            'settings': {
                'is_osc' : True,
                'osc_bayer' : 'RGGB',
                'crop_preview': False,
                'crop_preview_ybottom': 1,
                'crop_preview_ytop': 1,
                'crop_preview_xleft': 1,
                'crop_preview_xright': 1,
                'temp_setpoint': -35,
                'calib_setpoints': [-12.5, -10, -7.5, -5],   #A swag
                'day_warm': False,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4132,
                'y_width':  4117,
                'x_chip':   4132,
                'y_chip':   4117,
                'CameraXSize' : 4132,
                'CameraYSize' : 4117,
                'MaxBinX' : 2,
                'MaxBinY' : 2,
                'StartX' : 1,
                'StartY' : 1,
                'x_pixel':  9.0,
                'y_pixel': 9.0,
                'x_active': 4132,
                'y_active': 4117,
                # NB NB All these numbers are placeholds are are incorrect for the FLI camera
                'det_size': '[1:9600, 1:6422]',  # Physical chip data size as reutrned from driver
                'ccd_sec': '[1:9600, 1:6422]',
                'bias_sec': ['[1:22, 1:6388]', '[1:11, 1:3194]', '[1:7, 1:2129]', '[1:5, 1:1597]'],
                'det_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'data_sec': ['[25:9600, 1:6388]', '[13:4800, 1:3194]', '[9:3200, 1:2129]', '[7:2400, 1:1597]'],
                'trim_sec': ['[1:9576, 1:6388]', '[1:4788, 1:3194]', '[1:3192, 1:2129]', '[1:2394, 1:1597]'],
                'pix_scale': [0.4685, 0.9371, 1.8742],    #  1.4506,  bin-2  2* math.degrees(math.atan(9/3962000))*3600
                'x_field_deg': 0.5331,  # round(4096*0.468547/3600, 4),   #32_0 X 32 AMIN  3MIN X 0.5 DEG
                'y_field_deg': 0.5331,  # round(4096*0.468547/3600, 4),
                'field_area_sq_amin': 1023,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.25,  #Need to check this setting out
                'max_exposure': 600.0,
                'ref_dark': 300.0,
                'long_dark': 600.0,
                'can_subframe':  True,
                'min_subframe':  [128,128],
                'bin_modes':  [[2, 2, 0.937], [1, 1, 0.469], [4, 4, 1.87]],   # [3, 3, 1.45],Meaning no binning choice if list has only one entry, default should be first.
                'default_bin':  [2, 2, 0.937],    # Matched to seeing situation by owner
                'maximum_bin':  [1, 1, 0.469],    # Matched to seeing situation by owner
                'cosmics_at_default' : 'no',
                'cosmics_at_maximum' : 'yes',
                'bin_enable':  ['2 2'],
                'cycle_time':  [10, 12, 8, 6],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'rbi_delay':  0.,      # This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  False,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  False,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [9, 9, 9, 9],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  55000,
                'max_linearity':  55000.,
                'fullwell_capacity': [85000, 85000, 85000, 85000],
                'read_mode':  'Normal',
                'readout_mode': 'Normal',
                'readout_speed':  0.4,
                'readout_seconds': 6,
                'square_detector': True,
                'areas_implemented': ["600%", "300%", "220%", "150%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'default_rotation': 0.0000,
                'flat_bin_spec': '1,1',    #Default binning for flats
                'smart_stack_exposure_time': 30,
                #'bin_modes':  [[2, 2, 0.9371], [1, 1, 0.4685], [3, 3, 1.4056], [4, 4, 1.8742]],     #Meaning no binning if list has only one entry
                #'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                #'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'darkslide_com':  None,
                'shutter_type': "Electronic",
                
                'flat_bin_spec': ['1,1', '2 2'],    # List of binnings for flats
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683,
                    },
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
        #         'x_start':  0,
        #         'y_start':  0,
        #         'x_width':  6252,
        #         'y_width':  4176,
        #         'x_chip':   6280,
        #         'y_chip':   4210,
        #         'x_pixel':  3.76,
        #         'y_pixel':  3.76,
        #         'overscan_x': 0,
        #         'overscan_y': 0,
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


        # 'camera_4': {
        #     'parent': 'telescope1',
        #     'name': 'zs01',      #Important because this points to a server file structure by that name.
        #     'desc':  'ASI',
        #     'driver':  'ASCOM.FLI.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
        #     'startup_script':  None,
        #     'recover_script':  None,
        #     'shutdown_script':  None,
        #     'detector':  'OSemi 162803Sonyn',
        #     'manufacturer':  'ATIK -- Zwo',
        #     'use_file_mode':  False,
        #     'file_mode_path':  'D:/000ptr_saf/archive/sq01/autosaves/',
        #     'settings': {
        #         'temp_setpoint': -20,
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
}  #This brace closes the while configuration dictionary. Match found up top at:  site_config = {

get_ocn_status = None
get_enc_status = None

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