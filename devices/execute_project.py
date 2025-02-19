#%%
import time
import json
from typing import Dict, Any, Callable
import logging
from devices.sequencer_helpers import compute_target_coordinates
observation = json.loads('''{
  "site": "mrc",
  "enclosure": "enc1",
  "telescope": "0m35",
  "observation_type": "NORMAL",
  "state": "PENDING",

  "id": 583116837,
  "request_group_id": 1885213,

  "created": "2024-11-01T14:04:10.425775Z",
  "modified": "2024-11-01T14:04:10.425770Z",
  "start": "2024-11-02T07:22:14Z",
  "end": "2024-11-02T07:26:56Z",

  "name": "Full Detailed Observation",
  "submitter": "tbeccue",
  "proposal": "LCOSchedulerTest",
  "ipp_value": 1.05,
  "priority": 10,

  "request": {
    "id": 3445199,
    "modified": "2024-10-29T14:57:32.128148Z",
    "state": "PENDING",

    "duration": 282,
    "acceptability_threshold": 90.0,
    "optimization_type": "TIME",

    "observation_note": "",
    "extra_params": {},

    "configuration_repeats": 2,
    "configurations": [
      {
        "id": 10840779,
        "configuration_status": 750648588,
        "instrument_name": "q461",
        "instrument_type": "0M35-QHY461",
        "priority": 1,
        "repeat_duration": null,
        "state": "PENDING",
        "summary": {},
        "type": "EXPOSE",

        "target": {
          "dec": -7.6528696608383,
          "epoch": 2000.0,
          "extra_params": {},
          "hour_angle": null,
          "name": "40 Eridani",
          "parallax": 199.608,
          "proper_motion_dec": -3421.809,
          "proper_motion_ra": -2240.085,
          "ra": 63.8179984124771,
          "type": "ICRS"
        },
        "instrument_configs": [
          {
            "exposure_count": 1,
            "exposure_time": 15.0,
            "extra_params": {
              "offset_dec": 1,
              "offset_ra": 2,
              "rotator_angle": 5
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-L"
            },
            "rois": [],
            "rotator_mode": "RPA"
          },
          {
            "exposure_count": 2,
            "exposure_time": 10.0,
            "extra_params": {
              "offset_dec": 0,
              "offset_ra": 0,
              "rotator_angle": 0
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-R"
            },
            "rois": [],
            "rotator_mode": "RPA"
          }
        ],
        "acquisition_config": {
          "extra_params": {},
          "mode": "OFF"
        },
        "constraints": {
          "extra_params": {},
          "max_airmass": 1.6,
          "max_lunar_phase": 1.0,
          "min_lunar_distance": 30.0
        },
        "extra_params": {
          "dither_pattern": "custom"
        },
        "guide_camera_name": "mrc-qhy461",
        "guiding_config": {
          "exposure_time": null,
          "extra_params": {},
          "mode": "ON",
          "optical_elements": {},
          "optional": true
        }
      },
      {
        "acquisition_config": {
          "extra_params": {},
          "mode": "OFF"
        },
        "configuration_status": 750648589,
        "constraints": {
          "extra_params": {},
          "max_airmass": 1.6,
          "max_lunar_phase": 1.0,
          "min_lunar_distance": 30.0
        },
        "extra_params": {
          "dither_pattern": "custom"
        },
        "guide_camera_name": "mrc-qhy461",
        "guiding_config": {
          "exposure_time": null,
          "extra_params": {},
          "mode": "ON",
          "optical_elements": {},
          "optional": true
        },
        "id": 10840780,
        "instrument_configs": [
          {
            "exposure_count": 1,
            "exposure_time": 15.0,
            "extra_params": {
              "offset_dec": 1,
              "offset_ra": 2,
              "rotator_angle": 5
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-L"
            },
            "rois": [],
            "rotator_mode": "RPA"
          }
        ],
        "instrument_name": "q461",
        "instrument_type": "0M35-QHY461",
        "priority": 2,
        "repeat_duration": null,
        "state": "PENDING",
        "summary": {},
        "target": {
          "dec": 41.26875,
          "epoch": 2000.0,
          "extra_params": {},
          "hour_angle": null,
          "name": "m31",
          "parallax": 0.0,
          "proper_motion_dec": 0.0,
          "proper_motion_ra": 0.0,
          "ra": 10.684708,
          "type": "ICRS"
        },
        "type": "EXPOSE"
      },
      {
        "acquisition_config": {
          "extra_params": {},
          "mode": "OFF"
        },
        "configuration_status": 750648590,
        "constraints": {
          "extra_params": {},
          "max_airmass": 1.6,
          "max_lunar_phase": 1.0,
          "min_lunar_distance": 30.0
        },
        "extra_params": {
          "dither_pattern": "custom"
        },
        "guide_camera_name": "mrc-qhy461",
        "guiding_config": {
          "exposure_time": null,
          "extra_params": {},
          "mode": "ON",
          "optical_elements": {},
          "optional": true
        },
        "id": 10840779,
        "instrument_configs": [
          {
            "exposure_count": 1,
            "exposure_time": 15.0,
            "extra_params": {
              "offset_dec": 1,
              "offset_ra": 2,
              "rotator_angle": 5
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-L"
            },
            "rois": [],
            "rotator_mode": "RPA"
          },
          {
            "exposure_count": 2,
            "exposure_time": 10.0,
            "extra_params": {
              "offset_dec": 0,
              "offset_ra": 0,
              "rotator_angle": 0
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-R"
            },
            "rois": [],
            "rotator_mode": "RPA"
          }
        ],
        "instrument_name": "q461",
        "instrument_type": "0M35-QHY461",
        "priority": 3,
        "repeat_duration": null,
        "state": "PENDING",
        "summary": {},
        "target": {
          "dec": -7.6528696608383,
          "epoch": 2000.0,
          "extra_params": {},
          "hour_angle": null,
          "name": "40 Eridani",
          "parallax": 199.608,
          "proper_motion_dec": -3421.809,
          "proper_motion_ra": -2240.085,
          "ra": 63.8179984124771,
          "type": "ICRS"
        },
        "type": "EXPOSE"
      },
      {
        "acquisition_config": {
          "extra_params": {},
          "mode": "OFF"
        },
        "configuration_status": 750648591,
        "constraints": {
          "extra_params": {},
          "max_airmass": 1.6,
          "max_lunar_phase": 1.0,
          "min_lunar_distance": 30.0
        },
        "extra_params": {
          "dither_pattern": "custom"
        },
        "guide_camera_name": "mrc-qhy461",
        "guiding_config": {
          "exposure_time": null,
          "extra_params": {},
          "mode": "ON",
          "optical_elements": {},
          "optional": true
        },
        "id": 10840780,
        "instrument_configs": [
          {
            "exposure_count": 1,
            "exposure_time": 15.0,
            "extra_params": {
              "offset_dec": 1,
              "offset_ra": 2,
              "rotator_angle": 5
            },
            "mode": "Full",
            "optical_elements": {
              "filter": "mrc-L"
            },
            "rois": [],
            "rotator_mode": "RPA"
          }
        ],
        "instrument_name": "q461",
        "instrument_type": "0M35-QHY461",
        "priority": 4,
        "repeat_duration": null,
        "state": "PENDING",
        "summary": {},
        "target": {
          "dec": 41.26875,
          "epoch": 2000.0,
          "extra_params": {},
          "hour_angle": null,
          "name": "m31",
          "parallax": 0.0,
          "proper_motion_dec": 0.0,
          "proper_motion_ra": 0.0,
          "ra": 10.684708,
          "type": "ICRS"
        },
        "type": "EXPOSE"
      }
    ]
  }
}''')


