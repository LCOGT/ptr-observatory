#%%
import time
import json
from typing import Dict, Any, Callable
import logging
from devices.sequencer_helpers import compute_target_coordinates

def configdb_instrument_mapping_passes_validation(site_config) -> bool:
    if 'configdb_instrument_mapping' not in site_config:
        print('WARNING: tried to validate the configdb mapping in the site config but it was missing.')
        return False

    required_devices = [
        'mount',
        'camera',
        'filter_wheel',
        'focuser'
    ]
    problems = []

    configdb_mappings = site_config['configdb_instrument_mapping']

    # iterate through each configdb instrument -> PTR devices mapping. Usually just one per site.
    for instrument, device_maps in configdb_mappings.items():
        # Check that all required devices are specified
        for device_type in required_devices:
            if device_type in device_maps:
                # Check that the specific instrument exists
                device_name = device_maps[device_type]
                if device_name not in site_config[device_type]:
                    problems.append(f'Device name {device_name} is not defined in the list of {device_type}')
            else:
                problems.append(f'Instrument {instrument} is missing a mapping for device type: {device_type}')

    if len(problems) > 0:
        print('WARNING: errors found while validating the configdb_instrument_mapping:')
        for p in problems:
            print(p)
        return False
    else:
        return True


def get_devices_for_configuration(configuration: dict, observatory) -> dict:
    """ Return a dict with the device of each type to use in an observation request's configuration """
    o = observatory # less typing
    site_config = o.config
    instrument_type = configuration['instrument_type']
    instrument_name = configuration['instrument_name']

    configdb_mapping = observatory.config.get('configdb_instrument_mapping')

    # Use default devices as our fallback
    devices = {
        'camera': o.devices['main_cam'],
        'mount': o.devices['mount'],
        'filter_wheel': o.devices['main_fw'],
        'focuser': o.devices['main_focuser']
    }

    # Use default devices if the mapping fails validation
    if not configdb_instrument_mapping_passes_validation(site_config):
        print('Reverting to use default devices, which might make this observation a waste of time.')
        print('This should be an easy fix: update the site config with a configdb_instrument_mapping with correct device names')
        return devices
    # Use default devices if the mapping is missing the configdb instrument specified in this observation
    elif instrument_name not in site_config['configdb_instrument_mapping']:
        print('WARNING: configdb_instrument_mapping is missing instrument {instrument_name}, which we need for the current observation')
        print('Reverting to use default devices, which might make this observation a waste of time.')
        print('This should be an easy fix: add the configdb_instrument_mapping to the site config with correct devices specified')
        return devices
    # If no errors, then use the mapping to get our devices
    else:
        configdb_mapping = site_config['configdb_instrument_mapping'][instrument_name]
        devices['camera'] = o.device_by_name[configdb_mapping['camera']]
        devices['mount'] = o.device_by_name[configdb_mapping['mount']]
        devices['filterwheel'] = o.device_by_name[configdb_mapping['filter_wheel']]
        devices['focuser'] = o.device_by_name[configdb_mapping['focuser']]
    return devices


