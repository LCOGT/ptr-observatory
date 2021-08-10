
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


import threading
import win32com.client
import pythoncom
import serial
import time, json
import datetime
import shelve
from math import cos, radians    #"What plan do we have for making some imports be done this way, elg, import numpy as np...?"
from global_yard import g_dev    #"Ditto guestion we are importing a single object instance."

from astropy.time import Time

from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                         EarthLocation, AltAz
                         #This should be removed or put in a try

import ptr_utility
from config import site_config
import math

# =============================================================================
# from astropy.utils.iers import conf
# #conf.auto_max_age = None
# =============================================================================
#from astroquery.vizier import Vizier
#from astroquery.simbad import Simbad
#from devices.pywinusb_paddle import *



# siteLatitude = 34.342930277777775    #  34 20 34.569   #34 + (20 + 34.549/60.)/60.
# siteLongitude = -119.68112805555556  #-(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
# siteElevation = 317.75
# siteRefTemp = 15.0         #These should be a monthly average data.
# siteRefPress = 973.0       #mbar
# siteName = "Photon Ranch"
# siteAbbreviation = "PTR"
# siteCoordinates = EarthLocation(lat=siteLatitude*u.deg, \
#                                 lon=siteLongitude*u.deg,
#                                 height=siteElevation*u.m)
#ptr = EarthLocation(lat=siteLatitude*u.deg, lon=siteLongitude*u.deg, height=siteElevation*u.m)
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
HTOSec = 3600
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029
RefrOn = True

ModelOn = True
RatesOn = True
tzOffset = -7
loop_count = 0

mountOne = "PW_L600"
mountOneAscom = None

siteCoordinates = EarthLocation(lat=site_config['latitude']*u.deg, \
                                 lon=site_config['longitude']*u.deg,
                                 height=site_config['elevation']*u.m)
    #The mount is not threaded and uses non-blocking seek.

def ra_fix_r(ra):
    while ra >= TWOPI:
        ra -= TWOPI
    while ra < 0:
        ra += TWOPI
    return ra

def ra_dec_fix_r(ra, dec): #Note this is not a mechanical (TPOINT) transformation of dec
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

def ra_fix_h(ra):
    if ra >= 24:
        ra -= 24
    if ra < 0:
        ra = 24
    return ra


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
        self.site = config['site']
        self.site_path = config['site_path']
        self.config = config
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True
#       print('Can Asynch:  ', self.mount.CanSlewAltAzAsync)

        #hould put config Lat, lon, etc into mount, or at least check it is correct.
        self.site_coordinates = EarthLocation(lat=float(config['latitude'])*u.deg, \
                                lon=float(config['longitude'])*u.deg,
                                height=float(config['elevation'])*u.m)
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel   #for now this implies the primary telescope on a mounting.
        self.mount_message = "-"
        if self.config['agent_wms_enc_active']:
            self.site_is_proxy = True
        else:
            self.site_is_proxy = False
        if self.site == 'MRC2':
            self.has_paddle = config['mount']['mount2']['has_paddle']
        else:
            self.has_paddle = config['mount']['mount1']['has_paddle']
        self.object = "Unspecified"
        self.current_icrs_ra = "Unspecified_Ra"
        self.current_icrs_dec = " Unspecified_Dec"
        self.delta_t_s = HTOSec/12   #5 minutes
        self.prior_roll_rate = 0
        self.prior_pitch_rate = 0
        self.offset_received = False
        self.west_ha_correction_r = config['mount']['mount1']['west_ha_correction_r']
        self.west_dec_correction_r = config['mount']['mount1']['west_dec_correction_r']
        self.refraction = 0
        self.ha_corr = 0
        self.dec_corr = 0
        self.seek_commanded = False
        
        #self.mount.Park()
        if abs(self.west_ha_correction_r) > 0 or abs(self.west_dec_correction_r) > 0:
            self.flip_correction_needed = True
            print("Flip correction needed.")
        else:
            self.flip_correction_needed = False
        if not tel:
            print("Mount connected.")
        else:
            print("Auxillary Tel/OTA connected.")
        print(self.mount.Description)
        self.ra_offset = 0.0
        self.dec_offset = 0.0   #NB these should always start off at zero.
        if not self.mount.AtPark or self.mount.Tracking:
            #self.mount.RightAscensionRate = 0.0
            #self.mount.DeclinationRate = 0.0
            pass
        #breakpoint()
        #self.reset_mount_reference()
        #self.site_in_automatic = config['site_in_automatic_default']
        #self.automatic_detail = config['automatic_detail_default']
        self.move_time = 0
        try:
            ra1, dec1 = self.get_mount_reference()
            print("Mount reference:  ", ra1 ,dec1)
        except:
            print("No mount ref found.")
            pass

        #NB THe paddle needs a re-think and needs to be cast into its own thread. 20200310 WER
        if self.has_paddle:
            self._paddle = serial.Serial('COM28', timeout=0.1)
            self._paddle.write(b'ver\n')
            print(self._paddle.read(13).decode()[-8:])

    #        self._paddle.write(b"gpio iodir 00ff\n")
    #        self._paddle.write(b"gpio readall\n")
            self.paddleing = True
    #        print('a:',self._paddle.read(20).decode())
    #        print('b:',self._paddle.read(20).decode())
    #        print('c:',self._paddle.read(20).decode())
    #        print("Paddle  not operational??")
            self._paddle.close()
        else:
            self.paddeling = False
            #self.paddle_thread = threading.Thread(target=self.paddle, args=())
            #self.paddle_thread.start()
        print("exiting mount _init")
 

