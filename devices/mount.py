
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
import serial
import time, json
import datetime
import traceback
import os
import shelve
from math import cos, radians    #"What plan do we have for making some imports be done this way, elg, import numpy as np...?"
from global_yard import g_dev    #"Ditto guestion we are importing a single object instance."

from astropy.time import Time

from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun, get_moon, FK5, ICRS

import ptr_utility
import math
import ephem
from ptr_utility import plog



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
HTOSec = 3600
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029


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

def wait_for_slew():

    try:
        if not g_dev['mnt'].mount.AtPark:
            movement_reporting_timer=time.time()
            while g_dev['mnt'].mount.Slewing:
                if time.time() - movement_reporting_timer > 2.0:
                    plog( 'm>')
                    movement_reporting_timer=time.time()
                    g_dev['obs'].time_of_last_slew=time.time()
                g_dev['obs'].update_status(mount_only=True, dont_wait=True)

    except Exception as e:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        if 'pywintypes.com_error' in str(e):
            plog ("Mount disconnected. Recovering.....")
            time.sleep(30)
            g_dev['mnt'].mount.Connected = True
            #g_dev['mnt'].home_command()
        else:
            print ("trying recovery routine")
            q=0
            while True:
                time.sleep(10)
                plog ("recovery attempt " + str(q+1))
                q=q+1
                g_dev['obs'].update_status()
                try:
                    g_dev['mnt'].mount.Connected = True

                    break
                except:
                    plog("recovery didn't work")
                    plog(traceback.format_exc())
                    if q > 15:
                        pass
                        ######breakpoint()

    return

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
        except Exception as e:
            print (e)
            if 'PWI4_ASCOM' in str(e):
                os.system('"C:\Program Files (x86)\PlaneWave Instruments\PlaneWave Interface 4\PWI4.exe"')
            else:
                plog(traceback.format_exc())
                ######breakpoint()

        self.driver = driver

        if "ASCOM.SoftwareBisque.Telescope" in driver:
            self.theskyx = True
        else:
            self.theskyx = False

        self.site_coordinates = EarthLocation(lat=float(g_dev['evnt'].wema_config['latitude'])*u.deg, \
                                lon=float(g_dev['evnt'].wema_config['longitude'])*u.deg,
                                height=float(g_dev['evnt'].wema_config['elevation'])*u.m)
        self.latitude_r = g_dev['evnt'].wema_config['latitude']*DTOR
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel   #for now this implies the primary telescope on a mounting.
        self.mount_message = "-"
        self.has_paddle = config['mount']['mount1']['has_paddle']

        self.object = "Unspecified"
        try:
            self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        except:
            plog ("Failed to get the current sidereal time from the mount.")
        self.current_icrs_ra = self.mount.RightAscension
        self.current_icrs_dec = self.mount.Declination
        try:
            self.refr_on = config["mount"]["mount1"]["settings"]["refraction_on"]
            self.model_on = config["mount"]["mount1"]["settings"]["model_on"]
            self.rates_on = config["mount"]["mount1"]["settings"]["rates_on"]
        except:
            self.refr_on = False
            self.model_on = False
            self.rates_on = False

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
        try:
            ra1, dec1 = self.get_mount_reference()
            ra2, dec2 = self.get_flip_reference()
            plog("Mount references & flip (Look East):  ", ra1, dec1, ra2, dec2 )
        except:
            plog("No mount ref found.")
            pass

        #NB THe paddle needs a re-think and needs to be cast into its own thread. 20200310 WER
        if self.has_paddle:
            self._paddle = serial.Serial('COM28', timeout=0.1)
            self._paddle.write(b'ver\n')
            plog(self._paddle.read(13).decode()[-8:])

    #        self._paddle.write(b"gpio iodir 00ff\n")
    #        self._paddle.write(b"gpio readall\n")
            self.paddleing = True
    #        plog('a:',self._paddle.read(20).decode())
    #        plog('b:',self._paddle.read(20).decode())
    #        plog('c:',self._paddle.read(20).decode())
    #        plog("Paddle  not operational??")
            self._paddle.close()
        else:
            self.paddeling = False
            #self.paddle_thread = threading.Thread(target=self.paddle, args=())
            #self.paddle_thread.start()
        self.obs = ephem.Observer()
        self.obs.long = g_dev['evnt'].wema_config['longitude']*DTOR
        self.obs.lat = g_dev['evnt'].wema_config['latitude']*DTOR

        self.theskyx_tracking_rescues = 0

        # Here we figure out if it can report pierside. If it cannot, we need
        # not keep calling the mount to ask for it, which is slow and prone
        # to an ascom crash.
        try:
            self.pier_side = g_dev[
                "mnt"
            ].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
            self.can_report_pierside = True
        except Exception:
            plog ("Mount cannot report pierside. Setting the code not to ask again, assuming default pointing west.")
            self.can_report_pierside = False
            self.pier_side = 0

            pass

        # Similarly for DestinationSideOfPier
        try:
            g_dev[
                "mnt"
            ].mount.DestinationSideOfPier(0,0)  # 0 == Tel Looking West, is flipped.
            self.can_report_destination_pierside = True
        except Exception:
            plog ("Mount cannot report destination pierside. Setting the code not to ask again.")
            self.can_report_destination_pierside = False
            self.pier_side = 0

            pass

        if self.pier_side == 0:
            self.pier_side_str ="Looking West"
        else:
            self.pier_side_str = "Looking East"

        # NEED to initialise these variables here in case the mount isn't slewed
        # before exposures after bootup
        self.last_ra_requested = self.mount.RightAscension

        self.last_dec_requested = self.mount.Declination
        self.last_tracking_rate_ra = 0
        self.last_tracking_rate_dec = 0
        self.last_seek_time = time.time() - 5000

        # Minimising ASCOM calls by holding these as internal variables
        if self.mount.CanSetRightAscensionRate:
            self.CanSetRightAscensionRate=True
        else:
            self.CanSetRightAscensionRate=False
        self.RightAscensionRate = self.mount.RightAscensionRate
        if self.mount.CanSetDeclinationRate:
            self.CanSetDeclinationRate = True
        else:
            self.CanSetDeclinationRate = False
        self.DeclinationRate = self.mount.DeclinationRate

        self.EquatorialSystem=self.mount.EquatorialSystem

        self.previous_pier_side=self.mount.sideOfPier


        # The update_status routine collects the current atpark status and pier status.
        # This is a slow command, so unless the code needs to know IMMEDIATELY
        # whether the scope is parked, then this is polled rather than directly
        # asking ASCOM/MOUNT
        self.rapid_park_indicator=self.mount.AtPark
        self.rapid_pier_indicator=self.mount.sideOfPier


    def check_connect(self):
        try:
            if self.mount.Connected:
                return
            else:
                plog('Found mount not connected, reconnecting.')
                try:
                    self.mount.Connected = True
                    if self.mount.Connected:
                        return
                except Exception as e:
                    plog (traceback.format_exc())
                    plog ("mount reconnection failed.")

        except:
            plog('Found mount not connected via try: block fail, reconnecting.')
            time.sleep(5)
            try:
                self.mount.Connected = True
                if self.mount.Connected:
                    return
            except Exception as e:
                plog (traceback.format_exc())
                plog ("mount reconnection failed.")

            plog ("Trying full-scale reboot")
            try:
                win32com.client.pythoncom.CoInitialize()
                self.mount = win32com.client.Dispatch(self.driver)
                self.mount.Connected = True
                if self.mount.Connected:
                    return
            except Exception:
                plog (traceback.format_exc())
                plog ("mount full scale reboot failed.")


    def get_mount_coordinates(self):
        #global loop_count
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

        self.current_icrs_ra = self.mount.RightAscension    #May not be applied in positioning
        self.current_icrs_dec = self.mount.Declination

        return self.current_icrs_ra, self.current_icrs_dec

    def get_status(self):

        if self.tel == False:
            status = {
                'timestamp': round(time.time(), 3),
                'pointing_telescope': self.inst,
                'is_parked': self.mount.AtPark,
                'is_tracking': self.mount.Tracking,
                'is_slewing': self.mount.Slewing,
                'message': self.mount_message[:32]
            }
        elif self.tel == True:
            try:
                icrs_ra, icrs_dec = self.get_mount_coordinates()
                rd = SkyCoord(ra=icrs_ra*u.hour, dec=icrs_dec*u.deg)
            except:
                icrs_ra=self.current_icrs_ra
                icrs_dec=self.current_icrs_dec
                rd = SkyCoord(ra=self.current_icrs_ra*u.hour, dec=self.current_icrs_dec*u.deg)

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

            try:
                self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            except:
                plog ("Mount didn't accept request for sidereal time. Need to make a calculation for this.")

            if self.prior_roll_rate == 0:
                pass
            ha = icrs_ra - self.current_sidereal
            if ha < 12:
                ha  += 24
            if ha > 12:
                ha -= 24

            status = {
                'timestamp': round(time.time(), 3),
                'right_ascension': round(icrs_ra, 4),
                'declination': round(icrs_dec, 4),
                'sidereal_time': round(self.current_sidereal, 5),  #Should we add HA?
                #'refraction': round(self.refraction_rev, 2),
                'correction_ra': round(self.ha_corr, 4),  #If mount model = 0, these are very small numbers.
                'correction_dec': round(self.dec_corr, 4),
                'hour_angle': round(ha, 3),
                'demand_right_ascension_rate': round(self.prior_roll_rate, 9),   #NB as on 20231113 these rates are basically fixed and static. WER
                'mount_right_ascension_rate': round(self.RightAscensionRate, 9),   #Will use sec-RA/sid-sec
                'demand_declination_rate': round(self.prior_pitch_rate, 8),
                'mount_declination_rate': round(self.DeclinationRate, 8),
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
                'move_time': self.move_time
            }

        else:
            plog('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}
        #plog("Mount Status:  ", status)
        return status

    def get_quick_status(self, pre):

        try:
            icrs_ra, icrs_dec = self.get_mount_coordinates()
            rd = SkyCoord(ra=icrs_ra*u.hour, dec=icrs_dec*u.deg)
        except:
            icrs_ra=self.current_icrs_ra
            icrs_dec=self.current_icrs_dec
            rd = SkyCoord(ra=self.current_icrs_ra*u.hour, dec=self.current_icrs_dec*u.deg)

        aa = AltAz (location=self.site_coordinates, obstime=Time.now())
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
        if airmass > 10: airmass = 10
        airmass = round(airmass, 4)

        # NB NB THis code would be safer as a dict or other explicity named structure
        pre.append(time.time())
        pre.append(icrs_ra)
        pre.append(icrs_dec)
        pre.append(float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle))
        pre.append(self.RightAscensionRate)
        pre.append(self.DeclinationRate)
        pre.append(az)
        pre.append(alt)
        pre.append(zen)
        pre.append(airmass)
        pre.append(self.mount.AtPark)
        pre.append(self.mount.Tracking)
        pre.append(self.mount.Slewing)
        return pre


    def get_rapid_exposure_status(self, pre):

        try:
            rd = SkyCoord(ra=self.current_icrs_ra*u.hour, dec=self.current_icrs_dec*u.deg)
        except:
            icrs_ra, icrs_dec = self.get_mount_coordinates()
            rd = SkyCoord(ra=icrs_ra*u.hour, dec=icrs_dec*u.deg)
        aa = AltAz (location=self.site_coordinates, obstime=Time.now())
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
        if airmass > 10: airmass = 10
        airmass = round(airmass, 4)
        pre.append(time.time())
        pre.append(self.current_icrs_ra)
        pre.append(self.current_icrs_dec)
        pre.append(float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle))
        pre.append(0.0)
        pre.append(0.0)
        pre.append(az)
        pre.append(alt)
        pre.append(zen)
        pre.append(airmass)
        pre.append(False)
        pre.append(True)
        pre.append(False)
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

        #self.check_connect()
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
        return status

    def parse_command(self, command):

        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        self.check_connect()
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
        elif action == "home":
            self.home_command(req, opt)
        elif action == "set_site_manual":
            self.obsid_in_automatic = False
            self.automatic_detail = "Site & Enclosure set to Manual"
        elif action == "set_site_automatic":
            self.obsid_in_automatic = True
            self.automatic_detail = "Site set to Night time Automatic"
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
        elif action == 'center_on_pixels':
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

                wait_for_slew()
                self.mount.SlewToCoordinatesAsync(gora, godec)
                wait_for_slew()

                #breakpoint()
                #self.go_command(ra=gora, dec=godec)#, offset=True, calibrate=False)
            except:
                plog (traceback.format_exc())
                plog ("seems the image header hasn't arrived at the UI yet, wait a moment")

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
        plog ('sun alt: ' + str(sun_alt) + " sun az: " + str(sun_az))
        flatspot_az = sun_az - 180.  # Opposite az of the Sun
        if flatspot_az < 0:
            flatspot_az += 360.

        flatspot_alt = sun_alt + 105  # 105 degrees along great circle through zenith
        if flatspot_alt > 90:   # Over the zenith so specify alt at above azimuth
            flatspot_alt = 180 - flatspot_alt

        if flatspot_alt < 90 and sun_alt < -15:
            flatspot_az = sun_az

        return(flatspot_alt, flatspot_az)

    ###############################
    #        Mount Commands       #
    ###############################

    '''
    This is the standard go to that does not establish and tracking for refraction or
    envoke the mount model.

    '''

    def go_command(self, skyflatspot=None, ra=None, dec=None, az=None, alt=None, ha=None, objectname=None, offset=False, calibrate=False, auto_center=False, silent=False, skip_open_test=False,tracking_rate_ra = 0, tracking_rate_dec =  0, do_centering_routine=False):

        ''' Slew to the given ra/dec, alt/az or ha/dec or skyflatspot coordinates. '''

        # First thing to do is check the position of the sun and
        # Whether this violates the pointing principle.
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

            plog ("Requested Flat Spot, az: " + str(az) + " alt: " + str(alt))

            if self.config['degrees_to_avoid_zenith_area_for_calibrations'] > 0:
                #######breakpoint()
                if (90-alt) < self.config['degrees_to_avoid_zenith_area_for_calibrations']:
                    g_dev['obs'].send_to_user("Refusing skyflat pointing request as it is too close to the zenith for this scope.")
                    plog("Refusing skyflat pointing request as it is too close to the zenith for this scope.")
                    return 'refused'

        elif ra != None:
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
        elif ha != None:
            ha = float(ha)
            dec = float(dec)
            az, alt = ptr_utility.transform_haDec_to_azAlt(ha, dec, lat=self.config['latitude'])
            temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)
            altazskycoord=SkyCoord(alt=alt*u.deg, az=az*u.deg, obstime=Time.now(), location=self.site_coordinates, frame='altaz')
            ra = altazskycoord.icrs.ra.deg /15
            dec = altazskycoord.icrs.dec.deg

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

        # Fifth thing, check that the sky flat latch isn't on
        # (I moved the scope during flats once, it wasn't optimal)
        if not skyflatspot and (g_dev['seq'].morn_sky_flat_latch  or g_dev['seq'].eve_sky_flat_latch or g_dev['seq'].sky_flat_latch or g_dev['seq'].bias_dark_latch):
            g_dev['obs'].send_to_user("Refusing pointing request as the observatory is currently undertaking flats or calibration frames.")
            plog("Refusing pointing request as the observatory is currently taking flats or calibration frmaes.")
            return 'refused'


        if objectname != None:
            self.object = objectname
        else:
            self.object = 'unspecified'    #NB could possibly augment with "Near --blah--"

        self.unpark_command()


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

        icrs_ra, icrs_dec = self.get_mount_coordinates()   #Does not appear to be used

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


        #Note this initiates a mount move.  WE should Evaluate if the destination is on the flip side and pick up the
        #flip offset.  So a GEM could track into positive HA territory without a problem but the next reseek should
        #result in a flip.  So first figure out if there will be a flip:
        self.previous_pier_side=self.mount.sideOfPier

        if self.can_report_destination_pierside == True:
            try:                          #  NB NB Might be good to log is flipping on a re-seek.
                new_pierside =  self.mount.DestinationSideOfPier(ra, dec) #  A tuple gets returned: (pierside, Ra.h and dec.d)
                if len(new_pierside) > 1:
                    if new_pierside[0] == 0:
                        delta_ra, delta_dec = self.get_mount_reference()

                    else:
                        delta_ra, delta_dec = self.get_flip_reference()

            except:
                try:
                    new_pierside =  self.mount.DestinationSideOfPier(ra, dec) #  A tuple gets returned: (pierside, Ra.h and dec.d)
                    if new_pierside == 0:
                        delta_ra, delta_dec = self.get_mount_reference()

                    else:
                        delta_ra, delta_dec = self.get_flip_reference()

                except:
                    delta_ra, delta_dec = self.get_mount_reference()


        else:
            if self.previous_pier_side == 0:
                delta_ra, delta_dec = self.get_mount_reference()

            else:
                delta_ra, delta_dec = self.get_flip_reference()

        if g_dev['obs'].mount_reference_model_off:
            pass
        else:
            try:

                ra += delta_ra #NB it takes a restart to pick up a new correction which is also J.now.
                dec += delta_dec
            except:
                pass

        plog ("mount references in go_command: " + str(delta_ra) + " " + str(delta_dec))
        plog ("difference between request and pointing: " + str(ra - self.last_ra_requested))


        self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        # First move, then check the pier side
        successful_move=0
        while successful_move==0:
            try:
                wait_for_slew()
                g_dev['obs'].time_of_last_slew=time.time()
                g_dev['mnt'].last_slew_was_pointing_slew = True
                if ra < 0:
                    ra=ra+24
                if ra > 24:
                    ra=ra-24
                self.mount.SlewToCoordinatesAsync(ra, dec)  #Is this needed?
                wait_for_slew()
            except Exception:
                # This catches an occasional ASCOM/TheSkyX glitch and gets it out of being stuck
                # And back on tracking.
                try:
                    retry=0
                    while retry <3:
                        try:
                            if g_dev['mnt'].theskyx:

                                plog("The SkyX had an error.")
                                plog("Usually this is because of a broken connection.")
                                plog("Killing then waiting 60 seconds then reconnecting")
                                g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                                self.unpark_command()
                                wait_for_slew()
                                #self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
                                if ra < 0:
                                    ra=ra+24
                                if ra > 24:
                                    ra=ra-24
                                self.mount.SlewToCoordinatesAsync(ra, dec)
                                wait_for_slew()
                                retry=4
                            else:

                                plog (traceback.format_exc())
                                ######breakpoint()
                        except:
                            time.sleep(120)
                            retry=retry+1
                except:
                    plog (traceback.format_exc())
                    #######breakpoint()

            # Make sure the current pier_side variable is set
            g_dev["mnt"].pier_side=self.mount.sideOfPier
            if self.previous_pier_side == g_dev["mnt"].pier_side or self.can_report_destination_pierside:
                successful_move=1
            else:



                if g_dev['obs'].mount_reference_model_off:
                    pass

                else:
                    ra=self.last_ra_requested + delta_ra
                    dec=self.last_dec_requested + delta_dec


                if ra < 0:
                    ra=ra+24
                if ra > 24:
                    ra=ra-24
                plog('actual sent ra: ' + str(ra) + ' dec: ' + str(dec))
                wait_for_slew()
                g_dev['mnt'].last_slew_was_pointing_slew = True
                self.mount.SlewToCoordinatesAsync(ra, dec)
                wait_for_slew()
                successful_move=1

        if self.mount.Tracking == False:
            try:
                wait_for_slew()
                self.mount.Tracking = True
            except Exception:
                # Yes, this is an awfully non-elegant way to force a mount to start
                # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
                # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter

                if "Property write Tracking is not implemented in this driver" in str(traceback.format_exc()):
                    pass
                elif g_dev['mnt'].theskyx:
                    plog (traceback.format_exc())
                    plog("The SkyX had an error.")
                    plog("Usually this is because of a broken connection.")
                    plog("Killing then waiting 60 seconds then reconnecting")
                    g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                    self.unpark_command()
                    wait_for_slew()
                    if ra < 0:
                        ra=ra+24
                    if ra > 24:
                        ra=ra-24
                    self.mount.SlewToCoordinatesAsync(ra, dec)  #Is this needed?
                    wait_for_slew()

                else:
                    plog (traceback.format_exc())


        g_dev['obs'].time_of_last_slew=time.time()

        g_dev['obs'].time_since_last_slew = time.time()
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000
        wait_for_slew()
        if not silent:
            g_dev['obs'].send_to_user("Slew Complete.")

        if do_centering_routine:
            g_dev['seq'].centering_exposure()

        # Continue to keep track of pierside
        self.previous_pier_side=self.mount.sideOfPier

    def go_w_model_and_velocity(self, ra, dec, tracking_rate_ra=0, tracking_rate_dec=0, reset_solve=True):  #Note these rates need a system specification
        '''
        NB NB NB THis is new-old code having to do with supporting velocity and pointing
        correction for refraction and the installed mount model.  IF Model_on and
        refr_on are False this code defaults to use the go-command routine above.

        Slew to the given ra/dec coordinates, supplied in ICRS
        Note no dependency on current position.
        unpark the telescope mount
        '''  #  NB can we check if unparked and save time?
        self.last_ra = ra
        self.last_dec = dec
        self.last_tracking_rate_ra = tracking_rate_ra
        self.last_tracking_rate_dec = tracking_rate_dec
        self.last_seek_time = time.time()

        self.unpark_command()
        #Note this initiates a mount move.  WE should Evaluate if the destination is on the flip side and pick up the
        #flip offset.  So a GEM could track into positive HA territory without a problem but the next reseek should
        #result in a flip.  So first figure out if there will be a flip:

        try:

            try:                          #  NB NB Might be good to log is flipping on a re-seek.
                new_pierside =  self.mount.DestinationSideOfPier(ra, dec) #  A tuple gets returned: (pierside, Ra.h and dec.d)
                if len(new_pierside) > 1:
                    if new_pierside[0] == 0:
                        delta_ra, delta_dec = self.get_mount_reference()
                        pier_east = 1
                    else:
                        delta_ra, delta_dec = self.get_flip_reference()
                        pier_east = 0
            except:
                try:
                    new_pierside =  self.mount.DestinationSideOfPier(ra, dec) #  A tuple gets returned: (pierside, Ra.h and dec.d)
                    if new_pierside == 0:
                        delta_ra, delta_dec = self.get_mount_reference()
                        pier_east = 1
                    else:
                        delta_ra, delta_dec = self.get_flip_reference()
                        pier_east = 0
                except:
                    delta_ra, delta_dec = self.get_mount_reference()
                    pier_east = 1
        except Exception as e:
            print ("mount really doesn't like pierside calls ", e)
            pier_east = 1
         #Update incoming ra and dec with mounting offsets.
        print ("delta")
        print (delta_ra)
        ra += delta_ra #NB it takes a restart to pick up a new correction which is also J.now.
        dec += delta_dec
        ra, dec = ra_dec_fix_h(ra,dec)
        if self.mount.EquatorialSystem == 1:    #equTopocentric
            self.get_current_times()   #  NB We should find a way to refresh this once a day, esp. for status return.
            #  Input is meant to be IRCS, so change to that Astropy type;
            icrs_coord = SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
            jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
            ra = jnow_coord.ra.hour
            dec = jnow_coord.dec.degree

            if self.offset_received:
                ra += self.ra_offset          #Offsets are J.now and used to get target on Browser Crosshairs.
                dec += self.dec_offset
        ra_app_h, dec_app_d = ra_dec_fix_h(ra, dec)
        #'This is the "Forward" calculation of pointing.
        #Here we add in refraction and the TPOINT compatible mount model

        self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

        self.sid_now_r = self.current_sidereal*HTOR   #NB NB ADDED THIS FOR SRO, WHY IS THIS NEEDED?

        self.ha_obs_r, self.dec_obs_r, self.refr_asec = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_now_r)
        #ra_obs_r, dec_obs_r = ptr_utility.transformHatoRaDec(ha_obs_r, dec_obs_r, self.sid_now_r)
        #Here we would convert to model and calculate tracking rate correction.
        self.ha_mech, self.dec_mech = ptr_utility.transform_observed_to_mount_r(self.ha_obs_r, self.dec_obs_r, pier_east, loud=False, enable=True)
        self.ra_mech, self.dec_mech = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech, self.dec_mech, self.sid_now_r)
        self.ha_corr = ptr_utility.reduce_ha_r(self.ha_mech -self. ha_obs_r)*RTOS
        self.dec_corr = ptr_utility.reduce_dec_r(self.dec_mech - self.dec_obs_r)*RTOS


        if self.mount.Tracking == False:
            try:
                wait_for_slew()
                self.mount.Tracking = True
            except Exception as e:
                # Yes, this is an awfully non-elegant way to force a mount to start
                # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
                # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter
                if ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues < 5:
                    self.theskyx_tracking_rescues=self.theskyx_tracking_rescues + 1
                    self.home_command()
                    self.park_command()
                    wait_for_slew()
                    self.unpark_command()
                    wait_for_slew()
                    self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
                    wait_for_slew()

                    print ("this mount may not accept tracking commands")
                elif ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues >= 5:
                    print ("theskyx has been rescued one too many times. Just sending it to park.")
                    self.park_command()
                    wait_for_slew()
                    return
                else:
                    print ("problem with setting tracking: ", e)


        self.move_time = time.time()
        az, alt = ptr_utility.transform_haDec_to_azAlt_r(self.ha_mech, self.dec_mech, self.latitude_r)
        plog('MODEL HA, DEC, AZ, Refraction:  (asec)  ', self.ha_corr, self.dec_corr, az*RTOD, self.refr_asec)
        self.target_az = az*RTOD

        wait_for_slew()
        try:
            self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
            wait_for_slew()
        except Exception as e:
            # This catches an occasional ASCOM/TheSkyX glitch and gets it out of being stuck
            # And back on tracking.
            if ('Object reference not set to an instance of an object.' in str(e)):
                self.home_command()
                self.park_command()
                wait_for_slew()
                self.unpark_command()
                wait_for_slew()
                self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
                wait_for_slew()

        if self.mount.Tracking == False:
            try:
                wait_for_slew()
                self.mount.Tracking = True
            except Exception as e:
                # Yes, this is an awfully non-elegant way to force a mount to start
                # Tracking when it isn't implemented in the ASCOM driver. But if anyone has any better ideas, I am all ears - MF
                # It also doesn't want to get into an endless loop of parking and unparking and homing, hence the rescue counter
                if ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues < 5:
                    self.theskyx_tracking_rescues=self.theskyx_tracking_rescues + 1
                    self.park_command()
                    wait_for_slew()
                    self.unpark_command()
                    wait_for_slew()
                    self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
                    wait_for_slew()

                    print ("this mount may not accept tracking commands")
                elif ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues >= 5:
                    print ("theskyx has been rescued one too many times. Just sending it to park.")
                    self.park_command()
                    wait_for_slew()
                    return
                else:
                    print ("problem with setting tracking: ", e)

        g_dev['obs'].time_since_last_slew_or_exposure = time.time()
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000
        wait_for_slew()


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
            self.mount.RightAscensionRate = 0.0 # self.prior_roll_rate  #Neg number makes RA decrease
        else:
            self.prior_roll_rate = 0.0
        if self.mount.CanSetDeclinationRate:
           self.prior_pitch_rate = -(self.dec_mech_adv - self.dec_mech)*RTOS/self.delta_t_s    #20210329 OK 1 hour from zenith.  No Appsid correction per ASCOM spec.
           self.mount.DeclinationRate = self.prior_pitch_rate  #Neg sign makes Dec decrease
           #plog("Rates, refr are:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_asec)
        else:
            self.prior_pitch_rate = 0.0
        #plog(self.prior_roll_rate, self.prior_pitch_rate, refr_asec)
        # time.sleep(.5)
        # self.mount.SlewToCoordinatesAsync(ra_mech*RTOH, dec_mech*RTOD)
        time.sleep(1)   #fOR SOME REASON REPEATING THIS HELPS!
        if self.mount.CanSetRightAscensionRate:
            self.mount.RightAscensionRate = 0.0 #self.prior_roll_rate

        if self.mount.CanSetDeclinationRate:
            self.mount.DeclinationRate = self.prior_pitch_rate

        plog("Rates set:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_adv)
        self.seek_commanded = True
        #I think to reliable establish rates, set them before the slew.
        #self.mount.Tracking = True
        #self.mount.SlewToCoordinatesAsync(ra_mech*RTOH, dec_mech*RTOD)
        #self.current_icrs_ra = icrs_coord.ra.hour   #NB this assignment is incorrect
        #self.current_icrs_dec = icrs_coord.dec.degree

        # On successful movement of telescope reset the solving timer
        if reset_solve == True:
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000
        wait_for_slew()

    def stop_command(self, req, opt):
        plog("mount cmd: stopping mount")
        self.mount.AbortSlew()

    def home_command(self, req=None, opt=None):
        ''' slew to the home position '''
        plog("mount cmd: homing mount")
        if self.mount.CanFindHome:
            mount_at_home = self.mount.AtHome
            if mount_at_home:
                plog("Mount is at home.")
            elif not mount_at_home:
                g_dev['obs'].time_of_last_slew=time.time()
                plog(f"can find home: {self.mount.CanFindHome}")
                self.unpark_command()
                wait_for_slew()

                self.move_time = time.time()
                self.mount.FindHome()
                wait_for_slew()
        else:
            plog("Mount is not capable of finding home. Slewing to home_alt and home_az")
            self.move_time = time.time()
            home_alt = self.settings["home_altitude"]
            home_az = self.settings["home_azimuth"]
            g_dev['obs'].time_of_last_slew=time.time()
            g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True)

            wait_for_slew()
        wait_for_slew()

    def flat_panel_command(self, req, opt):
        ''' slew to the flat panel if it exists '''
        plog("mount cmd: slewing to flat panel")
        pass

    def tracking_command(self, req, opt):
        ''' set the tracking rates, or turn tracking off '''
        plog("mount cmd: tracking changed")
        pass

    def park_command(self, req=None, opt=None):
        ''' park the telescope mount '''
        if self.mount.CanPark:
            if not g_dev['mnt'].mount.AtPark:
                plog("mount cmd: parking mount")
                if g_dev['obs'] is not None:  #THis gets called before obs is created
                    g_dev['obs'].send_to_user("Parking Mount. This can take a moment.")
                g_dev['obs'].time_of_last_slew=time.time()
                wait_for_slew()
                self.mount.Park()

                wait_for_slew()
            if self.settle_time_after_park > 0:
                time.sleep(self.settle_time_after_park)
                plog("Waiting " + str(self.settle_time_after_park) + " seconds for mount to settle.")
            try:
                g_dev['fil'].current_filter, _, _ = g_dev["fil"].set_name_command(
                    {"filter": 'dark'}, {}
                )
            except:
                pass

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''
        if self.mount.CanPark:
            if self.mount.AtPark:
                plog("mount cmd: unparking mount")
                g_dev['obs'].send_to_user("Unparking Mount. This can take a moment.")
                g_dev['obs'].time_of_last_slew=time.time()

                try:
                    wait_for_slew()
                    self.mount.Unpark()
                    wait_for_slew()
                except:
                    if g_dev['mnt'].theskyx:
                        g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                        wait_for_slew()
                        self.mount.Unpark()
                        wait_for_slew()

                if self.settle_time_after_unpark > 0:
                    time.sleep(self.settle_time_after_unpark)
                    plog("Waiting " + str(self.settle_time_after_unpark) + " seconds for mount to settle.")

                if self.home_after_unpark:
                    try:
                        wait_for_slew()
                        self.mount.FindHome()
                        wait_for_slew()
                    except:
                        try:
                            home_alt = self.settings["home_altitude"]
                            home_az = self.settings["home_azimuth"]
                            wait_for_slew()
                            g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True)
                            wait_for_slew()
                        except:
                            if g_dev['mnt'].theskyx:

                                plog("The SkyX had an error.")
                                plog("Usually this is because of a broken connection.")
                                plog("Killing then waiting 60 seconds then reconnecting")
                                g_dev['seq'].kill_and_reboot_theskyx(-1,-1)
                                self.mount.Unpark()
                                wait_for_slew()
                                home_alt = self.settings["home_altitude"]
                                home_az = self.settings["home_azimuth"]
                                g_dev['mnt'].go_command(alt=home_alt,az= home_az, skip_open_test=True)
                            else:
                                plog (traceback.format_exc())
                    wait_for_slew()


    def paddle(self):
        return
        '''
        The real way this should work is monitor if a speed button is pushed, then log the time and
        start the thread.  If no button pushed for say 30 seconds, stop thread and re-join.  That way
        image operations are minimally disrupted.

        Normally this will never be started, unless we are operating locally in the observatory.
        '''


    def  adjust_mount_reference(self, err_ha, err_dec):

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1' + str(g_dev['obs'].name))
        try:
            init_ra = mnt_shelf['ra_cal_offset']
            init_dec = mnt_shelf['dec_cal_offset']     # NB NB THese need to be modulo corrected, maybe limited
        except:
            init_ra = 0.0
            init_dec =0.0

        plog("initial:  ", init_ra, init_dec)
        mnt_shelf['ra_cal_offset'] = init_ra + err_ha
        mnt_shelf['dec_cal_offset'] = init_dec + err_dec
        plog("final:  ", mnt_shelf['ra_cal_offset'], mnt_shelf['dec_cal_offset'])
        mnt_shelf.close()
        return

    def  adjust_flip_reference(self, err_ha, err_dec):
        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        try:
            init_ra = mnt_shelf['flip_ra_cal_offset']
            init_dec = mnt_shelf['flip_dec_cal_offset']     # NB NB THese need to be modulo corrected, maybe limited
        except:
            init_ra = 0.0
            init_dec =0.0
        mnt_shelf['flip_ra_cal_offset'] = init_ra + err_ha    #NB NB NB maybe best to reverse signs here??
        mnt_shelf['flip_dec_cal_offset'] = init_dec + err_dec
        mnt_shelf.close()
        return

    def set_mount_reference(self, delta_ra, delta_dec):
        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        mnt_shelf['ra_cal_offset'] = delta_ra
        mnt_shelf['dec_cal_offset'] = delta_dec
        mnt_shelf.close()
        return

    def set_flip_reference(self, delta_ra, delta_dec):
        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        mnt_shelf['flip_ra_cal_offset'] = delta_ra
        mnt_shelf['flip_dec_cal_offset'] = delta_dec
        mnt_shelf.close()
        return

    def get_mount_reference(self):

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        delta_ra = mnt_shelf['ra_cal_offset'] + self.west_clutch_ra_correction   #Note set up at initialize time.
        delta_dec = mnt_shelf['dec_cal_offset'] +  self.west_clutch_dec_correction
        mnt_shelf.close()
        return delta_ra, delta_dec


    def get_flip_reference(self):
        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        delta_ra = mnt_shelf['flip_ra_cal_offset'] + self.east_flip_ra_correction
        delta_dec = mnt_shelf['flip_dec_cal_offset'] + self.east_flip_dec_correction
        mnt_shelf.close()
        return delta_ra, delta_dec

    def reset_mount_reference(self):

        mnt_shelf = shelve.open(self.obsid_path + 'ptr_night_shelf/' + 'mount1'+ str(g_dev['obs'].name))
        mnt_shelf['ra_cal_offset'] = 0.000
        mnt_shelf['dec_cal_offset'] = 0.000
        mnt_shelf['flip_ra_cal_offset'] = 0.000
        mnt_shelf['flip_dec_cal_offset'] = 0.000
        mnt_shelf.close()
        return

if __name__ == '__main__':
    req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
    opt = {'area': 50}
    m = Mount('ASCOM.PWI4.Telescope', "mnt1", {})
    m.paddle()