# NOTE: Keep all values as strings for consistency, and to avoid errors with 
#       json conversion. 


site_name = "WMD"

site_config = {
    "site": "WMD",
    "alias": "West Mountain Drive, SBA CA USA",
    
    #*** Proably put Observing conditons here.
    #*** How do we associate a aenith pointed sky cam or IR cam or Seeing monitor?
    
    "enclosure": {
        "encl1": {
            "name": "encl1",
            "parent": "site",
            "alias": "Megawan",
            #"driver": 'ASCOM.SkyRoof.Dome',
            "driver": 'ASCOM.Simulator.Dome',
            "settings": {
                "lattitude": "34.34293028",
                "longitude": "-119.68112805",
                "elevation": "317.75", # meters above sea level
            },
        },
    },

    "mount": {
        "mount1": {
            "name": "mount1",
            "parent": "encl1",
            "alias": "eastpier",
            "desc":  'Planewave L500 AltAz',
            #"driver": 'ASCOM.PWI4.Telescope',
            "driver": 'ASCOM.Simulator.Telescope',
            "settings": {
                "lattitude": "34.34293028",
                "longitude": "-119.68105",
                "elevation": "317.75", # meters above sea level
                "home_altitude": "1.75",
                "home_azimuth": "178.0",
                "horizon":  "20",
                "h_detail": {
                     "0": "32",
                     "30": "35",
                     "36.5": "39",
                     "43": "28.6",
                     "59": "32.7",
                     "62": "28.6",
                     "65": "25.2",
                     "74": "22.6",
                     "82": "20",
                     "95.5": "20",
                     "101.5": "14",
                     "107.5": "10",
                     "130": "11",
                     "150": "20",
                     "172": "28",
                     "191": "25",
                     "213": "20",
                     "235": "15.3",
                     "260": "10.5",
                     "272": "17",
                     "294": "16.5",
                     "298.5": "18.6",
                     "303": "20.6",
                     "309": "27",
                     "315": "32",
                     "360": "32",
                },
            },
        },
                        
        "mount2": {
            "name": "mount2",
            "parent": "encl1",
            "alias": "westpier",
            "desc":  'ASA DM160 Equatorial',
            #"driver": 'AstrooptikServer.Telescope',
            "driver": 'ASCOM.Simulator.Telescope',
            "settings": {
                "lattitude": "34.34293028",
                "longitude": "-119.68108",
                "elevation": "317.75", # meters above sea level
                "home_altitude": "0.0",
                "home_azimuth": "180.0",
                "horizon":  "20",
                                "h_detail": {
                     "0": "32",
                     "30": "35",
                     "36.5": "39",
                     "43": "28.6",
                     "59": "32.7",
                     "62": "28.6",
                     "65": "25.2",
                     "74": "22.6",
                     "82": "20",
                     "95.5": "20",
                     "101.5": "14",
                     "107.5": "10",
                     "130": "11",
                     "150": "20",
                     "172": "28",
                     "191": "25",
                     "213": "20",
                     "235": "15.3",
                     "260": "10.5",
                     "272": "17",
                     "294": "16.5",
                     "298.5": "18.6",
                     "303": "20.6",
                     "309": "27",
                     "315": "32",
                     "360": "32",
                },
                
            },
        },
    },

    "rotator": {
        "rotator1": {
            "name": "rotator1",
            "parent": "mount1",
            "alias": "rotator",
            "desc":  'Planewave IRF PWI3',
            "driver": "ASCOM.Simulator.Rotator"
        }
    },

    "focuser": {
        "focuser1": {
            "name": "focuser1",
            "parent": "mount1",
            "alias": "focuser",
            "desc":  'Planewave IRF PWI3',
            "driver": "ASCOM.Simulator.Focuser"
        }
    },


    "filter": {
        "filter1": {
            "name": "filter1",
            "parent": "mount1",
            "alias": "dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            #"driver": "Custom Dual via Maxim",
            "driver": "ASCOM.Simulator.FilterWheel",
            "settings": {
                "count": "23",
                "filters": ['air', 'dif', 'w', 'CR', 'N2', 'u', 'g', 'r', 'i', 'zs', 'PL', 'PR', 'PG', 'PB', 'O3', 'HA', \
                            'S2', 'dif_u', 'dif_g', 'dif_r', 'dif_i', 'dif_zs', 'dark'],
                 "filter_index": ['(0, 0), (4, 0), (2, 0), (1, 0), (3, 0), (0, 5), (0, 6), (0, 7), (0, 8), (5, 0), (0, 4), \
                                  (0, 3), (0, 2), (0, 1), (7, 0), (6, 0), (8, 0), (4, 5), (4, 6), (4, 7), (4, 8), (9, 0), \
                                  (10, 9)'],
                 "filter_offset": ['-1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0']

            },
        }
    },

    "camera": {
        "cam1": {
            "name": "cam1",
            "parent": "mount1",
            "alias": "ea03",      #Important becuase this triggers a server file structure by that name.
            "desc":  'Apogee e2v U42 Back 2k^2',
            #"driver": 'Maxim.CCDCamera',
            "driver": 'ASCOM.Simulator.Camera',
            "settings": {
                "overscan_x": "50",
                "overscan_y": "0",
                "ns-offset": '0.0',
                "ew_offset": '0.0'

            },
        },
        "cam2": {
            "name": "cam2",
            "parent": "mount1",
            "alias": "sim_cam_2",
            "desc": "Simulated second camera",
            "driver": 'ASCOM.Simulator.Camera',
        },
    },


    "Aux OTA": {
        "OTA 2": {
            "name": "IR_cam_2",
            "parent": "mount1",
            "alias": "FLIR",
            "desc":  'FLIR NIR 10 micron 15deg.',
            "driver": 'http://10.15.0.18',
            "settings": {
                "ID": "0.0",
                "CH": "0.0",
                "TF": "0.0"

            },
        }
    },
            
    #***Probably put switch Here for above Mounting
    
    #Here I would lay in devices for Mount 2


    "server": {
        "server1": {
            "name": "QNAP",
            "winURL": "archive (\\10.15.0.82) (Q:)",
            "redis":  "(host='10.15.0.15', port=6379, db=0, decode_responses=True)"
        }
    },
}

