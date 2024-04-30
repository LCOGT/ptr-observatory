# -*- coding: utf-8 -*-
'''
Config for MRC1
'''
import json


'''
                                                                                                   1         1         1       1
         1         2         3         4         5         6         7         8         9         0         1         2       2
12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
'''

obs_id = 'mrc1'  # NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_config = {

    # Instance type specifies whether this is an obs or a wema
    'instance_type' : 'obs',
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name' : 'mrc',
    # The unique identifier for this obs
    'obs_id': 'mrc1',

    # Name, local and owner stuff
    'name': 'Mountain Ranch Camp Observatory 0m35 f7.2',
    'airport_code': 'SBA',
    'location': 'Near Santa Barbara CA,  USA',
    'telescope_description': '0m35 f7.2 Planewave CDK',
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'observatory_logo': None,
    'mpc_code':  'ZZ23',  # This is made up for now.
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',  # i.e, a multi-line text block supplied by the owner.  Must be careful about the contents for now.
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne
    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],


    # Default safety settings
    'safety_check_period': 45,  # MF's original setting.
    'closest_distance_to_the_sun': 45,  # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_moon': 3,  # Degrees. For normal pointing requests don't go this close to the moon.
    'minimum_distance_from_the_moon_when_taking_flats': 45,
    'lowest_requestable_altitude': 15,  # Degrees. For normal pointing requests don't allow requests to go this low.
    'lowest_acceptable_altitude' : -5.0, # Below this altitude, it will automatically try to home and park the scope to recover.
    'degrees_to_avoid_zenith_area_for_calibrations': 5,
    'degrees_to_avoid_zenith_area_in_general' : 0,
    'maximum_hour_angle_requestable' : 12,
    'temperature_at_which_obs_too_hot_for_camera_cooling' : 23,

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
    'temporary_local_pipe_archive_to_hold_files_while_copying' : 'D:/tempfolderforpipeline',
    'temporary_local_alt_archive_to_hold_files_while_copying' : 'D:/tempfolderforaltpath',

    # Setup of folders on local and network drives.
    'client_hostname':  'mrc-0m35',  # This is also the long-name  Client is confusing!
    'archive_path':  'D:/ptr/',  # Generic place for client host to stash misc stuff
    'local_calibration_path': 'D:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'plog_path':  'Q:/ptr/mrc1/',  # place where night logs can be found.
    'save_to_alt_path': 'no',
    'archive_age': 7,  # Number of days to keep files in the local archive before deletion. Negative means never delete

    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus file can not be saved.
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : False,
    # Number of files to send up to the ptrarchive simultaneously.
    'number_of_simultaneous_ptrarchive_streams' : 4,
    # Number of files to send over to the pipearchive simultaneously.
    'number_of_simultaneous_pipearchive_streams' : 4,
    # Number of files to send over to the altarchive simultaneously.
    'number_of_simultaneous_altarchive_streams' : 4,


    # Bisque mounts can't run updates in a thread ... yet... until I figure it out,
    # So this is False for Bisques and true for everyone else.
    'run_main_update_in_a_thread': True,
    'run_status_update_in_a_thread' : True,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.0,

    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats

    'bias_dark interval':  105.,   #minutes
    'eve_sky_flat_sunset_offset': -45.,  # 40 before Minutes  neg means before, + after.
    #'eve_sky_flat_sunset_offset': -45.,  # 40 before Minutes  neg means before, + after.
    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 5 ,
    'clock_and_auto_focus_offset': 8,

    'astro_dark_buffer': 30,   #Min before and after AD to extend observing window
    #'morn_flat_start_offset': -5,       #min from Sunrise
    'morn_flat_start_offset': -10,       #min from Sunrise
    'morn_flat_end_offset':  +45,        #min from Sunrise
    'end_night_processing_time':  90,   #  A guess
    'observing_begins_offset': 18,
    # How many minutes before Nautical Dawn to observe ....
    'observing_ends_offset': 18,



    # Exposure times for standard system exposures
    'focus_exposure_time': 5,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 20,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 1,    # How many minutes between weather checks
    'enclosure_check_period': 1,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': False,
    'auto_eve_sky_flat': False,

     'time_to_wait_after_roof_opens_to_take_flats': 120,   #Just imposing a minimum in case of a restart.
    'auto_midnight_moonless_bias_dark': False,
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': False,

    # FOCUS OPTIONS
    'periodic_focus_time': 12.0, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.75,  # What FWHM increase is needed to trigger an autofocus

    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 45,  # only update mount when X arcseconds away

    'defaults': {
        'mount': 'mount1',
        #'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector':  None,
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
    },
    'device_types': [
        'mount',
        #'telescope',
        'screen',    #  We do have one!  >>>>
        'rotator',
        'focuser',
        'selector',     #  Right now not used  >>>>
        'filter_wheel',
        'camera',
        'sequencer',    #NB I think we will add "engineering or telops" to the model >>>>
        'telops',       #   >>>>
    ],

    'mount': {
        'mount1': {       # NB There can only be one mount with our new model.  >>>>

            'tel_id': '0m35',
            'name': 'eastpier',
            'hostIP':  '10.15.0.30',
            'hostname':  'eastpier',
            'desc':  'Planewave L500 AltAz',
            'driver': 'ASCOM.PWI4.Telescope',  # Was 'ASCOM.AltAzDS.Telescope' prior to 20210417 WER
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'alignment': 'Alt-Az',
            'has_paddle': False,
            'pointing_tel': 'tel1',

            'default_zenith_avoid': 5.0,   #degrees floating
            'wait_after_slew_time': 0.0, # Some mounts report they have finished slewing but are still vibrating. This adds in some buffer time to a wait for slew.


            # Standard offsets to pointings
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction': 0.0,
            'east_flip_dec_correction': 0.0,  #

            # Activity before and after parking
            'home_after_unpark': True,
            'home_before_park': True,
            'settle_time_after_unpark' : 0,
            'settle_time_after_park' : 0,
            'time_inactive_until_park': 3600.0,  # How many seconds of inactivity until it will park the telescope

            # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly'
            'permissive_mount_reset': 'yes',

            'settings': {
                # Decimal degrees, North is Positive. These *could* be slightly different than site.
                'latitude_offset': 0.0,
                'longitude_offset': 0.0,  # Decimal degrees, West is negative
                'elevation_offset': 0.0,    # meters above sea level

                # For scopes that don't have a home postion in ASCOM,
                # These values are where to point on a home command.
                'home_altitude': 60,
                'home_azimuth': 359,

                # If there is a screen, where do I point at it?
                'fixed_screen_azimuth': 167.25,
                'fixed_screen _altitude': 0.54,

                # Information about the horizon around the scope.
                'horizon':  20,
                'horizon_detail': {  #In principle there can be slightly different Horizons for a multiple OTA obsp. >>>>
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

                # What is the TPOINT model for those scopes where
                # the mount software does not integrate these values.
                'model': {          #In principle different OTA's could have offsets.
                    'IH': 0,
                    'ID': 0.,
                    'WH': 0.,
                    'WD': 0.,
                    'MA': 0.,
                    'ME': 0.,
                    'CH': 0.,
                    'NP': 0.,
                    'TF': 0.,
                    'TX': 0.,
                    'HCES': 0.,
                    'HCEC': 0.,
                    'DCES': 0.,
                    'DCEC': 0.,
                    'IA': 0.0,
                    'IE': 0.0,
                    'CA': 0.0,
                    'NPAE': 0.0,
                    'AN': 0.0,
                    'AE': 0.0,  # AW?
                    'ACES': 0.0,
                    'ACEC': 0.0,
                    'ECES': 0.0,
                    'ECEC': 0.0,
                }

            },
        },

    },

    'telescope': {           #OTA or Optics might be a better name >>>>
        'telescope1': {      #MRC1 has two OTAs  >>>>
            #'parent': 'mount1',   #THis is redundant and unecessary >>>>
            'name': 'Main OTA',
            # 'desc':  'Planewave_CDK_14_F7.2',
            'telescop': 'mrc1',  # The tenth telescope at mrc will be 'mrc10'. mrc2 already exists.
            # the important thing is sites contain only a to z, but the string may get longer.
            #  From the BZ perspective TELESCOP must be unique
            'ptrtel': 'Planewave CDK 0.35m f7.2',
            'driver': 'None',  # Essentially this device is informational.  It is mostly about the optics.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'collecting_area':  76147,  # 178*178*math.pi*0.765
            'obscuration':  23.5,
            'aperture': 356,
            'f-ratio':  7.2,  # This and focal_length can be refined after a solve.
            'focal_length': 2563,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,  # This is a default for a single instrument system
            'selector_positions': 1,  # Note starts with 1
            'instrument names':  ['camera_1_1'],
            'instrument aliases':  ['QHY600Mono'],
            'configuration': {
                "position1": ["darkslide1", "filter_wheel1", "filter_wheel2", "camera1"]
            },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'filter_wheel1',
            'has_fans':  True,
            'has_cover': False,
            'settings': {
                'fans': ['Auto', 'High', 'Low', 'Off'],
                'offset_collimation': 0.0,  # If the mount model is current, these numbers are usually near 0.0
                #  for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  # new terms.
                'west_flip_ca_offset': 0.0,
                'west_flip_dec_offset': 0.0
            },
        },
# =============================================================================
#         'ota2': {      #Where the second OTA stuff goes
#         },
# =============================================================================
    },

    'rotator': {
        'rotator1': {
            'parent': 'telescope1',
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.AltAzDS.Rotator',
            'telescope_driver': 'ASCOM.AltAzDS.Telescope',
            'com_port':  None,
            'minimum': -180.0,
            'maximum': 360.0,
            'step_size':  0.0001,
            'backlash':  0.0,
            'unit':  'degree',
            'has_rotator': True  # Indicates to camera and Project to include rotation box.
        },
# =============================================================================
#         'rotator2': {    # >>>>
#         },
# =============================================================================

    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'Optec Alnitak 24"',
            'driver': None,  # This needs to be a four or 5 character string as in 'COM8' or 'COM22'
            'com_port': 'COM10',
            'minimum': 5.0,  # This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 170,  # Out of 0.0 - 255, this is the last value where the screen is linear with output.
                                # These values have a minor temperature sensitivity we have yet to quantify.
        },
# =============================================================================
#         'screen2': {       # >>>>
#             'parent': 'ota2',
#             'name': 'screen',
#             'desc':  'Optec Alnitak 24"',
#             'driver': 'None',  # This needs to be a four or 5 character string as in 'COM8' or 'COM22'
#             'com_port': 'COM99',
#             'minimum': 5.0,  # This is the % of light emitted when Screen is on and nominally at 0% bright.
#             'saturate': 170,  # Out of 0.0 - 255, this is the last value where the screen is linear with output.
#                                 # These values have a minor temperature sensitivity yet to quantify.
#         },
# =============================================================================
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',

            'focuser_movement_settle_time': 3,

            # Override the estimated best focus and start at the provided config value
            'start_at_config_reference': False,
            # Use previous best focus information to correct focuser for temperature change
            'correct_focus_for_temperature' : True,
            # highest value to consider as being in "good focus". Used to select last good focus value
            'maximum_good_focus_in_arcsecond': 3.0,

            # When the focusser has no previous best focus values
            # start from this reference position
            'reference': 7250,

            # Limits and steps for the focuser.
            'minimum': 0,    # NB this needs clarifying, we are mixing steps and microns.
            'maximum': 12700,
            'step_size': 1,
            'backlash':  0,
            'throw': 250,
            'unit': 'micron',
            'unit_conversion':  9.09090909091,  # Taken from Gemini at mid-range.
        },
