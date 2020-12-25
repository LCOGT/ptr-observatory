
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
start with nominal poblished catalogs whihc generally give names, Ra and dec, Season, mag etc but update them IFF the
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

tzOffset = -7

mountOne = "PW_L600"
mountOneAscom = None
#The mount is not threaded and uses non-blocking seek.     "Note no doule quotes.

def ra_fix(ra):
    while ra >= 24:
        ra -= 24
    while ra < 0:
        ra += 24
        #need to make this a full function
    return ra

class Mount:

    def __init__(self, driver: str, name: str, settings: dict, config: dict, astro_events, tel=False):
        self.name = name
        self.astro_events = astro_events
        g_dev['mnt'] = self
        self.site = config['site']
        self.site_path = config['site_path']
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True
#        print('Can Asynch:  ', self.mount.CanSlewAltAzAsync)

        #hould put config Lat, lon, etc into mount, or at least check it is correct.
        self.site_coordinates = EarthLocation(lat=float(config['latitude'])*u.deg, \
                                lon=float(config['longitude'])*u.deg,
                                height=float(config['elevation'])*u.m)
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel
        self.mount_message = "-"
        if self.site == 'wmd2':
            self.has_paddle = config['mount']['mount2']['has_paddle']
        else:
            self.has_paddle = config['mount']['mount1']['has_paddle']
        self.object = "Unspecified"
        self.current_icrs_ra = "Unspecified_Ra"
        self.current_icrs_dec = " Unspecified_Dec"
        self.offset_received = None
        if not tel:
            print("Mount connected.")
        else:
            print("Tel/OTA connected.")
        print(self.mount.Description)
        try:
            ra1, dec1 = self.get_mount_ref()
        except:
            self.reset_mount_ref()

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

    def get_status(self):
        self.check_connect()
        self.paddle()
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
        if self.tel == False:
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
            breakpoint()
            self.current_sidereal = self.mount.SiderealTime
            ra_off, dec_off = self.get_mount_ref() 
            if self. mount.EquatorialSystem == 1:
                self.get_current_times()
                jnow_ra = ra_fix(self.mount.RightAscension - ra_off)
                jnow_dec = self.mount.Declination - dec_off
                jnow_coord = SkyCoord(jnow_ra*u.hour, jnow_dec*u.degree, frame='fk5', \
                          equinox=self.equinox_now)
                icrs_coord = jnow_coord.transform_to(ICRS)
                self.current_icrs_ra = icrs_coord.ra.hour 
                self.current_icrs_dec = icrs_coord.dec.degree
            else:
                self.current_icrs_ra = ra_fix(self.mount.RightAscension - ra_off)    #May not be applied in positioning
                self.current_icrs_dec = self.mount.Declination - dec_off
            status = {
                'timestamp': round(time.time(), 3),
                'right_ascension': round(self.current_icrs_ra, 5),
                'declination': round(self.current_icrs_dec, 4),
                'sidereal_time': round(self.current_sidereal, 5),
                'tracking_right_ascension_rate': round(self.mount.RightAscensionRate, 9),   #Will use asec/s not s/s as ASCOM does.
                'tracking_declination_rate': round(self.mount.DeclinationRate, 8),
                'azimuth': round(self.mount.Azimuth, 3),
                'altitude': round(alt, 3),
                'zenith_distance': round(zen, 3),
                'airmass': round(airmass,4),
                'coordinate_system': str(self.rdsys),
                'equinox':  self.equinox_now,
                'pointing_instrument': str(self.inst),  # needs fixing
                'message': self.mount_message[:32]
#                f'is_parked': (self.mount.AtPark),
#                f'is_tracking': str(self.mount.Tracking),
#                f'is_slewing': str(self.mount.Slewing)
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
        ra_off, dec_off = self.get_mount_ref() 
        pre.append(time.time())
        pre.append(ra_fix(self.mount.RightAscension - ra_off))
        pre.append(self.mount.Declination - dec_off)
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
            'is_slewing': slew_avg

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
        elif action == "flat_panel":
            self.flat_panel_command(req, opt)
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
            self.go_command(req, opt, offset=True)
        elif action == 'calibrateAtFieldCenter':
            print (command)
            self.go_command(req, opt, calibrate=True)
        elif action == 'sky_flat_position':
            self.slewToSkyFlatAsync()
        else:
            print(f"Command <{action}> not recognized.")


    def get_current_times(self):
        self.ut_now = Time(datetime.datetime.now(), scale='utc', location=self.site_coordinates)   #From astropy.time
        self.sid_now = self.ut_now.sidereal_time('apparent')
        iso_day = datetime.date.today().isocalendar()
        self.doy = ((iso_day[1]-1)*7 + (iso_day[2] ))
        self.equinox_now = 'J' +str(round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2))
        return
    ###############################
    #        Mount Commands       #
    ###############################

    def go_command(self, req, opt,  offset=False, calibrate=False):
        ''' Slew to the given ra/dec coordinates. '''
        print("mount cmd. slewing mount, req, opt:  ", req, opt)

        ''' unpark the telescope mount '''  #  NB can we check if unparked and save time?
        if self.mount.CanPark:
            #print("mount cmd: unparking mount")
            self.mount.Unpark()
        try:
            if offset:   #This offset version supplies offsets as a fraction of the Full field.
                offset_x = float(req['image_x']) - 0.5   #Fraction of field.
                offset_y = float(req['image_y']) - 0.5
                if self.site == 'saf':
                    field_x = 0.38213275235200206*2/15.   #2 accounts for binning, 15 for hours.
                    field_y = 0.2551300253995927*2
                else:
                    field_x = (2679/2563)*0.38213275235200206*2/15.   #2 accounts for binning, 15 for hours.
                    field_y = (2679/2563)*0.2551300253995927*2
                self.ra_offset = -offset_x*field_x
                self.dec_offset = -offset_y*field_y
                ra = ra_fix(self.mount.RightAscension + self.ra_offset)
                dec = self.mount.Declination + self.dec_offset
                #NB NB NB Need to normalize dec
                #NB NB NB Need to add in de-rotation her
                self.mount.SlewToCoordinatesAsync(ra, dec)
                self.offset_received = True
                return
            elif calibrate:  #Note does not need req or opt
                if self.offset_received:
                    ra_off, dec_off = self.get_mount_ref()
                    ra_off += self.ra_offset
                    dec_off += self.dec_offset
                    self.set_mount_ref( ra_off, dec_off)
                    self.ra_offset = 0
                    self.dec_offset = 0
                    self.offset_received = False
                else:
                    print("No outstanding offset available for calibration, resetting.")
                    #We could use this path to clear a calibration.
                    self.reset_mount_ref()
                    self.ra_offset = 0
                    self.dec_offset = 0
                    self.offset_received = False
            else:
                ra = float(req['ra'])
                dec = float(req['dec'])
                self.ra_offset = 0
                self.dec_offset = 0
                self.offset_received = False
        except:
            print("Bad coordinates supplied.")
            self.message = "Bad coordinates supplied, try again."
            self.offset_received = False
            self.ra_offset = 0
            self.dec_offset = 0
            return

        # Offset from sidereal in arcseconds per SI second, default = 0.0
        tracking_rate_ra = opt.get('tracking_rate_ra', 0)

        # Arcseconds per SI second, default = 0.0
        tracking_rate_dec = opt.get('tracking_rate_dec', 0)
        ra_off, dec_off = self.get_mount_ref() 
        if self.mount.EquatorialSystem == 1:
            self.get_current_times()   #  NB We should find a way to refresh this once a day, esp. for status return.
            icrs_coord = SkyCoord(float(req['ra'])*u.hour, float(req['dec'])*u.degree, frame='icrs')
            jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
            ra = jnow_coord.ra.hour + ra_off
            dec = jnow_coord.dec.degree + dec_off
            ra = ra_fix(ra)
        self.mount.Tracking = True
        self.mount.SlewToCoordinatesAsync(ra, dec)
        self.mount.RightAscensionRate = tracking_rate_ra
        self.mount.DeclinationRate = tracking_rate_dec
        self.current_icrs_ra = icrs_coord.ra.hour
        self.current_icrs_dec = icrs_coord.dec.degree
        try:
            self.object = opt.get("object", "")
            print("Going to:  ", self.object)
        except:
            self.object = ""
            print("Go to object not named.")
        

    def go_coord(self, ra, dec):
        ''' Slew to the given ra/dec coordinates, supplied in ICRS '''
        #Thes should be coerced and use above code.
        ''' unpark the telescope mount '''  #  NB can we check if unparked and save time?
        if self.mount.CanPark:
            #print("mount cmd: unparking mount")
            self.mount.Unpark()
        # Offset from sidereal in arcseconds per SI second, default = 0.0
        tracking_rate_ra = 0#opt.get('tracking_rate_ra', 0)
        # Arcseconds per SI second, default = 0.0
        tracking_rate_dec =0#opt.get('tracking_rate_dec', 0)
        ra_off, dec_off = self.get_mount_ref() 
        if self.mount.EquatorialSystem == 1:
            self.get_current_times()   #  NB We should find a way to refresh this once a day, esp. for status return.
            icrs_coord = SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
            jnow_coord = icrs_coord.transform_to(FK5(equinox=self.equinox_now))
            ra = ra_fix(jnow_coord.ra.hour + ra_off)
            dec = jnow_coord.dec.degree + dec_off
            ra = ra_fix(ra)               
            #NB Dec needs proper fixing
        self.mount.Tracking = True
        self.mount.SlewToCoordinatesAsync(ra, dec)
        self.mount.RightAscensionRate = tracking_rate_ra
        self.mount.DeclinationRate = tracking_rate_dec
        self.current_icrs_ra = icrs_coord.ra.hour
        self.current_icrs_dec = icrs_coord.dec.degree

    def slewToSkyFlatAsync(self):
        az, alt = self.astro_events.flat_spot_now()
        self.unpark_command()
        self.mount.Tracking = False
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
            self.mount.FindHome()
        else:
            print("Mount is not capable of finding home. Slewing to zenith.")
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
            self.mount.Park()

    def unpark_command(self, req=None, opt=None):
        ''' unpark the telescope mount '''
        if self.mount.CanPark:
            print("mount cmd: unparking mount")
            self.mount.Unpark()

    def paddle(self):
        '''
        The real way this should work is monitor if a speed button is pushed, then log the time and
        start the thread.  If no button pushed for say 30 seconds, stop thread and re-join.  That way
        image operations are minimally disrupted.

        Normally this will never be started, unless we are operating locally in the observatory.
        '''
        return    #Temporary disable 20200817
    
        self._paddle = serial.Serial('COM28', timeout=0.1)
        self._paddle.write(b"gpio iodir 00ff\n")  #returns  16
        self._paddle.write(b"gpio readall\n")     #  returns 13
        temp_0 = self._paddle.read(21).decode()   #  This is a restate of read, a toss
        temp_1 = self._paddle.read(21).decode()
        print(len(temp_1))
        self._paddle.close()
        #print ('|' + temp[16:18] +'|')
        button = temp_1[14]
        spd= temp_1[13]
        direc = ''
        speed = 0.0
        print("Btn:  ", button, "Spd:  ", speed, "Dir:  ", direc)
        if button == 'E': direc = 'N'
        if button == 'B': direc = 'S'
        if button == 'D': direc = 'E'
        if button == '7': direc = 'W'
        if button == 'C': direc = 'NE'
        if button == '9': direc = 'SE'
        if button == '3': direc = 'SW'
        if button == '6': direc = 'NW'
        if spd ==  'C':
            speed = 0.
            EW = 1
            NS = 1
        if spd == '8':
            speed = 15.
            EW = 1
            NS = 1
        if spd ==  '4':
            speed = 45.
            EW = 1
            NS = 1
        if spd ==  '0':
            speed = 135.
            EW = 1
            NS = 1
        if spd ==  'D':
            speed = 0.
            EW = -1
            NS = 1
        if spd == '9':
            speed = 15.
            EW = -1
            NS = 1
        if spd ==  '5':
            speed = 45.
            EW = -1
            NS = 1
        if spd ==  '1':
            speed = 135.
            EW = -1
            NS = 1
        if spd ==  'E':
            speed = 0.
            EW = 1
            NS = -1
        if spd == 'A':
            speed = 15.
            EW = 1
            NS = -1
        if spd ==  '6':
            speed = 45.
            EW = 1
            NS = -1
        if spd ==  '2':
            speed = 135.
            EW = 1
            NS = -1
        if spd ==  'F':
            speed = 0.
            EW = -1
            NS = -1
        if spd == 'B':
            speed = 15.
            EW = -1
            NS = -1
        if spd == '7':
            speed = 45.
            EW = -1
            NS = -1
        if spd == '3':
            speed = 135.
            EW = -1
            NS = -1

        print(button, spd, direc, speed)
