# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019

@author: wrosing
'''
import json

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

site_name = 'wmd'

site_config = {
    'site': 'wmd',
    'alias': 'West Mountain Drive Observatory',
    'location': 'Santa Barbara, Californa,  USA',   #Tim if this does not work for you, propose a change.
    'observatory_url': 'https://starz-r-us.sky/clearskies',   #This is meant to be optional
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #i.e, a multi-line text block supplied by the owner.
                    
    'mpc_code':  'ZZ23',    #This is made up for now.
    'timezone': 'PDT',       #We might be smart to require some Python DateTime String Constant here
                             #since this is a serious place where misconfigurations occur.  We run on
                             #UTC and all translations to local time are 'informational.'  PTR will
                             #Not accept observatories whose master clocks run on local time, or where
                             #the longitude and value of UTC disagree by more than a smidegon.
    'latitude': '34.34293028',     #Decimal degrees, North is Positive
    'longitude': '-119.68112805',   #Decimal degrees, West is negative
    'elevation': '317.75',    # meters above sea level
    'reference_ambient':  ['15.0'],  #Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'observing_conditions': {
        'wx1': {
            'parent': 'site',
            'alias': 'Weather Station #1',
            'driver': 'redis'
            
        },
    },

                
    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'alias': 'Megawan',
            'hostIP':  '10.15.0.30',
            'driver': 'ASCOM.SkyRoofHub.Dome',
            'has_lights':  'true',
            'controlled_by':  ['mnt1', 'mnt2'],
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],                               
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
# =============================================================================
#         'web_cam2 ': {               #currently no support for building this object.
#             'parent': 'enclosure1',
#             'alias': 'FLIR',
#             'desc':  'FLIR NIR 10 micron Zenith View 90 deg',
#             'driver': 'http://10.15.0.18',
#             'fov':  '90.0'
#             },
#         },
# =============================================================================
    #Need to eventually add skycam here along with seeing monitor.
    },
                    
                        

    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'alias': 'eastpier',
            'hostIP':  '10.15.0.30',     #Can be a name if local DNS recognizes it.
            'hostname':  'eastpier',
            'desc':  'Planewave L500 AltAz',
            'driver': 'ASCOM.AltAzDS.Telescope',
            'alignment': 'Alt-Az',
            'has_paddle': 'false',    #or a string that permits proper configuration.
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
        'telescope1': {
            'parent': 'mount1',
            'alias': 'Main OTA',
            'desc':  'Planewave CDK 500 F6.8',
            'driver': 'None',                     #Essentially this device is informational.  It is mostly about the optics.
            'collecting_area':  '119773.0',
            'obscuration':  '39%',
            'aperture': '500',
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
            'parent': 'tel1',
            'alias': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.AltAzDS.Rotator',
            'minimum': '-180.0',
            'maximum': '360.0',
            'step_size':  '0.0001',
            'backlash':  '0.0',     
            'unit':  'degree'
        },
    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'alias': 'screen',
            'desc':  'Optec Alnitak 24"',
            'driver': 'COM22',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
            'minimum': '5.0',   #This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': '170',  #Out of 0.0 - 255, this is the last value where the screen is linear with output.
                                #These values have a minor temperature sensitivity yet to quantify.

        },
    },
                
    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'alias': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
            'reference':  '5941',    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   '15',      #Update when pinning reference
            'coef_c': '0',   #negative means focus moves out as Primary gets colder
            'coef_0': '0',  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '201200129',    #-102.0708 + 12402.224   20190829   R^2 = 0.67  Ad hoc added 900 units.
            'minimum': '0',
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
            "parent": "telescope1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": ['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],
            'settings': {
                'filter_count': '23',
                'filter_reference': '2',
                'filter_screen_sort':  ['0', '1', '2', '10', '7', '19', '6', '18', '12', '11', '13', '8', '20', '3', \
                                        '14', '15', '4', '16', '9', '21'],  # '5', '17'], #Most to least throughput, \
                                        #so screen brightens, skipping u and zs which really need sky.
                'filter_sky_sort':  ['17', '5', '21', '9', '16', '4', '15', '14', '3', '20', '8', '13', '11', '12', \
                                     '18', '6', '19', '7', '10', '2', '1', '0'],  #Least to most throughput
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                                ['air', '(0, 0)', '-1000', '0.01', '790', 'ai'],   # 0Mul Screen@100% by saturate*exp
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
                                ['dark', '(10, 9)', '0', '0.01', '0.0', 'dk']]   # 22
                                #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                                
            },
        },                  
    },

    'camera': {
        'camera1': {
            'parent': 'telescope1',
            'alias': 'df01',      #Important because this points to a server file structure by that name.
            'desc':  'FLI Microline e2vU42DD',
            'driver':  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',  #Code must work with both.
            'settings': {
                'x_start':  '0',
                'y_start':  '0',
                'x_width':  '2048',
                'x_pixel':  '13.5',
                'y_width':  '2048',
                'y_pixel':  '13.5',
                'overscan_x': '0',
                'overscan_y': '0',
                'north_offset': '0.0',
                'east_offset': '0.0',
                'rotation': '0.0',
                'min_exposure': '0.100',
                'max_exposure': '600.0',
                'can_subframe':  'true',
                'min_subframe':  '16:16',
                'is_cmos':  'false',
                'reference_gain': ['1.4', '1.4' ],     #One val for each binning.
                'reference_noise': ['14.0', '14.0' ],
                'reference_dark': ['0.2', '-30' ],
                'area': ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
                'bin_modes':  [['1', '1'], ['2', '2']],     #Meaning no binning if list has only one entry
                                               #otherwise enumerate all xy modes: [[1,1], [1,2], ...[3,2]...]
                'has_darkslide':  'false',
#                'darkslide':  ['Auto', 'Open', 'Close'],
                'has_screen': 'true',
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

    'sequencer': {
        'sequencer': {
            'parent': 'site',
            'alias': 'Sequencer',
            'desc':  'Automation Control',
            'driver': 'none',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'


        },
    },
    #As aboove, need to get this sensibly suported on GUI and in fits headers.            
    'web_cam': {
               
        'web_cam3 ': {
            'parent': 'mount1',
            'alias': 'FLIR',
            'desc':  'FLIR NIR 10 micron 15deg, sidecam',
            'driver': 'http://10.15.0.17',
            'fov':  '15.0',
            'settings': {
                'offset_collimation': '0.0',
                'offset_declination': '0.0',
                'offset_flexure': '0.0'

                },
            },

    },
       


            
    #***NEED to put switches here for above devices.
    
    #Need to build instrument selector and multi-OTA configurations.
    


    #AWS does not need this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': 'QNAP',
            'win_url': 'archive (\\10.15.0.82) (Q:)',
            'redis':  '(host=10.15.0.15, port=6379, db=0, decode_responses=True)'
        },
    },
}

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
        
   