# =============================================================================
#         'focuser2': {         # >>>>
#             'parent': 'ota2',
#             'name': 'focuser',
#             'desc':  'Optec Gemini',
#             'driver': 'ASCOM.OptecGemini.Focuser',
#             'start_at_config_reference': False,
#             'use_focuser_temperature': True,
#             # *********Guesses   7379@10 7457@20  7497 @ 25
#             # 'reference': 7250, #20221103    #7418,    # Nominal at 15C Primary temperature, in microns not steps. Guess
#             'reference': 7250,  # 20221103    #7418,    # Nominal at 15C Primary temperature, in microns not steps. Guess
#             'ref_temp':  10,      # Update when pinning reference  Larger at lower temperatures.
#             'coef_c': -8.583,    # Negative means focus moves out (larger numerically) as Primary gets colder
#             # 'coef_0': 7250,  #20221103# Nominal intercept when Primary is at 0.0 C.
#             'coef_0': 7355,  # 20221103# Nominal intercept when Primary is at 0.0 C.
#             'coef_date':  '20230220',  # A Guess as to coef_c
#             'z_compression': 0.0,  # microns per degree of zenith distance
#             'z_coef_date':  '20221002',   # 'reference': 4375,    #   Guess 20210904  Nominal at 10C Primary temperature
#             'use_local_temp':  True,
#             'minimum': 0,    # NB this needs clarifying, we are mixing steps and microns.
#             'maximum': 12700,
#             'step_size': 1,
#             'backlash':  0,
#             'throw': 250,
#             'unit': 'micron',
#             'unit_conversion':  9.09090909091,  # Taken from Gemini at mid-range.
#             'has_dial_indicator': False
#         },
#
# =============================================================================
    },
    'selector': {
        'selector1': {
            'parent': 'telescope1',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': None,
            'com_port': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 1,
            'instruments':  ['Main_camera'],  # , 'eShel_spect', 'planet_camera', 'UVEX_spect'],
            'cameras':  ['camera_1_1'],  # , 'camera_1_2', None, 'camera_1_4'],
            'guiders':  [None],  # , 'guider_1_2', None, 'guide_1_4'],
            'default': 0
        },

    },
    # Add CWL, BW and DQE to filter and detector specs.   HA3, HA6 for nm or BW.
    'filter_wheel': {
        "filter_wheel1": {
            "parent": "telescope1",
            "alias": "Dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            # 'ASCOM.FLI.FilterWheel',   #['ASCOM.FLI.FilterWheel1', 'ASCOM.FLI.FilterWheel2'],   #"Maxim",   #"Maxim.CCDCamera",  #
            "driver": "Maxim.CCDCamera",
            # "driver":   'ASCOM.FLI.FilterWheel',   #  NB THIS IS THE NEW DRIVER FROM peter.oleynikov@gmail.com  Found in Kepler ASCOM section
            "dual_wheel": True,

            #how long to wait for the filter to settle after a filter change(seconds)
            "filter_settle_time": 5, #20240104 Upped from 1 to 5 per MF recommandatin. WER

            # This ignores the automatically estimated filter gains and starts with the values from the config file
            'override_automatic_filter_throughputs': False,
            # WER - if there is no filter wheel, then these two are used, otherwise they are harmless
            "name": "RGGB",

            'ip_string': "",
            'settings': {

                'default_filter':  'PL',

                'auto_color_options': ['OSC'],  # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
                # B, G, R filter codes for this camera if it is a monochrome camera with filters
                'mono_RGB_colour_filters': ['pb', 'pg', 'pr'],
                'mono_RGB_relative_weights': [1.2, 1, 0.8],
                # ha, o3, s2 filter codes for this camera if it is a monochrome camera with filters
                'mono_Narrowband_colour_filters': ['ha', 'o3', 's2'],
                'mono_Narrowband_relative_weights': [1.0, 2, 2.5],


                # 'filter_data': [['air',     [0, 0], -1000,  2960,    [2, 17], 'ai'],  # 0 Surface ws 1400Lux at end of night run  Sun Akt 0,97 degrees
                #                 # 1  330NB NB NB If this in series should change focus about 1mm more.
                #                 ['dif',     [4, 0],     0,  16.00,   [2, 17], 'df'],
                #                 ['w',       [2, 0],     0,  2740,    [2, 17], 'w '],  # 2 346
                #                 ['PL',      [0, 4],     0,  2430,    [2, 17], "PL"],  # 3 317
                #                 ['gp',      [0, 6],     0,  2200,    [2, 17], 'gp'],  # 4
                #                 ['PB',      [0, 1],     0,  2050,    [2, 17], 'PB'],  # 5
                #                 ['PG',      [0, 2],     0,  1185,    [2, 17], 'PG'],  # 6
                #                 ['rp',      [0, 7],     0,  920,     [2, 17], 'rp'],  # 7
                #                 ['PR',      [0, 3],     0,  450,     [2, 17], 'PR'],  # 8
                #                 ['ip',      [0, 8],     0,  327,     [2, 17], 'ip'],  # 9
                #                 ['z',       [5, 0],     0,  58,      [2, 17], 'z'],  # 10
                #                 ['O3',      [7, 0],     0,  43,      [2, 17], '03'],  # 11
                #                 ['CR',      [1, 0],     0,  33,      [2, 17], 'CR'],  # 12
                #                 ['up',      [0, 5],     0,  29,      [1, 17], 'up'],  # 13
                #                 ['N2',      [3, 0],     0,  17,      [2, 17], 'N2'],  # 14
                #                 ['HA',      [6, 0],     0,  15.5,    [2, 17], 'HA'],  # 15
                #                 ['S2',      [8, 0],     0,  15,      [2, 17], 'S2'],  # 16 20240109 eve  Clear bright sky perfect evening

                #                 ['dark',    [8, 5],     0,  0.0,     [2, 17], 'dk']],  # 17


                'filter_data': [['air',     [0, 0],  'ai'],  # 0 Surface ws 1400Lux at end of night run  Sun Akt 0,97 degrees
                                # 1  330NB NB NB If this in series should change focus about 1mm more.
                                ['dif',     [4, 0],   'df'],
                                ['w',       [2, 0],  'w '],  # 2 346
                                ['PL',      [0, 4],    "PL"],  # 3 317
                                ['gp',      [0, 6],    'gp'],  # 4
                                ['PB',      [0, 1],    'PB'],  # 5
                                ['PG',      [0, 2],   'PG'],  # 6
                                ['rp',      [0, 7],   'rp'],  # 7
                                ['PR',      [0, 3],   'PR'],  # 8
                                ['ip',      [0, 8],   'ip'],  # 9
                                ['z',       [5, 0],   'z'],  # 10
                                ['O3',      [7, 0],    '03'],  # 11
                                ['CR',      [1, 0],    'CR'],  # 12
                                ['up',      [0, 5],   'up'],  # 13
                                ['N2',      [3, 0],   'N2'],  # 14
                                ['HA',      [6, 0],    'HA'],  # 15
                                ['S2',      [8, 0],     'S2'],  # 16 20240109 eve  Clear bright sky perfect evening

                                ['dark',    [8, 5],     'dk']],  # 17

                'focus_filter' : 'w',

                # # Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                # 'filter_screen_sort':  ['air', 'w', 'PL', 'gp', 'PB', 'rp', 'PG', 'PR', 'ip', 'O3', 'N2', 'CR', 'S2', 'HA'],  # 9, 21],  # 5, 17], #Most to least throughput, \
                # # so screen brightens, skipping u and zs which really need sky.

                # 'filter_sky_sort':     ['S2', 'HA', 'n2', 'up', 'CR', 'O3', 'z', 'ip', 'PR', 'rp', 'PG', 'PB', 'gp', 'PL', 'w', 'air'],

            },
        },
# =============================================================================
#         'filter_wheel_2': {      #   >>>>
#         },
# =============================================================================

    },


