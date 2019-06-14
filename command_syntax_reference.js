

/**
 *  Camera
 */

/**
 *  This is an example command that would be sent in the command queue.
 *  It will always include the device name, type, and timestamp.
 *  It will also include three additional entries: 
 *    - action
 *    - required params
 *    - optional params
 */
example_camera_command = {
    device: 'camera_1',
    type: 'camera',
    timestamp: 1558111000,
    action: 'expose',
    required_params: {
        time: 15.5, 
    },
    optional_params: {
        bin: 1,
        gain: 1,
        count: 3,
        filter: 'R',
        size: 1.0,
        keywords: [{observer: 'Tim'}, {project_code: 'M40'}]
    },
}
/**
 *  This is a list of all the actions that the camera can do.
 */
camera_actions = [ 'expose', 'stop' ]
/**
 *  For each possible actions, the required and optional parameters to 
 *  expect are described here.
 */
camera_commands = {
    expose: {
        required_params: {
            time: '(float) exposure time in seconds', 
        },
        optional_params: {
            bin: '(int) defaults to 1',
            gain: '(int) defaults to ??',
            count: '(int) defaults to 1',
            filter: '(str) filter name; defaults to current value',
            modes: '(list of str) camera mode (eg. fast-readout, etc).',
            size: '(float) size of image to use, between 0.0 - 1.0. Centered.',
            dither: '(str) ON or OFF',
            dither_step_size: '(float) default value of 0 if not included.',
            keywords: '(list of dicts) defaults to []. Each dict in list ' +
                      'is a single key/val entry for the fits header.',
        },
    },
    stop: {
        required_params: {},
        optional_params: {},
    },
}

/*****************************************************************************/

/**
 *  Mount
 */
example_mount_command = {
    device: 'mount1',
    type: 'mount',
    timestamp: 1558111000,
    action: 'go',
    required_params: {
        ra: 15.4,
        dec: 76.21,
    },
    optional_params: {}
}
mount_actions = [
    'go', 
    'stop', 
    'home', 
    'flat_panel', 
    'tracking', 
    'park',
]
mount_commands = {
    go: {
        required_params: {
            ra:'(float) decimal right ascension', 
            dec:'(float) decimal declination'
        },
        optional_params: {
            tracking_rate_ra:'(float), defaults to sidereal', 
            tracking_rate_dec:'(float), defaults to 0',
        }
    },
    stop: {
        required_params: {},
        optional_params: {},
    },
    home: {  
        required_params: {},
        optional_params: {},
    },
    flat_panel: {  
        required_params: {},
        optional_params: {},
    },
    tracking: {  
        required_params: {
            tracking: '(str) on or off'
        },
        optional_params: {
            ra_rate: '(str) defaults to sidereal',
            dec_rate: '(str) defaults to 0',
        },
    },
    park: {  
        required_params: {},
        optional_params: {},
    },
}

/*****************************************************************************/

/**
 *  Filter
 */
example_filter_command = {
    device: 'filter_2',
    type: 'filter',
    timestamp: 1558111000,
    action: 'set_position',
    required_params: {
        wheel_positions: [
            {wheel: 0, position: 3},
            {wheel: 1, position: 5},
        ],
    },
    optional_params: {},
}
filter_actions = [ 'set_position', 'set_name', 'home' ]
filter_commands = {
    set_position: {
        required_params: {
            wheel_positions: '(list of dict) list contains positions for' +
                             ' each wheel in filter as a dict. Format:' +
                             ' {wheel:(int), position(int)}'
        },
        optional_params: {}
    },
    set_name: {
        required_params: {
            filter_name: '(str) name of filter to set. Site must implement.'
        },
        optional_params: {},
    },
    home: {
        required_params: {},
        optional_params: {},
    }
}

/*****************************************************************************/

/**
 *  Focuser
 */