#            if direc != '':
        #print(direc, speed)
        _mount = self.mount
        #Need to add diagonal moves
        if direc == 'N':
            try:
                _mount.DeclinationRate = NS*speed
                self.paddleing = True
            except:
                pass
            print('cmd:  ', direc,  NS*speed)
        if direc == 'S':
            try:
                _mount.DeclinationRate = -NS*speed
                self.paddleing = True
            except:
                pass
            print('cmd:  ',direc,  -NS*speed)
        if direc == 'E':
            try:
                _mount.RightAscensionRate = EW*speed/15.   #Not quite the correct divisor.
                self.paddleing = True
            except:
                pass
            print('cmd:  ',direc, EW*speed/15.)
        if direc == 'W':
            try:
                _mount.RightAscensionRate = -EW*speed/15.
                self.paddleing = True
            except:
                pass
            print('cmd:  ',direc, -EW*speed/15.)
        if direc == '':
            try:
                _mount.DeclinationRate = 0.0
                _mount.RightAscensionRate = 0.0
            except:
                print("Rate set excepetion.")
            self.paddleing = False
        self._paddle.close()
        return

    def set_mount_ref(self, ra, dec):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = ra
        mnt_shelf['dec_cal_offset'] = dec
        mnt_shelf.close()
        return

    def get_mount_ref(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        ra = mnt_shelf['ra_cal_offset']
        dec = mnt_shelf['dec_cal_offset']
        mnt_shelf.close()
        return ra, dec

    def reset_mount_ref(self):
        mnt_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mount1')
        mnt_shelf['ra_cal_offset'] = 0.000
        mnt_shelf['dec_cal_offset'] = -0.00
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

