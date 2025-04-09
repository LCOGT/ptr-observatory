#%%
import time
import json
from typing import Dict, Any, Callable
import requests
import os
import re
from datetime import datetime, timezone
from devices.sequencer_helpers import compute_target_coordinates
from ptr_utility import plog

def timestamp_to_LCO_datestring(t):
    """ Takes a Unix timestamp and converts to YYYY-mm-ddThh-mm-ss.sss in UTC """
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec='milliseconds').split('+')[0]

def get_now_lco():
    return timestamp_to_LCO_datestring(time.time())


def configdb_instrument_mapping_passes_validation(site_config) -> bool:
    """
    Validates that the configdb_instrument_mapping in the site config is properly configured.

    Args:
        site_config: The site configuration dictionary

    Returns:
        bool: True if the mapping is valid, False otherwise
    """
    if 'configdb_instrument_mapping' not in site_config:
        plog.warn('tried to validate the configdb mapping in the site config but it was missing.')
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
        plog.err('errors found while validating the configdb_instrument_mapping:')
        for p in problems:
            plog(p)
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
        plog.warn('Reverting to use default devices, which might make this observation a waste of time.')
        plog('This should be an easy fix: update the site config with a configdb_instrument_mapping with correct device names')
        return devices
    # Use default devices if the mapping is missing the configdb instrument specified in this observation
    elif instrument_name not in site_config['configdb_instrument_mapping']:
        plog.warn(f'configdb_instrument_mapping is missing instrument {instrument_name}, which we need for the current observation')
        plog('Reverting to use default devices, which might make this observation a waste of time.')
        plog('This should be an easy fix: add the configdb_instrument_mapping to the site config with correct devices specified')
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
    VALID_END_STATES = ['COMPLETED', 'FAILED', 'NOT_ATTEMPTED']

    def __init__(self):
        self.site_proxy_offline = False
        if 'SITE_PROXY_BASE_URL' not in os.environ:
            plog.warn('the environment variable SITE_PROXY_BASE_URL is missing and scheduler observations won\'t work.')
            plog('Please add this to the .env file and restart the observatory.')
            self.site_proxy_offline = True
        if 'SITE_PROXY_TOKEN' not in os.environ:
            plog.warn('the environment variable SITE_PROXY_TOKEN is missing, which means we can\'t communicate with the site proxy')
            plog('Please add this to the .env file and restart the observatory.')
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

    def update_configuration_status(self, config_status_id, state, summary=None):
        """
        Send an update to the site proxy about a configuration's status

        Args:
            config_status_id (int): found in configuration['configuration_status']
            state (str): one of PENDING, ATTEMPTED, NOT_ATTEMPTED, COMPLETED, FAILED
            summary (dict, optional): Additional information about the configuration execution, containing:
                start (str): ISO format timestamp of when execution started
                end (str): ISO format timestamp of when execution ended
                state (str): Final state of execution, e.g., 'COMPLETED'
                reason (str): Explanation for the state, especially useful for failures
                time_completed (str): Execution duration in seconds
                events (dict): Any events that occurred during execution

        Returns:
            Response object or None if site proxy is offline
        """
        if self.site_proxy_offline:
            plog("Cannot update configuration status; missing env variables needed to connect to the site proxy.")
            return None

        endpoint = f'{self.base_url}/observation-portal/api/configurationstatus/{config_status_id}'
        request_body = {
            "state": state,
        }
        if summary:
            request_body["summary"] = summary

        try:
            return self.session.patch(endpoint, data=json.dumps(request_body))
        except requests.exceptions.RequestException as e:
            plog.err(f"failed to update configuration status: {e}")
            return None

    def update_exposure_start_time(self, config_status_id, start_time):
        plog('Site proxy doesn\'t currently support updating exposures_start_time')
        return


    def update_configuration_start(self, config_status_id):
        """ Update the status of a configuration when observing is started."""
        plog('Updating configuration status to ATTEMPTED for ', config_status_id)
        response = self.update_configuration_status(config_status_id, 'ATTEMPTED')
        if response.status_code != 200:
            plog.warn(f'failed to update configuration status to ATTEMPTED for {config_status_id}.')
            plog(f'Reason: {response.text}')
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
            - end (str): when the configuration ended in UTC: YYYY-mm-ddThh:mm:ss.sss
            - time_completed (str): seconds of time observed during this configuration
            - reason (str): if the configuration failed, the reason why
            - events (json): optional, not sure what this is for

        Returns:
            dict: response from the site proxy request or None if request failed
        """
        plog(f'Updating configuration status to {state} for {config_status_id}')
        if state not in self.VALID_END_STATES:
            plog.err(f'invalid state given to update the configuration {config_status_id}.')
            plog(f'Received {state}, but must be one of {", ".join(self.VALID_END_STATES)}.')
        if not self._is_valid_timestamp([start, end]):
            plog.warn(f'not all timestamps in {[start, end]} are formatted correctly for configuration status update.')
        summary = {
            "state": state,
            "start": start,
            "end": end,
            "time_completed": time_completed,
            "reason": reason,
            "events": events
        }
        response = self.update_configuration_status(config_status_id, state, summary)
        if response is None:
            plog.err(f'failed to update configuration status to {state} for {config_status_id}.')
            plog(f'Reason: site proxy is offline')
        elif response.status_code != 200:
            plog.err(f'failed to update configuration status to {state} for {config_status_id}.')
            plog(f'Reason: {response.text}')
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

    """

    def __init__(self, observation: dict, observatory) -> None:
        self.observation = observation
        self.o = observatory

        self.submitter_id = observation['submitter']

        # Check against this to determine whether a slew will require a full
        # platesolve or not
        self.last_requested_target = dict()

        # Save the coordinates the mount believes it is pointing at (which may differ from the
        # actual pointing), so that we can make use of the faster async_slew_direct function
        self.last_solved_mount_ra = None
        self.last_solved_mount_dec = None

        self.siteproxy = SiteProxy()

        # This tracks how much time has been observed for each configuration
        # We use the configuration status id as the key because we need to
        # differentiate between the same config running multiple times from the
        # configuration_repeat setting.
        self.configuration_time_tracker = {}
        for c in observation['request']['configurations']:
            self.configuration_time_tracker[c['configuration_status']] = 0 # init with 0 seconds observed

    def stop_condition_reached(self, at_time: float = None) -> tuple:
        """ Check for stop conditions at various times during a project execution.

        Checks:
        - The observation is no longer currently scheduled
        - The observatory has closed
        - A stop command has been recieved.

        Args:
            at_time (float, opt): unix time. If specified, check if the observation is scheduled to stop by this time.

        Returns: tuple of (stop_now, reason)
            stop_now (bool): True if we should stop, else False
            reason (str): reason for stopping
        """
        if at_time is None:
            at_time = time.time()

        observation_id = self.observation['id']
        request_id = self.observation['request']['id']
        schedule_manager = self.o.devices['sequencer'].schedule_manager
        observation_currently_scheduled = schedule_manager.calendar_event_is_active(observation_id, at_time)
        request_currently_scheduled = schedule_manager.is_observation_request_scheduled(request_id, at_time)

        # Just make a note if the scheduler modified the original observation
        if not observation_currently_scheduled and request_currently_scheduled:
            plog('INFO: during an observation of an LCO request, the observation ID changed but the request ID did not.')
            plog('This just means the scheduler adjusted the current observation. No action needed.')

        # Observatory status
        scope_in_manual_mode = self.o.scope_in_manual_mode # not used, but here as a reminder that it's an option
        shutter_closed = 'Closed' in self.o.enc_status['shutter_status']
        observatory_closed = not self.o.open_and_enabled_to_observe
        stop_all_activity_flag = self.o.stop_all_activity

        if not request_currently_scheduled:
            return True, 'The observation request is not scheduled at the provided time'

        if shutter_closed or observatory_closed:
            return True, 'The observatory is no longer open and able to observe'

        if stop_all_activity_flag:
            return True, 'Received a stop_all_activity command'

        return False, 'Ok to continue observing'


    def _go_to_target(self, mount_device, target: dict, offset_ra: float = 0, offset_dec: float = 0) -> None:
        """
        Slew to the target coordinates, applying any offsets

        Args:
            mount_device: The mount device to use for slewing
            target: Dictionary containing target coordinates and other info
            offset_ra: Offset in right ascension (arcseconds)
            offset_dec: Offset in declination (arcseconds)
        """
        if target['type'] != "ICRS":
            plog(f'Unsupported target type: {target["type"]}')
            return

        # convert from arcsec to hours
        offset_ra = offset_ra / 54000
        # convert from arcsec to degrees
        offset_dec = offset_dec / 3600

        plog('In go_to_target function during LCO observation run')
        plog(target)
        # update the pointing to account for proper motion and parallax
        proper_motion_parallax_adjusted_coords = compute_target_coordinates(target)
        ra = proper_motion_parallax_adjusted_coords['ra'] # units: hours
        dec = proper_motion_parallax_adjusted_coords['dec'] # units: degrees
        plog(f"central ra: {ra}")
        plog(f"central dec: {dec}")

        # Large mount movements should be centered using a platesolve routine.
        # Do this whenever the target has changed from the previous pointing.
        if self.last_requested_target != target:
            mount_device.go_command(ra=ra, dec=dec, objectname=target.get('name'), do_centering_routine=True, ignore_moon_dist=True)
            self.last_requested_target = target
            # Save the mount coordinates (which are slightly different than the actual coordinates)
            # for current/future offsets from the same central pointing
            self.last_solved_mount_ra = mount_device.right_ascension_directly_from_mount
            self.last_solved_mount_dec = mount_device.declination_directly_from_mount
            plog(f"Pointing is now at ra,dec of {ra}, {dec} according to platesolve.")
            plog(f"Mount has registered this as {self.last_solved_mount_ra}, {self.last_solved_mount_dec}")

        # If we're already close to our requested pointing, we can use a faster
        # slewing method that isn't reliable for large movements, but works well
        # for small adjustments
        #
        # The slew_async_directly method uses the mount coordinates rather than
        # the actual coordinats, which is why we saved the mount ra/dec after
        # the plate solve (above).
        mount_ra_with_offset = self.last_solved_mount_ra + offset_ra
        mount_dec_with_offset = self.last_solved_mount_dec + offset_dec
        mount_device.slew_async_directly(ra=mount_ra_with_offset, dec=mount_dec_with_offset)


    # Note: Defocus functionality not implemented, kept for API compatibility
    def _do_defocus(self, focuser_device, amount: float) -> None:
        """
        Placeholder for defocus functionality (not implemented)
        """
        plog(f'simulating defocus of {amount}')
        return

    # TODO: add target name to optional_params.object_name
    def _take_exposure(self, camera_device, filterwheel_device, time: float, filter_name: str, target_name: str,
                      smartstack: bool = True, substack: bool = True) -> dict:
        """
        Take an exposure with the specified parameters

        Args:
            camera_device: The camera device to use
            filterwheel_device: The filter wheel device to use
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
            'count': 1,
            'object_name': target_name
        }
        plog(f'Exposing image with filter {filter_name} for {time}s')
        return camera_device.expose_command(
            required_params,
            optional_params,
            user_id=self.submitter_id,
            user_name=self.submitter_id,
            skip_open_check=True,
            skip_daytime_check=True,
            filterwheel_device=filterwheel_device
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
                plog(f"Configuration missing required key: {key}")
                return False

        # Validate the configuration type
        if config['type'] not in ['EXPOSE', 'REPEAT_EXPOSE']:
            plog(f"Unsupported configuration type: {config['type']}")
            return False

        # Validate instrument configs
        if not config['instrument_configs'] or not isinstance(config['instrument_configs'], list):
            plog("Configuration must have at least one instrument_config")
            return False

        return True

    def _report_configuration_completion(self, configuration: dict, start_time: float) -> None:
        """
        Report the completion of a configuration to the site proxy

        Args:
            configuration: The completed configuration
            start_time: When the configuration started (timestamp)
        """
        config_status_id = configuration['configuration_status']
        start = timestamp_to_LCO_datestring(start_time)
        end = timestamp_to_LCO_datestring(time.time())
        state = "COMPLETED"
        time_completed = self.configuration_time_tracker[config_status_id]
        self.siteproxy.update_configuration_end(config_status_id, state, start, end, time_completed)

        # Calculate and display completion statistics
        total_requested_time = sum([ic['exposure_count'] * ic['exposure_time']
                                   for ic in configuration['instrument_configs']])
        completed_percent = round(100 * time_completed / total_requested_time, 1)
        plog(f'Configuration complete. Observed {time_completed}s of {total_requested_time}s, or {completed_percent}%')


    def _do_instrument_config(self, ic, config, devices, exposure_sequence_done: Callable[[], bool]) -> tuple:
        """
        Run a single instrument configuration.

        Args:
            ic (dict): instrument configuration to run
            config (dict): the configuration that contains the instrument configuration
            devices (dict): get the observatory device by key (mount, focuser, camera, filter_wheel)
            exposure_sequence_done (func): returns true if we're running in an EXPOSE_SEQUENCE configuration type, and
                                            the time as expired. Used to break out of an in-progress instrument config.

        Returns: tuple of (time_observed, reason)
            time_observed (str): total successful exposure time, in seconds
            reason (str): description why the instrument config is stopping
        """

        time_observed = 0

        try:
            mount = devices['mount']
            focuser = devices['focuser']
            camera = devices['camera']
            filter_wheel = devices['filter_wheel']

            # Ignore defocus for now, since focus routine is tied to camera expose command and I need to untangle them first.
            defocus = ic['extra_params'].get('defocus', False)
            if defocus:
                plog(f'Defocus was requested with value {defocus}, but this has not been implemented yet.')
                # do_defocus(focuser, defocus)

            offset_ra = ic['extra_params'].get('offset_ra', 0)
            offset_dec = ic['extra_params'].get('offset_dec', 0)
            target_name = config['target'].get('name', 'Unknown Target')
            self._go_to_target(mount, config['target'], offset_ra, offset_dec)

            stop, reason = self.stop_condition_reached()
            if stop:
                return time_observed, reason

            exposure_time = ic['exposure_time']
            exposure_count = ic['exposure_count']
            smartstack = config.get('smartstack', True)
            substack = config.get('substack', True)
            filter_name = ic['optical_elements']['filter'].strip('ptr-')
            for _ in range(exposure_count):
                # Check if the EXPOSE_SEQUENCE configuration is out of time, and we should stop now.
                if exposure_sequence_done():
                    return time_observed, 'SEQUENCE_END'

                # Check for other stop signals
                stop, reason = self.stop_condition_reached()
                if stop:
                    return time_observed, reason

                expose_result = self._take_exposure(camera, filter_wheel, exposure_time, filter_name, target_name, smartstack=smartstack, substack=substack)
                plog('expose result: ', expose_result)

                # Update the time observed for this configuration
                if isinstance(expose_result, dict) and 'error' in expose_result and not expose_result['error']:
                    time_observed += exposure_time
                    self.configuration_time_tracker[config['configuration_status']] += exposure_time
                else:
                    plog('Error in exposure result. Response was ', expose_result)


            plog(f'Finished instrument configuration. Exposed {time_observed} of {exposure_count * exposure_time} seconds')
            return time_observed, 'SUCCESS'

        except Exception as e:
            plog.warn(f'Unexpected failure while observing an instrument configuration: {e}')
            return time_observed, 'FAIL'


    def _do_configuration(self, configuration: dict, devices: dict) -> dict:
        """
        Execute a single configuration

        Args:
            configuration: The configuration to execute
            devices: Dictionary of devices to use

        Returns (dict): This is essentially the "summary" used to report configuration status
            start (str): time the configuration started in UTC "%Y-%m-%dT%H:%M:%S"
            end (str): time the configuration ended in UTC "%Y-%m-%dT%H:%M:%S"
            reason (str): why the configuration ended as not completed (if applicable), or emtpy
            state (str): the end state of this configuration--one of NOT_ATTEMPTED, COMPLETED, FAILED
            time_completed (float): amount of time successfully observed, in seconds
            events (dict): events dict


        """

        # Start the configuration
        configuration_start_time = time.time()
        config_status_id = configuration['configuration_status']
        self.siteproxy.update_configuration_start(config_status_id)

        # Helper function for generating our return value
        def create_summary(state: str, time_completed: int = 0, reason: str = '', events: dict = {}):
            return {
                'start': timestamp_to_LCO_datestring(configuration_start_time),
                'end': timestamp_to_LCO_datestring(time.time()),
                'state': state,
                'time_completed': time_completed,
                'reason': reason,
                'events': events,
            }

        # Create a helper function for identifying the end of an exposure sequence window
        config_type = configuration['type']
        repeat_duration = configuration.get('repeat_duration') or 0 # fallback to keep number type
        repeat_expose_end_time = configuration_start_time + repeat_duration
        def exposure_sequence_done():
            ''' Return True if configuration type is an exposure sequence and the duration has been exceeded'''
            return config_type == 'REPEAT_EXPOSE' and time.time() > repeat_expose_end_time

        # Run the configuration
        try:
            self._go_to_target(devices['mount'], configuration['target'])

            # Check for stop conditions
            stop, reason = self.stop_condition_reached()
            if stop:
                return create_summary('NOT_ATTEMPTED', reason=reason)

            # Update the time when we start taking exposures (not implemented yet)
            exposure_start_time = time.time()
            self.siteproxy.update_exposure_start_time(config_status_id, timestamp_to_LCO_datestring(exposure_start_time))

            if config_type == "EXPOSE":
                configuration_total_time_observed =  0
                for index, ic in enumerate(configuration['instrument_configs']):

                    # Check for stop conditions
                    stop, reason = self.stop_condition_reached()
                    if stop:
                        return create_summary('COMPLETED', configuration_total_time_observed, reason)

                    plog(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                    time_observed, reason = self._do_instrument_config(ic, configuration, devices, exposure_sequence_done)
                    configuration_total_time_observed += time_observed
                # Upon completion, return summary
                return create_summary('COMPLETED', configuration_total_time_observed)

            if config_type == "REPEAT_EXPOSE":
                configuration_total_time_observed = 0
                while not exposure_sequence_done():
                    for index, ic in enumerate(configuration['instrument_configs']):
                        plog(f'starting instrument config #{index + 1} of {len(configuration["instrument_configs"])}')
                        plog(f'type == REPEAT_EXPOSE, so we will continue looping over all instrument configs.')
                        plog(f'remaining time for REPEAT_EXPOSE is {repeat_expose_end_time - time.time()} seconds')
                        time_observed, reason = self._do_instrument_config(ic, configuration, devices, exposure_sequence_done)
                        configuration_total_time_observed += time_observed
                return create_summary('COMPLETED', configuration_total_time_observed)

            # If unknown config type: report status and return
            reason = f"Unsupported configuration type {config_type} for PTR. Skipping this configuration."
            plog(reason)
            return create_summary('NOT_ATTEMPTED', 0, reason)
        except Exception as e:
            plog.err(f'Configuration failed unexpectedly: {e}')
            return create_summary('FAILED', reason=f"Unexpected error: {e}")


    def run(self):
        """ Run the full observation """
        plog('Starting the following observation from LCO:')
        plog(json.dumps(self.observation, indent=2))
        request = self.observation['request']

        for index, configuration in enumerate(request['configurations']):
            plog(f'starting config #{index + 1} of {len(request["configurations"])}')
            if self._is_valid_config(configuration):
                devices = get_devices_for_configuration(configuration, self.o)
                summary = self._do_configuration(configuration, devices)
                self.siteproxy.update_configuration_status(configuration['configuration_status'], summary['state'], summary)
            else:
                # Set a NOT_ATTEMPTED state for this configuration
                config_status_id = configuration['configuration_status']
                now = timestamp_to_LCO_datestring(time.time())
                reason = 'Configuration validation failed'
                summary = {
                    "start": now,
                    "end": now,
                    "state": "NOT_ATTEMPTED",
                    "reason": reason,
                    "time_completed": 0,
                    "events": {}
                }
                plog(f'setting configuration {config_status_id} to NOT_ATTEMPTED: {reason}')
                self.siteproxy.update_configuration_status(config_status_id, 'NOT_ATTEMPTED', summary)
        plog(f'OBSERVATION COMPLETE\n\n')

# %%
