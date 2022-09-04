# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updated 20220904 22:42WER

@authors: wrosing, mfitz
''' 


#import json
import sys
#import time
import os
import pathlib
import socket

#  NB NB NB json is not bi-directional with tuples (), instead, use lists [],
                                                       #    nested if needed.

host_site = socket.gethostname()[:3].lower()   #  NB May be better to split on
                                         # '-' and use first part of hostname.
sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", host_site))

try:
    from site_config import *
except:
    print (str(host_site) + " isn't a real place or there isn't a config file\
                              that I can find!|n")
    #sys.exit()
    try:
        site_name = input('What site am I running at?\n')
        sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", \
                        site_name))

        try:
            from site_config import *
        except:
            print (str(site_name) + " isn't a real place, or there isn't a \
                                     config file that I can find!")
            sys.exit()

    except:
        print('You need to supply a correct site name.')
        sys.exit()

#print (site_config)




