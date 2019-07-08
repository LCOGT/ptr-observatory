# -*- coding: utf-8 -*-
"""
Created on Sun Jun 16 17:21:06 2019

@author: obs
"""

"""
A temporary OBS to get all the devices talking without AWS, and an easy way to share access.  Ideally no threading.
"""

import time, json, sys, threading

#from api_calls import API_calls

# import device classes -- order is important -- should match nesting in config.

from devices.observing_conditions import ObservingConditions
from devices.enclosure import Enclosure 
from devices.switch import Switch
from devices.rotator import Rotator
from devices.focuser import Focuser
from devices.filter import Filter
from devices.mount import Mount
from devices.camera import Camera
from config import site_config
from global_yard import g_dev 

#Create the devices


ocn = ObservingConditions('redis', 'ocn1')
enc = Enclosure('ASCOM.SkyRoof.Dome', 'enc1')
swi = None#Switch()
rot = Rotator("ASCOM.PWI3.Rotator", 'rot1')
foc = Focuser("ASCOM.PWI3.Focuser", 'foc1')
fil = Filter('Maxim.CCDCamera', 'fil1')
mnt = Mount('ASCOM.PWI4.Telescope', 'mnt1', site_config['mount']['mount1']['settings'])
cam = Camera( 'Maxim.CCDCamera', 'cam1', mnt, fil, foc, rot, swi, ocn)
    
    
    
    
    
if __name__ == '__main__':
    
    
    
    print('We\'re Back!')
    mnt_command = {'required_params': {'ra': '12', 'dec': '0.5'},
               'optional_params': {},
               'action': 'go'
               }
    print(mnt_command)
    mnt.parse_command(mnt_command)
    cam_command = {'required_params': {'time': '.3', 'frame': 'Light'},
               'optional_params': {'filter': '3', 'area': 25, 'count': '1'},
               'action': 'expose'
               }
    print(cam_command)
#    cam.parse_command(cam_command)
#    cam.parse_command(cam_command)
#    cam.parse_command(cam_command)
#    print('10/100%',  cam.t4-cam.t3,cam.t5-cam.t3)    
#    
    


