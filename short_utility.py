# -*- coding: utf-8 -*-
"""
Created on Thu Dec 21 23:03:06 2023

@author: obs
"""

# -*- coding: utf-8 -*-
"""
Created on Fri Nov 17 04:25:54 2023

@author: wrosi
"""
from collections import namedtuple
from datetime import datetime#, date
import math
from math import degrees, radians, sin, cos, asin, acos, tan, atan2, atan
import os
#import shelve
#import time

from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, ICRS, EarthLocation
#from astroquery.simbad import Simbad
import ephem
#from ptr_events import compute_day_directory
#from ptr_config import site_config
#from global_yard import g_dev

from datetime import timezone, timedelta #datetime,
#from dateutil import tz



Target = namedtuple(
    "Target", ["ra", "dec", "name", "simbad", "obj", "mag", "size", "pa", "ly", "cdist"]
)  # last a string with unit

DEG_SYM = "°"
PI = math.pi
TWOPI = math.pi * 2
PIOVER2 = math.pi / 2.0
DTOR = math.pi / 180.0
RTOD = 180 / math.pi
STOR = math.pi / 180.0 / 3600.0
RTOS = 3600.0 * 180.0 / math.pi
RTOH = 12.0 / math.pi
HTOR = math.pi / 12.0
HTOS = 15 * 3600.0
DTOS = 3600.0
STOD = 1 / 3600.0
STOH = 1 / 3600 / 15.0
SecTOH = 1 / 3600.0
APPTOSID = 1.00273811906  # USNO Supplement
MOUNTRATE = 15 * APPTOSID  # 15.0410717859
KINGRATE = 15.029

# try:
#     RefrOn = site_config["mount"]["mount1"]["settings"]["refraction_on"]
#     ModelOn = site_config["mount"]["mount1"]["settings"]["model_on"]
#     RatesOn = site_config["mount"]["mount1"]["settings"]["rates_on"]
# except:
RefrOn = True
ModelOn = True
RatesOn = True

HORIZON = 9.999  # Lower than actual mrc values.
ALTAZ = False
GEM = True
FORK = False

#These should be class variables ??
lat = 35
sin_lat = sin(radians(lat))
cos_lat = cos(radians(lat))

model = {}

model["IH"] = 0  # -2456.2107   #From ARO 20231122
model["ID"] = 0# +559.0443
model["EDH"] = 0
model["EDD"] = 0
model["MA"] = 1800 #+117.2244
model["ME"] = 0 #-397.5761
model["CH"] = 0 #-438.0139

model["NP"] = 0# +188.9130
model["TF"] = 0
model["TX"] = 0
model["HCES"] = 0
model["HCEC"] = 0
model["DCES"] = 0
model["DCEC"] = 0



# NB NB  These functions may not work for mechanical coordinates.
def reduce_ha_h(pHa):
    while pHa <= -12:
        pHa += 24.0
    while pHa > 12:
        pHa -= 24.0
    return pHa


def reduce_ra_h(pRa):
    while pRa < 0:
        pRa += 24.0
    while pRa >= 24:
        pRa -= 24.0
    return pRa


def reduce_dec_d(pDec):
    if pDec > 90.0:
        pDec = 90.0
    if pDec < -90.0:
        pDec = -90.0
    return pDec


def reduce_alt_d(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt


def reduce_az_d(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz


def reduce_ha_r(pHa):
    while pHa <= -PI:
        pHa += TWOPI
    while pHa > PI:
        pHa -= TWOPI
    return pHa


def reduce_ra_r(pRa):
    while pRa < 0:
        pRa += TWOPI
    while pRa >= TWOPI:
        pRa -= TWOPI
    return pRa


def reduce_dec_r(pDec):
    if pDec > PIOVER2:
        pDec = PIOVER2
    if pDec < -PIOVER2:
        pDec = -PIOVER2
    return pDec


def reduce_alt_r(pAlt):
    if pAlt > PIOVER2:
        pAlt = PIOVER2
    if pAlt < -PIOVER2:
        pAlt = -PIOVER2
    return pAlt


def reduce_az_r(pAz):
    while pAz < 0.0:
        pAz += TWOPI
    while pAz >= TWOPI:
        pAz -= TWOPI
    return pAz

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

def convert_to_mechanical_h_d(pRa, pDec, pFlip):
    if pFlip == "East":
        return (pRa, pDec)
    else:
        fDec = 180.0 - pDec
        pRa += 12.0
        while pRa >= 24:
            pRa -= 24.0
        while pRa < 0.0:
            pRa += 24.0
        return (pRa, fDec)


def rect_sph_d(pX, pY, pZ):
    rSq = pX * pX + pY * pY + pZ * pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ / rSq))