def get_camera_from_observation_config(observation, observatory):
  pass

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

    def go_to_target(target, offset_ra=0, offset_dec=0):
        if target['type'] != "ICRS":
            print(f'Unsupported target type: {target["type"]}')
            return

        # update the pointing to account for proper motion and parallax
        proper_motion_parallax_adjusted_coords = compute_target_coordinates(target)
        # add ra/dec offsets
        corrected_ra = proper_motion_parallax_adjusted_coords['ra'] + offset_ra
        corrected_dec = proper_motion_parallax_adjusted_coords['dec'] + offset_dec

        print(f'Slewing to ra {corrected_ra}, dec {corrected_dec}')
        mount.go_command(ra=corrected_ra, dec=corrected_dec, objectname=target.get('name'))

    def do_defocus(amount):
        print(f'simulating defocus of {amount}')
        return

    def take_exposure(time, filter_name, smartstack=True, substack=True):
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
        camera.expose_command(
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

    def do_configuration(config, devices):
        go_to_target(config['target'])

        config_type = config['type']

        repeat_duration = config.get('repeat_duration') or 0 # fallback to keep number type
        end_time = time.time() + repeat_duration
        def exposure_sequence_done():
            ''' Return True if configuration type is an exposure sequence and the duration has been exceeded'''
            return config_type == 'REPEAT_EXPOSE' and time.time() > end_time

        if config_type == "EXPOSE":
            for index, ic in enumerate(config['instrument_configs']):
                print(f'starting instrument config #{index}')
                do_instrument_config(ic, config, devices, exposure_sequence_done)
        elif config_type == "REPEAT_EXPOSE":
            while not exposure_sequence_done():
                for index, ic in enumerate(config['instrument_configs']):
                    print(f'starting instrument config #{index}')
                    do_instrument_config(ic, config, devices, exposure_sequence_done)
        else:
            print(f"Unknown config type {config_type}. Skipping this config.")


    def do_instrument_config(ic, config, devices, exposure_sequence_done: Callable[[], bool]) -> None:

        # Ignore defocus for now, since focus routine is tied to camera expose command and I need to untangle them first.
        defocus = ic['extra_params'].get('defocus', False)
        if defocus:
            print(f'Defocus was requested with value {defocus}, but this has not been implemented yet.')
            # do_defocus(defocus)

        offset_ra = ic['extra_params'].get('offset_ra', 0)
        offset_dec = ic['extra_params'].get('offset_dec', 0)
        go_to_target(config['target'], offset_ra, offset_dec)

        exposure_time = ic['exposure_time']
        exposure_count = ic['exposure_count']
        smartstack = config.get('smartstack', True)
        substack = config.get('substack', True)
        filter_name = ic['optical_elements']['filter'].strip('ptr-')
        for _ in range(exposure_count):
            if exposure_sequence_done():
                break
            take_exposure(exposure_time, filter_name, smartstack=smartstack, substack=substack)


    def do_observation(observation):
        request = observation['request']
        # devices = get_devices(observation)
        devices = None

        configuration_repeats = request['configuration_repeats']
        for _ in range(configuration_repeats):
            for index, config in enumerate(request['configurations']):
                print(f'starting config #{index}')
                if is_valid_config(config):
                    do_configuration(config, devices)
                else:
                    print('Config failed validation. Skipping.')

    do_observation(observation)