# =============================================================================  >>>>
#     'lamp_box': {
#         'lamp_box1': {
#             'parent': 'camera_1',  # Parent is camera for the spectrograph
#             'name': 'None',  # "UVEX Calibration Unit", 'None'
#             'desc': 'None',  # 'eshel',  # "uvex", 'None'
#             'spectrograph': 'None',  # 'echelle', 'uvex'; 'None'
#             'driver': 'None',  # ASCOM.Spox.Switch; 'None'; Note change to correct COM port used for the eShel calibration unit at mrc2
#             'switches': "None"  # A string of switches/lamps the box has for the FITS header. # 'None'; "Off,Mirr,Tung,NeAr" for UVEX
#         },
#     },
# =============================================================================



    # A site may have many cameras registered (camera1, camera2, camera3, ...) each with unique aliases -- which are assumed
    # to be the name an owner has assigned and in principle that name "kb01" is labeled and found on the camera.  Between sites,
    # there can be overlap of camera names.  LCO convention is letter of cam manuf, letter of chip manuf, then 00, 01, 02, ...
    # However this code will treat the camera name/alias as a string of arbitrary length:  "saf_Neyle's favorite_camera" is
    # perfectly valid as an alias.


    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'sq003cm',  # Important because this points to a server file structure by that name.
            'desc':  'QHY 410 Color',
            #'driver':  "ASCOM.QHYCCD_CAM2.Camera", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control",
            'service_date': '20231205',  #Replaced sq005mm which appears to have a circuit failure with prior QHY6oo. Left name unchanged.



            'detector':  'Sony IMX455 BI Mono',  # It would be good to build out a table of chip characteristics
            'use_file_mode':  False,   # NB we should clean out all file mode stuff.
            'file_mode_path':  'Q:/archive/sq01/maxim/',  # NB NB all file_mode Maxim stuff should go!
            'manufacturer':  "QHY",
            'settings': {

                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,


                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True,

                # Simple Camera Properties
                'is_cmos':  True,
                'is_osc': True,
                'is_color': True,  # NB we also have a is_osc key.
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
                #
                # QHY410C is gain 0, offset 9, mode 1
                'direct_qhy_readout_mode': 1,  #These settings may be wrong. WER 20230712

                'direct_qhy_gain': 0,
                'direct_qhy_offset': 9,
                'set_qhy_usb_speed': True,
                'direct_qhy_usb_traffic' : 60,     #NB NB Why two keys/
                #'direct_qhy_usb_speed' : 60,      #NB used in saving the image header.





                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                'interpolate_for_focus': True,
                # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'bin_for_focus': False,
                'focus_bin_value' : 1,
                'interpolate_for_sep': False,
                'bin_for_sep': False,  # This setting will bin the image for SEP photometry rather than interpolating.
                'sep_bin_value' : 1,
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
                'squash_on_x_axis': True,

                # What number of pixels to crop around the edges of a REDUCED image
                # This is primarily to get rid of overscan areas and also all images
                # Do tend to be a bit dodgy around the edges, so perhaps a standard
                # value of 30 is good. Increase this if your camera has particularly bad
                # edges.
                'reduced_image_edge_crop': 50,

                # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
                # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
                # RECOMMENDED DEFAULT DESIRE OF PTR
                'transpose_jpeg': False,
                'flipx_jpeg': False,
                'flipy_jpeg': False,
                'rotate180_jpeg': False,
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
                'focus_jpeg_size': 750, # How many pixels square to crop the focus image for the UI Jpeg

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
                'temp_setpoint': -2,  # Verify we can go colder
                'has_chiller': True,
                'chiller_com_port': 'COM1',
                'chiller_ref_temp':  15.0,  # C
                'day_warm': False,
                'day_warm_degrees': 8,  # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : False,


                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.
                'onebyone_pix_scale': 0.478,    #  This is the 1x1 binning pixelscale
                'native_bin': 1, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                'x_pixel':  5.94, # pixel size in microns
                'y_pixel':  5.94, # pixel size in microns

                #Please do not remove the following:  9576*6388
                # WAYNE - x field and y field are already calculated within camera.py on bootup and send up in the config
                # we don't neeed these values. Carolina is also calculating it already at the UI.
                # I made it calculate it directly PRECISELY because of incorrect values in the config file.

                #As long as the numbers below are here, even commented out, that if fine.
                #'x_field':  46.8, # amin  0.30259*9276/60   NB subtractedd 100 pix for trim
                #'y_field':  31.7, # amin  0k.30259*6288/60   NB subtractedd 100 pix for trim


                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.
                'drizzle_value_for_later_stacking': 0.5,
                'dither_enabled':  True,      #Set this way for tracking testing


                # This is the absolute minimum and maximum exposure for the camera
                'min_exposure': 0.0001,
                'max_exposure': 360.,
                # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'min_flat_exposure': 0.0001,
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 0.001,

                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain' : True,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.
                'camera_gain':   8.634, #[10., 10., 10., 10.],     #  One val for each binning.
                'camera_gain_stdev':   0.4, #[10., 10., 10., 10.],     #  One val for each binning.
                'read_noise':  47.74, #[9, 9, 9, 9],    #  All SWAGs right now
                'read_noise_stdev':   0.03, #[10., 10., 10., 10.],     #  One val for each binning.
                'dark_lim_adu': 0.15,   #adu/s of dark 20231229 moved down from 0.5
                'dark_lim_std': 15,  #first guess. See above.
                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 80000,  # NB Guess
                'saturate':   65535,
                'max_linearity':  60000,   # Guess
                # How long does it take to readout an image after exposure
                'cycle_time':            2.0,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 30,

                'smart_stack_exposure_NB_multiplier':  3,   #Michael's setting
                
                'substack': True, # Substack with this camera


                # As simple as it states, how many calibration frames to collect and how many to store.
                'number_of_bias_to_collect': 17,
                'number_of_dark_to_collect': 17,
                'number_of_flat_to_collect': 15,
                'number_of_bias_to_store': 63,
                'number_of_dark_to_store': 31,
                'number_of_flat_to_store': 31,
                # Default dark exposure time.
                'dark_exposure': 180,


                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  True,
                'darkslide_com':  'COM15',
                'shutter_type': "Electronic",
                'darkslide_type': "bistable",

                # 'has_screen': True,
                # 'screen_settings':  {
                #     'screen_saturation':  157.0,
                #     'screen_x4': -4E-12,  # 'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                #     'screen_x3':  3E-08,
                #     'screen_x2': -9E-05,
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
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
        },
    },
    'telops': {        #>>>>
        'sequencer1': {
            'parent': 'site',
            'name': 'Telops Scripts',
            'desc':  'Engineering Control',
            'driver': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
        },
    },
    # As aboove, need to get this sensibly suported on GUI and in fits headers.



    # # AWS does not need this, but my configuration code might make use of it.
    # 'server': {
    #     'server1': {
    #         'name': 'QNAP',
    #         'win_url': 'archive (\\10.15.0.82) (Q:)',
    #         'redis':  '(host=10.15.0.15, port=6379, db=0, decode_responses=True)',
    #         'startup_script':  None,
    #         'recover_script':  None,
    #         'shutdown_script':  None,
    #     },
    # },
}  # This brace closes the whole configuration dictionary. Match found up top at:  obs_config = {


if __name__ == '__main__':
    '''
    This is a simple test to send and receive via json.
    '''

    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config) == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')

