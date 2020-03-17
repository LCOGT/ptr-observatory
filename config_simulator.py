
# NOTE: Keep all values as strings for consistency, and to avoid errors with 
#       json conversion. 

site_name = "sim_site"

site_config = {
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
        "mount2": {
            "name": "mount2",
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
            "driver": "ASCOM.Simulator.Focuser",
            'parent': 'telescope1',
            'alias': 'focuser',
            'desc':  'Optec Gemini',
            'reference':  '5941',    #Nominal at 20C Primary temperature, in microns not steps.
            'ref_temp':   '15',      #Update when pinning reference
            'coef_c': '0',   #negative means focus moves out as Primary gets colder
            'coef_0': '0',  #Nominal intercept when Primary is at 0.0 C.
            'coef_date':  '20300314',
            'minimum': '0',    #NB this needs clarifying, we are mixing steps and microns.
            'maximum': '12700', 
            'step_size': '1',
            'backlash':  '0',
            'unit': 'steps',
            'unit_conversion':  '0.090909090909091',
            'has_dial_indicator': 'false'
        }
    },
    "rotator": {
        "rotator1": {
            "name": "rotator1",
            "driver": "ASCOM.Simulator.Rotator"
        }
    },
}