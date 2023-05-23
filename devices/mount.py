
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
import shelve
from math import cos, radians    #"What plan do we have for making some imports be done this way, elg, import numpy as np...?"
from global_yard import g_dev    #"Ditto guestion we are importing a single object instance."

from astropy.time import Time

from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS,  \
                         EarthLocation, AltAz, get_sun, get_moon
                         #This should be removed or put in a try

import ptr_utility
#from config import site_config
import math
#from pprint import pprint
import ephem
from ptr_utility import plog
#from planewave import platesolve


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

        self.obsid = config['obs_id']
        self.obsid_path = g_dev['obs'].obsid_path
        self.config = config
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True
        
        self.driver = driver
        
        
        if "ASCOM.SoftwareBisque.Telescope" in driver:
            self.theskyx = True
        else:
            self.theskyx = False

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
        if self.obsid == 'MRC2':
            self.has_paddle = config['mount']['mount2']['has_paddle']
        else:
            self.has_paddle = config['mount']['mount1']['has_paddle']
            
        
        self.object = "Unspecified"
        try:
            #self.current_sidereal = self.mount.SiderealTime
            # Replaced mount call above with much faster more accurate astropy calculation below
            self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)
            
        except:
            plog ("Failed to get the current sidereal time from the mount.")
        self.current_icrs_ra = self.mount.RightAscension
        self.current_icrs_dec = self.mount.Declination
        
        
        
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
        self.dec_offset = 0.0   #NB these should always start off at zero.
        #if not self.mount.AtPark or self.mount.Tracking:
            #self.mount.RightAscensionRate = 0.0
            #self.mount.DeclinationRate = 0.0
            #pass

        #self.reset_mount_reference()
        #self.obsid_in_automatic = config['site_in_automatic_default']
        #self.automatic_detail = config['automatic_detail_default']
        self.move_time = 0

        try:
            ra1, dec1 = self.get_mount_reference()
            ra2, dec2 = self.get_flip_reference()
            plog("Mount references & flip (Look East):  ", ra1, dec1, ra2, dec2 )
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

        self.theskyx_tracking_rescues = 0
        
        # Here we figure out if it can report pierside. If it cannot, we need 
        # not keep calling the mount to ask for it, which is slow and prone
        # to an ascom crash.
        try:
            self.pier_side = g_dev[
                "mnt"
            ].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
            self.can_report_pierside = True
        except Exception as e:
            #plog (e)
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
        except Exception as e:
            #plog (e)
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
        self.last_ra = self.mount.RightAscension
            
        self.last_dec = self.mount.Declination
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
        
        #breakpoint()
        
        
        # just some back to basics coordinates to test pointing issues
        self.mtf_dec_offset=0
        self.mtf_ra_offset=0
        
        
        

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
                breakpoint()
            
            plog ("Trying full-scale reboot")
            try:
                win32com.client.pythoncom.CoInitialize()
                self.mount = win32com.client.Dispatch(self.driver)
                self.mount.Connected = True
                if self.mount.Connected:
                    return
            except Exception as e:
                plog (traceback.format_exc())
                plog ("mount full scale reboot failed.")
                breakpoint()
            

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
                if self.can_report_pierside == True:
                    if self.mount.sideOfPier == 1:
                        self.pier_side = 1    #West (flip) side so Looking East   #Make this assignment a code-wide convention.
                    else:
                        self.pier_side = 0   #East side so Looking West
            except:
                self.pier_side=0
                
            # Replaced mount call above with much faster more accurate astropy calculation below
            self.current_sidereal = float((Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle)

            uncorr_mech_ra_h = self.mount.RightAscension
            uncorr_mech_dec_d = self.mount.Declination
            self.sid_now_r = self.current_sidereal*HTOR   # NB NB NB  Using Mount sidereal time might be problematic. THis this through carefully.

            uncorr_mech_ha_r, uncorr_mech_dec_r = ptr_utility.transform_raDec_to_haDec_r(uncorr_mech_ra_h*HTOR, uncorr_mech_dec_d*DTOR, self.sid_now_r)
            self.hour_angle = uncorr_mech_ha_r*RTOH
            roll_obs_r, pitch_obs_r = ptr_utility.transform_mount_to_observed_r(uncorr_mech_ha_r, uncorr_mech_dec_r, self.pier_side, loud=False)

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
                if self.can_report_pierside == True:
                    if self.pier_side == 1:
                        ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                    else:
                        ra_cal_offset, dec_cal_offset = self.get_flip_reference()
                else:
                    ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                    #ra_cal_offset=0
                    #dec_cal_offset=0
            except:
                try:
                    ra_cal_offset, dec_cal_offset = self.get_mount_reference()
                except:
                    plog ("couldn't get mount offset")
                    #self.reset_mount_reference()
                    ra_cal_offset=0
                    dec_cal_offset=0

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
                plog ("couldn't get offset")
                ra_cal_offset=0
                dec_cal_offset=0

            self.current_icrs_ra = ra_fix_r(self.mount.RightAscension - ra_cal_offset)    #May not be applied in positioning
            self.current_icrs_dec = self.mount.Declination - dec_cal_offset
        return self.current_icrs_ra, self.current_icrs_dec

    def get_status(self):
        
        if self.tel == False:
            #breakpoint()
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
                'right_ascension': round(icrs_ra, 5),
                'declination': round(icrs_dec, 4),
                'sidereal_time': round(self.current_sidereal, 5),  #Should we add HA?
                'refraction': round(self.refraction_rev, 2),
                'correction_ra': round(self.ha_corr, 4),  #If mount model = 0, these are very small numbers.
                'correction_dec': round(self.dec_corr, 4),
                'hour_angle': round(ha, 4),
                'demand_right_ascension_rate': round(self.prior_roll_rate, 9),
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
                'equinox':  self.equinox_now,
                'pointing_instrument': str(self.inst),  # needs fixing
                #'is_parked': self.mount.AtPark,     #  Send strings to AWS so JSON does not change case  Wrong. 20211202 'False' evaluates to True
                #'is_tracking': self.mount.Tracking,
                #'is_slewing': self.mount.Slewing,
                'message': str(self.mount_message[:54]),
                #'site_in_automatic': self.obsid_in_automatic,
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

        self.check_connect()
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

            self.go_command(req, opt)   #  Entered from Target Explorer or Telescope tabs.
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
            req['ra'] =  (Time(datetime.datetime.utcnow(), scale='utc', location=g_dev['mnt'].site_coordinates).sidereal_time('apparent')*u.deg) / u.deg / u.hourangle
            
            req['dec'] = 0.0
            self.go_command(req, opt, offset=False)
        elif action == "park":
            self.park_command(req, opt)
        elif action == "unpark":
            self.unpark_command(req, opt)
        elif action == 'center_on_pixels':
            plog (command)
            # Need to convert image fraction into offset
            image_x = req['image_x']
            image_y = req['image_y']            
            # And the current pixel scale
            pixscale=g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["pix_scale"]
            pixscale_hours=(pixscale/60/60) / 15
            pixscale_degrees=(pixscale/60/60) 
            # Calculate the RA and Dec of the pointing
            req['ra']=g_dev["mnt"].current_icrs_ra + (((float(image_x)-0.5) * g_dev['cam'].camera_x_size) * pixscale_hours)
            req['dec']=g_dev["mnt"].current_icrs_dec + (((float(image_y)-0.5)* g_dev['cam'].camera_y_size) * pixscale_degrees)
            plog ("X centre shift: " + str((((float(image_x)-0.5)* g_dev['cam'].camera_x_size)) * pixscale_hours))
            plog ("Y centre shift: " + str((((float(image_y)-0.5)* g_dev['cam'].camera_y_size)) * pixscale_degrees))
            plog ("New RA: " + str(req['ra']))
            plog ("New DEC: " + str(req['dec']))
            
            self.go_command(req, opt, offset=True, calibrate=False)

        elif action == 'sky_flat_position':
            self.slewToSkyFlatAsync(skip_open_test=True)
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
        
        # First thing to do is check the position of the sun and
        # Whether this violates the pointing principle. 
        sun_coords=get_sun(Time.now())        
        if 'ra' in req:
            ra = float(req['ra'])
            dec = float(req['dec'])
            temppointing=SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
            temppointingaltaz=temppointing.transform_to(AltAz(location=self.site_coordinates, obstime=Time.now()))
            alt = temppointingaltaz.alt.degree
            az = temppointingaltaz.az.degree
                                                    
        elif 'az' in req:
            az = float(req['az'])
            alt = float(req['alt'])
            temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)          
        elif 'ha' in req:
            ha = float(req['ha'])
            dec = float(req['dec'])
            az, alt = ptr_utility.transform_haDec_to_azAlt(ha, dec, lat=self.config['latitude'])
            temppointing = AltAz(location=self.site_coordinates, obstime=Time.now(), alt=alt*u.deg, az=az*u.deg)    
        sun_dist = sun_coords.separation(temppointing)

        if sun_dist.degree <  self.config['closest_distance_to_the_sun']:
            if not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                g_dev['obs'].send_to_user("Refusing pointing request as it is too close to the sun: " + str(sun_dist.degree) + " degrees.")
                plog("Refusing pointing request as it is too close to the sun: " + str(sun_dist.degree) + " degrees.")
                return
        
        # Second thing, check that we aren't pointing at the moon
        # UNLESS we have actually chosen to look at the moon.
        if self.object in ['Moon', 'moon', 'Lune', 'lune', 'Luna', 'luna',]:
            plog("Moon Request detected")
        else:
            moon_coords=get_moon(Time.now())          
            moon_dist = moon_coords.separation(temppointing)
            if moon_dist.degree <  self.config['closest_distance_to_the_moon']:
                g_dev['obs'].send_to_user("Refusing pointing request as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                plog("Refusing pointing request as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
                return
        
        # Third thing, check that the requested coordinates are not
        # below a reasonable altitude
        if alt < self.config['lowest_requestable_altitude']:
            g_dev['obs'].send_to_user("Refusing pointing request as it is too low: " + str(alt) + " degrees.")
            plog("Refusing pointing request as it is too low: " + str(alt) + " degrees.")
            return
        
        # Fourth thing, check that the roof is open and we are enabled to observe
        if (g_dev['obs'].open_and_enabled_to_observe==False and g_dev['enc'].mode == 'Automatic') and (not g_dev['obs'].debug_flag):
            g_dev['obs'].send_to_user("Refusing pointing request as the observatory is not enabled to observe.")
            plog("Refusing pointing request as the observatory is not enabled to observe.")
            return

        # Fifth thing, check that the sky flat latch isn't on
        # (I moved the scope during flats once, it wasn't optimal)
        if g_dev['seq'].morn_sky_flat_latch  or g_dev['seq'].eve_sky_flat_latch or g_dev['seq'].sky_flat_latch or g_dev['seq'].bias_dark_latch:
            g_dev['obs'].send_to_user("Refusing pointing request as the observatory is currently undertaking flats or calibration frames.")
            plog("Refusing pointing request as the observatory is currently taking flats or calibration frmaes.")
            return
            
        
        plog("mount cmd. slewing mount, req, opt:  ", req, opt)

        ''' unpark the telescope mount '''  #  NB can we check if unparked and save time?

        try:
            self.object = opt['object']
        except:
            self.object = 'unspecified'    #NB could possibly augment with "Near --blah--"
        self.unpark_command()  
        #g_dev['obs'].send_to_user("Slewing Telescope.")
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

        icrs_ra, icrs_dec = self.get_mount_coordinates()


        # MTF has commented out this section because it is not working. 
        # Not necessarily deleting it, 
        #
        # try:
        #     icrs_ra, icrs_dec = self.get_mount_coordinates()
        #     if offset:   #This offset version supplies offsets as a fraction of the Full field.
        #         #note it is based on mount coordinates.
        #         #Note we never look up the req dictionary ra or dec.
        #         if self.offset_received:
        #             plog("This is a second offset, are you sure you want to do this?")
        #         #
        #         offset_x = float(req['image_x']) - 0.5   #Fraction of field.
        #         offset_y = float(req['image_y']) - 0.5
        #         x_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['x_field_deg']
        #         y_field_deg = g_dev['cam'].config['camera']['camera_1_1']['settings']['y_field_deg']
        #         field_x = x_field_deg/15.   #  /15 for hours.
        #         field_y = y_field_deg
        #         #20210317 Changed signs fron Neyle.  NEEDS CONFIG File level or support.

        #         self.ra_offset = -offset_x*field_x/2  #/4   #NB NB 20201230 Signs needs to be verified. 20210904 used to be +=, which did not work.
        #         self.dec_offset = offset_y*field_y/2 #/4    #NB where the 4 come from?                plog("Offsets:  ", round(self.ra_offset, 5), round(self.dec_offset, 4))
        #         plog('Offsets:  ', offset_x, self.ra_offset, offset_y, self.dec_offset)

        #         if not self.offset_received:
        #             self.ra_prior, self.dec_prior = icrs_ra, icrs_dec #Do not let this change.
        #         self.offset_received = True   # NB Above we are accumulating offsets, but should not need to.
        #         #NB NB Position angle may need to be taken into account 20201230
        #         #apply this to the current telescope position(which may already incorporate a calibration)
        #         #need to get the ICRS telescope position.

        #         #Set up to go to the new position.
        #         ra, dec = ra_dec_fix_h(icrs_ra + self.ra_offset, icrs_dec + self.dec_offset)
        #         alt_az = False

        #     elif calibrate:  #Note does not need req or opt
        #         #breakpoint()
        #         if self.offset_received:
        #             ra_cal_offset, dec_cal_offset = self.get_mount_reference()
        #             plog("Stored calibration offsets:  ",round(ra_cal_offset, 5), round(dec_cal_offset, 4))
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()
        #             accum_ra_offset = icrs_ra - self.ra_prior
        #             accum_dec_offset = icrs_dec - self.dec_prior
        #             ra_cal_offset += accum_ra_offset #self.ra_offset  #NB WE are adding an already correctly signed offset.The offset is positive to right of screen therefore a smaller numer on the RA line.
        #             dec_cal_offset += accum_dec_offset #self.dec_offset
        #             self.set_mount_reference(ra_cal_offset, dec_cal_offset)
        #             self.ra_offset = 0
        #             self.dec_offset = 0
        #             self.offset_received = False
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()  #20210116 THis is returning some form of apparent
        #             ra = self.ra_prior #icrs_ra
        #             dec = self.dec_prior #icrs_dec
        #             #We could just return but will seek just to be safe
        #             alt_az = False
        #         else:
        #             plog("No outstanding offset available for calibration, reset existing calibration.")
        #             # NB We currently use this path to clear a calibration.  But should be ad explicit Command instead. 20201230
        #             # breakpoint()
        #             self.reset_mount_reference()
        #             self.ra_offset = 0
        #             self.dec_offset = 0
        #             self.offset_received = False
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()
        #             ra = self.ra_prior #icrs_ra
        #             dec = self.dec_prior #icrs_dec
        #             alt_az = False
        #             #We could just return but will seek just to be safe
        #     elif auto_center:  #Note does not need req or opt
        #     #breakpoint()
        #         if self.offset_received:
        #             ra, dec, time_of_last = g_dev['obs'].get_last_reference()
        #             ra_cal_offset, dec_cal_offset = self.get_mount_reference()
        #             plog("Stored calibration offsets:  ",round(ra_cal_offset, 5), round(dec_cal_offset, 4))
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()
        #             accum_ra_offset = icrs_ra - self.ra_prior
        #             accum_dec_offset = icrs_dec - self.dec_prior
        #             ra_cal_offset += accum_ra_offset #self.ra_offset  #NB WE are adding an already correctly signed offset.The offset is positive to right of screen therefore a smaller numer on the RA line.
        #             dec_cal_offset += accum_dec_offset #self.dec_offset
        #             self.set_mount_reference(ra_cal_offset, dec_cal_offset)
        #             self.ra_offset = 0
        #             self.dec_offset = 0
        #             self.offset_received = False
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()  #20210116 THis is returning some form of apparent
        #             ra = self.ra_prior #icrs_ra
        #             dec = self.dec_prior #icrs_dec
        #             #We could just return but will seek just to be safe
        #             alt_az = False
        #         else:
        #             plog("No outstanding offset available for calibration, reset existing calibration.")
        #             # NB We currently use this path to clear a calibration.  But should be ad explicit Command instead. 20201230
        #             # breakpoint()
        #             self.reset_mount_reference()
        #             self.ra_offset = 0
        #             self.dec_offset = 0
        #             self.offset_received = False
        #             icrs_ra, icrs_dec = self.get_mount_coordinates()
        #             ra = self.ra_prior #icrs_ra
        #             dec = self.dec_prior #icrs_dec
        #             alt_az = False
        #             #We could just return but will seek just to be safe
        #     else:   #  NB confusing logic   this is meant to be the simple seek case.
        #             #  Here we DO read the req dictionary ra and dec or appear to also get alt and az,but that is not implemnented WER 20220212
        try:
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
                    az, alt = ptr_utility.transform_haDec_to_azAlt(ha, dec, lat=self.config['latitude'])
    
                    self.ra_offset = 0  #NB Not adding in self.ra_offset is correct unless a Calibrate occured.
                    self.dec_offset = 0
                    self.offset_received = False
                    ra_dec = False
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

        self.move_time = time.time()
        
        self.object = opt.get("object", "")
        if self.object == "":
           # plog("Go to unamed target.")
            g_dev['obs'].send_to_user("Slewing telescope to un-named target!  ",  p_level="INFO")
        else:
            #plog("Going to:  ", self.object)   #NB Needs cleaning up.
            g_dev['obs'].send_to_user("Slewing telescope to:  " + str( self.object),  p_level="INFO")
        
        if object_is_moon:
            g_dev['obs'].time_of_last_slew=time.time()
            self.go_coord(ra1, dec1, tracking_rate_ra=dra_moon, tracking_rate_dec = ddec_moon)
        elif alt_az == True:
            g_dev['obs'].time_of_last_slew=time.time()
            self.move_to_azalt(az, alt)
            g_dev['obs'].send_to_user("Slew Complete.")
        elif ra_dec == True:
            g_dev['obs'].time_of_last_slew=time.time()
            self.go_coord(ra, dec, tracking_rate_ra=tracking_rate_ra, tracking_rate_dec = tracking_rate_dec)
            g_dev['obs'].send_to_user("Slew Complete.")
            
        

        # On successful movement of telescope reset the solving timer
        g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
        g_dev['obs'].images_since_last_solve = 10000    

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
        self.last_seek_time = time.time() - 5000

        self.unpark_command()  
        #Note this initiates a mount move.  WE should Evaluate if the destination is on the flip side and pick up the
        #flip offset.  So a GEM could track into positive HA territory without a problem but the next reseek should
        #result in a flip.  So first figure out if there will be a flip:

        
        if self.can_report_destination_pierside == True:   
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
        else: 
            if self.pier_side == 0:
                pier_east = 1
            else:
                pier_east = 0
         #Update incoming ra and dec with mounting offsets.

        try:        
            ra += delta_ra #NB it takes a restart to pick up a new correction which is also J.now.
            dec += delta_dec
        except:
            pass
        ra, dec = ra_dec_fix_h(ra,dec)
        if self.EquatorialSystem == 1:    #equTopocentric
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
  
        self.move_time = time.time()
        az, alt = ptr_utility.transform_haDec_to_azAlt_r(self.ha_mech, self.dec_mech, self.latitude_r)
        self.target_az = az*RTOD

        wait_for_slew() 

        try:
            g_dev['obs'].time_of_last_slew=time.time()
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
                
                    plog ("this mount may not accept tracking commands")
                elif ('Property write Tracking is not implemented in this driver.' in str(e)) and self.theskyx_tracking_rescues >= 5:
                    plog ("theskyx has been rescued one too many times. Just sending it to park.")
                    self.park_command()
                    wait_for_slew()
                    return
                else:
                    plog ("problem with setting tracking: ", e)
        
        g_dev['obs'].time_since_last_slew = time.time()
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
        if self.CanSetRightAscensionRate:
            self.prior_roll_rate = -((self.ha_mech_adv - self. ha_mech)*RTOS*MOUNTRATE/self.delta_t_s - MOUNTRATE)/(APPTOSID*15)    #Conversion right 20219329
            self.mount.RightAscensionRate = 0.0 # self.prior_roll_rate  #Neg number makes RA decrease
            self.RightAscensionRate = 0.0
        else:
            self.prior_roll_rate = 0.0
        if self.CanSetDeclinationRate:
           self.prior_pitch_rate = -(self.dec_mech_adv - self.dec_mech)*RTOS/self.delta_t_s    #20210329 OK 1 hour from zenith.  No Appsid correction per ASCOM spec.
           self.mount.DeclinationRate = 0.0 #self.prior_pitch_rate  #Neg sign makes Dec decrease
           self.DeclinationRate = 0.0 #self.prior_pitch_rate
           #plog("Rates, refr are:  ", self.prior_roll_rate, self.prior_pitch_rate, self.refr_asec)
        else:
            self.prior_pitch_rate = 0.0
       
        if self.CanSetRightAscensionRate:
            self.mount.RightAscensionRate = 0.0 #self.prior_roll_rate
            self.RightAscensionRate = 0.0
        if self.CanSetDeclinationRate:
            self.mount.DeclinationRate = 0.0#self.prior_pitch_rate
            self.DeclinationRate = 0.0 #self.prior_pitch_rate

        self.seek_commanded = True        

        # On successful movement of telescope reset the solving timer
        if reset_solve == True:
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000
        wait_for_slew()   

    def slewToSkyFlatAsync(self, skip_open_test=False):      
        # This will only move the scope if the observatory is open
        # UNLESS it has been sent a command from particular routines
        # e.g. pointing the telescope in a safe location BEFORE opening the roof
        if not skip_open_test:
        
            if (not (g_dev['events']['Cool Down, Open'] < ephem.now() < g_dev['events']['Naut Dusk']) and \
                not (g_dev['events']['Naut Dawn'] < ephem.now() < g_dev['events']['Close and Park'])):
                g_dev['obs'].send_to_user("Refusing skyflat pointing request as it is outside skyflat time")
                plog("Refusing pointing request as it is outside of skyflat pointing time.")
                return
            
            if (g_dev['obs'].open_and_enabled_to_observe==False and g_dev['enc'].mode == 'Automatic') and (not g_dev['obs'].debug_flag):
                g_dev['obs'].send_to_user("Refusing skyflat pointing request as the observatory is not enabled to observe.")
                plog("Refusing skyflat pointing request as the observatory is not enabled to observe.")
                return

        az, alt = self.astro_events.flat_spot_now()
        self.unpark_command()        

        if self.mount.Tracking == True:
            if not self.theskyx:   
                self.mount.Tracking = False
            else:
                pass

        self.move_time = time.time()
        try:
            g_dev['obs'].time_of_last_slew=time.time()
            #self.move_to_azalt(az, max(alt, 35))   #Hack for MRC testing
            self.move_to_azalt(az, alt)   #Hack for MRC testing
            g_dev['obs'].time_of_last_slew = time.time()
            # On successful movement of telescope reset the solving timer
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000

        except:
            plog (traceback.format_exc())
            #plog ("NEED TO POINT TELESCOPE TO RA AND DEC, MOUNT DOES NOT HAVE AN ALTAZ request in the driver")



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
            self.move_to_azalt(home_az, home_alt)
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
                self.mount.Park()
                
                wait_for_slew()

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''
        if self.mount.CanPark:
            if self.mount.AtPark:
                plog("mount cmd: unparking mount")
                g_dev['obs'].send_to_user("Unparking Mount. This can take a moment.")
                g_dev['obs'].time_of_last_slew=time.time()
                self.mount.Unpark()
                wait_for_slew()
                if self.home_after_unpark:
                    try: 
                        self.mount.FindHome()
                    except:
                        home_alt = self.settings["home_altitude"]
                        home_az = self.settings["home_azimuth"]
                        self.move_to_azalt(home_az, home_alt)
                    wait_for_slew()

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
#         #plog ('|' + temp[16:18] +'|')
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
    
    def move_to_azalt(self, az, alt):
        plog ("Moving to Alt " + str(alt) + " Az " + str(az))
        if self.config['mount']['mount1']['has_ascom_altaz'] == True:
            wait_for_slew() 
            g_dev['obs'].time_of_last_slew=time.time()
            self.mount.SlewToAltAzAsync(az, alt)
            g_dev['obs'].time_since_last_slew = time.time()
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000
            wait_for_slew()
        else:            
            aa = AltAz (location=self.site_coordinates, obstime=Time.now())
            tempcoord= SkyCoord(az=az*u.deg, alt=alt*u.deg, frame=aa)
            tempcoord=tempcoord.transform_to(frame='icrs')
            tempRA=tempcoord.ra.deg / 15
            tempDEC=tempcoord.dec.deg            
            wait_for_slew() 
            try:
                g_dev['obs'].time_of_last_slew=time.time()
                self.mount.SlewToCoordinatesAsync(tempRA, tempDEC)
            except Exception as e:
                if ('Object reference not set to an instance of an object.' in str(e)):                       
                    #self.home_command()
                    self.unpark_command()
                    g_dev['obs'].time_of_last_slew=time.time()
                    self.mount.SlewToCoordinatesAsync(tempRA, tempDEC)
                    plog (traceback.format_exc())
            
            g_dev['obs'].time_since_last_slew = time.time()
            g_dev['obs'].last_solve_time = datetime.datetime.now() - datetime.timedelta(days=1)
            g_dev['obs'].images_since_last_solve = 10000
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