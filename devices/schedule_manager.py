
from datetime import datetime
from dateutil import parser
import time
import json
import requests
import os
import threading
from devices.sequencer_helpers import is_valid_utc_iso
from ptr_utility import plog


class NightlyScheduleManager:
    def __init__(self,
                 site: str,
                 schedule_start: int,
                 schedule_end: int,
                 ptr_update_interval: int=60,  # Default to 60 seconds
                 lco_update_interval: int=30,   # Default to 30 seconds
                 include_lco_scheduler: bool=True,
                 configdb_telescope: str=None,
                 configdb_enclosure: str=None,
                ):
        """ A class that manages the schedule for the night. This class is responsible for getting the schedule from the
        site proxy and the PTR calendar and keeping track of the events that are happening.

        Args:
        - site (str): the ptr site (e.g. mrc1). Used for fetching PTR calendar events.
        - schedule_start (int): unix timestamp; get events that start after this time
        - schedule_end   (int): unix timestamp; get events that end before this time
        - ptr_update_interval (int): How often to update PTR schedule in seconds
        - lco_update_interval (int): How often to update LCO schedule in seconds
        - include_lco_scheduler (bool): if this is false, we won't show errors for missing LCO scheduler info
        - configdb_telescope (str): the telecope id used in configdb, used to
            filter the site proxy schedules to only include this site
        - configdb_enclosure (str): name of the enclosure in configdb, used like above
        """

        self.site_proxy_offline = not include_lco_scheduler # Set site proxy offline if we're not including the lco scheduler
        if include_lco_scheduler:
            if 'SITE_PROXY_BASE_URL' not in os.environ:
                plog.err('the environment variable SITE_PROXY_BASE_URL is missing and scheduler observations won\'t work.')
                plog('Please add this to the .env file and restart the observatory.')
                self.site_proxy_offline = True
            if 'SITE_PROXY_TOKEN' not in os.environ:
                plog.err('ERROR: the environment variable SITE_PROXY_TOKEN is missing, which means we can\'t communicate with the site proxy')
                plog('Please add this to the .env file and restart the observatory.')
                self.site_proxy_offline = True
            if configdb_telescope == None:
                plog.err('the configdb_telescope is not set. This is required to fetch the schedule from the site proxy.')
                plog('Observations from the scheduler will not be fetched.')
                self.site_proxy_offline = True
            if configdb_enclosure == None:
                plog.warn('the configdb_enclosure is not set. This is useful for better filtering of site proxy scheudles.')
                plog.warn('It should be an easy value to add to the site config')
        self.site_proxy_base_url = os.getenv('SITE_PROXY_BASE_URL')
        self.site_proxy = requests.Session()
        self.site_proxy.headers.update({'Authorization': os.getenv('SITE_PROXY_TOKEN')})
        self.configdb_telescope = configdb_telescope
        self.configdb_enclosure = configdb_enclosure

        self.site = site

        if schedule_start > schedule_end:
            plog.err("schedule_start is after schedule_end. This is probably not what you want.")
        if schedule_end < time.time():
            plog.warn("schedule_end is in the past. This is probably not what you want.")
        self.schedule_start = schedule_start
        self.schedule_end   = schedule_end

        self._ptr_events = []
        self._lco_events = []
        self._time_of_last_lco_schedule = None

        self._completed_ids = []

        # Thread control variables
        self.ptr_update_interval = ptr_update_interval
        self.lco_update_interval = lco_update_interval
        self._stop_threads = threading.Event()

        # Thread objects
        self._ptr_thread = None
        self._lco_thread = None

        # Thread status indicators
        self.ptr_thread_running = False
        self.lco_thread_running = False

        # Lock for thread-safe operations
        self._lock = threading.RLock()

        plog(f"Starting the schedule manager")
        plog(f"PTR schedules: {True}")
        plog(f"LCO schedules: {not self.site_proxy_offline}")
        self.start_update_threads()


    def _timestamp(self, date: str):
        """ Automatically convert the date formats to unix timestamps

        Designed to supported date formats found in the responses from the PTR calendar and the site proxy:
        - "2025-02-15T02:36:49Z"
        - "2025-02-15T02:36:49.123456Z"
        """
        try:
            return parser.parse(date).timestamp()
        except:
            return None


    def _get_lco_last_scheduled(self):
        """
        Get the time the latest schedule was created by the LCO scheduler
        This is useful to know if we need to update the schedule or not.
        """
        if self.site_proxy_offline:
            return
        url = self.site_proxy_base_url + '/observation-portal/api/last_scheduled/'
        try:
            response = self.site_proxy.get(url)
            # Check if the response is successful and not empty
            if response.status_code == 200 and response.text.strip():
                return response.json().get('last_scheduled')
            else:
                plog(f"Warning: LCO scheduler API returned unexpected response. Status: {response.status_code}, Content: {response.text}")
                return None
        except json.JSONDecodeError:
            plog(f"Warning: Could not decode JSON from LCO scheduler API. Response content: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            plog(f"Warning: Error connecting to LCO scheduler API: {str(e)}")
            return None


    def update_lco_schedule(self, start_time=None, end_time=None):
        """
        Get the latest schedule for this site from the site proxy.
        This function only gets the schedule if it's changed since the last request.

        Args:
        - start_time (str): get events ending after this time. string formatted as YYYY-mm-ddTHH:MM:SSZ
        - end_time (str): get events ending before this time. string formatted as YYYY-mm-ddTHH:MM:SSZ
        """
        if self.site_proxy_offline:
            return

        # First check if there's anything new since last time we checked
        last_lco_schedule_time = self._get_lco_last_scheduled()
        if self._time_of_last_lco_schedule and self._time_of_last_lco_schedule == last_lco_schedule_time:
            return

        # Update the last scheduled time and proceed with fetching the latest
        self._time_of_last_lco_schedule = last_lco_schedule_time

        if start_time is None or not is_valid_utc_iso(start_time):
            start_time = datetime.fromtimestamp(self.schedule_start).isoformat().split(".")[0]
        if end_time is None or not is_valid_utc_iso(end_time):
            end_time = datetime.fromtimestamp(self.schedule_end).isoformat().split(".")[0]

        url = self.site_proxy_base_url + '/observation-portal/api/schedule/'
        params = {
            'start': start_time,
            'end': end_time,
            'telescope': self.configdb_telescope,
            'enclosure': self.configdb_enclosure
        }
        try:
            events = self.site_proxy.get(url, params=params).json().get('results', [])
        except:
            plog(f"Failed to update the LCO schedule. Request url was {url} and url params were {params}.")
            events = []

        with self._lock:
            self._lco_events = [
                {
                    "start": self._timestamp(event["start"]),
                    "end": self._timestamp(event["end"]),
                    "id": event["id"],
                    "origin": "lco",
                    "event": event
                }
                for event in events
            ]

    def update_ptr_schedule(self, start_time=None, end_time=None):
        """
        A function called that updates the calendar blocks - both to get new calendar blocks and to
        check that any running calendar blocks are still there with the same time window.

        Args:
        - start_time (str): get events ending after this time. string formatted as YYYY-mm-ddTHH:MM:SSZ
        - end_time (str): get events ending before this time. string formatted as YYYY-mm-ddTHH:MM:SSZ
        """

        calendar_update_url = "https://calendar.photonranch.org/calendar/siteevents"

        if start_time is None or not is_valid_utc_iso(start_time):
            start_time = datetime.fromtimestamp(self.schedule_start).isoformat().split(".")[0] + "Z"
        if end_time is None or not is_valid_utc_iso(end_time):
            end_time = datetime.fromtimestamp(self.schedule_end).isoformat().split(".")[0] + "Z"

        # Make sure the times are formatted correctly
        if not is_valid_utc_iso(start_time):
            raise ValueError(f"start_time must be formatted YYYY-m-ddTHH:MM:SSZ. Actual input was {start_time}")
        if not is_valid_utc_iso(end_time):
            raise ValueError(f"end_time must be formatted YYYY-m-ddTHH:MM:SSZ. Actual input was {end_time}")

        body = json.dumps({
            "site": self.site,
            "start": start_time,
            "end": end_time,
            "full_project_details": False,
        })

        try:
            events = requests.post(calendar_update_url, body, timeout=20).json()
        except:
            plog(f"ERROR: Failed to update the calendar. This is not normal. Request url was {calendar_update_url} and body was {body}.")
            events = []

        with self._lock:
            self._ptr_events = [
                {
                    "start": self._timestamp(event["start"]),
                    "end": self._timestamp(event["end"]),
                    "id": event["event_id"],
                    "origin": "ptr",
                    "event": event
                }
                for event in events
            ]

    def get_ptr_project_details(self, event):
        """ Get the project details associated a PTR calendar event """
        event = event['event']
        # for reasons, these are possible project_id values when no project is
        # associated with the event
        null_project_ids = [None, 'none', 'none#']
        if 'project_id' not in event or event['project_id'] in null_project_ids:
            return None

        url_proj = "https://projects.photonranch.org/projects/get-project"
        request_body = json.dumps({
            "project_name": event['project_id'].split('#')[0],
            "created_at": event['project_id'].split('#')[1],
        })
        response = requests.post(url_proj, request_body, timeout=10)

        if response.status_code == 200:
            project = response.json()
            return project

        else:
            plog('Failed to retrieve project details for event: ', event)
            return None

    def update_now(self, override_warning=False):
        """ Update the schedule now """
        if not override_warning:
            plog(f'Updating full schedule now. Note that this already happens every {self.ptr_update_interval}s and {self.lco_update_interval}s so it may not be necessary to call this manually.')

        # Create threads for each update operation
        lco_thread = threading.Thread(
            target=self.update_lco_schedule,
            name="LCO_Update_Now_Thread",
            daemon=True
        )
        ptr_thread = threading.Thread(
            target=self.update_ptr_schedule,
            name="PTR_Update_Now_Thread",
            daemon=True
        )

        # Start both threads
        lco_thread.start()
        ptr_thread.start()

        # Wait for both threads to complete
        lco_thread.join()
        ptr_thread.join()


    def add_completed_id(self, id):
        """ Mark this event as complete, so we can avoid trying to run it again """
        with self._lock:
            self._completed_ids.append(id)

    def check_is_completed(self, id):
        """ Check if an event has been marked as completed"""
        with self._lock:
            return id in self._completed_ids

    def clear_completed_ids(self):
        """ Clear the list of completed events """
        with self._lock:
            self._completed_ids = []

    def reset(self, start=None, end=None):
        """Reset the schedule manager with new observing times."""

        # Stop the threads if they're running
        self.stop_update_threads()

        with self._lock:
            if start != None:
                self.schedule_start = start
            if end != None:
                self.schedule_end = end
            self._ptr_events = []
            self._lco_events = []
            self._time_of_last_lco_schedule = None
            self._completed_ids = []

        # Restart the threads if they were running before
        if self.ptr_thread_running or self.lco_thread_running:
            self.start_update_threads()

    @property
    def schedule(self):
        """ Return the list of all events sorted by start time"""
        with self._lock:
            all_events = self._ptr_events + self._lco_events
            return sorted(all_events, key=lambda x: x["start"])

    @property
    def simple_schedule(self):
        """ Return a simplified version of the schedule, with only the start and end times"""
        with self._lock:
            return [
                {
                    "start": event["start"],
                    "end": event["end"],
                    "origin": event["origin"],
                    "id": event["id"],
                }
                for event in self.schedule
            ]

    @property
    def schedule_is_empty(self):
        with self._lock:
            return len(self._ptr_events + self._lco_events) == 0

    def get_active_events(self, unix_time=None):
        """ Get events happening now (default), or at a specific time (if provided). """
        if unix_time is None:
            unix_time = time.time()
        events = []
        with self._lock:
            for event in self.schedule:
                if event["start"] <= unix_time <= event["end"]:
                    events.append(event)
        return events

    def is_observation_request_scheduled(self, obs_req_id, unix_time=None):
        """ Check if an obsevation request (lco) is scheduled now (default), or at an optionally specified time. """
        observations = self.get_active_events(unix_time)
        lco_observation = next((obs for obs in observations if obs['origin'] == "lco"), None)
        return lco_observation and lco_observation['event']['request']['id'] == obs_req_id

    def calendar_event_is_active(self, event_id, unix_time=None):
        """ Check if a calendar event is active now (default), or at an optionally specified time """
        return event_id in [event["id"] for event in self.get_active_events(unix_time)]

    def get_observation_to_run(self, unix_time=None):
        """
        Get an observation that is scheduled to run now (default), or at an optionally specified time.
        If there are any observations from the LCO scheduler, return the first one.
        Otherwise, return the first PTR event with a project attached.

        Response format follows the format of the events in the schedule list,
        with the addition of a 'project' key that contains the project details
        for PTR projects:
        {
            'id': str,
            'start': timestamp,     # unix
            'end': timestamp,       # unix
            'origin': str,          # 'ptr' or 'lco'
            'event': {
                'project': dict,    # only present if origin is 'ptr'
                ...                 # this would be the rest of the calendar event for ptr,
                                      or an observation 'result' from the site_proxy for lco.
            }
        }

        """
        if self.schedule_is_empty:
            return None

        # Default to now
        if unix_time is None:
            unix_time = time.time()

        with self._lock:
            events = self.get_active_events(unix_time)
            events = [x for x in events if not self.check_is_completed(x["id"])]

            for event in events:
                # First check for scheduler events, and return the first one if available
                if event["origin"] == "lco":
                    return event

                # If no scheduler events are available, return the first PTR event with
                # a project associated with it
                else:
                    project = self.get_ptr_project_details(event)
                    if project:
                        return {
                            **event,
                            'event': {
                                **event['event'],
                                'project': project
                            }
                        }

        # If no events with projects/observations are available, return None
        return None

    def _ptr_update_loop(self):
        """Thread function that updates the PTR schedule at regular intervals."""
        self.ptr_thread_running = True

        while not self._stop_threads.is_set():
            try:
                self.update_ptr_schedule()
            except Exception as e:
                plog(f"Error in PTR schedule update thread: {str(e)}")

            # Sleep until next update interval or until stopped
            self._stop_threads.wait(self.ptr_update_interval)

        self.ptr_thread_running = False

    def _lco_update_loop(self):
        """Thread function that updates the LCO schedule at regular intervals."""
        self.lco_thread_running = True

        while not self._stop_threads.is_set():
            try:
                self.update_lco_schedule()
            except Exception as e:
                plog(f"Error in LCO schedule update thread: {str(e)}")

            # Sleep until next update interval or until stopped
            self._stop_threads.wait(self.lco_update_interval)

        self.lco_thread_running = False

    def start_update_threads(self):
        """Start the schedule update threads."""
        with self._lock:
            # Only start threads if they're not already running
            if not self.ptr_thread_running:
                self._ptr_thread = threading.Thread(
                    target=self._ptr_update_loop,
                    name="PTRScheduleUpdateThread",
                    daemon=True  # Make thread a daemon so it exits when main program exits
                )
                self._ptr_thread.start()

            if not self.lco_thread_running:
                self._lco_thread = threading.Thread(
                    target=self._lco_update_loop,
                    name="LCOScheduleUpdateThread",
                    daemon=True  # Make thread a daemon so it exits when main program exits
                )
                self._lco_thread.start()

    def stop_update_threads(self):
        """Stop the schedule update threads."""
        if not (self.ptr_thread_running or self.lco_thread_running):
            return

        self._stop_threads.set()

        # Wait for threads to complete if they're running
        if self._ptr_thread and self._ptr_thread.is_alive():
            self._ptr_thread.join(timeout=2.0)  # Wait up to 2 seconds for thread to finish

        if self._lco_thread and self._lco_thread.is_alive():
            self._lco_thread.join(timeout=2.0)  # Wait up to 2 seconds for thread to finish

        # Reset the stop event
        self._stop_threads.clear()


    # The rest of the functions in this class are used to inject a fake observation for simple testing
    def inject_fake_lco_observation(self, request=None, end_time_offset=3600, lat=None, lng=None):
        """
        Inject a fake LCO observation for testing purposes.

        Args:
            request (dict, optional): The request configuration to use for the fake observation.
                                    If None, a default request will be generated.
            end_time_offset (int, optional): Number of seconds from now when the
                                            observation will end. Defaults to 3600 (1 hour).
            lat (float, optional): Latitude in degrees for target visibility calculation.
                                Defaults to None (which will use a bright default target).
            lng (float, optional): Longitude in degrees for target visibility calculation.
                                Defaults to None (which will use a bright default target).

        Returns:
            dict: The created fake event
        """
        # Calculate start time (1 minute ago)
        start_time = time.time() - 60

        # Calculate end time (default: 1 hour from now)
        end_time = time.time() + end_time_offset

        # Generate a request if one isn't provided
        if request is None:
            request = self.generate_fake_request(lat, lng)

        # Create a unique ID for this fake observation
        fake_id = f"fake_lco_{int(time.time())}"

        # Create the fake event with the structure expected by the scheduler
        fake_event = {
            "start": start_time,
            "end": end_time,
            "id": fake_id,
            "origin": "lco",
            "event": {
                "id": fake_id,
                "start": datetime.fromtimestamp(start_time).isoformat() + "Z",
                "end": datetime.fromtimestamp(end_time).isoformat() + "Z",
                "request": request,
                # Add other required fields from a typical LCO event
                "name": "Fake LCO Observation",
                "site": self.site,
                "enclosure": self.configdb_enclosure or "enc1",
                "telescope": self.configdb_telescope or "0m31",
                "state": "PENDING",
                "observation_type": "NORMAL",
                "created": "2025-02-15T02:33:31.083076Z",
                "ipp_value": 1.05,
                "modified": "2025-02-15T02:33:31.083071Z",
                "priority": 10,
                "proposal": "PTR_integration_test_proposal",
                "request_group_id": 12345,
                "submitter": "tbeccue",
            }
        }

        # Add the fake event to the LCO events list
        with self._lock:
            self._lco_events.append(fake_event)

        plog(f"Injected fake LCO observation with ID {fake_id}")
        return fake_event

    def find_visible_target(self, lat=None, lng=None):
        """
        Find a target that's likely to be visible at the given coordinates.

        Args:
            lat (float, optional): Latitude in degrees. If None, a bright default target is used.
            lng (float, optional): Longitude in degrees. If None, a bright default target is used.

        Returns:
            tuple: (name, ra_deg, dec_deg, note) of the selected target
        """
        import math
        from datetime import datetime

        # List of bright targets that could be visible at various times
        # Format: name, RA (degrees), Dec (degrees), notes
        bright_targets = [
            ("Sirius", 101.28, -16.71, "Brightest star"),
            ("Canopus", 95.99, -52.70, "Second brightest star"),
            ("Arcturus", 213.91, 19.18, "Bright northern star"),
            ("Vega", 279.23, 38.78, "Summer star in northern hemisphere"),
            ("Capella", 79.17, 45.99, "Bright winter star in northern hemisphere"),
            ("Rigel", 78.63, -8.20, "Bright star in Orion"),
            ("Betelgeuse", 88.79, 7.41, "Red supergiant in Orion"),
            ("Altair", 297.69, 8.87, "Bright summer star"),
            ("Aldebaran", 68.98, 16.51, "Bright red giant"),
            ("Antares", 247.35, -26.43, "Red supergiant in Scorpius"),
            ("Spica", 201.29, -11.16, "Bright star in Virgo"),
            ("Pollux", 116.32, 28.03, "Bright star in Gemini"),
            ("Deneb", 310.35, 45.28, "Bright star in Cygnus"),
            ("Regulus", 152.09, 11.96, "Bright star in Leo"),
            ("Fomalhaut", 344.41, -29.62, "Bright star in Southern hemisphere"),
            ("M31 Galaxy", 10.68, 41.27, "Andromeda Galaxy"),
            ("M42 Nebula", 83.82, -5.39, "Orion Nebula"),
            ("M45 Cluster", 56.75, 24.11, "Pleiades star cluster")
        ]

        # If lat/lng not provided, return default target
        if lat is None or lng is None:
            # Default to Sirius as it's the brightest star
            return bright_targets[0]

        # Current time for visibility calculations
        now = datetime.utcnow()
        current_time = now.hour + now.minute/60.0  # Hours in UTC

        # Convert lng to local sidereal time (rough approximation)
        local_sidereal_time = (current_time + lng/15.0) % 24

        # For each target, calculate if it might be above horizon
        visible_targets = []
        for target in bright_targets:
            name, ra_deg, dec_deg, _ = target

            # Convert RA from degrees to hours
            ra_hours = ra_deg / 15.0

            # Calculate hour angle (rough approximation)
            hour_angle = (local_sidereal_time - ra_hours) % 24
            if hour_angle > 12:
                hour_angle = hour_angle - 24

            # Calculate altitude (simplified formula)
            # sin(alt) = sin(lat)*sin(dec) + cos(lat)*cos(dec)*cos(ha)
            dec_rad = math.radians(dec_deg)
            lat_rad = math.radians(lat)
            ha_rad = math.radians(hour_angle * 15)  # Convert hour angle to degrees then to radians

            altitude = math.asin(math.sin(lat_rad) * math.sin(dec_rad) +
                            math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad))
            altitude_deg = math.degrees(altitude)

            # If above horizon (with some margin), add to visible targets
            if altitude_deg > 15:  # 15 degrees above horizon for better visibility
                visible_targets.append((target, altitude_deg))

        # Sort by altitude and take the highest one
        if visible_targets:
            visible_targets.sort(key=lambda x: x[1], reverse=True)
            selected_target = visible_targets[0][0]
            plog(f"Selected target for fake observation: {selected_target[0]} ({selected_target[3]})")
            return selected_target

        # If no targets are visible, return default
        plog("No targets above 15 degrees found, defaulting to Sirius")
        return bright_targets[0]

    def generate_fake_request(self, lat=None, lng=None):
        """
        Generate a fake observation request with a target that's likely to be visible
        at the given coordinates.

        Args:
            lat (float, optional): Latitude in degrees. If None, a bright default target is used.
            lng (float, optional): Longitude in degrees. If None, a bright default target is used.

        Returns:
            dict: A properly formatted request object for use in fake observations
        """
        from datetime import datetime

        # Find a suitable target
        name, ra_deg, dec_deg, note = self.find_visible_target(lat, lng)

        # Create a request ID based on current timestamp
        request_id = int(time.time() * 1000)

        # Build a request object that matches the expected structure
        request = {
            "acceptability_threshold": 90.0,
            "configuration_repeats": 1,
            "configurations": [
                {
                    "acquisition_config": {
                        "extra_params": {},
                        "mode": "OFF",
                    },
                    "configuration_status": request_id + 1,
                    "constraints": {
                        "extra_params": {},
                        "max_airmass": 2.0,
                        "max_lunar_phase": 1.0,
                        "min_lunar_distance": 30.0,
                    },
                    "extra_params": {
                        "smartstack": True,
                    },
                    "guide_camera_name": "",
                    "guiding_config": {
                        "exposure_time": None,
                        "extra_params": {},
                        "mode": "OFF",
                        "optical_elements": {},
                        "optional": True,
                    },
                    "id": request_id + 2,
                    "instrument_configs": [
                        {
                            "exposure_count": 5,
                            "exposure_time": 10.0,
                            "extra_params": {
                                "rotator_angle": 0,
                            },
                            "mode": "full",
                            "optical_elements": {"filter": "ptr-w"},
                            "rois": [],
                            "rotator_mode": "RPA",
                        }
                    ],
                    "instrument_name": "qhy461" if hasattr(self, 'configdb_telescope') and self.configdb_telescope else "main_camera",
                    "instrument_type": f"PTR-{self.site.upper()}" if hasattr(self, 'site') and self.site else "PTR-TEST",
                    "priority": 1,
                    "repeat_duration": None,
                    "state": "PENDING",
                    "summary": {},
                    "target": {
                        "dec": dec_deg,
                        "epoch": 2000.0,
                        "extra_params": {},
                        "hour_angle": None,
                        "name": name,
                        "parallax": 0,
                        "proper_motion_dec": 0,
                        "proper_motion_ra": 0,
                        "ra": ra_deg,
                        "type": "ICRS",
                    },
                    "type": "EXPOSE",
                }
            ],
            "duration": 300,  # 5 minutes
            "extra_params": {},
            "id": request_id,
            "modified": datetime.utcnow().isoformat() + "Z",
            "observation_note": "This is a fake observation for testing",
            "optimization_type": "TIME",
            "state": "PENDING",
        }
        return request

