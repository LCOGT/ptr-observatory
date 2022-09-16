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
import glob

host_site = socket.gethostname()[:3].lower()   #  NB May be better to split on
                                         # '-' and use first part of hostname.
if host_site =='saf':
    host_site == 'aro'    #  NB NB THIS is a blatant hack.
sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", host_site))

#print (pathlib.Path().resolve().replace('ptr-observatory',''))
cwd = str(pathlib.Path().resolve())
print (cwd.replace('ptr-observatory',''))
hwd = cwd.replace('ptr-observatory','')
hostnamefile=glob.glob(hwd+'hostname*')
print (hostnamefile[0])
print (hostnamefile[0].split('hostname'))
print (hostnamefile[0].split('hostname')[1])
site_name = hostnamefile[0].split('hostname')[1]
print (site_name)

sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", 'sro'))
from site_config import *
sys.exit()
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
#  print (site_config)




