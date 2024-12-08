# -*- coding: utf-8 -*-
'''
obs_config.py   obs_config.py   obs_config.py   obs_config.py   obs_config.py
Created on Fri Feb 07,  11:57:41 2020
Updated 20220914 WER   This version does not support color camera channel.
Updates 20231102 WER   This is meant to clean up and refactor wema/obsp
architecture

@author: wrosing

NB NB NB  If we have one config file then paths need to change depending upon
hich host does what job.

aro-0m30      10.0.0.73
aro-wema      10.0.0.50
Power Control 10.0.0.100   admin arot******
Roof Control  10.0.0.200   admin arot******    /setup.html     for setup.
Redis         10.0.0.174:6379  ; rds = redis.Redis(host='10.0.0.174',
              port=6379); rds.set('wx', 'bogus'); rds.get('wx').decode()
Dragonfly     Obsolete.

Hubble V1  00:41:27.30 +41:10:10.4
'''

'''
   Example : at 0.6 µm, at the F/D 6 focus of an instrument, the focusing tolerance which leads to a focusing \
   precision better than l/8 is 8*62*0.0006*(1/8) = 0.02 mm, ie ± 20 microns.

    F/d Tolerance
        ± mm

    2   0.0025

    3   0.005

    4   0.01

    5   0.015

    6   0.02

    8   0.04

    10  0.06

    12  0.09

    15  0.13

    20  0.24

    30  0.54
'''

#                                                                                                  1         1         1
#                  2         3         4         5         6         7         8         9         0         1         2
#23456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
import json


obs_id = 'aro1'