#    def get_status(self):
#        m = self.mount
#        status = {
#            "name": self.name,
#            "type":"mount",
#            "RightAscension": str(m.RightAscension),
#            "Declination": str(m.Declination),
#            "RightAscensionRate": str(m.RightAscensionRate),
#            "DeclinationRate": str(m.DeclinationRate),
#            "AtHome": str(m.AtHome),
#            "AtPark": str(m.AtPark),
#            "Azimuth": str(m.Azimuth),
#            "GuideRateDeclination":  str(0.0), #str(m.GuideRateDeclination),
#            "GuideRateRightAscension": str(0.0), #(m.GuideRateRightAscension),
#            "IsPulseGuiding": str(m.IsPulseGuiding),
#            "SideOfPier": str(m.SideOfPier),
#            "Slewing": str(m.Slewing),
#            "Tracking": str(m.Tracking),
#            "TrackingRate": str(0.0), #(m.TrackingRate),
#            # Target ra and dec throws error if they have not been set.
#            # Maybe we don't even need to include them in the status...
#            #"TargetDeclination": str(m.TargetDeclination),
#            #"TargetRightAscension": str(m.TargetRightAscension),
#        }
#        return status

    def check_connect(self):
        try:
            if self.mount.Connected:
                return
            else:
                print('Found mount not connected, reconnecting.')
                self.mount.Connected = True
                return
        except:
            print('Found mount not connected via try: block fail, reconnecting.')
            self.mount.Connected = True
            return

    def get_mount_coordinates(self):
        global loop_count
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
        if self.seek_commanded:    #Used for debugging.
            pass

        ra_cal_offset, dec_cal_offset = self.get_mount_reference()   #Get from shelf.
        if ra_cal_offset or dec_cal_offset:
            #breakpoint()
            pass
        look_west = 0    # == 0  self.flip_correction_needed
        if self. mount.EquatorialSystem == 1:
            loop_count += 1
            if loop_count == 5:
               # breakpoint()
                pass
            self.get_current_times()
            if self.mount.sideOfPier == 1:
                pierside = 1    #West side looking East   #Make this assignment a code-wide convention.
            else:
                pierside = 0   #East looking West
            uncorr_mech_ra_h = self.mount.RightAscension
            uncorr_mech_dec_d = self.mount.Declination

            uncorr_mech_ha_r, uncorr_mech_dec_r = ptr_utility.transform_raDec_to_haDec_r(uncorr_mech_ra_h*HTOR, uncorr_mech_dec_d*DTOR, self.sid_now_r)
            roll_obs_r, pitch_obs_r = ptr_utility.transform_mount_to_observed_r(uncorr_mech_ha_r, uncorr_mech_dec_r, pierside, loud=False)
            app_ra_r, app_dec_r, refr_asec = ptr_utility.obsToAppHaRa(roll_obs_r, pitch_obs_r, self.sid_now_r)
            self.refraction_rev = refr_asec
            '''
            # NB NB Read status could be used to recalculate and apply more accurate and current roll and pitch rates.
            '''
            jnow_ra_r = ptr_utility.reduce_ra_r(app_ra_r - ra_cal_offset*HTOR)    # NB the mnt_refs are subtracted here.  Check units are correct.
            jnow_dec_r = ptr_utility.reduce_dec_r( app_dec_r - dec_cal_offset*DTOR)

            # try:
            #     if not self.mount.AtPark:   #Applying rates while parked faults.
            #         if self.mount.CanSetRightAscensionRate and self.prior_roll_rate != 0 :
            #             self.mount.RightAscensionRate =self.prior_roll_rate
            #         if self.mount.CanSetDeclinationRate and self.prior_pitch_rate != 0:
            #             self.mount.DeclinationRate = self.prior_pitch_rate
            #             #print("Rate found:  ", self.prior_roll_rate, self.prior_pitch_rate, self.ha_corr, self.dec_corr)
            # except:
            #     print("mount status rate adjust exception.")
   
            if self.mount.sideOfPier == look_west \
                and self.flip_correction_needed:
                jnow_ra_r -=  self.west_ha_correction_r   #Brought in from local calib.py file correction is subtracted.  #This is meant to handle a flip klunk.
                jnow_dec_r -= self.west_dec_correction_r
            jnow_ra_r, jnow_dec_r = ra_dec_fix_r(jnow_ra_r, jnow_dec_r)
            jnow_coord = SkyCoord(jnow_ra_r*RTOH*u.hour, jnow_dec_r*RTOD*u.degree, frame='fk5', \
                      equinox=self.equinox_now)
            icrs_coord = jnow_coord.transform_to(ICRS)
            self.current_icrs_ra = icrs_coord.ra.hour
            self.current_icrs_dec = icrs_coord.dec.degree
        else:
            breakpoint()
            #NB This is an unused and not completely implemented path, or does Planwave PWI-4 use it?
            #breakpoint()   #20201230 WE should not get here.
            self.current_icrs_ra = ra_fix_r(self.mount.RightAscension - ra_cal_offset)    #May not be applied in positioning
            self.current_icrs_dec = self.mount.Declination - dec_cal_offset
        return self.current_icrs_ra, self.current_icrs_dec

    def get_status(self):
        #This is for now 20201230, the primary place to source mount/tel status, needs fixing.
        self.check_connect()
        self.paddle()   # NB Should ohly be called if in config.
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
        if airmass > 10: airmass = 10.0
        airmass = round(airmass, 4)
        #Be careful to preserve order
        #print(self.device_name, self.name)
        if self.site_is_proxy:
            self.site_is_proxy = True