def execute_project_from_lco1(observation, observatory):
    """ Strategy:

    # Unknowns:
    # When to center?
    # When to autofocus?

    # Assumptions:
    # "type" is "EXPOSE" or "REPEAT_EXPOSE"
    # "guiding_config" is ignored in favor of smartstacks/substacks
    # "acquisition_config" is ignored
    # "rotator_mode" and "rotator_angle" are ignored (unsupported)
    # "defocus" is ignored since implementing is tricky with focus being controlled by camera

    Need to test:
    - observation stops when the scheduled time has finished
    - manual commands don't interfere

    Manually verify:
    - pointing is decent
    - stays focused


    """
    mount = observatory.devices['mount']
    camera = observatory.devices['main_cam']
    focuser = observatory.devices['main_focuser']
    filterwheel = observatory.devices['main_fw']

    submitter_id = observation['submitter']

    def go_to_target(mount_device, target, offset_ra=0, offset_dec=0):
        if target['type'] != "ICRS":
            print(f'Unsupported target type: {target["type"]}')
            return

        print('In go_to_target function during LCO observation run')
        print(target)
        # update the pointing to account for proper motion and parallax
        proper_motion_parallax_adjusted_coords = compute_target_coordinates(target)
        # add ra/dec offsets
        corrected_ra = proper_motion_parallax_adjusted_coords['ra'] + offset_ra
        corrected_dec = proper_motion_parallax_adjusted_coords['dec'] + offset_dec

        print(f'Slewing to ra {corrected_ra}, dec {corrected_dec}')
        mount_device.go_command(ra=corrected_ra, dec=corrected_dec, objectname=target.get('name'))

    def do_defocus(focuser_device, amount):
        print(f'simulating defocus of {amount}')
        return

    def take_exposure(camera_device, filter_wheel_device, time, filter_name, smartstack=True, substack=True):
        required_params = {
            'time': time,
            'image_type': 'light',
            'smartstack': smartstack,
            'substack': substack,
        }
        optional_params = {
            'filter': filter_name,
            'count': 1
        }
        print(f'Exposing image with filter {filter_name} for {time}s')
        camera_device.expose_command(
            required_params,
            optional_params,
            user_id=submitter_id,
            user_name=submitter_id,
            skip_open_check=True,
            skip_daytime_check=True,
        )
        return

    def is_valid_config(config):
        # validate configuration
        print('simulating config validation (return True)')
        return True

    def do_configuration(configuration, devices):
        go_to_target(devices['mount'], configuration['target'])

        config_type = configuration['type']

        repeat_duration = configuration.get('repeat_duration') or 0 # fallback to keep number type
        end_time = time.time() + repeat_duration
        def exposure_sequence_done():
            ''' Return True if configuration type is an exposure sequence and the duration has been exceeded'''
            return config_type == 'REPEAT_EXPOSE' and time.time() > end_time

        if config_type == "EXPOSE":
            for index, ic in enumerate(configuration['instrument_configs']):
                print(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                do_instrument_config(ic, configuration, devices, exposure_sequence_done)
        elif config_type == "REPEAT_EXPOSE":
            while not exposure_sequence_done():
                for index, ic in enumerate(configuration['instrument_configs']):
                    print(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                    do_instrument_config(ic, configuration, devices, exposure_sequence_done)
        else:
            print(f"Unknown config type {config_type}. Skipping this config.")


    def do_instrument_config(ic, config, devices, exposure_sequence_done: Callable[[], bool]) -> None:
        mount = devices['mount']
        focuser = devices['focuser']
        camera = devices['camera']
        filter_wheel = devices['filter_wheel']

        # Ignore defocus for now, since focus routine is tied to camera expose command and I need to untangle them first.
        defocus = ic['extra_params'].get('defocus', False)
        if defocus:
            print(f'Defocus was requested with value {defocus}, but this has not been implemented yet.')
            # do_defocus(focuser, defocus)

        offset_ra = ic['extra_params'].get('offset_ra', 0)
        offset_dec = ic['extra_params'].get('offset_dec', 0)
        go_to_target(mount, config['target'], offset_ra, offset_dec)

        exposure_time = ic['exposure_time']
        exposure_count = ic['exposure_count']
        smartstack = config.get('smartstack', True)
        substack = config.get('substack', True)
        filter_name = ic['optical_elements']['filter'].strip('ptr-')
        for _ in range(exposure_count):
            if exposure_sequence_done():
                break
            take_exposure(camera, filter_wheel, exposure_time, filter_name, smartstack=smartstack, substack=substack)


    def do_observation(observation, observatory):
        print('Starting the following observation from LCO:')
        print(json.dumps(observation, indent=2))
        request = observation['request']

        configuration_repeats = request['configuration_repeats']
        for cr in range(configuration_repeats):
            print(f'Doing configuration repeat #{cr + 1} of {configuration_repeats}')
            for index, configuration in enumerate(request['configurations']):
                print(f'starting config #{index + 1} of {len(request["configurations"])}')
                if is_valid_config(configuration):
                    devices = get_devices_for_configuration(configuration, observatory)
                    do_configuration(configuration, devices)
                else:
                    print('Config failed validation. Skipping.')

        print(f'OBSERVATION COMPLETE\n\n')

    do_observation(observation, observatory)

