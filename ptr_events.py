 # -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
#Continuum Analytics Python ver 3.5.2-0.pyEphem __version__ = '3.7.6.0'
#Computer clock is UTC, Windows Time Zone is UTC, no Daylight slaving.
'''
This is also very old code just grafted on. Needs variable renaming, and a good scrub.

'''

from math import *
import shelve
import ephem

from datetime import datetime, timedelta
from math import degrees

#from ptr_config import *
from global_yard import *
#from ptr_utility import *
from astropy.time import Time

#WMD:    #NB these should all come from config
siteLatitude = 34.34293028    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
siteLongitude = -119.68112805 #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
siteElevation = 317.75
siteRefTemp = 15        #These should be a monthly average data.
siteRefPress = 973
SCREENFLATDURATION = 230/1440           #2.4    3h20min rough measure 20170811
BIASDARKDURATION = 300/1440             #5 hours
MORNBIASDARKDURATION = 12/1440          #12 min
LONGESTSCREEN = 5/1440                  #2 min
LONGESTDARK = (800/60)/1440 

# SAF:    
# siteLatitude = 35.554444    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
# siteLongitude = -105.870278 #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
# siteElevation = 2187
# siteRefTemp = 10.0         #These should be a monthly average data.
# siteRefPress = 784.0
# SCREENFLATDURATION = 230/1440           #2.4    3h20min rough measure 20170811
# BIASDARKDURATION = 300/1440             #5 hours
# MORNBIASDARKDURATION = 12/1440          #12 min
# LONGESTSCREEN = 5/1440                  #2 min
# LONGESTDARK = (800/60)/1440             #13.33 min

DAY_Directory = None
Day_tomorrow = None
dayNow = None

def reduceHa(pHa):
    while pHa <= -12:
        pHa += 24.0
    while pHa > 12:
        pHa -= 24.0
    return pHa



def getJulianDateTime():
    global jYear,JD, MJD, unixEpochOf, localEpoch
    e = Time(datetime.now().isoformat())
    unixEpochOf = time.time()
    jYear = 'J'+str(round(e.jyear, 3))
    JD = e.jd
    MJD =e.mjd
    localEpoch = datetime.now()#.isoformat()


def illumination(sunRa, sunDec, sunElev, sunDia, moonRa, moonDec, moonElev, moonDia):
    '''
    Returns illumination on a flat surface in lux. (lumens/m^2. Visual 555nm
    centered light distribution.)      From Supplement to Astro. Almanac,
    Seidelman et al.
    This routine is good to 0.01 lux.  Note low end star and skyglow is
    approximate.

    History
    2011/03/04    WER    First coded.
                         A real test routine should be added.
    2011/10/18    WER    Cleaned up for inclusion in pubSub
    20120911      WER    Clean up more decimal trig. Note Lunar diameter not included.
    '''

    #Enter above with  sunDia, moonDia in degrees., rest are radians
    #sunElev = degrees(sunElev)
    #lmoonElev = degrees(moonElev)

    if sunElev >= -18:
        if sunElev >= 20:
            il = (3.74, 3.97, -4.07, 1.47)
        elif sunElev >= 5:
            il = (3.05, 13.28, -45.98, 64.33)
        elif sunElev >= -0.8:
            il = (2.88, 22.26, -207.64, 1034.3)
        elif sunElev >= -5:
            il = (2.88, 21.81, -258.11, -858.36)
        elif sunElev >= -12:
            il = (2.7, 12.17, -431.69, -1899.93)
        else:
            il = (13.84, 262.72, 1447.42, 2797.93)
        x = sunElev / 90.
        i =  10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) + \
                  2 * log10(sunDia/0.50664))
    else:
        i = 0
    if i < 0: i =0
    f=0
    if moonElev >= -0.8:
        if moonElev >= 20:
            il = (-1.95, 4.06, -4.24, 1.56)
        elif moonElev >= 5:
            il = (-2.58, 12.58, -42.58, 59.06)
        else:
            il = (-2.79, 24.27, -252.95, 1321.29)
        x = moonElev / 90
        raDist = radians(reduceHa(degrees(moonRa - sunRa)))
        e = degrees(acos(sin(sunDec) * sin(moonDec) + cos(sunDec) * \
                         cos(moonDec) * cos(raDist)))
        f = 180 - e
        if f > 180:
            f = 180
        if f < 0:
            f = 0
        j =  10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) + \
                  (-0.00868 * f - 0.0000000022 * (f ** 4))) + \
                  2*log10(moonDia/0.951)    #This should be ckecked - moon dia
    else:
        j = 0
    if j < 0: j = 0
    #sunIllum = i
    #moonIllum = j
    illuminance= i + j + 0.002
    #   0.002 = stars and galaxy -- averaged; rest is Airglow,
    #   2e-3 lux is brightness of stars + airglow. Ratio is relative to that number.
    skyBrightRatio = illuminance/0.002
    if skyBrightRatio < 1: skyBrightRatio = 1
    skyMag = 22-2.5*log10(skyBrightRatio)
    return illuminance,  skyMag  #Units are lux, dimensionless ratio, approx mag/sq-asec
    #