# =============================================================================
#       The notion of multiple telescopes has not been implemented yet.
#       For now, 20201230 we use calls to mounting
# =============================================================================
        if self.tel == False:
            #breakpoint()
            status = {
                'timestamp': round(time.time(), 3),
#                f'right_ascension': str(self.mount.RightAscension),
#                f'declination': str(self.mount.Declination),
#                f'sidereal_time': str(self.mount.SiderealTime),
#                f'tracking_right_ascension_rate': str(self.mount.RightAscensionRate),
#                f'tracking_declination_rate': str(self.mount.DeclinationRate),
#                f'azimuth': str(self.mount.Azimuth),
#                f'altitude': str(alt),
#                f'zenith_distance': str(zen),
#                f'airmass': str(airmass),
#                f'coordinate_system': str(self.rdsys),
                'pointing_telescope': self.inst,  #needs fixing
                'is_parked': self.mount.AtPark,
                'is_tracking': self.mount.Tracking,
                'is_slewing': self.mount.Slewing,
                'message': self.mount_message[:32]
            }
        elif self.tel == True:
            self.current_sidereal = self.mount.SiderealTime
            icrs_ra, icrs_dec = self.get_mount_coordinates()  #20210430  Looks like thie faulted during a slew.
            if self.seek_commanded:
                #print('In Status:  ', self.prior_roll_rate, self.prior_pitch_rate)
                #print('From Mnt :  ', self.mount.RightAscensionRate, self.mount.DeclinationRate)
                pass
            status = {
                'timestamp': round(time.time(), 3),
                'right_ascension': round(icrs_ra, 5),
                'declination': round(icrs_dec, 4),
                'sidereal_time': round(self.current_sidereal, 5),  #Should we add HA?
                'refraction': round(self.refraction_rev, 2),
                'correction_ra': round(self.ha_corr, 4),  #If mount model = 0, these are very small numbers.
                'correction_dec': round(self.dec_corr, 4),

                'demand_right_ascension_rate': round(self.prior_roll_rate, 9),
                'mount_right_ascension_rate': round(self.mount.RightAscensionRate, 9),   #Will use sec-RA/sid-sec
                'demand_declination_rate': round(self.prior_pitch_rate, 8),
                'mount_declination_rate': round(self.mount.DeclinationRate, 8),
                'azimuth': round(self.mount.Azimuth, 3),
                'altitude': round(alt, 3),
                'zenith_distance': round(zen, 3),
                'airmass': round(airmass,4),
                'coordinate_system': str(self.rdsys),
                'equinox':  self.equinox_now,
                'pointing_instrument': str(self.inst),  # needs fixing
                'is_parked': str(self.mount.AtPark),     #  Send strings to AWS so JSON does not change case
                'is_tracking': str(self.mount.Tracking),
                'is_slewing': str(self.mount.Slewing),
                'message': str(self.mount_message[:54]),
                #'site_in_automatic': self.site_in_automatic,
                #'automatic_detail': str(self.automatic_detail),
                'move_time': self.move_time
            }
        else:
            print('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}

        return status  #json.dumps(status)

# =============================================================================
# #20160316 OK
# def transform_mount_to_Icrs(pCoord, pCurrentPierSide, pLST=None, loud=False):
#
#     if pLST is not None:
#         lclSid = pLST
#     else:
#         lclSid =sidTime
#     if loud: print('Pcoord:  ', pCoord)
#     roll, pitch = transform_raDec_to_haDec(pCoord[0], pCoord[1], sidTime)
#     if loud: print('MountToICRS1')
#     obsHa, obsDec = transform_mount_to_observed(roll, pitch, pCurrentPierSide)
#     if loud: print('MountToICRS2')
#     appRa, appDec = obsToAppHaRa(obsHa, obsDec, sidTime)
#     if loud: print('Out:  ', appRa, appDec, jYear)
#     pCoordJnow = SkyCoord(appRa*u.hour, appDec*u.degree, frame='fk5', \
#                           equinox=equinox_now)
#     if loud: print('pCoord:  ', pCoordJnow)
#     t = pCoordJnow.transform_to(ICRS)
#     if loud: print('returning ICRS:  ', t)
#     return (reduceRa(fromHMS(str(t.ra.to_string(u.hour)))),  \
#             reduceDec(fromDMS(str(t.dec.to_string(u.degree)))))
# =============================================================================



    def get_quick_status(self, pre):

        self.check_connect()
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
        if airmass > 10: airmass = 10
        airmass = round(airmass, 4)
        ra_off, dec_off = self.get_mount_reference()
        # NB NB THis code would be safer as a dict or other explicity named structure
        pre.append(time.time())
        icrs_ra, icrs_dec = self.get_mount_coordinates()
        pre.append(icrs_ra)
        pre.append(icrs_dec)
        pre.append(self.mount.SiderealTime)
        pre.append(self.mount.RightAscensionRate)
        pre.append(self.mount.DeclinationRate)
        pre.append(self.mount.Azimuth)
        pre.append(alt)
        pre.append(zen)
        pre.append(airmass)
        pre.append(self.mount.AtPark)
        pre.append(self.mount.Tracking)
        pre.append(self.mount.Slewing)
        #print(pre)
        return pre

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

        self.check_connect()
        t_avg = round((pre[0] + post[0])/2, 3)
        #print(t_avg)
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
        return status  #json.dumps(status)

    def parse_command(self, command):
        breakpoint()
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        self.check_connect()
        if action == "go":
            self.go_command(req, opt)   #  Entered from Target Explorer or Telescope tabs.
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        elif action == "set_site_manual":
            self.site_in_automatic = False
            self.automatic_detail = "Site & Enclosure set to Manual"
        elif action == "set_site_automatic":
            self.site_in_automatic = True
            self.automatic_detail = "Site set to Night time Automatic"
        elif action == "tracking":
            self.tracking_command(req, opt)
        elif action in ["pivot", 'zero', 'ra=sid, dec=0']:
            req['ra'] = self.mount.SiderealTime
            req['dec'] = 0.0
            self.go_command(req, opt, offset=False)
        elif action == "park":
            self.park_command(req, opt)
        elif action == "unpark":
            self.unpark_command(req, opt)
        elif action == 'center_on_pixels':
            print (command)
            self.go_command(req, opt, offset=True, calibrate=False)
        elif action == 'calibrateAtFieldCenter':
            print (command)
            #breakpoint()
            self.go_command(req, opt, calibrate=True)
        elif action == 'sky_flat_position':
            self.slewToSkyFlatAsync()
        else:
            print(f"Command <{action}> not recognized.")


    def get_current_times(self):
        self.ut_now = Time(datetime.datetime.now(), scale='utc', location=self.site_coordinates)   #From astropy.time
        self.sid_now_h = self.ut_now.sidereal_time('apparent').value
        self.sid_now_r = self.sid_now_h*HTOR

        iso_day = datetime.date.today().isocalendar()
        self.day = ((iso_day[1]-1)*7 + (iso_day[2] ))
        self.equinox_now = 'J' +str(round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2))
        return
    ###############################
    #        Mount Commands       #
    ###############################

    '''
    Having two similar functions here is consing and error prone.
    Go Command responds to commands from AWS.  Go Coords responds to
    internal changes of pointing occasion by the program and passed
    in as ra and dec direc tparameters, not dictionaries.

    '''

    def go_command(self, req, opt,  offset=False, calibrate=False):
        ''' Slew to the given ra/dec coordinates. '''
        print("mount cmd. slewing mount, req, opt:  ", req, opt)

        ''' unpark the telescope mount '''  #  NB can we check if unparked and save time?

        if self.mount.CanPark:
            #print("mount cmd: unparking mount")
            self.mount.Unpark()
        try:
            icrs_ra, icrs_dec = self.get_mount_coordinates()
            if offset:   #This offset version supplies offsets as a fraction of the Full field.
                #note it is based on mount coordinates.
                #Note we never look up the req dictionary ra or dec.
                if self.offset_received:
                    print("This is a second offset, are you sure you want to do this?")
                #
                offset_x = float(req['image_x']) - 0.5   #Fraction of field.
                offset_y = float(req['image_y']) - 0.5
                x_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['x_field_deg']
                y_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['y_field_deg']
                field_x = x_field_deg/15.   #  /15 for hours.
                field_y = y_field_deg
                #20210317 Changed signs fron Neyle.  NEEDS CONFIG File level or support.
                breakpoint()
                self.ra_offset += offset_x*field_x/4   #NB NB 20201230 Signs needs to be verified.
                self.dec_offset += -offset_y*field_y/4
                print("Offsets:  ", round(self.ra_offset, 5), round(self.dec_offset, 4))
                if not self.offset_received:
                    self.ra_prior, self.dec_prior = icrs_ra, icrs_dec #Do not let this change.
                self.offset_received = True   # NB Above we are accumulating offsets, but should not need to.
                #NB NB Position angle may need to be taken into account 20201230
                #apply this to the current telescope position(which may already incorporate a calibration)
                #need to get the ICRS telescope position.

                #Set up to go to the new position.
                ra, dec = ra_dec_fix_h(icrs_ra + self.ra_offset, icrs_dec + self.dec_offset)

            elif calibrate:  #Note does not need req or opt
                #breakpoint()
                if self.offset_received:

                    ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                    print("Stored calibration offsets:  ",round(ra_cal_offset, 5), round(dec_cal_offset, 4))
                    icrs_ra, icrs_dec = self.get_mount_coordinates()
                    accum_ra_offset = icrs_ra - self.ra_prior
                    accum_dec_offset = icrs_dec - self.dec_prior
                    ra_cal_offset += accum_ra_offset #self.ra_offset  #NB WE are adding an already correctly signed offset.The offset is positive to right of screen therefore a smaller numer on the RA line.
                    dec_cal_offset += accum_dec_offset #self.dec_offset
                    self.set_mount_reference(ra_cal_offset, dec_cal_offset)
                    self.ra_offset = 0
                    self.dec_offset = 0
                    self.offset_received = False
                    icrs_ra, icrs_dec = self.get_mount_coordinates()  #20210116 THis is returning some form of apparent
                    ra = self.ra_prior #icrs_ra
                    dec = self.dec_prior #icrs_dec
                    #We could just return but will seek just to be safe
                else:
                    print("No outstanding offset available for calibration, reset existing calibration.")
                    # NB We currently use this path to clear a calibration.  But should be ad explicit Command instead. 20201230
                    # breakpoint()
                    self.reset_mount_reference()
                    self.ra_offset = 0
                    self.dec_offset = 0
                    self.offset_received = False
                    icrs_ra, icrs_dec = self.get_mount_coordinates()
                    ra = self.ra_prior #icrs_ra
                    dec = self.dec_prior #icrs_dec

                    #We could just return but will seek just to be safe
            else:
                'Here we DO read the req dictiary ra and Dec.'
                try:
                    ra = float(req['ra'])
                    dec = float(req['dec'])
                    self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                    self.dec_offset = 0
                    self.offset_received = False
                    ra_dec = True
                except:
                    az = float(req['az'])
                    alt = float(req['alt'])
                    self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                    self.dec_offset = 0
                    self.offset_received = False
                    ra_dec = False
        except:
            print("Bad coordinates supplied.")
            self.message = "Bad coordinates supplied, try again."
            self.offset_received = False
            self.ra_offset = 0
            self.dec_offset = 0
            return
        # Tracking rate offsets from sidereal in arcseconds per SI second, default = 0.0
        tracking_rate_ra = opt.get('tracking_rate_ra', 0)
        tracking_rate_dec = opt.get('tracking_rate_dec', 0)
        delta_ra, delta_dec =self.get_mount_reference()
        #breakpoint()
        ra, dec = ra_dec_fix_h(ra + delta_ra, dec + delta_dec)   #Plus compensates for measured offset
        self.move_time = time.time()
        self.go_coord(ra, dec, tracking_rate_ra=tracking_rate_ra, tracking_rate_dec = tracking_rate_dec)
        self.object = opt.get("object", "")
        if self.object == "":
            print("Go to unamed target.")
        else:
            print("Going to:  ", self.object)   #NB Needs cleaning up.
            
    def re_seek(self, dither):
        if dither == 0:
            self.go_coord(self.last_ra, self.last_dec, self.last_tracking_rate_ra, self.last_tracking_rate_dec)
        else:
            breakpoint()
            
            
            

    def go_coord(self, ra, dec, tracking_rate_ra=0, tracking_rate_dec=0):  #Note these rates need a system specification
        '''
        Slew to the given ra/dec coordinates, supplied in ICRS
        Note no dependency on current position.
        unpark the telescope mount
        '''  #  NB can we check if unparked and save time?
        self.last_ra = ra
        self.last_dec = dec
        self.last_tracking_rate_ra = tracking_rate_ra
        self.last_tracking_rate_dec = tracking_rate_dec
        self.last_seek_time = time.time()

        if self.mount.CanPark:
            #print("mount cmd: unparking mount")
            self.mount.Unpark()
        ra_cal_offset, dec_cal_offset = self.get_mount_reference() # This is a Shelved basic offset, may be zero if a full model is in place.
        if self.mount.EquatorialSystem == 1:
            self.get_current_times()   #  NB We should find a way to refresh this once a day, esp. for status return.
            icrs_coord = SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
            jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
            ra = jnow_coord.ra.hour
            dec = jnow_coord.dec.degree
            if self.offset_received:
                ra +=  ra_cal_offset + self.ra_offset          #Offsets are J.now and used to get target on Browser Crosshairs.
                dec +=  dec_cal_offset + self.dec_offset              
        pier_east = 1
        if self.flip_correction_needed:   #self.config.flip_correction_needed woul dbe more readable.
            pier_east = 0
            #pier_west = 1
            #pier_unknown = -1
            try:
                new_pierside = self.mount.DestinationSideOfPier(ra, dec)  # A tuple gets returned.
                if new_pierside[0] == pier_east:
                    ra += self.east_ra_correction  #NB it takes a restart to pick up a new correction which is also J.now.
                    dec += self.east_dec_correction
            except:
                #DestSide... not implemented in PWI_4
                pass
        ra_app_h, dec_app_d = ra_dec_fix_h(ra, dec)
        

        
        #'This is the "Forward" calculation of pointing.
        #Here we add in refraction and the TPOINT compatible mount model

        self.ha_obs_r, self.dec_obs_r, self.refr_asec = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_now_r)
        #ra_obs_r, dec_obs_r = ptr_utility.transformHatoRaDec(ha_obs_r, dec_obs_r, self.sid_now_r)
        #Here we would convert to model and calculate tracking rate correction.
        self.ha_mech, self.dec_mech = ptr_utility.transform_observed_to_mount_r(self.ha_obs_r, self.dec_obs_r, pier_east, loud=False, enable=True)       
        self.ra_mech, self.dec_mech = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech, self.dec_mech, self.sid_now_r)
        self.ha_corr = ptr_utility.reduce_ha_r(self.ha_mech -self. ha_obs_r)*RTOS
        self.dec_corr = ptr_utility.reduce_dec_r(self.dec_mech - self.dec_obs_r)*RTOS
        self.mount.Tracking = True
        self.move_time = time.time()
        print('MODEL HA, DEC, Refraction:  (asec)  ', self.ha_corr, self.dec_corr, self.refr_asec)

        self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
        ###  figure out velocity  Apparent place is unchanged.
        self.sid_next_r = (self.sid_now_h + self.delta_t_s*STOH)*HTOR    #delta_t_s is five minutes
        self.ha_obs_adv, self.dec_obs_adv, self.refr_adv = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_next_r)   #% minute advance
        self.ha_mech_adv, self.dec_mech_adv = ptr_utility.transform_observed_to_mount_r(self.ha_obs_adv, self.dec_obs_adv, pier_east, loud=False)
        self.ra_adv, self.dec_adv = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech_adv, self.dec_mech_adv, self.sid_next_r)
        self.adv_ha_corr = ptr_utility.reduce_ha_r(self.ha_mech_adv - self.ha_obs_adv)*RTOS     #These are mechanical values, not j.anything
        self.adv_dec_corr = ptr_utility.reduce_dec_r(self.dec_mech_adv - self.dec_obs_adv)*RTOS
        self.prior_seek_ha_h = self.ha_mech
        self.prior_seek_dec_d = self.dec_mech
        self.prior_seek_time = time.time()
        self.prior_sid_time =  self.sid_now_r
        '''
        The units of this property are arcseconds per SI (atomic) second.
        Please note that for historic reasons the units of the
        RightAscensionRate property are seconds of RA per sidereal second.
        '''
        if self.mount.CanSetRightAscensionRate:
            self.prior_roll_rate = -((self.ha_mech_adv - self. ha_mech)*RTOS*MOUNTRATE/self.delta_t_s - MOUNTRATE)/(APPTOSID*15)    #Conversion right 20219329
            self.mount.RightAscensionRate = self.prior_roll_rate  #Neg number makes RA decrease
        else:
            self.prior_roll_rate = 0.0
        if self.mount.CanSetDeclinationRate:
           self.prior_pitch_rate = -(self.dec_mech_adv - self.dec_mech)*RTOS/self.delta_t_s    #20210329 OK 1 hour from zenith.  No Appsid correction per ASCOM spec.
           self.mount.DeclinationRate = self.prior_pitch_rate  #Neg sign makes Dec decrease
           print("rates:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_asec)
        else:
            self.prior_pitch_rate = 0.0
        #print(self.prior_roll_rate, self.prior_pitch_rate, refr_asec)
       # time.sleep(.5)
       # self.mount.SlewToCoordinatesAsync(ra_mech*RTOH, dec_mech*RTOD)
        time.sleep(1)   #fOR SOME REASON REPEATING THIS HELPS!
        if self.mount.CanSetRightAscensionRate:
            self.mount.RightAscensionRate = self.prior_roll_rate

        if self.mount.CanSetDeclinationRate:
            self.mount.DeclinationRate = self.prior_pitch_rate

        print("Rates set:  ", self.prior_roll_rate, self.prior_pitch_rate,self.refr_adv)
        self.seek_commanded = True
        #I think to reliable establish rates, set them before the slew.
        #self.mount.Tracking = True
        #self.mount.SlewToCoordinatesAsync(ra_mech*RTOH, dec_mech*RTOD)
        #self.current_icrs_ra = icrs_coord.ra.hour   #NB this assignment is incorrect
        #self.current_icrs_dec = icrs_coord.dec.degree

    def slewToSkyFlatAsync(self):
        az, alt = self.astro_events.flat_spot_now()
        self.unpark_command()
        self.mount.Tracking = False
        self.move_time = time.time()
        self.mount.SlewToAltAzAsync(az, alt)


    def stop_command(self, req, opt):
        print("mount cmd: stopping mount")
        self.mount.AbortSlew()

    def home_command(self, req, opt):
        ''' slew to the home position '''
        print("mount cmd: homing mount")
        if self.mount.AtHome:
            print("Mount is at home.")
        elif False: #self.mount.CanFindHome:    # NB what is this all about?
            print(f"can find home: {self.mount.CanFindHome}")
            self.mount.Unpark()
            #home_alt = self.settings["home_altitude"]
            #home_az = self.settings["home_azimuth"]
            #self.mount.SlewToAltAzAsync(home_alt, home_az)
            self.move_time = time.time()
            self.mount.FindHome()
        else:
            print("Mount is not capable of finding home. Slewing to zenith.")
            self.move_time = time.time()
            self.mount.SlewToAltAzAsync(88., 0.)

    def flat_panel_command(self, req, opt):
        ''' slew to the flat panel if it exists '''
        print("mount cmd: slewing to flat panel")
        pass

    def tracking_command(self, req, opt):
        ''' set the tracking rates, or turn tracking off '''
        print("mount cmd: tracking changed")
        pass

    def park_command(self, req=None, opt=None):
        ''' park the telescope mount '''
        print(self.mount.CanPark)
        if self.mount.CanPark:
            print("mount cmd: parking mount")
            self.move_time = time.time()
            self.mount.Park()

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''
        if self.mount.CanPark:
            print("mount cmd: unparking mount")
            self.mount.Unpark()

    def paddle(self):
        return
        '''
        The real way this should work is monitor if a speed button is pushed, then log the time and
        start the thread.  If no button pushed for say 30 seconds, stop thread and re-join.  That way
        image operations are minimally disrupted.

        Normally this will never be started, unless we are operating locally in the observatory.
        '''
#         return    #Temporary disable 20200817

#         self._paddle = serial.Serial('COM28', timeout=0.1)
#         self._paddle.write(b"gpio iodir 00ff\n")  #returns  16
#         self._paddle.write(b"gpio readall\n")     #  returns 13
#         temp_0 = self._paddle.read(21).decode()   #  This is a restate of read, a toss
#         temp_1 = self._paddle.read(21).decode()
#         print(len(temp_1))
#         self._paddle.close()
#         #print ('|' + temp[16:18] +'|')
#         button = temp_1[14]
#         spd= temp_1[13]
#         direc = ''
#         speed = 0.0
#         print("Btn:  ", button, "Spd:  ", speed, "Dir:  ", direc)
#         if button == 'E': direc = 'N'
#         if button == 'B': direc = 'S'
#         if button == 'D': direc = 'E'
#         if button == '7': direc = 'W'
#         if button == 'C': direc = 'NE'
#         if button == '9': direc = 'SE'
#         if button == '3': direc = 'SW'
#         if button == '6': direc = 'NW'
#         if spd ==  'C':
#             speed = 0.
#             EW = 1
#             NS = 1
#         if spd == '8':
#             speed = 15.
#             EW = 1
#             NS = 1
#         if spd ==  '4':
#             speed = 45.
#             EW = 1
#             NS = 1
#         if spd ==  '0':
#             speed = 135.
#             EW = 1
#             NS = 1
#         if spd ==  'D':
#             speed = 0.
#             EW = -1
#             NS = 1
#         if spd == '9':
#             speed = 15.
#             EW = -1
#             NS = 1
#         if spd ==  '5':
#             speed = 45.
#             EW = -1
#             NS = 1
#         if spd ==  '1':
#             speed = 135.
#             EW = -1
#             NS = 1
#         if spd ==  'E':
#             speed = 0.
#             EW = 1
#             NS = -1
#         if spd == 'A':
#             speed = 15.
#             EW = 1
#             NS = -1
#         if spd ==  '6':
#             speed = 45.
#             EW = 1
#             NS = -1
#         if spd ==  '2':
#             speed = 135.
#             EW = 1
#             NS = -1
#         if spd ==  'F':
#             speed = 0.
#             EW = -1
#             NS = -1
#         if spd == 'B':
#             speed = 15.
#             EW = -1
#             NS = -1
#         if spd == '7':
#             speed = 45.
#             EW = -1
#             NS = -1
#         if spd == '3':
#             speed = 135.
#             EW = -1
#             NS = -1

#         print(button, spd, direc, speed)
# #            if direc != '':
#         #print(direc, speed)
#         _mount = self.mount
#         #Need to add diagonal moves
#         if direc == 'N':
#             try:
#                 _mount.DeclinationRate = NS*speed
#                 self.paddleing = True
#             except:
#                 pass
#             print('cmd:  ', direc,  NS*speed)
#         if direc == 'S':
#             try:
#                 _mount.DeclinationRate = -NS*speed
#                 self.paddleing = True
#             except:
#                 pass
#             print('cmd:  ',direc,  -NS*speed)
#         if direc == 'E':
#             try:
#                 _mount.RightAscensionRate = EW*speed/15.   #Not quite the correct divisor.
#                 self.paddleing = True
#             except:
#                 pass
#             print('cmd:  ',direc, EW*speed/15.)
#         if direc == 'W':
#             try:
#                 _mount.RightAscensionRate = -EW*speed/15.
#                 self.paddleing = True
#             except:
#                 pass
#             print('cmd:  ',direc, -EW*speed/15.)
#         if direc == '':
#             try:
#                 _mount.DeclinationRate = 0.0
#                 _mount.RightAscensionRate = 0.0
#             except:
#                 print("Rate set excepetion.")
#             self.paddleing = False
#         self._paddle.close()
#         return

    def set_mount_reference(self, delta_ra, delta_dec):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = delta_ra
        mnt_shelf['dec_cal_offset'] = delta_dec
        mnt_shelf.close()
        return

    def get_mount_reference(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        delta_ra = mnt_shelf['ra_cal_offset']
        delta_dec = mnt_shelf['dec_cal_offset']
        mnt_shelf.close()
        return delta_ra, delta_dec

    def reset_mount_reference(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = 0.000
        mnt_shelf['dec_cal_offset'] = 0.000
        return

        '''
         class Darkslide(object):

           def __init__(self, pCOM):
               self.slideStatus = 'unknown'

           def openDarkslide(self):
               self._com = serial.Serial(pCom, timeout=0.1)
               self._com.write(b'@')
               self.slideStatus = 'open'
               self._com.close()

           def closeDarkslide(self):
               self._com = serial.Serial(pCom, timeout=0.1)
               self._com.write(b'A')
               self.slideStatus = 'closed'
               self._com.close()

           def darkslideStatus(self):
               return self.slideStatus


        class Probe(object):

            def __init__(self, pCom):
                self.probePosition = None
                print('Probe class called with:  ', pCom)
                self.commPort = pCom

            def probeRead(self):
               with serial.Serial(self.commPort, timeout=0.3) as com:
                   com.write(b'R1\n')
                   self.probePosition = float(com.read(6).decode())
                   com.close()
                   print(self.probePosition)
        '''


if __name__ == '__main__':
    req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
    opt = {'area': 50}
    m = Mount('ASCOM.PWI4.Telescope', "mnt1", {})
    m.paddle()
#    pre=[]
#    post=[]
#    m.get_quick_status(pre)
#    time.sleep(2)
#    m.get_quick_status(post)
#    print(m.get_average_status(pre, post))
    #print(c.get_ascom_description())
