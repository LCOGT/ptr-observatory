
# NOTE: Keep all values as strings for consistency, and to avoid errors with 
#       json conversion. 

sim_config = {
    "site": "sim_site",

    "mount": {
        "mount1": {
            "name": "mount1",
            "driver": 'ASCOM.Simulator.Telescope',
            "settings": {
                "lattitude": "34.4",
                "longitude": "-119.7",
                "elevation": "485", # meters above sea level
                "home_altitude": "0.0",
                "home_azimuth": "0.0",
            },
        },
    },

    "camera": {
        "cam1": {
            "name": "cam1",
            "driver": 'ASCOM.Simulator.Camera',
        },
        "cam2": {
            "name": "cam2",
            "driver": 'ASCOM.Simulator.Camera',
        },
    },

    "filter": {
        "filter1": {
            "name": "filter1",
            "driver": "ASCOM.Simulator.FilterWheel",
        }
    },

    "telescope": {
        "telescope1": {
            "name": "telescope1",
            "driver": "ASCOM.Simulator.Telescope"
        }
    },

    "focuser": {
        "focuser1": {
            "name": "focuser1",
            "driver": "ASCOM.Simulator.Focuser"
        }
    },
    "rotator": {
        "rotator1": {
            "name": "rotator1",
            "driver": "ASCOM.Simulator.Rotator"
        }
    },
}