def flat_spot_now(go=False):
    ra, dec, sun_alt, sun_az, *other = sunNow()
    print('Sun:  ', sun_alt, sun_az)
    sun_az2 = sun_az - 180.
    if sun_az2 < 0:
        sun_az2 += 360.
    sun_alt2 = sun_alt + 105
    if sun_alt2 > 90:
        sun_alt2 = 180 - sun_alt2
    elif sun_alt2 <=90:
        sun_az2 = sun_az
    if go:
        g_dev['mnt'].mount.SlewToAltAzAsync(sun_az2, sun_alt2)

    return(sun_alt2, sun_az2)


def sunNow():
    sun = ephem.Sun()
    sun.compute()
    moon = ephem.Moon()
    moon.compute()
    #if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
    ptr = ephem.Observer()     #Photon Ranch
    ptr.lat = str(siteLatitude)
    ptr.lon = str(siteLongitude)
    ptr.elev = siteElevation
    ptr.compute_pressure()
    ptr.temp = siteRefTemp

    sun.compute(ptr)
    #if loud: print('Sun Now: ', sun.ra, sun.dec, sun.az, sun.alt, ptr.date)
    moon.compute(ptr)
    # if loud: print('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)

    return sun.ra, sun.dec, degrees(sun.alt), degrees(sun.az), moon.ra, moon.dec,\
           degrees(moon.alt), moon.size/3600

def illuminationNow():

    sunRa, sunDec, sunElev, sunAz, moonRa, moonDec, moonElev, moonDia \
    = sunNow()
    illuminance, skyMag = illumination(sunRa, sunDec, sunElev, 0.5, \
                                       moonRa, moonDec, moonElev, moonDia)
    return round(illuminance, 3), round(skyMag ,2)
    #if loud: print('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)

