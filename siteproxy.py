
import os
import requests
import json
import re
from ptr_utility import plog


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

    def upload_data(self, image_path, is_thumbnail=False, metadata={}):
        """Upload a file to the archive."""
        if self.site_proxy_offline:
            plog("Stopping requested upload to site proxy. Site proxy is offline, probably due to missing env variables.")
            return None

        # For thumbnails (jpgs): set the url and validate the required metadata
        if is_thumbnail:
            plog('Uploading thumbnail via the site proxy')
            url = f"{self.base_url}/archive/api/ingest_thumbnail"
            required_thumbnail_metadata = [
                'size',
                'frame_basename',
                'DATE-OBS',
                'DAY-OBS',
                'INSTRUME',
                'SITEID',
                'TELID',
                'PROPID',
                'BLKUID',
                'REQNUM',
                'OBSTYPE'
            ]
            for key in required_thumbnail_metadata:
                if key not in metadata:
                    plog.warn(f"Cannot upload thumbnail. Missing required metadata key: {key}")
                    return None

        # For regular fits files
        else:
            plog('Uploading fits data via the site proxy')
            url = f"{self.base_url}/archive/api/ingest"

        # Send to the site proxy
        with open(image_path, 'rb') as data_file:
            files = {'file': data_file}
            response = self.session.post(url, files=files, data=metadata, stream=True)
            return response


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


    def get_lco_schedule(self, start_time, end_time, telescope, enclosure=None):
        """Get the latest schedule for a site from the site proxy."""
        if self.site_proxy_offline:
            return []

        url = self.base_url + '/observation-portal/api/schedule/'
        params = {
            'start': start_time,
            'end': end_time,
            'telescope': telescope,
        }
        if enclosure:
            params['enclosure'] = enclosure

        try:
            return self.session.get(url, params=params).json().get('results', [])
        except:
            plog(f"Failed to update the LCO schedule. Request url was {url} and url params were {params}.")
            return []


    def get_lco_last_scheduled(self):
        """Get the time the latest schedule was created by the LCO scheduler."""
        if self.site_proxy_offline:
            return None

        url = self.base_url + '/observation-portal/api/last_scheduled/'
        try:
            response = self.session.get(url)
            if response.status_code == 200 and response.text.strip():
                return response.json().get('last_scheduled')
            else:
                plog(f"Warning: LCO scheduler API returned unexpected response.")
                return None
        except Exception as e:
            plog(f"Warning: Error connecting to LCO scheduler API: {str(e)}")
            return None
