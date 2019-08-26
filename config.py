# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019

@author: wrosing
'''
import json

#NB NB NB json is not bi-directional with tuples (), use lists [] instead.

site_name = 'wmd'

site_config = {
    'site': 'wmd',
    'alias': 'West Mountain Drive Observatory',
    'location': 'Santa Barbara, Californa,  USA',   #Tim if this does not work for you, \
                                                     #propose a change.
    'observatory_url': 'https://starz-r-us.sky/clearskies',   #This is meant to be optional
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we loose charge of our democracy.''',    #i.e, a multipline text block supplied by the owner.
                    
    'mpc_code':  'ZZ23',
    'timezone': 'PDT',       #We might be smart to require some Python DateTime String Constant here
                             #since this is a serious place where misconfigurations occur.  We run on
                             #UTC and all translations to local time are 'informational.'  PTR will
                             #Not accept observatories whose master clocks run on local time, or where
                             #the longitude and value of UTC disagree by more than a hour or so.
    'latitude': '34.34293028',
    'longitude': '-119.68112805',
    'elevation': '317.75',    # meters above sea level
    'reference_ambient':  ['12.1'],  #Alternately 12 entries, one for every - mid month.
    'observing_conditions': {
        'wx1': {
            'parent': 'site',
            'alias': 'Weather Station #1',
            'driver': 'redis'
            
        },
    },

                
    'enclosure': {
        'encl1': {
            'parent': 'site',
            'alias': 'Megawan',
            'driver': 'ASCOM.SkyRoof.Dome',
            'has_lights':  'true',
            'controlled_by':  ['mnt1', 'mnt2'],
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],                               
            },
        },
    },
                    
                        

    'mount': {
        'mnt1': {
            'parent': 'encl1',
            'alias': 'eastpier',
            'hostIP':  '10.15.0.30',     #Can be a name if local DNS recognizes it.
            'hostname':  'eastpier',
            'desc':  'Planewave L500 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',
            'alignment': 'Alt-Az',
            'pointing_tel': 'tel1',     #This can be changed to 'tel2' by user.  This establishes a default.
            'settings': {
                'lattitude': '34.34293028',   #These could in principle be different than site by  small amount
                'longitude': '-119.68105',
                'elevation': '317.75', # meters above sea level
                'home_park_altitude': '0',
                'home_park_azimuth': '174.0',
                'horizon':  '20',
                'horizon_detail': {
                     '0': '32',
                     '30': '35',
                     '36.5': '39',
                     '43': '28.6',
                     '59': '32.7',
                     '62': '28.6',
                     '65': '25.2',
                     '74': '22.6',
                     '82': '20',
                     '95.5': '20',
                     '101.5': '14',
                     '107.5': '12',
                     '130': '12',
                     '150': '20',
                     '172': '28',
                     '191': '25',
                     '213': '20',
                     '235': '15.3',
                     '260': '11',
                     '272': '17',
                     '294': '16.5',
                     '298.5': '18.6',
                     '303': '20.6',
                     '309': '27',
                     '315': '32',
                     '360': '32',
                },
            },
        },

    },

    'telescope': {
        'tel1': {
            'parent': 'mnt1',
            'alias': 'main OTA',
            'desc':  'Planewave CDK 450mm F6',
            'driver': 'None',                     #Essentially this device is informational.  It is mostly about optics.
            'collecting_area':  '146438.0',
            'obscuration':  '33%',
            'aperture': '450.0',
            'focal_length': '2457.3',
            'has_dew_heater':  'true',
            'has_fans':  'true',
            'has_cover':  'false',
            'has_screen':  'true',    #Screen is in FRONT of cover
                'settings': {
                    'dew_heater': ['Auto', 'On', 'Off'],
                    'fans': ['Auto','High', 'Low', 'Off'],
                    'screen': {
                               'saturate':  '157',
                               'screen_gain':  '12.3'},

                    'offset_collimation': '0.0',
                    'offset_declination': '0.0',
                    'offset_flexure': '0.0',
            },
        },
    },
  
    'rotator': {
        'rotator1': {
            'parent': 'tel1',
            'alias': 'rotator',
            'desc':  'Planewave IRF PWI3',
            'driver': 'ASCOM.PWI3.Rotator',
            'minimum': '-180.0',
            'maximum': '360.0',
            'step_size':  '0.0001',
            'unit':  'degree'
        },
    },

    'screen': {
        'screen1': {
            'parent': 'tel1',
            'alias': 'screen',
            'desc':  'Optec Alnitak 24"',
            'driver': 'COM22',
            'minimum': '5.0',
            'saturate': '170',  #out of 0.0 - 255

        },
    },
                
    'focuser': {
        'focuser1': {
            'parent': 'tel1',
            'alias': 'focuser',
            'desc':  'Planewave IRF PWI3',
            'driver': 'ASCOM.PWI3.Focuser',
            'reference':  '9986',    #Nominal at 20C Primary temperature
            'coef_c': '-164.0673',   #negative means focus moves out as Primary gets colder
            'coef_0': '13267.37  ',  #Nominal intercept when Primary is at 0.0 C.
            'minimum': '0.0',
            'maximum': '25200',
            'step_size': '1.0',
            'unit': 'micron',
            'has_dial_indicator': 'false'
        },

    },


    'filter_wheel': {
        "filter_wheel1": {
            "parent": "tel1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": ['ASCOM.FLI.FilterWheel', 'ASCOM.FLI.FilterWheel1'],
            'settings': {
                'filter_count': '23',
                'filter_reference': '2',
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gainb'],
                                ['air', '(0, 0)', '-1000', '0.01', '369.0'],
                                ['dif', '(4, 0)', '0', '0.01', '8.18'],
                                ['w', '(2, 0)', '0', '0.01', '4.355'],
                                ['ContR', '(1, 0)', '0', '0.01', '334.0'],
                                ['N2', '(3, 0)', '0', '0.01', '0.585'],
                                ['u', '(0, 5)', '0', '0.01', '4.23'],
                                ['g', '(0, 6)', '0', '0.01', '5.165'],
                                ['r', '(0, 7)', '0', '0.01', '3.105'],
                                ['i', '(0, 8)', '0', '0.01', '0.541'],
                                ['zs', '(5, 0)', '0', '0.01', '0.042'],
                                ['PL', '(0, 4)', '0', '0.01', '334.0'],
                                ['PR', '(0, 3)', '0', '0.01', '83.00'],
                                ['PG', '(0, 2)', '0', '0.01', '80.0'],
                                ['PB', '(0, 1)', '0', '0.01', '80.0'],
                                ['O3', '(7, 0)', '0', '0.01', '136.0'],
                                ['HA', '(6, 0)', '0', '0.01', '194.0'],
                                ['S2', '(8, 0)', '0', '0.01', '30.0'],
                                ['dif_u', '(4, 5)', '0', '0.01', '4.0'],
                                ['dif_g', '(4, 6)', '0', '0.01', '5.0'],
                                ['dif_r', '(4, 7)', '0', '0.01', '3.0'],
                                ['dif_i', '(4, 8)', '0', '0.01', '0.5'],
                                ['dif_zs', '(9, 0)', '0', '0.01', '0.04'],
                                ['dark', '(10, 9)', '0', '0.01', '0.0']]
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 100  20190731 measured.
            },
        },                  
    },

    'camera': {
        'cam1': {
            'parent': 'tel1',
            'alias': 'gf01',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Kepler 400',
            'driver':  'ASCOM.FLI.Kepler.Camera',
            'settings': {
                'x_start':  '256',
                'y_start':  '256',
                'x_width':  '1536',
                'y_width':  '1536',
                'overscan_x': '0',
                'overscan_y': '0',
                'north_offset': '0.0',
                'east_offset': '0.0',
                'rotation': '0.0',
                'min_exposure': '0.200',
                'max_exposure': '120.0',
                'can_subframe':  'true',
                'area': ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
                'bin_modes': [['1', '1']],     #Meaning no binning.
                                               #otherwise enumerate all xy modes: [[1,1], [1,2], ...[3,2]...]
                'has_darkslide':  'false',
                'has_screen': 'true',
#                'darkslide':  ['Auto', 'Open', 'Close'],
                'screen_settings':  {
                    'screen_saturation':  '157.0',
                    'screen_x4':  '-4E-12',  #'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  '3E-08',
                    'screen_x2':  '-9E-05',
                    'screen_x1':  '.1258',
                    'screen_x0':  '8.683' 
                },
            },
        },
                   
    },


    'web_cam': {
        'web_cam1 ': {
            'parent': 'encl1',
            'alias': 'MegaCam',
            'desc':  'AXIS PTZ w control',
            'driver': 'http://10.15.0.19',
            'fov':  '90.0',
            'altitude': '90.0',
            'azimuth':  '0.0'      #or '180.0'
            },
                
        'web_cam3 ': {
            'parent': 'mnt1',
            'alias': 'FLIR',
            'desc':  'FLIR NIR 10 micron 15deg.',
            'driver': 'http://10.15.0.17',
            'fov':  '15.0',
            'settings': {
                'offset_collimation': '0.0',
                'offset_declination': '0.0',
                'offset_flexure': '0.0'

                },
            },
        'web_cam2 ': {
            'parent': 'encl1',
            'alias': 'FLIR',
            'desc':  'FLIR NIR 10 micron Zenith View 90 deg',
            'driver': 'http://10.15.0.18',
            'fov':  '90.0'
            },
    },
       


            
    #***NEED to put switches here for above devices.
    


    #I am not sure AWS needs this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': 'QNAP',
            'win_url': 'archive (\\10.15.0.82) (Q:)',
            'redis':  '(host=10.15.0.15, port=6379, db=0, decode_responses=True)'
        },
    },
}

if __name__ == '__main__':
    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')