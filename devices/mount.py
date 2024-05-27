
"""
20200310 WER
General comments.  Note use of double quotes.  Maybe this is our convention for polemics and trading opinions then we strip
out of the Production source?

'''   use single quotes and # for code documentation and standaing comments

      use double quotes for talking to each other, or for actual quotes, document references and the like.
#"    in-line version of a polemic.   Does not go to production source.  A 'team-quote.'

      NB (nota bene) means "someone should fix this eventually!"   Please add your initials.   A valid fix is to delete the
      message.  They can go to production source.

The missing thing is mount management is more uniform treatement of the frame of reference of pointing, and the astrometric
solutions provided.  This is probably a WER task to sort out.  From the AWS user point of view we want to start with Modern
catalog positions, nominally ICRS, particularly as realized by the current GAIA release.  Other objects (Messier) as an example
we always try to go through Strassbourg to get coordinates.  Updates to those happen but they are carefully vetted.  We can
start with nominal published catalogs which generally give names, Ra and dec, Season, mag etc but update them IFF the
Strassborug data is more current.  Star charts are harder.  But there is some new stuff in the Pixinsight realse we might
want to take advantage of.

Refraction and mount models need to be added, but the problem is the state of mounting code over various manufactures is a
complete mess.  I have done this now for four different mountings and telescope setups so I think I can abstract things in a
way that the user experience can be uniform.  The goal is to get the best unguided tracking possible.  Although observing > 60
degt Zenith is inadvisable, if the Comet is here you are going to go for it right down to the horizon.  So getting refraction
right is important.

For pretty pictures one thing I would like to add to the 'coordinates' for an object is specification of Ra and Dec offset and
a Rotation (in the form of a Position Angle) that we have selected once we have imaged the object.  The user can of course
specify something different by selecting Catalog (N up, E to the left, PA = 0), Recommened( blah list here), or user (blah
list here retained in user account.)

"""


#import threading
import win32com.client
#import pythoncom
# import serial
# import time, json
import datetime
import traceback
# import os
import copy
import shelve
import threading
# import queue
from math import cos, radians    #"What plan do we have for making some imports be done this way, elg, import numpy as np...?"
from global_yard import g_dev    #"Ditto guestion we are importing a single object instance."

from astropy.time import Time

from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun, get_moon, FK5#, ICRS

#import short_utility as ptr_utility  #Once this works please undo this hack.

import math
import ephem
from ptr_utility import plog
import time

DEBUG = False

DEG_SYM = '°'
PI = math.pi
TWOPI = PI*2
PIOVER2 = PI/2.
DTOR = PI/180.
RTOD = 180/PI
STOR = PI/180./3600.
RTOS = 3600.*180./PI
RTOH = 12./PI
HTOR = PI/12.
HTOS = 15*3600.
DTOS = 3600.
STOD = 1/3600.
STOH = 1/3600/15.
SecTOH = 1/3600.
HTOSec = 3600.
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029

LOOK_WEST = 0  #These four constants reflect ASCOM conventions
LOOK_EAST = 1  #Flipped
ON_EAST_SIDE = 0   #Not Flipped.
ON_WEST_SIDE = 1   #This means flipped.
IS_FLIPPED = 1
IS_NORMAL = 0


tzOffset = -7
loop_count = 0

mountOne = "PW_L600"
mountOneAscom = None


def ra_fix_r(ra):
    while ra >= TWOPI:
        ra -= TWOPI
    while ra < 0:
        ra += TWOPI
    return ra

def ra_fix_h(ra):
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra = 24
    return ra

def ha_fix_h(ha):
    while ha <= -12:
        ha += 24.0
    while ha > 12:
        ha -= 24.0
    return ha

def ha_fix_r(ha):
    while ha <= -PI:
        ha += TWOPI
    while ha > PI:
        ha -= TWOPI
    return ha

def dec_fix_d(pDec):   #NB NB Note this limits not fixes!!!
    if pDec > 90.0:
        pDec = 90.0
    if pDec < -90.0:
        pDec = -90.0
    return pDec

def dec_fix_r(pDec):   #NB NB Note this limits not fixes!!!
    if pDec > PIOVER2:
        pDec = PIOVER2
    if pDec < -PIOVER2:
        pDec = -PIOVER2
    return pDec


def ra_dec_fix_r(ra, dec): #Note this is not a mechanical (TPOINT) transformation of dec and HA/RA
    if dec > PIOVER2:
        dec = PI - dec
        ra -= PI
    if dec < -PIOVER2:
        dec = -PI - dec
        ra += PI
    if ra < 0:
        ra += TWOPI
    if ra >= TWOPI:
        ra -= TWOPI
    return ra, dec

def ra_dec_fix_h(ra, dec):
    if dec > 90:
        dec = 180 - dec
        ra -= 12
    if dec < -90:
        dec = -180 - dec
        ra += 12
    if ra >= 24:
        ra -= 24
    if ra < 0:
        ra = 24
    return ra, dec

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
    return math.atan2(math.sin(theta) - b, math.cos(theta) - a)



class Mount:
    '''
    Note the Mount is a purely physical device , while the telescope reflects
    the optical pointing of the respective telescope.  However a reference tel=False
    is used to set up the mount.  Ideally this should be a very rigid stable telescope
    that is rarely disturbed or removed.
    '''

    def __init__(self, driver: str, name: str, settings: dict, config: dict, astro_events, tel=False):
        self.name = name
        self.astro_events = astro_events
        g_dev['mnt'] = self

        self.obsid = config['obs_id']
        self.obsid_path = g_dev['obs'].obsid_path
        self.config = config
        self.device_name = name
        self.settings = settings

        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)

        try:
            self.mount.Connected = True
        except:
            self.mount_busy=False
            plog(traceback.format_exc())

        self.driver = driver

        if "ASCOM.SoftwareBisque.Telescope" in driver:
            self.theskyx = True
        else:
            self.theskyx = False

        self.site_coordinates = EarthLocation(lat=float(g_dev['evnt'].wema_config['latitude'])*u.deg, \
                                lon=float(g_dev['evnt'].wema_config['longitude'])*u.deg,
                                height=float(g_dev['evnt'].wema_config['elevation'])*u.m)
        self.latitude_r = g_dev['evnt'].wema_config['latitude']*DTOR
        self.sin_lat = math.sin(self.latitude_r)
        self.cos_lat = math.cos(self.latitude_r)
        self.pressure =g_dev['evnt'].wema_config['reference_pressure']
        self.temperature = g_dev['evnt'].wema_config['reference_ambient']
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel   #for now this implies the primary telescope on a mounting.
        self.mount_message = "-"
        self.has_paddle = config['mount']['mount1']['has_paddle']

        self.object = "Unspecified"
        self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        #DIRECT MOUNT POSITION READ #1
        #NB NB this is toally incorrect.  The mount is mechanical. self.current_icrs_ra is used!
        self.current_icrs_ra = self.mount.RightAscension  #this _icrs_ reference is used in saftey check..
        self.current_icrs_dec = self.mount.Declination
        self.current_mount_sidereal = self.mount.SiderealTime
        self.current_mechanical_ra = self.mount.RightAscension
        self.current_mechanical_dec = self.mount.Declination
        self.current_mechanical_sidereal = self.mount.SiderealTime
        try:
            self.ICRS2000 = config["mount"]["mount1"]["settings"]['ICRS2000_input_coords']
            self.refr_on = config["mount"]["mount1"]["settings"]["refraction_on"]
            self.model_on = config["mount"]["mount1"]["settings"]["model_on"]
            self.model_type = config["mount"]["mount1"]["settings"]["model_type"]
            self.rates_on = config["mount"]["mount1"]["settings"]["rates_on"]
        except:
            self.ICRS2000 = True    #This is the default for coordinates provided by the PTR GUI
            self.refr_on = False    #These also are probably the settings for The SkyX since it does all this internally.
            self.model_on = False
            self.model_type = 'Equatorial'
            self.rates_on = False

        if self.model_type == 'Equatorial':
            try:
                self.model = config["mount"]["mount1"]["settings"]["model_equat"]
            except:
                plog ("No model in config, using 0 model")
                self.model = {
                    'ih': 0.0, #"Home naturally points to West for AP GEM mounts.
                    'id': 0.00, #These two are zero-point references for HA/Ra and dec.
                    'eho': 0.0, #"East Hour angle Offset -- NOTE an offset
                    'edo': 0.0, #"East Dec Offset
                    'ma': 0.0, # Azimuth error of polar axia
                    'me': 0.0,  # Elev error of polar axisDefault is about -60 asec above pole for ARO
                    'ch': 0.0,  #Optical axis not perp to dec axis
                    'np': 0.0,  #Non-perp of polar and dec axis
                    'tf': 0.0,  #Sin flexure -- Hook's law.
                    'tx': 0.0,  #Tangent flexure
                    'hces': 0.0, #Centration error of encoders.
                    'hcec': 0.0,
                    'dces': 0.0,
                    'dcec': 0.0,
                    }
        else:
            try:
                self.model = config["mount"]["mount1"]["settings"]["model_altAz"]
            except:
                plog ("No model in config, using 0 model")
                self.model = {
                    'ih': 0.0, #"Home naturally points to West for AP GEM mounts.
                    'id': 0.00, #These two are zero-point references for HA/Ra and dec.
                    'eho': 0.0, #"East Hour angle Offset -- NOTE an offset
                    'edo': 0.0, #"East Dec Offset
                    'ma': 0.0, # Azimuth error of polar axia
                    'me': 0.0,  # Elev error of polar axisDefault is about -60 asec above pole for ARO
                    'ch': 0.0,  #Optical axis not perp to dec axis
                    'np': 0.0,  #Non-perp of polar and dec axis
                    'tf': 0.0,  #Sin flexure -- Hook's law.
                    'tx': 0.0,  #Tangent flexure
                    'hces': 0.0, #Centration error of encoders.
                    'hcec': 0.0,
                    'dces': 0.0,
                    'dcec': 0.0,
                    }
        for key in self.model:
            self.model[key] = math.radians(self.model[key]/ 3600.)  #Convert  asec to degrees then radians



        self.delta_t_s = HTOSec/12   #5 minutes
        self.prior_roll_rate = 0
        self.prior_pitch_rate = 0
        self.offset_received = False
        self.west_clutch_ra_correction = config['mount']['mount1']['west_clutch_ra_correction']
        self.west_clutch_dec_correction = config['mount']['mount1']['west_clutch_dec_correction']
        self.east_flip_ra_correction = config['mount']['mount1']['east_flip_ra_correction']
        self.east_flip_dec_correction = config['mount']['mount1']['east_flip_dec_correction']
        self.settle_time_after_unpark = config['mount']['mount1']['settle_time_after_unpark']
        self.settle_time_after_park = config['mount']['mount1']['settle_time_after_park']

        self.refraction = 0
        self.target_az = 0   #Degrees Azimuth
        self.ha_corr = 0
        self.dec_corr = 0
        self.seek_commanded = False
        self.home_after_unpark = config['mount']['mount1']['home_after_unpark']
        self.home_before_park = config['mount']['mount1']['home_before_park']
        self.parking_or_homing=False
        self.wait_after_slew_time= config['mount']['mount1']['wait_after_slew_time']
        if abs(self.east_flip_ra_correction) > 0 or abs(self.east_flip_dec_correction) > 0:
            self.flip_correction_needed = True
            plog("Flip correction may be needed.")
        else:
            self.flip_correction_needed = False
        if not tel:
            plog("Mount connected.")
        else:
            plog("Auxillary Tel/OTA connected.")
        plog(self.mount.Description)
        self.ra_offset = 0.0
        self.dec_offset = 0.0
        self.move_time = 0
        self.obs = ephem.Observer()
        self.obs.long = g_dev['evnt'].wema_config['longitude']*DTOR
        self.obs.lat = g_dev['evnt'].wema_config['latitude']*DTOR

        self.theskyx_tracking_rescues = 0

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1' + str(g_dev['obs'].name))
        try:
            self.longterm_storage_of_mount_references=mnt_shelf['longterm_storage_of_mount_references']
            self.longterm_storage_of_flip_references=mnt_shelf['longterm_storage_of_flip_references']

            # self.longterm_storage_of_mount_references=[]
            # self.longterm_storage_of_flip_references=[]

        except:
            plog ("Could not load the mount deviations from the shelf, starting again.")
            self.longterm_storage_of_mount_references=[]
            self.longterm_storage_of_flip_references=[]
        mnt_shelf.close()

        plog ("Mount deviations, mount then flip:")
        plog (self.longterm_storage_of_mount_references)
        plog (self.longterm_storage_of_flip_references)

        self.last_mount_reference_time=time.time() - 86400
        self.last_flip_reference_time=time.time() - 86400

        self.last_mount_reference_ha = 0.0
        self.last_mount_reference_dec = 0.0
        self.last_flip_reference_ha = 0.0
        self.last_flip_reference_dec = 0.0

        self.last_flip_reference_ha_offset = 0.0
        self.last_flip_reference_dec_offset = 0.0
        self.last_mount_reference_ha_offset = 0.0
        self.last_mount_reference_dec_offset = 0.0

        # NEED to initialise these variables here in case the mount isn't slewed
        # before exposures after bootup

        #DIRECT MOUNT POSITION READ #2
        self.last_ra_requested = self.mount.RightAscension
        self.last_dec_requested = self.mount.Declination
        self.last_sidereal_requested = self.mount.SiderealTime

        self.last_tracking_rate_ra = 0
        self.last_tracking_rate_dec = 0
        self.last_seek_time = time.time() - 5000
        self.last_slew_was_pointing_slew = False
        self.currently_creating_status = False

        # Minimising ASCOM calls by holding these as internal variables
        if self.mount.CanSetRightAscensionRate:
            plog ("Can Set RightAscensionRate")
            self.CanSetRightAscensionRate=True
        else:
            plog ("CANNOT Set RightAscensionRate")
            self.CanSetRightAscensionRate=False
        self.RightAscensionRate = self.mount.RightAscensionRate

        if self.mount.CanSetDeclinationRate:
            self.CanSetDeclinationRate = True
            plog ("Can Set DeclinationRate")
        else:
            self.CanSetDeclinationRate = False
            plog ("CANNOT Set DeclinationRate")
        self.DeclinationRate = self.mount.DeclinationRate

        #IMPORTANT Ap1600 Info.
        #hogwash:   #Set Rate unit to asec/sec and Relative to Sid.  Rates are in asec/sec
                    #So a dec rate value of 15.0477 causes about a dec rate -15!  Not a typo, the sign is reversed.
                    #For RA a rate entry of 0.0 means normal tracking, a entry of 0.1 means RA increases 1 sec in ra
                    #every 10 seconds of time.
                    #Divide RArate by APPTOSID to get an exact rate display on APCC
                    #Multiply DEC rate by APPTOSID for an exact rate display.
                    #self.mount.RightAscensionRate = 1/APPTOSID  Ra rate = 15.0000000
                    #self.mount.DeclinationRate = 15*APPTOSID  Dec Rate = 15.0000000
                    #self.mount.RightAscensionRate = 0.0  Returns to normal tracking
        #Truth:   Supply asec per sec/APPTOSID for RA and asec per sec for DEC, just
                  #like the ASCOM litrature says.  The display on APCC can be confusing
                  #The rates display on the AP GpTo ASCOM driver (tall skinny window)
                  #is correct and shows the input asec/sec values.



        self.EquatorialSystem = self.mount.EquatorialSystem

        self.previous_pier_side = self.mount.sideOfPier
        self.pier_side_last_check = self.mount.sideOfPier
        self.request_new_pierside=False
        self.request_new_pierside_ra=1.0
        self.request_new_pierside_dec=1.0

        self.can_park = self.mount.CanPark
        self.can_set_tracking = self.mount.CanSetTracking

        self.can_sync_mount = self.mount.CanSync

        # The update_status routine collects the current atpark status and pier status.
        # This is a slow command, so unless the code needs to know IMMEDIATELY
        # whether the scope is parked, then this is polled rather than directly
        # asking ASCOM/MOUNT
        self.rapid_park_indicator=copy.deepcopy(self.mount.AtPark)
        self.rapid_pier_indicator=copy.deepcopy(self.mount.sideOfPier)

        #DIRECT MOUNT POSITION READ #3
        self.right_ascension_directly_from_mount = copy.deepcopy(self.mount.RightAscension)
        self.declination_directly_from_mount = copy.deepcopy(self.mount.Declination)
        self.sidereal_time_directly_from_mount = copy.deepcopy(self.mount.SiderealTime)
        #Verified these set the rates additively to mount supplied refraction rate.20231221 WER
        self.right_ascension_rate_directly_from_mount = copy.deepcopy(self.mount.RightAscensionRate)
        self.declination_rate_directly_from_mount = copy.deepcopy(self.mount.DeclinationRate)


        # initialisation values
        self.alt= 45
        self.airmass = 1.5
        self.az = 160
        self.zen = 45


        self.inverse_icrs_and_rates_timer=time.time() - 180

        self.current_tracking_state=copy.deepcopy(self.mount.Tracking)

        self.request_tracking_on = False
        self.request_tracking_off = False

        self.request_set_RightAscensionRate=False
        self.request_set_DeclinationRate=False

        self.CanFindHome = self.mount.CanFindHome

        # This is a latch to prevent multiple commands being sent to latch at the same time.
        self.mount_busy=False

        self.pier_flip_detected=False

        tempunparked=False
        # if mount is parked, temporarily unpark it quickly to test pierside functions.
        if self.mount.AtPark:
            self.mount.Unpark()
            tempunparked=True
            self.rapid_park_indicator=False

        # Here we figure out if it can report pierside. If it cannot, we need
        # not keep calling the mount to ask for it, which is slow and prone
        # to an ascom crash.
        try:
            self.pier_side = g_dev["mnt"].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
            self.can_report_pierside = True
        except Exception:
            plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            self.can_report_pierside = False
            self.pier_side = 0
            pass

        # Similarly for DestinationSideOfPier
        try:
            g_dev["mnt"].mount.DestinationSideOfPier(0,0)  # 0 == Tel Looking West, is flipped.
            self.can_report_destination_pierside = True
        except Exception:
            plog ("Mount cannot report destination pierside. Setting the code not to ask again.")
            self.can_report_destination_pierside = False
            self.pier_side = 0
            pass

        self.new_pierside =0

        if self.pier_side == 0:
            self.pier_side_str ="Looking West"
        else:
            self.pier_side_str = "Looking East"

        if tempunparked:
            self.mount.Park()
            self.rapid_park_indicator=True

        self.currently_slewing= False
        self.abort_slew_requested=False
        self.find_home_requested=False

        self.sync_mount_requested=False

        self.syncToRA=12.0   #Moved these two variables up from below the next block of code WER
        self.syncToDEC=-20.0 #And why these values?SidTime for RA might be better, or synch to Park5.
        #This faults. WER 20240519  and why are we synching the mount here?
        #Next mount_update.wincom does not exist yet, hence teh fault.
        try:
            #self.mount_update_wincom.SyncToCoordinates(self.syncToRA,self.syncToDEC)
            pass
        except:
            pass




        self.unpark_requested=False
        self.park_requested=False
        self.slewtoRA = 1.0
        self.slewtoDEC = 34.0
        self.slewtoAsyncRequested=False
        self.request_find_home=False

        self.mount_update_period=0.1
        self.mount_update_timer=time.time() - 2* self.mount_update_period
        self.mount_updates=0
        self.mount_update_paused=False
        self.mount_update_reboot=False

        self.mount_update_thread=threading.Thread(target=self.mount_update_thread)
        self.mount_update_thread.start()

        self.wait_for_mount_update()
        self.get_status()