def rect_sph_r(pX, pY, pZ):
    rSq = pX * pX + pY * pY + pZ * pZ
    return math.atan2(pY, pX), math.asin(pZ / rSq)

def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll) * cPitch, math.sin(pRoll) * cPitch, math.sin(pPitch)

def sph_rect_r(pRoll, pPitch):
    cPitch = math.cos(pPitch)
    return math.cos(pRoll) * cPitch, math.sin(pRoll) * cPitch, math.sin(pPitch)


def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta


def centration_d(theta, a, b):
    theta = math.radians(theta)
    return math.degrees(
        math.atan2(math.sin(theta) - STOR * b, math.cos(theta) - STOR * a)
    )


def centration_r(theta, a, b):
    return math.atan2(math.sin(theta) - STOR * b, math.cos(theta) - STOR * a)

def appToObsRaHa(appRa, appDec, pSidTime):
    global raRefr, decRefr, refAsec
    try:
        g_dev["ocn"].get_proxy_temp_press()
    except:
        pass
    appHa, appDec = transform_raDec_to_haDec_r(appRa, appDec, pSidTime)
    appAz, appAlt = transform_haDec_to_azAlt_r(
        appHa, appDec, site_config["latitude"] * DTOR
    )
    try:
        obsAlt, refAsec = apply_refraction_inEl_r(
            appAlt, g_dev["ocn"].temperature, g_dev["ocn"].pressure
        )
        obsHa, obsDec = transform_azAlt_to_haDec_r(
            appAz, obsAlt, site_config["latitude"] * DTOR
        )
    except:
        pass

    raRefr = reduce_ha_r(appHa - obsHa) * HTOS
    decRefr = -reduce_dec_r(appDec - obsDec) * DTOS
    return reduce_ha_r(obsHa), reduce_dec_r(obsDec), refAsec



def transform_haDec_to_az_alt(pLocal_hour_angle, pDec):
    #global sin_lat, cos_lat     #### Check to see if these can be eliminated
    decr = radians(pDec)
    sinDec = sin(decr)
    cosDec = cos(decr)
    mHar = radians(15.0 * pLocal_hour_angle)
    sinHa = sin(mHar)
    cosHa = cos(mHar)
    altitude = degrees(asin(sin_lat * sinDec + cos_lat * cosDec * cosHa))
    x = cosHa * sin_lat - tan(decr) * cos_lat
    azimuth = degrees(atan2(sinHa, x)) + 180
    # azimuth = reduceAz(azimuth)
    # altitude = reduceAlt(altitude)
    return (azimuth, altitude)  # , local_hour_angle)


def transform_azAlt_to_haDec(pAz, pAlt):
    #global sin_lat, cos_lat, lat
    alt = radians(pAlt)
    sinAlt = sin(alt)
    cosAlt = cos(alt)
    az = radians(pAz) - PI
    sinAz = sin(az)
    cosAz = cos(az)
    if abs(abs(alt) - PIOVER2) < 1.0 * STOR:
        return (
            0.0,
            lat
        )  # by convention azimuth points South at local zenith
    else:
        dec = degrees(asin(sinAlt * sin_lat - cosAlt * cosAz * cos_lat))
        ha = degrees(atan2(sinAz, (cosAz * sin_lat + tan(alt) * cos_lat)))/15.
        return (reduce_ha_h(ha), reduce_dec_d(dec))

