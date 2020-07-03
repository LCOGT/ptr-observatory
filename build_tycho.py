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
from collections import namedtuple
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                         EarthLocation, AltAz
from astroquery.vizier import Vizier
from astroquery.simbad import Simbad
import ephem


iso_day = datetime.date.today().isocalendar()
equinox_years = round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2) - 2000
tycho_cat = open("C:/Users/obs/Documents/GitHub/ptr-observatory/support_info/tycho_mag_7.dat", 'r')
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
    tycho_tuple.append((ra_hours,dec_degrees))
tycho_cat.close()
tycho_tuple.sort()

def dist_sort_targets(pRa, pDec, pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global tycho_tuple
    ha =   pSidTime - pRa
    while ha < -12:
        ha += 24
    while ha >= 12:
        ha -= 12
    if ha < 0:
        sign = -1
    else:
        sign = 1

    c1 = SkyCoord(ra=pRa*u.hr, dec=pDec*u.deg)
    sortedTargetList = []
    for star in tycho_tuple:
        #if horizonCheck(star[0], star[1], pSidTime):
        c2 = SkyCoord(ra=star[1]*u.hr, dec=star[0]*u.deg)
        cat_ha = pSidTime - star[1]
        while cat_ha < -12:
            cat_ha += 24
        while cat_ha >= 12:
            cat_ha -= 12
        if cat_ha < 0:
            cat_sign = -1
        else:
            cat_sign = 1
        if cat_sign == sign:
            sep = c1.separation(c2)
            sortedTargetList.append((round(sep.degree, 3), star))
    sortedTargetList.sort()
    #print('distSortTargets', len(targetList), targetList, '\n\n')
    #print('distSortTargets', len(sortedTargetList), SortedTargetList, '\n\n')
    return sortedTargetList[0]     #  NB NB NBNeed to guard against an empty list.

if __name__ == '__main__':
    print (dist_sort_targets(0, 34, 23))



