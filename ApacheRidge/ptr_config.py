# -*- coding: utf-8 -*-
"""
Created on Thu Jul 21 18:02:28 2016

@author: wrosing
"""
'''
This is very old code. This mostly concerns shelving (persiting) valus between invocation of the site vode.
'''
import redis
import shelve
from astropy import units as u
from astropy.coordinates import EarthLocation #SkyCoord, FK5, ICRS, FK4, Distance
from global_yard import g_dev
core1_redis = redis.StrictRedis(host='10.15.0.15', port=6379, db=0, decode_responses=True)


#NB This is being reference before config is loaded, so we have duplicate entries.
# =============================================================================
# WMD site
# siteLatitude = 34.342930277777775    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
# siteLongitude = -119.68112805555556  #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
# siteElevation = 317.75
# siteRefTemp = 15.0         #These should be a monthly average data.
# siteRefPress = 973.0       #mbar
# =============================================================================
# =============================================================================
# saf site
#     'latitude': '35.554444',     #Decimal degrees, North is Positive
#     'longitude': '-105.870278',   #Decimal degrees, West is negative
#     'elevation': '2187',    # meters above sea level
#     'reference_ambient':  ['10.0'],  #Degress Celsius.  Alternately 12 entries, one for every - mid month.
#     'reference_pressure':  ['781.0'],  #mbar   A rough guess 20200315
# =============================================================================
siteLatitude = 35.554444    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
siteLongitude = -105.870278  #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
siteElevation = 2187
siteRefTemp = 10.0         #These should be a monthly average data.
siteRefPress = 781.0       #mbar
siteCoordinates = EarthLocation(lat=siteLatitude*u.deg, \
                                lon=siteLongitude*u.deg,
                                height=siteElevation*u.m)
#ptr = EarthLocation(lat=siteLatitude*u.deg, lon=siteLongitude*u.deg, height=siteElevation*u.m)




def next_seq(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['cam'].archive_path + 'ptr_night_shelf\\' + pCamera)
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
    camShelf = shelve.open(g_dev['cam'].archive_path + 'ptr_night_shelf\\' + pCamera)
    #seq = camShelf['Sequence']      # a 9 character string
    seqInt = int(-1)
    seqInt  += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    print('Making new seq: ' , pCamera, seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    return seq

# def set_focal_ref(pCamera, ref):    #This appears to be a dictionary and there is a type error Line 76
#     camShelf = shelve.open((g_dev['cam'].archive_path + 'ptr_night_shelf\\' + str(pCamera))
#     camShelf['Focus Ref'] = int(ref)
#     camShelf.close()
#     return int(camShelf['Focus Ref'])

# def get_focal_ref(pCamera):
#     camShelf = shelve.open((g_dev['cam'].archive_path + 'ptr_night_shelf\\' + str(pCamera))
#     return int(camShelf['Focus Ref'])

if __name__ =='__main__':
    print('siteConfig module for PTR started locally.', '\n')