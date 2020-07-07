# -*- coding: utf-8 -*-
'''
Created on Fri Feb 07,  11:57:41 2020
Updated 202003115 18:18 WER

@author: wrosing
'''
import json
from pprint import pprint

#NB NB NB json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.

site_name = 'saf'

site_config = {
    'site': site_name,
    'defaults': {
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
    'name': 'Apache Ridge Observatory',
    'location': 'Santa Fe, New Mexico,  USA',
    'site_path':  'D:/000ptr_saf/',    #Path to where all Photon Ranch data and state are to be found
    'observatory_url': 'https://starz-r-us.sky/clearskies2',   #This is meant to be optional
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #i.e, a multi-line text block supplied by the owner.

    'mpc_code':  'ZZ24',    #This is made up for now.
    'time_offset':  '-6.0',
    'timezone': 'MDT',       #We might be smart to require some Python DateTime String Constant here
                             #since this is a serious place where misconfigurations occur.  We run on
                             #UTC and all translations to local time are 'informational.'  PTR will
                             #Not accept observatories whose master clocks run on local time, or where
                             #the longitude and value of UTC disagree by more than a smidegon.
    'latitude': '35.554444',     #Decimal degrees, North is Positive
    'longitude': '-105.870278',   #Decimal degrees, West is negative
    'elevation': '2187',    # meters above sea level
    'reference_ambient':  ['10.0'],  #Degress Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  ['781.0'],  #mbar   A rough guess 20200315

    'observing_conditions' : {
        'observing_conditions1': {
            'parent': 'site',
            'name': 'Boltwood',
            'driver': 'ASCOM.Boltwood.ObservingConditions',
            'driver_2':  'ASCOM.Boltwood.OkToOpen.SafetyMonitor',
            'driver_3':  'ASCOM.Boltwood.OkToImage.SafetyMonitor',
            'has_unihedron':  'true',
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  '13'    #'False" or numeric of COM port.
        },
    },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'name': 'HomeDome',
            'hostIP':  '10.0.0.140',
            'driver': 'ASCOMDome.Dome',
            'has_lights':  'false',
            'controlled_by': 'mount1',
			'is_dome': 'true',
            'mode': 'Automatic',
            'cool_down': '30.0',     #  Minutes prior to sunZ88Op time.
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
            },
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
            'has_paddle': 'false',      #paddle refers to something supported in the python code, not the AP paddle.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2'... by user.  This establishes a default.
            'settings': {
			    'latitude_offset': '0.0',     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': '0.0',   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': '0.0',    # meters above sea level
                'home_park_altitude': '0',
                'home_park_azimuth': '180',
                'horizon':  '20',
                'horizon_detail': {
                     '0': '10',
                     '90': '10',
                     '180': '10',
                     '270': '10',
                },
            },
        },

    },

    'telescope': {
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'desc':  'Ceravolo 300mm F4.9',
            'driver': 'none',                     #Essentially this device is informational.  It is mostly about the optics.
            'collecting_area':  '49303',
            'obscuration':  '55%',
            'aperture': '300',
            'focal_length': '1470',
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
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.OptecGemini.Rotator',
			'com_port':  'COM10',
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
            'name': 'screen',
            'desc':  'Optec Alnitak 16"',
            'driver': 'COM14',  #This needs to be a four or 5 character string as in 'COM8' or 'COM22'
            'minimum': '5.0',   #This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': '255',  #Out of 0.0 - 255, this is the last value where the screen is linear with output.
                                #These values have a minor temperature sensitivity yet to quantify.
                                #THESE ARE STARTING VALUES

        },
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
			'com_port':  'None',
            'reference':  '10065',    #Nominal at 20C Primary temperature
            'ref_temp':   '15',    #Update when pinning reference
            'coef_c': '0',   #negative means focus moves out as Primary gets colder
            'coef_0': '10065',  #Nominal intercept when Primary is at 0.0 C. Looks wrong!
            'coef_date':  '20200615',    #Per Neyle   SWAG
            'minimum': '0',     #NB this area is confusing steps and microns, and need fixing.
            'maximum': '12700',
            'step_size': '1',       #This is probably 0.09090909090909...
            'backlash':  '0',
            'unit': 'micron',
            'unit_conversion': '9.09090909091',
            'has_dial_indicator': 'false'
        },

    },


    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "FLI filter wheel",
            "desc":  'FLI Centerline 50mm round.',
            "driver": 'MAXIM',
            'settings': {
                'filter_count': '13',    # dark filer not implemented yet.
                'filter_reference': '0',   #We choose to use W as the default filter.
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                        ['w',    '(0,  0)',     '0', ' 0.01', ['6   ', ' 20'], 'w '],   # 0 Mul Screen@100% by saturate*exp
                        ['B',    '(1,  0)',     '0', ' 63.6', ['35  ', ' 20'], 'B '],   # 1
                        ['V',    '(2,  0)',     '0', ' 0.01', ['15  ', ' 20'], 'V '],   # 2
                        ['R',    '(3,  0)',     '0', ' 0.01', ['20  ', ' 20'], 'R '],   # 3
                        ["gp",   '(4,  0)',     '0', '114.0', ['13  ', ' 20'], "gp"],   # 4
                        ["rp",   '(5,  0)',     '0', '00.01', ['20  ', ' 20'], "rp"],   # 5
                        ["ip",   '(6,  0)',     '0', '00.01', ['33  ', ' 20'], "ip"],   # 6
                        ['O3',   '(7,  0)',     '0', '09.75', ['360' , '170'], 'O3'],   # 7 430  use 2x215?
                        ['HA',   '(8,  0)',     '0', '09.42', ['360' , '170'], 'HA'],   # 8 4500
                        ['S2',   '(9,  0)',     '0', '09.80', ['360' , '170'], 'S2'],   # 9 6300
                        ['N2',   '(10, 0)',     '0', '09.34', ['360' , '170'], "N2"],   # 10 4700
                        ['EXO',  '(11, 0)',     '0', ' 0.01', ['6.5 ', ' 20'], 'ex'],   # 11
                        ['air',  '(12, 0)', '-1000', ' 0.01', ['4.5 ', ' 20'], 'ai'],   # 12
                        ['dark', '(13, 0)',     '0', ' 0.01', ['15  ', ' 20'], 'dk']]  # 13  20200315 This needs to be set up as a \
                        #  'dark' filter =   cascade of say N2 and B or O3 and i.
                        #Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                'filter_screen_sort':  ['12', '0', '11', '2', '3', '5', '6', '4', '1'],   # don't use narrow yet,  '8', '10', '9'], useless to try.
                'filter_sky_sort':  ['9', '10', '8', '7', '1', '4', '6', '5', '3', '2', '11', '0', '12']  #Least to most throughput
            },
        },
    },


    'camera': {
        'camera1': {
            'parent': 'telescope1',
            'name': 'sq01',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro',
            'driver':  "ASCOM.QHYCCD.Camera",   #"Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera',
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'settings': {
                'temp_setpoint': '-7.5',
                'calib_setpoints': ['-10', '-7.5', '-5', '-7.5' ],  #  Picked by day-of-year mod len(list)
                'day_warm': 'False',
                'cooler_on': 'True',
                'x_start':  '0',
                'y_start':  '0',
                'x_width':  '9600',   #NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  '6422',
                'x_chip':  '9576',   #NB Should specify the active pixel area.   20200315 WER
                'y_chip':  '6388',
                'x_trim_offset':  '8',   #  NB these four entries are guesses.
                'y_trim_offset':  '8',
                'x_bias_start':  '9577',
                'y_bias_start' : '6389',
                'x_pixel':  '3.76',
                'y_pixel':  '3.76',
                'overscan_x': '24',
                'overscan_y': '34',
                'north_offset': '0.0',    #  These three are normally 0.0 for the primary telescope
                'east_offset': '0.0',
                'rotation': '0.0',
                'min_exposure': '0.001',
                'max_exposure': '600.0',
                'can_subframe':  'true',
                'min_subframe':  '128,128',
                'bin_modes':  [['1, 1'], ['2, 2']],     #Meaning no binning if list has only one entry\
                'default_bin':  '1,1',    #Always square and matched to seeing situation by owner
                'readout_time':  ['4', '4'],
                'rbi_delay':  '0',      # This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  'True',
                'can_set_gain':  'True',
                'reference_gain': ['28', '28'],     #One val for each binning.
                'reference_noise': ['2', '2'],    #  NB Guess
                'reference_dark': ['0.2', '0.0'],    #Guesses?
                'saturate':  '55000',
                'area': ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg', 'chip'],  #NB Area does not include overscan.
                'has_darkslide':  'false',
                 #darkslide':  ['Auto', 'Open', 'Close'],
                'has_screen': 'true',
                'screen_settings':  {
                    'screen_saturation':  '157.0',   #This reflects WMD setting and needs proper values.
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
        'sequencer1': {
            'parent': 'site',
            'name': 'Sequencer',
            'desc':  'Automation Control',
            'driver': 'none',


        },
    },

    #I am not sure AWS needs this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': 'none',
            'win_url': 'none',
            'redis':  '(host=none, port=6379, db=0, decode_responses=True)'
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

