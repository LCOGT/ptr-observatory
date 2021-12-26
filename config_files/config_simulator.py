# -*- coding: utf-8 -*-
'''
Created by Tim Beccue, 2020-03-16

This is a configuration file designed to simulate an observatory using
ASCOM simulators.

The file is adapted from a version of the WMD config, and is a work in
progress. The key differences are the names of the drivers listed under each
device; they point to the ASCOM simulator drivers that should already be
installed on the computer in order to work.

Most of the numbers in this config file aren't used. However, some of the
site code depends on some of these values. Eventually this should be cleaned.

Modified 20200323 by WER  A simple simulation of an observatory at ALI in Tibet.

'''
import json

site_name = 'DHsim'

site_config = {
    'site': site_name.lower(),
    'name': "Darren's'Simulated Site",
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
    #'archive_path': 'Q:/',     #Really important, this is where state and results are stored. Can be a NAS server.
    'location': 'Goleta CA, USA',
    #'observatory_url': 'https://starz-r-us.sky/clearskies',
    'mpc_code':  'ZZ23',    #This is made up for now.
    'time_offset':  -7,
    'TZ_database_name':  'America/Los_Angeles',
    'timezone': 'PDT',      
    'latitude': 34.35595969,     #Decimal degrees, North is Positive
    'longitude': -119.6851323955,   #Decimal degrees, West is negative
    'elevation': 12,    # meters above sea level
    'reference_ambient':  [15.0],  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  [1010],  #mbar Alternately 12 entries, one for every - mid month.
    'site_in_automatic_default': False,
    'automatic_detail_default': 'Manual default',
    #'observing_conditions': {
        #'wx1': {
            #'parent': 'site',
            #'alias': 'Weather Station #1',
            #'driver': 'redis'
           #
            #},
        #},

    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'alias': 'SimDome',
            'driver': 'ASCOM.Simulator.Dome',
            'has_lights':  'true',
            'is_dome':  'true',
            'controlled_by':  ['mnt1'],
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
                },
            },
        },
# =============================================================================
#     'web_cam': {
#         'web_cam1 ': {
#             'parent': 'enclosure1',
#             'alias': 'MegaCam',
#             'desc':  'AXIS PTZ w control',
#             'driver': 'http://10.15.0.19',
#             'fov':  '90.0',
#             'altitude': '90.0',
#             'azimuth':  '0.0'      #or '180.0 if Pole is low.
#             },
#         #Need to find a way to get this supported and displaying and ultimately logging the 10 micron sky signal.
# =============================================================================

    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'alias': 'mount1_alias',
            #'hostIP':  '10.15.0.30',     #Can be a name if local DNS recognizes it.
            #'hostname':  'eastpier',
            'desc':  'simulator mount',
            'driver': 'ASCOM.Simulator.Telescope',
            #'alignment': 'Alt-Az',
            'has_paddle': 'false',    #or a string that permits proper configuration.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2' by user.  This establishes a default.
            'settings': {
			    'latitude_offset': '0.0',     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': '0.0',   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': '0.0',    # meters above sea level
                'home_park_altitude': '0',   #Having this setting is important for PWI4 where it can easily be messed up.
                'home_park_azimuth': '174.0',
                'horizon':  '20',

            },
        },

    },

    'telescope': {
        'telescope1': {
            'parent': 'mount1',
            'alias': 'Main OTA',
            'desc':  'Planewave CDK 500 F6.8',
            'driver': 'None',                     #Essentially this device is informational.  It is mostly about the optics.
            'collecting_area':  '119773.0',
            'obscuration':  '39%',
            'aperture': '500',
            'f-ratio':  '6.8',   #This and focal_lenght can be refined after a solve.
            'focal_length': '3454',
            'has_dew_heater':  'false',
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'camera_name':  'camera1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  'true',
            'has_cover':  'false',
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': '0.0',    #If the mount model is current, these numbers are usually near 0.0
                                                #for tel1.  Units are arcseconds.
                'offset_declination': '0.0',
                'offset_flexure': '0.0',
                },
        },
    },

    'rotator': {
        'rotator1': {
            'parent': 'telescope1',
            'alias': 'rotator_simulator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.Simulator.Rotator',
            'minimum': '-180.0',
            'maximum': '360.0',
            'step_size':  '0.0001',
            'backlash':  '0.0',
            'unit':  'degree'
            },
    },

