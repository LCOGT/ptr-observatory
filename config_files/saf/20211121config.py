
# -*- coding: utf-8 -*-
'''
Created on Fri Feb 07,  11:57:41 2020
Updated 20200902 WER

@author: wrosing
'''
import json
#from pprint import pprint

#  NB NB  Json is not bi-directional with tuples (), use lists [], nested if tuples as needed, instead.
#  NB NB  My convention is if a value is naturally a float I add a decimal point even to 0.

site_name = 'saf'

site_config = {
    'site': str(site_name.lower()),
    'debug_site_mode': False,
    'owner':  ['google-oauth2|102124071738955888216', 'google-oauth2|112401903840371673242'],  # Neyle,  Or this can be some aws handle.
    'owner_alias': ['ANS'],
    'admin_aliases': ["ANS", "WER", "TB", "DH", "KVH", 'KC'],
    'agent_wms_enc_active':  True,    #True if the agent is used at a site.
    'redis_ip': '127.0.0.1',   #None if no redis path present, localhost if redis is self-contained
    'defaults': {
        'observing_conditions': 'observing_conditions1',  #  These are used as keys, may go away.
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
    'name': 'Apache Ridge Observatory 0m3f4.9/9',
    'airport_code':  'SAF', 
    'location': 'Santa Fe, New Mexico,  USA',
    'site_path':  'F:/',    #  Path to where all Photon Ranch data and state are to be found
    'aux_archive_path': '//house-computer/saf_archive_2/archive/',  #  Path to auxillary backup disk not on this host.
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
    'latitude': 35.554298,     #  Decimal degrees, North is Positive
    'longitude': -105.870197,   #  Decimal degrees, West is negative
    'elevation': 2194,    #  meters above sea level
    'reference_ambient':  [10],  #  Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  [794.0],    #mbar   A rough guess 20200315
    
    'site_in_automatic_default': "Automatic",   #  ["Manual", "Shutdown", "Automatic"]
    'automatic_detail_default': "Enclosure is initially set to Automatic mode.",
    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': True,
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': False,
    're-calibrate_on_solve': True, 
    

    'observing_conditions' : {
        'observing_conditions1': {
            'parent': 'site',
            'name': 'Boltwood',
            'driver': 'ASCOM.Boltwood.ObservingConditions',
            'driver_2':  'ASCOM.Boltwood.OkToOpen.SafetyMonitor',
            'driver_3':  'ASCOM.Boltwood.OkToImage.SafetyMonitor',
            'redis_ip': '127.0.0.1',   #None if no redis path present
            'has_unihedron':  True,
            'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
            'unihedron_port':  10    #  False, None or numeric of COM port.
        },
    },


    'enclosure': {
        'enclosure1': {
            'parent': 'site',
            'name': 'HomeDome',
            'hostIP':  '10.0.0.140',
            'driver': 'ASCOMDome.Dome',  #'ASCOM.DigitalDomeWorks.Dome',  #  ASCOMDome.Dome',  #  ASCOM.DeviceHub.Dome',  #  ASCOM.DigitalDomeWorks.Dome',  #"  ASCOMDome.Dome',
            'has_lights':  False,
            'controlled_by': 'mount1',
			'is_dome': True,
            'mode': 'Manual',
            
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
            'default_zenith_avoid': 0.0,   #degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            'pointing_tel': 'tel1',     #This can be changed to 'tel2'... by user.  This establishes a default.
            'west_ha_correction_r':  0.0, #-52*0.5751/3600/15,    #incoming unit is pixels, outgoing is min or degrees. 20201230
            'west_dec_correction_r': 0.0, #356*0.5751/3600,  #Altair was Low and right, so too South and too West.
            'settings': {
			    'latitude_offset': 0.0,     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': 0.0,   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': 0.0,    # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 180.,
                'horizon':  20.,    #  Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  #  Meant to be something to draw on the Skymap with a spline fit.
                     '0.1': 10,
                     '90': 11.2,
                     '180.0': 10,
                     '270': 10,
                     '360': 10
                     },  #  We use a dict because of fragmented azimuth mesurements.
                'refraction_on': True, 
                'model_on': True, 
                'rates_on': True,
                'model': {
                    'IH': 0.0,
                    'ID': 0.0,
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

    },

    'telescope': {                            #Note telescope == OTA  Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'desc':  'Ceravolo 300mm F4.9/F9 convertable',
            'driver': None,                     #  Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 31886,
            'obscuration':  0.55,
            'aperture': 30,
            'focal_length': 1470, #1470,   #2697,   #  Converted to F9, measured 20200905  11.1C
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
            #F4.9 setup
            'reference': 5016,    #  20210313  Nominal at 10C Primary temperature
            'ref_temp':  5.1,    #  Update when pinning reference
            'coef_c': 26.055,   #  Negative means focus moves out as Primary gets colder
            'coef_0': 4905,  #  Nominal intercept when Primary is at 0.0 C. 
            'coef_date':  '20211005',    #This appears to be sensible result 44 points -13 to 3C'reference':  6431,    #  Nominal at 10C Primary temperature
            # #F9 setup
            # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
            # 'ref_temp':  27.,    #  Update when pinning reference
            # 'coef_c': -78.337,   #  negative means focus moves out as Primary gets colder
            # 'coef_0': 5969,  #  Nominal intercept when Primary is at 0.0 C. 
            # 'coef_date':  '20210903',    #  SWAG  OLD: This appears to be sensible result 44 points -13 to 3C
            'minimum': 0,     #  NB this area is confusing steps and microns, and need fixing.
            'maximum': 12600,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'unit': 'micron',
            'unit_conversion': 9.09090909091,
            'has_dial_indicator': False
        },

    },

    'selector': {
        'selector1': {
            'parent': 'telescope1',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': 'Null',
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
    
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "LCO filter wheel FW50_001d",
            'service_date': '20110716',
            "driver": "LCO.dual",  #  'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'ip_string': 'http://10.0.0.110',
            "dual_wheel": True,
            'settings': {
                'filter_count': 38,
                'home_filter':  0,
                'default_filter': "w",
                'filter_reference': 7,   #  We choose to use W as the default filter.  Gains taken at F9, Ceravolo 300mm
                'filter_data': [['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'generic'],
                        
                        ['air',  [0,  0], -800, 81.2, [2   ,  20], 'ai'],    # 0.  Gains 20211020 Clear NE sky
                        ['w',    [7,  0],    0, 72.8, [360 , 170], 'w '],    # 1.
                        ['up',   [1,  0],    0, 2.97, [2   ,  20], 'up'],    # 2.
                        ['gp',   [2,  0],    0, 52.5, [.77 ,  20], 'gp'],    # 3.
                        ['rp',   [3,  0],    0, 14.5, [1.2 ,  20], 'rp'],    # 4.
                        ['ip',   [4,  0],    0, 3.35, [.65 ,  20], 'ip'],    # 5.
                        ['z',    [5,  0],    0, .419, [1.0 ,  20], 'zs'],    # 6.
                        ['zp',   [0,  9],    0, .523, [360 , 170], 'zp'],    # 7.
                        ['y',    [6,  0],    0, .057, [360 , 170], 'y '],    # 8.
                        ['EXO',  [8,  0],    0, 34.2, [360 , 170], 'ex'],    # 9.
                        ['JB',   [9,  0],    0, 32.4, [0.65,  20], 'BB'],    #10.
                        ['JV',   [10, 0],    0, 23.3, [.32 ,  20], 'BV'],    #11.
                        ['Rc',   [11, 0],    0, 14.3, [10  , 170], 'BR'],    #12.
                        ['Ic',   [12, 0],    0, 2.17, [360 , 170], 'BI'],    #13.
                        ['PL',   [7,  0],    0, 72.7, [360 , 170], 'PL'],    #14.
                        ['PR',   [0,  8],    0, 11.0, [.32 ,  20], 'PB'],    #15.
                        ['PG',   [0,  7],    0, 18.6, [30  , 170], 'PG'],    #16.
                        ['PB',   [0,  6],    0, 42.3, [360 , 170], 'PR'],    #17.
                        ['NIR',  [0, 10],    0, 3.06, [0.65,  20], 'ni'],    #18.
                        ['O3',   [0,  2],    0, 1.84, [360 , 170], 'O3'],    #19.
                        ['HA',   [0,  3],    0, .400, [360 , 170], 'HA'],    #20.
                        ['N2',   [13, 0],    0, .233, [360 , 170], 'N2'],    #21.
                        ['S2',   [0,  4],    0, .221, [0.65,  20], 'S2'],    #22.
                        ['CR',   [0,  5],    0, .425, [360 , 170], 'Rc'],    #23.
                        ['dark', [5,  6],    0, 0.20, [360 , 170], 'dk'],    #24
                        ['dif',  [0,  1],    0, 0.21, [360 , 170], 'df'],    #25
                        ['difw',   [7,  1],  0, 300., [0.65,  20], 'dw'],    #26.
                        ['difup',  [1,  1],  0, 10.5, [0.65,  20], 'du'],    #27.
                        ['difgp',  [2,  1],  0, 234,  [0.65,  20], 'dg'],    #28.
                        ['difrp',  [3,  1],  0, 70.0, [0.65,  20], 'dr'],    #29.
                        ['difip',  [4,  1],  0, 150., [0.65,  20], 'di'],    #30.
                        ['difz',   [5,  1],  0, 0.73, [0.65,  20], 'ds'],    #31.
                        ['dify',   [6,  1],  0, 0.15, [0.65,  20], 'dY'],    #32.
                        ['difEXO', [8,  1],  0, 161., [0.65,  20], 'dx'],    #33.
                        ['difJB',  [9,  1],  0, 42.5, [0.65,  20], 'dB'],    #34.
                        ['difJV',  [10, 1],  0, 33.0, [0.65,  20], 'dV'],    #35.
                        ['difRc',  [11, 1],  0, 22.2, [0.65,  20], 'dR'],    #36.
                        ['difIc',  [12, 1],  0, 10. , [0.65,  20], 'dI']],   #37.        38 valid entries, only 36 useable.
                'filter_screen_sort':  [12, 0, 11, 2, 3, 5, 4, 1, 6],   #  don't use narrow yet,  8, 10, 9], useless to try.
                
                
                'filter_sky_sort': [8, 22, 21, 20, 23, 6, 7, 19, 2, 13, 18, 5, 15,\
                                    12, 4, 11, 16, 10, 9, 17, 3, 14, 1, 0]    #No diffuser based filters
                #'filter_sky_sort': [7, 19, 2, 13, 18, 5, 15,\
                #                    12, 4, 11, 16, 10, 9, 17, 3, 14, 1, 0]    #basically no diffuser based filters
                #[32, 8, 22, 21, 20, 23, 31, 6, 7, 19, 27, 2, 37, 13, 18, 30, 5, 15, 36, 12,\
                 #                   29, 4, 35, 34, 11, 16, 10, 33, 9, 17, 28, 3, 26, 14, 1, 0]                   

                                    
            },
        },
    },
        
    'lamp_box': {
        'lamp_box1': {
            'parent': 'camera_1_1',  # Parent is camera for the spectrograph
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
            'name': 'sq002',      #  Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro',
            'service_date': '20211111',
            'driver': "ASCOM.QHYCCD.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ##  'ASCOM.FLI.Kepler.Camera',
            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'G:/000ptr_saf/archive/sq01/autosaves/',

            'settings': {
                'temp_setpoint': -10,
                'calib_setpoints': [-10, -7.5, -6.5, -5.5, -4.0 ],  #  Should vary with season? by day-of-year mod len(list)
                'day_warm': False,
                'cooler_on': True,
                'x_start':  0,
                'y_start':  0,
                'x_width':  4800,   #  NB Should be set up with overscan, which this camera is!  20200315 WER
                'y_width':  3211,
                'x_chip':  9576,   #  NB Should specify the active pixel area.   20200315 WER
                'y_chip':  6388,
                'x_trim_offset':  8,   #  NB these four entries are guesses.
                'y_trim_offset':  8,
                'x_bias_start':  9577,
                'y_bias_start' : 6389,
                'x_active': 4784,
                'y_active': 3194,
                'x_pixel':  3.76,
                'y_pixel':  3.76,
                'pix_scale': 1.0551,     #  asec/pixel F9   0.5751  , F4.9  1.0481         
                'x_field_deg': 1.3928,   #   round(4784*1.0481/3600, 4),
                'y_field_deg': 0.9299,   #  round(3194*1.0481/3600, 4),
                'overscan_x': 24,
                'overscan_y': 3,
                'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,     #  Not sure why these three are even here.
                'rotation': 0.0,        #  Probably remove.
                'min_exposure': 0.00001,
                'max_exposure': 300.0,
                'can_subframe':  True,
                'min_subframe':  [128, 128],       
                'bin_modes':  [[2, 2, 1.06], [3, 3, 1.58], [4, 4, 2.11], [1, 1, 0.53]],   #Meaning no binning choice if list has only one entry, default should be first.
                'default_bin':  [2, 2, 1.06],    #  Matched to seeing situation by owner
                'cycle_time':  [18, 15, 15],  # 3x3 requires a 1, 1 reaout then a software bin, so slower.
                'rbi_delay':  0.,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color':  False,
                'can_set_gain':  True,
                'bayer_pattern':  None,    #  Need to verify R as in RGGB is pixel x=0, y=0, B is x=1, y = 1
                'can_set_gain':  True,
                'reference_gain': [10., 10., 10., 10.],     #  One val for each binning.
                'reference_noise': [1.1, 1.1, 1.1, 1.1],    #  All SWAGs right now
                'reference_dark': [0.0, 0.0, 0.0, 0.0],     #  Might these best be pedastal values?
                                    #hdu.header['RDMODE'] = (self.config['camera'][self.name]['settings']['read_mode'], 'Camera read mode')
                    #hdu.header['RDOUTM'] = (self.config['camera'][self.name]['readout_mode'], 'Camera readout mode')
                    #hdu.header['RDOUTSP'] = (self.config['camera'][self.name]['settings']['readout_speed'], '[FPS] Readout speed')
                'read_mode':  'Normal',
                'readout_mode':  'Normal',
                'readout_speed': 0.4,
                'saturate':  50000,
                'max_linearity': 55000,
                'fullwell_capacity': 80000.,
                'areas_implemented': ["600%", "500%", "450%", "300%", "220%", "150%", "133%", "Full", "Sqr", '71%', '50%',  '35%', '25%', '12%'],
                'default_area':  "Full",
                'has_darkslide':  True,
                'darkslide_com':  'COM17',
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
        
        


