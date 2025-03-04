#%%
import time
import json
from typing import Dict, Any, Callable
import requests
import os
import re
from datetime import datetime, timezone
from devices.sequencer_helpers import compute_target_coordinates

def timestamp_to_LCO_datestring(t):
    """ Takes a Unix timestamp and converts to YYYY-mm-ddThh-mm-ss.sss in UTC """
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec='milliseconds').split('+')[0]


def configdb_instrument_mapping_passes_validation(site_config) -> bool:
    """
    Validates that the configdb_instrument_mapping in the site config is properly configured.

    Args:
        site_config: The site configuration dictionary

    Returns:
        bool: True if the mapping is valid, False otherwise
    """
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
    """
    Return a dict with the device of each type to use in an observation request's configuration

    Args:
        configuration: The configuration dictionary from the observation request
        observatory: The observatory object

    Returns:
        dict: A dictionary mapping device types to device objects
    """
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
        print(f'WARNING: configdb_instrument_mapping is missing instrument {instrument_name}, which we need for the current observation')
        print('Reverting to use default devices, which might make this observation a waste of time.')
        print('This should be an easy fix: add the configdb_instrument_mapping to the site config with correct devices specified')
        return devices
    # If no errors, then use the mapping to get our devices
    else:
        configdb_mapping = site_config['configdb_instrument_mapping'][instrument_name]
        devices['camera'] = o.device_by_name[configdb_mapping['camera']]
        devices['mount'] = o.device_by_name[configdb_mapping['mount']]
        devices['filter_wheel'] = o.device_by_name[configdb_mapping['filter_wheel']]
        devices['focuser'] = o.device_by_name[configdb_mapping['focuser']]
    return devices

class SiteProxy:
    """
    A class to handle communication with the site proxy service.
    Manages configuration status updates for scheduled observations.
    """
    VALID_STATES = ['COMPLETED', 'FAILED', 'NOT_ATTEMPTED']

    def __init__(self):
        self.site_proxy_offline = False
        if 'SITE_PROXY_BASE_URL' not in os.environ:
            print('WARNING: the environment variable SITE_PROXY_BASE_URL is missing and scheduler observations won\'t work.')
            print('Please add this to the .env file and restart the observatory.')
            self.site_proxy_offline = True
        if 'SITE_PROXY_TOKEN' not in os.environ:
            print('WARNING: the environment variable SITE_PROXY_TOKEN is missing, which means we can\'t communicate with the site proxy')
            print('Please add this to the .env file and restart the observatory.')
            self.site_proxy_offline = True

        self.base_url = os.getenv('SITE_PROXY_BASE_URL')
        self.session = requests.Session()
        self.session.headers.update({'Authorization': os.getenv('SITE_PROXY_TOKEN')})

    def _is_valid_timestamp(self, s):
        """
        Ensure that dates are formatted to match YYYY-mm-ddThh:mm:ss.sss
        Works with a single string input or an array of date strings

        Returns:
            bool: True if all timestamps are valid, False otherwise
        """
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$"
        if isinstance(s, list):
            return all(re.match(pattern, ts) for ts in s)
        return bool(re.match(pattern, s))

    def _update_configuration_status(self, config_status_id, state, summary=None):
        """
        Send an update to the site proxy about a configuration's status

        Returns:
            Response object or None if site proxy is offline
        """
        if self.site_proxy_offline:
            print("Cannot update configuration status; missing env variables needed to connect to the site proxy.")
            return None

        endpoint = f'{self.base_url}/observation-portal/api/configurationstatus/{config_status_id}'
        request_body = {
            "state": state,
        }
        if summary:
            request_body["summary"] = summary

        try:
            return self.session.patch(endpoint, request_body)
        except requests.exceptions.RequestException as e:
            print(f"Error updating configuration status: {e}")
            return None

    def update_configuration_start(self, config_status_id):
        """ Update the status of a configuration when observing is started."""
        print('Updating configuration status to ATTEMPTED for ', config_status_id)
        response = self._update_configuration_status(config_status_id, 'ATTEMPTED')
        if response.status_code != 200:
            print(f'WARNING: failed to update configuration status to ATTEMPTED for {config_status_id}.')
            print(f'Reason: {response.text}')
        return response

    def update_configuration_end(self, config_status_id, state, start, end, time_completed, reason="", events={}):
        """
        Update the status of a configuration when observing is finished.

        Args:
            - config_status_id (str): the id for the configuration_status we are updating.
                This is found in the configuration under 'configuration_status'.
                Note: this is different from the configuration id!
            - state (str): either COMPLETED, FAILED, or (rarely) NOT_ATTEMPTED
            - start (str): when the configuration started in UTC: YYYY-mm-ddThh:mm:ss.sss
            - end (str): when the configuration started in UTC: YYYY-mm-ddThh:mm:ss.sss
            - time_completed (str): seconds of time observed during this configuration
            - reason (str): if the configuration failed, the reason why
            - events (json): optional, not sure what this is for

        Returns:
            dict: response from the site proxy request or None if request failed
        """
        print(f'Updating configuration status to {state} for {config_status_id}')
        if state not in self.VALID_STATES:
            print(f'WARNING: invalid state given to update the configuration {config_status_id}.')
            print(f'Received {state}, but must be one of {", ".join(self.VALID_STATES)}.')
        if not self._is_valid_timestamp([start, end]):
            print(f'WARNING: not all timestamps in {[start, end]} are formatted correctly for configuration status update.')
        summary = {
            "state": state,
            "start": start,
            "end": end,
            "time_completed": time_completed,
            "reason": reason,
            "events": events
        }
        response = self._update_configuration_status(config_status_id, state, summary)
        if response.status_code != 200:
            print(f'WARNING: failed to update configuration status to {state} for {config_status_id}.')
            print(f'Reason: {response.text}')
        return response

