# -*- coding: utf-8 -*-
'''
Config for MRC1

October_30 Version.  Generally trying to simplify and streamline the code and improve breakpoint- and debug-ability.

Re-organizing obs-config to better cluster common themes like safety settings, camera configuration ...

On Threads and Concurency:

    The inner loop for the active cameras must be able to run fast.  So as an example, breaking out of it to read overall
    ASCOM status, or tending to the incoming command queue looking for  STOP/Cancel is not a good idea.  However just how
    precise in time status has to be is debatable, since we can reliably platesolve.


'''
import json


'''
                                                                                                   1         1         1       1
         1         2         3         4         5         6         7         8         9         0         1         2       2
12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678


'''
#pOWER SWITCH ON 10.15.0.60  CHANNEL 3 not the ones marked Camera


obs_id = 'aro2'  # NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_config = {

    # Instance type specifies whether this is an obs or a wema
    'instance_type' : 'obs',
    'instance_is_private': False,
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name' : 'aro',
    # The unique identifier for this obs
    'obs_id': 'aro2',

    # Name, local and owner stuff
    'name': "Apache Ridge Observatory  PW 0m45 f6.8  52'X39'",
    'airport_code': 'SAF',
    'location': 'Santa Fe, New Mexico,  USA',
    'telescope_description': 'PW 0m45 F6.8',
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'observatory_logo': None,
    'mpc_code':  'ZZ23',  # This is made up for now.
    'dedication':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',  # i.e, a multi-line text block supplied by the owner.  Must be careful about the contents for now.
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne
    'owner_alias': ['ANS', 'WER'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "MF",  "TB"],

    # Default safety settings
    'safety_check_period': 120,  # MF's original setting was 45.

    # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_sun': 30,
    # Degrees. For normal pointing requests don't go this close to the moon.
    'closest_distance_to_the_moon': 5,
    'minimum_distance_from_the_moon_when_taking_flats': 30,
    # Degrees. For normal pointing requests don't allow requests to go this low.
    'lowest_requestable_altitude': 20,
    # Below this altitude, it will automatically try to home and park the scope to recover.
    'lowest_acceptable_altitude': 0,
    'degrees_to_avoid_zenith_area_for_calibrations': 0,
    'degrees_to_avoid_zenith_area_in_general': 3,
    'maximum_hour_angle_requestable': 9,  #This limit makes little sense
    # NB NB WER ARO Obs has a chiller
    'temperature_at_which_obs_too_hot_for_camera_cooling': 30,

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
    'always_do_a_centering_exposure_regardless_of_nearby_reference': True,
    'owner_only_commands': False,


    # Default safety settings
    'eng_mode': True,
    'has_lightning_detector': False,
    # 'safety_check_period': 45,  # MF's original setting.
    # 'closest_distance_to_the_sun': 45,  # Degrees. For normal pointing requests don't go this close to the sun.
    # 'closest_distance_to_the_moon': 3,  # Degrees. For normal pointing requests don't go this close to the moon.
    # 'minimum_distance_from_the_moon_when_taking_flats': 30,
    # 'lowest_requestable_altitude': 15,  # Degrees. For normal pointing requests don't allow requests to go this low.
    # 'lowest_acceptable_altitude' : 10, # Below this altitude, it will automatically try to home and park the scope to recover.
    # 'degrees_to_avoid_zenith_area_for_calibrations': 5,
    # 'degrees_to_avoid_zenith_area_in_general' : 0,  #Hill prevents seeing much below pole @ MRC
    # 'temperature_at_which_obs_too_hot_for_camera_cooling' : 30,

    # # These are the default values that will be set for the obs
    # # on a reboot of obs.py. They are safety checks that
    # # can be toggled by an admin in the Observe tab.
    # 'scope_in_manual_mode': False,   #This is poorly named  the Enclosure is Manual vs Auto
    # 'mount_reference_model_off': False,
    # 'sun_checks_on': False,
    # 'moon_checks_on': False,
    # 'altitude_checks_on': False,
    # 'daytime_exposure_time_safety_on': False,

    # Depending on the pointing capacity of the scope OR the field of view OR both
    # The pointing may never be quite good enough to center the object without
    # a centering exposure. On initial commissioning, it should be set to always autocenter
    # until you are convinced the natural pointing with empirical corrections is "good enough"


    # NB NB NB we should specify has_pipe# has_redis   and IP of redis   WER



    # Setup of folders on local and network drives.
    'ingest_raws_directly_to_archive': False,   #which archive? I assume not the datalab / ptrarchive , but 'injest' implies LCO archive  WER
    'save_calib_and_misc_files': True,
    # LINKS TO PIPE FOLDER
    'save_raws_to_pipe_folder_for_nightly_processing': True,
    'pipe_archive_folder_path': 'X:/localptrarchive/',  #WER changed Z to X 20231113 @1:16 UTC
    # 'temporary_local_pipe_archive_to_hold_files_while_copying' : 'D:/tempfolderforpipeline',
    # 'temporary_local_alt_archive_to_hold_files_while_copying' : 'D:/tempfolderforaltpath',
    'client_hostname':  'mrc-0m30',  # This is also the long-name  Client is confusing!
    'archive_path':  'D:/ptr/',  # Generic place for client host to stash misc stuff
    'local_calibration_path': 'D:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files
    'alt_path':  'D:/ptr/',  # Generic place for this host to stash misc stuff
    'plog_path':  'D:/ptr/aro2/',  # place where night logs can be found.
    'save_to_alt_path': 'no',
    'archive_age': 2,  # Number of days to keep files in the local archive before deletion. Negative means never delete

    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    'save_substack_components_raws': True, # this setting saves the component 10s/30s completely raw files out as well during a substack
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus file can not be saved.
    # These are options to minimise diskspace for calibrations
    'produce_fits_file_for_final_calibrations': True,
    'save_archive_versions_of_final_calibrations' : False,
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : False,
    # Number of files to send up to the ptrarchive simultaneously.
    'number_of_simultaneous_ptrarchive_streams' : 4,
    # Number of files to send over to the pipearchive simultaneously.
    'number_of_simultaneous_pipearchive_streams' : 4,
    # Number of files to send over to the altarchive simultaneously.
    'number_of_simultaneous_altarchive_streams' : 4,


    'push_file_list_to_pipe_queue': False,

    # The site can fully platesolve each image before it is sent off to s3 or a PIPE
    # If there are spare enough cycles at the site, this saves time for the PIPE
    # to concentrate on more resource heavy reductions.
    # Also leads to fully platesolved reduced images on the local site computer
    # Usually set this to True
    # if the scope has a decent NUC.... CURRENTLY LEAVE AS IS UNTIL MTF HAS FINISHED TESTING THIS.
    'fully_platesolve_images_at_site_rather_than_pipe' : True,



    "platesolve_timeout": 60, # Default should be about 45 seconds, but slower computers will take longer

    # Bisque mounts can't run updates in a thread ... yet... until I figure it out,
    # So this is False for Bisques and true for everyone else.
    'run_main_update_in_a_thread': True,
    'run_status_update_in_a_thread' : True,

    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.5,
    'has_lightning_detector': False,

    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats

    'bias_dark interval':  120.,   #minutes
    'eve_sky_flat_sunset_offset': -30.,  # 40 before Minutes  neg means before, + after.
    #'eve_sky_flat_sunset_offset': -45.,  # 40 before Minutes  neg means before, + after.
    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 15 ,
    'clock_and_auto_focus_offset': -10,

    'astro_dark_buffer': 10,   #Min before and after AD to extend observing window
    #'morn_flat_start_offset': -5,       #min from Sunrise
    'morn_flat_start_offset': -10,       #min from Sunrise
    'morn_flat_end_offset':  +40,        #min from Sunrise
    'end_night_processing_time':  90,   #  A guess
    'observing_begins_offset': 18,
    # How many minutes before Nautical Dawn to observe ....
    'observing_ends_offset': 18,



    # Exposure times for standard system exposures
    'focus_exposure_time': 5,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 12,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 3,    # How many minutes between weather checks
    'enclosure_check_period': 3,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': True,
    'auto_eve_sky_flat': True,

     'time_to_wait_after_roof_opens_to_take_flats': 3,   #Just imposing a minimum in case of a restart.
    'auto_midnight_moonless_bias_dark': True,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark':  True,

    # FOCUS OPTIONS
    'periodic_focus_time': 2, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.5,  # What FWHM increase is needed to trigger an autofocus

    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image   #20250112  Changed these two to make some sense. WER  Not rebooting tonight for this.
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 45,  # only update mount when X arcseconds away
    'limit_mount_tweak': 15,




    'defaults': {
        'mount': 'aropier2',
        #'telescope': 'Main OTA',
        'focuser': 'focuser',
        'rotator': 'rotator',
        'selector':  None,
        'screen': 'screen',
        'filter_wheel': 'Dual filter wheel',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer'
    },
    # Initial roles are assigned here. These may change during runtime.
    # Value is the device display name
    # This is where to configure a second device of the same type if you want to control it in the site code.
    # Devices are referenced in obs with self.devices['device_role']
    # Also important to note: these must match the roles in obs.py create_devices().
    # Roles are standardized across all sites even if not all roles are used at each site.
    'device_roles': {
        'mount': 'aropier2',
        'main_rotator': 'rotator',
        'main_focuser': 'focuser',
        'main_fw': 'Dual filter wheel',

        # Cameras
        'main_cam': 'camera_1_1',
        # Cameras below aren't currently used, but here as an example.
        'guide_cam': None,
        'widefield_cam': None,
        'allsky_cam': None,
    },
    'device_types': [
        'mount',
        #'telescope',
        #'screen',    #  We do have one!  >>>>
        'rotator',
        'focuser',
        'selector',     #  Right now not used  >>>>
        'filter_wheel',
        'camera',
        'sequencer',    #NB I think we will add "engineering or telops" to the model >>>>
        #'telops',       #   >>>>
    ],

    'mount': {
        'aropier2': {       # NB There can only be one mount with our new model.  >>>>
             'parent': 'enclosure1',
            'tel_id': '0m35',
            'name': 'aropier2',
            'hostIP':  '10.0,0.102',
            'hostname':  'aro2-0m45',
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
            'needs_to_wait_for_dome' : False,

            # Standard offsets to pointings
            'west_clutch_ra_correction': 0.0,
            'west_clutch_dec_correction': 0.0,
            'east_flip_ra_correction': 0.0,
            'east_flip_dec_correction': 0.0,  #

            # Activity before and after parking
            'home_after_unpark': False,
            'home_before_park': False,
            'settle_time_after_unpark' : 5,
            'settle_time_after_park' : 5,
            'time_inactive_until_park': 900.0,  # How many seconds of inactivity until it will park the telescope

            # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly'
            'permissive_mount_reset': 'no',

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
                'fixed_screen_azimuth': 189.0,
                'fixed_screen _altitude': 0.0,

                # Information about the horizon around the scope.
                'horizon':  25,
                'horizon_detail': {  #In principle there can be slightly different Horizons for a multiple OTA obsp. >>>>
                      '0.0': 25.,
                      '90': 25.,
                      '180': 25.,
                      '270': 25.,
                      '359': 25.
                },
                'ICRS2000_input_coords':  True,
                # Refraction is applied during pointing.
                'refraction_on': False,
                'model_on': False,
                'model_type': "Alt_Az",
                # Rates implied by model and refraction applied during tracking.
                'rates_on': False,
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
    #            round(206255*6/(1468*1000), 3)
    #                                                         3.76 micron     6 KAF     9 KAF 11 Marana   15 FLI
    # Roh 350 F3.0, 142.2 BFL, 1050 FL, 350 Ap   56%   60mm   0.739 asec/pix
    # Hon 305 F3.8  162   BFL, 1159 FL, 305 Ap   24%   60mm   0.669 asec/pix
    # Cer 300 F4.9  183   BFL, 1468 FL, 300 Ap   55%   55mm   0.528 asec/pix  0.843
    # CDK 300 F8.0, 265   BFL, 2541 FL, 318 Ap   42%   52mm   0.305 asec/pix  0.487
    # CDK 350 F7.2, 282   BFL, 2563 FL. 356 Ap.  48.5% 52mm   0.303 asec/pix
    # CDK 450 F6.8, 262.3 BFL, 2939 FL, 432 Ap.  48.6% 70mm   0.264 asec/pix  0.421
    # DFM 400 f8,              3200 FL, 600 AP,               0.242           0.387     0.580  0.709      0.967
    # CDk 600 F6.5, 364.5 BFL, 3962 FL, 610 Ap,  47%   70mm   0.196 asec/pix  0.312     0.469  0.573      0.781
    # DFM 600 f8,              4800 FL, 600 AP,               0.162                     0.387  0.473      0.645



    'telescope': {           #OTA or Optics might be a better name >>>>
        'Main OTA': {      #MRC1 has two OTAs  >>>>
            #'parent': 'eastpier',   #THis is redundant and unecessary >>>>
            'name': 'Main OTA',
            'desc':  'Planewave_CDK_17_F6.8',
            'telescop': 'aro2',  # The tenth telescope at mrc will be 'mrc10'. mrc2 already exists.
            # the important thing is sites contain only a to z, but the string may get longer.
            #  From the BZ perspective TELESCOP must be unique
            'ptrtel': 'APW 450, CDK.',
            'driver': 'None',  # Essentially this device is informational.  It is mostly about the optics.
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'collecting_area':  111836, #  79410.55*0.76
            'obscuration':  23.7,  # %
            'aperture': 432.0,
            'f-ratio':  6.8,  # This and focal_length can be refined after a solve.
            'focal_length':  2939.0,   #An earlier measurement found 1121mm for this and 0.691775 fr the pixel scale.
                                       #We need more data before changing these from the factory spec. 20250112 WER
            'screen_name': 'screen',
            'focuser_name':  'focuser',
            'rotator_name':  'rotator',
            'has_instrument_selector': False,  # This is a default for a single instrument system
            'selector_positions': 1,  # Note starts with 1
            'instrument names':  ['camera_1_1'],
            'instrument aliases':  ['QHY461Mono'],
            'configuration': {
                "position1": ["darkslide1", "filter_wheel1", "filter_wheel2", "camera_1_1"]
            },
            'camera_name':  'camera_1_1',
            'filter_wheel_name':  'Dual filter wheel',
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
        'rotator': {
            'parent': 'Main OTA',
            'name': 'rotator',
            'desc':  'Opetc Gemini',
            'driver': 'ASCOM.AltAzDS.Rotator',  #ASCOM.AltAzDS.Rotator','   #ASCOM.OptecGemini1.Rotator, ASCOM.OptecGemini.Rotator
            'telescope_driver': 'ASCOM.AltAzDS.Telescope',  #No longer needed??
            'com_port':  'COM14',
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
        'screen': {
            'parent': 'Main OTA',
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
        'focuser': {
            'parent': 'Main OTA',
            'name': 'focuser',
            'desc':  'Optec Gemini',
            'driver': 'ASCOM.OptecGemini.Focuser',

            'focuser_movement_settle_time': 3,

            # Override the estimated best focus and start at the provided config value
            'start_at_config_reference': False,
            # Use previous best focus information to correct focuser for temperature change
            'correct_focus_for_temperature' : True,
            # highest value to consider as being in "good focus". Used to select last good focus value
            'maximum_good_focus_in_arcsecond': 3,

            # When the focusser has no previous best focus values
            # start from this reference position

            'reference': 4875,  #20250326 @ 10.7C Run after adjusting collar
            'z_compression': 0, #Not used as of 20250111
            'z_coef_date':  '20250325',
            'relative_focuser': False,
            # Limits and steps for the focuser.
            'minimum': 0,    #  Units are microns
            'maximum': 12700,
            'step_size': 1.0,   #  This is misnamed!
            'backlash':  300,
            'throw': 200,
            'focus_tolerance':  130,
            'unit': 'micron',
            'unit_conversion':  9.09090909091,  #  Steps per micron
            'has_dial_indicator': False
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
        'selector': {
            'parent': 'Main OTA',
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
        "Dual filter wheel": {
            "parent": "Main OTA",
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

                'default_filter':  'w',

                'auto_color_options': ['OSC'],  # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
                # B, G, R filter codes for this camera if it is a monochrome camera with filters
                'mono_RGB_colour_filters': ['pr', 'pg', 'pb'],
                'mono_RGB_relative_weights': [0.8, 1, 2],
                # ha, o3, s2 filter codes for this camera if it is a monochrome camera with filters
                'mono_Narrowband_colour_filters': ['ha', 'o3', 's2'],  #these should implement basic Hubble or CFHT Pallets
                'mono_Narrowband_relative_weights': [1.0, 2, 2.5],  #Consider adding CWL and BW to the table below

                'filter_data': [['air',     [0, 0],   'ai'],  # 1
                                ['V',       [1, 0],   'V '],  # 2  Wheel closest to camera
                                ['B',       [2, 0],   "B "],  # 3
                                ['zs',      [3, 0],   "zs"],  # 4
                                ['w',       [4, 0],   'w '],  # 5
                                ['up',      [5, 0],   'up'],  # 6
                                ['gp',      [6, 0],   'gp'],  # 7
                                ['rp',      [7, 0],   'rp'],  # 8
                                ['ip',      [8, 0],   'ip'],  # 9

                                ['sy',      [0, 1],   'sy'],  # 10 Wheel closest to rotator
                                ['sb',      [0, 2],   'sb'],  # 11
                                ['sv',      [0, 3],   'sv'],  # 12
                                ['su',      [0, 4],   'su'],  # 13
                                ['O3',      [0, 5],   'o3'],  # 14
                                ['Hb',      [0, 6],   'hb'],  # 15
                                ['Ha',      [0, 7],   "ha"],  # 16
                                ['S2',      [0, 8],   's2'],  # 17
                                ['dk',      [5 ,8],   'dk']], # 18

                # 'filter_data': [['air',     [0, 0],   'ai'],  # 1
                #                 ['V',       [0, 1],   'V '],  # 2  Wheel closest to camera
                #                 ['B',       [0, 2],   "B "],  # 3
                #                 ['zs',      [0, 3],   "zs"],  # 4
                #                 ['w',       [4, 0],   'w '],  # 5
                #                 ['up',      [0, 5],   'up'],  # 6
                #                 ['gp',      [0, 6],   'gp'],  # 7
                #                 ['rp',      [0, 7],   'rp'],  # 8
                #                 ['ip',      [0, 8],   'ip'],  # 9

                #                 ['sy',      [1, 0],   'sy'],  # 10 Wheel closest to rotator
                #                 ['sb',      [2, 0],   'sb'],  # 11
                #                 ['sv',      [3, 0],   'sv'],  # 12
                #                 ['su',      [4, 0],   'su'],  # 13
                #                 ['O3',      [5, 0],   'o3'],  # 14
                #                 ['Hb',      [6, 0],   'hb'],  # 15
                #                 ['Ha',      [7, 0],   "ha"],  # 16
                #                 ['S2',      [8, 0],   's2'],  # 17
                #                 ['dk',      [8, 5],   'dk']], # 18

                'focus_filter' : 'w',

                # # Screen = 100; QHY400 ~ 92% DQE   HDR Mode    Screen = 160 sat  20190825 measured.
                # 'filter_screen_sort':  ['air', 'w', 'PL', 'gp', 'PB', 'rp', 'PG', 'PR', 'ip', 'O3', 'N2', 'CR', 'S2', 'HA'],  # 9, 21],  # 5, 17], #Most to least throughput, \
                # # so screen brightens, skipping u and zs which really need sky.

                # 'filter_sky_sort':     ['S2', 'HA', 'n2', 'up', 'CR', 'O3', 'z', 'ip', 'PR', 'rp', 'PG', 'PB', 'gp', 'PL', 'w', 'air'],

            },
        },


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
            'name': 'sq101sm',  #sq100sm Important because this points to a server file structure by that name.
            'desc':  'QHY 461 BSI Mono',

            'overscan_trim' : 'QHY461',
            #'driver':  "ASCOM.QHYCCD_CAM2.Camera", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control",
            'service_date': '20250218',  #'20240801',  #Replaced sq005mm which appears to have a circuit failure with prior QHY6oo.
            'switch_driver':  'ASCOM.Device1.Switch', #this is a temp hack, we should install the Powerbox as a first-class device.
            #the camera is on " Output 4", whatever that ends up meaning.  Hopefull = Switch4.

            'detector':  'Sony IMX461 BSI Mono',  # It would be good to build out a table of chip characteristics  6280 x 4210  Inspect: 62:4102, 4:6076  Sony 6244X4168 Active Optical black Hor 16, rear 0, Vert 22, rear 0
            'use_file_mode':  False,   # NB we should clean out all file mode stuff.
            'file_mode_path':  'D:/archive/sq0100sm/maxim/',  # NB NB all file_mode Maxim stuff should go!
            'manufacturer':  "QHY",
            'settings': {

                # These are the offsets in degrees of the actual telescope from the latitude and longitude of the WEMA settings
                'north_offset': 0.0,  # These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,


                # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.
                'hold_flats_in_memory': True,

                # Simple Camera Properties
                'is_cmos':  True,
                'is_osc': False,
                'is_color': False,
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
                #
                'direct_qhy_readout_mode': 1,  #These settings may be wrong. WER 20230712  We want high gain mode.

                'direct_qhy_gain': 60,       #as of 20250220 WER
                'direct_qhy_offset': 30,
                'set_qhy_usb_speed': True,
                'direct_qhy_usb_traffic' : 60,
                #'direct_qhy_usb_speed' : 60,      #NB used in saving the image header.



                # There are some infuriating popups on theskyx that manually
                # need to be dealt with when doing darks and lights.
                # This setting uses a workaround for that. This is just for CMOS
                # CCDs are fine.
                'cmos_on_theskyx': False,

                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.
                'interpolate_for_focus': True,
                # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'bin_for_focus': False,
                'focus_bin_value' : 1, #Chg 20250218
                'interpolate_for_sep': False,
                'bin_for_sep': False,  # This setting will bin the image for SEP photometry rather than interpolating.
                'sep_bin_value' : 1, #Chg 20250218
                # This setting will bin the image for platesolving rather than interpolating.
                'bin_for_platesolve': False,
                'platesolve_bin_value' : 1, #Chg 20250218

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
                'rotate180_fits': True,  # This also should be flipxy!
                'rotate90_fits': False,
                'rotate270_fits': False,
                'squash_on_x_axis': False,

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


                'dk_times':  [3.5, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 30.0, 90.0],    #unused right now.

                # This is the area for cooling related settings
                'cooler_on': True,     #Cooler is ambiguous nname
                'temp_setpoint': 2,    # Verify we can go colder
                'has_chiller': False,
                'chiller_com_port': 'COM1',
                'chiller_ref_temp':  25,  # C
                "temp_setpoint_tolerance": 2.5,   #  C


                # This is the yearly range of temperatures.
                # Based on New Mexico and Melbourne's variation... sorta similar.
                # There is a cold bit and a hot bit and an inbetween bit.
                # from the 15th of the month to the 15 of the month
                #
                # ( setpoint, day_warm_difference, day_warm troe our false)
                'set_temp_setpoint_by_season' : False,
                'temp_setpoint_nov_to_feb' : ( 2, 6, True),
                'temp_setpoint_feb_to_may' : ( 2, 8, True),
                'temp_setpoint_may_to_aug' : ( 2, 8, True),
                'temp_setpoint_aug_to_nov' : ( 2, 8, True),


                'day_warm': False,
                'day_warm_degrees': 0,  # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : False,


                # These are the physical values for the camera
                # related to pixelscale. Binning only applies to single
                # images. Stacks will always be drizzled to to drizzle value from 1x1.
                'x_pixel':  3.76,  #  pixel size in microns
                'y_pixel':  3.76,  #  pixel size in microns
                'manual_onebyone_pix_scale': 0.2639,  #  This is the 1x1 binning pixelscale    3.76*206255/1159000
                'native_bin': 1,   #  Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.


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
                'drizzle_value_for_later_stacking':  0.74,
                'dither_enabled':  True,      #Set this way for tracking testing


                # This is the absolute minimum and maximum exposure for the camera
                'min_exposure': 0.0000001,
                'max_exposure': 180.,
                # For certain shutters, short exposures aren't good for /VIGNETTE/ flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.
                'min_flat_exposure': 0.0000001,
                # Realistically there is maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'max_flat_exposure': 20.0,
                # During the daytime with the daytime safety mode on, exposures will be limited to this maximum exposure
                'max_daytime_exposure': 0.5,

                # One of the best cloud detections is to estimate the gain of the camera from the image
                # If the variation, and hence gain, is too high according to gain + stdev, the flat can be easily rejected.
                # Should be off for new observatories coming online until a real gain is known.
                'reject_new_flat_by_known_gain' : False,
                # These values are just the STARTING values. Once the software has been
                # through a few nights of calibration images, it should automatically calculate these gains.
                'specsheet_conversion_gain': 0.3,  # e-/adu
                'meas_camera_gain':   0.27225, #20250112 morning typical, consistent with specsheet.
                'camera_gain_stdev':   0.01, #Rough
                'specsheet_readnoise': 1.68, #Clearly at odds with "Used Readnoise report.
                'read_noise':  0.789,   #e-/ADUConv gain @ 62  THis value needs review
                'read_noise_stdev':   None, # Nothing reported
                'dark_lim_adu': 1,   #adu/s of dark 20231229 moved down from 0.5
                'dark_lim_std': 15,  #first guess. See above.
                # Saturate is the important one. Others are informational only.
                'fullwell_capacity': 20000,  #e-  Consistent with 0.3e-/adu
                'saturate':   64000,
                'max_linearity':  60000,   # Guess
                # How long does it take to readout an image after exposure?  Should this be inter-fastest substack time?
                'cycle_time':            2.0,
                # What is the base smartstack exposure time?
                # It will vary from scope to scope and computer to computer.
                # 30s is a good default.
                'smart_stack_exposure_time': 30,

                'smart_stack_exposure_NB_multiplier':  3,   #Michael's setting

                'substack': True, # Substack with this camera

                # As simple as it states, how many calibration frames to collect and how many to store.
                'number_of_bias_to_collect': 35,
                'number_of_dark_to_collect': 9,
                'number_of_flat_to_collect': 9,
                'number_of_bias_to_store': 33,
                'number_of_dark_to_store': 21,
                'number_of_flat_to_store': 21,
                # Default dark exposure time.
                'dark_exposure': 180,


                # In the EVA Pipeline, whether to run cosmic ray detection on individual images
                'do_cosmics': True,
                # Simialrly for Salt and Pepper
                'do_saltandpepper' : True,
                # And debanding
                'do_debanding' : False,

                # Does this camera have a darkslide, if so, what are the settings?
                'has_darkslide':  True,
                'darkslide_com':  'COM8',
                'shutter_type': "Iris",
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
        'sequencer': {
            'parent': 'site',
            'name': 'sequencer',
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

