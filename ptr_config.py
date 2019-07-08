# -*- coding: utf-8 -*-
"""
Created on Thu Jul 21 18:02:28 2016

@author: wrosing
"""
'''
NBNBNB THis should be a generic Linux compatible config file,
with an appropriate tree structure.

Work to get site specifics out of all code and generalize the
code so we can specify different cameras, filters, and so on
generically.  Capture site specifics here.

This module needs considerable expansion and PEP8.

For Wx, sky, etc., create a uniform source with lower sample
rate during day, higher at night.  Where computations are expensive,
run them on non-loaded computers.  E.g., Wx report includes
solar elevation and diameter, moon elev and diameter so we can
compute calculatedSky.
'''

import time
import redis
import shelve
#from astropy.time import Time
from astropy import units as u
from astropy.coordinates import EarthLocation #SkyCoord, FK5, ICRS, FK4, Distance, \

###This is important:  c ONE r
core1_redis = redis.StrictRedis(host='10.15.0.15', port=6379, db=0, decode_responses=True)
siteVersion = "20180811"
siteLatitude = 34.342930277777775    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
siteLongitude = -119.68112805555556  #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
siteElevation = 317.75
siteRefTemp = 15.0         #These should be a monthly average data.
siteRefPress = 973.0       #mbar
siteName = "Photon Ranch"
siteAbbreviation = "PTR"
siteCoordinates = EarthLocation(lat=siteLatitude*u.deg, \
                                lon=siteLongitude*u.deg,
                                height=siteElevation*u.m)
#ptr = EarthLocation(lat=siteLatitude*u.deg, lon=siteLongitude*u.deg, height=siteElevation*u.m)

tzOffset = -7

mountOne = "PW_L500"
mountOneAscom = None
cameraOneOne = "ea03"

##NB Need to implement a clearer dual wheel scheme.
#filters are 1 to three letter generic, followed optionally by a 3 didgit
#serial No. which is usually ignored until fits headers are documented in the
#camera code.  WHeels can be multi-layer, includuig a fixed one filter layer.
cameraOneOneFilters = ['air', 'B', 'g', 'V', 'r', 'i', 'zs',  'W', 'EXO', \
                       'Ha', 'O3', 'S2', 'N2'] #air, ...air, ...dark = O3zs
cameraTwoTwo = "qc02"
cameraTwoOneFilters = ['lpr']
cameraThreeOne= None
cameraThreeOneFilters = []
mountTwo = "ASA_DM160"
mountTwoAscom =None
cameraTwoOne = 'qc01'

cameraTwoTwo = None
cameraTwoThree ='kq01'
 #?
cameraTwoFour = None


print('siteConfig for PTR loaded. Ver:  ', siteVersion, '\n')

def next_seq(pCamera):
    global SEQ_Counter
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + pCamera)
    #print('Shelf:  ', camShelf)
    sKey = 'Sequence'
    #print(type(sKey), sKey)
    seq = camShelf[sKey]      #get an 8 character string
    seqInt = int(seq)
    seqInt += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    #print(pCamera,seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

def reset_seq(pCamera):
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(pCamera))
    #seq = camShelf['Sequence']      # a 9 character string
    seqInt = int(-1)
    seqInt  += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    print('Making new seq: ' , pCamera, seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    return seq

def set_focal_ref(pCamera, ref):
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(pCamera))
    camShelf['Focus Ref'] = int(ref)
    camShelf.close()
    return 

def get_focal_ref(pCamera):
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(pCamera))
    return int(camShelf['Focus Ref'])

if __name__ =='__main__':
    print('siteConfig module for PTR started locally. Ver:  ', siteVersion, '\n')