class SchedulerObservation:
    """
    Handles execution of scheduled observations from the LCO system.

    Assumptions:
    - "type" is "EXPOSE" or "REPEAT_EXPOSE"
    - "guiding_config" is ignored in favor of smartstacks/substacks
    - "acquisition_config" is ignored
    - "rotator_mode" and "rotator_angle" are ignored (unsupported)
    - "defocus" is ignored since implementing is tricky with focus being controlled by camera

    Need to test:
    - observation stops when the scheduled time has finished
    - manual commands don't interfere

    Manually verify:
    - pointing is decent
    - stays focused
    """

    def __init__(self, observation: dict, observatory) -> None:
        self.observation = observation
        self.o = observatory

        self.submitter_id = observation['submitter']

        # This tracks how much time has been observed for each configuration
        # We use the configuration status id as the key because we need to
        # differentiate between the same config running multiple times from the
        # configuration_repeat setting.
        self.configuration_time_tracker = {}
        for c in observation['request']['configurations']:
            self.configuration_time_tracker[c['configuration_status']] = 0 # init with 0 seconds observed


    def _go_to_target(self, mount_device, target: dict, offset_ra: float = 0, offset_dec: float = 0) -> None:
        """
        Slew to the target coordinates, applying any offsets

        Args:
            mount_device: The mount device to use for slewing
            target: Dictionary containing target coordinates and other info
            offset_ra: Offset in right ascension (hours)
            offset_dec: Offset in declination (degrees)
        """
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

    # Note: Defocus functionality not implemented, kept for API compatibility
    def _do_defocus(self, focuser_device, amount: float) -> None:
        """
        Placeholder for defocus functionality (not implemented)
        """
        print(f'simulating defocus of {amount}')
        return

    def _take_exposure(self, camera_device, filter_wheel_device, time: float, filter_name: str,
                      smartstack: bool = True, substack: bool = True) -> dict:
        """
        Take an exposure with the specified parameters

        Args:
            camera_device: The camera device to use
            filter_wheel_device: The filter wheel device to use
            time: Exposure time in seconds
            filter_name: Name of the filter to use
            smartstack: Whether to use smartstack
            substack: Whether to use substack

        Returns:
            dict: Result of the expose command
        """
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
        return camera_device.expose_command(
            required_params,
            optional_params,
            user_id=self.submitter_id,
            user_name=self.submitter_id,
            skip_open_check=True,
            skip_daytime_check=True,
        )

    def _is_valid_config(self, config: dict) -> bool:
        """
        Validate that a configuration is properly formed and can be executed

        Args:
            config: The configuration to validate

        Returns:
            bool: True if the configuration is valid, False otherwise
        """
        # Basic validation checks
        required_keys = ['type', 'target', 'instrument_configs', 'configuration_status']
        for key in required_keys:
            if key not in config:
                print(f"Configuration missing required key: {key}")
                return False

        # Validate the configuration type
        if config['type'] not in ['EXPOSE', 'REPEAT_EXPOSE']:
            print(f"Unsupported configuration type: {config['type']}")
            return False

        # Validate instrument configs
        if not config['instrument_configs'] or not isinstance(config['instrument_configs'], list):
            print("Configuration must have at least one instrument_config")
            return False

        # Other validation checks could be added here

        return True

    def _do_configuration(self, configuration: dict, devices: dict, siteproxy: SiteProxy) -> None:
        """
        Execute a single configuration

        Args:
            configuration: The configuration to execute
            devices: Dictionary of devices to use
            siteproxy: The site proxy for status updates
        """
        configuration_start_time = time.time()
        config_status_id = configuration['configuration_status']
        siteproxy.update_configuration_start(config_status_id)

        config_type = configuration['type']
        repeat_duration = configuration.get('repeat_duration') or 0 # fallback to keep number type
        end_time = configuration_start_time + repeat_duration
        def exposure_sequence_done():
            ''' Return True if configuration type is an exposure sequence and the duration has been exceeded'''
            return config_type == 'REPEAT_EXPOSE' and time.time() > end_time

        self._go_to_target(devices['mount'], configuration['target'])

        if config_type == "EXPOSE":
            for index, ic in enumerate(configuration['instrument_configs']):
                print(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                self._do_instrument_config(ic, configuration, devices, exposure_sequence_done)

            # After configuration is done: report config status and return
            self._report_configuration_completion(configuration, configuration_start_time, siteproxy)
            return

        if config_type == "REPEAT_EXPOSE":
            while not exposure_sequence_done():
                for index, ic in enumerate(configuration['instrument_configs']):
                    print(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                    print(f'type == REPEAT_EXPOSE, so we will continue looping over all instrument configs.')
                    print(f'remaining time for REPEAT_EXPOSE is {end_time - time.time()} seconds')
                    self._do_instrument_config(ic, configuration, devices, exposure_sequence_done)

            self._report_configuration_completion(configuration, configuration_start_time, siteproxy)
            return

        # If unknown config type: report status and return
        print(f"Unsupported configuration type {config_type}. Skipping this configuration.")
        start = timestamp_to_LCO_datestring(configuration_start_time)
        end = timestamp_to_LCO_datestring(time.time())
        state = 'NOT_ATTEMPTED'
        time_completed = 0
        reason = f'Unsupported configuration type {config_type}'
        siteproxy.update_configuration_end(config_status_id, state, start, end, time_completed, reason)
        return

    def _report_configuration_completion(self, configuration: dict, start_time: float, siteproxy: SiteProxy) -> None:
        """
        Report the completion of a configuration to the site proxy

        Args:
            configuration: The completed configuration
            start_time: When the configuration started (timestamp)
            siteproxy: The site proxy for status updates
        """
        config_status_id = configuration['configuration_status']
        start = timestamp_to_LCO_datestring(start_time)
        end = timestamp_to_LCO_datestring(time.time())
        state = "COMPLETED"
        time_completed = self.configuration_time_tracker[config_status_id]
        siteproxy.update_configuration_end(config_status_id, state, start, end, time_completed)

        # Calculate and display completion statistics
        total_requested_time = sum([ic['exposure_count'] * ic['exposure_time']
                                   for ic in configuration['instrument_configs']])
        completed_percent = round(100 * time_completed / total_requested_time, 1)
        print(f'Configuration complete. Observed {time_completed}s of {total_requested_time}s, or {completed_percent}%')


    def _do_instrument_config(self, ic, config, devices, exposure_sequence_done: Callable[[], bool]) -> None:
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
        self._go_to_target(mount, config['target'], offset_ra, offset_dec)

        exposure_time = ic['exposure_time']
        exposure_count = ic['exposure_count']
        smartstack = config.get('smartstack', True)
        substack = config.get('substack', True)
        filter_name = ic['optical_elements']['filter'].strip('ptr-')
        for _ in range(exposure_count):
            if exposure_sequence_done():
                break
            expose_result = self._take_exposure(camera, filter_wheel, exposure_time, filter_name, smartstack=smartstack, substack=substack)
            print('expose result: ', expose_result)

            # Update the time observed for this configuration
            if isinstance(expose_result, dict) and 'error' in expose_result and not expose_result['error']:
                self.configuration_time_tracker[config['configuration_status']] += exposure_time
            else:
                print('Error in exposure result. Response was ', expose_result)


    def run(self):
        """ Run the full observation """
        print('Starting the following observation from LCO:')
        print(json.dumps(self.observation, indent=2))
        request = self.observation['request']
        siteproxy = SiteProxy()

        for index, configuration in enumerate(request['configurations']):
            print(f'starting config #{index + 1} of {len(request["configurations"])}')
            if self._is_valid_config(configuration):
                devices = get_devices_for_configuration(configuration, self.o)
                self._do_configuration(configuration, devices, siteproxy)
            else:
                print('Config failed validation. Skipping.')
        print(f'OBSERVATION COMPLETE\n\n')
