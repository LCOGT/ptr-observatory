# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 20:47:53 2019

@author: obs
"""

# NOTE: Keep all values as strings for consistency, and to avoid errors with 
#       json conversion. 


site_name = "WMD"

site_config = {
    "site": "WMD",
    "alias": "West Mountain Drive, SBA CA USA",

    #*** Proably put Observing conditons here.
    #*** How do we associate a aenith pointed sky cam or IR cam or Seeing monitor?
    
    "observing_conditions": {
        "wx-1": {
            "name": "wx-1",
            "parent": "site",
            "alias": "Wx",
            "driver": 'redis'
            
        },
    },

                
    "enclosure": {
        "encl1": {
            "name": "encl1",
            "parent": "site",
            "alias": "Megawan",
            "driver": 'ASCOM.SkyRoof.Dome',
            "has_lights":  ['White', 'Red', 'IR'],
            "settings": {
                "lattitude": "34.34293028",
                "longitude": "-119.68112805",
                "elevation": "317.75", # meters above sea level
                "lights":  "Auto/White/Red/IR/Off",       #A way to encode possible states or options???
                                                          #First Entry is default condition.
                                                
            },
        },
    },
                    
                        

    "mount": {
        "mnt1": {
            "name": "mnt1",
            "parent": "encl1",
            "alias": "eastpier",
            "desc":  'Planewave L500 AltAz',
            "driver": 'ASCOM.PWI4.Telescope',
            "settings": {
                "lattitude": "34.34293028",
                "longitude": "-119.68105",
                "elevation": "317.75", # meters above sea level
                "home/park_altitude": "1.75",
                "home/park_azimuth": "178.0",
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
                "collecting_area":  '350000.0',
                "obscuration":  "33%",
                "aperture": "450.0",
                "focal_length": "2457.3",
                "has_cover":  "False",
            },
        },      
    },

     "telescope": {
        "tel1": {
            "name": "tel11",
            "parent": "mount1",
            "alias": "main",
            "desc":  "Planewave CDK 450mm F6",
            "driver": "None",                     #Essentially this device is informational.  It is mostly about optics.
            "collecting_area":  '350000.0',
            "obscureation":  "33%",
            "aperture": "450.0",
            "focal_length": "2457.3",
            "has_cover":  "False",
            "has_dew_heaters":  "True",
                "settings": {
                    "dew_heat": "Auto|On|Off",
                    "fans": "High|Auto|Low|Off",
                    "cover": "Close|Open",  
            },
            
        },
#        "tel2": {
#            "name": "tel12",
#            "parent": "mount1",
#            "alias": "auxillary",
#            "desc":  "Astro-physics Starfire 180mm F7",
#            "driver": "None",                     #Essentially this device is informational.  It is mostly about optics.
#            "collecting_area":  "25446",
#            "aperture": "180",
#            "focal_length": "1260",
#            "has_cover":  "True",
#            "Has_dew_heaters":  "True",
#                "settings": {
#                    "Dew_heat": "Auto|On|Off",
#                    "Fans": "High|Auto|Low|Off",
#                    "Cover": "Close|Open", 
#            },
#            
#        },
    },
    
    "rotator": {
        "rotator1": {
            "name": "rotator1",
            "parent": "tel1",
            "alias": "rotator",
            "desc":  'Planewave IRF PWI3',
            "driver": "ASCOM.PWI3.Rotator",
            
        },
                
#        "rotator2": {
#            "name": "rotator2",
#            "parent": "tel2",
#            "alias": "rotator",
#            "desc":  'Optec',
#            "driver": "ASCOM.PWI3.Rotator",
#            
#        }
    },


    "focuser": {
        "focuser1": {
            "name": "focuser1",
            "parent": "tel1",
            "alias": "focuser",
            "desc":  'Planewave IRF PWI3',
            "driver": "ASCOM.PWI3.Focuser",
            "reference":  '11011'
        },
                
#        "focuser2": {
#            "name": "focuser2",
#            "parent": "tel2",
#            "alias": "focuser",
#            "desc":  'Planewave IRF PWI3',
#            "driver": "ASCOM.PWI3.Focuser",
#            "reference":  '11011'
#        }
    },


    "filter": {
        "filter1": {
            "name": "filter1",
            "parent": "tel1",
            "alias": "dual filter wheel",
            "desc":  'FLI Centerline Custom Dual 50mm sq.',
            "driver": 'Maxim.CCDCamera',
            "settings": {
                "filter_count": "23",
                "filters": ['air', 'dif', 'w', 'ContR', 'N2', 'u', 'g', 'r', 'i', 'zs', 'PL', 'PR', 'PG', 'PB', 'O3', 'HA', \
                            'S2', 'dif_u', 'dif_g', 'dif_r', 'dif_i', 'dif_zs', 'dark'],
                 "_filter_index": ['(0, 0), (4, 0), (2, 0), (1, 0), (3, 0), (0, 5), (0, 6), (0, 7), (0, 8), (5, 0), (0, 4), \
                                  (0, 3), (0, 2), (0, 1), (7, 0), (6, 0), (8, 0), (4, 5), (4, 6), (4, 7), (4, 8), (9, 0), \
                                  (10, 9)'],
                 "_filter_offset": ['-1000', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', \
                                   '0', '0', '0', '0', '0', '0']

            },
        },
#        "filter2": {
#            "name": "filter2",
#            "parent": "tel2",
#            "alias": "dual filter wheel",
#            "desc":  'QHY Centerline Custom Dual 50mm sq.',
#            "driver": 'Maxim.CCDCamera',
#            "settings": {
#                "filter_count": "23",
#                "filters": ['air', 'duo', 'triad', 'LPR', 'dark'],
#                 "_filter_index": ['(0, 0), (4, 0), (2, 0), (1, 0), (3, 0), (0, 5), (0, 6), (0, 7), (0, 8), (5, 0), (0, 4), \
#                                  (0, 3), (0, 2), (0, 1), (7, 0), (6, 0), (8, 0), (4, 5), (4, 6), (4, 7), (4, 8), (9, 0), \
#                                  (10, 9)'],
#                 "_filter_offset": ['-1000', '0', '0', '0', '0']
#
#            },
#        },
    },

    "camera": {
        "cam1": {
            "name": "cam1",
            "parent": "tel1",
            "alias": "ea03",      #Important becuase this triggers a server file structure by that name.
            "desc":  'Apogee e2v U42 Back 2k^2',
            "driver": 'Maxim.CCDCamera',
            "settings": {
                "x_pixels":  "2048",
                "y_pixels":  "2048",
                "overscan_x": "50",
                "overscan_y": "0",
                "ns_offset": '0.0',
                "ew_offset": '0.0',
                "area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
                "bins": ['Square=True',  'MaxX=1'],
                "can_bin":  'False',   #Swr binning is square max of 4,  Usually> bin2 is useless.
                "can_subframe":  'True',
                "has_screen": "True",
                "has_darkslide":  "False"
            },
        },

#        "cam2": {
#            "name": "cam2",
#            "parent": "tel2",
#            "alias": "qgc01",      #Important becuase this triggers a server file structure by that name.
#            "desc":  'QHY 367C',
#            "driver": 'Maxim.CCDCamera',
#            "settings": {
#                "x_pixels":  "7376",
#                "y_pixels":  "4938",
#                "overscan_x": "0",
#                "overscan_y": "0",
#                "ns_offset": '0.0',
#                "ew_offset": '0.0',
#                "area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg'],
#                "bins": ['Square=True',  'MaxX=2'],
#                "can_bin":  'True',   #Swr binning is square max of 4,  Usually> bin2 is useless.
#                "can_subframe":  'True',
#                "has_screen": "True",
#                "has_darkslide":  "False"
#            },
#        },
    },



    "web_cam": {
        "web_cam1 ": {
            "name": "web_cam1",
            "parent": "encl1",
            "alias": "MegaCam",
            "desc":  'AXIS PTZ w control',
            "driver": 'http://10.15.0.19',
            "fov":  "90.0",

        },
                
        "web_cam3 ": {
            "name": "web_cam2",
            "parent": "mount3",
            "alias": "FLIR",
            "desc":  'FLIR NIR 10 micron 15deg.',
            "driver": 'http://10.15.0.17',
            "fov":  "15.0",
            "settings": {
                "DID": "0.0",
                "DCH": "0.0",
                "DTF": "0.0"

            },
        },
        "web_cam2 ": {
            "name": "web_cam2",
            "parent": "encl1",
            "alias": "FLIR",
            "desc":  'FLIR NIR 10 micron Zenith View 90 deg',
            "driver": 'http://10.15.0.18',
            "fov":  "90.0",

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