site_config = {
    # Instance type specifies whether this is an obs or a wema
    'instance_type': 'obs',
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name': 'aro',
    # The unique identifier for this obs
    'obs_id': 'aro1',


    # Name, local and owner stuff
    'name': 'Apache Ridge Observatory 0m3 f4.9/9',

    'location': 'Santa Fe, New Mexico,  USA',
    # This is meant to be an optional informatinal website associated with the observatory.
    'observatory_url': 'https://starz-r-us.sky/clearskies2',
    'observatory_logo': None,   #
    'mpc_code':  'ZZ23',  # This is made up for now.
    'dedication':   '''
                    Now is the time for all good persons
                    to get out and vote, lest we lose
                    charge of our democracy.
                    ''',    # i.e, a multi-line text block supplied and formatted by the owner.
    'owner':  ['google-oauth2|102124071738955888216', \
               'google-oauth2|112401903840371673242'],  # Neyle,
    'owner_alias': ['ANS', 'WER'],
    'admin_aliases': ["ANS", "WER", "TELOPS"],



    # Default safety settings
    'safety_check_period': 120,  # MF's original setting was 45.

    # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_sun': 30,
    # Degrees. For normal pointing requests don't go this close to the moon.
    'closest_distance_to_the_moon': 5,
    'minimum_distance_from_the_moon_when_taking_flats': 30,
    # Degrees. For normal pointing requests don't allow requests to go this low.
    'lowest_requestable_altitude': 15,
    # Below this altitude, it will automatically try to home and park the scope to recover.
    'lowest_acceptable_altitude': -10,
    'degrees_to_avoid_zenith_area_for_calibrations': 0,
    'degrees_to_avoid_zenith_area_in_general': 0,
    'maximum_hour_angle_requestable': 9,
    # NB NB WER ARO Obs has a chiller
    'temperature_at_which_obs_too_hot_for_camera_cooling': 32,


    # These are the default values that will be set for the obs
    # on a reboot of obs.py. They are safety checks that
    # can be toggled by an admin in the Observe tab.

    # # Engineering start

    # 'scope_in_manual_mode': True,
    # 'scope_in_engineering_mode': True,
    # 'mount_reference_model_off': True,
    # 'sun_checks_on': False,
    # 'moon_checks_on': False,
    # 'altitude_checks_on': False,
    # 'daytime_exposure_time_safety_on': False,
    # 'simulate_open_roof': True,
    # 'auto_centering_off': True,
    # 'self_guide_on': False,
    # 'always_do_a_centering_exposure_regardless_of_nearby_reference':  False,   #this is a qustionable setting
    # 'owner_only_commands':True,

    # #SAFESTART

    'scope_in_manual_mode': False,
    'scope_in_engineering_mode': False,
    'mount_reference_model_off': False,
    'sun_checks_on': True,
    'moon_checks_on': True,
    'altitude_checks_on': True,
    'daytime_exposure_time_safety_on': True,   #Perhaps condition by roof open/closed?
    'simulate_open_roof': False,
    'auto_centering_off': False,
    'self_guide_on': True,
    'always_do_a_centering_exposure_regardless_of_nearby_reference': False,
    'owner_only_commands': False,


    # Setup of folders on local and network drives.
    'ingest_raws_directly_to_archive': True,  # This it the OCS-archive, archive-photonranch.org
    # LINKS TO PIPE FOLDER
    'save_raws_to_pipe_folder_for_nightly_processing': True,
    # WER changed Z to X 20231113 @1:16 UTC
    'pipe_archive_folder_path': 'X:/localptrarchive/',
    # 'temporary_local_pipe_archive_to_hold_files_while_copying' : 'F:/tempfolderforpipeline',
    # LINKS FOR OBS FOLDERS
    'client_hostname': "ARO-0m30",     # Generic place for this host to stash.
    'archive_path': 'F:/ptr/',
    'alt_path': 'Q:/ptr/',
    # 'temporary_local_alt_archive_to_hold_files_while_copying' : 'F:/tempfolderforaltpath',

    'save_to_alt_path': 'yes',
    # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'local_calibration_path': 'F:/ptr/',
    # Number of days to keep files in the local archive before deletion. Negative means never delete
    'archive_age': 4.0,

    'redis_available':  True,
    'redis_ip': "10.0.0.174:6379",

    # Scratch drive folder
    'scratch_drive_folder': 'D:/obstemp/',


    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    # To save space, the focus file can not be saved.
    'keep_focus_images_on_disk': True,
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first': True,
    # Number of files to send up to the ptrarchive simultaneously.
    'number_of_simultaneous_ptrarchive_streams': 4,
    # Number of files to send over to the pipearchive simultaneously.
    'number_of_simultaneous_pipearchive_streams': 4,
    # Number of files to send over to the altarchive simultaneously.
    'number_of_simultaneous_altarchive_streams': 4,


    # Bisque mounts can't run updates in a thread ... yet... until I figure it out,
    # So this is False for Bisques and true for everyone else.
    'run_main_update_in_a_thread': True,
    'run_status_update_in_a_thread': True,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.5,
    'has_lightning_detector':  True,

    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats
    'bias_dark interval':  120.,  # minutes
    # Was 55 WER 20240313 Before Sunset Minutes  neg means before, + after.
    'eve_sky_flat_sunset_offset': -30.,
    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 15.,
    'clock_and_auto_focus_offset': -10,  # min before start of observing
    'astro_dark_buffer': 10,  # Min before and after AD to extend observing window
    'morn_flat_start_offset': -10.,  # min from Sunrise
    'morn_flat_end_offset': +40.,  # min from Sunrise
    'end_night_processing_time':  90.,  # A guess
    # 'observing_begins_offset': -1,       #min from AstroDark
    # How many minutes before civilDawn to do ....



    # Exposure times for standard system exposures
    'focus_exposure_time': 5,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 12,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 3,    # How many minutes between weather checks
    'enclosure_check_period': 3,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': True,
    # Units??  Just imposing a minimum in case of a restart.
    'time_to_wait_after_roof_opens_to_take_flats': 3,
    # WER 20240303 Afternoon, changed from True
    'auto_midnight_moonless_bias_dark': True,
    'auto_morn_sky_flat':  True,
    'auto_morn_bias_dark':  True,

    # FOCUS OPTIONS
    # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'periodic_focus_time': 2,
    'stdev_fwhm': 0.4,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.5,  # What FWHM increase is needed to trigger an autofocus

    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes    NB WER  3 seconds????
    'threshold_mount_update': 45,  # only update mount zero point when X arcseconds away
    # units?  maximum radial drift allowed for a correction when running a block
    'limit_mount_tweak': 15,

    'defaults': {
        'screen': 'screen1',
        'mount': 'mount1',
        # 'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        # 'rotator': 'rotator1',
        'selector': None,
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
    },
    'device_types': [
        'mount',
        # 'telescope',
        # 'screen',
        # 'rotator',
        'selector',
        'filter_wheel',
        'focuser',
        'camera',
        'sequencer',
    ],
    'short_status_devices':  [
        'mount',
        # 'telescope',
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
            # Can be a name if local DNS recognizes it.
            'hostIP':  '10.0.0.140',
            'hostname':  'safpier',
            'desc':  'AP 1600 GoTo',
            'driver': 'AstroPhysicsV2.Telescope',
            # this is redundnat with a term below near model.
            'alignment': 'Equatorial',
            # degrees floating, 0.0 means do not apply this constraint.
            'default_zenith_avoid': 0.0,
            # Some mounts report they have finished slewing but are still vibrating. This adds in some buffer time to a wait for slew.
            'wait_after_slew_time': 0.0,

            # paddle refers to something supported by the Python code, not the AP paddle.
            'has_paddle': False,
            # Presumably this is the AltAzDServer from Optec.
            'has_ascom_altaz': False,
            # This can be changed to 'tel2'... by user.  This establishes a default.
            'pointing_tel': 'tel1',

            'home_after_unpark': False,
            'home_before_park': False,

            'settle_time_after_unpark': 5,
            'settle_time_after_park': 5,
            #
            # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'permissive_mount_reset': 'no',
            # How many seconds of inactivity until it will park the telescope
            'time_inactive_until_park': 900.0,

            # final:   0.0035776615398219747 -0.1450812805892454
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction':   0.0,  # Initially -0.039505313212952586,
            'east_flip_dec_correction':  0.0,  # initially  -0.39607711292257797,
            'settings': {
                # Decimal degrees, North is Positive   These *could* be slightly different than site.
                'latitude_offset': 0.0,
                # Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
                'longitude_offset': 0.0,
                'elevation_offset': 0.0,  # meters above sea level
                'home_altitude': 0.0,
                'home_azimuth': 0.0,
                # Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon':  25.,
                'horizon_detail': {  # Meant to be something to draw on the Skymap with a spline fit.
                    '0.0': 25.,
                    '90': 25.,
                    '180': 25.,
                    '270': 25.,
                    '359': 25.
                },  # We use a dict because of fragmented azimuth measurements.
                'ICRS2000_input_coords':  True,
                # Refraction is applied during pointing.
                'refraction_on': True,
                'model_on': True,
                'model_type': "Equatorial",
                # Rates implied by model and refraction applied during tracking.
                'rates_on': True,
                # In the northern hemisphere, positive MA means that the pole of the mounting
                # is to the right of due north.
                # In the northern hemisphere, positive ME means that the pole of the mounting is
                # below the true (unrefracted) pole. A mounting aligned the refracted pole (for most
                # telescopes probably the simplest and best thing to aim for in order to avoid unwanted
                # field rotation effects will have negative ME.                'model_date':  "n.a.",
                # units for model are asec/radian
                'model_equat': {
                    # Home naturally points to West for AP GEM mounts.  Howeveer when @ Park 5 it is flipped.
                    'ih':   0.0,
                    # These two are zero-point references for HA/Ra and dec.
                    'id':   0.0,
                    'eho':  0.0,  # East Hour angle Offset -- NOTE an offset
                    'edo':  0.0,  # East Dec Offset
                    'ma':   73.0,  # Azimuth error of polar axis
                    'me':   300.0,  # Elev error of polar axisDefault is about -60 asec above pole for ARO
                    'ch':   -115.0,  # Optical axis not perp to dec axis
                    'np':   0.0,  # Non-perp of polar and dec axis
                    'tf':   0.0,  # Sin flexure -- Hook's law.
                    'tx':   0.0,  # Tangent flexure
                    'hces': 0.0,  # Sin centration error of RA encoder
                    'hcec': 0.0,  # Cos centration error of RA encoder
                    'dces': 0.0,  # Sin centration error of DEC encoder
                    'dcec': 0.0,  # Cos centration error of DEC encoder
                }                # 'model_version': 'N.A', # As in "20240526-1.mod"   Eventually we can put the model name here and pick up automatically.




                ,
                'model_altAz': {
                    # "Home naturally points to West for AP GEM mounts.
                    'ia': 000.00,
                    'ie': 0.00,  # These two are zero-point references.
                    'eho': 0.0,  # "East Hour angle Offset -- NOTE an offset
                    'edo': 0.0,  # "East Dec Offset
                    'ma': 0.0,
                    'me': 0.0,  # Default is about -60 asec above pole for ARO
                    'ch': 0.0,
                    'np': 0.0,
                    'tf': 0.0,
                    'tx': 0.0,
                    'hces': 0.0,
                    'hcec': 0.0,
                    'dces': 0.0,
                    'dcec': 0.0,
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
            # Essentially this device is informational.  It is mostly about the optics.
            'driver': None,
            'collecting_area': 31808,  # This is correct as of 20230420 WER
            # Informatinal, already included in collecting_area.
            'obscuration':  0.55,
            'aperture': 30,
            # 1470,   #2697,   # Converted to F9, measured 20200905  11.1C  1468.4 @ F4.9?
            'focal_length': 1468.4,
            'has_dew_heater':  False,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            # This is a default for a single instrument system
            'has_instrument_selector': False,
            'selector_positions': 1,            # Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                # This needs expanding into something easy for the owner to change.
                'f-ratio':  'f4.9',
                "position1": ["darkslide1", "filter_wheel1", "camera1"]
            },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  True,
            'has_cover':  False,
            # East is negative  These will vary per telescope.
            'axis_offset_east': -19.5,  #Inches appently!
            'axis_offset_south': -8,  # South is negative

            'settings': {
                'fans': ['Auto', 'High', 'Low', 'Off'],
                # If the mount model is current, these numbers are usually near 0.0
                'offset_collimation': 0.0,
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
            # This is the % of light emitted when Screen is on and nominally at 0% bright.
            'minimum': 5,
            # Out of 0 - 255, this is the last value where the screen is linear with output.
            'saturate': 255,
            # These values have a minor temperature sensitivity yet to quantify.


        },


    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',
                    'com_port': 'COM13',  # AP 'COM5'  No Temp Probe on SRO AO Honders
            'start_at_config_reference': False,
            'correct_focus_for_temperature': True,
            # highest value to consider as being in "good focus". Used to select last good focus value
            'maximum_good_focus_in_arcsecond': 3.0,
            'focuser_movement_settle_time': 3,
            # F4.9 setup
            'reference':  5221.2,    #  20241204
            'ref_temp':   7.5,       #  Average for the fit ~ 27.5 degrees wide +20 to -75
            'temp_coeff': -24.974,   #  R^2 = 0.769

            # F9 setup
            # 'reference': unknown,
            # 'temp_coeff': unknown,  #  Meas   -12 c to 4C so nominal -4C
            #  microns per degree of tube temperature
            'z_compression': 0.0,  # microns per degree of zenith distance
            'z_coef_date':  '20240820',
            # NB this area is confusing steps and microns, and needs fixing.
            'minimum': 0,
            'maximum': 12600,  # 12672 actually
            'step_size': 1,
            'backlash': 600,   # non-zero means enabled, + means over-travel when moving out, then come back IN  same amount.
            'throw': 90., #20240925 reduced from: #140,  # Start with 10X focus tolerance.
            'focus_tolerance':  130,    #Microns  ??? used Golf Focus Caclulator
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
            # 'eShel_spect', 'planet_camera', 'UVEX_spect'],
            'instruments':  ['Aux_camera'],

            'cameras':  ['camera_1_1'],  # 'camera_1_2', None, 'camera_1_4'],

            'guiders':  [None],  # 'guider_1_2', None, 'guide_1_4'],
            'default': 0
        },

    },

    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "LCO FW50_001d",
            'service_date': '20210716',


            # sec  WER 20240303 continuing test.  how long to wait for the filter to settle after a filter change(seconds)
            "filter_settle_time": 1,
            # This ignores the automatically estimated filter gains and starts with the values from the config file
            'override_automatic_filter_throughputs': False,

            "driver": "LCO.dual",  # 'ASCOM.FLI.FilterWheel',   #'MAXIM',
            'ip_string': 'http://10.0.0.110',
            "dual_wheel": True,
            'filter_reference': 'PL',
            'settings': {
                # 'filter_count': 23,
                # "filter_type": "50mm_sq.",
                # "filter_manuf": "Astrodon",
                # 'home_filter':  1,
                'default_filter': "PL",
                'focus_filter': 'PL',
                # 'filter_reference': 1,   # We choose to use PL as the default filter.  Gains taken at F9, Ceravolo 300mm
                # Columns for filter data are : ['filter', 'filter_index', 'filter_offset', 'sky_gain', 'screen_gain', 'alias']
                # NB NB Note to WER please add cwl, bw and 'shape'.  Throughputs ADJUSTED 20240103 Eve run


                # 'filter_data': [
                #         ['Air',  [0,  0], -800, 1200.,  [2   ,  20], 'AIR'],    #0  Gains est and some from 20240106 listing
                #         ['PL',   [7,  0],    0, 1100.,  [360 , 170], 'Photo Luminance - does not pass NIR'],     #1
                #         ['Exo',  [8,  0],    0, 915.,   [360 , 170], 'Exoplanet - yellow, no UV or far NIR'], #2
                #         ['PB',   [0,  6],    0, 700,    [360 , 170], 'Photo Blue'],     #3
                #         ['gp',   [2,  0],    0, 820.,   [.77 ,  20], "Sloan g'"],       #4
                #         ['PR',   [0,  8],    0, 520.,   [.32 ,  20], 'Photo Blue'],     #5
                #         ['PG',   [0,  7],    0, 470.,   [30  , 170], 'Photo Green'],     #6
                #         ['BB',   [9,  0],    0, 500.,   [0.65,  20], 'Bessell B'],     #7
                #         ['BV',   [10, 0],    0, 540.,   [.32 ,  20], 'Bessell V'],     #8
                #         ['BR',   [11, 0],    0, 600.,   [10  , 170], 'Bessell R'],     #9
                #         ['rp',   [3,  0],    0, 560.,   [1.2 ,  20], "Sloan r'"],     #10
                #         ['NIR',  [0, 10],    0, 226.,   [0.65,  20], 'Near IR - redward of PL'],     #11  Value suspect 2023/10/23 WER
                #         ['ip',   [4,  0],    0, 250.,   [.65 ,  20], "Sloan i'"],     #12
                #         ['BI',   [12, 0],    0, 155.,   [360 , 170], 'Bessell I'],     #13
                #         ['up',   [1,  0],    0, 39.0,   [2   ,  20], "Sloan u'"],     #14
                #         ['O3',   [0,  2],    0, 36.0,   [360 , 170], 'Oxygen III'],     #15    #guess
                #         ['zp',   [0,  9],    0, 11.0,   [1.0 ,  20], "Sloan z-short"],     #16    # NB ZP is a broader filter than zs.
                #         ['CR',   [0,  5],    0, 9.0,    [360 , 170], 'Continuum Red - for Star subtraction'],  #17
                #         ['HA',   [0,  3],    0, 8.0,    [360 , 170], 'Hydrogen Alpha - aka II'],     #18
                #         ['N2',   [13, 0],    0, 4.5,    [360 , 170], 'Nitrogen II'],     #19
                #         ['S2',   [0,  4],    0, 4.5,    [0.65,  20], 'Sulphur II'],     #20

                #         ['Y',    [6,  0],    0, 7.3,    [360 , 170], "Rubin Y - low throughput, defective filter in top area "],     #21


                #         ['dark', [1,  3],    0, 0.00,  [360 , 170], 'dk']],    #22     #Not a real filter.  Total 23
                #Front filter wheel is LCO  Square 50 mm 10 positions
                #Back (near camera wheel is LCO 50mm rount with 13 positions so
                #the capacity is  air + 23 filters.v)
                'filter_data': [
                    ['Air',  [0,  0],   'AIR'],  # 0
                    ['PL',   [7,  0],   'Photo Luminance'],  # 1
                    ['Exo',  [8,  0],   'Exoplanet'],  # 2
                    ['PB',   [0,  6],   'Photo Blue'],  # 3
                    ['gp',   [2,  0],   "Sloan g"],  # 4
                    ['PR',   [0,  8],   'Photo Red'],  # 5
                    ['PG',   [0,  7],   'Photo Green'],  # 6
                    ['BB',   [9,  0],   'Bessell B'],  # 7
                    ['BV',   [10, 0],   'Bessell V'],  # 8
                    # ['BR',   [11, 0],   'Bessell R'],    #9
                    ['rp',   [3,  0],   "Sloan r"],  # 10
                    # ['NIR',  [0, 10],   'Near IR'],      #11  Value suspect 2023/10/23 WER
                    ['ip',   [4,  0],   "Sloan i"],  # 12
                    # ['BI',   [12, 0],   'Bessell I'],    #13
                    ['up',   [1,  0],   "Sloan u"],  # 14
                    ['O3',   [0,  2],   'Oxygen III'],  # 15    #guess
                    # 16    # NB ZP is a broader filter than zs.
                    ['zs',   [0,  9],   "Sloan z-short"],
                  # ['CR',   [0,  5],   'Continuum Red - for Star subtraction'],  #17
                    ['HA',   [0,  3],   'Hydrogen Alpha'],  # 18
                    ['N2',   [13, 0],   'Nitrogen II'],  # 19
                    ['S2',   [0,  4],   'Sulphur II'],  # 20

                    # ['Y',    [6,  0],   "Rubin Y"],      #21


                    ['dk', [1,  3],   'dk']],  # 22     #Not a real filter.  Total 23

                # 'filter_screen_sort':  ['ip'],   # don't use narrow yet,  8, 10, 9], useless to try.
                # 'filter_sky_sort': ['S2','N2','HA','CR','zs','zp','up','O3','BI','NIR','ip','PR','BR',\
                #                     'rp','PG','BV','BB','PB','gp','EXO','PL','air'],  #Needs fixing once we get a good input series. 20240106 WER




            },




        },
    },

    'lamp_box': {
        'lamp_box1': {
            'parent': 'camera_1',  # Parent is camera for the spectrograph
            'name': 'None',  # "UVEX Calibration Unit", 'None'
            'desc': 'None',  # 'eshel',  # "uvex", 'None'
            'spectrograph': 'None',  # 'echelle', 'uvex'; 'None'
            'driver': 'None',  # ASCOM.Spox.Switch; 'None'; Note change to correct COM port used for the eShel calibration unit at mrc2
            'switches': "None"  # A string of switches/lamps the box has for the FITS header. # 'None'; "Off,Mirr,Tung,NeAr" for UVEX
        },
    },

    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            # Important because this points to a server file structure by that name.
            'name': 'sq003ms',
            'desc':  'QHY 600Pro',
            'overscan_trim': 'QHY600',
            'service_date': '20240604',
            # 'driver': "ASCOM.QHYCCD.Camera", #"Maxim.CCDCamera",  # "ASCOM.QHYCCD.Camera", ## 'ASCOM.FLI.Kepler.Camera',
            # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control",

            'detector':  'Sony IMX455',
            'manufacturer':  'QHY',
            'use_file_mode':  False,
            'file_mode_path':  'G:/000ptr_saf/archive/sq003ms/autosaves/',


            'settings': {

                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True,

                # Simple Camera Properties
                'is_cmos':  True,
                'is_osc': False,
                'is_color': False,  # NB we also have a is_osc key.
                'osc_bayer': 'RGGB',

                # There are some infuriating popups on theskyx that manually
                # need to be dealt with when doing darks and lights.
                # This setting uses a workaround for that. This is just for CMOS
                # CCDs are fine.
                'cmos_on_theskyx': False,

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


                # THIS IS THE PRE-TESTING SETTINGS FOR NEW MODE 11 Mar 2024
                # # In that sense, QHY600 NEEDS to be set at GAIN 26 and the only thing to adjust is the offset.....
                # # USB Speed is a tradeoff between speed and banding, min 0, max 60. 60 is least banding. Most of the
                # # readout seems to be dominated by the slow driver (difference is a small fraction of a second), so I've left it at 60 - least banding.
                # 'direct_qhy_readout_mode' : 3,
                # 'direct_qhy_gain' : 26,
                # 'direct_qhy_offset' : 60,
                # #'direct_qhy_usb_speed' : 50,
                # 'direct_qhy_usb_traffic' : 45,  #Early 20240103 = 50, not clear earlier but better than before.
                # #The pattern before came and went. Now consitent at 50.  Changing to 45.
                # #Which one of these is actually used?
                # 'set_qhy_usb_speed': True,
                # 'direct_qhy_usb_speed' : 45,    #20240106 Afternoon WER Was 60



                # # In that sense, QHY600 NEEDS to be set at GAIN 26 and the only thing to adjust is the offset.....
                # # USB Speed is a tradeoff between speed and banding, min 0, max 60. 60 is least banding. Most of the
                # # readout seems to be dominated by the slow driver (difference is a small fraction of a second), so I've left it at 60 - least banding.
                # 'direct_qhy_readout_mode' : 0,
                # 'direct_qhy_gain' : 26,
                # 'direct_qhy_offset' : 60,
                # #'direct_qhy_usb_speed' : 50,
                # 'direct_qhy_usb_traffic' : 45,  #Early 20240103 = 50, not clear earlier but better than before.
                # #The pattern before came and went. Now consitent at 50.  Changing to 45.
                # #Which one of these is actually used?
                # 'set_qhy_usb_speed': True,

                # #"speed isn't used I think - MTF, it is actually USB Traffic
                # #'direct_qhy_usb_speed' : 45,    #20240106 Afternoon WER Was 60


                # HERE IS THE POTENTIAL MODE 1 SETTINGS
                'direct_qhy_readout_mode': 1,  #High Gain mode
                'direct_qhy_gain': 58,   #Above low noise setting
                'direct_qhy_offset': 10,
                # 'direct_qhy_usb_speed' : 50,
                'direct_qhy_usb_traffic': 50,
                # The pattern before came and went. Now consitent at 50.  Changing to 45.
                # Which one of these is actually used?
                'set_qhy_usb_speed': True,


                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                # 'interpolate_for_focus': False,
                # # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                # 'bin_for_focus': False,
                # 'focus_bin_value' : 1,
                # 'interpolate_for_sep': False,
                # 'bin_for_sep': False,  # This setting will bin the image for SEP photometry rather than interpolating.
                # 'sep_bin_value' : 1,
                # This setting will bin the image for platesolving rather than interpolating.
                # 'bin_for_platesolve': False,
                # 'platesolve_bin_value' : 1,

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
                'rotate180_fits':True,  # This also should be flipxy!
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
                'rotate90_jpeg': False,
                'rotate180_jpeg':False,
                'rotate270_jpeg': False,

                # This is purely to crop the preview jpeg for the UI
                'crop_preview': False,
                'crop_preview_ybottom': 2,  # 2 needed if Bayer array
                'crop_preview_ytop': 2,
                'crop_preview_xleft': 2,
                'crop_preview_xright': 2,

                # # For large fields of view, crop the images down to solve faster.
                # # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
                # # Probably also similar for platesolving.
                # # for either pointing or platesolving even on more modest size fields of view.
                # # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
                # # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless
                # # you clearly need to.
                # 'focus_image_crop_width': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full width
                # 'focus_image_crop_height': 0.0,  # For excessive fields of view, to speed things up crop the image to a fraction of the full height
                # 'focus_jpeg_size': 1500, # How many pixels square to crop the focus image for the UI Jpeg

                # # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE
                # 'platesolve_image_crop': 0.0,  # Platesolve crops have to be symmetrical

                # # Really, the SEP image should not be cropped unless your field of view and number of sources
                # # Are taking chunks out of the processing time.
                # # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
                # 'sep_image_crop_width': 0.0,
                # # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width
                # 'sep_image_crop_height': 0.0,

                # This is the area for cooling related settings
                'cooler_on': True,
                'temp_setpoint': -8,  # 20240914 up from 3C, new camera installed 20240604
                'temp_setpoint_tolerance': 2,
                'has_chiller': True,
                # "temp_setpoint_tolarance": 1.5,
                'chiller_com_port': 'COM1',
                'chiller_ref_temp': 25,  # C 20240906




                # This is the yearly range of temperatures.
                # Based on New Mexico and Melbourne's variation... sorta similar.
                # There is a cold bit and a hot bit and an inbetween bit.
                # from the 15th of the month to the 15 of the month
                #
                # ( setpoint, day_warm_difference, day_warm troe our false)
                'set_temp_setpoint_by_season' : True,
                'temp_setpoint_nov_to_feb' : ( -8, 6, True),
                'temp_setpoint_feb_to_may' : ( 3, 8, True),
                'temp_setpoint_may_to_aug' : ( 6, 8, True),
                'temp_setpoint_aug_to_nov' : ( 3, 8, True),

                'day_warm': True,  # This is converted to a 0 or 1 depending on the Boolean value

                'day_warm_degrees': 4,  # Assuming the Chiller is working.
                'protect_camera_from_overheating': False,

                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.
                # 'onebyone_pix_scale': 0.528,    #  This is the 1x1 binning pixelscale
                'onebyone_pix_scale': 0.5283,  # This is the 1x1 binning pixelscale
                # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                'native_bin': 1,
                'x_pixel':  3.76,  # pixel size in microns
                'y_pixel':  3.76,  # pixel size in microns
                # 'field_x':  1.3992,   #4770*2*0.528/3600
                # 'field_y':  0.9331,    #3181*2*0.528/3600
                # 'field_sq_deg':  1.3056,
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.
                'drizzle_value_for_later_stacking': 0.5,
                'dither_enabled':  True,  # Set this way for tracking testing


                # This is the absolute minimum and maximum exposure for the camera
                'min_exposure': 0.0001,
                'max_exposure': 180.,
                # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'min_flat_exposure': 0.0005,
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 1.0,


                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain': True,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.
                # 'camera_gain':   2.15, #[10., 10., 10., 10.],     #  One val for each binning.
                # 'camera_gain_stdev':   0.16, #[10., 10., 10., 10.],     #  One val for each binning.
                # 'read_noise':  9.55, #[9, 9, 9, 9],    #  All SWAGs right now
                # 'read_noise_stdev':   0.004, #[10., 10., 10., 10.],     #  One val for each binning.
                'dark_lim_adu': 3.0,  # adu/s of dark 20231229 moved down from 0.5
                'dark_lim_std': 15,  # first guess. See above.
                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 65000,  # NB Guess
                'saturate':   62500,
                'max_linearity':  61000,   # Guess
                # How long does it take to readout an image after exposure
                'cycle_time':            2.0,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 30,
                'smart_stack_exposure_NB_multiplier':  3,  # Michael's setting
                'substack': True,

                # As simple as it states, how many calibration frames to collect and how many to store.
                'number_of_bias_to_collect': 31,
                'number_of_dark_to_collect': 13,
                'number_of_flat_to_collect': 7,  # increased from 5  20231226 WER
                'number_of_bias_to_store': 33,
                'number_of_dark_to_store': 27,
                'number_of_flat_to_store': 21,
                # Default dark exposure time.
                'dark_exposure': 180,

                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  True,
                'darkslide_type': 'bistable',
                'darkslide_can_report':  False,
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
    # This area should be re-purposed to introduce the pipeline and or an additional local mega-NAS.
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
    if str(site_config) == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')