# These are examples for reference. They are not used in the code.
sample_ptr_calendar_response = [
    {
        "origin": "PTR",
        "creator": "Tim Beccue",
        "resourceId": "tbo2",
        "site": "tbo2",
        "creator_id": "google-oauth2|100354044221813550027",
        "reservation_note": "",
        "event_id": "a179dcad-d7b4-40c8-9a4e-bf2f0df0d9ff",
        "reservation_type": "project",
        "project_id": "Simple observation from LCO - tbo2#2025-02-04T05:04:55Z",
        "end": "2025-03-08T01:35:00Z",
        "project_priority": "standard",
        "last_modified": "2025-03-08T00:30:54Z",
        "start": "2025-03-07T23:35:00Z",
        "title": "Tim Beccue",
    }
]

sample_site_proxy_schedule_response = {
    "count": 74,
    "next": None,
    "previous": None,
    "results": [
        {
            "created": "2025-02-15T02:33:31.083076Z",
            "enclosure": "enc1",
            "end": "2025-02-15T03:11:43Z",
            "id": 583120106,
            "ipp_value": 1.05,
            "modified": "2025-02-15T02:33:31.083071Z",
            "name": "Full Complete Observation mrc1",
            "observation_type": "NORMAL",
            "priority": 10,
            "proposal": "PTR_integration_test_proposal",
            "request": {
                "acceptability_threshold": 90.0,
                "configuration_repeats": 2,
                "configurations": [
                    {
                        "acquisition_config": {
                            "extra_params": {},
                            "mode": "OFF",
                        },
                        "configuration_status": 750654859,
                        "constraints": {
                            "extra_params": {},
                            "max_airmass": 1.6,
                            "max_lunar_phase": 1.0,
                            "min_lunar_distance": 30.0,
                        },
                        "extra_params": {
                            "dither_pattern": "custom",
                            "smartstack": True,
                            "substack": True,
                        },
                        "guide_camera_name": "",
                        "guiding_config": {
                            "exposure_time": None,
                            "extra_params": {},
                            "mode": "OFF",
                            "optical_elements": {},
                            "optional": True,
                        },
                        "id": 10840803,
                        "instrument_configs": [
                            {
                                "exposure_count": 10,
                                "exposure_time": 15.0,
                                "extra_params": {
                                    "offset_dec": 1,
                                    "offset_ra": 2,
                                    "rotator_angle": 0,
                                },
                                "mode": "full",
                                "optical_elements": {"filter": "ptr-w"},
                                "rois": [],
                                "rotator_mode": "RPA",
                            },
                            {
                                "exposure_count": 40,
                                "exposure_time": 10.0,
                                "extra_params": {
                                    "offset_dec": 0,
                                    "offset_ra": 0,
                                    "rotator_angle": 0,
                                },
                                "mode": "full",
                                "optical_elements": {"filter": "ptr-w"},
                                "rois": [],
                                "rotator_mode": "RPA",
                            },
                        ],
                        "instrument_name": "qhy461",
                        "instrument_type": "PTR-MRC1-0M31-QHY461",
                        "priority": 1,
                        "repeat_duration": None,
                        "state": "PENDING",
                        "summary": {},
                        "target": {
                            "dec": -7.6528696608383,
                            "epoch": 2000.0,
                            "extra_params": {},
                            "hour_angle":None,
                            "name": "40 Eridani",
                            "parallax": 199.608,
                            "proper_motion_dec": -3421.809,
                            "proper_motion_ra": -2240.085,
                            "ra": 63.8179984124771,
                            "type": "ICRS",
                        },
                        "type": "EXPOSE",
                    }
                ],
                "duration": 2094,
                "extra_params": {},
                "id": 3445217,
                "modified": "2025-02-18T14:35:00.293445Z",
                "observation_note": "",
                "optimization_type": "TIME",
                "state": "WINDOW_EXPIRED",
            },
            "request_group_id": 1885231,
            "site": "mrc",
            "start": "2025-02-15T02:36:49Z",
            "state": "PENDING",
            "submitter": "tbeccue",
            "telescope": "0m31",
        },
    ],
}
