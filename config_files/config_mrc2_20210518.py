# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20200316   WER

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

site_name = 'mrc2'    #NB These must be unique across all of PTR.  

site_config = {
    'site': site_name.lower(), #TIM this may no longer be needed.  
    'defaults': {   #TIM this may no longer be needed.  
        'observing_conditions': 'observing_conditions1',
        'enclosure': 'enclosure1',
        'mount': 'mount1',
        'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector': 'selector1',
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1',
        },
    'name': 'Mountain Ranch Camp Observatory 0m6f6.8',
    'location': 'Santa Barbara, California,  USA',
    'airport_code': 'SBA',
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne
    'telescope_description':  '0m61 f6.8 Planewave CDK',
    'site_path': 'Q:/',     #Really important, this is where state and results are stored.
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #i.e, a multi-line text block supplied by the owner.  Must be careful about the contents for now.

    'mpc_code':  'ZZ23',    #This is made up for now.
    'time_offset':  -7,
    'TZ_database_name':  'America/Los_Angeles',
    'timezone': 'PDT',      
    'latitude': 34.34595969,     #Decimal degrees, North is Positive
    'longitude': -119.6811323955,   #Decimal degrees, West is negative
    'elevation': 317.75,    # meters above sea level
    'reference_ambient':  [15.0],  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  [973],  #mbar Alternately 12 entries, one for every - mid month.
    'site_in_automatic_default': False,
    'automatic_detail_default': 'Manual default',
    'observing_conditions': {
        'observing_conditions1': {
            'parent': 'site',
            'name': 'Weather Station #1',
            'driver': 'redis'

            },
        },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'name': 'Megawan',
            'hostIP':  '10.15.0.30',
            'driver': 'ASCOM.SkyRoofHub.Dome',   # NB this is clearly wrong, use redis on each side.
            'recover_script':  None,
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
            },

    #Need to eventually add skycam here along with seeing monitor.
    },



    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'name': 'westpier',
            'hostIP':  '10.15.0.40',     #Can be a name if local DNS recognizes it.
            'hostname':  'westpier',
            'desc':  'Planewave L600 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',  #This picks up signals to the rotator from the mount.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'alignment': 'Alt-Az',
            'has_paddle': False,    #or a string that permits proper configuration.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2' by user.  This establishes a default.
            'east_ra_correction': 0.0,
            'east_dec_correction': 0.0,
            'settings': {
 			    'latitude_offset': 0.025,     #Meters North is Positive   These *could* be slightly different than site.
 			    'longitude_offset': 0-2.5,   #meters West is negative  #NB This could be an eval( <<site config data>>))
 			    'elevation_offset': 0.5,    # meters above sea level
                'home_park_altitude': 0,   #Having this setting is important for PWI4 where it can easily be messed up.
                'home_park_azimuth': 1195.0,
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
                },
            },
    },

    'telescope': {
        'telescope1': {
            'parent': 'mount2',
            'name': 'Main OTA',
            'desc':  'Planewave CDK 600 F6.8',   #i seem to use desc, an alias more or less for the same thing.
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

            'has_fans':  True,
            'has_cover':  True,
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': 0.0,    #If the mount model is current, these numbers are usually near 0.0
                                                #for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
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
            'parent': 'telescope1',    #NB Note we are changing to an abbrevation. BAD!
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.AltAzDS.Rotator',
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None , 
            'minimum': -180.0,
            'maximum': 360.0,
            'step_size':  0.0001,
            'backlash':  0.0,
            'unit':  'degree'
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
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None, 
            'reference':  6500,    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   22.5,      #Update when pinning reference  Larger at lower temperatures.
            'coef_c': -0.0,   #negative means focus moves out as Primary gets colder
            'coef_0': 6000,  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '202004501',
            'minimum': 0,    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'step_size': 1,
            'backlash':  0,
            'unit': 'steps',
            'unit_conversion':  0.090909090909091,
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
            'instruments':  ['main_camera', 'eShel', 'eye_piece', 'UVEX'],
            'cameras':  ['camera_1_1', 'camera_1_2', 'none', 'camera_1_4'],
            'guiders':  [None, 'guider_1_2', None, 'guide_1_4'],
            'default': 0
            },

    },

    #Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    #FW's may need selector-like treatment 
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "tel1",
            "alias": "Dual filter wheel",
            'dual_wheel':  True,
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": ['ASCOM.Apogee.FilterWheel', 'ASCOM.Apogee2.FilterWheel'],
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'settings': {
                'filter_count': '20',
                'filter_reference': '1',
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air',     [0, 0], -1000, 0.01, [2, 17], 'ai'],   # 0
                                ['w',       [1, 0],     0, 0.01, [2, 17], 'w '],   # 1
                                ['dif',     [2, 0],     0, 0.01, [2, 17], 'df'],   # 2
                                ['O3',      [3, 0],     0, 0.01, [2, 17], 'CO'],   # 3
                                ['HA',      [4, 0],     0, 0.01, [2, 17], 'HA'],   # 4
                                ['N2',      [5, 5],     0, 0.01, [2, 17], 'S2'],   # 5
                                ['S2',      [6, 6],     0, 0.01, [2, 17], 'N2'],   # 6
                                ['B',       [0, 1],     0, 0.01, [2, 17], 'B '],   # 7
                                ['g',       [0, 2],     0, 0.01, [2, 17], 'g '],   # 8
                                ['V',       [0, 3],     0, 0.01, [2, 17], 'V '],   # 9
                                ['r',       [0, 4],     0, 0.01, [2, 17], 'r '],  # 10
                                ['i',       [0, 5],     0, 0.01, [2, 17], 'i '],  # 11
                                ['EXO',     [0, 6],     0, 0.01, [2, 17], 'EX'],  # 12
                                ['dif_B',   [2, 1],     0, 0.01, [2, 17], 'Ha'],  # 13
                                ['dif_g',   [2, 2],     0, 0.01, [2, 17], 'dg'],  # 14
                                ['dif_V',   [2, 3],     0, 0.01, [2, 17], 'dV'],  # 15
                                ['dif_r',   [2, 5],     0, 0.01, [2, 17], 'dr'],  # 16
                                ['dif_i',   [2, 6],     0, 0.01, [2, 17], 'di'],  # 17
                                ['dif_EXO', [2, 0],     0, 0.01, [2, 17], 'dE'],  # 18
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
    
    #Ultimately every camera needs a specific configuration file.


    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'kf01',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Microline OnSemi 16803',
            'driver':  'ASCOM.FLI.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'OnSemi 162803',
            'manufacturer':  'FLI -- Finger Lakes Instrumentation',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/sq01/autosaves/',
            'settings': {
                'temp_setpoint': -35,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4096,
                'y_width':  4096,
                'x_chip':   4096,
                'y_chip':   4096,
                'x_pixel':  9,
                'y_pixel':  9,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.25,  #Need to check this setting out
                'max_exposure': 360.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  False,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  False,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  50000,
                'square_detector': True,
                'areas_implemented': ["600%", "300%", "220%", "150%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                    },
                },
        },
        'camera_1_2': {
            'parent': 'telescope1',
            'name': 'sq02',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 268M',
            'driver':  'ASCOM.QHYCCD.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'Sony IMX571',
            'manufacturer':  'QHY -- http://QHYCCD.COM',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/sq02/autosaves/',
            'settings': {    #NB Need to add specification for chiller and its control
                'temp_setpoint': -10,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  6252,
                'y_width':  4176,
                'x_chip':   6280,
                'y_chip':   4210,
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.00003,  #Need to check this setting out
                'max_exposure': 3600.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  False,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  False,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  50000,
                'square_detector': True,
                'areas_implemented': [ "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                    },
                },
        },
        'camera_1_4': {
            'parent': 'telescope1',
            'name': 'zs01',      #Important because this points to a server file structure by that name.
            'desc':  'ASI',
            'driver':  'ASCOM.FLI.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'OSemi 162803Sonyn',
            'manufacturer':  'ATIK -- Zwo',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/sq01/autosaves/',
            'settings': {
                'temp_setpoint': -20,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4096,
                'y_width':  4096,
                'x_chip':   4096,
                'y_chip':   4096,
                'x_pixel':  9,
                'y_pixel':  9,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.25,  #Need to check this setting out
                'max_exposure': 360.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  True,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  False,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  50000,
                'square_detector': True,
                'areas_implemented': [ "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                    },
                },
        },
        'ag_1_2': {
            'parent': 'telescope1',
            'name': 'ag02',      #Important because this points to a server file structure by that name.
            'desc':  'QHY Uncooled Guider',
            'driver':  'ASCOM.QHYCCD_GUIDER.Camera',   #'OM.FLI.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'Sony',
            'manufacturer':  'QHY -- Finger Lakes Instrumentation',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/ag02/autosaves/',
            'settings': {
                'temp_setpoint': 10,
                'cooler_on': False,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4096,
                'y_width':  4096,
                'x_chip':   4096,
                'y_chip':   4096,
                'x_pixel':  9,
                'y_pixel':  9,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.001,  #Need to check this setting out
                'max_exposure': 360.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  True,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  False,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  50000,
                'square_detector': False,
                'areas_implemented': ["Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'bin_modes':  [[1, 1], [2, 2]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                    },
                },
        },
        'ag_1_4': {
            'parent': 'telescope1',
            'name': 'ag04',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 174M',
            'driver':  'ASCOM.QHYCCD_CAM2.Camera',   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work withall three
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'Sony',
            'manufacturer':  'QHY --  ',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/ag04/autosaves/',
            'settings': {
                'temp_setpoint': -15,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4096,
                'y_width':  4096,
                'x_chip':   4096,
                'y_chip':   4096,
                'x_pixel':  9,
                'y_pixel':  9,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.25,  #Need to check this setting out
                'max_exposure': 360.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  True,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  True,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                'saturate':  50000,
                'square_detector': False,
                'areas_implemented': [ "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'bin_modes':  [[1, 1], [2, 2]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
                'cycle_time':  [18, 15, 12, 9],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                    },
                },
        },
    },

    'sequencer': {
        'sequencer2': {
            'parent': 'site',
            'name': 'Sequencer',
            'desc':  'Automation Control',
            'driver': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None, 
        },
    },

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

if __name__ == '__main__':
    '''
    This is a simple test to send and receive via json.
    '''

    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    else:
        print("Strings did not match.")
    if site_config == site_unjasoned:
        print('Dictionaries matched.')
    else:
        print('Dictionaries did not match.')
