
# -*- coding: utf-8 -*-
'''
Created on Fri Feb 07,  11:57:41 2020
Updated 20200902 WER

@author: wrosing
'''
import json
from pprint import pprint

#  NB NB  Json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.
#  NB NB  My convention is if a value is naturally a float I add a decimal point even to 0.

site_name = 'saf'

site_config = {
    'site': str(site_name),
    'debug_site_mode': False,
    'defaults': {
        'observing_conditions': 'observing_conditions1',  #  These are used as keys, may go away.
        'enclosure': 'enclosure1',
        'screen': 'screen1',
        'mount': 'mount1',
        'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera1',
        'sequencer': 'sequencer1'
        },
    'name': 'Apache Ridge Observatory',
    'location': 'Santa Fe, New Mexico,  USA',
    'site_path':  'D:/000ptr_saf/',    #  Path to where all Photon Ranch data and state are to be found
    'observatory_url': 'https://starz-r-us.sky/clearskies2',   #  This is meant to be optional
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',    #  i.e, a multi-line text block supplied and formatted by the owner.
    'TZ_database_name':  'America/Denver',
    'mpc_code':  'ZZ24',    #  This is made up for now.
    'time_offset':  -6.0,   #  These two keys may be obsolete give the new TZ stuff 
    'timezone': 'MDT',      #  This was meant to be coloquial Time zone abbreviation, alternate for "TX_data..."
    'latitude': 35.55444,     #  Decimal degrees, North is Positive
    'longitude': -105.870278,   #  Decimal degrees, West is negative
    'elevation': 2194,    #  meters above sea level
    'reference_ambient':  [10.],  #  Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  [794.0],    #mbar   A rough guess 20200315

    'observing_conditions' : {
        'observing_conditions1': {
            'parent': 'site',
            'name': 'Boltwood',
            'driver': 'ASCOM.Boltwood.ObservingConditions',
            'driver_2':  'ASCOM.Boltwood.OkToOpen.SafetyMonitor',
            'driver_3':  'ASCOM.Boltwood.OkToImage.SafetyMonitor',
            'has_unihedron':  True,
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  13    #  False, None or numeric of COM port.
        },
    },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'name': 'HomeDome',
            'hostIP':  '10.0.0.140',
            'driver': 'ASCOMDome.Dome',
            'has_lights':  False,
            'controlled_by': 'mount1',
			'is_dome': True,
            'mode': 'Automatic',
            'cool_down': 89.0,     #  Minutes prior to sunset.
            'settings': {
                'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
                                                                        #First Entry is always default condition.
                'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
            },
            'eve_bias_dark_dur':  2.0,   #  hours Duration, prior to next.
            'eve_screen_flat_dur': 1.0,   #  hours Duration, prior to next.
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
            'name': 'safpier',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'safpier',
            'desc':  'AP 1600 GoTo',
            'driver': 'AstroPhysicsV2.Telescope',
            'alignment': 'Equatorial',
            'has_paddle': False,      #paddle refers to something supported in the python code, not the AP paddle.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2'... by user.  This establishes a default.
            'settings': {
			    'latitude_offset': 0.0,     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': 0.0,   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': 0.0,    # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 180.,
                'horizon':  20.,    #  Meant to be a circular horizon.  None if below is filled in.
                'horizon_detail': {  #  Meant to be something to draw on the Skymap with a spline fit.
                     '0.1': 10,
                     '90': 11.2,
                     '180.0': 10,
                     '270': 10,
                },  #  We use a dict because of fragmented azimuth selections.
            },
        },

    },

    'telescope': {                            #Note telescope == OTA  Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'desc':  'Ceravolo 300mm F4.9/F9 convertable',
            'driver': None,                     #  Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 4930,
            'obscuration':  0.55,
            'aperture': 30,
            'focal_length': 2697,   #  Converted to F9, measured 20200905  11.1C
            'has_dew_heater':  False,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   #This is a default for a single instrument system
            'selector_positions': 1,            #Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                 "position1": ["darkslide1", "filter_wheel1", "camera1"]
                 },
            'camera_name':  'camera1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  True,
            'has_cover':  False,
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': 0.0,    #  If the mount model is current, these numbers are usually near 0.0
                                              #  for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ ha_offset': 0.0,  #  new terms.
                'west_flip_ ca_offset': 0.0,
                'west_flip_ dec_offset': 0.0
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
            'desc':  'Optec Alnitak 16"',
            'driver': 'COM14',  #  This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
            'minimum': 5,   #  This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 255,  #  Out of 0 - 255, this is the last value where the screen is linear with output.
                              #  These values have a minor temperature sensitivity yet to quantify.


        },
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
			'com_port':  None,
            'reference':  9896,    #  Nominal at 20C Primary temperature
            'ref_temp':   18.5,    #  Update when pinning reference
            'coef_c': 0.0,   #  negative means focus moves out as Primary gets colder
            'coef_0': 9896,  #  Nominal intercept when Primary is at 0.0 C. Looks wrong!
            'coef_date':  '20200904',    #  pure SWAG  -WER
            'minimum': 0,     #  NB this area is confusing steps and microns, and need fixing.
            'maximum': 12700,
            'step_size': 1,
            'backlash': 0,
            'unit': 'micron',
            'unit_conversion': 9.09090909091,
            'has_dial_indicator': False
        },

    },


    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "FLI filter wheel",
            "desc":  'FLI Centerline 50mm square.',
            "driver": 'MAXIM',  #  'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'settings': {
                'filter_count': 14,
                'home_filter':  0,
                'filter_reference': 0,   #  We choose to use W as the default filter.
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'abbreviation'],
                        ['w',    [0,  0],    0, 249, [0.45,  20], 'w '],   # 0 
                        ['B',    [1,  0],    0,  80, [2   ,  20], 'B '],   # 1
                        ['V',    [2,  0],    0,  69, [.77 ,  20], 'V '],   # 2
                        ['R',    [3,  0],    0,  46, [1.2 ,  20], 'R '],   # 3
                        ["gp",   [4,  0],    0, 147, [.65 ,  20], "gp"],   # 4
                        ["rp",   [5,  0],    0,  45, [1.0 ,  20], "rp"],   # 5
                        ["ip",   [6,  0],    0,  12, [10  , 170], "ip"],   # 6
                        ['O3',   [7,  0],    0, 2.6, [360 , 170], 'O3'],   # 7
                        ['HA',   [8,  0],    0, 0.6, [360 , 170], 'HA'],   # 8
                        ['S2',   [9,  0],    0, 0.7, [360 , 170], 'S2'],   # 9
                        ['N2',   [10, 0],    0, 0.6, [360 , 170], "N2"],   # 10
                        ['EXO',  [11, 0],    0, 112, [0.65,  20], 'ex'],   # 11
                        ['air',  [12, 0], -800, 280, [.32 ,  20], 'ai'],   # 12
                        ['dark', [13, 0],    0,  .1, [30  , 170], 'dk']],  # 13
                        #  'dark' filter =   cascade of say N2 and B or O3 and i.
                        
                'filter_screen_sort':  [12, 0, 11, 2, 3, 5, 4, 1, 6],   #  don't use narrow yet,  8, 10, 9], useless to try.
                
               'filter_sky_sort':  [12, 8]#, 10, 9, 7, 6, 5, 3, 2, 1, 4, 11, 0, 12]  #  Least to most throughput
            },
        },
    },


    'camera': {
        'camera1': {
            'parent': 'telescope1',
            'name': 'sq01',      #  Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro',
            'driver':  "Maxim.CCDCamera",   #  "ASCOM.QHYCCD.Camera",   #  'ASCOM.FLI.Kepler.Camera',
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'D:/000ptr_saf/archive/sq01/autosaves/',
            'settings': {
                'temp_setpoint': -4,
                'calib_setpoints': [-7.5, -6.5, -5.5, -4.5 ],  #  Should vary with season? by day-of-year mod len(list)
                'day_warm': False,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  9600,   #  NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  6422,
                'x_chip':  9576,   #  NB Should specify the active pixel area.   20200315 WER
                'y_chip':  6388,
                'x_trim_offset':  8,   #  NB these four entries are guesses.
                'y_trim_offset':  8,
                'x_bias_start':  9577,
                'y_bias_start' : 6389,
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                'overscan_x': 24,
                'overscan_y': 3,
                'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,     #  Not sure why these three are even here.
                'rotation': 0.0,        #  Probably remove.
                'min_exposure': 0.00001,
                'max_exposure': 600.0,
                'can_subframe':  True,
                'min_subframe':  [128, 128],
                'bin_modes':  [[1, 1], [2, 2], [3, 3], [4, 4]],       #Meaning no binning if list has only one entry
                'default_bin':  [2, 2],    #  Always square and matched to seeing situation by owner
                'readout_time':  [6, 4, 4, 4],
                'rbi_delay':  0.,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color':  False,
                'can_set_gain':  True,
                'bayer_pattern':  None,    #  Need to verify
                'can_set_gain':  True,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Migh these best be pedastal values?
                'saturate':  50000,
                'areas_implemented': [600, 300, 220, 150, "Full", "Sqr", 71, 50,  35, 25, 12],
                'default_area':  "Full",
                'has_darkslide':  False,
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,   #  This reflects WMD setting and needs proper values.
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

if __name__ == '__main__':
    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')

