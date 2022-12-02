
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
import traceback
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
from pprint import pprint
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
RefrOn = True

ModelOn = True
RatesOn = True
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
        while g_dev['mnt'].mount.Slewing: #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
            if g_dev['mnt'].mount.Slewing: plog( 'm>')
            #if g_dev['enc'].status['dome_slewing']: st += 'd>'

            time.sleep(0.2)
            g_dev['obs'].update_status()            
            
    except:
        plog("Motion check faulted.")
        plog(traceback.format_exc())
        breakpoint()
    
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

        self.site = config['site']
        self.site_path = config['client_path']
        self.config = config
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True

        if "ASCOM.SoftwareBisque.Telescope" in config['mount']['mount1']['driver']:
            self.theskyx = True
        else:
            self.theskyx = False

#       plog('Can Asynch:  ', self.mount.CanSlewAltAzAsync)

        #hould put config Lat, lon, etc into mount, or at least check it is correct.

        self.site_coordinates = EarthLocation(lat=float(config['latitude'])*u.deg, \
                                lon=float(config['longitude'])*u.deg,
                                height=float(config['elevation'])*u.m)
        self.latitude_r = config['latitude']*DTOR
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel   #for now this implies the primary telescope on a mounting.
        self.mount_message = "-"
        if self.config['wema_is_active']:
            self.site_is_proxy = True
        else:
            self.site_is_proxy = False
        if self.site == 'MRC2':
            self.has_paddle = config['mount']['mount2']['has_paddle']
        else:
            self.has_paddle = config['mount']['mount1']['has_paddle']
            
        
        self.object = "Unspecified"
        self.current_sidereal = self.mount.SiderealTime
        self.current_icrs_ra = "Unspecified_Ra"
        self.current_icrs_dec = " Unspecified_Dec"
        self.delta_t_s = HTOSec/12   #5 minutes
        self.prior_roll_rate = 0
        self.prior_pitch_rate = 0
        self.offset_received = False
        self.west_clutch_ra_correction = config['mount']['mount1']['west_clutch_ra_correction']
        self.west_clutch_dec_correction = config['mount']['mount1']['west_clutch_dec_correction']
        self.east_flip_ra_correction = config['mount']['mount1']['east_flip_ra_correction']
        self.east_flip_dec_correction = config['mount']['mount1']['east_flip_dec_correction']
        self.refraction = 0
        self.target_az = 0   #Degrees Azimuth
        self.ha_corr = 0
        self.dec_corr = 0
        self.seek_commanded = False
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
        self.dec_offset = 0.0   #NB these should always start off at zero.
        if not self.mount.AtPark or self.mount.Tracking:
            #self.mount.RightAscensionRate = 0.0
            #self.mount.DeclinationRate = 0.0
            pass

        #self.reset_mount_reference()
        #self.site_in_automatic = config['site_in_automatic_default']
        #self.automatic_detail = config['automatic_detail_default']
        self.move_time = 0

        try:
            ra1, dec1 = self.get_mount_reference()
            ra2, dec2 = self.get_flip_reference()
            plog("Mount references clutch, flip (Look East):  ", ra1, dec1, ra2, dec2 )
        except:
            plog("No mount ref found.")
            pass
        #plog("Reset Mount Reference.")

        #self.reset_mount_reference()
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
        self.obs.long = config['longitude']*DTOR
        self.obs.lat = config['latitude']*DTOR

        plog("exiting mount _init")

    def check_connect(self):
        try:
            if self.mount.Connected:
                return
            else:
                plog('Found mount not connected, reconnecting.')
                self.mount.Connected = True
                return
        except:
            plog('Found mount not connected via try: block fail, reconnecting.')
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

        look_west = 0    #  NO NO NO!self.flip_correction_needed
        look_east = 1    #  This in not the stow side so flip needed.
        if self. mount.EquatorialSystem == 1:
            loop_count += 1
            if loop_count == 5:
               # breakpoint()
                pass
            self.get_current_times()
            try:
                if self.mount.sideOfPier == 1:
                    pierside = 1    #West (flip) side so Looking East   #Make this assignment a code-wide convention.
                else:
                    pierside = 0   #East side so Looking West
            except:
                pierside=0
                #print ("Mount does not report pier side.")
            self.current_sidereal = self.mount.SiderealTime
            uncorr_mech_ra_h = self.mount.RightAscension
            uncorr_mech_dec_d = self.mount.Declination
            self.sid_now_r = self.current_sidereal*HTOR   # NB NB NB  Using Mount sidereal time might be problematic. THis this through carefully.

            uncorr_mech_ha_r, uncorr_mech_dec_r = ptr_utility.transform_raDec_to_haDec_r(uncorr_mech_ra_h*HTOR, uncorr_mech_dec_d*DTOR, self.sid_now_r)
            self.hour_angle = uncorr_mech_ha_r*RTOH
            roll_obs_r, pitch_obs_r = ptr_utility.transform_mount_to_observed_r(uncorr_mech_ha_r, uncorr_mech_dec_r, pierside, loud=False)

            app_ra_r, app_dec_r, refr_asec = ptr_utility.obsToAppHaRa(roll_obs_r, pitch_obs_r, self.sid_now_r)
            self.refraction_rev = refr_asec
            '''
            # NB NB Read status could be used to recalculate and apply more accurate and current roll and pitch rates.
            '''
            #jnow_ra_r = ptr_utility.reduce_ra_r(app_ra_r - ra_cal_offset*HTOR)    # NB the mnt_refs are subtracted here.  Units are correct.
           # jnow_dec_r = ptr_utility.reduce_dec_r( app_dec_r - dec_cal_offset*DTOR)

            # try:
            #     if not self.mount.AtPark:   #Applying rates while parked faults.
            #         if self.mount.CanSetRightAscensionRate and self.prior_roll_rate != 0 :
            #             self.mount.RightAscensionRate =self.prior_roll_rate
            #         if self.mount.CanSetDeclinationRate and self.prior_pitch_rate != 0:
            #             self.mount.DeclinationRate = self.prior_pitch_rate
            #             #plog("Rate found:  ", self.prior_roll_rate, self.prior_pitch_rate, self.ha_corr, self.dec_corr)
            # except:
            #     plog("mount status rate adjust exception.")

            try:
                if self.mount.sideOfPier == look_west:
                    ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                else:
                    ra_cal_offset, dec_cal_offset = self.get_flip_reference()
            except:
                ra_cal_offset=0
                dec_cal_offset=0
                #print ("Mount does not report pier side")

            jnow_ra_r = ptr_utility.reduce_ra_r(app_ra_r - ra_cal_offset*HTOR)    # NB the mnt_refs are subtracted here.  Units are correct.
            jnow_dec_r = ptr_utility.reduce_dec_r( app_dec_r - dec_cal_offset*DTOR)
            jnow_ra_r, jnow_dec_r = ra_dec_fix_r(jnow_ra_r, jnow_dec_r)
            jnow_coord = SkyCoord(jnow_ra_r*RTOH*u.hour, jnow_dec_r*RTOD*u.degree, frame='fk5', equinox=self.equinox_now)   # NB NB 'fk5' ????
            icrs_coord = jnow_coord.transform_to(ICRS)
            self.current_icrs_ra = icrs_coord.ra.hour
            self.current_icrs_dec = icrs_coord.dec.degree
        else:

            try:
                ra_cal_offset, dec_cal_offset = self.get_mount_reference()
            except:
                ra_cal_offset=0
                dec_cal_offset=0

            self.current_icrs_ra = ra_fix_r(self.mount.RightAscension - ra_cal_offset)    #May not be applied in positioning
            self.current_icrs_dec = self.mount.Declination - dec_cal_offset
        return self.current_icrs_ra, self.current_icrs_dec

    def get_status(self):
        #This is for now 20201230, the primary place to source mount/tel status, needs fixing.\#NB a lot of the status time is taken up with Mount communication.
        self.check_connect()
        #breakpoint()
        #self.paddle()   # NB Should ohly be called if in config.
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
        if airmass > 10: airmass = 10.0   # We should caution the user if AM > 2, and alert them if >3
        airmass = round(airmass, 4)
        #Be careful to preserve order
        #plog(self.device_name, self.name)
        # if self.site_is_proxy:
        #     self.site_is_proxy = True

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
                #plog('In Status:  ', self.prior_roll_rate, self.prior_pitch_rate)
                #plog('From Mnt :  ', self.mount.RightAscensionRate, self.mount.DeclinationRate)
                icrs_ra, icrs_dec = self.get_mount_coordinates()  #20210430  Looks like this faulted during a slew.
            if self.prior_roll_rate == 0:
                pass
            ha = icrs_ra - self.current_sidereal
            if ha < 12:
                ha  += 24
            if ha > 12:
                ha -= 24
            try:
                self.pier_side = self.mount.SideOfPier  #DID not work early on with PW Alt Az mounts
                #plog('ASCOM SideOfPier ==  ', self.pier_side)
            except:
                self.pier_side = 0.   # This explicitly defines alt-az (Planewave) as Looking West (tel on East side)
            if self.pier_side == 0:
                self.pier_side_str ="Looking West"
            else:
                self.pier_side_str = "Looking East"
            #breakpoint()
            status = {
                'timestamp': round(time.time(), 3),
                'right_ascension': round(icrs_ra, 5),
                'declination': round(icrs_dec, 4),
                'sidereal_time': round(self.current_sidereal, 5),  #Should we add HA?
                'refraction': round(self.refraction_rev, 2),
                'correction_ra': round(self.ha_corr, 4),  #If mount model = 0, these are very small numbers.
                'correction_dec': round(self.dec_corr, 4),
                'hour_angle': round(ha, 4),
                'demand_right_ascension_rate': round(self.prior_roll_rate, 9),
                'mount_right_ascension_rate': round(self.mount.RightAscensionRate, 9),   #Will use sec-RA/sid-sec
                'demand_declination_rate': round(self.prior_pitch_rate, 8),
                'mount_declination_rate': round(self.mount.DeclinationRate, 8),
                'pier_side':self.pier_side,
                'pier_side_str': self.pier_side_str,
                'azimuth': round(self.mount.Azimuth, 3),
                'target_az': round(self.target_az, 3),
                'altitude': round(alt, 3),
                'zenith_distance': round(zen, 3),
                'airmass': round(airmass,4),
                'coordinate_system': str(self.rdsys),
                'equinox':  self.equinox_now,
                'pointing_instrument': str(self.inst),  # needs fixing
                'is_parked': self.mount.AtPark,     #  Send strings to AWS so JSON does not change case  Wrong. 20211202 'False' evaluates to True
                'is_tracking': self.mount.Tracking,
                'is_slewing': self.mount.Slewing,
                'message': str(self.mount_message[:54]),
                #'site_in_automatic': self.site_in_automatic,
                #'automatic_detail': str(self.automatic_detail),
                'move_time': self.move_time
            }
            # This write the mount conditin back to the dome, only needed if self.is_dome
