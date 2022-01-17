# -*- coding: utf-8 -*-
"""
Created on Sun Jan 16 20:09:25 2022

@author: obs
"""

import math

DEG_SYM = '°'
PI = math.pi
TWOPI = math.pi*2
PIOVER2 = math.pi/2.
DTOR = math.pi/180.
RTOD = 180/math.pi
STOR = math.pi/180./3600.
RTOS = 3600.*180./math.pi
RTOH = 12./math.pi
HTOR = math.pi/12.
HTOS = 15*3600.
DTOS = 3600.
STOD = 1/3600.
STOH = 1/3600/15.
SecTOH = 1/3600.
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029

def convert_to_mechanical_h_d(pRa, pDec, pFlip):
    if pFlip == 'East':
        return (pRa, pDec)
    else:
        fDec = 180. - pDec
        pRa += 12.
        while pRa >= 24:
            pRa -= 24.
        while pRa < 0.:
            pRa += 24.
        return (pRa, fDec)

def rect_sph_d(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))

def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)

def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta

def centration_d (theta, a, b):
    theta = math.radians(theta)
    return math.degrees(math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

def centration_r (theta, a, b):
    # = math.radians(theta)
    return (math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

def transform_raDec_to_haDec_r(pRa, pDec, pSidTime):

    return (reduce_ha_r(pSidTime - pRa), reduce_dec_r(pDec))

def transform_haDec_to_raDec_r(pHa, pDec, pSidTime):
    return (reduce_ra_r(pSidTime - pHa), reduce_dec_r(pDec))

def transform_haDec_to_azAlt_r(pLocal_hour_angle, pDec, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = pDec
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = pLocal_hour_angle
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.asin(sinLat*sinDec + cosLat*cosDec*cosHa)
    y = sinHa
    x = cosHa*sinLat - math.tan(decr)*cosLat
    azimuth = math.atan2(y, x) + PI
    azimuth = reduce_az_r(azimuth)
    altitude = reduce_alt_r(altitude)
    return (azimuth, altitude)#, local_hour_angle)

def transform_azAlt_to_haDec_r(pAz, pAlt, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    alt = pAlt
    sinAlt = math.sin(alt)
    cosAlt = math.cos(alt)
    az = pAz - PI
    sinAz = math.sin(az)
    cosAz = math.cos(az)
    if abs(abs(alt) - PIOVER2) < 1.0*STOR:
        return (0.0, reduce_dec_r(latr))     #by convention azimuth points South at local zenith
    else:
        dec = math.asin(sinAlt*sinLat - cosAlt*cosAz*cosLat)
        ha = math.atan2(sinAz, (cosAz*sinLat + math.tan(alt)*cosLat))
        return (reduce_ha_r(ha), reduce_dec_r(dec))

def transform_azAlt_to_raDec_r(pAz, pAlt, pLatitude, pSidTime):
    ha, dec = transform_azAlt_to_haDec_r(pAz, pAlt, pLatitude)
    return transform_haDec_to_raDec_r(ha, dec, pSidTime)

def dome_adjust_rah_decd(hah, azd, altd, flip, r, offe, offs ):  #Flip = 'east' implies tel looking East.
                                            #AP Park five is 'west'. offsets are neg for east and
                                            #south at Park five.
    if flip == 'East':
        y = offe + r*math.sin(math.radians(hah*15.))
        if azd >270 or azd <= 90:
            x = offs + r*math.cos(math.radians(altd))
        else:
            x = offs - r*math.cos(math.radians(altd))
                               
    elif flip == 'West':
        y = -offe + r*math.sin(hah*15)
        if azd >270 or azd <= 90:
            x = -offs + r*math.cos(math.radians(altd))
        else:
            x = -offs - r*math.cos(math.radians(altd))
    naz = -math.degrees(math.atan2(y,x))
    if naz < 0:
        naz += 360
    if naz >= 360: 
        naz -= 360
        
    return round(naz, 2)
    print(flip, 'x= ', x,'y= ', y, 'az= ', round(naz, 2))
        



if __name__ == "__main__":
    #                    ha  dc  az   al  flip     r  oe     os
    naz =dome_adjust_rah_decd(5, 35,   358, 10, 'West', 70, -19.55, -8)
   #dome_adjust_rah_decd(00, 35, 000, 45, 'East', 70, -19.55, -8)

    