#    'screen': {
#        'screen1': {
#            'parent': 'telescope1',
#            'alias': 'screen',
#            'desc':  'Optec Alnitak 24"',
#            'driver': 'COM6',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
#            'minimum': '5.0',   #This is the % of light emitted when Screen is on and nominally at 0% bright.
#            'saturate': '170',  #Out of 0.0 - 255, this is the last value where the screen is linear with output.
#                                #These values have a minor temperature sensitivity yet to quantify.
#
#            },
#    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'alias': 'focuser_simulator',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.Simulator.Focuser',
            'reference':  '5941',    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   '15',      #Update when pinning reference
            'coef_c': '0',   #negative means focus moves out as Primary gets colder
            'coef_0': '0',  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '20300314',
            'minimum': '0',    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': '12700',
            'step_size': '1',
            'backlash':  '0',
            'unit': 'steps',
            'unit_conversion':  '0.090909090909091',
            'has_dial_indicator': 'false'
            },

    },

    #Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "tel1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": ['ASCOM.Simulator.FilterWheel', 'ASCOM.Simulator.FilterWheel'],
            'settings': {
                'filter_count': '23',
                'filter_reference': '2',
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air', '(0, 0)', '-1000', '0.01', '790', 'ai'],   # 0
                                ['dif', '(4, 0)', '0', '0.01', '780', 'di'],   # 1
                                ['w', '(2, 0)', '0', '0.01', '780', 'w_'],   # 2
                                ['ContR', '(1, 0)', '0', '0.01', '175', 'CR'],   # 3
                                ['N2', '(3, 0)', '0', '0.01', '101', 'N2'],   # 4
                                ['u', '(0, 5)', '0', '0.01', '0.2', 'u_'],   # 5
                                ['g', '(0, 6)', '0', '0.01', '550', 'g_'],   # 6
                                ['r', '(0, 7)', '0', '0.01', '630', 'r_'],   # 7
                                ['i', '(0, 8)', '0', '0.01', '223', 'i_'],   # 8
                                ['zs', '(5, 0)', '0', '0.01', '15.3','zs'],   # 9
                                ['PL', '(0, 4)', '0', '0.01', '775', "PL"],   # 10
                                ['PR', '(0, 3)', '0', '0.01', '436', 'PR'],   # 11
                                ['PG', '(0, 2)', '0', '0.01', '446','PG'],   # 12
                                ['PB', '(0, 1)', '0', '0.01', '446', 'PB'],   # 13
                                ['O3', '(7, 0)', '0', '0.01', '130','03'],   # 14
                                ['HA', '(6, 0)', '0', '0.01', '101','HA'],   # 15
                                ['S2', '(8, 0)', '0', '0.01', '28','S2'],   # 16
                                ['dif_u', '(4, 5)', '0', '0.01', '0.2', 'du'],   # 17
                                ['dif_g', '(4, 6)', '0', '0.01', '515','dg'],   # 18
                                ['dif_r', '(4, 7)', '0', '0.01', '600', 'dr'],   # 19
                                ['dif_i', '(4, 8)', '0', '0.01', '218', 'di'],   # 20
                                ['dif_zs', '(9, 0)', '0', '0.01', '14.5', 'dz'],   # 21
                                ['dark', '(10, 9)', '0', '0.01', '0.0', 'dk']],   # 22
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  ['0', '1', '2', '10', '7', '19', '6', '18', '12', '11', '13', '8', '20', '3', \
                                        '14', '15', '4', '16', '9', '21'],  # '5', '17'], #Most to least throughput, \
                                #so screen brightens, skipping u and zs which really need sky.
                'filter_sky_sort':  ['17', '5', '21', '9', '16', '4', '15', '14', '3', '20', '8', '13', '11', '12', \
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
    },

    'sequencer': {
        'sequencer': {
            'parent': 'site',
            'alias': 'Sequencer',
            'desc':  'Automation Control',
            'driver': 'none'
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
        
    #As aboove, need to get this sensibly suported on GUI and in fits headers.
#    'web_cam': {
#
#        'web_cam3 ': {
#            'parent': 'mount1',
#            'alias': 'FLIR',
#            'desc':  'FLIR NIR 10 micron 15deg, sidecam',
#            'driver': 'http://10.15.0.17',
#            'fov':  '15.0',
#            'settings': {
#                'offset_collimation': '0.0',
#                'offset_declination': '0.0',
#                'offset_flexure': '0.0'
#
#                },
#            },
#
#    },


    #Need to put switches here for above devices.

    #Need to build instrument selector and multi-OTA configurations.

    #AWS does not need this, but my configuration code might make use of it.
#    'server': {
#        'server1': {
#            'name': 'QNAP',
#            'win_url': 'archive (\\10.15.0.82) (Q:)',
#            'redis':  '(host=10.15.0.15, port=6379, db=0, decode_responses=True)'
#        },
#    },

#}    #This brace closes the while configuration dictionary. Match found up top at:  site_config = {