example_focus_command = {
    device: 'focuser_1', 
    type: 'focuser',
    timestamp: 1558111000,
    action: 'move_relative',
    required_params: {
        position: -15,
    },
    optional_params: {},
}
focuser_actions = [ 'move_relative', 'move_absolute', 'stop', 'home', 'auto' ]
focuser_commands = {
    move_relative: {
        required_params: {
            position: '(float) microns from current position, + or -',
        },
        optional_params: {}
    },
    move_absolute: {
        required_params: {
            position: '(float) microns from home position, + or -',
        },
        optional_params: {}
    },
    stop: {
        required_params: {},
        optional_params: {},
    },
    home: { 
        required_params: {},
        optional_params: {},
    },
    auto: {
        required_params: {},
        optional_params: {},
    }
}

/*****************************************************************************/

/**
 *  Rotator
 */
example_rotate_command = {
    device: 'rotator_2', 
    type: 'rotator',
    timestamp: 1558111000,
    action: 'move_relative',
    required_params: {
        position: -45,
    },
    optional_params: {},
}
rotator_actions = [ 'move_relative', 'move_absolute', 'home' ]
rotator_commands = {
    move_relative: {
        required_params: {
            position: '(float) degrees from 0 position, + or -',
        },
        optional_params: {},
    },
    move_absolute: {
        required_params: {
            position: '(float) degrees from current position, + or -',
        },
        optional_params: {}
    },
    home: {
        required_params: {},
        optional_params: {},
    }
}

/*****************************************************************************/

/**
 * Selector (typcally 4-position indexing mirror)
 */
example_selector_command = {
    device: 'selector_1', 
    type: 'selector',
    timestamp: 1558111000,
    action: 'set_position',
    required_params: {
        position: 2,
    },
    optional_params: {},
}
selector_actions = [ 'set_position' ]
selector_commands = {
    set_position: {
        required_params: {
            position: '(int) 1-indexed position.',
        },
        optional_params: {},
    },
}

/*****************************************************************************/

/**
 * Switch
 */
example_switch_command = {
    device: 'switch_1', 
    type: 'switch',
    timestamp: 1558111000,
    action: 'pulse',
    required_params: {
        period: 600
    },
    optional_params: {
        init_state: 'OFF'
    },
}
switch_actions = [ 'on', 'off', 'pulse' ]
switch_commands = {
    on: {
        required_params: {},
        optional_params: {
            values: '(list) of arguments that might be needed for the device.'
        },
    },
    off: {
        required_params: {},
        optional_params: {
            values: '(list) of arguments that might be needed for the device.'
        },
    },
    pulse: {
        required_params: {
            period: '(int) seconds for a complete on/off cycle.' +
                    ' note: device will be on for only half period.',
        },
        optional_params: {
            init_state: '(str) ON or OFF. Defaults to ON if not provided.',
            values: '(list) of arguments that might be needed for the device.'
        },
    },
}

/*****************************************************************************/

/**
 * Enclosure
 */
example_enclosure_command = {
    device: 'enclosure_1', 
    type: 'enclosure',
    timestamp: 1558111000,
    action: 'open',
    required_params: {},
    optional_params: {},
}
enclosure_actions = [ 
    'open', 
    'close', 
    'slew_alt', 
    'slew_az', 
    'sync_az',
    'sync_mount', 
    'park', 
]
enclosure_commands = {
    open: {
        required_params: {},
        optional_params: {},
    },
    close: {
        required_params: {},
        optional_params: {},
    },
    slew_alt: {
        required_params: {
            altitude: '(float) move to reveal this altitude'
        },
        optional_params: {},
    },
    slew_az: {
        required_params: {
            azimuth: '(float) move to this azimuth'
        },
        optional_params: {},
    },
    sync_az: {
        required_params: {
            azimuth: '(float) sync to this azimuth'
        },
        optional_params: {},
    },
    sync_mount: {
        required_params: {
            mount: '(str) name of mount to sync with.'
        },
        optional_params: {},
    },
    park: {
        required_params: {},
        optional_params: {},
    }
}