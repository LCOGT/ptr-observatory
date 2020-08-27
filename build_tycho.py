# -*- coding: utf-8 -*-
"""
Created on Mon May 18 15:47:06 2020

@author: obs
"""

import datetime as datetime
from datetime import timedelta
import socket
import struct
import os
import shelve
import math
from collections import namedtuple
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                         EarthLocation, AltAz
from astroquery.vizier import Vizier
from astroquery.simbad import Simbad
import ephem
from pprint import pprint


iso_day = datetime.date.today().isocalendar()
equinox_years = round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2) - 2000
#C:/Users/obs/Documents/GitHub/ptr-observatory/support_info
tycho_cat = open("C:/Users/obs/Documents/GitHub/ptr-observatory/support_info/tycho_mag_7.dat", 'r')

tycho_tuple = []
count = 0
for line in tycho_cat:
    entry = line.split(' ')
    count += 1
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
#print(count)


def reduceHa(pHa):
    while pHa <= -12:
        pHa += 24.0
    while pHa > 12:
        pHa -= 24.0
    return pHa

def reduceRa(pRa):
    while pRa < 0:
        pRa += 24.0
    while pRa >= 24:
        pRa -= 24.0
    return pRa

def reduceDec( pDec):
    if pDec > 90.0:
        pDec = 90.0
    if pDec < -90.0:
        pDec = -90.0
    return pDec

def reduceAlt(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt

def reduceAz(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz

def transform_haDec_to_azAlt(pLocal_hour_angle, pDec):
    lat = 35.554444   # NB Bad form.
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
    azimuth = reduceAz(azimuth)
    altitude = reduceAlt(altitude)
    return (azimuth, altitude)#, local_hour_angle)

def dist_sort_targets(pRa, pDec, pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global tycho_tuple
    ha =   reduceHa(pSidTime - pRa)
    c1 = SkyCoord(ra=pRa*u.hr, dec=pDec*u.deg)
    sortedTargetList = []
    for star in tycho_tuple:
        #if horizonCheck(star[0], star[1], pSidTime):
        c2 = SkyCoord(ra=star[1]*u.hr, dec=star[0]*u.deg)
        cat_ha = reduceHa(pSidTime - star[1])
        sep = c1.separation(c2)
        if sep.degree > 65 :
            continue
        sortedTargetList.append((sep.degree, star))
    sortedTargetList.sort()
    #print('distSortTargets', len(targetList), targetList, '\n\n')
    #print('distSortTargets', len(sortedTargetList), sortedTargetList, '\n\n')
    #print('distSortTargets', len(sortedTargetList), '\n\n')
    return sortedTargetList

def az_sort_targets(pSidTime, grid=4):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
       # NB Bad form. Pick up constants from config.
    sorted_target_list = dist_sort_targets(pSidTime, 35.55, pSidTime)
    #print(len(sorted_target_list))
    az_sorted_targets = []
    for star in sorted_target_list:
        #if horizonCheck(star[0], star[1], pSidTime):
        c2 = SkyCoord(ra=star[1]*u.hr, dec=star[0]*u.deg)
        cat_ha = reduceHa(pSidTime - star[1][1])
        az, alt = transform_haDec_to_azAlt(cat_ha, star[1][0])
        #if cat_sign == sign:

        if  alt < 25 or alt > 84:
            continue
        az_sorted_targets.append((az, star[1]))
    az_sorted_targets.sort()
    #print('distSortTargets', len(targetList), targetList, '\n\n')
    #print('AzSortTargets', az_sorted_targets[:],len(az_sorted_targets[:]), '\n\n')
    return az_sorted_targets[::int(grid)]

if __name__ == '__main__':
    print (len(az_sort_targets(17)))
