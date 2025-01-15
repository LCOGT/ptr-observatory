# ptr-observatory

When complete, this code will operate observatories in the Photon Ranch network. 

## Installation and Setup

This code requires Python 3.8 or above. Clone the repository to your local Windows machine:

```
git clone https://github.com/LCOGT/ptr-observatory.git
cd ptr-observatory
```

Install the Python dependencies with `$ pip install -r requirements.txt`, preferably in a virtual environment.

Currently, this project does not run on Mac or Linux systems.

## Config Files

Modify `config.py` as appropriate. Make sure to specify the correct ASCOM drivers for each device.
These drivers should already be configured using the ASCOM device chooser.

### Device Names

Devices are defined in the config in a dict of the parent type. For example, the cameras are in a dict called `camera`:
```python
config = {
  "camera": {
    "ec00zwo": {
      # configuration or this camera
    },
    "widefield cam": { 
      # configuration for a second camera...
    },
    "random camera": {
      # configuration for another camera...
    }
  }
}
```

There are two ways devices are uniquely identified:

1. `name`: The name of the device is its key in device_type dict. For example, the above camera names would be
   "ec00zwo", "widefield cam", and "random camera". This is the name shown in the UI, and is used when routing commands
   to the requested device.
2. `role`: The role of a device indicates its place in the observatory setup, and is used to address the device in the
   code. Not all devices will have a role, but most will. If a device doesn't have a role, it can only be accessed by 
   user commands.

Device roles are not defined in the device config, but in a separate part of the site config under the key `device_roles`.
In this dict, all roles are presented as keys, and occupied roles have the device name as the value, or `None` otherwise.
The list of device roles is standardized across all sites. Any changes to this list should be updated here in the readme,
as well as in the obs.py create_devices() method and in every site config.

Below is the device_roles part of a site config in a hypothetical site whose only devices are the cameras listed above:

```python
config = {
  'camera': { ... },
  'device_types': {
  'device_roles': {
      'mount': None, # there will only ever be one mount, so its role is simply "mount"
      'main_focuser': None,
      'main_fw': None, 
      'main_rotator': None,

      # Cameras
      'main_cam': 'ec00zwo',
      'guide_cam': None,
      'widefield_cam': 'widefield cam',
      'allsky_cam': None,
    },
  }
}
```

#### How it's used

Devices are initialized in the Observatory `__init__` routine, via `create_devices`. This routine creates a few
different ways to access the device instances.

##### By Role

The most common way is using the device role via `self.devices`. For example, the device with the role of "main_cam"
is found at `self.devices["main_cam"]`. This returns the device object, or None if there are no devices with that role.

##### By Type -> Name

Devices are also stored in a nested dictionary by type and then name. To get the camera "ec00zwo", you could use
`self.all_devices["camera"]["ec00zwo"]`, which returns the camera object. This is mainly useful for iterating through
all devices of certain type.

##### By Name

Devices can be directly accessed by their name via `self.device_by_name`. This is useed primarily when routing commands
to the correct device. If the payload of the command includes `device_name`, then the command is sent to
`self.device_by_name[device_name]`.
 
#### Similar usage within the devices themselves
These properties (devices, all_devices, devices_by_name) are all available from the device instances themselves after
initialization is complete. All devices are initialized with the parent context as `obs`. So instead of accessing the
main focuser from obs.py with `self.devices["main_focuser"]`, accessing from any device class would use
`self.obs.devices['main_focuser']`.

### ASCOM Drivers

## Usage

Run `obs.py`. Credentials will be verified with aws, ASCOM devices will connect, and finally the infinite loop of checking for commands to run and updating status.

This code is designed to take commands sent through the client web interface at [www.photonranch.org](www.photonranch.org). Alternatively, you can send commands directly to api.photonranch.org. See the [photonranch-api](https://github.com/LCOGT/photonranch-api) repository README for details.
