# -*- coding: utf-8 -*-
"""
Created on Mon May 18 15:47:06 2020

@author: obs
"""
import math
from math import *
import datetime as datetime
from datetime import timedelta
import time
import socket
import struct
import os
import shelve
from collections import namedtuple
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                         EarthLocation, AltAz
#from astroquery.vizier import Vizier
#from astroquery.simbad import Simbad
import ephem
#from global_yard import g_dev


iso_day = datetime.date.today().isocalendar()
equinox_years = round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2) - 2000
tycho_cat = open("../ptr-observatory/support_info/tycho_mag_7.dat", 'r')

tycho_tuple = []
for line in tycho_cat:
    entry = line.split(' ')
    ra_hours = round((float(entry[4])/60 + float(entry[3]))/60 + float(entry[2]) + equinox_years* float(entry[11])/3600, 5)
    if entry[6][0] == '-':
        sign = -1
    else:
        sign = 1
    #print (entry, sign, float(entry[6][1:]), float(entry[7]), float(entry[8]))
    dec_degrees = round(sign*(float(entry[8])/3600 + float(entry[7])/60 + float(entry[6][1:])) + equinox_years* float(entry[13])/3600, 4)
    tycho_tuple.append((dec_degrees, ra_hours))
tycho_cat.close()
tycho_tuple.sort()
print('# of Tycho stars in grid:  ', len(tycho_tuple))

def transform_haDec_to_azAlt(pLocal_hour_angle, pDec):
    #lat = g_dev['cfg']['latitude']
    lat=35.554444
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = math.radians(pDec)
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = math.radians(15.*pLocal_hour_angle)
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.degrees(math.asin(sinLat*sinDec + cosLat*cosDec*cosHa))
    y = sinHa
    x = cosHa*sinLat - math.tan(decr)*cosLat
    azimuth = math.degrees(math.atan2(y, x)) + 180
    while azimuth >= 360:
        azimuth -= 360.
    while azimuth < 0:
        azimuth += 360.

    return azimuth, altitude

def dist_sort_targets(pRa, pDec, pSidTime, horizon=25):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    global tycho_tuple


    # #print(pRa, pDec, pSidTime)
    # We compute which side of sky it is on so we do not flip.
    ha =   pSidTime - pRa
    while ha < -12:
        ha += 24
    while ha >= 12:
        ha -= 12
    if ha < 0:
        target_sign = -1
    else:
        target_sign = 1

    c1 = SkyCoord(ra=pRa*u.hr, dec=pDec*u.deg)

    sortedTargetList = []
    for star in tycho_tuple:
        #  Convert catalog Ra, Dec to an Astropy SkyCoordinate.
        c2 = SkyCoord(ra=star[1]*u.hr, dec=star[0]*u.deg )
        cat_ha = pSidTime - star[1]
        while cat_ha < -12:
            cat_ha += 24
        while cat_ha >= 12:
            cat_ha -= 12
        #Compute its AltAz coordinates:
        azimuth, altitude = transform_haDec_to_azAlt(cat_ha, star[0])#  lat=35.554444)
        if altitude < horizon:
            continue
        if cat_ha < 0:
            cat_sign = -1
        else:
            cat_sign = 1
        #  This should be paramaterized with mount type.
        if cat_sign == target_sign:    # This prevents a flip
            sep = c1.separation(c2)

            sortedTargetList.append((sep.degree, star))
    sortedTargetList.sort()
    #print('distSortTargets', len(sortedTargetList), sortedTargetList, '\n\n')
    return sortedTargetList[0]

if __name__ == '__main__':
    print (dist_sort_targets(1, 9, 0))



