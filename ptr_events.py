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
#import shelve
import ephem
from datetime import datetime
import time
#import pytz
from math import degrees
# import skyfield 
# from skyfield import api, almanac
# from skyfield.nutationlib import iau2000b
# print('ObsImports:  ', config, '\n\'', config.site_config['site'])
from global_yard import *
from astropy.time import Time
from pprint import pprint

# NB Change these to hours not fractions of a day.  Should come from site config not be in code here.
SCREENFLATDURATION = 90/1440            #1.5 hours
BIASDARKDURATION = 180/1440             #3 hours
MORNBIASDARKDURATION = 90/1440          #1.5 min
LONGESTSCREEN = (75/60)/1440            #1 min
LONGESTDARK = (385/60)/1440             #6 min

DAY_Directory = None   #NB this is an evil use of Globals by WER.  20200408   WER
Day_tomorrow = None
dayNow = None

class Events:

    def __init__(self, config: dict):
        self.config = config
        g_dev['evnt'] = self
        self.siteLatitude = round(float(self.config['latitude']), 8)    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
        self.siteLongitude = round(float(self.config['longitude']), 8) #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
        self.siteElevation =  round(float(self.config['elevation']), 3)
        self.siteRefTemp =  round(float(self.config['reference_ambient'][0]), 2)       #These should be a monthly average data.
        self.siteRefPress =  round(float(self.config['reference_pressure'][0]), 2)

    ###############################
    ###    Internal Methods    ####
    ###############################

    def _sortTuple(self, tup):
        ''' Function to sort the list by second item of tuple '''
        # reverse = None (Sorts in Ascending order)
        # key is set to sort using second element of
        # sublist lambda has been used
        return(sorted(tup, key = lambda x: x[1]))

    def _reduceHa(self, pHa):
        while pHa <= -12:
            pHa += 24.0
        while pHa > 12:
            pHa -= 24.0
        return pHa

    def _getJulianDateTime(self):
        global jYear,JD, MJD, unixEpochOf, localEpoch
        e = Time(datetime.now().isoformat())
        unixEpochOf = time.time()
        jYear = 'J'+str(round(e.jyear, 3))
        JD = e.jd
        MJD =e.mjd
        localEpoch = datetime.now()#.isoformat()

    def _illumination(self, sunRa, sunDec, sunElev, sunDia, moonRa, moonDec, moonElev, moonDia):
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
            raDist = radians(self._reduceHa(degrees(moonRa - sunRa)))
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
        return illuminance,  skyMag   #  #Units are lux, dimensionless ratio, approx mag/sq-asec

    def _sunNow(self):
        sun = ephem.Sun()
        sun.compute()
        moon = ephem.Moon()
        moon.compute()
        #if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()     #Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        sun.compute(ptr)
        #if loud: print('Sun Now: ', sun.ra, sun.dec, sun.az, sun.alt, ptr.date)
        moon.compute(ptr)
        # if loud: print('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)
        return sun.ra, sun.dec, degrees(sun.alt), degrees(sun.az), moon.ra, moon.dec,\
            degrees(moon.alt), moon.size/3600

    def sun_az_now(self):
        sun = ephem.Sun()
        sun.compute()
        moon = ephem.Moon()
        moon.compute()
        #if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()     #Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        sun.compute(ptr)
        #if loud: print('Sun Now: ', sun.ra, sun.dec, sun.az, sun.alt, ptr.date)
        moon.compute(ptr)
        # if loud: print('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)
        return  degrees(sun.az)

    def _calcEveFlatValues(self, ptr, sun, pWhen, skyFlatEnd, loud=False, now_spot=False):
        # NB This needs to deal with the Moon being too close!
        ptr.date = pWhen
        sun.compute(ptr)
        if loud: print('Sunset, sidtime:  ', pWhen, ptr.sidereal_time())
        if loud: print('Eve Open  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) - 180
        while  SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        if loud: print('Flat spot at az alt:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        if loud: print('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = skyFlatEnd
        sun.compute(ptr)
        if loud: print('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)#SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)   
        if loud: print('Flatspots:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
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

    def _calcMornFlatValues(self, ptr, sun, pWhen,  sunrise, loud=False):
        ptr.date = pWhen
        sun.compute(ptr)
        if loud: print()
        if loud: print('Morn Flat Start, sidtime:  ', pWhen, ptr.sidereal_time())
        if loud: print('Morn Flat Start Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) + 180
        while SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90.:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        print('Flat spot at:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        print('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = sunrise
        sun.compute(ptr)
        if loud: print('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)#SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)
        if loud: print('Flatspot:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
        FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
        print('Morn Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
        span = 86400*(sunrise - pWhen)
        print('Duration:  ', str(round(span/60, 2)) +   'min')
        RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
        DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
        print('Morn Rates:  ', RaDot, DecDot, '\n')
        return (degrees(FlatStartRa)/15, degrees(FlatStartDec), \
                degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

    def _sunPhaseAngle(self, offsetHrs=0.0):
        dayNow = ephem.now()
        ptr = ephem.Observer()     #Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
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

    #############################
    ###     Public Methods   ####
    #############################

    def getSunEvents(self):
        '''
        This is used in the enclosure module to determine if is a good time
        of day to open.  THIS CODE IS EVIL, it duplicates another computation and can be a source
        of divergent values.
        '''
        sun = ephem.Sun()
        #sun.compute(dayNow)
        moon = ephem.Moon()
        #moon.compute(dayNow)
        #if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()     #Photon Ranch
        ptr.date = dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        ptr.horizon = '-0:34'
        sunset = ptr.next_setting(sun)
        middleNight = ptr.next_antitransit(sun)
        sunrise = ptr.next_rising(sun)
        ops_win_begin = sunset - 89/1440
        return (ops_win_begin, sunset, sunrise, ephem.now())

    def flat_spot_now(self):
        '''
        Return a tuple with the (alt, az) of the flattest part of the sky.
        '''
        ra, dec, sun_alt, sun_az, *other = self._sunNow()
        print('Sun:  ', sun_az, sun_alt)
        sun_az2 = sun_az - 180.   #  Opposite az of the Sun
        if sun_az2 < 0:
            sun_az2 += 360.
        sun_alt2 = sun_alt + 105   #105 degrees along great circle through zenith
        if sun_alt2 > 90:   # Over the zenith so specify alt at above azimuth
            sun_alt2 = 180 - sun_alt2
        else:
            sun_az2 = sun_az  # The sun is >15 degrees below horizon, use its az

        return(sun_az2, sun_alt2)

    def illuminationNow(self):

        sunRa, sunDec, sunElev, sunAz, moonRa, moonDec, moonElev, moonDia \
        = self._sunNow()
        illuminance, skyMag = self._illumination(sunRa, sunDec, sunElev, 0.5, \
                                        moonRa, moonDec, moonElev, moonDia)
        return round(illuminance, 3), round(skyMag ,2)
        #if loud: print('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)

    def compute_day_directory(self, loud=False):
        # NBNBNB Convert this to skyfield!
        '''
        Mandatory:  The day_directory is the datestring for the Julian day as defined
        by the local astronomical Noon.  Restating the software any time within that
        24 hour period resultin in the Same day_directory.    Site restarts may occur
        at any time but automatic ones will normally occur somewhat after the prior
        night's  final reductions and the upcoming local Noon.

        '''
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
        day_str = dayStr
        #print('Day String', dayStr)
        if len(dayStr[1]) == 1:
            dayStr[1] = '0' + dayStr[1]
        if len(dayStr[2]) == 1:
            dayStr[2] = '0' + dayStr[2]
        #print('Day String', dayStr)
        DAY_Directory = dayStr[0] + dayStr[1] + dayStr[2]
        day_str = DAY_Directory
        g_dev['day'] = DAY_Directory
        g_dev['d-a-y'] = f"{day_str[0:4]}-{day_str[4:6]}-{day_str[6:]}"
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
        next_day = Day_tomorrow
        g_dev['next_day'] = f"{next_day[0:4]}-{next_day[4:6]}-{next_day[6:]}"
        if loud: print('DaDIR:  ', DAY_Directory)
        print('\nNext Day is:  ', g_dev['next_day'])
        print('Now is:  ', ephem.now(), g_dev['d-a-y'])

        return DAY_Directory

    def display_events(self):   # Routine above needs to be called first.
        global dayNow
        # print('Events module loaded at: ', ephem.now(), round((ephem.now()), 4))
        loud = True
        sun = ephem.Sun()
        #sun.compute(dayNow)
        moon = ephem.Moon()
        #moon.compute(dayNow)
        #if loud: print('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()     #Photon Ranch
        ptr.date = dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        ptr.horizon = '-0:34'
        sunset = ptr.next_setting(sun)
        middleNight = ptr.next_antitransit(sun)
        sunrise = ptr.next_rising(sun)
        next_moonrise = ptr.next_rising(moon)
        next_moontransit = ptr.next_transit(moon)
        next_moonset = ptr.next_setting(moon)
        last_moonrise = ptr.previous_rising(moon)
        last_moontransit = ptr.previous_transit(moon)
        last_moonset = ptr.previous_setting(moon)
        ptr.horizon = '2'
        sun.compute(ptr)
        #if loud: print('Sun 2: ', sun.ra, sun.dec, sun.az, sun.alt)
        ops_win_begin = sunset - 89/1440      # Needs to come from site config  NB 1 hour
        ptr.horizon = '-1.5'
        sun.compute(ptr)
        #if loud: print('Sun -6: ', sun.ra, sun.dec, sun.az, sun.alt)
        eve_skyFlatBegin = sunset - 60/1440. #ptr.next_setting(sun)
        morn_skyFlatEnd = ptr.next_rising(sun)
        ptr.horizon = '-6'
        sun.compute(ptr)
        #if loud: print('Sun -6: ', sun.ra, sun.dec, sun.az, sun.alt)
        civilDusk = ptr.next_setting(sun)
        civilDawn = ptr.next_rising(sun)
        ptr.horizon = '-11.75'
        sun.compute(ptr)
        #if loud: print('Sun -14.9: ', sun.ra, sun.dec, sun.az, sun.alt)
        eve_skyFlatEnd = ptr.next_setting(sun)
        morn_skyFlatBegin = ptr.next_rising(sun)
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
        eveRaDot, eveDecDot = self._calcEveFlatValues(ptr, sun, ops_win_begin, eve_skyFlatEnd, loud=True)
        mornFlatStartRa, mornFlatStartDec, mornFlatEndRa, mornFlatEndDec, mornRaDot, \
                        mornDecDot = self._calcMornFlatValues(ptr, sun, morn_skyFlatBegin, \
                                                        sunrise, loud=True)
        endEveScreenFlats = ops_win_begin - LONGESTSCREEN
        beginEveScreenFlats = endEveScreenFlats - SCREENFLATDURATION
        endEveBiasDark = beginEveScreenFlats - LONGESTDARK
        beginEveBiasDark = endEveBiasDark - BIASDARKDURATION

        # Morning times queue off on when flats are no longer
        # gatherable,  A close is then issued, then after closing,
        # morning screen flats begin, followed by bias dark and then
        # morning reductions.  So the times below are the latest case.

        beginMornScreenFlats = sunrise + 4/1440    #  4 min allowed for close up.
        endMornScreenFlats = beginMornScreenFlats + SCREENFLATDURATION
        beginMornBiasDark = endMornScreenFlats + LONGESTSCREEN
        endMornBiasDark = beginMornBiasDark + MORNBIASDARKDURATION
        beginReductions = endMornBiasDark + LONGESTDARK

        # try:
        #     # WMD specific and apparently unused.
        #     obsShelf = shelve.open('Q:\\ptr_night_shelf\\site')
        #     obsShelf['DayDir'] = DAY_Directory
        #     obsShelf['EphemDate'] = dayNow
        #     obsShelf['EveSun'] = (eveSunRa, eveSunDec, eveSunAz1, eveSunAlt1)
        #     obsShelf['EveSunRa/Dec'] = (float(sun.ra), float(sun.dec))
        #     obsShelf['MornSun'] = (mornSunRa ,mornSunDec, mornSunAz1, mornSunAlt1)
        #     obsShelf['Duration'] = round(duration, 2)
        #     obsShelf['MoonRa/Dec'] = (float(moon.ra), float(moon.dec))
        #     obsShelf['MoonPhase'] = float(moonPhase)
        #     obsShelf.close()
        # except:
        #     pass
        # finally:
        #     pass

        #  NB NB Should add sit time to this report.
        print('Events module reporting for duty. \n')
        print('Ephem date     :    ', dayNow)
        print("Julian Day     :    ")
        print("MJD            :    ")
        print('Day_Directory  :    ', DAY_Directory)
        print('Next day       :    ', Day_tomorrow)
        print('Night Duration :    ', str(round(duration, 2)) + ' hr')
        print('Moon Ra; Dec   :    ', round(mid_moon_ra, 2), ";  ", round(mid_moon_dec, 1))
        print('Moon phase %   :    ', round(mid_moon_phase, 1), '%\n')
        print("Key events for the evening, presented by the Solar System: \n")
        evnt = [('Eve Bias Dark      ', ephem.Date(beginEveBiasDark)),
                ('End Eve Bias Dark  ', ephem.Date(endEveBiasDark)),
                ('Eve Scrn Flats     ', ephem.Date(beginEveScreenFlats)),
                ('End Eve Scrn Flats ', ephem.Date(endEveScreenFlats)),
                ('Ops Window Start   ', ephem.Date(ops_win_begin)),  #Enclosure may open.
                ('Cool Down, Open    ', ephem.Date(ops_win_begin + 0.5/1440)),
                ('Eve Sky Flats      ', ephem.Date(eve_skyFlatBegin)),
                ('Sun Set            ', sunset),
                ('Civil Dusk         ', civilDusk),
                ('End Eve Sky Flats  ', eve_skyFlatEnd),
                ('Clock & Auto Focus ', ephem.Date(eve_skyFlatEnd + 1/1440.)),
                ('Naut Dusk          ', nauticalDusk),
                ('Observing Begins   ', ephem.Date(nauticalDusk + 5/1440.)),
                ('Astro Dark         ', astroDark),
                ('Middle of Night    ', middleNight),
                ('End Astro Dark     ', astroEnd),
                ('Observing Ends     ', ephem.Date(nauticalDawn - 5/1440.)),
                ('Final Clock & AF   ', ephem.Date(nauticalDawn - 4/1440.)),
                ('Naut Dawn          ', nauticalDawn),
                ('Morn Sky Flats     ', morn_skyFlatBegin),
                ('Civil Dawn         ', civilDawn),
                ('End Morn Sky Flats ', morn_skyFlatEnd),
                ('Ops Window Closes  ', ephem.Date(morn_skyFlatEnd + 0.5/1440)),   #Enclosure must close
                ('Sun Rise           ', sunrise),
                ('Prior Moon Rise    ', last_moonrise),
                ('Prior Moon Transit ', last_moontransit),
                ('Prior Moon Set     ', last_moonset),
                ('Moon Rise          ', next_moonrise),
                ('Moon Transit       ', next_moontransit),
                ('Moon Set           ', next_moonset)]

        #print("No report of post-close events is available yet. \n\n")
        evnt_sort = self._sortTuple(evnt)
        day_dir = self.compute_day_directory()
        #Edit out rise and sets prior to or after operations.
        while evnt_sort[0][0] != 'Eve Bias Dark      ':
            evnt_sort.pop(0)
        # while evnt_sort[-1][0] != 'Morn Sun >2 deg':  # Ditto, see above.
        #     evnt_sort.pop(-1)

        while evnt_sort[-1][0] in ['Moon Rise          ', 'Moon Transit       ', ]:
             evnt_sort.pop(-1)
        evnt_sort
        timezone = "  " + self.config['timezone'] + ": "
        offset = self.config['time_offset']
        for evnt in evnt_sort:

            print(evnt[0], 'UTC: ', evnt[1], timezone, ephem.Date(evnt[1] + float(offset)/24.))    # NB Additon of local times would be handy here.
        event_dict = {}
        for item in evnt_sort:
            event_dict[item[0].strip()]= item[1]
        event_dict['use_by'] = ephem.Date(sunrise + 4/24.)
        event_dict['day_directory'] = str(day_dir)
        g_dev['events'] = event_dict



        # print("g_dev['events']:  ", g_dev['events'])

        #NB I notice some minor discrepancies in lunar timing. Should re-check all the dates and times wer 20200408