def apply_refraction_in_alt(pApp_alt, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg     #note change to mbar
    global RefrOn
    # From Astronomical Algorithms.  Max error 0.89" at 0 elev.
    # 20210328 This code does not the right thing if star is below the Pole and is refracted above it.
    if not RefrOn:
        return pApp_alt, 0.0
    elif pApp_alt > 0:
        ref = (1 / tan(DTOR * (pApp_alt + 7.31 / (pApp_alt + 4.4))) + 0.001351521673756295)
        ref -= 0.06 * sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        obs_alt = pApp_alt + ref / 60.0
        return reduce_alt_d(obs_alt), ref * 60.0    #note the Observed _altevation is > apparent.
    else:
        #Just return refr for elev = 0
        ref = 1 / tan(DTOR * (7.31 / (pApp_alt + 4.4))) + 0.001351521673756295
        ref -= 0.06 * sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        return reduce_alt_d(obs_alt), ref * 60.0

def correct_refraction_in_alt(pObs_alt, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg
    global RefrOn
    if not RefrOn:
        return pObs_alt, 0.0, 0
    else:
        ERRORlimit = 0.01 * STOR
        count = 0
        error = 10
        trial = pObs_alt
        while abs(error) > ERRORlimit:
            appTrial, ref = apply_refraction_in_alt(trial, pSiteRefTemp, pSiteRefPress)
            error = appTrial - pObs_alt
            trial -= error
            count += 1
            if count > 25:  # count about 12 at-0.5 deg. 3 at 45deg.
                return reduce_alt_d(pObs_alt)
        return reduce_alt_d(trial), reduce_alt_d(pObs_alt - trial)  * 3600.0, count

def forward_adjust (pRoll, pPitch, pPierSide, loud=False):
    #Need to add in J2000 to Jnow
    bRoll, bPitch = transform_observed_to_mount(pRoll, pPitch, pPierSide)
    eRoll, ePitch = transform_observed_to_mount(pRoll+1/3600, pPitch, pPierSide)
    print(eRoll-bRoll, ePitch-bPitch)
    pass


def transform_observed_to_mount(pRoll, pPitch, pPierSide, loud=False, enable=False):
    """
    Long-run probably best way to do this in inherit a model dictionary.

    NBNBNB improbable minus sign of ID, WD

    This implements a basic 7 term TPOINT transformation.
    This routine is directly invertible. Input in radians.
    """
    #breakpoint()
    #loud = True

    if not ModelOn:
        return (pRoll, pPitch)
    else:
        if True:  # TODO needs to specify, else statement unreachable.
            ih = model["IH"]    #Units are all arc-seconds/radian
            idec = model["ID"]
            edh = model["EDH"]    #These 2 are differential if mount is flipped.
            edd = model["EDD"]
            ma = model["MA"]
            me = model["ME"]
            ch = model["CH"]
            np = model["NP"]
            tf = model["TF"]
            tx = model["TX"]
            hces = model["HCES"]
            hcec = model["HCEC"]
            dces = model["DCES"]
            dcec = model["DCEC"]
        else:
            ia = model["IA"]
            ie = model["IE"]
            an = model["AN"]
            aw = model["AW"]
            ca = model["CA"]
            npae = model["NPAE"]
            aces = model["ACES"]
            acec = model["ACEC"]
            eces = model["ECES"]
            ecec = model["ECEC"]
        # R to HD convention
        # pRoll  in Hours
        # pPitch in degrees
        # Apply IJ and ID to incoming coordinates, and if needed GEM correction.
        rRoll = math.radians(pRoll * 15 - ih / 3600.0)
        rPitch = math.radians(pPitch - idec / 3600.0)
        siteLatitude = lat

        if FORK or GEM:
            #"Pier_side" is now "Look East" or "Look West" For a GEM. Given ARO Telescope starts Looking West
            if pPierSide == 'Look West':
                rRoll = math.radians(pRoll * 15 - ih / 3600.0)
                rPitch = math.radians(pPitch - idec / 3600.0)
                ch /= 3600
                np /= 3600
            elif pPierSide == 'Look East':    #Apply differential correction and flip CH, NP terms.
                ch = -ch / 3600.0
                np = -np / 3600.0
                rRoll += math.radians(edh / 3600.0)
                rPitch += math.radians(edd / 3600.0)  # NB Adjust signs to normal EWNS view
            else:
                breakpoint()
                pass
            if loud:
                print(ih, idec, edh, edd, ma, me, ch, np, tf, tx, hces, hcec, dces, dcec, pPierSide)

            # This is exact trigonometrically:
            if loud:
                print("Pre CN; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
            cnRoll = rRoll + math.atan2(
                math.cos(math.radians(np)) * math.tan(math.radians(ch))
                + math.sin(math.radians(np)) * math.sin(rPitch),
                math.cos(rPitch),
            )
            cnPitch = math.asin(
                math.cos(math.radians(np))
                * math.cos(math.radians(ch))
                * math.sin(rPitch)
                - math.sin(math.radians(np)) * math.sin(math.radians(ch))
            )
            if loud:
                print("Post CN; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
            x, y, z = sph_rect_r(cnRoll, cnPitch)
            if loud:
                print("To spherical:  ", x, y, z, x * x + y * y + z * z)
            # Apply MA error:
            y, z = rotate_r(y, z, math.radians(-ma / 3600.0))
            # Apply ME error:
            x, z = rotate_r(x, z, math.radians(-me / 3600.0))
            if loud:
                print("Post ME:       ", x, y, z, x * x + y * y + z * z)
            # Apply latitude
            x, z = rotate_r(x, z, math.radians(90.0 - siteLatitude))
            if loud:
                print("Post-Lat:  ", x, y, z, x * x + y * y + z * z)
            # Apply TF, TX
            az, alt = rect_sph_d(x, y, z)  # math.pi/2. -
            if loud:
                print("Az Alt:  ", az + 180.0, alt)
            # flexure causes mount to sag so a shift in el, apply then
            # move back to other coordinate system
            zen = 90 - alt
            if zen >= 89:
                clampedTz = 57.289961630759144  # tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl = (
                math.radians(tf / 3600.0) * math.sin(math.radians(zen))
                + math.radians(tx / 3600.0) * clampedTz
            )
            alt += defl * RTOD
            if loud:
                print(
                    "Post Tf,Tx; az, alt, z, defl:  ",
                    az + 180.0,
                    alt,
                    z * RTOD,
                    defl * RTOS,
                )
            # The above is dubious but close for small deflections.
            # Unapply Latitude

            x, y, z = sph_rect_d(az,alt)
            x, z = rotate_r(x, z, -math.radians(90.0 - siteLatitude))
            fRoll, fPitch = rect_sph_d(x, y, z)
            cRoll = centration_d(fRoll, -hces, hcec)
            cPitch = centration_d(fPitch, -dces, dcec)
            if loud:
                print("Back:  ", x, y, z, x * x + y * y + z * z)
                print("Back-Lat:  ", x, y, z, x * x + y * y + z * z)
                print("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
                print("f,c Roll: ", fRoll, cRoll)
                print("f, c Pitch: ", fPitch, cPitch)
            corrRoll = reduce_ha_h(cRoll / 15.0)
            corrPitch = reduce_dec_d(cPitch)
            if loud:
                print("Final:   ", fRoll * RTOH, fPitch * RTOD)
            raCorr = reduce_ha_h(corrRoll - pRoll) * 15 * 3600
            decCorr = reduce_dec_d(corrPitch - pPitch) * 3600
            # 20210328  Note this may not work at Pole.
            #if enable:
            #    print("Corrections in asec:  ", raCorr, decCorr)
            return (corrRoll * HTOR, corrPitch * DTOR)
        elif ALTAZ:
            if loud:
                print(
                    ih, idec, ia, ie, an, aw, tf, tx, ca, npae, aces, acec, eces, ecec
                )

            # Convert Incoming Ha, Dec to Alt-Az system, apply corrections then
            # convert back to equitorial. At this stage we assume positioning of
            # the mounting is still done in Ra/Dec coordinates so the canonical
            # velocities are generated by the mounting, not any Python level code.

            loud = False
            az, alt = transform_haDec_to_az_alt(pRoll, pPitch)  #units!!
            # Probably a units problem here.
            rRoll = math.radians(az + ia / 3600.0)
            rPitch = math.radians(alt - ie / 3600.0)
            ch = ca / 3600.0
            np = npae / 3600.0
            # This is exact trigonometrically:

            cnRoll = rRoll + math.atan2(
                math.cos(math.radians(np)) * math.tan(math.radians(ch))
                + math.sin(math.radians(np)) * math.sin(rPitch),
                math.cos(rPitch),
            )
            cnPitch = math.asin(
                math.cos(math.radians(np))
                * math.cos(math.radians(ch))
                * math.sin(rPitch)
                - math.sin(math.radians(np)) * math.sin(math.radians(ch))
            )
            if loud:
                print("Pre CANPAE; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
                print("Post CANPAE; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
            x, y, z = sph_rect_d(math.degrees(cnRoll), math.degrees(cnPitch))

            # Apply AN error:
            y, z = rotate_r(y, z, math.radians(-aw / 3600.0))
            # Apply AW error:
            x, z = rotate_r(x, z, math.radians(an / 3600.0))
            az, el = rect_sph_d(x, y, z)
            if loud:
                print("To spherical:  ", x, y, z, x * x + y * y + z * z)
                print("Pre  AW:       ", x, y, z, math.radians(aw / 3600.0))
                print("Post AW:       ", x, y, z, x * x + y * y + z * z)
                print("Pre  AN:       ", x, y, z, math.radians(an / 3600.0))
                print("Post AN:       ", x, y, z, x * x + y * y + z * z)
                print("Az El:  ", az + 180.0, el)
            # flexure causes mount to sag so a shift in el, apply then
            # move back to other coordinate system
            zen = 90 - el
            if zen >= 89:
                clampedTz = 57.289961630759144  # tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl = (
                math.radians(tf / 3600.0) * math.sin(math.radians(zen))
                + math.radians(tx / 3600.0) * clampedTz
            )
            el += defl * RTOD
            if loud:
                print(
                    "Post Tf,Tx; az, el, z, defl:  ",
                    az + 180.0,
                    el,
                    z * RTOD,
                    defl * RTOS,
                )
            # The above is dubious but close for small deflections.
            # Unapply Latitude

            x, y, z = sph_rect_d(az, el)
            if loud:
                print("Back:  ", x, y, z, x * x + y * y + z * z)
            fRoll, fPitch = rect_sph_d(x, y, z)
            if loud:
                print("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
            cRoll = centration_d(fRoll, aces, acec)
            if loud:
                print("f,c Roll: ", fRoll, cRoll)
            cPitch = centration_d(fPitch, -eces, ecec)
            if loud:
                print("f, c Pitch: ", fPitch, cPitch)
            corrRoll = reduce_az_r(cRoll)
            corrPitch = reduce_alt_r(cPitch)
            if loud:
                print("Final Az, ALT:   ", corrRoll, corrPitch)
            haH, decD = transform_azAlt_to_haDec(corrRoll, corrPitch)   #Units
            raCorr = reduce_ha_h(haH - pRoll) * 15 * 3600
            decCorr = reduce_dec_d(decD - pPitch) * 3600
            if loud:
                print("Corrections:  ", raCorr, decCorr)
            return (haH, decD)

def apply_refraction_inEl_r(pAppEl, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg
    global RefrOn
    # From Astronomical Algorithms.  Max error 0.89" at 0 elev.
    # 20210328 This code does not the right thing if star is below the Pole and is refracted above it.
    breakpoint()
    if not RefrOn:
        return pAppEl, 0.0
    elif pAppEl > 0:
        pAppEl *= RTOD  # Formulas assume elevation in degrees
        ref = (
            1 / math.tan(DTOR * (pAppEl + 7.31 / (pAppEl + 4.4))) + 0.001351521673756295
        )
        ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        obsEl = pAppEl + ref / 60.0
        obsEl *= DTOR
        return reduce_alt_r(obsEl), ref * 60.0
    else:
        ref = 1 / math.tan(DTOR * (7.31 / (pAppEl + 4.4))) + 0.001351521673756295
        ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        obsEl = pAppEl + ref / 60.0
        obsEl *= DTOR
        return reduce_alt_r(obsEl), ref * 60.0


def correct_refraction_inEl_r(pObsEl, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg
    global RefrOn
    if not RefrOn:
        return pObsEl, 0.0
    else:
        ERRORlimit = 0.01 * STOR
        count = 0
        error = 10
        trial = pObsEl
        while abs(error) > ERRORlimit:
            appTrial, ref = apply_refraction_inEl_r(trial, pSiteRefTemp, pSiteRefPress)
            error = appTrial - pObsEl
            trial -= error
            count += 1
            if count > 25:  # count about 12 at-0.5 deg. 3 at 45deg.
                return reduce_dec_r(pObsEl)
        return reduce_dec_r(trial), reduce_dec_r(pObsEl - trial) * RTOD * 3600.0

press = 970 * u.hPa
temp = 10 * u.deg_C
hum = 0.5  # 50%

print("Short utility module loaded at: ", ephem.now(), round((ephem.now()), 4))

if __name__ == "__main__":
   print("Welcome to the new, shorter utility module.")