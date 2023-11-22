# -*- coding: utf-8 -*-
'''

Created on Fri Feb 07,  11:57:41 2020
Updated 20220914 WER   This version does not support color camera channel.
Updates 20231102 WER   This is meant to clean up and refactor wema/obsp architecture

@author: wrosing

NB NB NB  If we have one config file then paths need to change depending upon which host does what job.

aro-0m30      10.0.0.73
aro-wema      10.0.0.50
Power Control 10.0.0.100   admin arot******
Roff Control  10.0.0.200   admin arot******
Redis         10.0.0.73:6379
Dragonfly   Obsolete.
'''

#                                                                                                  1         1         1
#        1         2         3         4         5         6         7         8         9         0         1         2
#23456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
import json



obs_id = 'aro1'

site_config = {
    # Instance type specifies whether this is an obs or a wema
    'instance_type' : 'obs',
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name' : 'aro',
    # The unique identifier for this obs
    'obs_id': 'aro1',


    # Name, local and owner stuff
    'name': 'Apache Ridge Observatory 0m3f4.9/9',

    'location': 'Santa Fe, New Mexico,  USA',
    'observatory_url': 'https://starz-r-us.sky/clearskies2',   # This is meant to be optional
    'observatory_logo': None,   # I expect
    'mpc_code':  'ZZ23',    #This is made up for now.
    'dedication':   '''
                    Now is the time for all good persons
                    to get out and vote, lest we lose
                    charge of our democracy.
                    ''',    # i.e, a multi-line text block supplied and formatted by the owner.
    'owner':  ['google-oauth2|102124071738955888216', \
               'google-oauth2|112401903840371673242'],  # Neyle,
    'owner_alias': ['ANS', 'WER'],
    'admin_aliases': ["ANS", "WER", 'KVH', "TELOPS", "TB", "DH", "KVH", 'KC'],



    # Default safety settings
    'safety_check_period': 45,  # MF's original setting.

    'closest_distance_to_the_sun': 30,  # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_moon': 5,  # Degrees. For normal pointing requests don't go this close to the moon.
    'minimum_distance_from_the_moon_when_taking_flats': 30,
    'lowest_requestable_altitude': -1,  # Degrees. For normal pointing requests don't allow requests to go this low.
    'degrees_to_avoid_zenith_area_for_calibrations': 0,
    'degrees_to_avoid_zenith_area_in_general' : 0,
    'maximum_hour_angle_requestable' : 12,
    'temperature_at_which_obs_too_hot_for_camera_cooling' : 32, # NB NB WER ARO Obs has a chiller

    # These are the default values that will be set for the obs
    # on a reboot of obs.py. They are safety checks that
    # can be toggled by an admin in the Observe tab.
    'scope_in_manual_mode': False,
    'mount_reference_model_off': False,
    'sun_checks_on': True,
    'moon_checks_on': True,
    'altitude_checks_on': True,
    'daytime_exposure_time_safety_on': True,



    # Setup of folders on local and network drives.
    'ingest_raws_directly_to_archive': True,
    # LINKS TO PIPE FOLDER
    'save_raws_to_pipe_folder_for_nightly_processing': False,
    'pipe_archive_folder_path': 'X:/localptrarchive/',  #WER changed Z to X 20231113 @1:16 UTC
    'temporary_local_pipe_archive_to_hold_files_while_copying' : 'F:/tempfolderforpipeline',
    # LINKS FOR OBS FOLDERS
    'client_hostname':"ARO-0m30",     # Generic place for this host to stash.
    'archive_path': 'F:/ptr/',
    'alt_path': 'Q:/ptr/',
    'temporary_local_alt_archive_to_hold_files_while_copying' : 'F:/tempfolderforaltpath',

    'save_to_alt_path' : 'yes',
    'local_calibration_path': 'F:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'archive_age' : 10.0, # Number of days to keep files in the local archive before deletion. Negative means never delete




    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus file can not be saved.
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : True,
    # Number of files to send up to the ptrarchive simultaneously.
    'number_of_simultaneous_ptrarchive_streams' : 4,
    # Number of files to send over to the pipearchive simultaneously.
    'number_of_simultaneous_pipearchive_streams' : 4,
    # Number of files to send over to the altarchive simultaneously.
    'number_of_simultaneous_altarchive_streams' : 4,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.0,


    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats
    'bias_dark interval':  105.,   #minutes
    'eve_sky_flat_sunset_offset': -45.,  # Before Sunset Minutes  neg means before, + after.
    'end_eve_sky_flats_offset': -1 ,      # How many minutes after civilDusk to do....
    'clock_and_auto_focus_offset':-10,   #min before start of observing
    'astro_dark_buffer': 30,   #Min before and after AD to extend observing window
    'morn_flat_start_offset': -10,       #min from Sunrise
    'morn_flat_end_offset':  +45,        #min from Sunrise
    'end_night_processing_time':  90,   #  A guess
    #'observing_begins_offset': -1,       #min from AstroDark
    # How many minutes before civilDawn to do ....



     # Exposure times for standard system exposures
     'focus_exposure_time': 15,  # Exposure time in seconds for exposure image
     'pointing_exposure_time': 20,  # Exposure time in seconds for exposure image

     # How often to do various checks and such
     'observing_check_period': 3,    # How many minutes between weather checks
     'enclosure_check_period': 3,    # How many minutes between enclosure checks

     # Turn on and off various automated calibrations at different times.
     'auto_eve_bias_dark': True,
     'auto_eve_sky_flat': True,
     'time_to_wait_after_roof_opens_to_take_flats': 120,   #Just imposing a minimum in case of a restart.
     'auto_midnight_moonless_bias_dark': False,
     'auto_morn_sky_flat': True,
     'auto_morn_bias_dark': True,

     # FOCUS OPTIONS
     'periodic_focus_time': 3.0, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
     'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
     'focus_trigger': 0.6,  # What FWHM increase is needed to trigger an autofocus

     # PLATESOLVE options
     'solve_nth_image': 1,  # Only solve every nth image
     'solve_timer': 0.05,  # Only solve every X minutes    NB WER  3 seconds????
     'threshold_mount_update': 45,  # only update mount when X arcseconds away



    'defaults': {
        'screen': 'screen1',
        'mount': 'mount1',
        #'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        #'rotator': 'rotator1',
        'selector': None,
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
        'mount',
        #'telescope',
        #'screen',
        #'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',
        'sequencer',
        ],
    'short_status_devices':  [
       'mount',
       #'telescope',
       # 'screen',
       'rotator',
       'focuser',
       'selector',
       'filter_wheel',
       'camera',
       'sequencer',
       ],


    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'name': 'aropier1',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'safpier',
            'desc':  'AP 1600 GoTo',
            'driver': 'AstroPhysicsV2.Telescope',
            'alignment': 'Equatorial',
            'default_zenith_avoid': 0.0,   # degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            'has_ascom_altaz': False,
            'pointing_tel': 'tel1',     # This can be changed to 'tel2'... by user.  This establishes a default.

            'home_after_unpark' : False,
            'home_before_park' : False,

            'settle_time_after_unpark' : 10,
            'settle_time_after_park' : 10,
  #
            'permissive_mount_reset' : 'no', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            'west_clutch_ra_correction': 0.0,  #final:   0.0035776615398219747 -0.1450812805892454
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction':   0.0, # Initially -0.039505313212952586,
            'east_flip_dec_correction':  0.0,  #initially  -0.39607711292257797,
            'settings': {
                'latitude_offset': 0.0,    #  Decimal degrees, North is Positive   These *could* be slightly different than site.
                'longitude_offset': 0.0,   #  Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
                'elevation_offset': 0.0,   #  meters above sea level
                'home_altitude': 0.0,
                'home_azimuth': 0.0,
                'horizon':  25.,    # Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  # Meant to be something to draw on the Skymap with a spline fit.
                    '0.0': 25.,
                    '90' : 25.,
                    '180': 25.,
                    '270': 25.,
                    '359': 25.
                    },  #  We use a dict because of fragmented azimuth measurements.
                'refraction_on': True,  #  Refraction is applied during pointing.
                'model_on': True,  #  Model is applied during pointing.
                'rates_on': True,  #  Rates implied by model and refraction applie during tracking.
                'model': {
                    'IH': 0.00, #
                    'ID': 0.00, #
                    'WIH': 0.0,
                    'WID': 0.0,
                    'MA': 0.0,
                    'ME': 0.0,
                    'CH': 0.0,
                    'NP': 0.0,
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



    'telescope': {                            # OTA = Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'telescop': 'aro1',
            'desc':  'Ceravolo 300mm F4.9/F9 convertable',
            'ptrtel': 'cvagr-0m30-f9-f4p9-001',
            'driver': None,                     # Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 31808,   #This is correct as of 20230420 WER
            'obscuration':  0.55,  # Informatinal, already included in collecting_area.
            'aperture': 30,
            'focal_length': 1470,  # 1470,   #2697,   # Converted to F9, measured 20200905  11.1C
            'has_dew_heater':  False,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   # This is a default for a single instrument system
            'selector_positions': 1,            # Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                 'f-ratio':  'f4.9',     #  This needs expanding into something easy for the owner to change.
                 "position1": ["darkslide1", "filter_wheel1", "camera1"]
                 },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  True,
            'has_cover':  False,
            'axis_offset_east': -19.5,  # East is negative  These will vary per telescope.
            'axis_offset_south': -8,  # South is negative

            'settings': {
                'fans': ['Auto', 'High', 'Low', 'Off'],
                'offset_collimation': 0.0,    # If the mount model is current, these numbers are usually near 0.0
                                              # for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  # new terms.
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
            'step_size':  0.0001,     # Is this correct?
            'backlash':  0.0,
            'throw': 300,
            'unit':  'degree'    # 'steps'
        },

    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'Optec Alnitak 16"',
            'driver': 'COM14',  # This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
            'minimum': 5,   # This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 255,  # Out of 0 - 255, this is the last value where the screen is linear with output.
                              # These values have a minor temperature sensitivity yet to quantify.


        },


    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
		    'com_port': 'COM13',    #AP 'COM5'  No Temp Probe on SRO AO Honders
            'start_at_config_reference': False,
            'correct_focus_for_temperature' : True,
            'maximum_good_focus_in_arcsecond': 2.5, # highest value to consider as being in "good focus". Used to select last good focus value

            # # F4.9 setup
            # 'reference': 5800,    # 20210313  Nominal at 10C Primary temperature
            # 'ref_temp':  5.1,    # Update when pinning reference
            #F9 setup
            'reference': 5524, #5743,    #  Meas   Nominal at 10C Primary temperature
            'z_compression': 0.0, #  microns per degree of zenith distance
            'z_coef_date':  '20221002',
            'minimum': 0,     # NB this area is confusing steps and microns, and need fixing.
            'maximum': 12600,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'throw': 125,
            'unit': 'micron',
            'unit_conversion': 9.09090909091,
            'has_dial_indicator': False
        },

    },

    'selector': {
        'selector1': {
            'parent': 'telescope2',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': None,
            'com_port': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 1,
            'instruments':  ['Aux_camera'],  # 'eShel_spect', 'planet_camera', 'UVEX_spect'],

            'cameras':  ['camera_1_1'],  # 'camera_1_2', None, 'camera_1_4'],

            'guiders':  [None], # 'guider_1_2', None, 'guide_1_4'],
            'default': 0
            },

    },

    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "LCO FW50_001d",
            'service_date': '20210716',


            "filter_settle_time": 0, #how long to wait for the filter to settle after a filter change(seconds)
            'override_automatic_filter_throughputs': False, # This ignores the automatically estimated filter gains and starts with the values from the config file

            "driver": "LCO.dual",  # 'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'ip_string': 'http://10.0.0.110',
            "dual_wheel": True,
            'filter_reference': 'PL',
            'settings': {
                'filter_count': 23,
                "filter_type": "50mm_sq.",
                "filter_manuf": "Astrodon",
                'home_filter':  1,
                'default_filter': "PL",
                'focus_filter' : 'PL',
                'filter_reference': 1,   # We choose to use PL as the default filter.  Gains taken at F9, Ceravolo 300mm
                # Columns for filter data are : ['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'alias']
                #NB NB Note to WER please add cwl, bw and 'shape'
                'filter_data': [
                        ['Air',  [0,  0], -800, 1850., [2   ,  20], 'AIR'],    #0  Gains 20230703
                        ['Exo',  [8,  0],    0,  945., [360 , 170], 'Exoplanet - yellow, no UV or NIR'],     #1

                        ['PL',   [7,  0],    0, 1330., [360 , 170], 'Photo Luminance - does not pass NIR'],     #2
                        ['PR',   [0,  8],    0, 437.,  [.32 ,  20], 'Photo Blue'],     #3
                        ['PG',   [0,  7],    0, 495.,  [30  , 170], 'Photo Green'],     #4
                        ['PB',   [0,  6],    0, 545,   [360 , 170], 'Photo Blue'],     #5
                        ['NIR',  [0, 10],    0, 168.,  [0.65,  20], 'Near IR - redward of PR'],     #6  Value suspect 2023/10/23 WER

                        ['O3',   [0,  2],    0, 45.0,  [360 , 170], 'Oxygen III'],     #7    #guess
                        ['HA',   [0,  3],    0, 12.8,  [360 , 170], 'Hydrogen Alpha - aka II'],     #8
                        ['N2',   [13, 0],    0, 5.97,  [360 , 170], 'Nitrogen II'],     #9
                        ['S2',   [0,  4],    0, 6.09,  [0.65,  20], 'Sulphur II'],     #10
                        ['CR',   [0,  5],    0, 12.0,  [360 , 170], 'Continuum Red - for Star subtraction'],     #11

                        ['up',   [1,  0],    0, 32.5,  [2   ,  20], "Sloan u'"],     #12
                        ['BB',   [9,  0],    0, 506.,  [0.65,  20], 'Bessell B'],     #13
                        ['gp',   [2,  0],    0, 822.,  [.77 ,  20], "Sloan g'"],     #14
                        ['BV',   [10, 0],    0, 609.,  [.32 ,  20], 'Bessell V'],     #15
                        ['BR',   [11, 0],    0, 527.,  [10  , 170], 'Bessell R'],     #16
                        ['rp',   [3,  0],    0, 464.,  [1.2 ,  20], "Sloan r'"],     #17
                        ['ip',   [4,  0],    0, 193.,  [.65 ,  20], "Sloan i'"],     #18
                        ['BI',   [12, 0],    0, 114.,  [360 , 170], 'Bessell I'],     #19
                        ['zp',   [0,  9],    0,  23.,  [360 , 170], "Sloan z'"],     #20    # NB I think these may be backward labeled,
                        ['zs',   [5,  0],    0, 16.88, [1.0 ,  20], "Sloan z-short"],     #21    # NB ZP is a broader filter than zs.
                        ['Y',    [6,  0],    0, 7.3,   [360 , 170], "Rubin Y - low throughput, defective filter in top area "],     #22


                        ['dark', [1,  3],    0, 0.00,  [360 , 170], 'dk']],    #23     #Not a real filter.



                'filter_screen_sort':  ['ip'],   # don't use narrow yet,  8, 10, 9], useless to try.
                'filter_sky_sort': ['N2','S2','HA','CR','zs','zp','up','O3','BI','NIR','ip','PR','rp',\
                                    'PG','BB','BR','BV','PB','gp','EXO','PL','air'],




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

    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'sq002ms',      # Important because this points to a server file structure by that name.
            'desc':  'QHY 600Pro',
            'service_date': '20211111',
            #'driver': "ASCOM.QHYCCD.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ## 'ASCOM.FLI.Kepler.Camera',
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #

            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'G:/000ptr_saf/archive/sq01/autosaves/',


            'settings': {

                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.

                # Simple Camera Properties
                'is_cmos':  True,
                'is_osc': False,
                'is_color': False,  # NB we also have a is_osc key.
                'osc_bayer': 'RGGB',



                # For direct QHY usage we need to set the appropriate gain.
                # This changes from site to site. "Fast" scopes like the RASA need lower gain then "slow".
                # Sky quality is also important, the worse the sky quality, the higher tha gain needs to be
                # Default for QHY600 is GAIN: 26, OFFSET: 60, readout mode 3.
                # Random tips from the internet:
                # After the exposure, the background in the image should not be above 10% saturation of 16Bit while the brightest bits of the image should not be overexposed
                # The offset should be set so that there is at least 300ADU for the background
                # I guess try this out on the standard smartstack exposure time.
                # https://www.baader-planetarium.com/en/blog/gain-and-offset-darks-flats-and-bias-at-cooled-cmos-cameras/
                #
                # Also the "Readout Mode" is really important also
                # Readout Mode #0 (Photographic DSO Mode)
                # Readout Mode #1 (High Gain Mode)
                # Readout Mode #2 (Extended Fullwell Mode)
                # Readout Mode #3 (Extended Fullwell Mode-2CMS)
                #
                # With the powers invested in me, I have decided that readout mode 3 is the best. We can only pick one standard one
                # and 0 is also debatably better for colour images, but 3 is way better for dynamic range....
                # We can't swip and swap because the biases and darks and flats will change, so we are sticking with 3 until
                # something bad happens with 3 for some reason
                #
                # In that sense, QHY600 NEEDS to be set at GAIN 26 and the only thing to adjust is the offset.....
                # USB Speed is a tradeoff between speed and banding, min 0, max 60. 60 is least banding. Most of the
                # readout seems to be dominated by the slow driver (difference is a small fraction of a second), so I've left it at 60 - least banding.
                'direct_qhy_readout_mode' : 3,
                'direct_qhy_gain' : 26,
                'direct_qhy_offset' : 60,
                #'direct_qhy_usb_speed' : 50,
                'direct_qhy_usb_traffic' : 50,

                'set_qhy_usb_speed': False,
                'direct_qhy_usb_speed' : 0,

                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                'interpolate_for_focus': False,
                # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'bin_for_focus': True,
                'focus_bin_value' : 2,
                'interpolate_for_sep': False,
                'bin_for_sep': True,  # This setting will bin the image for SEP photometry rather than interpolating.
                'sep_bin_value' : 2,
                # This setting will bin the image for platesolving rather than interpolating.
                'bin_for_platesolve': False,
                'platesolve_bin_value' : 1,

                # Colour image tweaks.
                'osc_brightness_enhance': 1.0,
                'osc_contrast_enhance': 1.2,
                'osc_saturation_enhance': 1.5,
                'osc_colour_enhance': 1.2,
                'osc_sharpness_enhance': 1.2,
                'osc_background_cut': 15.0,


                # ONLY TRANSFORM THE FITS IF YOU HAVE
                # A DATA-BASED REASON TO DO SO.....
                # USUALLY TO GET A BAYER GRID ORIENTATED CORRECTLY
                # ***** ONLY ONE OF THESE SHOULD BE ON! *********
                'transpose_fits': False,
                'flipx_fits': False,
                'flipy_fits': False,
                'rotate180_fits': False,  # This also should be flipxy!
                'rotate90_fits': False,
                'rotate270_fits': False,
                'squash_on_x_axis': False,

                # What number of pixels to crop around the edges of a REDUCED image
                # This is primarily to get rid of overscan areas and also all images
                # Do tend to be a bit dodgy around the edges, so perhaps a standard
                # value of 30 is good. Increase this if your camera has particularly bad
                # edges.
                'reduced_image_edge_crop': 30,

                # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
                # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
                # RECOMMENDED DEFAULT DESIRE OF PTR
                'transpose_jpeg': False,
                'flipx_jpeg': False,
                'flipy_jpeg': False,
                'rotate180_jpeg': True,
                'rotate90_jpeg': False,
                'rotate270_jpeg': False,

                # This is purely to crop the preview jpeg for the UI
                'crop_preview': False,
                'crop_preview_ybottom': 2,  # 2 needed if Bayer array
                'crop_preview_ytop': 2,
                'crop_preview_xleft': 2,
                'crop_preview_xright': 2,

                # For large fields of view, crop the images down to solve faster.
                # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
                # Probably also similar for platesolving.
                # for either pointing or platesolving even on more modest size fields of view.
                # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
                # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless
                # you clearly need to.
                'focus_image_crop_width': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full width
                'focus_image_crop_height': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full height
                'focus_jpeg_size': 1500, # How many pixels square to crop the focus image for the UI Jpeg

                # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE
                'platesolve_image_crop': 0.0,  # Platesolve crops have to be symmetrical

                # Really, the SEP image should not be cropped unless your field of view and number of sources
                # Are taking chunks out of the processing time.
                # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
                'sep_image_crop_width': 0.0,
                # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
                'sep_image_crop_height': 0.0,

                # This is the area for cooling related settings
                'cooler_on': True,
                'temp_setpoint': -7.5,  # Verify we can go colder
                'has_chiller': True,
                'chiller_com_port': 'COM1',
                'chiller_ref_temp':  15.0,  # C
                'day_warm': False,   #This is converted to a 0 or 1 depending ont he Boolean value
                'day_warm_degrees': 0,  # Assuming the Chiller is working.
                'protect_camera_from_overheating' : False,

                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.
                'onebyone_pix_scale': 0.528,    #  This is the 1x1 binning pixelscale
                'native_bin': 2, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                'x_pixel':  3.76, # pixel size in microns
                'y_pixel':  3.76, # pixel size in microns
                'field_x':  1.3992,   #4770*2*0.528/3600
                'field_y':  0.9331,    #3181*2*0.528/3600
                'field_sq_deg':  1.3056,
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.
                'drizzle_value_for_later_stacking': 0.5,


                # This is the absolute minimum and maximum exposure for the camera
                'min_exposure': 0.0001,
                'max_exposure': 360.,
                # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'min_flat_exposure': 0.01,
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 0.5,


                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain' : True,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.
                'camera_gain':   2.15, #[10., 10., 10., 10.],     #  One val for each binning.
                'camera_gain_stdev':   0.16, #[10., 10., 10., 10.],     #  One val for each binning.
                'read_noise':  9.55, #[9, 9, 9, 9],    #  All SWAGs right now
                'read_noise_stdev':   0.004, #[10., 10., 10., 10.],     #  One val for each binning.
                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 80000,  # NB Guess
                'saturate':   65535,
                'max_linearity':  60000,   # Guess
                # How long does it take to readout an image after exposure
                'cycle_time':            0.0,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 15,


                # As simple as it states, how many calibration frames to collect and how many to store.
                'number_of_bias_to_collect': 33,
                'number_of_dark_to_collect': 15,
                'number_of_flat_to_collect': 9,
                'number_of_bias_to_store': 63,
                'number_of_dark_to_store': 31,
                'number_of_flat_to_store': 17,
                # Default dark exposure time.
                'dark_exposure': 360,

                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  True,
                'darkslide_com':  'COM10',
                'shutter_type': "Electronic",



                # 'has_screen': False,
                # 'screen_settings':  {
                #     'screen_saturation':  157.0,   # This reflects WMD setting and needs proper values.
                #     'screen_x4':  -4E-12,  # 'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                #     'screen_x3':  3E-08,
                #     'screen_x2':  -9E-05,
                #     'screen_x1':  .1258,
                #     'screen_x0':  8.683
                # },
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

    # I am not sure AWS needs this, but my configuration code might make use of it.
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