# =============================================================================
#             #  Here we should add any correction to fine tune the dome azimuth and sent that to
#             # the dome instead of having the dome track the telescope.  Note we also need to
#             # control DOme slaving at this point.  20220211 WER
# =============================================================================

            try:
                if g_dev['enc'].is_dome:
                    try:
                        mount = open(g_dev['wema_share_path']+'mnt_cmd.txt', 'w')
                        mount.write(json.dumps(status))
                        mount.close()
                    except:
                        try:
                            time.sleep(3)
                            # mount = open(self.config['wema_path']+'mnt_cmd.txt', 'r')
                            # mount.write(json.loads(status))
                            mount = open(g_dev['wema_share_path']+'mnt_cmd.txt', 'w')
                            mount.write(json.dumps(status))
                            mount.close()
                        except:
                            try:
                                time.sleep(3)
                                mount = open(g_dev['wema_share_path']+'mnt_cmd.txt', 'w')
                                mount.write(json.dumps(status))
                                mount.close()
                            except:
                                mount = open(g_dev['wema_share_path']+'mnt_cmd.txt', 'w')
                                mount.write(json.dumps(status))
                                mount.close()
                                plog("3rd try to append to enc-cmd  list.")
            except:
                pass
        else:
            plog('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}

        return status  #json.dumps(status)

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
        try:
            ra_off, dec_off = self.get_mount_reference()
        except:
            #print ("get_quick_status offset... is zero")
            ra_off = 0
            dec_off = 0
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
        #plog(pre)
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
        #plog(t_avg)
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
            plog(f"Command <{action}> not recognized.")


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
    Having two similar functions here is confusing and error prone.
    Go Command responds to commands from AWS.  Go Coords responds to
    internal changes of pointing occasion by the program and passed
    in as ra and dec direc tparameters, not dictionaries.

    '''

    def go_command(self, req, opt,  offset=False, calibrate=False, auto_center=False):
        ''' Slew to the given ra/dec coordinates. '''
        plog("mount cmd. slewing mount, req, opt:  ", req, opt)

        ''' unpark the telescope mount '''  #  NB can we check if unparked and save time?

        try:
            self.object = opt['object']
        except:
            self.object = 'unspecified'    #NB could possibly augment with "Near --blah--"
        if self.mount.CanPark:
            #plog("mount cmd: unparking mount")
            if self.mount.AtPark:
                self.mount.Unpark()   #  Note we do not open the dome since we may be mount testing in the daytime.
        try:
            clutch_ra = g_dev['mnt']['mount1']['east_clutch_ra_correction']
            clutch_dec = g_dev['mnt']['mount1']['east_clutch_dec_correction']
        except:
            clutch_ra = 0.0
            clutch_dec = 0.0
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
            object_is_moon = True

        else:
            object_is_moon = False

        try:
            icrs_ra, icrs_dec = self.get_mount_coordinates()
            if offset:   #This offset version supplies offsets as a fraction of the Full field.
                #note it is based on mount coordinates.
                #Note we never look up the req dictionary ra or dec.
                if self.offset_received:
                    plog("This is a second offset, are you sure you want to do this?")
                #
                offset_x = float(req['image_x']) - 0.5   #Fraction of field.
                offset_y = float(req['image_y']) - 0.5
                x_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['x_field_deg']
                y_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['y_field_deg']
                field_x = x_field_deg/15.   #  /15 for hours.
                field_y = y_field_deg
                #20210317 Changed signs fron Neyle.  NEEDS CONFIG File level or support.

                self.ra_offset = -offset_x*field_x/2  #/4   #NB NB 20201230 Signs needs to be verified. 20210904 used to be +=, which did not work.
                self.dec_offset = offset_y*field_y/2 #/4    #NB where the 4 come from?                plog("Offsets:  ", round(self.ra_offset, 5), round(self.dec_offset, 4))
                plog('Offsets:  ', offset_x, self.ra_offset, offset_y, self.dec_offset)

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
                    plog("Stored calibration offsets:  ",round(ra_cal_offset, 5), round(dec_cal_offset, 4))
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
                    plog("No outstanding offset available for calibration, reset existing calibration.")
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
            elif auto_center:  #Note does not need req or opt
            #breakpoint()
                if self.offset_received:
                    ra, dec, time_of_last = g_dev['obs'].get_last_reference()
                    ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                    plog("Stored calibration offsets:  ",round(ra_cal_offset, 5), round(dec_cal_offset, 4))
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
                    plog("No outstanding offset available for calibration, reset existing calibration.")
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
            else:   #  NB confusing logic   this is meant to be the simple seek case.
                    #  Here we DO read the req dictionary ra and dec or appear to also get alt and az,but that is not implemnented WER 20220212
                try:
                    ra = float(req['ra'])
                    dec = float(req['dec'])
                    self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                    self.dec_offset = 0
                    self.offset_received = False
                    ra_dec = True
                    alt_az = False

                except:
                    try:
                        az = float(req['az'])
                        alt = float(req['alt'])
                        self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                        self.dec_offset = 0
                        self.offset_received = False
                        ra_dec = False
                        alt_az = True

                    except:
                        ha = float(req['ha'])
                        dec = float(req['dec'])
                        #ra = float (ra) - self.sid_now_r
                        #print (float (ha) - self.sid_now_r)
                        #print (self.sid_now_r)
                        #print (self.mount.SiderealTime)
                        #ra = ha+ self.mount.SiderealTime
                        az, alt = ptr_utility.transform_haDec_to_azAlt(ha, dec, lat=self.config['latitude'])

                        self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                        self.dec_offset = 0
                        self.offset_received = False
                        ra_dec = False
                        #ra_dec = False
                        alt_az = True

        except:
            plog("Bad coordinates supplied.")
            g_dev['obs'].send_to_user("Bad coordinates supplied! ",  p_level="WARN")
            self.message = "Bad coordinates supplied, try again."
            self.offset_received = False
            self.ra_offset = 0
            self.dec_offset = 0
            return

        # Tracking rate offsets from sidereal in arcseconds per SI second, default = 0.0
        tracking_rate_ra = opt.get('tracking_rate_ra', 0)
        tracking_rate_dec = opt.get('tracking_rate_dec', 0)
# ============================================================================= Get rid of this, redundant application of the offset
#         delta_ra, delta_dec = self.get_mount_reference()
#         ra, dec = ra_dec_fix_h(ra + delta_ra, dec + delta_dec)   #Plus compensates for measured offset
# =============================================================================
        self.move_time = time.time()
        if object_is_moon:
            self.go_coord(ra1, dec1, tracking_rate_ra=dra_moon, tracking_rate_dec = ddec_moon)
        elif alt_az == True:
            self.move_to_altaz(az, alt)

        elif ra_dec == True:
            self.go_coord(ra, dec, tracking_rate_ra=tracking_rate_ra, tracking_rate_dec = tracking_rate_dec)
        self.object = opt.get("object", "")
        if self.object == "":
           # plog("Go to unamed target.")
            g_dev['obs'].send_to_user("Going to un-named target!  ",  p_level="INFO")
        else:
            #plog("Going to:  ", self.object)   #NB Needs cleaning up.
            g_dev['obs'].send_to_user("Going to:  " + str( self.object),  p_level="INFO")

        # On successful movement of telescope reset the solving timer
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000

    def re_seek(self, dither):
        if dither == 0:
            self.go_coord(self.last_ra, self.last_dec, self.last_tracking_rate_ra, self.last_tracking_rate_dec)
        else:
            pass#breakpoint()

    def go_coord(self, ra, dec, tracking_rate_ra=0, tracking_rate_dec=0, reset_solve=True):  #Note these rates need a system specification
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
            #plog("mount cmd: unparking mount")
            if self.mount.AtPark:
                self.mount.Unpark()   #  Note we do not open the dome since we may be mount testing in the daytime.
        #Note this initiates a mount move.  WE should Evaluate if the destination is on the flip side and pick up the
        #flip offset.  So a GEM could track into positive HA territory without a problem but the next reseek should
        #result in a flip.  So first figure out if there will be a flip:

        try:
            new_pierside =  self.mount.DestinationSideOfPier(ra, dec) #  A tuple gets returned: (pierside, Ra.h and dec.d)
            try:                          #  NB NB Might be good to log is flipping on a re-seek.
                if len(new_pierside) > 1:
                    if new_pierside[0] == 0:
                        delta_ra, delta_dec = self.get_mount_reference()
                        pier_east = 1
                    else:
                        delta_ra, delta_dec = self.get_flip_reference()
                        pier_east = 0
            except:
                if new_pierside == 0:
                    delta_ra, delta_dec = self.get_mount_reference()
                    pier_east = 1
                else:
                    delta_ra, delta_dec = self.get_flip_reference()
                    pier_east = 0

            #Update incoming ra and dec with mounting offsets.
            ra += delta_ra #NB it takes a restart to pick up a new correction which is also J.now.
            dec += delta_dec
        except:
            print ("mount really doesn't like pierside calls")
            pier_east = 1
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
        self.sid_now_r = self.mount.SiderealTime*HTOR   #NB NB ADDED THIS FOR SRO, WHY IS THIS NEEDED?

        self.ha_obs_r, self.dec_obs_r, self.refr_asec = ptr_utility.appToObsRaHa(ra_app_h*HTOR, dec_app_d*DTOR, self.sid_now_r)
        #ra_obs_r, dec_obs_r = ptr_utility.transformHatoRaDec(ha_obs_r, dec_obs_r, self.sid_now_r)
        #Here we would convert to model and calculate tracking rate correction.
        self.ha_mech, self.dec_mech = ptr_utility.transform_observed_to_mount_r(self.ha_obs_r, self.dec_obs_r, pier_east, loud=False, enable=True)
        self.ra_mech, self.dec_mech = ptr_utility.transform_haDec_to_raDec_r(self.ha_mech, self.dec_mech, self.sid_now_r)
        self.ha_corr = ptr_utility.reduce_ha_r(self.ha_mech -self. ha_obs_r)*RTOS
        self.dec_corr = ptr_utility.reduce_dec_r(self.dec_mech - self.dec_obs_r)*RTOS

        try:
            self.mount.Tracking = True
        except:
            print ("this mount may not accept tracking commands")
        self.move_time = time.time()
        az, alt = ptr_utility.transform_haDec_to_azAlt_r(self.ha_mech, self.dec_mech, self.latitude_r)
        plog('MODEL HA, DEC, AZ, Refraction:  (asec)  ', self.ha_corr, self.dec_corr, az*RTOD, self.refr_asec)
        self.target_az = az*RTOD


        self.mount.SlewToCoordinatesAsync(self.ra_mech*RTOH, self.dec_mech*RTOD)  #Is this needed?
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

    def slewToSkyFlatAsync(self):
        az, alt = self.astro_events.flat_spot_now()
        self.unpark_command()        

        if self.mount.Tracking == True:
            if not self.theskyx:   
                self.mount.Tracking = False
            else:
                plog("mount tracking but it is theskyx and I haven't figure out how to turn it off yet. ")

        self.move_time = time.time()
        try:
            self.move_to_altaz(az, alt)
            # On successful movement of telescope reset the solving timer
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000

        except:
            print (traceback.format_exc())
            #print ("NEED TO POINT TELESCOPE TO RA AND DEC, MOUNT DOES NOT HAVE AN ALTAZ request in the driver")



    def stop_command(self, req, opt):
        plog("mount cmd: stopping mount")
        self.mount.AbortSlew()

    def home_command(self, req, opt):
        ''' slew to the home position '''
        plog("mount cmd: homing mount")
        if self.mount.AtHome:
            plog("Mount is at home.")
        elif False: #self.mount.CanFindHome:    # NB what is this all about?
            plog(f"can find home: {self.mount.CanFindHome}")
            self.mount.Unpark()
            #home_alt = self.settings["home_altitude"]
            #home_az = self.settings["home_azimuth"]
            #self.move_to_altaz(home_alt, home_az)
            self.move_time = time.time()
            self.mount.FindHome()
        else:
            plog("Mount is not capable of finding home. Slewing to zenith.")
            self.move_time = time.time()
            self.move_to_altaz(0, 80)
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
        plog(self.mount.CanPark)
        if self.mount.CanPark:
            plog("mount cmd: parking mount")
            self.move_time = time.time()
            self.mount.Park()

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''
        if self.mount.CanPark:
            plog("mount cmd: unparking mount")
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
#         plog(len(temp_1))
#         self._paddle.close()
#         #print ('|' + temp[16:18] +'|')
#         button = temp_1[14]
#         spd= temp_1[13]
#         direc = ''
#         speed = 0.0
#         plog("Btn:  ", button, "Spd:  ", speed, "Dir:  ", direc)
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

#         plog(button, spd, direc, speed)
# #            if direc != '':
#         #plog(direc, speed)
#         _mount = self.mount
#         #Need to add diagonal moves
#         if direc == 'N':
#             try:
#                 _mount.DeclinationRate = NS*speed
#                 self.paddleing = True
#             except:
#                 pass
#             plog('cmd:  ', direc,  NS*speed)
#         if direc == 'S':
#             try:
#                 _mount.DeclinationRate = -NS*speed
#                 self.paddleing = True
#             except:
#                 pass
#             plog('cmd:  ',direc,  -NS*speed)
#         if direc == 'E':
#             try:
#                 _mount.RightAscensionRate = EW*speed/15.   #Not quite the correct divisor.
#                 self.paddleing = True
#             except:
#                 pass
#             plog('cmd:  ',direc, EW*speed/15.)
#         if direc == 'W':
#             try:
#                 _mount.RightAscensionRate = -EW*speed/15.
#                 self.paddleing = True
#             except:
#                 pass
#             plog('cmd:  ',direc, -EW*speed/15.)
#         if direc == '':
#             try:
#                 _mount.DeclinationRate = 0.0
#                 _mount.RightAscensionRate = 0.0
#             except:
#                 plog("Rate set excepetion.")
#             self.paddleing = False
#         self._paddle.close()
#         return

    def  adjust_mount_reference(self, err_ha, err_dec):
        #old_ha, old_dec = self.get_mount_reference()
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        init_ra = mnt_shelf['ra_cal_offset']
        init_dec = mnt_shelf['dec_cal_offset']     # NB NB THese need to be modulo corrected, maybe limited
        plog("initial:  ", init_ra, init_dec)
        mnt_shelf['ra_cal_offset'] = init_ra + err_ha
        mnt_shelf['dec_cal_offset'] = init_dec + err_dec
        plog("final:  ", mnt_shelf['ra_cal_offset'], mnt_shelf['dec_cal_offset'])
        mnt_shelf.close()
        return

    def  adjust_flip_reference(self, err_ha, err_dec):
        #old_ha, old_dec = self.get_mount_reference()
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        init_ra = mnt_shelf['flip_ra_cal_offset']
        init_dec = mnt_shelf['flip_dec_cal_offset']     # NB NB THese need to be modulo corrected, maybe limited

        plog("initial:  ", init_ra, init_dec)
        mnt_shelf['flip_ra_cal_offset'] = init_ra + err_ha    #NB NB NB maybe best to reverse signs here??
        mnt_shelf['flip_dec_cal_offset'] = init_dec + err_dec
        plog("final:  ", mnt_shelf['flip_ra_cal_offset'], mnt_shelf['flip_dec_cal_offset'])
        mnt_shelf.close()
        return

    def set_mount_reference(self, delta_ra, delta_dec):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = delta_ra
        mnt_shelf['dec_cal_offset'] = delta_dec
        mnt_shelf.close()
        return

    def set_flip_reference(self, delta_ra, delta_dec):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['flip_ra_cal_offset'] = delta_ra
        mnt_shelf['flip_dec_cal_offset'] = delta_dec
        mnt_shelf.close()
        return

    def get_mount_reference(self):

        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        delta_ra = mnt_shelf['ra_cal_offset'] + self.west_clutch_ra_correction   #Note set up at initialize time.
        delta_dec = mnt_shelf['dec_cal_offset'] +  self.west_clutch_dec_correction
        mnt_shelf.close()
        return delta_ra, delta_dec

    def get_flip_reference(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        #NB NB NB The ease may best have a sign change asserted.
        delta_ra = mnt_shelf['flip_ra_cal_offset'] + self.east_flip_ra_correction
        delta_dec = mnt_shelf['flip_dec_cal_offset'] + self.east_flip_dec_correction
        mnt_shelf.close()
        return delta_ra, delta_dec

    def reset_mount_reference(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = 0.000
        mnt_shelf['dec_cal_offset'] = 0.000
        mnt_shelf['flip_ra_cal_offset'] = 0.000
        mnt_shelf['flip_dec_cal_offset'] = 0.000
        mnt_shelf.close()
        return
    
    def move_to_altaz(self, az, alt):
        print ("Moving to Alt " + str(alt) + " Az " + str(az))
        if self.config['mount']['mount1']['has_ascom_altaz'] == True:
            self.mount.SlewToAltAzAsync(az, alt)
            wait_for_slew()
        else:
            plog("Recaclulating RA and DEC for Alt Az move")
            aa = AltAz (location=self.site_coordinates, obstime=Time.now())
            #breakpoint()
            tempcoord= SkyCoord(az=az*u.deg, alt=alt*u.deg, frame=aa)
            tempcoord=tempcoord.transform_to(frame='icrs')
            tempRA=tempcoord.ra.deg / 15
            tempDEC=tempcoord.dec.deg
            print (tempRA)
            print (tempDEC)
            #self.site_coordinates
            self.mount.SlewToCoordinatesAsync(tempRA, tempDEC)
            wait_for_slew()
        

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
                plog('Probe class called with:  ', pCom)
                self.commPort = pCom

            def probeRead(self):
               with serial.Serial(self.commPort, timeout=0.3) as com:
                   com.write(b'R1\n')
                   self.probePosition = float(com.read(6).decode())
                   com.close()
                   plog(self.probePosition)
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
#    plog(m.get_average_status(pre, post))
    #plog(c.get_ascom_description())