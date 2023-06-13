
'''
FIRST Created on Fri Aug  2 11:57:41 2019

Refactored on 20230407

@author: wrosing, et al.
'''
import json

'''                                                                                                1         1         1       1
         1         2         3         4         5         6         7         8         9         0         1         2       2
12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678
'''

# NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.
degree_symbol = "°"
site_name = 'mrc'
obs_id = None  # NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_config = {

    'site': 'mrc',
    'site_id': 'mrc',
    'obs_id': None,  # a WEMA is not a telescope aka Observatory
    'observatory_location': site_name.lower(),  # in LCO case, an airport code such as OGG


    'debug_site_mode': False,

    'debug_mode': False,
    'admin_owner_commands_only': False,
    'debug_duration_sec': 3600,

    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne

    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],

    'client_hostname':  'MRC-0m35',  # This is also the long-name  Client is confusing!
    # NB NB disk D at mrc may be faster for temp storage
    'client_path':  'Q:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'Q:/ptr/',  # Generic place for this host to stash misc stuff
    'plog_path':  'Q:/ptr/mrc1/',  # place where night logs can be found.
    'save_to_alt_path': 'no',
    'archive_path':  'Q:/ptr/',

    'archive_age': -99.9,  # Number of days to keep files in the local archive before deletion. Negative means never delete
    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',

    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': True,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': True,  # To save space, the focus file can not be saved.


    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing': 1.0,

    'aux_archive_path':  None,  # NB NB we might want to put Q: here for MRC
    'wema_is_active':  True,          # True if the split computers used at a site.  NB CHANGE THE DAMN NAME!
    'wema_hostname': 'MRC-WMS-ENC',   # Prefer the shorter version
    'wema_path':  'Q:/ptr/',  # '/wema_transfer/',
    'dome_on_wema':   True,
    'site_IPC_mechanism':  'redis',   # ['None', shares', 'shelves', 'redis']  Pick One
    'wema_write_share_path': 'Q:/ptr/',  # Meant to be where Wema puts status data.
    'client_read_share_path':  'Q:/ptr/',  # NB these are all very confusing names.
    'client_write_share_path': 'Q:/ptr/',
    'redis_ip': '10.15.0.109',  # '127.0.0.1', None if no redis path present,
    'obsid_is_generic':  False,   # A simply  single computer ASCOM site.
    'obsid_is_specific':  False,  # Indicates some special code for this site, found at end of config.


    'host_wema_site_name':  'MRC',  # The umbrella header for obsys in close geographic proximity,
                                    #  under the control of one wema
    'name': 'Mountain Ranch Camp Observatory 0m35f7.2',
    'airport_code': 'SBA',
    'location': 'Near Santa Barbara CA,  USA',
    'telescope_description': '0m35 f7.2 Planewave CDK',
    'observatory_url': 'https://starz-r-us.sky/clearskies',
    'observatory_logo': None,
    'description':  '''
                    Now is the time for all good persons
                    to get out and vote early and often lest
                    we lose charge of our democracy.
                    ''',  # i.e, a multi-line text block supplied by the owner.  Must be careful about the contents for now.
    'location_day_allsky':  None,  # Thus ultimately should be a URL, probably a color camera.
    'location_night_allsky':  None,  # Thus ultimately should be a URL, usually Mono camera with filters.
    'location _pole_monitor': None,  # This probably gets us to some sort of image (Polaris in the North)
    'location_seeing_report': None,  # Probably a path to a jpeg or png graph.
    'debug_flag': True,  # Be careful about setting this flag True when pushing up to dev!
    'TZ_database_name': 'America/Los_Angeles',
    'mpc_code':  'ZZ23',  # This is made up for now.
    'time_offset': -8,     # NB these two should be derived from Python libs so change is automatic
    'timezone': 'PST',
    'latitude': 34.459375,  # Decimal degrees, North is Positive
    'longitude': -119.681172,  # Decimal degrees, West is negative
    'elevation': 317.75,    # meters above sea level
    'reference_ambient':  10.0,  # Degrees Celsius.  Alternately 12 entries, one for every - mid month.
    'reference_pressure':  977.83,  # mbar Alternately 12 entries, one for every - mid month.


    'obsid_roof_control': False,  # MTF entered this in to remove sro specific code  NB 'site_is_specifc' also deals with this
    'obsid_allowed_to_open_roof': False,
    'period_of_time_to_wait_for_roof_to_open': 50,  # seconds - needed to check if the roof ACTUALLY opens.
    'only_scope_that_controls_the_roof': False,  # If multiple scopes control the roof, set this to False
    'check_time': 300,  # MF's original setting.
    'maximum_roof_opens_per_evening': 4,
    # How many minutes to use as the default retry time to open roof. This will be progressively multiplied as a back-off function.
    'roof_open_safety_base_time': 15,


    'obsid_in_automatic_default': "Shutdown",  # "Manual", "Shutdown"
    'automatic_detail_default': "Enclosure is set to Shutdown mode.",

    # =============================================================================
    # At somepoint here some of this might better be associated with the Telescope not the site -- or
    # consider them to be site-wide rules.
    # =============================================================================

    'closest_distance_to_the_sun': 45,  # Degrees. For normal pointing requests don't go this close to the sun.

    'closest_distance_to_the_moon': 10,  # Degrees. For normal pointing requests don't go this close to the moon.

    'lowest_requestable_altitude': -5,  # Degrees. For normal pointing requests don't allow requests to go this low.

    'observing_check_period': 5,    # How many minutes between weather checks
    'enclosure_check_period': 5,    # How many minutes between enclosure checks

    'auto_eve_bias_dark': True,

    'auto_midnight_moonless_bias_dark': False,
    'auto_eve_sky_flat': False,

    'eve_sky_flat_sunset_offset': -60.,  # 40 before Minutes  neg means before, + after.

    'eve_cool_down_open': -65.0,
    'auto_morn_sky_flat': False,
    'auto_morn_bias_dark': False,
    're-calibrate_on_solve': True,
    'pointing_calibration_on_startup': False,  # MF I am leaving this alone.
    # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'periodic_focus_time': 0.5,
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_exposure_time': 10,  # Exposure time in seconds for exposure image
    'focus_trigger': 0.75,  # What FWHM increase is needed to trigger an autofocus
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 100,  # only update mount when X arcseconds away

    'defaults': {
        'observing_conditions': 'observing_conditions1',
        'enclosure': 'enclosure1',
        'mount': 'mount1',
        'telescope': 'telescope1',
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector':  None,
        'screen': 'screen1',
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
    },
    'device_types': [
        'observing_conditions',
        'enclosure',
        'mount',
        'telescope',
        # 'screen',
        'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',

        'sequencer',
    ],
    'wema_types': [
        'observing_conditions',
        'enclosure',
    ],
    'enc_types': [
        'enclosure'
    ],
    'short_status_devices':  [
        # 'observing_conditions',
        # 'enclosure',
        'mount',
        'telescope',
        # 'screen',
        'rotator',
        'focuser',
        'selector',
        'filter_wheel',
        'camera',

        'sequencer',
    ],
}

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
