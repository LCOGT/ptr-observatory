
'''
ptr_events.py  ptr_events.py  ptr_events.py  ptr_events.py  ptr_events.py

This is the Events organiser utility module

'''

# NB Change these to hours not fractions of a day.  Should come from site config not be in code here.
from math import log10, acos, sin, cos, radians, degrees
import ephem
from datetime import datetime, timezone, timedelta
from dateutil import tz
from global_yard import g_dev
from astropy.time import Time
from ptr_utility import plog
from astropy.coordinates import EarthLocation, AltAz, get_sun
from astropy import units as u
import traceback
import requests
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))

class Events:
    def __init__(self, config: dict, wema_config: dict):
        self.config = config
        self.wema_config = wema_config
        self.day_directory = None
        self.dayNow = ephem.now()

        # Fallback if we're missing the wema config
        if wema_config is None:

            plog(f"WARNING: failed to get config for wema for use with Events. Fallback to hardcoded values that are probably wrong for the site being run!!")
            self.wema_config={}
            self.wema_config['latitude']=7.378917
            self.wema_config['longitude']=-135.257229

            self.wema_config['elevation']=20
            self.wema_config['reference_ambient']=20
            self.wema_config['reference_pressure']=20
            self.wema_config['time_offset']= -11   #  These two keys may be obsolete given the new TZ stuff
            self.wema_config['timezone']= 'SST'
            self.wema_config['TZ_database_name']='Pacific/Midway'

            self.wema_config['eve_cool_down_open'] = float(-65.0) # How many minutes after sunrise to open. Default -65 = an hour-ish before sunset. Gives time to cool and get narrowband flats
            self.wema_config['morn_close_and_park'] = float(32.0) # How many minutes after sunrise to close. Default 32 minutes = enough time for narrowband flats

            plog ("Failed to get wema_config")
            plog(traceback.format_exc())


        self.siteLatitude = round(float(self.wema_config['latitude']), 8)  # 34 20 34.569   #34 + (20 + 34.549/60.)/60.
        self.siteLongitude = round(float(self.wema_config['longitude']), 8)  # -(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
        self.siteElevation = round(float(self.wema_config['elevation']), 3)

        self.site_coordinates = EarthLocation(lat=float(self.wema_config['latitude'])*u.deg, \
                                lon=float(self.wema_config['longitude'])*u.deg,
                                height=float(self.wema_config['elevation'])*u.m)

        self.siteRefTemp = round(float(self.wema_config['reference_ambient']), 2)  # These should be a monthly average data.
        self.siteRefPress = round(float(self.wema_config['reference_pressure']), 2)

        self.event_dict = self.calculate_events() # This is the primary function of this class

    ###############################
    ###    Internal Methods    ####
    ###############################

    def _sortTuple(self, tup):
        ''' Function to sort the list by second item of tuple '''
        # reverse = None (Sorts in Ascending order)
        # key is set to sort using second element of
        # sublist lambda has been used
        return(sorted(tup, key=lambda x: x[1]))

    def _reduceHa(self, pHa):
        while pHa <= -12:
            pHa += 24.0
        while pHa > 12:
            pHa -= 24.0
        return pHa

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
            i = 10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) +
                     2 * log10(sunDia/0.50664))
        else:
            i = 0
        if i < 0:
            i = 0
        f = 0
        if moonElev >= -0.8:
            if moonElev >= 20:
                il = (-1.95, 4.06, -4.24, 1.56)
            elif moonElev >= 5:
                il = (-2.58, 12.58, -42.58, 59.06)
            else:
                il = (-2.79, 24.27, -252.95, 1321.29)
            x = moonElev / 90
            raDist = radians(self._reduceHa(degrees(moonRa - sunRa)))
            e = degrees(acos(sin(sunDec) * sin(moonDec) + cos(sunDec) *
                             cos(moonDec) * cos(raDist)))
            f = 180 - e
            if f > 180:
                f = 180
            if f < 0:
                f = 0
            j = 10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) +
                     (-0.00868 * f - 0.0000000022 * (f ** 4))) + \
                2*log10(moonDia/0.951)  # This should be ckecked - moon dia
        else:
            j = 0
        if j < 0:
            j = 0

        illuminance = i + j + 0.002
        #   0.002 = stars and galaxy -- averaged; rest is Airglow,
        #   2e-3 lux is brightness of stars + airglow. Ratio is relative to that number.
        skyBrightRatio = illuminance/0.002
        if skyBrightRatio < 1:
            skyBrightRatio = 1
        skyMag = 22-2.5*log10(skyBrightRatio)
        return illuminance,  skyMag  # Units are lux, dimensionless ratio, approx mag/sq-asec

    def _sunNow(self):
        sun = ephem.Sun()
        sun.compute()
        moon = ephem.Moon()
        moon.compute()
        ptr = ephem.Observer()  # Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        sun.compute(ptr)
        moon.compute(ptr)
        return sun.ra, sun.dec, degrees(sun.alt), degrees(sun.az), moon.ra, moon.dec,\
            degrees(moon.alt), moon.size/3600

    def _calcEveFlatValues(self, ptr, sun, pWhen, skyFlatEnd, loud=False, now_spot=False):

        def plog_if_loud(*args, **kwargs):
            if loud: plog(*args, **kwargs)

        ptr.date = pWhen
        sun.compute(ptr)
        plog_if_loud('Sunset, sidtime:  ', pWhen, ptr.sidereal_time())
        plog_if_loud('Eve Open  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) - 180
        while SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        plog_if_loud('Flat spot at az alt:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        plog_if_loud('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = skyFlatEnd
        sun.compute(ptr)
        plog_if_loud('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)  # SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)
        plog_if_loud('Flatspots:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
        FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
        plog_if_loud('Eve Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
        span = 86400*(skyFlatEnd - pWhen)
        plog_if_loud('Duration:  ', str(round(span/60, 2)) + 'min')
        RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
        DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
        plog_if_loud('Eve Rates:  ', RaDot, DecDot)
        if now_spot:
            plog_if_loud(type(FlatStartRa))
            plog_if_loud('ReturningRa/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
            return degrees(FlatStartRa)/15, degrees(FlatStartDec)
        else:
            return (degrees(FlatStartRa)/15, degrees(FlatStartDec),
                    degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

    def _calcMornFlatValues(self, ptr, sun, pWhen,  sunrise, loud=False):
        def plog_if_loud(*args, **kwargs):
            if loud: plog(*args, **kwargs)
        ptr.date = pWhen
        sun.compute(ptr)
        plog_if_loud()
        plog_if_loud('Morn Flat Start, sidtime:  ', pWhen, ptr.sidereal_time())
        plog_if_loud('Morn Flat Start Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) + 180
        while SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90.:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        plog('Flat spot at:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        plog('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = sunrise
        sun.compute(ptr)
        plog_if_loud('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)  # SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)
        plog_if_loud('Flatspot:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
        FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
        plog('Morn Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
        span = 86400*(sunrise - pWhen)
        plog('Duration:  ', str(round(span/60, 2)) + 'min')
        RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
        DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
        plog('Morn Rates:  ', RaDot, DecDot, '\n')
        return (degrees(FlatStartRa)/15, degrees(FlatStartDec),
                degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

    def _compute_day_directory(self, loud=False):
        '''
        Mandatory:  The day_directory is the datestring for the Julian day as defined
        by the local astronomical Noon.  Restating the software any time within that
        24 hour period resultin in the Same day_directory.    Site restarts may occur
        at any time but automatic ones will normally occur somewhat after the prior
        night's  final reductions and the upcoming local Noon.
        '''

        # Checking the local time to check if it is setting up for tonight or tomorrow night.
        now_utc = datetime.now(timezone.utc)  # timezone aware UTC, shouldn't depend on clock time.
        to_zone = tz.gettz(self.wema_config['TZ_database_name'])
        now_here = now_utc.astimezone(to_zone)
        int_sunrise_hour = ephem.Observer().next_rising(ephem.Sun()).datetime().hour + 1
        if int(now_here.hour) < int_sunrise_hour:
            now_here = now_here - timedelta(days=1)
        if len(str(now_here.day)) == 1:
            nowhereday = '0' + str(now_here.day)
        else:
            nowhereday = str(now_here.day)
        if len(str(now_here.month)) == 1:
            nowheremonth = '0' + str(now_here.month)
        else:
            nowheremonth = str(now_here.month)

        DAY_Directory = f"{now_here.year}{nowheremonth}{nowhereday}"
        plog('Day_Directory:  ', DAY_Directory)
        g_dev['day'] = DAY_Directory
        self.day_directory = DAY_Directory
        return DAY_Directory

    #############################
    ###     Public Methods   ####
    #############################

    def getSunEvents(self):
        '''
        This is used in the enclosure module to determine if is a good time
        of day to open.
        '''
        sun = ephem.Sun()
        ptr = ephem.Observer()
        ptr.date = self.dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        ptr.horizon = '-0:34'
        sunset = ptr.next_setting(sun)
        sunrise = ptr.next_rising(sun)
        ptr.horizon = '-6'
        sun.compute(ptr)
        civilDusk = ptr.next_setting(sun)
        ops_win_begin = civilDusk - 121/1440
        return (ops_win_begin, sunset, sunrise, ephem.now())

    def sun_az_alt_now(self):

        altazframe=AltAz(obstime=Time.now(), location=self.site_coordinates)
        sun_coords=get_sun(Time.now()).transform_to(altazframe)
        return sun_coords.az.degree, sun_coords.alt.degree

    def illuminationNow(self):

        sunRa, sunDec, sunElev, sunAz, moonRa, moonDec, moonElev, moonDia \
            = self._sunNow()
        illuminance, skyMag = self._illumination(sunRa, sunDec, sunElev, 0.5,
                                                 moonRa, moonDec, moonElev, moonDia)
        return round(illuminance, 3), round(skyMag, 2)

    def calculate_events(self, endofnightoverride='no'):
        self.dayNow = ephem.now()

        # Creating ephem objects to use to calculate timings.
        sun = ephem.Sun()
        moon = ephem.Moon()
        ptr = ephem.Observer()
        ptr.date = self.dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp

        # Calculating relevant times according to the sun and the moon.
        ptr.horizon = '-0:34'
        self.sunset = ptr.next_setting(sun)
        self.middleNight = ptr.next_antitransit(sun)
        self.sunrise = ptr.next_rising(sun)
        self.next_moonrise = ptr.next_rising(moon)
        self.next_moontransit = ptr.next_transit(moon)
        self.next_moonset = ptr.next_setting(moon)
        self.last_moonrise = ptr.previous_rising(moon)
        self.last_moontransit = ptr.previous_transit(moon)
        self.last_moonset = ptr.previous_setting(moon)

        # Calculating civil twilight times
        ptr.horizon = '-6'
        sun.compute(ptr)
        self.civilDusk = ptr.next_setting(sun)
        self.civilDawn = ptr.next_rising(sun)

        # Calculating nautical twilight times
        ptr.horizon = '-12'
        sun.compute(ptr)
        self.nauticalDusk = ptr.next_setting(sun)  # Can start clocking and autofocus.
        self.nauticalDawn = ptr.next_rising(sun)

        # Calculating astronomical twilight times
        ptr.horizon = '-18'
        sun.compute(ptr)
        self.astroDark = ptr.next_setting(sun)
        self.astroEnd = ptr.next_rising(sun)

        # A bit of a contorted way of making sure the timings calculate the correct days and times
        # at certain peculiar times of the day that ephem finds tricky to interpret.
        if (self.nauticalDusk - self.astroDark) > 0.5:
            self.nautDusk_plus_half = self.dayNow
        else:
            self.nautDusk_plus_half = (self.nauticalDusk + self.astroDark)/2  # observing starts
        if (self.nauticalDawn - self.astroEnd) > 0.5:
            self.nautDawn_minus_half = self.dayNow
        else:
            self.nautDawn_minus_half = (self.nauticalDawn + self.astroEnd)/2  # Observing ends.

        self.duration = (self.astroEnd - self.astroDark)*24
        ptr.date = self.middleNight
        moon.compute(ptr)
        sun = ephem.Sun()
        sun.compute(ptr)
        self.mid_moon_ra = moon.ra
        self.mid_moon_dec = moon.dec
        self.mid_moon_phase = moon.phase
        plog('Middle night,  Moon Ra Dec Phase:  ', moon.ra, moon.dec, moon.phase)  # , moon.az, moon.alt)

        # The end of the night is when "End Morn Bias Dark" occurs. All timings must end with that
        # as this is when the night ends and the schedule gets reconfigured. So anything scheduled AFTER
        # then needs to be pulled back a day. Primarily because it sometimes does weird things.....
        self.endNightTime = ephem.Date(self.sunrise + 120/1440.)
        #breakpoint()
        self.cool_down_open = self.sunset + self.wema_config['eve_cool_down_open']/1440
        self.close_and_park = self.sunrise + self.wema_config['morn_close_and_park']/1440
        self.eve_skyFlatBegin = self.sunset + self.config['eve_sky_flat_sunset_offset']/1440

        if endofnightoverride == 'no':
            if ephem.Date(self.eve_skyFlatBegin) > self.endNightTime:
                self.eve_skyFlatBegin = self.eve_skyFlatBegin - 24*ephem.hour
            if ephem.Date(self.sunset) > self.endNightTime:
                self.sunset = self.sunset - 24*ephem.hour
            if ephem.Date(self.civilDusk) > self.endNightTime:
                self.civilDusk = self.civilDusk - 24*ephem.hour
            if ephem.Date(self.nauticalDusk) > self.endNightTime:
                self.nauticalDusk = self.nauticalDusk - 24*ephem.hour
            if ephem.Date(self.nautDusk_plus_half) > self.endNightTime:
                self.nautDusk_plus_half = self.nautDusk_plus_half - 24*ephem.hour
            if ephem.Date(self.astroDark) > self.endNightTime:
                self.astroDark = self.astroDark - 24*ephem.hour
            if ephem.Date(self.middleNight) > self.endNightTime:
                self.middleNight = self.middleNight - 24*ephem.hour
            if ephem.Date(self.astroEnd) > self.endNightTime:
                self.astroEnd = self.astroEnd - 24*ephem.hour
            if ephem.Date(self.nautDawn_minus_half) > self.endNightTime:
                self.nautDawn_minus_half = self.nautDawn_minus_half - 24*ephem.hour
            if ephem.Date(self.nauticalDawn) > self.endNightTime:
                self.nauticalDawn = self.nauticalDawn - 24*ephem.hour
            if ephem.Date(self.civilDawn) > self.endNightTime:
                self.civilDawn = self.civilDawn - 24*ephem.hour
            if ephem.Date(self.sunrise) > self.endNightTime:
                self.sunrise = self.sunrise - 24*ephem.hour
            if ephem.Date(self.cool_down_open) > self.endNightTime:
                self.cool_down_open = self.cool_down_open - 24*ephem.hour


        self.cool_down_open = self.sunset + self.wema_config['eve_cool_down_open']/1440
        self.close_and_park = self.sunrise + self.wema_config['morn_close_and_park']/1440
        #******************  NB NB Cool down and open comes from the WEMA Config.
        #***** Code in this computer has to verify open was not delayed or close is early.

#         # MTF instituted a hard 35 minute deviation to be systemwide to deal reasonably
#         # with the LCO scheduler. We don't need different values for different scopes anyway realistically.
#         # self.observing_begins=self.astroDark - self.config['astro_dark_buffer']/1440
#         # self.observing_ends=self.astroEnd + self.config['astro_dark_buffer']/1440

#         self.observing_begins=self.astroDark - 35/1440
#         self.observing_ends=self.astroEnd + 35/1440

        self.observing_begins=self.astroDark - self.config['astro_dark_buffer']/1440
        self.observing_ends=self.astroEnd + self.config['astro_dark_buffer']/1440


        self.evnt = [('Eve Bias Dark      ', ephem.Date(self.cool_down_open - self.config['bias_dark interval']/1440)),
                     ('End Eve Bias Dark  ', ephem.Date(self.cool_down_open - (1.25*6)/1440)),
                     ('Ops Window Start   ', ephem.Date(self.cool_down_open)),  # Enclosure may open.
                     ('Cool Down, Open    ', ephem.Date(self.cool_down_open)),
                     ('Eve Sky Flats      ', ephem.Date(self.sunset + self.config['eve_sky_flat_sunset_offset']/1440)),  # Nominally -35 for SRO
                     ('Sun Set            ', ephem.Date(self.sunset)),
                     ('Civil Dusk         ', ephem.Date(self.civilDusk)),
                     ('End Eve Sky Flats  ', ephem.Date(self.civilDusk + self.config['end_eve_sky_flats_offset']/1440)),
                     ('Observing Begins   ', ephem.Date(self.observing_begins)),
                     ('Clock & Auto Focus ', ephem.Date(self.observing_begins - self.config['clock_and_auto_focus_offset']/1440)),
                     ('Naut Dusk          ', ephem.Date(self.nauticalDusk)),
                     ('Astro Dark         ', ephem.Date(self.astroDark)),
                     ('Middle of Night    ', ephem.Date(self.middleNight)),
                     ('End Astro Dark     ', ephem.Date(self.astroEnd)),
                     ('Observing Ends     ', ephem.Date(self.observing_ends)),
                     ('Naut Dawn          ', ephem.Date(self.nauticalDawn)),
                     ('Civil Dawn         ', ephem.Date(self.civilDawn)),
                     ('Morn Sky Flats     ', ephem.Date(self.sunrise + self.config['morn_flat_start_offset']/1440.)),
                     ('Sun Rise           ', ephem.Date(self.sunrise)),
                     ('End Morn Sky Flats ', ephem.Date(self.sunrise  + self.config['morn_flat_end_offset']/1440.)),
                     ('Ops Window Closes  ', ephem.Date(self.close_and_park - 2/1440.)),
                     ('Close and Park     ', ephem.Date(self.close_and_park)),

                     ('Morn Bias Dark     ', ephem.Date(self.close_and_park + 2/1440.)),  #I guess this is warm-up time!
                     ('End Morn Bias Dark ', ephem.Date(night_reset := self.close_and_park +  self.config['bias_dark interval']/1440.)),
                     ('Nightly Reset      ', ephem.Date(night_reset + 2/1440.)),
                     #('End Nightly Reset  ', ephem.Date(night_reset + self.config['end_night_processing_time']/1440.)),  #Just a Guess
                     ('Prior Moon Rise    ', ephem.Date(self.last_moonrise)),
                     ('Prior Moon Transit ', ephem.Date(self.last_moontransit)),
                     ('Prior Moon Set     ', ephem.Date(self.last_moonset)),
                     ('Moon Rise          ', ephem.Date(self.next_moonrise)),
                     ('Moon Transit       ', ephem.Date(self.next_moontransit)),
                     ('Moon Set           ', ephem.Date(self.next_moonset))]

        self.evnt_sort = self._sortTuple(self.evnt)

        self.timezone = "  " + self.wema_config['timezone'] + ": "
        self.offset = self.wema_config['time_offset']

        event_dict = {}
        for item in self.evnt_sort:
            event_dict[item[0].strip()] = item[1]
        event_dict['use_by'] = ephem.Date(self.sunrise + 4/24.)
        event_dict['day_directory'] = self._compute_day_directory()

        g_dev['events'] = event_dict
        self.event_dict = event_dict
        return event_dict

    def display_events(self, endofnightoverride='no'):

        plog('Events module reporting for duty. \n')
        plog('Ephem date     :    ', self.dayNow)
        plog('Night Duration :    ', str(round(self.duration, 2)) + ' hr')
        plog('Moon Ra; Dec   :    ', round(self.mid_moon_ra, 2), ";  ", round(self.mid_moon_dec, 1))
        plog('Moon phase %   :    ', round(self.mid_moon_phase, 1), '%\n')
        plog("Key events for the evening, presented by the Solar System: \n")

        for self.evnt in self.evnt_sort:
            plog(self.evnt[0], 'UTC: ', self.evnt[1], self.timezone, ephem.Date(self.evnt[1] + float(self.offset)/24.))