def calcEveFlatValues(pWhen, loud=False, now_spot=False):
    ptr.date = pWhen
    sun.compute(ptr)
    if loud: print('Sunset, sidtime:  ', pWhen, ptr.sidereal_time())
    if loud: print('Eve Open  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
    SunAz1 = degrees(sun.az) - 180
    if SunAz1 < 0: SunAz1 += 360
    liftAlt = (degrees(sun.alt) + 105)
    if liftAlt <= 90:
        SunAlt1 = liftAlt
    else:
        SunAlt1 = 180 - liftAlt
    if loud: print('Flat spot at:  ', SunAz1, SunAlt1)
    FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
    if loud: print('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
    ptr.date = skyFlatEnd
    sun.compute(ptr)
    if loud: print('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)#SunRa = float(sun.ra)
    SunAz2 = degrees(sun.az) - 180
    SunAlt2 =  degrees(sun.alt) + 105
    if SunAlt2 > 90.:
        SunAlt2 = 180 - degrees(sun.alt) + 105
    if loud: print('Flatspot:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
    FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
    if loud: print('Eve Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
    span = 86400*(skyFlatEnd - pWhen)
    if loud: print('Duration:  ', str(round(span/60, 2)) +   'min')
    RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
    DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
    if loud: print('Eve Rates:  ', RaDot, DecDot)
    if now_spot:
        if loud: print(type(FlatStartRa))
        if loud: print('ReturningRa/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        return  degrees(FlatStartRa)/15, degrees(FlatStartDec)
    else:
        return (degrees(FlatStartRa)/15, degrees(FlatStartDec), \
        degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

def calcMornFlatValues(pWhen, loud=False):
    ptr.date = pWhen
    sun.compute(ptr)
    if loud: print()
    if loud: print('Morn Flat Start, sidtime:  ', pWhen, ptr.sidereal_time())
    if loud: print('Morn Flat Start Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
    SunAz1 = degrees(sun.az) + 180
    SunAlt1 = (degrees(sun.alt) + 105)
    if SunAlt1 > 90.:
        SunAlt1 = 180 -(degrees(sun.alt) + 105)
    print('Flat spot at:  ', SunAz1, SunAlt1)
    FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
    print('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
    ptr.date = sunZ88Cl
    sun.compute(ptr)
    if loud: print('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)#SunRa = float(sun.ra)
    SunAz2 = degrees(sun.az) + 180
    SunAlt2 = 180 -(degrees(sun.alt) + 105)
    if loud: print('Flatspot:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
    FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
    print('Morn Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
    span = 86400*(sunrise - pWhen)
    print('Duration:  ', str(round(span/60, 2)) +   'min')
    RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
    DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
    print('Morn Rates:  ', RaDot, DecDot)
    return (degrees(FlatStartRa)/15, degrees(FlatStartDec), \
            degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

#NBNBNB Convert this to skyfield!
print('Events module loaded at: ', ephem.now(), round((ephem.now()), 4))
loud = True

'''
Mantatory:  The day_directory is the datestring for the Julian day as defined
by the local astronomical Noon.  Restating the software any time within that
24 hour period resultin in the Same day_directory.    Site restarts may occur
at any time but automatic ones will normally occur somewhat after the prior
night's  final reductions and the upcoming local Noon.

'''

def compute_day_directory(loud=False):
    global DAY_Directory, dayNow, Day_tomorrow
    intDay = int(ephem.now())
    dayFrac = ephem.now() - intDay
    if dayFrac < 0.20833:
        dayNow = intDay - 0.55
    else:
        dayNow = intDay + 0.45
    ephem.date = ephem.Date(dayNow)
    ephem.tomorrow = ephem.Date(dayNow + 1)
    dayStr = str(ephem.date).split()[0]
    dayStr = dayStr.split('/')
    #print('Day String', dayStr)
    if len(dayStr[1]) == 1:
        dayStr[1] = '0' + dayStr[1]
    if len(dayStr[2]) == 1:
        dayStr[2] = '0' + dayStr[2]
    #print('Day String', dayStr)
    DAY_Directory = dayStr[0] + dayStr[1] + dayStr[2]
    if loud: print('DaDIR:  ', DAY_Directory)

    dayStr = str(ephem.tomorrow).split()[0]
    dayStr = dayStr.split('/')
    #print('Day String', dayStr)
    if len(dayStr[1]) == 1:
        dayStr[1] = '0' + dayStr[1]
    if len(dayStr[2]) == 1:
        dayStr[2] = '0' + dayStr[2]
    #print('Day String', dayStr)
    Day_tomorrow = dayStr[0] + dayStr[1] + dayStr[2]
    if loud: print('DaDIR:  ', DAY_Directory)

    return DAY_Directory

compute_day_directory()

sun = ephem.Sun()
#sun.compute(dayNow)
moon = ephem.Moon()
#moon.compute(dayNow)
#if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
ptr = ephem.Observer()     #Photon Ranch
ptr.date = dayNow
ptr.lat = str(siteLatitude)
ptr.lon = str(siteLongitude)
ptr.elev = siteElevation
ptr.compute_pressure()
ptr.temp = siteRefTemp
ptr.horizon = '-0:34'
sunset = ptr.next_setting(sun)
middleNight = ptr.next_antitransit(sun)
sunrise = ptr.next_rising(sun)
ptr.horizon = '2'
sun.compute(ptr)
#if loud: print('Sun 2: ', sun.ra, sun.dec, sun.az, sun.alt)
sunZ88Op = ptr.next_setting(sun)
sunZ88Cl = ptr.next_rising(sun)
ptr.horizon = '-6'
sun.compute(ptr)
#if loud: print('Sun -6: ', sun.ra, sun.dec, sun.az, sun.alt)
civilDusk = ptr.next_setting(sun)
civilDawn = ptr.next_rising(sun)
ptr.horizon = '-10'
sun.compute(ptr)
#if loud: print('Sun -14.9: ', sun.ra, sun.dec, sun.az, sun.alt)
skyFlatEnd = ptr.next_setting(sun)
skyFlatBegin = ptr.next_rising(sun)
ptr.horizon = '-12'
sun.compute(ptr)
#if loud: print('Sun -12: ', sun.ra, sun.dec, sun.az, sun.alt)
nauticalDusk = ptr.next_setting(sun)
nauticalDawn = ptr.next_rising(sun)

ptr.horizon = '-18'
sun.compute(ptr)
#if loud: print('Sun -18: ', sun.ra, sun.dec, sun.az, sun.alt)
#if loud: print('Dark: ', sun.az, sun.alt)
astroDark = ptr.next_setting(sun)
astroEnd = ptr.next_rising(sun)
duration = (astroEnd - astroDark)*24
ptr.date = middleNight
moon.compute(ptr)
sun=ephem.Sun()
sun.compute(ptr)
#if loud: print('Middle night  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
if loud: print('Middle night Moon:  ', moon.ra, moon.dec)#, moon.az, moon.alt)
mid_moon_ra = moon.ra
mid_moon_dec = moon.dec
mid_moon_phase = moon.phase

eveFlatStartRa, eveFlatStartDec, eveFlatEndRa, eveFlatEndDec, \
                eveRaDot, eveDecDot =  calcEveFlatValues(sunZ88Op, loud=True)

mornFlatStartRa, mornFlatStartDec, mornFlatEndRa, mornFlatEndDec, \
                mornRaDot, mornDecDot =  calcMornFlatValues(skyFlatBegin, \
                loud=True)

endEveScreenFlats = sunZ88Op  - LONGESTSCREEN
beginEveScreenFlats = endEveScreenFlats - SCREENFLATDURATION
endEveBiasDark = beginEveScreenFlats - LONGESTDARK
beginEveBiasDark = endEveBiasDark - BIASDARKDURATION

#Morning times queue off on when flats are no longer
#gatherable,  A close is then issued, then after closing,
#morning screen flats begin, followed by bias dark and then
#morning reductions.  So the times below are the latest case.

beginMornScreenFlats = sunZ88Cl + 2/1440
endMornScreenFlats = beginMornScreenFlats + SCREENFLATDURATION
beginMornBiasDark = endMornScreenFlats + LONGESTSCREEN
endMornBiasDark = beginMornBiasDark + MORNBIASDARKDURATION
beginReductions =  endMornBiasDark + LONGESTDARK

try:

    obsShelf = shelve.open('Q:\\ptr_night_shelf\\site')

    obsShelf['DayDir'] = DAY_Directory
    obsShelf['EphemDate'] = dayNow
    obsShelf['EveSun'] = (eveSunRa, eveSunDec, eveSunAz1, eveSunAlt1)
    obsShelf['EveSunRa/Dec'] = (float(sun.ra), float(sun.dec))
    obsShelf['MornSun'] = (mornSunRa ,mornSunDec, mornSunAz1, mornSunAlt1)
    obsShelf['Duration'] = round(duration, 2)
    obsShelf['MoonRa/Dec'] = (float(moon.ra), float(moon.dec))
    obsShelf['MoonPhase'] = float(moonPhase)

    obsShelf.close()
except:
    pass
finally:
    pass


def sunPhaseAngle(offsetHrs=0.0):
    dayNow = ephem.now()
    ptr = ephem.Observer()     #Photon Ranch
    ptr.lat = str(siteLatitude)
    ptr.lon = str(siteLongitude)
    ptr.elev = siteElevation
    ptr.compute_pressure()
    ptr.temp = siteRefTemp
    ptr.date = ephem.Date(dayNow + offsetHrs*ephem.hour)
    sun = ephem.Sun()
    sun.compute(ptr)
    moon = ephem.Moon()
    moon.compute(ptr)
    saz = reduceAz(degrees(sun.az) + 180)
    sal = degrees(sun.alt)
    if sal > 0.5:
        saz = 0
        #NBNBNB this needs to be improved to implement sun earth eclipse shadow.
    maz = degrees(moon.az)
    mal = degrees(moon.alt)

    if loud: print('Sun Now: ', saz, degrees(sun.alt))
    moon.compute(ptr)
    if loud: print('Moon Now: ', degrees(moon.az), degrees(moon.alt))
    return round(saz, 2)

print('Events module reporting for duty. \n')

print('Ephem date    :    ', dayNow)
print('DayDir        :    ', DAY_Directory)
print('Next day      :    ', Day_tomorrow)
print('Night Duration :    ', str(round(duration, 2)) + ' hr')
print('MoonRaDec     :    ', (round(mid_moon_ra, 2), round(mid_moon_dec , 1)))
print('Moon phase %  :    ', round(mid_moon_phase, 1))
print(('\n'))


evnt = [('Beg Bias Dark :    ', ephem.Date(beginEveBiasDark)),
        ('End Bias Dark :    ', ephem.Date(endEveBiasDark)),
        ('Beg Scrn Flats:    ', ephem.Date(beginEveScreenFlats)),
        ('End Scrn Flats:    ', ephem.Date(endEveScreenFlats)),
        ('SunZ88 Opening:    ', sunZ88Op),
        ('Beg Sky Flats :    ', sunZ88Op),
        ('Sun   next_set:    ', sunset),
        ('Civil  Dusk   :    ', civilDusk),
        ('Naut   Dusk   :    ', nauticalDusk),
        ('Flat End      :    ', skyFlatEnd),
        ('Astro  Dark   :    ', astroDark),
        ('Middle Night  :    ', middleNight),
        ('Astro  End    :    ', astroEnd),
        ('Flat Start    :    ', skyFlatBegin),
        ('Naut   Dawn   :    ', nauticalDawn),
        ('Civil  Dawn   :    ', civilDawn),
        ('Sun  next_rise:    ', sunrise),
        ('SunZ88   Close:    ', sunZ88Cl),
        ('Moon rise:         ', ptr.previous_rising(moon)),
        ('Moon transit  :    ', ptr.previous_transit(moon)),
        ('Moon set      :    ', ptr.previous_setting(moon)),
        ('Moon rise     :    ', ptr.next_rising(moon)),
        ('Moon transit  :    ', ptr.next_transit(moon)),
        ('Moon rise     :    ', ptr.next_setting(moon))]

# Function to sort the list by second item of tuple
def Sort_Tuple(tup):

    # reverse = None (Sorts in Ascending order)
    # key is set to sort using second element of
    # sublist lambda has been used
    return(sorted(tup, key = lambda x: x[1]))

evnt_sort = Sort_Tuple(evnt)
#Edit out rise and sets prior to or after operations.
while evnt_sort[0][0] != 'Beg Bias Dark :    ':
    evnt_sort.pop(0)
while evnt_sort[-1][0] != 'SunZ88   Close:    ':
    evnt_sort.pop(-1)
for evnt in evnt_sort:
    print(evnt[0], evnt[1])
##Early start check needs to be added!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

'''
Landolt "bonus fields"
RA J2000	DE J2000	N    Star Field

00 54 41 +00 45 00 4 L010
02 23 38 +13 27 38 3 L020 PG0220+132
02 33 41 +05 18 40 6 L030 PG0231+051
03 54 38 +00 28 00 3 L040
06 52 20 -00 20 00 9 L070
07 24 15 -00 32 55 8 L075 RU 149
07 29 55 -02 06 18 7 L080 RU 152
09 21 28 +02 46 03 5 L090 PG0918+029
09 45 12 -03 09 24 5 L095 PG0942-029
09 56 40 -00 24 53 4 L100
10 50 03 -00 00 32 4 L110 PG1047+003
12 42 22 -00 40 00 4 L120
13 25 39 -08 49 16 5 L130 PG1323-086
15 28 11 -07 16 27 5 L140 PG1525-071
15 30 50 +06 00 56 4 L150 PG1528+062
15 33 11 +05 32 27 3 L155 PG1530+057
15 38 48 -00 21 45 4 L160 107 457+
16 35 24 +09 47 50 5 L165 PG1633+099
16 59 32 +07 43 31 4 L170 PG1657+078
17 44 15 -00 02 25 3 L180 109 954+
18 42 10 +00 20 30 8 L190 110 504+
19 37 37 +00 26 00 3 L200
20 43 59 -10 47 42 4 L210 MARK A
21 40 57 +00 27 00 2 L215
22 16 28 -00 21 15 4 L220 PG2213-006
23 33 44 +05 46 36 3 L230 PG2331+055
23 38 44 +00 42 55 3 L235 PG2336+004
'''

if __name__ == '__main__':

    print('Ephem date    :    ', dayNow)
    print('DayDir        :    ', DAY_Directory)
    print('Night Duration :    ', str(round(duration, 2)) + ' hr')
    print('MoonRaDec     :    ', (round(mid_moon_ra, 2), round(mid_moon_dec , 1)))
    print('Moon phase %  :    ', round(mid_moon_phase, 1))
    print(('\n'))

    evnt = [('Beg Bias Dark :    ', ephem.Date(beginEveBiasDark)),
            ('End Bias Dark :    ', ephem.Date(endEveBiasDark)),
            ('Beg Scrn Flats:    ', ephem.Date(beginEveScreenFlats)),
            ('End Scrn Flats:    ', ephem.Date(endEveScreenFlats)),
            ('SunZ88 Opening:    ', sunZ88Op),
            ('Beg Sky Flats :    ', sunZ88Op),
            ('Sun   next_set:    ', sunset),
            ('Civil  Dusk   :    ', civilDusk),
            ('Naut   Dusk   :    ', nauticalDusk),
            ('Flat End      :    ', skyFlatEnd),
            ('Astro  Dark   :    ', astroDark),
            ('Middle Night  :    ', middleNight),
            ('Astro  End    :    ', astroEnd),
            ('Flat Start    :    ', skyFlatBegin),
            ('Naut   Dawn   :    ', nauticalDawn),
            ('Civil  Dawn   :    ', civilDawn),
            ('Sun  next_rise:    ', sunrise),
            ('SunZ88   Close:    ', sunZ88Cl),
            ('Moon rise:         ', ptr.previous_rising(moon)),
            ('Moon transit  :    ', ptr.previous_transit(moon)),
            ('Moon set      :    ', ptr.previous_setting(moon)),
            ('Moon rise     :    ', ptr.next_rising(moon)),
            ('Moon transit  :    ', ptr.next_transit(moon)),
            ('Moon rise     :    ', ptr.next_setting(moon))]

    # # Function to sort the list by second item of tuple
    # def Sort_Tuple(tup):

    #     # reverse = None (Sorts in Ascending order)
    #     # key is set to sort using second element of
    #     # sublist lambda has been used
    #     return(sorted(tup, key = lambda x: x[1]))

    # evnt_sort = Sort_Tuple(evnt)
    # #Edit out rise and sets prior to or after operations.
    # while evnt_sort[0][0] != 'Beg Bias Dark :    ':
    #     evnt_sort.pop(0)
    # while evnt_sort[-1][0] != 'SunZ88   Close:    ':
    #     evnt_sort.pop(-1)
    # for evnt in evnt_sort:
    #     print(evnt[0], evnt[1])








