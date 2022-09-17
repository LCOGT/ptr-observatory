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

# This routine here removes all mention of previous configs from the path... for safety and my local computer got clogged with all manner of configs in the path (MTF)
pathRemovals=[]
for q in range(len(sys.path)):
   #print (sys.path[q])
    if 'ptr-observatory' in sys.path[q] and 'configs' in sys.path[q]:
        print ('Removing old config path: ' + str(sys.path[q]))
        pathRemovals.append(sys.path[q])

for remover in pathRemovals:
    sys.path.remove(remover)

pathdone=0

## First try to get the hostname from a file in the directory above (..) ptr-observatory
cwd=str(pathlib.Path().resolve())
hwd=cwd.replace('ptr-observatory','')
hostnamefile=glob.glob(hwd+'hostname*')
try:
    site_name=hostnamefile[0].split('hostname')[1]
    print(site_name)
    print ('Adding new config path: ' + str(os.path.join(pathlib.Path().resolve(),"configs", site_name)))
    sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", site_name))
    pathdone=1
except:
    print ("Could not find a hostname* file in the directory above ptr-observatory e.g. hostnamesro")
    print ("trying another method")


#try:

if pathdone==0:
    print ("Attempting hostname approach to config file")

    host_site = socket.gethostname()[:3].lower()   #  NB May be better to split on
                                         # '-' and use first part of hostname.
    if host_site =='saf':
        host_site == 'aro'    #  NB NB THIS is a blatant hack.
    print ('Adding new config path: ' + str(os.path.join(pathlib.Path().resolve(),"configs", host_site)))
    sys.path.append(os.path.join(pathlib.Path().resolve(),"configs", host_site))

try:
    from site_config import *

except:

    print ("Failed the hostname approach to config file")
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