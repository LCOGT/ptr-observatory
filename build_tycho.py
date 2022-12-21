# -*- coding: utf-8 -*-
"""
Created on Mon May 18 15:47:06 2020

@author: obs
"""

import os
import datetime
import math
from pathlib import Path
from astropy import units as u
from astropy.coordinates import SkyCoord
from global_yard import g_dev


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


def reduceDec(pDec):
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
    lat = g_dev["evnt"].siteLatitude
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = math.radians(pDec)
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = math.radians(15.0 * pLocal_hour_angle)
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.degrees(math.asin(sinLat * sinDec + cosLat * cosDec * cosHa))
    y = sinHa
    x = cosHa * sinLat - math.tan(decr) * cosLat
    azimuth = math.degrees(math.atan2(y, x)) + 180
    azimuth = reduceAz(azimuth)
    altitude = reduceAlt(altitude)
    return (azimuth, altitude)


def dist_sort_targets(pRa, pDec, pSidTime):
    """
    Given incoming Ra and Dec, produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In addition, full site
    horizon cull is applied.
    """

    if "tycho_tuple" not in globals():
        bootup_tycho()
        print("Booting up Tycho catalogue for the first time")

    ha = reduceHa(pSidTime - pRa)
    c1 = SkyCoord(ra=pRa * u.hr, dec=pDec * u.deg)
    sortedTargetList = []

    for star in tycho_tuple:
        c2 = SkyCoord(ra=star[1] * u.hr, dec=star[0] * u.deg)
        cat_ha = reduceHa(pSidTime - star[1])
        sep = c1.separation(c2)
        if sep.degree > 65:
            continue

        # Altitude checks for focus stars
        az, alt = transform_haDec_to_azAlt(cat_ha, star[0])

        if alt < 30.0 or alt > 80.0:
            continue
        sortedTargetList.append((sep.degree, star))
    sortedTargetList.sort()
    return sortedTargetList


def az_sort_targets(pSidTime, grid=4):
    """Sorts list of targets by azimuth measurement"""
    # NB Bad form. Pick up constants from config.
    sorted_target_list = dist_sort_targets(pSidTime, g_dev['mnt'].config['latitude'], pSidTime)
    az_sorted_targets = []
    for star in sorted_target_list:
        cat_ha = reduceHa(pSidTime - star[1][1])
        az, alt = transform_haDec_to_azAlt(cat_ha, star[1][0])
        az_sorted_targets.append((az, star[1]))
    az_sorted_targets.sort()
    return az_sorted_targets[:: int(grid)]


def bootup_tycho():

    iso_day = datetime.date.today().isocalendar()
    equinox_years = (
        round((iso_day[0] + ((iso_day[1] - 1) * 7 + (iso_day[2])) / 365), 2) - 2000
    )

    # Relative path Tycho opener
    parentPath = Path(os.getcwd())
    print("Current Working Directory is: " + str(parentPath))
    try:
        tycho_cat = open(str(parentPath) + "\support_info\\tycho_mag_7.dat", "r")
    except:
        print("Tycho Catalogue failed to open.")

    global tycho_tuple
    tycho_tuple = []
    count = 0
    for line in tycho_cat:
        entry = line.split(" ")
        count += 1
        ra_hours = round(
            (float(entry[4]) / 60 + float(entry[3])) / 60
            + float(entry[2])
            + equinox_years * float(entry[11]) / 3600,
            5,
        )
        if entry[6][0] == "-":
            sign = -1
        else:
            sign = 1
        dec_degrees = round(
            sign * (float(entry[8]) / 3600 + float(entry[7]) / 60 + float(entry[6][1:]))
            + equinox_years * float(entry[13]) / 3600,
            4,
        )
        tycho_tuple.append((dec_degrees, ra_hours))
    tycho_cat.close()
    tycho_tuple.sort()

    # Run and set tpt_tuple to a grid.
    try:
        tpt_perfect = open(str(parentPath) + "\\support_info\\perfect.dat", "r")
    except:
        print("TPoint catalogue failed to open.")

    global tpt_tuple

    tpt_tuple1 = []
    count = 0
    toss = tpt_perfect.readline()
    toss = tpt_perfect.readline()
    toss = tpt_perfect.readline()
    toss = tpt_perfect.readline()
    for line in tpt_perfect:
        entry = line.split(" ")
        if entry[0][0:3] == "END":
            break
        ha = reduceHa(
            -(int(entry[0]) + (int(entry[1]) + float(entry[2]) / 60.0) / 60.0)
        )
        if abs(ha) > 6:
            continue
        if entry[3][0] == "-":
            sign = -1
        else:
            sign = 1
        dec = sign * (int(entry[3][1:]) + (int(entry[4]) + float(entry[5]) / 60) / 60.0)
        count += 1
        az, alt = transform_haDec_to_azAlt(ha, dec)
        tpt_tuple1.append((az, (ha, dec)))
    tpt_tuple1.sort()
    tpt_tuple = []
    for entry in tpt_tuple1:
        tpt_tuple.append(entry[1])