#First add in various needed functions for coordinate conversions

    def transform_haDec_to_az_alt(self, pLocal_hour_angle_h, pDec_d):
        #global sin_lat, cos_lat     #### Check to see if these can be eliminated
        decr = radians(pDec_d)
        sinDec = math.sin(decr)
        cosDec = math.cos(decr)
        mHar = radians(15.0 * pLocal_hour_angle_h)
        sinHa = math.sin(mHar)
        cosHa = math.cos(mHar)
        altitude = math.degrees(math.asin(self.sin_lat * sinDec + self.cos_lat * cosDec * cosHa))
        x = cosHa * self.sin_lat - math.tan(decr) * self.cos_lat
        azimuth = math.degrees(math.atan2(sinHa, x)) + 180
        # azimuth = reduceAz(azimuth)
        # altitude = reduceAlt(altitude)
        return (azimuth, altitude)  # , local_hour_angle)


    def transform_azAlt_to_haDec(self, pAz, pAlt):
        #global sin_lat, cos_lat, lat
        alt = math.radians(pAlt)
        sinAlt = math.sin(alt)
        cosAlt = math.cos(alt)
        az = math.radians(pAz) - PI
        sinAz = math.sin(az)
        cosAz = math.cos(az)
        if abs(abs(alt) - PIOVER2) < 1.0 * STOR:
            return (
                0.0,
                self.lat
            )  # by convention azimuth points South at local zenith
        else:
            dec = math.degrees(math.asin(sinAlt * self.sin_lat - cosAlt * cosAz * self.cos_lat))
            ha = math.degrees(math.atan2(sinAz, (cosAz * self.sin_lat + math.tan(alt) * self.cos_lat)))/15.
            return (ha_fix_h(ha), dec_fix_d(dec))

    def apply_refraction_in_alt(self, pApp_alt):  # Deg, C. , mmHg     #note change to mbar

        # From Astronomical Algorithms.  Max error 0.89" at 0 elev.
        # 20210328 This code does not the right thing if star is below the Pole and is refracted above it.
        if not self.refr_on:
            return pApp_alt, 0.0
        elif pApp_alt > 0:
            ref = (1 / math.tan(DTOR * (pApp_alt + 7.31 / (pApp_alt + 4.4))) + 0.001351521673756295)
            ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
            ref *= 283 / (273 + self.temperature)
            ref *= self.pressure / 1010.0
            obs_alt = pApp_alt + ref / 60.0
            return dec_fix_d(obs_alt), ref * 60.0    #note the Observed _altevation is > apparent.
        else:
            #Just return refr for elev = 0
            obs_alt=0
            ref = 1 / math.tan(DTOR * (7.31 / (pApp_alt + 4.4))) + 0.001351521673756295
            ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
            ref *= 283 / (273 + self.temperature)
            ref *= self.pressure / 1010.0
            return dec_fix_d(obs_alt), round(ref * 60.0,3)

    def correct_refraction_in_alt(self, pObs_alt):  # Deg, C. , mmHg

        if not self.refr_on:
            return pObs_alt, 0.0, 0
        else:
            ERRORlimit = 0.01 * STOR
            count = 0
            error = 10
            trial = pObs_alt
            while abs(error) > ERRORlimit:
                appTrial, ref = self.apply_refraction_in_alt(trial)
                error = appTrial - pObs_alt
                trial -= error
                count += 1
                if count > 25:  # count about 12 at-0.5 deg. 3 at 45deg.
                    return dec_fix_d(pObs_alt)

            return dec_fix_d(trial), dec_fix_d(pObs_alt - trial)  * 3600.0, count

    def transform_mechanical_to_icrs(self, pRoll_h, pPitch_d, pPierSide, loud=False):
        # I am amazed this works so well even very near the celestial pole.
        # input is Ha in hours and pitch in degrees.
        if not self.model_on:
            return (pRoll_h, pPitch_d, 0, 0)
        else:

            cosDec = math.cos(pPitch_d*DTOR)
            ERRORlimit = 0.01 * STOR
            count = 0
            error = 10
            rollTrial = pRoll_h
            pitchTrial = pPitch_d
            while abs(error) > ERRORlimit:

                obsRollTrial, obsPitchTrial, ra_vel, dec_vel = self.transform_icrs_to_mechanical(
                    rollTrial, pitchTrial, pPierSide
                )
                #Not vel's are calculated for the current side time
                errorRoll = ha_fix_h(obsRollTrial - pRoll_h)*HTOR
                errorPitch = dec_fix_d(obsPitchTrial - pPitch_d)*DTOR
                # This needs a unit checkout.
                error = math.sqrt(
                    cosDec * (errorRoll) ** 2 + (errorPitch) ** 2
                )  # Removed *15 from errorRoll
                rollTrial -= errorRoll*RTOH
                pitchTrial -= errorPitch*RTOD
                count += 1
                if count > 500:  # count about 12 at-0.5 deg. 3 at 45deg.
                    #if loud:
                    #plog("transform_mount_to_observed_r() FAILED!")
                    return pRoll_h, pPitch_d, 0.0, 0.0

            print("Refr and Corrections in asec:  ",round(self.refr_asec, 2), round(self.raCorr, 2), round(self.decCorr, 2))
            #if DEBUG:  plog("Iterations:  ", count, ra_vel, dec_vel)

            return_ra = ra_fix_h(rollTrial)

            return return_ra, dec_fix_d(pitchTrial), 0 , 0 #ra_vel, dec_vel

    def transform_icrs_to_mechanical(self, icrs_ra_h, icrs_dec_d, rapid_pier_indicator, loud=False, enable=False):
           #Note when starting up Rapid Pier indicator may be incorrect.
        self.get_current_times()

        if self.ICRS2000:
            #Convert to Apparent
            icrs_coord = SkyCoord(icrs_ra_h*u.hour, icrs_dec_d*u.degree, frame='icrs')
            jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
            #jnow_coord_2 = icrs_coord.transform_to(ICRS(equinox=self.equinox_now))
            #breakpoint()
            ra = jnow_coord.ra.hour
            dec = jnow_coord.dec.degree
        else:
            ra = icrs_ra_h
            dec = icrs_dec_d
        #plog('Converted j.now: ', ra, dec)

        if self.offset_received:
            ra += self.ra_offset          #Offsets are J.now and used to get target on Browser Crosshairs.
            dec += self.dec_offset
        ra_app_h, dec_app_d = ra_dec_fix_h(ra, dec)

        #First, convert Ra to Ha
        self.sid_now_h = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        #First, convert Ra to Ha
        ha_app_h = ha_fix_h(self.sid_now_h - ra_app_h)
        #plog('Converted j.now + OFFSET ra, ha, dec: ', ra_app_h, ha_app_h, dec_app_d)
        if self.refr_on:
            #Convert to Observed
            #next convert to ALT az, and save the az
            az_d, alt_d = self.transform_haDec_to_az_alt(ha_app_h, dec_app_d)
            #next add in the refractive lift
            alt_ref_d, self.refr_asec = self.apply_refraction_in_alt(alt_d)
            #next convert back to Ha and dec
            if DEBUG: print("                ref:  ", round(self.refr_asec, 2))
            ha_obs_h, dec_obs_d = self.transform_azAlt_to_haDec(az_d, alt_ref_d)
        else:
            ha_obs_h = ha_app_h
            dec_obs_d =dec_app_d
        #plog('Converted obs + OFFSET refr, ha, dec: ', self.refr_asec, ha_obs_h, dec_obs_d)
        if self.model_on:
            #Convert to Mechanical.

            self.slewtoHA, self.slewtoDEC = self.transform_observed_to_mount(ha_obs_h, dec_obs_d, self.rapid_pier_indicator, loud=False, enable=False)
            self.slewtoRA = ra_fix_h(self.sid_now_h - self.slewtoHA)
            self.ha_rate = 0.0
            self.dec_rate = 0.0
            pass
        #plog('Mech ra, ha, dec: ', self.slewtoRA, self.slewtoHA, self.slewtoDEC)
        if self.rates_on:
            #Compute Velocities.  Typically with a CCD we rarely expose longer than 300 sec  so we
            # are going to use 600 sec as the time delta.
            step = 3600 #seconds  #at zenith refraction is about 13 asec for first hour.
            self.delta_step = step/3600.
            self.delta_sid_now_h = self.sid_now_h + self.delta_step
            delta_ha_app_h = ha_fix_h(self.delta_sid_now_h - ra_app_h)
            if self.refr_on:
                #Convert to Observed
                #next convert to ALT az, and save the az
                az_d, alt_d = self.transform_haDec_to_az_alt(delta_ha_app_h, dec_app_d)
                #next add in the refractive lift
                alt_ref_d, self.delta_refr_asec = self.apply_refraction_in_alt(alt_d)
                #next convert back to Ha and dec

                delta_ha_obs_h, delta_dec_obs_d = self.transform_azAlt_to_haDec(az_d, alt_ref_d)
            else:
                delta_ha_obs_h = ha_app_h
                delta_dec_obs_d =dec_app_d
            if self.model_on:
                #Convert to Mechanical.
                self.delta_slewtoHA, self.delta_slewtoDEC = self.transform_observed_to_mount(delta_ha_obs_h, delta_dec_obs_d, self.rapid_pier_indicator, loud=False, enable=False)
                self.delta_slewtoRA = ra_fix_h(self.delta_sid_now_h - self.delta_slewtoHA)
            else:
                self.delta_slewtoRA = self.slewtoRA
                self.delta_slewtoHA = delta_ha_obs_h
                self.delta_slewtoDEC = self.slewtoDEC
            # if 34.5 < dec_app_d < 35.5 and -2 < ha_app_h < 2:
            #     #breakpoint()
            #     pass
            self.ha_rate = (self.delta_slewtoHA - self.slewtoHA)*HTOSec/APPTOSID #step needed in this!
            self.dec_rate = (self.delta_slewtoDEC - self.slewtoDEC)*DTOS/step
        return(self.slewtoRA, self.slewtoDEC, 0, 0) #self.ha_rate, self.dec_rate)
        pass

    def transform_observed_to_mount(self, pRoll_h, pPitch_d, pPierSide, loud=False, enable=False):
        """
        Long-run probably best way to do this is inherit a model dictionary.

        NBNBNB improbable minus sign of ID, WD

        This implements a basic 7 term TPOINT transformation.
        This routine is interatively invertible.
        """
        #breakpoint()
        #loud = True

        if not self.model_on:
            return (pRoll_h, pPitch_d)
        else:

            # R to HD convention
            # pRoll  in Hours
            # pPitch in degrees
            #Apply IH and ID to incoming coordinates, and if needed GEM correction.
            rRoll = math.radians(pRoll_h * 15) - self.model['ih']  #This is the basic calibration for Park Position.
            rPitch = math.radians(pPitch_d) - self.model['id']
            # siteLatitude = self.latitude_r
            GEM = True
            if GEM:
                #"Pier_side" is now "Look East" or "Look West" For a GEM. Given ARO Telescope starts Looking West


                #In ASCOM Pier east, looking West is pierside = 0
                if pPierSide == LOOK_WEST:
                    #rRoll = math.radians(pRoll_h * 15) - self.model['ih']  #This is the basic calibration for Park Position.
                    #rPitch = math.radians(pPitch_d) - self.model['id']
                    ch = self.model['ch']
                    np = self.model['np']
                elif pPierSide == LOOK_EAST:    #Add in offset correction and flip CH, NP terms.
                    rRoll += self.model['eho']
                    rPitch += self.model['edo']
                    ch = -self.model['ch']
                    np = -self.model['np']
                    pass
                # if loud:
                #     plog(ih, idec, edh, edd, ma, me, ch, np, tf, tx, hces, hcec, dces, dcec, pPierSide)

                # This is exact trigonometrically:
                if loud:
                    plog("Pre CN; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
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
                    plog("Post CN; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
                x, y, z = sph_rect_r(cnRoll, cnPitch)
                if loud:
                    plog("To spherical:  ", x, y, z, x * x + y * y + z * z)
                # Apply MA error:
                y, z = rotate_r(y, z, -self.model['ma'])
                # Apply ME error:
                x, z = rotate_r(x, z, -self.model['me'])
                if loud:
                    plog("Post MA, ME:       ", x, y, z, x * x + y * y + z * z)
                # Apply latitude
                x, z = rotate_r(x, z, (PIOVER2 - self.latitude_r))
                if loud:
                    plog("Post-Lat:  ", x, y, z, x * x + y * y + z * z)
                # Apply TF, TX
                az, alt = rect_sph_d(x, y, z)  # math.pi/2. -
                if loud:
                    plog("Az Alt:  ", az + 180.0, alt)
                # flexure causes mount to sag so a shift in el, apply then
                # move back to other coordinate system
                zen = 90 - alt
                if zen >= 89:
                    clampedTz = 57.289961630759144  # tan(89)
                else:
                    clampedTz = math.tan(math.radians(zen))
                defl = (
                    self.model['tf'] * math.sin(math.radians(zen))
                    + self.model['tx'] * clampedTz
                )
                alt += defl * RTOD
                if loud:
                    plog(
                        "Post Tf,Tx; az, alt, z, defl:  ",
                        az + 180.0,
                        alt,
                        z * RTOD,
                        defl * RTOS,
                    )
                # The above is dubious but close for small deflections.
                # Unapply Latitude

                x, y, z = sph_rect_d(az,alt)
                x, z = rotate_r(x, z, -(PIOVER2 - self.latitude_r))
                fRoll, fPitch = rect_sph_r(x, y, z)
                cRoll = centration_r(fRoll, -self.model['hces'], self.model['hcec'])
                cPitch = centration_r(fPitch, -self.model['dces'], self.model['dcec'])

                if loud:
                    plog("Back:  ", x, y, z, x * x + y * y + z * z)
                    plog("Back-Lat:  ", x, y, z, x * x + y * y + z * z)
                    plog("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
                    plog("f,c Roll: ", fRoll, cRoll)
                    plog("f, c Pitch: ", fPitch, cPitch)
                corrRoll = ha_fix_r(cRoll)
                corrPitch = cPitch
                if loud:
                    plog("Final:   ", fRoll * RTOH, fPitch * RTOD)
                self.raCorr = (ha_fix_r(corrRoll - pRoll_h*HTOR))*RTOS  #Stash the correction
                self.decCorr = (dec_fix_r(corrPitch - pPitch_d*DTOR))*RTOS
                # 20210328  Note this may not work at Pole.
                #if enable:
                if DEBUG: print("Corrections in asec:  ", round(self.raCorr, 2), round(self.decCorr, 2))
                return (corrRoll*RTOH, corrPitch*RTOD )
            elif not GEM:
                #if loud:
                    # plog(
                    #     ih, idec, ia, ie, an, aw, tf, tx, ca, npae, aces, acec, eces, ecec
                    # )
                pass

                # Convert Incoming Ha, Dec to Alt-Az system, apply corrections then
                # convert back to equitorial. At this stage we assume positioning of
                # the mounting is still done in Ra/Dec coordinates so the canonical
                # velocities are generated by the mounting, not any Python level code.

                # loud = False
                # az, alt = transform_haDec_to_az_alt(pRoll, pPitch)  #units!!
                # # Probably a units problem here.
                # rRoll = math.radians(az + ia / 3600.0)
                # rPitch = math.radians(alt - ie / 3600.0)
                # ch = ca / 3600.0
                # np = npae / 3600.0
                # # This is exact trigonometrically:

                # cnRoll = rRoll + math.atan2(
                #     math.cos(math.radians(np)) * math.tan(math.radians(ch))
                #     + math.sin(math.radians(np)) * math.sin(rPitch),
                #     math.cos(rPitch),
                # )
                # cnPitch = math.asin(
                #     math.cos(math.radians(np))
                #     * math.cos(math.radians(ch))
                #     * math.sin(rPitch)
                #     - math.sin(math.radians(np)) * math.sin(math.radians(ch))
                # )
                # if loud:
                #     plog("Pre CANPAE; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
                #     plog("Post CANPAE; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
                # x, y, z = sph_rect_d(math.degrees(cnRoll), math.degrees(cnPitch))

                # # Apply AN error:
                # y, z = rotate_r(y, z, math.radians(-aw / 3600.0))
                # # Apply AW error:
                # x, z = rotate_r(x, z, math.radians(an / 3600.0))
                # az, el = rect_sph_d(x, y, z)
                # if loud:
                #     plog("To spherical:  ", x, y, z, x * x + y * y + z * z)
                #     plog("Pre  AW:       ", x, y, z, math.radians(aw / 3600.0))
                #     plog("Post AW:       ", x, y, z, x * x + y * y + z * z)
                #     plog("Pre  AN:       ", x, y, z, math.radians(an / 3600.0))
                #     plog("Post AN:       ", x, y, z, x * x + y * y + z * z)
                #     plog("Az El:  ", az + 180.0, el)
                # # flexure causes mount to sag so a shift in el, apply then
                # # move back to other coordinate system
                # zen = 90 - el
                # if zen >= 89:
                #     clampedTz = 57.289961630759144  # tan(89)
                # else:
                #     clampedTz = math.tan(math.radians(zen))
                # defl = (
                #     math.radians(tf / 3600.0) * math.sin(math.radians(zen))
                #     + math.radians(tx / 3600.0) * clampedTz
                # )
                # el += defl * RTOD
                # if loud:
                #     plog(
                #         "Post Tf,Tx; az, el, z, defl:  ",
                #         az + 180.0,
                #         el,
                #         z * RTOD,
                #         defl * RTOS,
                #     )
                # # The above is dubious but close for small deflections.
                # # Unapply Latitude

                # x, y, z = sph_rect_d(az, el)
                # if loud:
                #     plog("Back:  ", x, y, z, x * x + y * y + z * z)
                # fRoll, fPitch = rect_sph_d(x, y, z)
                # if loud:
                #     plog("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
                # cRoll = centration_d(fRoll, aces, acec)
                # if loud:
                #     plog("f,c Roll: ", fRoll, cRoll)
                # cPitch = centration_d(fPitch, -eces, ecec)
                # if loud:
                #     plog("f, c Pitch: ", fPitch, cPitch)
                # corrRoll = reduce_az_r(cRoll)
                # corrPitch = reduce_alt_r(cPitch)
                # if loud:
                #     plog("Final Az, ALT:   ", corrRoll, corrPitch)
                # haH, decD = transform_azAlt_to_haDec(corrRoll, corrPitch)   #Units
                # raCorr = reduce_ha_h(haH - pRoll) * 15 * 3600
                # decCorr = reduce_dec_d(decD - pPitch) * 3600
                # if loud:
                #     plog("Corrections:  ", raCorr, decCorr)
                # return (haH, decD)





    # Note this is a thread!
    def mount_update_thread(self):   # NB is this the best name for this? Update vs Command

        win32com.client.pythoncom.CoInitialize()

        self.mount_update_wincom = win32com.client.Dispatch(self.driver)
        try:
            self.mount_update_wincom.Connected = True
        except:
            # perhaps the AP mount doesn't like this.
            pass

        # This stopping mechanism allows for threads to close cleanly.
        while True:
            try:
                # update every so often, but update rapidly if slewing.
                if self.mount_update_reboot:
                    win32com.client.pythoncom.CoInitialize()
                    self.mount_update_wincom = win32com.client.Dispatch(self.driver)
                    try:
                        self.mount_update_wincom.Connected = True
                    except:
                        # perhaps the AP mount doesn't like this.
                        pass
                    self.mount_update_paused=False
                    self.mount_update_reboot=False
                    self.pier_flip_detected=False

                    self.rapid_park_indicator=copy.deepcopy(self.mount_update_wincom.AtPark)
                    self.currently_slewing=False
                    g_dev['mnt'].pier_side_last_check=copy.deepcopy(self.rapid_pier_indicator)


                    self.mount_updates=self.mount_updates + 1  #A monotonic increasing integer counter

                if self.currently_slewing or (((self.mount_update_timer < time.time() - self.mount_update_period) and not self.mount_update_paused)):# or (no(self.currently_slewing) and not self.mount_update_paused):

                    self.currently_slewing= self.mount_update_wincom.Slewing

                    if self.currently_slewing:
                        try:
                            self.pier_flip_detected=False

                            #DIRECT MOUNT POSITION READ #4  But this time from mount_update_wincom
                            # This is the direct command WHILE SLEWING.
                            # This part of the thread just updates the position
                            # Purely to make the green crosshair update as
                            # quickly as possible
                            self.right_ascension_directly_from_mount = copy.deepcopy(self.mount_update_wincom.RightAscension)
                            self.declination_directly_from_mount = copy.deepcopy(self.mount_update_wincom.Declination)
                            self.sidereal_time_directly_from_mount= copy.deepcopy(self.mount_update_wincom.SiderealTime)
                            # # Here we calculate the values that go to the status.
                            # self.inverse_icrs_ra, self.inverse_icrs_dec, inverse_ra_vel, inverse_dec_vel = self.transform_mechanical_to_icrs(self.right_ascension_directly_from_mount, self.declination_directly_from_mount,  self.rapid_pier_indicator)
                            # #I left the above two velocities as local becuse we will not do anything with them.

                            if self.model_on:
                                # Dont need to correct temporary slewing values as it is moving
                                self.inverse_icrs_ra = self.right_ascension_directly_from_mount
                                self.inverse_icrs_dec = self.declination_directly_from_mount
                                self.inverse_icrs_and_rates_timer=time.time()

                        except:
                            plog ("Issue in slewing mount thread")
                            plog(traceback.format_exc())

                        self.mount_updates=self.mount_updates + 1
                        self.mount_update_timer=time.time()
                    else:
                        #  Starting here ae tha vari0us mount commands and reads...
                        try:

                            if self.can_sync_mount:
                                if self.sync_mount_requested:
                                    self.sync_mount_requested=False
                                    self.mount_update_wincom.SyncToCoordinates(self.syncToRA,self.syncToDEC)


                            if self.unpark_requested:
                                self.unpark_requested=False
                                self.mount_update_wincom.Unpark()
                                self.rapid_park_indicator=False

                            if self.park_requested:
                                self.park_requested=False
                                self.mount_update_wincom.Park()
                                self.rapid_park_indicator=True

                            if self.find_home_requested:
                                self.find_home_requested=False
                                if self.mount_update_wincom.AtHome:
                                    plog("Mount is at home.")
                                else:
                                    g_dev['obs'].time_of_last_slew=time.time()
                                    if self.mount_update_wincom.AtPark:
                                        self.mount_update_wincom.Unpark()

                                    while self.mount_update_wincom.Slewing:
                                        plog("waiting for slew before homing")
                                        time.sleep(0.2)
                                    self.mount_update_wincom.FindHome()

                            if self.abort_slew_requested:
                                self.abort_slew_requested=False
                                self.mount_update_wincom.AbortSlew()

                            if self.slewtoAsyncRequested:
                                self.slewtoAsyncRequested=False

                                # Don't slew while exposing!
                                try:
                                    while g_dev['cam'].shutter_open:
                                        plog ("mount thread waiting for camera")
                                        time.sleep(0.2)
                                except:
                                    plog ("mount thread camera wait failed.")

                                self.mount_update_wincom.SlewToCoordinatesAsync(self.slewtoRA , self.slewtoDEC)
                                self.currently_slewing=True

                            # If we aren't slewing this update and we haven't
                            # updated the position for a minute, update the position.
                            elif (time.time() - self.inverse_icrs_and_rates_timer) > 60:

                                if self.model_on:

                                    self.inverse_icrs_ra, self.inverse_icrs_dec, self.inverse_ra_vel, self.inverse_dec_vel = self.transform_mechanical_to_icrs(self.right_ascension_directly_from_mount, self.declination_directly_from_mount,  self.rapid_pier_indicator)
                                    self.inverse_icrs_and_rates_timer=time.time()

                                    if self.CanSetRightAscensionRate:
                                        self.request_set_RightAscensionRate=False
                                        try:
                                            self.mount_update_wincom.RightAscensionRate=self.inverse_ra_vel
                                            #plog ("new RA rate set: " +str(self.RightAscensionRate))
                                        except:
                                            pass  #This faults if mount is parked.
                                        self.RightAscensionRate=self.inverse_ra_vel
                                        #plog ("new RA rate set: " +str(self.RightAscensionRate))

                                    if self.CanSetDeclinationRate:
                                        self.request_set_DeclinationRate=False
                                        try:
                                            self.mount_update_wincom.DeclinationRate=self.inverse_dec_vel
                                            #plog ("new DEC rate set: " +str(self.DeclinationRate))
                                        except:
                                            pass  #This faults if mount is parked.
                                        self.DeclinationRate=self.inverse_dec_vel



                                # if self.CanSetDeclinationRate:
                                #     self.mount_update_wincom.DeclinationRate = 0

                            if self.request_tracking_on:
                                self.request_tracking_on = False
                                self.mount_update_wincom.Tracking = True

                            if self.request_tracking_off:
                                self.request_tracking_off = False
                                self.mount_update_wincom.Tracking = False

                            if self.request_new_pierside:
                                self.request_new_pierside=False
                                if self.can_report_destination_pierside:
                                    self.new_pierside=self.mount_update_wincom.DestinationSideOfPier(self.request_new_pierside_ra, self.request_new_pierside_dec)

                            if self.request_set_RightAscensionRate and self.CanSetRightAscensionRate:
                                self.request_set_RightAscensionRate=False
                                self.mount_update_wincom.RightAscensionRate=self.request_new_RightAscensionRate
                                self.RightAscensionRate=self.request_new_RightAscensionRate
                                #plog ("new RA rate set: " +str(self.RightAscensionRate))

                            if self.request_set_DeclinationRate and self.CanSetDeclinationRate:
                                self.request_set_DeclinationRate=False
                                self.mount_update_wincom.DeclinationRate=self.request_new_DeclinationRate
                                self.DeclinationRate=self.request_new_DeclinationRate
                                #plog ("new DEC rate set: " +str(self.DeclinationRate))

                            if self.request_find_home:
                                self.request_find_home=False
                                self.mount_update_wincom.FindHome()

                            self.rapid_park_indicator=copy.deepcopy(self.mount_update_wincom.AtPark)

                            if not self.rapid_park_indicator:
                                if self.can_report_pierside:
                                    self.rapid_pier_indicator=copy.deepcopy(self.mount_update_wincom.sideOfPier)
                                    self.current_tracking_state=self.mount_update_wincom.Tracking
                                    try:
                                        if not (g_dev['mnt'].pier_side_last_check==g_dev['mnt'].rapid_pier_indicator):
                                            self.pier_flip_detected=True
                                            plog ("PIERFLIP DETECTED!")
                                    except:
                                        plog ("missing pier_side_last_check variable probs")
                                        plog(traceback.format_exc())
                                    g_dev['mnt'].pier_side_last_check=copy.deepcopy(self.rapid_pier_indicator)

                            #DIRECT MOUNT POSITION READ #5
                            self.right_ascension_directly_from_mount = copy.deepcopy(self.mount_update_wincom.RightAscension)
                            self.declination_directly_from_mount = copy.deepcopy(self.mount_update_wincom.Declination)
                            #self.sidereal_time_directly_from_mount= copy.deepcopy(self.mount_update_wincom.SiderealTime)
                            self.right_ascension_rate_directly_from_mount = copy.deepcopy(self.mount_update_wincom.RightAscensionRate)
                            self.declination_rate_directly_from_mount = copy.deepcopy(self.mount_update_wincom.DeclinationRate)




                        except:
                            plog ("Issue in normal mount thread")
                            plog(traceback.format_exc())
                        self.mount_updates=self.mount_updates + 1
                        self.mount_update_timer=time.time()

                else:
                    if not self.currently_slewing:
                        time.sleep(self.mount_update_period)

            except Exception as e:
                plog ("some type of glitch in the mount thread: " + str(e))
                plog(traceback.format_exc())
        #END of Mount Update Thread.  Note it spins on the while True. line 446

    def wait_for_slew(self, wait_after_slew=True):
        try:
            actually_slewed=False
            if not g_dev['mnt'].rapid_park_indicator:
                movement_reporting_timer = time.time()
                while g_dev['mnt'].return_slewing():
                    if actually_slewed==False:
                        actually_slewed=True
                    if time.time() - movement_reporting_timer > g_dev['obs'].status_interval:
                        plog('m>')
                        movement_reporting_timer = time.time()
                    # if not g_dev['obs'].currently_updating_status and g_dev['obs'].update_status_queue.empty():
                    g_dev['mnt'].get_mount_coordinates_after_next_update()
                    g_dev['obs'].update_status(mount_only=True, dont_wait=True)#, dont_wait=True)

                # Then wait for slew_time to settle
                if actually_slewed and wait_after_slew:
                    time.sleep(g_dev['mnt'].wait_after_slew_time)

        except: #  Exception as e:
            self.mount_busy=False
            plog("Motion check faulted.")
            plog(traceback.format_exc())
        return

    def return_side_of_pier(self):
        return self.rapid_pier_indicator

    def return_right_ascension(self):
        return self.right_ascension_directly_from_mount

    def return_declination(self):
        return self.declination_directly_from_mount

    def return_slewing(self):
        sleep_period= self.mount_update_period / 4
        current_updates=copy.deepcopy(self.mount_updates)
        while current_updates==self.mount_updates:
            time.sleep(sleep_period)
        return self.currently_slewing

    def return_tracking(self):
        return self.current_tracking_state

    def wait_for_mount_update(self):
        sleep_period= self.mount_update_period / 4
        current_updates=copy.deepcopy(self.mount_updates)
        while current_updates==self.mount_updates:
            time.sleep(sleep_period)

    def set_tracking_on(self):
        if self.return_slewing() == False:
            if self.can_set_tracking:
                if not self.current_tracking_state:
                    self.request_tracking_on = True
                    self.wait_for_mount_update()
                self.current_tracking_state=True
            else:
                #plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
                pass
        return

    def set_tracking_off(self):
        if self.return_slewing() == False:
            if self.can_set_tracking:
                if self.current_tracking_state:
                    self.request_tracking_off = True
                    self.wait_for_mount_update()
                self.current_tracking_state=False
            else:
                pass
                #plog("mount is not tracking but this mount doesn't support ASCOM changing tracking")
        return

    def get_mount_coordinates(self):
        '''
        Build up an ICRS coordinate from mount reported coordinates,
        removing offset and pierside calibrations.  From either flip
        the ICRS coordiate returned should be that of the object
        commanded, hence removing the offsets that are needed to
        position the mount on the axis.

        Returns
        -------
        ra : TYPE
            DESCRIPTION.
        dec : TYPE
            DESCRIPTION.

        '''
        #NB THE mount returns coordinates that are basically J.now, not ICRS 2000
        self.current_icrs_ra = self.right_ascension_directly_from_mount    #May not be applied in positioning
        self.current_icrs_dec = self.declination_directly_from_mount

        return self.current_icrs_ra, self.current_icrs_dec

    def get_mount_coordinates_after_next_update(self):
        '''
        Build up an ICRS coordinate from mount reported coordinates,
        removing offset and pierside calibrations.  From either flip
        the ICRS coordiate returned should be that of the object
        commanded, hence removing the offsets that are needed to
        position the mount on the axis.

        Returns
        -------
        ra : TYPE
            DESCRIPTION.
        dec : TYPE
            DESCRIPTION.

        '''

        self.wait_for_mount_update()
        self.current_icrs_ra = self.right_ascension_directly_from_mount    #May not be applied in positioning
        self.current_icrs_dec = self.declination_directly_from_mount
        return self.current_icrs_ra, self.current_icrs_dec

    def get_mount_rates(self):
        '''
        Build up an ICRS coordinate from mount reported coordinates,
        removing offset and pierside calibrations.  From either flip
        the ICRS coordiate returned should be that of the object
        commanded, hence removing the offsets that are needed to
        position the mount on the axis.
        '''
        self.current_rate_ra = self.right_ascension_rate_directly_from_mount
        self.current_rate_dec = self.declination_rate_directly_from_mount
        return self.current_rate_ra, self.current_rate_dec

    # This is called directly from the obs code to probe for flips, recenter, etc. Hence "directly"
    def slew_async_directly(self, ra, dec):
        self.wait_for_slew(wait_after_slew=False)
        #### Slew to CoordinatesAsync block
        self.slewtoRA = ra
        self.slewtoDEC = dec
        self.slewtoAsyncRequested=True
        self.wait_for_mount_update()
        self.wait_for_slew(wait_after_slew=False)
        ###################################
        g_dev['obs'].rotator_has_been_checked_since_last_slew=False

        self.wait_for_slew(wait_after_slew=False)
        self.get_mount_coordinates()

    def get_status(self):

        if self.currently_creating_status:
            return copy.deepcopy(self.previous_status)

        self.currently_creating_status = True

        if self.tel == False:
            status = {
                'timestamp': round(time.time(), 3),
                'pointing_telescope': self.inst,
                'is_parked': self.rapid_park_indicator,
                'is_tracking': self.current_tracking_state,
                #'is_slewing': self.mount.Slewing,
                'message': self.mount_message[:32]
            }
        elif self.tel == True:
            rd = SkyCoord(ra=self.right_ascension_directly_from_mount*u.hour, dec=self.declination_directly_from_mount*u.deg)
            aa = AltAz(location=self.site_coordinates, obstime=Time.now())
            rd = rd.transform_to(aa)
            alt = float(rd.alt/u.deg)
            az = float(rd.az/u.deg)
            zen = round((90 - alt), 3)
            if zen > 90:
                zen = 90.0
            if zen < 0.1:    #This can blow up when zen <=0!
                new_z = 0.1
            else:
                new_z = zen
            sec_z = 1/cos(radians(new_z))
            airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
            if airmass > 10: airmass = 10.0   # We should caution the user if AM > 2, and alert them if >3
            airmass = round(airmass, 4)
            self.alt= alt
            self.airmass = airmass
            self.az = az
            self.zen = zen

            self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=self.site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            # if abs(self.current_sidereal - self.sidereal_time_directly_from_mount) > 0.0001:
            #     breakpoint()
            #     pass
            if self.prior_roll_rate == 0:
                pass
            ha = self.right_ascension_directly_from_mount - self.current_sidereal
            if ha < 12:
                ha  += 24
            if ha > 12:
                ha -= 24

            try:
                h = self.inverse_icrs_ra
                d = self.inverse_icrs_dec
            except:
                h = 12.    #just to get this initilized
                d = -55.

            #The above routine is not finished and will end up returning ICRS not observed.
            status = {
                'timestamp': round(time.time(), 3),
                'right_ascension': round(h, 4),
                'declination': round(d, 4),
                'sidereal_time': round(self.current_sidereal, 5),  #Should we add HA?
                #'refraction': round(self.refraction_rev, 2),
                'correction_ra': round(self.ha_corr, 4),  #If mount model = 0, these are very small numbers.
                'correction_dec': round(self.dec_corr, 4),
                'hour_angle': round(ha, 3),
                'demand_right_ascension_rate': round(self.prior_roll_rate, 9),   #NB as on 20231113 these rates are basically fixed and static. WER
                'mount_right_ascension_rate': round(self.right_ascension_rate_directly_from_mount, 9),   #Will use sec-RA/sid-sec
                'demand_declination_rate': round(self.prior_pitch_rate, 8),
                'mount_declination_rate': round(self.declination_rate_directly_from_mount, 8),
                'pier_side':self.pier_side,
                'pier_side_str': self.pier_side_str,
                'azimuth': round(az, 3),
                'target_az': round(self.target_az, 3),
                'altitude': round(alt, 3),
                'zenith_distance': round(zen, 3),
                'airmass': round(airmass,4),
                'coordinate_system': str(self.rdsys),
                'pointing_instrument': str(self.inst),
                'message': str(self.mount_message[:54]),
                'move_time': self.move_time,

            }
        else:
            plog('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}






        self.previous_status = copy.deepcopy(status)
        self.currently_creating_status = False
        return copy.deepcopy(status)

    def get_rapid_exposure_status(self, pre):

        pre.append(time.time())
        pre.append(self.current_icrs_ra)
        pre.append(self.current_icrs_dec)
        pre.append(float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle))
        pre.append(0.0)
        pre.append(0.0)
        pre.append(self.az)
        pre.append(self.alt)
        pre.append(self.zen)
        pre.append(self.airmass)
        pre.append(False)
        pre.append(True)
        pre.append(False)
        return copy.deepcopy(pre)

    @classmethod
    def two_pi_avg(cls, pre, post, half):
        if abs(pre - post) > half:
            if pre > half:
                pre = pre - 2*half
            if post > half:
                post = post - 2*half

        avg = (pre + post)/2
        while avg < 0:
            avg = avg + 2*half
        while avg >= 2*half:
            avg = avg - 2*half
        return avg

    def get_average_status(self, pre, post):    #Add HA to this calculation.

        t_avg = round((pre[0] + post[0])/2, 3)
        ra_avg = round(Mount.two_pi_avg(pre[1],  post[1], 12), 6)
        dec_avg = round((pre[2] + post[2])/2, 4)
        sid_avg = round(Mount.two_pi_avg(pre[3],  post[3], 12), 5)
        rar_avg = round((pre[4] + post[4])/2, 6)
        decr_avg = round((pre[5] + post[5])/2, 6)
        az_avg = round(Mount.two_pi_avg(pre[6],  post[6], 180), 3)
        alt_avg = round((pre[7] + post[7])/2, 3)
        zen_avg = round((pre[8] + post[8])/2, 3)
        air_avg = abs(round((pre[9] + post[9])/2, 4))
        if air_avg > 20.0:
            air_avg = 20.0
        if pre[10] and post[10]:
            park_avg = True
        else:
            park_avg = False
        if pre[11] or post[11]:
            track_avg = True
        else:
            track_avg = False
        if pre[12] or post[12]:
            slew_avg = True
        else:
            slew_avg = False

        status = {
            'timestamp': t_avg,
            'right_ascension': ra_avg,
            'declination': dec_avg,
            'sidereal_time': sid_avg,
            'tracking_right_ascension_rate': rar_avg,
            'tracking_declination_rate': decr_avg,
            'azimuth':  az_avg,
            'altitude': alt_avg,
            'zenith_distance': zen_avg,
            'airmass': air_avg,
            'coordinate_system': str(self.rdsys),
            'instrument': str(self.inst),
            'is_parked': park_avg,
            'is_tracking': track_avg,
            'is_slewing': slew_avg,
            'move_time': self.move_time

        }
        return copy.deepcopy(status)

    def parse_command(self, command):

        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "go":
            if 'ra' in req:
                result = self.go_command(ra=req['ra'], dec=req['dec'])   #  Entered from Target Explorer or Telescope tabs.
            elif 'az' in req:
                result = self.go_command(az=req['az'], alt=req['alt'])   #  Entered from Target Explorer or Telescope tabs.
            elif 'ha' in req:
                result = self.go_command(ha=req['ha'], dec=req['dec'])   #  Entered from Target Explorer or Telescope tabs.

            if 'do_centering_routine' in opt and result != 'refused':
                if opt['do_centering_routine']:
                    g_dev['seq'].centering_exposure()

        elif action == "stop":
            self.stop_command(req, opt)

        elif action == 'center_on_pixels':
            if g_dev['obs'].open_and_enabled_to_observe:
                if True:
                    g_dev['obs'].send_to_user("Feature Not Implemented At This Moment.")
                else:
                    plog (command)
                    try:

                        # Need to convert image fraction into offset
                        image_y = req['image_x']
                        image_x = req['image_y']
                        # And the current pixel scale
                        pixscale=float(req['header_pixscale'])
                        pixscale_hours=(pixscale/60/60) / 15
                        pixscale_degrees=(pixscale/60/60)
                        # Calculate the RA and Dec of the pointing
                        center_image_ra=float(req['header_rahrs'])
                        center_image_dec=float(req['header_decdeg'])

                        # y pixel seems to be RA
                        # x pixel seems to be DEC
                        # negative for dec
                        x_center= int(g_dev['cam'].imagesize_x/2)
                        y_center= int(g_dev['cam'].imagesize_y/2)

                        #x_pixel_shift = x_center- ((float(image_x)) * g_dev['cam'].imagesize_x)
                        #y_pixel_shift = y_center- ((float(image_y)) * g_dev['cam'].imagesize_y)
                        x_pixel_shift = x_center- ((float(image_x)) * g_dev['cam'].imagesize_x)
                        y_pixel_shift = y_center- ((float(image_y)) * g_dev['cam'].imagesize_y)
                        plog ("X pixel shift: " + str(x_pixel_shift))
                        plog ("Y pixel shift: " + str(y_pixel_shift))

                        gora=center_image_ra + (y_pixel_shift * pixscale_hours)
                        godec=center_image_dec - (x_pixel_shift * pixscale_degrees)

                        plog ("X centre shift (asec): " + str((x_pixel_shift * pixscale)))
                        plog ("Y centre shift (asec): " + str(((y_pixel_shift * pixscale))))

                        plog ("X centre shift (hours): " + str((x_pixel_shift * pixscale_hours)))
                        plog ("Y centre shift (degrees): " + str(((y_pixel_shift * pixscale_degrees))))
                        #plog ("New RA: " + str(req['ra']))
                        #plog ("New DEC: " + str(req['dec']))

                        #plog ("New RA - Old RA = "+ str(float(req['ra'])-center_image_ra))
                        #plog ("New dec - Old dec = "+ str(float(req['dec'])-center_image_dec))

                        self.wait_for_slew(wait_after_slew=False)

                        #### Slew to CoordinatesAsync block
                        self.slewtoRA = gora
                        self.slewtoDEC = godec
                        self.slewtoAsyncRequested=True
                        self.wait_for_mount_update()
                        self.wait_for_slew(wait_after_slew=False)
                        ###################################
                        g_dev['obs'].rotator_has_been_checked_since_last_slew=False

                        # end mount command #
                        self.wait_for_slew(wait_after_slew=False)
                        self.get_mount_coordinates()

                    except:
                        plog (traceback.format_exc())
                        plog ("seems the image header hasn't arrived at the UI yet, wait a moment")
            else:
                g_dev['obs'].send_to_user("Observatory not open. Center on pixels not done.")
                plog("Observatory not open. Center on pixels not done.")

        elif not ("admin" in command['user_roles']) or ("owner" in command['user_roles']):
            g_dev['obs'].send_to_user("Command not available to non-admins.")


        elif action == "home":
            self.home_command(req, opt)
        elif action == "tracking":
            self.tracking_command(req, opt)
        elif action in ["pivot", 'zero', 'ra=sid, dec=0']:
            ra =  (Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle
            dec = 0.0
            self.go_command(ra=ra, dec=dec, offset=False)
        elif action == "park":
            self.park_command(req, opt)
        elif action == "unpark":
            self.unpark_command(req, opt)
        elif action == 'sky_flat_position':
            g_dev['mnt'].go_command(skyflatspot=True)
        else:
            plog(f"Command <{action}> not recognized.")

    def get_current_times(self):
        self.ut_now = Time(datetime.datetime.now(), scale='utc', location=self.site_coordinates)   #From astropy.time
        self.sid_now_h = self.ut_now.sidereal_time('apparent').value
        self.sid_now_r = self.sid_now_h*HTOR
        iso_day = datetime.date.today().isocalendar()
        self.day = ((iso_day[1]-1)*7 + (iso_day[2] ))
        self.equinox_now = 'J' +str(round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2))
        return

    def flat_spot_now(self):
        '''
        Return a tuple with the (az, alt) of the flattest part of the sky.
        '''
        # Current Frame
        altazframe=AltAz(obstime=Time.now(), location=self.site_coordinates)
        sun_coords=get_sun(Time.now()).transform_to(altazframe)

        sun_alt=sun_coords.alt.degree
        sun_az=sun_coords.az.degree
        flatspot_az = sun_az - 180.  # Opposite az of the Sun
        if flatspot_az < 0:
            flatspot_az += 360.
        flatspot_alt = sun_alt + 105  # 105 degrees along great circle through zenith
        if flatspot_alt > 90:   # Over the zenith so specify alt at above azimuth
            flatspot_alt = 180 - flatspot_alt
        if flatspot_alt < 90 and sun_alt < -15:
            flatspot_az = sun_az
        self.flatspot_alt=flatspot_alt
        self.flatspot_az=flatspot_az
        return(flatspot_alt, flatspot_az)

    ###############################
    #        Mount Commands       #
    ###############################


    def sync_to_pointing(self, syncToRA, syncToDec):

        self.syncToRA=syncToRA
        self.syncToDEC=syncToDec
        self.sync_mount_requested=True
        plog ("Mount synced to : " + str(syncToRA) + " " + str(syncToDec))
        self.wait_for_mount_update()



    '''
    This is the standard go to that does not establish and tracking for refraction or
    envoke the mount model.

    '''

    def go_command(self, skyflatspot=None, ra=None, dec=None, az=None, alt=None, ha=None, \
                   objectname=None, offset=False, calibrate=False, auto_center=False, \
                   silent=False, skip_open_test=False,tracking_rate_ra = 0, \
                   tracking_rate_dec =  0, do_centering_routine=False, dont_wait_after_slew=False):

        ''' Slew to the given ra/dec, alt/az or ha/dec or skyflatspot coordinates. '''

        # First thing to do is check the position of the sun and
        # Whether this violates the pointing principle.
        try:
            sun_coords=get_sun(Time.now())
            if skyflatspot != None:
                if not skip_open_test:
                    if (not (g_dev['events']['Cool Down, Open'] < ephem.now() < g_dev['events']['Naut Dusk']) and \
                        not (g_dev['events']['Naut Dawn'] < ephem.now() < g_dev['events']['Close and Park'])):
                        g_dev['obs'].send_to_user("Refusing skyflat pointing request as it is outside skyflat time")
                        plog("Refusing pointing request as it is outside of skyflat pointing time.")
                        return 'refused'

                    if g_dev['obs'].open_and_enabled_to_observe==False :
                        g_dev['obs'].send_to_user("Refusing skyflat pointing request as the observatory is not enabled to observe.")
                        plog("Refusing skyflat pointing request as the observatory is not enabled to observe.")
                        return 'refused'

                alt, az = self.flat_spot_now()
                temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)
                altazskycoord=SkyCoord(alt=alt*u.deg, az=az*u.deg, obstime=Time.now(), location=self.site_coordinates, frame='altaz')
                ra = altazskycoord.icrs.ra.deg /15
                dec = altazskycoord.icrs.dec.deg

                plog ("Moving to requested Flat Spot, az: " + str(round(az,1)) + " alt: " + str(round(alt,1)))

                if self.config['degrees_to_avoid_zenith_area_for_calibrations'] > 0:
                    if (90-alt) < self.config['degrees_to_avoid_zenith_area_for_calibrations']:
                        g_dev['obs'].send_to_user("Refusing skyflat pointing request as it is too close to the zenith for this scope.")
                        plog("Refusing skyflat pointing request as it is too close to the zenith for this scope.")
                        return 'refused'
            #NB the following code needs to deal with other reference frames...
            elif ra != None:   #implying RA and Dec are supplied. Compute resulting altitude
                ra = float(ra)
                dec = float(dec)
                temppointing=SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
                temppointingaltaz=temppointing.transform_to(AltAz(location=self.site_coordinates, obstime=Time.now()))
                alt = temppointingaltaz.alt.degree
                az = temppointingaltaz.az.degree

            elif az != None:
                az = float(az)
                alt = float(alt)
                temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)
                altazskycoord=SkyCoord(alt=alt*u.deg, az=az*u.deg, obstime=Time.now(), location=self.site_coordinates, frame='altaz')
                ra = altazskycoord.icrs.ra.deg /15
                dec = altazskycoord.icrs.dec.deg
            elif ha != None:   #NB need to convert HA to an RA then proceed as if RA and DEC were supplied.
                ha = float(ha)
                dec = float(dec)
                az, alt = self.transform_haDec_to_azAlt(ha, dec)
                temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)
                altazskycoord=SkyCoord(alt=alt*u.deg, az=az*u.deg, obstime=Time.now(), location=self.site_coordinates, frame='altaz')
                ra = altazskycoord.icrs.ra.deg /15
                dec = altazskycoord.icrs.dec.deg
        except:
            plog("something went wrong dealing with coordinates")
            plog (traceback.format_exc())
            return 'refused'

        sun_dist = sun_coords.separation(temppointing)
        if g_dev['obs'].sun_checks_on:
            if sun_dist.degree <  self.config['closest_distance_to_the_sun'] and g_dev['obs'].open_and_enabled_to_observe:
                if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                    g_dev['obs'].send_to_user("Refusing pointing request as it is too close to the sun: " + str(sun_dist.degree) + " degrees.")
                    plog("Refusing pointing request as it is too close to the sun: " + str(sun_dist.degree) + " degrees.")
                    return 'refused'

        # Second thing, check that we aren't pointing at the moon
        # UNLESS we have actually chosen to look at the moon.
        if g_dev['obs'].moon_checks_on:
            if self.object in ['Moon', 'moon', 'Lune', 'lune', 'Luna', 'luna',]:
                plog("Moon Request detected")
            else:
                moon_coords=get_moon(Time.now())
                moon_dist = moon_coords.separation(temppointing)
                if moon_dist.degree <  self.config['closest_distance_to_the_moon']:
                    g_dev['obs'].send_to_user("Refusing pointing request as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                    plog("Refusing pointing request as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                    return 'refused'

        # Third thing, check that the requested coordinates are not
        # below a reasonable altitude
        if g_dev['obs'].altitude_checks_on:
            if alt < self.config['lowest_requestable_altitude']:
                g_dev['obs'].send_to_user("Refusing pointing request as it is too low: " + str(alt) + " degrees.")
                plog("Refusing pointing request as it is too low: " + str(alt) + " degrees.")
                return 'refused'

        # Fourth thing, check that the roof is open and we are enabled to observe
        if (g_dev['obs'].open_and_enabled_to_observe==False )  and not g_dev['obs'].scope_in_manual_mode:
            g_dev['obs'].send_to_user("Refusing pointing request as the observatory is not enabled to observe.")
            plog(g_dev['obs'].open_and_enabled_to_observe)
            plog("Refusing pointing request as the observatory is not enabled to observe.")
            return 'refused'

        if objectname != None:
            self.object = objectname
        else:
            self.object = 'unspecified'    #NB could possibly augment with "Near --blah--"

        self.unpark_command()   #can we qualify this?


        if self.object in ['Moon', 'moon', 'Lune', 'lune', 'Luna', 'luna',]:
            self.obs.date = ephem.now()
            moon = ephem.Moon()
            moon.compute(self.obs)
            ra1, dec1 = moon.ra*RTOH, moon.dec*RTOD
            self.obs.date = ephem.Date(ephem.now() + 1/144)   #  10 minutes
            moon.compute(self.obs)
            ra2, dec2 = moon.ra*RTOH, moon.dec*RTOD
            dra_moon = (ra2 - ra1)*15*3600/600
            ddec_moon = (dec2 - dec1)*3600/600
            ra=ra1
            dec=dec1
            tracking_rate_ra=dra_moon
            tracking_rate_dec = ddec_moon

        # During flats the scope is so continuously nudged as to make reporting of nudges meaningless... so don't report.
        if not skyflatspot:
            if self.object == "":
                if not silent:
                    g_dev['obs'].send_to_user("Slewing telescope to un-named target!  ",  p_level="INFO")
            else:
                if not silent:
                    g_dev['obs'].send_to_user("Slewing telescope to:  " + str( self.object),  p_level="INFO")

        self.last_ra_requested = ra
        self.last_dec_requested = dec
        self.last_tracking_rate_ra = tracking_rate_ra
        self.last_tracking_rate_dec = tracking_rate_dec
        self.last_seek_time = time.time() - 5000

        self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        self.previous_pier_side=self.rapid_pier_indicator

        plog ("RA and Dec pre icrs to mech: " + str(round(ra,6))+ " " + str(round(dec,6)))

        ###################################### HERE IS WHERE THE NEW WAYNE STUFF SHOULD GO


        #Here is the point for slewing the telescope.  There is a lot
        #to sort out here.  Incoming coordinates are assumed to be
        #ICRS2000.0.  There are conversions to Apparent, then Observed
        #(refraction) then to mechanical (mount-modeled) coordinates and
        #velocities.  The status loop needs to process the opposite
        #direction: from Mount to ICRS and from time to time to update
        #the velocities.  If all this is computed correctly the drift
        #rate should be minimal.

        #Below we need to be sure we have the right pierside predicted for the seek that is about to happen.
        #self.mech_ra, self.mech_dec, self.roll_rate, self.pitch_rate= self.transform_icrs_to_mechanical(self.slewtoRA, self.slewtoDEC, self.rapid_pier_indicator, loud=False, enable=False)
        #self.mech_ra, self.mech_dec, self.roll_rate, self.pitch_rate= self.transform_icrs_to_mechanical(ra, dec, self.rapid_pier_indicator, loud=False, enable=False)
        #ra, dec, self.roll_rate, self.pitch_rate= self.transform_icrs_to_mechanical(ra, dec, self.rapid_pier_indicator, loud=False, enable=False)
        if self.model_on:
            ra, dec, roll_rate, pitch_rate = self.transform_icrs_to_mechanical(ra, dec, self.rapid_pier_indicator)
            #Above  we need to decide where to update the rates after a seek




            if self.CanSetRightAscensionRate:
                self.request_set_RightAscensionRate=True
                self.request_new_RightAscensionRate=roll_rate


            if self.CanSetDeclinationRate:
                self.request_set_DeclinationRate=True
                self.request_new_DeclinationRate=pitch_rate

            ############################################################################## NEW WAYNE BARRIER WALL


            plog ("RA and Dec post icrs to mech: " + str(round(ra,6))+ " " + str(round(dec,6)))
            plog ("Roll Rate: " + str(roll_rate))
            plog ("Pitch Rate: " + str(pitch_rate))


        # Don't need a mount reference for skyflatspots!
        if not skyflatspot and not g_dev['obs'].mount_reference_model_off:

            if self.can_report_destination_pierside == True:
                try:
                    self.request_new_pierside=True
                    self.request_new_pierside_ra=ra
                    self.request_new_pierside_dec=dec
                    self.wait_for_mount_update()
                    if len(self.new_pierside) > 1:
                        if self.new_pierside[0] == 0:
                            delta_ra, delta_dec = self.get_mount_reference(ra,dec)
                        else:
                            delta_ra, delta_dec = self.get_flip_reference(ra,dec)
                except:
                    try:
                        self.request_new_pierside=True
                        self.request_new_pierside_ra=ra
                        self.request_new_pierside_dec=dec
                        self.wait_for_mount_update()
                        if self.new_pierside == 0:
                            delta_ra, delta_dec = self.get_mount_reference(ra,dec)
                        else:
                            delta_ra, delta_dec = self.get_flip_reference(ra,dec)
                    except:
                        self.mount_busy=False
                        delta_ra, delta_dec = self.get_mount_reference(ra,dec)
            else:
                if self.previous_pier_side == 0:
                    delta_ra, delta_dec = self.get_mount_reference(ra,dec)
                else:
                    delta_ra, delta_dec = self.get_flip_reference(ra,dec)




            if not g_dev['obs'].mount_reference_model_off:
                plog ("Reference used for mount deviation in go_command")
                plog (str(delta_ra*15* 60) + " RA (Arcmins), " + str(delta_dec*60) + " Dec (Arcmins)")

                ra = ra + delta_ra
                dec = dec + delta_dec
        else:
            delta_ra=0
            delta_dec=0





        # First move, then check the pier side
        successful_move=0
        while successful_move==0:
            try:
                self.wait_for_slew(wait_after_slew=False)
                g_dev['obs'].time_of_last_slew=time.time()
                g_dev['mnt'].last_slew_was_pointing_slew = True
                if ra < 0:
                    ra=ra+24
                if ra > 24:
                    ra=ra-24
                #### Slew to CoordinatesAsync block
                self.slewtoRA = ra
                self.slewtoDEC = dec
                self.slewtoAsyncRequested=True
                self.wait_for_mount_update()
                if not dont_wait_after_slew:
                    self.wait_for_slew(wait_after_slew=False)
                ###################################
                g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                if not dont_wait_after_slew:
                    self.wait_for_slew(wait_after_slew=False)
                self.get_mount_coordinates()
            except Exception:
                self.mount_busy=False
                # This catches an occasional ASCOM/TheSkyX glitch and gets it out of being stuck
                # And back on tracking.
                try:
                    retry=0
                    while retry <3:
                        try:
                            if g_dev['mnt'].theskyx:
                                plog (traceback.format_exc())
                                #breakpoint()
                                plog("The SkyX had an error.")
                                plog("Usually this is because of a broken connection.")
                                plog("Killing then waiting 60 seconds then reconnecting")
                                g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                                self.unpark_command()
                                self.wait_for_slew(wait_after_slew=False)
                                if ra < 0:
                                    ra=ra+24
                                if ra > 24:
                                    ra=ra-24
                                #### Slew to CoordinatesAsync block
                                self.slewtoRA = ra
                                self.slewtoDEC = dec
                                self.slewtoAsyncRequested=True
                                self.wait_for_mount_update()
                                self.wait_for_slew(wait_after_slew=False)
                                ###################################
                                g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                                self.wait_for_slew(wait_after_slew=False)
                                self.get_mount_coordinates()
                                retry=4
                            else:
                                plog (traceback.format_exc())
                        except:
                            self.mount_busy=False
                            time.sleep(120)
                            retry=retry+1
                except:
                    self.mount_busy=False
                    plog (traceback.format_exc())

            g_dev["mnt"].pier_side=self.rapid_pier_indicator
            if self.previous_pier_side == g_dev["mnt"].pier_side or self.can_report_destination_pierside:
                successful_move=1
            else:
                # if g_dev['obs'].mount_reference_model_off:
                #     pass
                # else:
                #     ra=self.last_ra_requested + delta_ra
                #     dec=self.last_dec_requested + delta_dec


                if ra < 0:
                    ra=ra+24
                if ra > 24:
                    ra=ra-24
                self.wait_for_slew(wait_after_slew=False)
                g_dev['mnt'].last_slew_was_pointing_slew = True
                #### Slew to CoordinatesAsync block
                self.slewtoRA = ra
                self.slewtoDEC = dec
                self.slewtoAsyncRequested=True
                self.wait_for_mount_update()
                if not dont_wait_after_slew:
                    self.wait_for_slew(wait_after_slew=False)
                ###################################
                g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                if not dont_wait_after_slew:
                    self.wait_for_slew(wait_after_slew=False)
                self.get_mount_coordinates()
                successful_move=1


        if not self.current_tracking_state:
            try:
                if not dont_wait_after_slew:
                    self.wait_for_slew(wait_after_slew=False)
                    self.set_tracking_on()
            except Exception:
                # Yes, this is an awfully non-elegant way to force a mount to start
                # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
                # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter
                self.mount_busy=False
                if "Property write Tracking is not implemented in this driver" in str(traceback.format_exc()):
                    pass
                elif g_dev['mnt'].theskyx:
                    plog (traceback.format_exc())
                    plog("The SkyX had an error.")
                    plog("Usually this is because of a broken connection.")
                    plog("Killing then waiting 60 seconds then reconnecting")
                    g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                    self.unpark_command()
                    self.wait_for_slew(wait_after_slew=False)
                    if ra < 0:
                        ra=ra+24
                    if ra > 24:
                        ra=ra-24

                    #### Slew to CoordinatesAsync block
                    self.slewtoRA = ra
                    self.slewtoDEC = dec
                    self.slewtoAsyncRequested=True
                    self.wait_for_mount_update()
                    self.wait_for_slew(wait_after_slew=False)
                    ###################################
                    g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                    self.wait_for_slew(wait_after_slew=False)
                    self.get_mount_coordinates()

                else:
                    plog (traceback.format_exc())

        g_dev['obs'].time_of_last_slew=time.time()
        g_dev['obs'].time_since_last_slew = time.time()
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000
        if not dont_wait_after_slew:
            self.wait_for_slew(wait_after_slew=False)


        #g_dev['obs'].drift_tracker_ra=0
        #g_dev['obs'].drift_tracker_dec=0
        g_dev['obs'].drift_tracker_timer=time.time()

        if not silent and not skyflatspot:
            g_dev['obs'].send_to_user("Slew Complete.")

        if do_centering_routine:
            g_dev['seq'].centering_exposure()


        self.previous_pier_side=self.rapid_pier_indicator

    # def go_w_model_and_velocity(self, ra, dec, tracking_rate_ra=0, tracking_rate_dec=0, reset_solve=True):  #Note these rates need a system specification
    #     '''
    #     NB NB NB THis is new-old code having to do with supporting velocity and pointing
    #     correction for refraction and the installed mount model.  IF Model_on and
    #     refr_on are False this code defaults to use the go-command routine above.

    #     Slew to the given ra/dec coordinates, supplied in ICRS
    #     Note no dependency on current position.
    #     unpark the telescope mount
    #     '''  #  NB can we check if unparked and save time?

    #     breakpoint()  #WE SHOULD NOT GET HERE!  JUST CHECKING -WER
    #     self.last_ra = ra
    #     self.last_dec = dec
    #     self.last_tracking_rate_ra = tracking_rate_ra
    #     self.last_tracking_rate_dec = tracking_rate_dec
    #     self.last_seek_time = time.time()

    #     #
    #     #self.unpark_command()
    #     #Note this initiates a mount move.  WE should Evaluate if the destination is on the flip side and pick up the
    #     #flip offset.  So a GEM could track into positive HA territory without a problem but the next reseek should
    #     #result in a flip.  So first figure out if there will be a flip:
    #     try:
    #         try:
    #             self.request_new_pierside=True
    #             self.request_new_pierside_ra=ra
    #             self.request_new_pierside_dec=dec

    #             self.wait_for_mount_update()

    #             if len(self.new_pierside) > 1:
    #                 if self.new_pierside[0] == 0:
    #                     delta_ra, delta_dec = self.get_mount_reference(ra,dec)
    #                     pier_east = 1
    #                 else:
    #                     delta_ra, delta_dec = self.get_flip_reference(ra,dec)
    #                     pier_east = 0
    #         except:
    #             try:
    #                 self.request_new_pierside=True
    #                 self.request_new_pierside_ra=ra
    #                 self.request_new_pierside_dec=dec

    #                 self.wait_for_mount_update()

    #                 if self.new_pierside == 0:
    #                     delta_ra, delta_dec = self.get_mount_reference(ra,dec)
    #                     pier_east = 1
    #                 else:
    #                     delta_ra, delta_dec = self.get_flip_reference(ra,dec)
    #                     pier_east = 0
    #             except:
    #                 self.mount_busy=False
    #                 delta_ra, delta_dec = self.get_mount_reference(ra,dec)
    #                 pier_east = 1
    #     except Exception as e:
    #         self.mount_busy=False
    #         plog ("mount really doesn't like pierside calls ", e)
    #         pier_east = 1
    #       #Update incoming ra and dec with mounting offsets.

    #     # plog ("delta")
    #     # plog (delta_ra)
    #     # ra += delta_ra #NB it takes a restart to pick up a new correction which is also J.now.
    #     # dec += delta_dec
    #     # ra, dec = ra_dec_fix_h(ra,dec)
    #     breakpoint()
    #     if self.EquatorialSystem == 1:  #ie., equTopocentric input to the telescope
    #         self.get_current_times()   #  NB We should find a way to refresh this once a day, esp. for status return.
    #         #  Input is meant to be IRCS, so change to that Astropy type;
    #         icrs_coord = SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
    #         jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
    #         ra = jnow_coord.ra.hour
    #         dec = jnow_coord.dec.degree

    #         if self.offset_received:
    #             ra += self.ra_offset          #Offsets are J.now and used to get target on Browser Crosshairs.
    #             dec += self.dec_offset
    #     ra_app_h, dec_app_d = ra_dec_fix_h(ra, dec)
    #     #'This is the "Forward" calculation of pointing.
    #     #Here we add in refraction and the TPOINT compatible mount model

    #     self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
    #     #Cosider adding a comparision with Sid time as reported by telescope.
    #     self.sid_now_r = self.current_sidereal*HTOR   #NB NB ADDED THIS FOR SRO, WHY IS THIS NEEDED?

    #     self.ha_obs_r, self.dec_obs_r, self.refr_asec = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_now_r)
    #     #ra_obs_r, dec_obs_r = ptr_utility.transformHatoRaDec(ha_obs_r, dec_obs_r, self.sid_now_r)
    #     #Here we would convert to model and calculate tracking rate correction.
    #     self.ha_mech, self.dec_mech = ptr_utility.transform_observed_to_mount_r(self.ha_obs_r, self.dec_obs_r, pier_east, loud=False, enable=True)
    #     self.ra_mech, self.dec_mech = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech, self.dec_mech, self.sid_now_r)
    #     self.ha_corr = ptr_utility.reduce_ha_r(self.ha_mech -self. ha_obs_r)*RTOS
    #     self.dec_corr = ptr_utility.reduce_dec_r(self.dec_mech - self.dec_obs_r)*RTOS


    #     if not self.current_tracking_state:
    #         try:
    #             self.wait_for_slew(wait_after_slew=False)
    #             self.set_tracking_on()
    #         except Exception as e:
    #             self.mount_busy=False
    #             # Yes, this is an awfully non-elegant way to force a mount to start
    #             # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
    #             # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter
    #             if ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues < 5:
    #                 self.theskyx_tracking_rescues=self.theskyx_tracking_rescues + 1
    #                 self.home_command()
    #                 self.park_command()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 self.unpark_command()
    #                 self.wait_for_slew(wait_after_slew=False)

    #                 #### Slew to CoordinatesAsync block
    #                 self.slewtoRA = self.ra_mech*RTOH
    #                 self.slewtoDEC = self.dec_mech*RTOD
    #                 self.slewtoAsyncRequested=True
    #                 self.wait_for_mount_update()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 ###################################

    #                 g_dev['obs'].rotator_has_been_checked_since_last_slew=False

    #                 self.wait_for_slew(wait_after_slew=False)
    #                 self.get_mount_coordinates()
    #                 plog ("this mount may not accept tracking commands")
    #             elif ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues >= 5:
    #                 plog ("theskyx has been rescued one too many times. Just sending it to park.")
    #                 self.park_command()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 return
    #             else:
    #                 plog ("problem with setting tracking: ", e)


    #     self.move_time = time.time()
    #     az, alt = ptr_utility.transform_haDec_to_azAlt_r(self.ha_mech, self.dec_mech, self.latitude_r)
    #     plog('MODEL HA, DEC, AZ, Refraction:  (asec)  ', self.ha_corr, self.dec_corr, az*RTOD, self.refr_asec)
    #     self.target_az = az*RTOD

    #     self.wait_for_slew(wait_after_slew=False)
    #     try:

    #         #### Slew to CoordinatesAsync block
    #         self.slewtoRA = self.ra_mech*RTOH
    #         self.slewtoDEC = self.dec_mech*RTOD
    #         self.slewtoAsyncRequested=True
    #         self.wait_for_mount_update()
    #         self.wait_for_slew(wait_after_slew=False)
    #         ###################################
    #         g_dev['obs'].rotator_has_been_checked_since_last_slew=False
    #         self.wait_for_slew(wait_after_slew=False)
    #         self.get_mount_coordinates()
    #     except Exception as e:
    #         self.mount_busy=False
    #         # This catches an occasional ASCOM/TheSkyX glitch and gets it out of being stuck
    #         # And back on tracking.
    #         if ('Object reference not set to an instance of an object.' in str(e)):
    #             self.home_command()
    #             self.park_command()
    #             self.wait_for_slew(wait_after_slew=False)
    #             self.unpark_command()
    #             self.wait_for_slew(wait_after_slew=False)
    #             #### Slew to CoordinatesAsync block
    #             self.slewtoRA = self.ra_mech*RTOH
    #             self.slewtoDEC = self.dec_mech*RTOD
    #             self.slewtoAsyncRequested=True
    #             self.wait_for_mount_update()
    #             self.wait_for_slew(wait_after_slew=False)
    #             ###################################
    #             g_dev['obs'].rotator_has_been_checked_since_last_slew=False
    #             self.wait_for_slew(wait_after_slew=False)
    #             self.get_mount_coordinates()

    #     if not self.current_tracking_state:
    #         try:
    #             self.wait_for_slew(wait_after_slew=False)
    #             self.set_tracking_on()
    #         except Exception as e:
    #             self.mount_busy=False
    #             # Yes, this is an awfully non-elegant way to force a mount to start
    #             # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
    #             # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter
    #             if ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues < 5:
    #                 self.theskyx_tracking_rescues=self.theskyx_tracking_rescues + 1
    #                 self.park_command()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 self.unpark_command()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 #### Slew to CoordinatesAsync block
    #                 self.slewtoRA = self.ra_mech*RTOH
    #                 self.slewtoDEC = self.dec_mech*RTOD
    #                 self.slewtoAsyncRequested=True
    #                 self.wait_for_mount_update()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 ###################################
    #                 g_dev['obs'].rotator_has_been_checked_since_last_slew=False
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 self.get_mount_coordinates()
    #                 plog ("this mount may not accept tracking commands")
    #             elif ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues >= 5:
    #                 plog ("theskyx has been rescued one too many times. Just sending it to park.")
    #                 self.park_command()
    #                 self.wait_for_slew(wait_after_slew=False)
    #                 return
    #             else:
    #                 plog ("problem with setting tracking: ", e)

    #     g_dev['obs'].time_since_last_slew_or_exposure = time.time()
    #     g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
    #     g_dev['obs'].images_since_last_solve = 10000
    #     self.wait_for_slew(wait_after_slew=False)

    #     ###  figure out velocity  Apparent place is unchanged.
    #     self.sid_next_r = (self.sid_now_h + self.delta_t_s*STOH)*HTOR    #delta_t_s is five minutes
    #     self.ha_obs_adv, self.dec_obs_adv, self.refr_adv = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_next_r)   #% minute advance
    #     self.ha_mech_adv, self.dec_mech_adv = ptr_utility.transform_observed_to_mount_r(self.ha_obs_adv, self.dec_obs_adv, pier_east, loud=False)
    #     self.ra_adv, self.dec_adv = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech_adv, self.dec_mech_adv, self.sid_next_r)
    #     self.adv_ha_corr = ptr_utility.reduce_ha_r(self.ha_mech_adv - self.ha_obs_adv)*RTOS     #These are mechanical values, not j.anything
    #     self.adv_dec_corr = ptr_utility.reduce_dec_r(self.dec_mech_adv - self.dec_obs_adv)*RTOS
    #     self.prior_seek_ha_h = self.ha_mech
    #     self.prior_seek_dec_d = self.dec_mech
    #     self.prior_seek_time = time.time()
    #     self.prior_sid_time =  self.sid_now_r
    #     '''
    #     The units of this property are arcseconds per SI (atomic) second.
    #     Please note that for historic reasons the units of the
    #     RightAscensionRate property are seconds of RA per sidereal second.
    #     '''
    #     if self.CanSetRightAscensionRate:
    #         self.prior_roll_rate = -((self.ha_mech_adv - self. ha_mech)*RTOS*MOUNTRATE/self.delta_t_s - MOUNTRATE)/(APPTOSID*15)    #Conversion right 20219329

    #         self.request_set_RightAscensionRate=True
    #         self.request_new_RightAscensionRate=0.0
    #         self.wait_for_mount_update()

    #     else:
    #         self.prior_roll_rate = 0.0

    #     if self.CanSetDeclinationRate:
    #        self.prior_pitch_rate = -(self.dec_mech_adv - self.dec_mech)*RTOS/self.delta_t_s    #20210329 OK 1 hour from zenith.  No Appsid correction per ASCOM spec.

    #        self.request_set_DeclinationRate=True
    #        self.request_new_DeclinationRate=self.prior_pitch_rate
    #        self.wait_for_mount_update()

    #        #plog("Rates, refr are:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_asec)
    #     else:
    #         self.prior_pitch_rate = 0.0
    #     #plog(self.prior_roll_rate, self.prior_pitch_rate, refr_asec)
    #     # time.sleep(.5)

    #     if self.CanSetRightAscensionRate:
    #         self.request_set_RightAscensionRate=True
    #         self.request_new_RightAscensionRate=0.0
    #         self.wait_for_mount_update()


    #     if self.CanSetDeclinationRate:
    #         self.request_set_DeclinationRate=True
    #         self.request_new_DeclinationRate=self.prior_pitch_rate
    #         self.wait_for_mount_update()

    #     plog("Rates set:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_adv)

    #     # On successful movement of telescope reset the solving timer
    #     if reset_solve == True:
    #         g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
    #         g_dev['obs'].images_since_last_solve = 10000
    #     self.wait_for_slew(wait_after_slew=False)

    def stop_command(self, req, opt):
        plog("mount cmd: stopping mount")

        self.abort_slew_requested=True
        self.wait_for_mount_update()

    def home_command(self, req=None, opt=None):
        ''' slew to the home position '''
        plog("mount cmd: homing mount")
        self.parking_or_homing=True
        if self.CanFindHome:
            self.find_home_requested=True
            self.wait_for_mount_update()
            g_dev['obs'].rotator_has_been_checked_since_last_slew=False
            self.wait_for_slew(wait_after_slew=False)
            self.get_mount_coordinates()
        else:
            plog("Mount is not capable of finding home. Slewing to home_alt and home_az")
            self.move_time = time.time()
            home_alt = self.settings["home_altitude"]
            home_az = self.settings["home_azimuth"]
            g_dev['obs'].time_of_last_slew=time.time()
            g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True, skyflatspot=True)

            self.wait_for_slew(wait_after_slew=False)
        self.wait_for_slew(wait_after_slew=False)
        self.parking_or_homing=False

    def flat_panel_command(self, req, opt):
        ''' slew to the flat panel if it exists '''
        plog("mount cmd: slewing to flat panel")
        pass

    def park_command(self, req=None, opt=None):
        ''' park the telescope mount '''
        if self.can_park:
            self.parking_or_homing=True
            sleep_period= self.mount_update_period / 4
            current_updates=copy.deepcopy(self.mount_updates)
            while current_updates==self.mount_updates:
                time.sleep(sleep_period)
            if not self.rapid_park_indicator:
                plog("mount cmd: parking mount")
                if g_dev['obs'] is not None:  #THis gets called before obs is created
                    g_dev['obs'].send_to_user("Parking Mount. This can take a moment.")
                g_dev['obs'].time_of_last_slew=time.time()
                self.wait_for_slew(wait_after_slew=False)
                self.park_requested=True
                sleep_period= self.mount_update_period / 4
                current_updates=copy.deepcopy(self.mount_updates)
                while current_updates==self.mount_updates:
                    time.sleep(sleep_period)

                g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                self.rapid_park_indicator=True
                self.wait_for_slew(wait_after_slew=False)
                if self.settle_time_after_park > 0:
                    time.sleep(self.settle_time_after_park)
                    plog("Waiting " + str(self.settle_time_after_park) + " seconds for mount to settle.")
            try:
                g_dev['fil'].current_filter, _, _ = g_dev["fil"].set_name_command(
                    {"filter": 'dk'}, {}
                )
            except:
                pass
            self.parking_or_homing=False

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''

        if self.can_park:
            self.parking_or_homing=True
            sleep_period= self.mount_update_period / 4
            current_updates=copy.deepcopy(self.mount_updates)
            while current_updates==self.mount_updates:
                time.sleep(sleep_period)

            if self.rapid_park_indicator:
                plog("mount cmd: unparking mount")
                g_dev['obs'].send_to_user("Unparking Mount. This can take a moment.")
                g_dev['obs'].time_of_last_slew=time.time()
                self.unpark_requested=True
                sleep_period= self.mount_update_period / 4
                current_updates=copy.deepcopy(self.mount_updates)
                while current_updates==self.mount_updates:
                    time.sleep(sleep_period)

                g_dev['obs'].rotator_has_been_checked_since_last_slew=False

                self.rapid_park_indicator=False
                self.wait_for_slew(wait_after_slew=False)

                if self.settle_time_after_unpark > 0:
                    time.sleep(self.settle_time_after_unpark)
                    plog("Waiting " + str(self.settle_time_after_unpark) + " seconds for mount to settle.")

                if self.home_after_unpark:
                    try:
                        self.wait_for_slew(wait_after_slew=False)
                        self.request_find_home=True
                        self.wait_for_mount_update()
                        g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                        self.wait_for_slew(wait_after_slew=False)
                    except:
                        try:
                            home_alt = self.settings["home_altitude"]
                            home_az = self.settings["home_azimuth"]
                            self.wait_for_slew(wait_after_slew=False)
                            g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True, skyflatspot=True)
                            self.wait_for_slew(wait_after_slew=False)
                        except:
                            if g_dev['mnt'].theskyx:

                                plog("The SkyX had an error.")
                                plog("Usually this is because of a broken connection.")
                                plog("Killing then waiting 60 seconds then reconnecting")
                                g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                                self.unpark_command()
                                g_dev['obs'].rotator_has_been_checked_since_last_slew=False
                                self.rapid_park_indicator=False
                                self.wait_for_slew(wait_after_slew=False)
                                home_alt = self.settings["home_altitude"]
                                home_az = self.settings["home_azimuth"]
                                g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True, skyflatspot=True)
                            else:
                                plog (traceback.format_exc())
                    self.wait_for_slew(wait_after_slew=False)
            self.parking_or_homing=False


    def record_mount_reference(self, deviation_ha, deviation_dec, pointing_ra, pointing_dec):

        # The HA is for the actual requested HA, NOT the solved ra
        HA=self.current_sidereal - pointing_ra + deviation_ha

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1' + str(g_dev['obs'].name))
        mnt_shelf['ra_cal_offset'] = deviation_ha
        mnt_shelf['dec_cal_offset'] = deviation_dec
        mnt_shelf['last_mount_reference_time']=time.time()
        mnt_shelf['last_mount_reference_ha']= HA
        mnt_shelf['last_mount_reference_dec']= pointing_dec + deviation_dec

        self.last_mount_reference_time=time.time()
        self.last_mount_reference_ha = HA
        self.last_mount_reference_dec = pointing_dec
        self.last_mount_reference_ha_offset =  deviation_ha
        self.last_mount_reference_dec_offset =  deviation_dec


        #breakpoint()
        # Add in latest point to the list of mount references
        # This has to be done in terms of hour angle due to changes over time.
        # We need to store time, HA, Dec, HA offset, Dec offset.
        #HA=self.current_sidereal - pointing_ra + deviation_ha
        # Removing older references
        counter=0
        deleteList=[]
        for entry in self.longterm_storage_of_mount_references:
            distance_from_new_reference= abs((entry[1] -HA) * 15) + abs(entry[2] - pointing_dec+deviation_dec)
            if distance_from_new_reference < 2:
                plog ("Found and removing an old reference close to new reference: " + str(entry))
                #self.longterm_storage_of_mount_references.remove(entry)
                deleteList.append(counter)
            counter=counter+1
        for index in sorted(deleteList, reverse=True):
            del self.longterm_storage_of_mount_references[index]
        plog ("Deviation in mount reference: HA: " + str(deviation_ha) + " Dec: " + str(deviation_dec))
        plog ("Recording and using new mount reference: HA: " + str(deviation_ha) + " arcminutes, Dec: " + str(deviation_dec) + " arcminutes." )

        self.longterm_storage_of_mount_references.append([time.time(),HA,pointing_dec + deviation_dec , deviation_ha,  deviation_dec])
        mnt_shelf['longterm_storage_of_mount_references']=self.longterm_storage_of_mount_references
        mnt_shelf.close()

        return

    def record_flip_reference(self, deviation_ha, deviation_dec, pointing_ra, pointing_dec):

        # The HA is for the actual requested HA, NOT the solved ra
        HA=self.current_sidereal - pointing_ra + deviation_ha

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        mnt_shelf['flip_ra_cal_offset'] = deviation_ha    #NB NB NB maybe best to reverse signs here??
        mnt_shelf['flip_dec_cal_offset'] = deviation_dec
        mnt_shelf['last_flip_reference_time']=time.time()
        mnt_shelf['last_flip_reference_ha']= HA
        mnt_shelf['last_flip_reference_dec']= pointing_dec + deviation_dec

        self.last_flip_reference_time=time.time()
        self.last_flip_reference_ha = HA
        self.last_flip_reference_dec = pointing_dec
        self.last_flip_reference_ha_offset =  deviation_ha
        self.last_flip_reference_dec_offset =  deviation_dec

        # Add in latest point to the list of mount references
        # This has to be done in terms of hour angle due to changes over time.
        # We need to store time, HA, Dec, HA offset, Dec offset.
        #HA=self.current_sidereal - pointing_ra  + deviation_ha

        #breakpoint()
        # # Removing older references
        # for entry in self.longterm_storage_of_flip_references:
        #     distance_from_new_reference= abs((entry[1] -HA) * 15) + abs(entry[2] - pointing_dec+deviation_dec)
        #     if distance_from_new_reference < 2:
        #         plog ("Found and removing an old reference close to new reference: " + str(entry))
        #         self.longterm_storage_of_mount_references.remove(entry)
        plog ("Deviation in flip reference: HA: " + str(deviation_ha) + " Dec: " + str(deviation_dec))
        plog ("Recording and using new flip reference: HA: " + str(deviation_ha ) + " arcminutes, Dec: " + str(deviation_dec ) + " arcminutes." )

        counter=0
        deleteList=[]
        for entry in self.longterm_storage_of_flip_references:
            distance_from_new_reference= abs((entry[1] -HA) * 15) + abs(entry[2] - pointing_dec+deviation_dec)
            if distance_from_new_reference < 2:
                plog ("Found and removing an old reference close to new reference: " + str(entry))
                #self.longterm_storage_of_mount_references.remove(entry)
                deleteList.append(counter)
            counter=counter+1

        for index in sorted(deleteList, reverse=True):
            del self.longterm_storage_of_flip_references[index]

        self.longterm_storage_of_flip_references.append([time.time(),HA,pointing_dec + deviation_dec, deviation_ha,  deviation_dec])
        mnt_shelf['longterm_storage_of_flip_references']=self.longterm_storage_of_flip_references
        mnt_shelf.close()

        return

    def get_mount_reference(self, pointing_ra, pointing_dec):

        HA = self.current_sidereal - pointing_ra
        # Have a look through shelf to find closest reference:

        # Removing older references
        distance_from_closest_reference=180
        found_close_reference= False

        for entry in self.longterm_storage_of_flip_references:
            distance_from_new_reference= abs((entry[1] -HA) * 15) + abs(entry[2] - pointing_dec)
            if distance_from_new_reference < 5:
                if distance_from_new_reference < distance_from_closest_reference:
                    found_close_reference=True
                    close_reference=copy.deepcopy(entry)

        if found_close_reference:
            plog ("Found nearby mount offset in shelf: " + str(close_reference))
            plog ("Using reference: HA: " + str(close_reference[3] * 15 * 60) + " arcminutes, Dec: " + str(close_reference[4] * 60) + " arcminutes." )

            self.last_mount_reference_time=close_reference[0]
            self.last_mount_reference_ha =close_reference[1]
            self.last_mount_reference_dec =close_reference[2]
            self.last_mount_reference_ha_offset = close_reference[3]
            self.last_mount_reference_dec_offset = close_reference[4]

            return close_reference[3], close_reference[4]

        distance_from_current_reference_in_ha = abs(self.last_mount_reference_ha - HA)
        distance_from_current_reference_in_dec = abs(self.last_mount_reference_dec- pointing_dec)
        absolute_distance=pow(pow(distance_from_current_reference_in_ha*cos(radians(pointing_dec)),2)+pow(distance_from_current_reference_in_dec,2),0.5)

        if  absolute_distance < 10:
            plog ("last reference is nearby, using current reference")
            return self.last_mount_reference_ha_offset, self.last_mount_reference_dec_offset
        else:
            plog ("No previous deviation reference nearby")
            return 0.0,0.0


    def get_flip_reference(self, pointing_ra, pointing_dec):

        HA = self.current_sidereal - pointing_ra

        distance_from_closest_reference=180
        found_close_reference= False

        for entry in self.longterm_storage_of_flip_references:
            distance_from_new_reference= abs((entry[1] -HA) * 15) + abs(entry[2] - pointing_dec)
            if distance_from_new_reference < 5:
                if distance_from_new_reference < distance_from_closest_reference:
                    found_close_reference=True
                    close_reference=copy.deepcopy(entry)

        if found_close_reference:
            plog ("Found nearby mount offset in shelf: " + str(close_reference))
            plog ("Using reference: HA: " + str(close_reference[3] * 15 * 60) + " arcminutes, Dec: " + str(close_reference[4] * 60) + " arcminutes." )

            self.last_flip_reference_time=close_reference[0]
            self.last_flip_reference_ha =close_reference[1]
            self.last_flip_reference_dec =close_reference[2]
            self.last_flip_reference_ha_offset = close_reference[3]
            self.last_flip_reference_dec_offset = close_reference[4]

            return close_reference[3], close_reference[4]

        distance_from_current_reference_in_ha = abs(self.last_flip_reference_ha - HA)
        distance_from_current_reference_in_dec = abs(self.last_flip_reference_dec- pointing_dec)
        absolute_distance=pow(pow(distance_from_current_reference_in_ha*cos(radians(pointing_dec)),2)+pow(distance_from_current_reference_in_dec,2),0.5)

        if  absolute_distance < 10:
            plog ("last reference is nearby, using current reference")
            return self.last_flip_reference_ha_offset, self.last_flip_reference_dec_offset
        else:
            plog ("No previous deviation reference nearby")
            return 0.0,0.0

# if __name__ == '__main__':
#     req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
#     opt = {'area': 50}
#     m = Mount('ASCOM.PWI4.Telescope', "mnt1", {})
#     m.paddle()