# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20200316   WER

@author: wrosing
'''
import json

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

# TIM  I have tried to follow "Photon travel order"

site_name = 'wmd2'    #NB These must be unique across all of PTR.  

site_config = {
    'site': 'wmd2',
    'defaults': {   #TIM this may no longer be needed.  
        'observing_conditions': 'observing_conditions1',
        'enclosure': 'enclosure1',
        'mount': 'mount1',
        'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera1',
        'sequencer': 'sequencer1'
        },
    'name': 'WMD2 0m61 f6.8 Planewave CDK',
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
# =============================================================================
#     'web_cam': {
#         'web_cam1 ': {
#             'parent': 'enclosure1',
#             'name': 'MegaCam',
#             'desc':  'AXIS PTZ w control',
#             'driver': 'http://10.15.0.19',
#             'fov':  '90.0',
#             'altitude': '90.0',
#             'azimuth':  '0.0'      #or '180.0 if Pole is low.
#             },
#         #Need to find a way to get this supported and displaying and ultimately logging the 10 micron sky signal.
# =============================================================================
# =============================================================================
#         'web_cam2 ': {               #currently no support for building this object.
#             'parent': 'enclosure1',
#             'name': 'FLIR',
#             'desc':  'FLIR NIR 10 micron Zenith View 90 deg',
#             'driver': 'http://10.15.0.18',
#             'fov':  '90.0'
#             },
#         },
# =============================================================================
    #Need to eventually add skycam here along with seeing monitor.
    },

"""
Tim: Here is a decision at a site do we number the mounts, or start over with each one.  Since the
about enclosure key 'controlled by' is a list this implies MOUNTS are sequentially numbered if they
share an enclosure.  I think it is simple to numerb all the mounts at a site.

We can start over with Telescope1, 2 etc for each mount without any confusion I believe.
    
"""

    'mount': {
        'mount2': {
            'parent': 'enclosure1',
            'name': 'westpier',
            'hostIP':  '10.15.0.40',     #Can be a name if local DNS recognizes it.
            'hostname':  'westpier',
            'desc':  'Planewave L600 AltAz',
            'driver': 'ASCOM.AltAzDS.Telescope',  #This picks up signals to the rotator from the mount.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'alignment': 'Alt-Az',
            'has_paddle': False,    #or a string that permits proper configuration.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2' by user.  This establishes a default.
            'settings': {
			    'latitude_offset': 0.025,     #Meters North is Positive   These *could* be slightly different than site.
			    'longitude_offset': 0-2.5,   #meters West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': 0.5,    # meters above sea level
                'home_park_altitude': 0,   #Having this setting is important for PWI4 where it can easily be messed up.
                'home_park_azimuth': 1195.0,
                'horizon':  20,
                'horizon_detail': {    #This can vary mount to mount.
                     0: 32,
                     30: 35,
                     36.5: 39,
                     43: 28.6,
                     59: 32.7,
                     62: 28.6,
                     65: 25.2,
                     74: 22.6,
                     82: 20,
                     95.5: 20,
                     101.5: 14,
                     107.5: 12,
                     130: 12,
                     150: 20,
                     172: 28,
                     191: 25,
                     213: 20,
                     235: 15.3,
                     260: 11,
                     272: 17,
                     294: 16.5,
                     298.5: 18.6,
                     303: 20.6,
                     309: 27,
                     315: 32,
                     360: 32,
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
                # 'camera_name':  'camera1',
                # 'filter_wheel_name':  'filter_wheel1',
            'has_instrument_selelector': True,
            'selector_positions':  4,   # Will assume if key is omitted or value is None that there is no selector.
            'instruument names':  ['camera1', 'spectrograph1', 'camera2', 'spectrograph2'],
            'instruument aliases':  ['QHY600Mone', 'Alpy', 'FLI 16803', 'Fiber Echelle'],
            'configuration: {
                 "position1": {
                     'darkslide1','}}
        },

            # 'telescope2': {
            #     'parent': 'mount1',
            #     'name': 'Aux OTA',
            #     'desc':  'Astro=Physics AP185 Refractor',
            #     'driver': None,                     #Essentially this device is informational.  It is mostly about the optics.
            #     'startup_script':  None,
            #     'recover_script':  None,
            #     'shutdown_script':  None,  
            #     'collecting_area':  '26880',
            #     'obscuration':  '0.0%',
            #     'aperture': '585',
            #     'f-ratio':  '7.5',   #This and focal_lenght can be refined after a solve.
            #     'focal_length': '1387.5',
            #     'has_dew_heater':  False,
            #     'screen_name': 'screen2',
            #     'focuser_name':  'focuser2',
            #     'rotator_name':  'rotator2',
            #     'camera_name':  'camera2',
            #     'filter_wheel_name':  None,
            #     'has_fans':  False,
            #     'has_cover':  True,
            #     'settings': {
            #         'fans': [None],
            #         'offset_collimation': '0.0',    #If the mount model is current, these numbers are usually near 0.0
            #                                         #for tel1.  Units are arcseconds.
            #         'offset_declination': '0.0',
            #         'offset_flexure': '0.0',
            #         },
            # },
    },

    'rotator': {
        'rotator1': {
            'parent': 'telescope2',    #NB Note we are changing to an abbrevation. BAD!
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
       # 'rotator2': {
       #      'parent': 'tel2',    #NB Note we are changing to an abbrevation. BAD!
       #      'name': 'Aux Rotator',
       #      'desc':  'Opetc Gemini',
       #      'driver': 'ASCOM.AltAzDS.Rotator2',
       #      'startup_script':  None,
       #      'recover_script':  None,
       #      'shutdown_script':  None , 
       #      'minimum': '-180.0',
       #      'maximum': '360.0',
       #      'step_size':  '0.0001',
       #      'backlash':  '0.0',
       #      'unit':  'degree'
       #      },
    },

    'screen': {
        'screen1': {
            'parent': 'telescope2',
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
      # 'screen2': {
      #       'parent': 'telescope2',
      #       'name': 'screen',
      #       'desc':  'Optec Alnitak 24"',
      #       'driver': 'COM77',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
      #       'startup_script':  None,
      #       'recover_script':  None,
      #       'shutdown_script':  None,  
      #       'minimum': '5.0',   #This is the % of light emitted when Screen is on and nominally at 0% bright.
      #       'saturate': '170',  #Out of 0.0 - 255, this is the last value where the screen is linear with output.
      #                           #These values have a minor temperature sensitivity yet to quantify.
      #       },
    },

    'focuser': {
        'focuser21': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None, 
            'reference':  56500,    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   22.5,      #Update when pinning reference  Larger at lower temperatures.
            'coef_c': -0.0,   #negative means focus moves out as Primary gets colder
            'coef_0': 0,  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '202004510',
            'minimum': 0,    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'step_size': 1,
            'backlash':  0,
            'unit': 'steps',
            'unit_conversion':  0.090909090909091,
            'has_dial_indicator': False
            },
       # 'focuser2': {
       #      'parent': 'telescope2',
       #      'name': 'aux_focuser',
       #      'desc':  'Optec Gemini',
       #      'driver': 'ASCOM.OptecGemini.Focuser2',
       #      'startup_script':  None,
       #      'recover_script':  None,
       #      'shutdown_script':  None, 
       #      'reference':  '5941',    #Nominal at 20C Primary temperature, in microns not steps.
       #      'ref_temp':   '15',      #Update when pinning reference
       #      'coef_c': '0',   #negative means focus moves out as Primary gets colder
       #      'coef_0': '0',  #Nominal intercept when Primary is at 0.0 C.
       #      'coef_date':  '20300314',
       #      'minimum': '0',    #NB this needs clarifying, we are mixing steps and microns.
       #      'maximum': '12700',
       #      'step_size': '1',
       #      'backlash':  '0',
       #      'unit': 'steps',
       #      'unit_conversion':  '0.090909090909091',
       #      'has_dial_indicator': False
       #      },
       
    },

    #Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "tel1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": "Maxim",   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'settings': {
                'filter_count': '23',
                'filter_reference': '2',
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air', '(0, 0)', '-1000','0.01',['2', '17'], 'ai'], # 0
                                ['dif', '(4, 0)', '0', '0.01',   ['2', '17'], 'di'], # 1
                                ['W', '(0, 0)', '0', '0.01',     ['2', '17'], 'w '], # 2
                                ['ContR', '(1, 0)', '0', '0.01', ['2', '17'], 'CR'], # 3
                                ['N2', '(3, 0)', '0', '0.01',    ['2', '17'], 'N2'], # 4
                                ['u', '(0, 5)', '0', '0.01',     ['2', '17'], 'u_'], # 5
                                ['g', '(0, 6)', '0', '0.01',     ['2', '17'], 'g_'], # 6
                                ['r', '(0, 7)', '0', '0.01',     ['2', '17'], 'r_'], # 7
                                ['i', '(0, 8)', '0', '0.01',     ['2', '17'], 'i_'], # 8
                                ['zs', '(5, 0)', '0', '0.01',    ['2', '17'], 'zs'], # 9
                                ['PL', '(0, 4)', '0', '0.01',    ['2', '17'], "PL"], # 10
                                ['PR', '(0, 3)', '0', '0.01',    ['2', '17'], 'PR'], # 11
                                ['PG', '(0, 2)', '0', '0.01',    ['2', '17'], 'PG'], # 12
                                ['PB', '(0, 1)', '0', '0.01',    ['2', '17'], 'PB'], # 13
                                ['O3', '(7, 0)', '0', '0.01',    ['2', '17'], '03'], # 14
                                ['HA', '(6, 0)', '0', '0.01',    ['2', '17'], 'HA'], # 15
                                ['S2', '(8, 0)', '0', '0.01',    ['2', '17'], 'S2'], # 16
                                ['dif_u', '(4, 5)', '0', '0.01', ['2', '17'], 'du'], # 17
                                ['dif_g', '(4, 6)', '0', '0.01', ['2', '17'], 'dg'], # 18
                                ['dif_r', '(4, 7)', '0', '0.01', ['2', '17'], 'dr'], # 19
                                ['dif_i', '(4, 8)', '0', '0.01', ['2', '17'], 'di'], # 20
                                ['dif_zs', '(9, 0)', '0', '0.01',['2', '17'], 'dz'], # 21
                                ['dark', '(10, 9)', '0', '0.01', ['2', '17'], 'dk']],# 22
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  ['0', '1', '2', '10', '7', '19', '6', '18', '12', '11', '13', '8', '20', '3', \
                                        '14', '15', '4', '16'],   #  '9', '21'],  # '5', '17'], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.
                'filter_sky_sort':     ['17', '5', '21', '9', '16', '4', '15', '14', '3', '20', '8', '13', '11', '12', \
                                        '18', '6', '19', '7', '10', '2', '1', '0']  #Least to most throughput

            },
        },
    },



    # A site may have many cameras registered (camera1, camera2, camera3, ...) each with unique aliases -- which are assumed
    # to be the name an owner has assigned and in principle that name "kb01" is labeled and found on the camera.  Between sites,
    # there can be overlap of camera names.  LCO convention is letter of cam manuf, letter of chip manuf, then 00, 01, 02, ...
    # However this code will treat the camera name/alias as a string of arbitrary length:  "saf_Neyle's favorite_camera" is
    # perfectly valid as an alias.


    'camera': {
        'camera2': {
            'parent': 'telescope2',
            'name': 'kf01',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Microline OnSemi 16803',
            'driver':  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work with both.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,  
            'detector':  'OnSemi 162803',
            'manufacturer':  'FLI -- Finger Lakes Instrumentation',
            'settings': {
                'temp_setpoint': -35,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4096,
                'y_width':  34096,
                'x_chip':   4096,
                'y_chip':   4096,
                'x_pixel':  9,
                'y_pixel':  9,
                'overscan_x': 0,
                'overscan_y': 0,
                'north_offset': 0.0,
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.100,
                'max_exposure': 600.0,
                'can_subframe':  True,
                'min_subframe':  '16:16',
                'is_cmos':  False,
                'reference_gain': [1.4, 1.4 ],     #One val for each binning.
                'reference_noise': [14.0, 14.0 ],
                'reference_dark': [0.2, -30 ],
                'saturate':  55000,
                'areas_implemented': [100, 71, 50, 33, 25, 12.5],
                'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],     #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #Always square and matched to seeing situation by owner
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
        
#         'camera2': {
#             'parent': 'telescope2',
#             'name': 'sq01',      #Important because this points to a server file structure by that name.
#             'desc':  'GHY 600Pro',
#             'driver':  "ASCOM.QHYCCD.Camera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work with both.
#             'startup_script':  None,
#             'recover_script':  None,
#             'shutdown_script':  None,  
#             'detector':  'Sony Exmore',
#             'manufacturer':  'QHY',
#             'settings': {
#                 'x_start':  '0',
#                 'y_start':  '0',
#                 'x_width':  '9600',
#                 'y_width':  '6642',
#                 'x_chip':   '9600',
#                 'y_chip':   '6642',
#                 'x_pixel':  '6.0',
#                 'y_pixel':  '6.0',
#                 'overscan_x': '0',
#                 'overscan_y': '0',
#                 'north_offset': '0.0',
#                 'east_offset': '0.0',
#                 'rotation': '0.0',
#                 'min_exposure': '0.001',
#                 'max_exposure': '300',
#                 'can_subframe':  True,
#                 'min_subframe':  '16:16',
#                 'is_cmos_':  False,                
#                 'is_cmos_16':  True,
#                 'bin_modes':  [['1', '1'], ['2', '2']],     #Meaning no binning if list has only one entry
#                 'default_bin':  '1',    #Always square and matched to seeing situation by owner               'reference_gain': ['1.4', '1.4' ],     #One val for each binning.
#                 'reference_noise': ['1.0', '1.0' ],
#                 'reference_dark': ['0.2', '-30' ],
#                 'saturate':  '55000',
#                 'area': ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
#                 'has_shutter':  False,   
#                 'has_darkslide':  False,
#                 'darkslide_option':  'screen_2',
# #                'darkslide':  ['Auto', 'Open', 'Close'],
#                 'has_screen': True,
#                 'screen_settings':  {     # This is meant to be for the specific camera.  NBNBNB Owner cannot simply enter tihs.
#                     'screen_saturation':  '157.0',
#                     'screen_x4':  '-4E-12',  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
#                     'screen_x3':  '3E-08',
#                     'screen_x2':  '-9E-05',
#                     'screen_x1':  '.1258',
#                     'screen_x0':  '8.683'
#                     },
#                 },
#        },
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
    #As aboove, need to get this sensibly suported on GUI and in fits headers.
    # 'web_cam': {

    #     'web_cam3 ': {
    #         'parent': 'mount1',
    #         'name': 'FLIR',
    #         'desc':  'FLIR NIR 10 micron 15deg, sidecam',
    #         'driver': 'http://10.15.0.17',
    #         'startup_script':  None,
    #         'recover_script':  None,
    #         'shutdown_script':  None,  
    #         'fov':  '15.0',
    #         'settings': {
    #             'offset_collimation': '0.0',
    #             'offset_declination': '0.0',
    #             'offset_flexure': '0.0'

    #             },
    #         },

    #},


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
    breakpoint()

