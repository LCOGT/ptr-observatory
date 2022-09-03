# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20220107 20:01 WER

@author: wrosing
'''
import json
import sys
import time
import os
import pathlib

'''
Ports.txt
Tested 202009
25  
COM8    SkyRoof
COM9    PWI4
COM10   PWI4
COM11   Dew Heater
COM12   EFA
COM13   Alnitak Screen
COM14  	Gemini
COM15   Darkslide
COM16   Camera Peg
        Pwr 1  FLI unPlug
        Pwr 2
        Pwr 3
        Pwr 4   Cam and filters.
Com17   OTA Peg
        Pwr 1  Gemini
        Pwr 2 EFA

Located on CDK 14 OTA:

Pegasus Astro  COM17
PW EFA PWI3    COM12
PW DEW Heat    COM11
GEMINI         COM14

Located on Camera Assembly:

Pegasus Astro   COM16
Vincent Shutt   COM15   Darkslide
FlI FW 1     Closest to tel
FlI FW 2     closest to cam  flifil0
QHY600         AstroImaging Equipment


'''

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

#site_name = 'mrc'    #NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'

site_name = input('What site am I running at?\n')



sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", site_name))

try:
    from site_config import *
except:
    print (str(site_name) + " isn't a real place or there isn't a config file that I can find!")
    sys.exit()

print (site_config)

# #print (site_name)

# # THIS BIT OF CODE DUMPS AN OLD CONFIG FILE TO A NEW JSON... where    
# # with open("sample.json", "w") as outfile:
# #     json.dump(sitegoog, outfile)

# try:
#     with open("configs\\" +str(site_name) + '.json', 'r') as f:
#       site_config = json.load(f)
# except:
#     print (str(site_name) + " isn't a real place or there isn't a config file that I can find!")
#     sys.exit()



