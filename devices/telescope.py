# -*- coding: utf-8 -*-
"""
Created on Mon Jul 29 14:56:25 2019

@author: obs
"""

import win32com.client
import pythoncom
import time, json
import datetime
from math import cos, radians
from global_yard import g_dev
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                                EarthLocation, AltAz
#from astroquery.vizier import Vizier
#from astroquery.simbad import Simbad

#The mount is not threaded and uses non-blocking seek.
'''
NGP
12 51 36.7151981
+27 06 11.193172
'''
class Telescope:

    def __init__(self, driver: str, name: str, settings: dict, config: dict, tel=False):
        self.name = name
        g_dev['tel'] = self
        self.device_name = name
        self.settings = settings
        self.rdsys = 'J.now'
        self.inst = name[:3] + name[-1]
        self.tel = tel
        self.telescope_message = "-"
        self.site_coordinates = EarthLocation(lat=float(config['latitude'])*u.deg, \
                        lon=float(config['longitude'])*u.deg,
                        height=float(config['elevation'])*u.m)


        if not tel:    # This looks like ol debugging cruft.
            print(f"Mount is connected.")
        else:
            print(self.inst + "  is connected.")


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

    def get_current_times(self):
        self.ut_now = Time(datetime.datetime.now(), scale='utc', location=self.site_coordinates)   #From astropy.time
        self.sid_now = self.ut_now.sidereal_time('apparent')
        iso_day = datetime.date.today().isocalendar()
        self.doy = ((iso_day[1]-1)*7 + (iso_day[2] ))
        self.equinox_now = 'J' +str(round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2))
        return

    def get_status(self):
        alt = g_dev['mnt'].mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
        if int(airmass) > 5:
            airmass_string = " >> 5 "
            airmass = 5.0
        else:
            airmass = round(airmass, 4)
            airmass_string = str(airmass)
        #Be careful to preserve order
        #print(self.device_name, self.name)
        if self.tel == False:
            status = {
                f'timestamp': str(round(time.time(), 3)),
#                f'right_ascension': str(self.mount.RightAscension),
#                f'declination': str(self.mount.Declination),
#                f'sidreal_time': str(self.mount.SiderealTime),
#                f'tracking_right_ascension_rate': str(self.mount.RightAscensionRate),
#                f'tracking_declination_rate': str(self.mount.DeclinationRate),
#                f'azimuth': str(self.mount.Azimuth),
#                f'altitude': str(alt),
#                f'zenith_distance': str(zen),
#                f'airmass': str(airmass),
#                f'coordinate_system': str(self.rdsys),
                f'pointing_telescope': str(self.inst),  #needs fixing
                f'is_parked': str(g_dev['mnt'].mount.AtPark).lower(),
                f'is_tracking': str(g_dev['mnt'].mount.Tracking).lower(),
                f'is_slewing': str(g_dev['mnt'].mount.Slewing).lower(),
                f'message': g_dev['mnt'].mount_message[:32]
            }
        elif self.tel == True:
            self.current_sidereal = g_dev['mnt'].mount.SiderealTime
            if g_dev['mnt'].mount.EquatorialSystem == 1:
                self.get_current_times()
                jnow_ra = g_dev['mnt'].mount.RightAscension
                jnow_dec = g_dev['mnt'].mount.Declination
                jnow_coord = SkyCoord(jnow_ra*u.hour, jnow_dec*u.degree, frame='fk5', \
                          equinox=self.equinox_now)
                icrs_coord = jnow_coord.transform_to(ICRS)
                self.current_icrs_ra = icrs_coord.ra.hour
                self.current_icrs_dec = icrs_coord.dec.degree
            else:
                self.current_icrs_ra = g_dev['mnt'].mount.RightAscension
                self.current_icrs_dec = sg_dev['mnt'].mount.Declination
            status = {
                f'timestamp': str(round(time.time(), 3)),
                f'right_ascension': str(round(self.current_icrs_ra, 5)),  #
                f'declination': str(round(self.current_icrs_dec, 4)),
                f'sidereal_time': str(round(self.current_sidereal, 5)),
                f'tracking_right_ascension_rate': str(g_dev['mnt'].mount.RightAscensionRate),   #Will use asec/s not s/s as ASCOM does.
                f'tracking_declination_rate': str(g_dev['mnt'].mount.DeclinationRate),
                f'azimuth': str(round(g_dev['mnt'].mount.Azimuth, 3)),
                f'altitude': str(round(alt, 3)),
                f'zenith_distance': str(round(zen, 3)),
                f'airmass': airmass_string,
                f'coordinate_system': str(self.rdsys),
                f'equinox':  self.equinox_now,
                f'pointing_instrument': str(self.inst),  # needs fixing
                f'message': g_dev['mnt'].mount_message[:32]
#                f'is_parked': (self.mount.AtPark),
#                f'is_tracking': str(self.mount.Tracking),
#                f'is_slewing': str(self.mount.Slewing)

            }
        else:
            print('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}
        return status  #json.dumps(status)

    def get_quick_status(self, pre):
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3)
        if airmass > 10: airmass = 10
        airmass = round(airmass, 4)
        pre.append(time.time())
        pre.append(self.mount.RightAscension)
        pre.append(self.mount.Declination)
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



    def get_average_status(self, pre, post):
        t_avg = round((pre[0] + post[0])/2, 3)
        print(t_avg)
        ra_avg = round(Mount.two_pi_avg(pre[1],  post[1], 12), 6)
        dec_avg = round((pre[2] + post[2])/2, 4)
        sid_avg = round(Mount.two_pi_avg(pre[3],  post[3], 12), 5)
        rar_avg = round((pre[4] + post[4])/2, 6)
        decr_avg = round((pre[5] + post[5])/2, 6)
        az_avg = round(Mount.two_pi_avg(pre[6],  post[6], 180), 3)
        alt_avg = round((pre[7] + post[7])/2, 3)
        zen_avg = round((pre[8] + post[8])/2, 3)
        air_avg = round((pre[9] + post[9])/2, 4)
        if pre[10] and post[10]:
            park_avg = "T"
        else:
            park_avg = "F"
        if pre[11] or post[11]:
            track_avg = "T"
        else:
            track_avg = "F"
        if pre[12] or post[12]:
            slew_avg = "T"
        else:
            slew_avg = "F"

        status = {
            f'timestamp': t_avg,
            f'right_ascension': ra_avg,
            f'declination': dec_avg,
            f'sidreal_time': sid_avg,
            f'tracking_right_ascansion_rate': rar_avg,
            f'tracking_declination_rate': decr_avg,
            f'azimuth':  az_avg,
            f'alttitude': alt_avg,
            f'zenith_distance': zen_avg,
            f'airmass': air_avg,
            f'coordinate_system': str(self.rdsys),
            f'instrument': str(self.inst),
            f'is_parked': park_avg,
            f'is_tracking': track_avg,
            f'is_slewing': slew_avg

        }
        return status  #json.dumps(status)

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        print(f"Tel Command <{action}> not recognized.")


