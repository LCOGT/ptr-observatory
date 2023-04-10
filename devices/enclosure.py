import win32com.client
from global_yard import g_dev
#import redis
import time
import math as math
#import shelve
import json
import socket
import os
#import ptr_config

import urllib

#from site_config import get_enc_status

#from pprint import pprint
from ptr_utility import plog

'''
Curently this module interfaces to a Dome (az control) or a pop-top roof style enclosure.

This module contains a Manager, which is called during a normal status scan which emits
Commands to Open and close based on Events and the weather condition. Call the manager
if you want to do something with the dome since it coordinates with the Events dictionary.

The Events time periods apply a collar, if you will, around when automatic dome opening
is possible.  The event phases are found in g_dev['events'].  The basic window is defined
with respect to Sunset and Sunrise so it varies each day.

NB,  Dome refers to a rotating roof that presumably needs azimuth alignmnet of some form
Shutter, Roof, Slit, etc., are the same things.
'''

# =============================================================================
# This module has been modified into wema only code, then unmodified to be normal enclousre code.
# =============================================================================

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
APPTOSID = 1.00273811906  # USNO Supplement
MOUNTRATE = 15*APPTOSID  # 15.0410717859
KINGRATE = 15.029


def test_connect(host='http://google.com'):
    try:
        urllib.request.urlopen(host)  # Python 3.x
        return True
    except:
        return False


def f_to_c(f):
    return round(5*(f - 32)/9, 2)


def convert_to_mechanical_h_d(pRa, pDec, pFlip):
    if pFlip == 'East':
        return (pRa, pDec)
    else:
        fDec = 180. - pDec
        pRa += 12.
        while pRa >= 24:
            pRa -= 24.
        while pRa < 0.:
            pRa += 24.
        return (pRa, fDec)


def rect_sph_d(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))


def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)


def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta


def centration_d(theta, a, b):
    theta = math.radians(theta)
    return math.degrees(math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))


def centration_r(theta, a, b):
    # = math.radians(theta)
    return (math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

# def transform_raDec_to_haDec_r(pRa, pDec, pSidTime):

#     return (reduce_ha_r(pSidTime - pRa), reduce_dec_r(pDec))

# def transform_haDec_to_raDec_r(pHa, pDec, pSidTime):
#     return (reduce_ra_r(pSidTime - pHa), reduce_dec_r(pDec))

# def transform_haDec_to_azAlt_r(pLocal_hour_angle, pDec, latr):
#     sinLat = math.sin(latr)
#     cosLat = math.cos(latr)
#     decr = pDec
#     sinDec = math.sin(decr)
#     cosDec = math.cos(decr)
#     mHar = pLocal_hour_angle
#     sinHa = math.sin(mHar)
#     cosHa = math.cos(mHar)
#     altitude = math.asin(sinLat*sinDec + cosLat*cosDec*cosHa)
#     y = sinHa
#     x = cosHa*sinLat - math.tan(decr)*cosLat
#     azimuth = math.atan2(y, x) + PI
#     azimuth = reduce_az_r(azimuth)
#     altitude = reduce_alt_r(altitude)
#     return (azimuth, altitude)#, local_hour_angle)

# def transform_azAlt_to_haDec_r(pAz, pAlt, latr):
#     sinLat = math.sin(latr)
#     cosLat = math.cos(latr)
#     alt = pAlt
#     sinAlt = math.sin(alt)
#     cosAlt = math.cos(alt)
#     az = pAz - PI
#     sinAz = math.sin(az)
#     cosAz = math.cos(az)
#     if abs(abs(alt) - PIOVER2) < 1.0*STOR:
#         return (0.0, reduce_dec_r(latr))     #by convention azimuth points South at local zenith
#     else:
#         dec = math.asin(sinAlt*sinLat - cosAlt*cosAz*cosLat)
#         ha = math.atan2(sinAz, (cosAz*sinLat + math.tan(alt)*cosLat))
#         return (reduce_ha_r(ha), reduce_dec_r(dec))

# def transform_azAlt_to_raDec_r(pAz, pAlt, pLatitude, pSidTime):
#     ha, dec = transform_azAlt_to_haDec_r(pAz, pAlt, pLatitude)
#     return transform_haDec_to_raDec_r(ha, dec, pSidTime)

# =============================================================================
#
# def dome_adjust_rah_decd(hah, azd, altd, flip, r, offe, offs ):  #Flip = 'east' implies tel looking East.
#                                             #AP Park five is 'West'. offsets are neg for east and
#                                             #south at Park five.
#     #First lay down in Y X plane a crow's eye view and a mount pointing up into Z axis
#     # with the appriate telescope OTA fffsets.  Use "Looking East"
#
#     #For a latitude that is positive, and incoming ha = 0, dec = 0
#     #we need to rotate those coordinates so the X footprints are correct,
#     x = None
#     y = None
#     z = None
#     flip = "Looking East"
#     offe = -19.5
#     offs = -8
#     rad = 60
#     hah = 5
#     dec = 35.5
#     lat = 35.5
#     plog(x, y, z, "Dec = lat")
#     if flip == 'Looking West':
#         x = offs*math.cos(math.radians(dec - lat))
#         y = offe
#         z = rad*math.cos(math.radians(dec - lat))
#         # if azd >270 or azd <= 90:
#         #     x = offs + r*math.cos(math.radians(altd))
#         # else:
#         #     x = offs - r*math.cos(math.radians(altd)
#     elif flip == 'Looking East':
#         x = -offs*math.cos(math.radians(dec -lat))
#         y = -offe
#         z = rad*math.cos(math.radians(dec - lat))
#         #y = -offe + r*math.sin(hah*15)
#     plog(x, y, z)
#     #Now the next step is rotate in the Y -Z plane to deal
#     #with the HA on the mount.  Note as the mount follows
#     #the stars, X, (60" up even) does not vary
#     y, z = rotate_r(y, z, -hah*HTOR)
#     plog(x, y, z, -math.degrees(math.atan2(y,x)))
#
#
#     basically cos(latitude)
#     naz = -math.degrees(math.atan2(y,x))
#     if naz < 0:
#         naz += 360
#     if naz >= 360:
#         naz -= 360
#
#     return round(naz, 2)
# =============================================================================


class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.obsid = config['obs_id']
        self.config = config
        g_dev['enc'] = self
        self.slew_latch = False
        self.dome_open = None  # Just initialising this variable
        if self.config['obsid_in_automatic_default'] == "Automatic":

            self.site_in_automatic = True
            self.mode = 'Automatic'
        elif self.config['obsid_in_automatic_default'] == "Manual":
            self.site_in_automatic = False

            self.mode = 'Manual'
        else:
            self.obsid_in_automatic = False
            self.mode = 'Shutdown'
        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
        self.directly_connected = self.config['enclosure']['enclosure1']['directly_connected']
        self.time_of_next_slew = time.time()
        self.hostname = socket.gethostname()
        if self.hostname in self.config['wema_hostname']:
            self.is_wema = True
        else:
            self.is_wema = False
        if self.config['wema_is_active']:

            self.site_has_proxy = True  # NB Site is proxy needs a new name.
        else:
            self.site_has_proxy = False
        if self.config['dome_on_wema']:
            self.dome_on_wema = True
        else:
            self.dome_on_wema = False
        if self.obsid in ['simulate',  'dht']:  # DEH: added just for testing purposes with ASCOM simulators.
            self.observing_conditions_connected = True
            self.site_is_proxy = False
            plog("observing_conditions: Simulator drivers connected True")
        elif self.config['obsid_is_specific']:

            self.site_is_specific = True
            self.site_is_generic = False

            #  Note OCN has no associated commands.
            #  Note monkey patch
            from site_config import get_enc_status
            self.get_status = get_enc_status
            # self.get_status = config.get_enc_status   # NB NB Bogus line of code
            # Get current ocn status just as a test.
            self.status = self.get_status(g_dev)

        elif self.is_wema or not self.dome_on_wema:  # or self.obsid_is_generic
            #  This is meant to be a generic Observing_condition code
            #  instance that can be accessed by a simple site or by the WEMA,
            #  assuming the transducers are connected to the WEMA.
            self.obsid_is_generic = True
            win32com.client.pythoncom.CoInitialize()

            self.enclosure = win32com.client.Dispatch(driver)

            plog(self.enclosure)
            try:
                if not self.enclosure.Connected:
                    self.enclosure.Connected = True
                plog("ASCOM enclosure connected.")
            except:
                plog("ASCOM enclosure NOT connected, proabably the App is not connected to telescope.")
        else:
            self.obsid_is_generic = False  # NB NB Changed to False for MRC from SRA where True
        self.last_current_az = 315.
        self.last_slewing = False
        self.prior_status = {'enclosure_mode': 'Manual'}  # Just to initialze this rarely used variable.
        self.status = None  # Initialise this to cut down on faults.

        self.guarded_roof_open_timer = time.time()

        if self.config['obsid_allowed_to_open_roof'] == True or self.config['obsid_allowed_to_open_roof'] in ['yes']:
            self.obsid_allowed_to_open_roof = True
        else:
            self.obsid_allowed_to_open_roof = False

        if self.config['obs_id'] == 'aro':
            plog('\n&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&& \n')
            plog('      20221014  Close commands are blocked,  System defaults to manual. \n ')
            plog('&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&& \n')

    def get_status(self) -> dict:

        if self.directly_connected and not self.is_dome:
            #plog("we got a direct connect status!")
            try:
                shutter_status = self.enclosure.ShutterStatus
            except:
                plog("self.enclosure.Roof.ShutterStatus -- Faulted. ")
                shutter_status = 5

            if shutter_status == 0:
                stat_string = "Open"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', True)
            elif shutter_status == 1:
                stat_string = "Closed"
                self.shutter_is_closed = True
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 2:
                stat_string = "Opening"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 3:
                stat_string = "Closing"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 4:
                # breakpoint()
                stat_string = "Error"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            else:
                stat_string = "Software Fault"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            self.status_string = stat_string

            # status = {'shutter_status': stat_string,
            #          'enclosure_synchronized': True, #self.following, 20220103_0135 WER
            #          'dome_azimuth': 0,
            #          'dome_slewing': False,
            #          'enclosure_mode': self.mode,
            #          'enclosure_message': "No message"}, #self.state}#self.following, 20220103_0135 WER

            status = {'shutter_status': stat_string}
            #status['dome_slewing'] = False
            status['enclosure_mode'] = str(self.mode)
            status['dome_azimuth'] = 0.0
            #status['enclosure_mode'] = self.mode
            #status['enclosure_message']: self.state
            #status['enclosure_synchronized']= True

            return status

        elif not self.is_wema and self.site_has_proxy and self.dome_on_wema:
            if self.config['site_IPC_mechanism'] == 'shares':
                try:
                    enclosure = open(g_dev['wema_share_path'] + 'enclosure.txt', 'r')
                    status = json.loads(enclosure.readline())
                    enclosure.close()
                    self.status = status
                    self.prior_status = status
                    g_dev['enc'].status = status
                    return status
                except:
                    try:
                        time.sleep(3)
                        enclosure = open(g_dev['wema_share_path'] + 'enclosure.txt', 'r')
                        status = json.loads(enclosure.readline())
                        enclosure.close()
                        self.status = status
                        self.prior_status = status
                        g_dev['enc'].status = status
                        return status
                    except:
                        try:
                            time.sleep(3)
                            enclosure = open(g_dev['wema_share_path'] + 'enclosure.txt', 'r')
                            status = json.loads(enclosure.readline())
                            enclosure.close()
                            self.status = status
                            self.prior_status = status
                            g_dev['enc'].status = status
                            return status
                        except:
                            plog("Using prior enclosure status after 3 failures.")
                            g_dev['enc'].status = self.prior_status
                            return self.prior_status
            elif self.config['site_IPC_mechanism'] == 'redis':

                try:
                    status = eval(g_dev['redis'].get('enc_status'))
                except:
                    status = g_dev['redis'].get('enc_status')
                self.status = status
                self.prior_status = status
                g_dev['enc'].status = status
            else:
                pass
                # breakpoint()
            self.status = status
            g_dev['enc'].status = status
            return status

        elif self.obsid_is_generic or self.is_wema or not self.dome_on_wema:  # NB Should be AND?
            try:
                shutter_status = self.enclosure.ShutterStatus
            except:
                plog("self.enclosure.Roof.ShutterStatus -- Faulted. ")
                shutter_status = 5
            try:
                self.dome_home = self.enclosure.AtHome
            except:
                self.dome_home = True

            if shutter_status == 0:
                stat_string = "Open"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', True)
            elif shutter_status == 1:
                stat_string = "Closed"
                self.shutter_is_closed = True
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 2:
                stat_string = "Opening"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 3:
                stat_string = "Closing"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            elif shutter_status == 4:
                # breakpoint()
                stat_string = "Error"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            else:
                stat_string = "Software Fault"
                self.shutter_is_closed = False
                #g_dev['redis'].set('Shutter_is_open', False)
            self.status_string = stat_string
            if shutter_status in [2, 3]:
                in_motion = True
            else:
                in_motion = False
            self.last_az = 316.5  # THis should be a config for Dome_home_azimuth
            status = {'shutter_status': stat_string}
            status['dome_slewing'] = in_motion
            status['enclosure_mode'] = str(self.mode)
            status['dome_azimuth'] = round(float(self.last_az), 1)
            status['enclosure_mode'] = self.mode
            #status['enclosure_message']: self.state
            status['enclosure_synchronized'] = True
            # g_dev['redis'].set('enc_status', status, ex=3600)  #This is occasionally used by mouning.

            if self.is_dome:

                try:
                    # Occasionally this property throws an exception:  (W HomeDome)
                    current_az = self.enclosure.Azimuth
                    slewing = self.enclosure.Slewing
                    # if slewing:
                    #     plog("Dome says: Dome is slewing")
                    # else:
                    #     plog("Dome says: Dome not slewing")
                    self.last_current_az = current_az
                    self.last_slewing = slewing
                except:
                    current_az = self.last_current_az
                    slewing = self.last_slewing  # 20220103_0212 WER

                if self.dome_on_wema:  # if local dome this creates a fals slewing report
                    gap = current_az - self.last_current_az
                    while gap >= 360:
                        gap -= 360
                    while gap <= -360:
                        gap += 360
                    if abs(gap) > 2:
                        plog("Azimuth change > 2 deg detected,  Slew:  ", self.enclosure.Slewing)
                        slewing = True
                    else:
                        slewing = False

                self.last_az = current_az
                status = {'shutter_status': stat_string,
                          'enclosure_synchronized': True,  # self.following, 20220103_0135 WER
                          'dome_azimuth': round(self.enclosure.Azimuth, 1),
                          'dome_slewing': slewing,
                          'enclosure_mode': self.mode,
                          'enclosure_message': "No message"},  # self.state}#self.following, 20220103_0135 WER
                try:
                    status = status[0]
                except:
                    pass
                # if moving or self.enclosure.Slewing:
                #     in_motion = True
                # else:
                #     in_motion = False
                # status['dome_slewing'] = in_motion
                # # g_dev['redis'].set('dome_slewing', in_motion, ex=3600)
                # # g_dev['redis'].set('enc_status', status, ex=3600)
            if not self.dome_on_wema:
                self.status = status
                #plog("g_dev:  ", g_dev['enc'].status['dome_slewing'])
                return status
        elif self.is_wema and self.config['site_IPC_mechanism'] == 'shares':
            try:
                enclosure = open(self.config['wema_write_share_path']+'enclosure.txt', 'w')
                enclosure.write(json.dumps(status))
                enclosure.close()
            except:
                time.sleep(3)
                try:
                    enclosure = open(self.config['wema_write_share_path']+'enclosure.txt', 'w')
                    enclosure.write(json.dumps(status))
                    enclosure.close()
                except:
                    time.sleep(3)
                    try:
                        enclosure = open(self.config['wem_-write_share_path']+'enclosure.txt', 'w')
                        enclosure.write(json.dumps(status))
                        enclosure.close()
                    except:
                        time.sleep(3)
                        enclosure = open(self.config['wema_write_share_path']+'enclosure.txt', 'w')
                        enclosure.write(json.dumps(status))
                        enclosure.close()
                        plog("4th try to write enclosure status.")

        elif self.is_wema and self.config['site_IPC_mechanism'] == 'redis':
            g_dev['redis'].set('enc_status', status)  # THis needs to become generalized IPC

# =============================================================================
#         # return status
# =============================================================================

        # Here we check if the observer has sent the WEMA any commands.
        mnt_command = None
        redis_command = None
        if self.is_wema and self.site_has_proxy and self.config['site_IPC_mechanism'] == 'shares':
            _redis = False
            # NB NB THis really needs a context manage so no dangling open files
            try:
                enc_cmd = open(self.config['wema_write_share_path'] + 'enc_cmd.txt', 'r')
                enc_status = json.loads(enc_cmd.readline())
                enc_cmd.close()
                os.remove(self.config['wema_write_share_path'] + 'enc_cmd.txt')
                redis_command = enc_status  # NB NB bad practice to name this a redis command
            except:
                try:
                    time.sleep(1)
                    enc_cmd = open(self.config['wema_write_share_path'] + 'enc_cmd.txt', 'r')
                    enc_status = json.loads(enc_cmd.readline())
                    enc_cmd.close()
                    os.remove(self.config['wema_write_share_path'] + 'enc_cmd.txt')
                    redis_command = enc_status
                except:
                    try:
                        time.sleep(1)
                        enc_cmd = open(self.config['wema_write_share_path'] + 'enc_cmd.txt', 'r')
                        enc_status = json.loads(enc_cmd.readline())
                        enc_cmd.close()
                        os.remove(self.config['wema_write_share_path'] + 'enc_cmd.txt')
                        redis_command = enc_status
                    except:
                        #plog("Finding enc_cmd failed after 3 tries, no harm done.")
                        redis_command = ['none']
            mnt_command = None
            try:
                mnt_cmd = open(self.config['wema_write_share_path'] + 'mnt_cmd.txt', 'r')
                mnt_status = json.loads(mnt_cmd.readline())
                mnt_cmd.close()
                os.remove(self.config['wema_write_share_path'] + 'mnt_cmd.txt')
                mnt_command = mnt_status
            except:
                try:
                    time.sleep(1)
                    mnt_cmd = open(self.config['wema_write_share_path'] + 'mnt_cmd.txt', 'r')
                    mnt_status = json.loads(mnt_cmd.readline())
                    mnt_cmd.close()
                    os.remove(self.config['wema_write_share_path'] + 'mnt_cmd.txt')
                    mnt_command = mnt_status
                except:
                    try:
                        time.sleep(1)
                        mnt_cmd = open(self.config['wema_write_share_path'] + 'mnt_cmd.txt', 'r')
                        mnt_status = json.loads(mnt_cmd.readline())
                        mnt_cmd.close()
                        os.remove(self.config['wema_write_share_path'] + 'mnt_cmd.txt')
                        mnt_command = mnt_status
                    except:
                        #plog("Finding enc_cmd failed after 3 tries, no harm done.")
                        mnt_command = ['none']

        elif self.dome_on_wema and self.is_wema and self.site_has_proxy and \
                self.config['site_IPC_mechanism'] == 'redis':
            # It is presumed there is an expiration date on open command at least.
            redis_command = g_dev['redis'].get('enc_cmd')
            # NB NB NB Need to prevent executing stale commands.  Note Redis_command is overloaded.
            _redis = True

        if redis_command is not None:

            plog(redis_command)
            pass
            # plog(redis_command)
        # Note this is very bogus, some remant from long ago.
        # try:
        #     redis_command = redis_command[0]  # it can come in as ['setManual']
        # except:
        #     pass
        if redis_command == 'open':
            if _redis:
                g_dev['redis'].delete('enc_cmd')
            plog("enclosure remote cmd: open.")
            self.manager(open_cmd=True, close_cmd=False)
            try:
                self.following = True
            except:
                pass
            self.dome_open = True
            self.dome_home = True
        elif redis_command == 'close':  # NB NB this is confusing.  Command not always from redis.
            if _redis:
                g_dev['redis'].delete('enc_cmd')
            plog("enclosure remote cmd: close.")
            self.manager(close_cmd=True, open_cmd=False)

            try:
                self.following = False
            except:
                pass
            self.dome_open = False
            self.dome_home = True
        elif redis_command in ['set_auto', 'setAuto', 'setauto']:
            if _redis:
                g_dev['redis'].delete('enc_cmd')
            plog("Change to Automatic.")
            self.obsid_in_automatic = True
            self.mode = 'Automatic'
        elif redis_command in ['set_manual', 'setManual']:
            if _redis:
                g_dev['redis'].delete('enc_cmd')
            plog("Change to Manual.")
            self.obsid_in_automatic = False
            self.mode = 'Manual'
        elif redis_command in ['set_shutdown', 'setShutdown']:
            if _redis:
                g_dev['redis'].delete('enc_cmd')
            plog("Change to Shutdown & Close")
            self.manager(close_cmd=True, open_cmd=False)
            self.obsid_in_automatic = False
            self.mode = 'Shutdown'
        elif self.is_dome and redis_command == 'go_home':
            if _redis:
                g_dev['redis'].delete('go_home')
        elif self.is_dome and redis_command == 'sync_enc':
            self.following = True
            plog("Scope Dome following set On")
            if _redis:
                g_dev['redis'].delete('sync_enc')
        elif self.is_dome and redis_command == 'unsync_enc':
            self.following = False
            plog("Scope Dome following turned OFF")
            # NB NB NB no command to dome here
            if _redis:
                g_dev['redis'].delete('unsync_enc')
        else:

            pass
        self.status = status
        self.prior_status = status
        g_dev['enc'].status = status
        #status['enclosure_mode']: self.mode
        #status['enclosure_message']: self.state
        #self.status['enclosure_synchronized']= True
        if mnt_command is not None and mnt_command != '' and mnt_command != ['none']:

            try:
                # breakpoint()
                #plog( mnt_command)
                # adj1 = dome_adjust(mount_command['altitude'], mount_command['azimuth'], \
                #                   mount_command['hour_angle'])
                # adjt = dome_adjust(mount_command['altitude'], mount_command['target_az'], \
                #                   mount_command['hour_angle'])
                track_az = mnt_command['azimuth']
                target_az = mnt_command['target_az']
            except:
                track_az = 0
                target_az = 0
                pass
            if self.is_dome and self.status is not None:  # First time around, stauts is None.
                if mnt_command['is_slewing'] and not self.slew_latch:   # NB NB NB THIS should have a timeout
                    self.enclosure.SlewToAzimuth(float(target_az))
                    self.slew_latch = True  # Isuing multiple Slews causes jerky Dome motion.
                elif self.slew_latch and not mnt_command['is_slewing']:
                    self.slew_latch = False  # Return to Dpme following.
                    self.enclosure.SlewToAzimuth(float(track_az))
                elif (not self.slew_latch) and (self.status['enclosure_synchronized'] or
                                                self.mode == "Automatic"):  # self.status['enclosure_synchronized']
                    # This is normal dome following.

                    try:
                        if shutter_status not in [2, 3]:  # THis should end annoying report. [2,3] not very readable!
                            self.enclosure.SlewToAzimuth(float(track_az))
                    except:
                        plog("Dome refused slew, probably updating, closing or opening; usually a harmless situation:  ", shutter_status)
        try:
            self.manager(_redis=_redis)  # There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        except:
            pass
        self.status = status
        self.prior_status = status
        g_dev['enc'].status = status
        return status

    def parse_command(self, command):
        "Note:  This code is typically received by the observer's enclosure module but commands execute at the WEMA's\
                host computer.  The command is killed upon execution."

        if self.config['enclosure']['enclosure1']['enc_is_specific']:
            return  # There is noting to do!
        # This gets commands from AWS, not normally used.
        req = command['required_params']
        opt = command['optional_params']

        action = command['action']
        cmd_list = []
        generic = True
        _redis = False
        shares = False
        if self.dome_on_wema and self.config['wema_is_active'] and self.config['site_IPC_mechanism'] == 'redis':
            _redis = True
            shares = False
            generic = False
        if self.dome_on_wema and self.config['wema_is_active'] and self.config['site_IPC_mechanism'] == 'shares':
            _redis = False
            shares = True
            generic = False
        if action == "open":

            if _redis:
                g_dev['redis'].set('enc_cmd', 'open', ex=300)
            if shares:
                cmd_list.append('open')
            if generic:
                self.open_command(req, opt)
        elif action == "close":
            if _redis:
                g_dev['redis'].set('enc_cmd', 'close', ex=300)
            if shares:
                cmd_list.append('close')
            if generic:
                self.close_command(req, opt)
        elif action == "setAuto":
            if _redis:
                g_dev['redis'].set('enc_cmd', 'setAuto', ex=300)
            if shares:
                cmd_list.append('set_auto')
            if generic:
                self.mode = 'Automatic'
            g_dev['enc'].obsid_in_automatic = True
            g_dev['enc'].automatic_detail = "Night Automatic"
            plog("Site and Enclosure set to Automatic.")
        elif action == "setManual":
            if _redis:
                g_dev['redis'].set('enc_cmd', 'setManual', ex=300)
            if shares:
                cmd_list.append('set_manual')
            if generic:
                self.mode = 'Manual'
            g_dev['enc'].obsid_in_automatic = False
            g_dev['enc'].automatic_detail = "Manual Only"
        elif action in ["setStayClosed", 'setShutdown', 'shutDown']:
            if _redis:
                g_dev['redis'].set('enc_cmd', 'setShutdown', ex=300)
            if shares:
                cmd_list.append('set_shutdown')
            if generic:
                self.mode = 'Shutdown'
            g_dev['enc'].obsid_in_automatic = False
            g_dev['enc'].automatic_detail = "Site Shutdown"
        elif action == "home_dome":
            if shares:
                cmd_list.append('go_home')
        elif action == 'track_telescope':
            if shares:
                cmd_list.append('sync_enc')
        elif action == 'stop_tracking_telescope':
            if shares:
                cmd_list.append('unsync_enc')
        elif action == 'simulate_weather_hold':
            if shares:
                cmd_list.append('toggle_wx_hold')
        #     self.slew_alt_command(req, opt)
        # elif action == "slew_az":
        #     self.slew_az_command(req, opt)
        # elif action == "sync_az":
        #     self.sync_az_command(req, opt)
        # elif action == "sync_mount":
        #     self.sync_mount_command(req, opt)
        # elif action == "park":
        #     self.park_command(req, opt)
        else:
            plog("Command <{action}> not recognized.")

        if len(cmd_list) > 0:
            try:
                enclosure = open(self.config['client_write_share_path']+'enc_cmd.txt', 'w')
                enclosure.write(json.dumps(cmd_list))
                enclosure.close()
            except:
                try:
                    time.sleep(3)
                    enclosure = open(self.config['client_write_share_path']+'enc_cmd.txt', 'w')
                    enclosure.write(json.dumps(cmd_list))
                    enclosure.close()
                except:
                    try:
                        time.sleep(3)
                        enclosure = open(self.config['client_write_share_path']+'enc_cmd.txt', 'w')
                        enclosure.write(json.dumps(cmd_list))
                        enclosure.close()
                    except:
                        time.sleep(3)
                        enclosure = open(self.config['client_write_share_path']+'enc_cmd.txt', 'w')
                        enclosure.write(json.dumps(cmd_list))
                        enclosure.close()
                        plog("4th try to append to enc-cmd  list.")
        return

    ##############################
    #     Enclosure Commands     #
    ##############################

    def open_roof_directly(self, req: dict, opt: dict):
        # if g_dev['enc'].status['shutter_status'] != 'Open' or not self.dome_open:
        self.enclosure.OpenShutter()
        plog("An actual shutter open command has been issued.")

    def close_roof_directly(self, req: dict, opt: dict):
        # if g_dev['enc'].status['shutter_status'] != 'Open' or not self.dome_open:
        self.enclosure.CloseShutter()
        plog("An actual shutter close command has been issued.")

    def open_command(self, req: dict, opt: dict):
        #     ''' open the enclosure '''
        #g_dev['redis'].set('enc_cmd', 'open', ex=1200)
        # self.guarded_open()
        self.manager(open_cmd=True)
        plog("enclosure cmd: open.")

    #     pass

    def close_command(self, req: dict, opt: dict):
        #     ''' close the enclosure '''
        #g_dev['redis'].set('enc_cmd', 'close', ex=1200)
        self.manager(close_cmd=True)
        plog("enclosure cmd: close.")

    #     pass

    # def slew_alt_command(self, req: dict, opt: dict):
    #     plog("enclosure cmd: slew_alt")
    #     pass

    # def slew_az_command(self, req: dict, opt: dict):
    #     plog("enclosure cmd: slew_az")
    #     self.dome_home = False    #As a general rule
    #     pass

    # def sync_az_command(self, req: dict, opt: dict):
    #     plog("enclosure cmd: sync_alt")
    #     pass

    def sync_mount_command(self, req: dict, opt: dict):
        #plog("enclosure cmd: sync_az")
        # if self.site not in ['sro', 'mrc', 'mrc2', 'aro', 'eco']:  #NB NB GASP, this needs a re-think!!
        # if False: # Currently this does nothing?
        self.enclosure.Slaved = True
        self.following = True
        self.enclosure_synchronized = True

    # def park_command(self, req: dict, opt: dict):
    #     ''' park the enclosure if it's a dome '''
    #     plog("enclosure cmd: park")
    #     self.dome_home = True
    #     pass

    def guarded_open(self):
        # The guard is obsessively redundant!

        if self.config['observing_conditions']['observing_conditions1']['driver'] == None or \
            (g_dev['ocn'].status['wx_ok'] in [True, 'Yes'] and not (g_dev['ocn'].wx_hold
                                                                    or g_dev['ocn'].clamp_latch)):     # NB Is Wx ok really the right criterion???
            try:

                if self.site_allowed_to_open_roof == True:
                    if time.time() > self.guarded_roof_open_timer:
                        print(g_dev['enc'].status['shutter_status'] != 'Open')
                        print(self.dome_open)
                        if g_dev['enc'].status['shutter_status'] != 'Open' or not self.dome_open:
                            self.enclosure.OpenShutter()
                            plog("An actual shutter open command has been issued.")
                            if self.enclosure.ShutterStatus == 0:
                                g_dev['obs'].send_to_user("Roof/shutter has opened.", p_level='INFO')
                                #self.redis_server.set('Shutter_is_open', True)
                                self.dome_open = True
                                self.dome_home = True
                                return True
                            else:
                                plog("A command to open the roof was sent.")
                                plog("But the roof failed to open.")
                                plog("We can only try once every 5 minutes.")
                                self.guarded_roof_open_timer = time.time() + 300
                                return False
                    else:
                        plog("An open command was requested, but an attempt was made only recently. Still waiting to try again")

                else:
                    plog("An open command was sent, but this site is not allowed to open the roof (site-config)")
                    return False
            except:
                plog("Attempt to open roof/shutter failed at quarded_open command.")
                g_dev['obs'].send_to_user("Roof/Shutter failed to open.", p_level='INFO')
               # self.redis_server.set('Shutter_is_open', False)
                return False
        return False

    # This is the place where the enclosure is autonomus during operating hours. Delicut Code!!!
    def manager(self, open_cmd=False, close_cmd=False, _redis=False):
        '''
        Now what if code hangs?  To recover from that ideally we need a deadman style timer operating on a
        separate computer.
        First check out code restarts and roof is NOT CLOSED, what happens
        during day, etc.
        '''

        # if not self.is_wema:  #NB NB NB this is clearly not correct.
        #     return   #Nothing to do.

        #  NB NB NB Gather some facts:

        ops_window_start, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()

        az_opposite_sun = g_dev['evnt'].sun_az_now()
        #plog('Sun Az: ', az_opposite_sun)
        az_opposite_sun -= 180.
        if az_opposite_sun < 0:
            az_opposite_sun += 360.
        if az_opposite_sun >= 360:
            az_opposite_sun -= 360.
        if self.is_dome:
            shutter_str = "Dome."
        else:
            shutter_str = "Roof."

        #wx_is_ok = g_dev['ocn'].wx_is_ok

        #  NB NB First deal with the possible observing window being available or not.
        #  THis routine basically opens and keeps dome opposite the sun. Whether system
        #  takes sky flats or not is determined by the scheduler or calendar.  Mounting
        #  could be parked.

        if test_connect():
            net_connected = True
        else:
            net_connected = False

       # The following Redis hold makes little sense

        # try:
        #     redis_hold = eval(self.redis_server.get('wx_hold'))
        # except:
        #     redis_hold =False

        wx_hold = g_dev['ocn'].wx_hold  # or redis_hold  #TWO PATHS to pick up wx-hold.
        if self.mode == "Automatic" and (open_cmd or close_cmd):
            g_dev['obs'].send_to_user("User enclosure requests not honored in Automatic mode.", p_level='INFO')
        if self.mode == 'Shutdown':
            #  NB in this situation we should always Park telescope, rotators, etc.
            #  NB This code is weak
            if self.is_dome and self.enclosure.CanSlave:
                try:
                    self.following = False
                    self.enclosure_synchronized = False
                except:
                    plog('Could not decouple dome following.')
            # if self.status_string in ['Open']:

            # Always attempt to close.... the string may be wrong!
            try:
                self.enclosure.CloseShutter()
                self.dome_open = False
                self.dome_home = True
            except:
                plog('Dome refused close command.')

            self.dome_opened = False
            self.dome_homed = True
            self.enclosure_synchronized = False
            if _redis:
                g_dev['redis'].set('park_the_mount', True, ex=3600)
            if open_cmd:
                g_dev['obs'].send_to_user("Request Open not allowed in Shutdown mode.", p_level='INFO')
            if close_cmd:
                g_dev['obs'].send_to_user("Request Close is ignored in Shutdown mode.", p_level='INFO')
        elif wx_hold:  # There is no reason to deny a wx_hold!
            # We leave telescope to track with dome closed.
            if self.is_dome and self.enclosure.CanSlave:
                try:
                    self.following = False
                    self.enclosure_synchronized = False
                except:
                    self.following = False
                    self.enclosure_synchronized = False
                    plog('Could not decouple dome following.')
            if self.status_string in ['Open']:
                try:
                    self.enclosure.CloseShutter()
                    self.dome_open = False
                    self.dome_home = True
                except:
                    plog('Enclosure refused close command.')
            self.dome_opened = False
            self.dome_homed = True

            # Note we left the telescope alone

        elif open_cmd and self.mode == 'Manual' and net_connected:  # NB NB NB Ideally Telescope parked away from Sun.
            if g_dev['enc'].status['shutter_status'] != 'Open' or not self.dome_open:
                self.guarded_open()
                self.dome_opened = True
                self.dome_homed = True

        elif close_cmd and self.mode == 'Manual':
            try:
                self.enclosure.CloseShutter()
                self.dome_open = False
                self.dome_home = True
                g_dev['obs'].send_to_user("Enclosure commanded to close in Manual mode.", p_level='INFO')
            except:
                plog('Dome refused close command. Try again in 120 sec')
                time.sleep(120)
                try:
                    self.enclosure.CloseShutter()
                    self.dome_open = False
                    self.dome_home = True
                except:
                    plog('Dome refused close command second time.')
                    g_dev['obs'].send_to_user("Enclosure failed to close in Manual mode.", p_level='INFO')
            self.dome_opened = False
            self.dome_homed = True  # g_dev['events']['Cool Down, Open']  <=
        elif ((g_dev['events']['Cool Down, Open'] <= ephem_now < g_dev['events']['Observing Ends']) and
              g_dev['enc'].mode == 'Automatic') and not (g_dev['ocn'].wx_hold or g_dev['ocn'].clamp_latch) and net_connected:
            try:
                # if self.status_string in ['Closed']:   #Fails at SRO, attriute not set. 20220806 wer
                # ****************************NB NB NB For SRO we have no control so just observe and skip all this logic

                # Don't check the string, the string could be wrong!

                if g_dev['enc'].status['shutter_status'] != 'Open' or not self.dome_open:
                    plog("Entering Guarded open, Expect slew opposite Sun")
                    self.guarded_open()
                    self.dome_opened = True
                    self.dome_homed = True
            except Exception as e:
                plog("Error while opening the roof ", e)

            # if _redis: g_dev['redis'].set('Enc Auto Opened', True, ex= 600)   # Unused
            try:
                if self.status_string in ['Open'] and ephem_now < g_dev['events']['End Eve Sky Flats']:
                    if self.is_dome:
                        self.enclosure.SlewToAzimuth(az_opposite_sun)
                        plog("Slewing Opposite Sun")
                        g_dev['obs'].send_to_user("Dome slewing opposite the Solar azimuth", p_level='INFO')
                        time.sleep(5)
            except:
                pass
        # THIS should be the ultimate backup to force a close
        elif ephem_now >= g_dev['events']['Close and Park']:  # sunrise + 45/1440:
            # WE are now outside the observing window, so Sun is up!!!
            # If Automatic just close straight away.
            if self.obsid_in_automatic or (close_cmd and self.mode in ['Manual', 'Shutdown']):
                if self.is_dome and self.enclosure.CanSlave:
                    #enc_at_home = self.enclosure.AtHome
                    self.following = False
                else:
                    self.following = False
                    #enc_at_home = True
                    pass
                if close_cmd:
                    self.state = 'User Closed the ' + shutter_str
                else:
                    self.state = 'Automatic Daytime normally Closed the ' + shutter_str
                try:
                    self.enclosure.CloseShutter()
                    self.dome_opened = False
                    self.dome_homed = True

               # plog("Daytime Close issued to the " + shutter_str  + "   No longer following Mount.")
                except:
                    plog("Shutter Failed to close at End of Morning Sky Flats.")
                #self.mode = 'Manual'
        return


# if __name__ =='__main__':
#     plog('Enclosure class started locally')
#     enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')
# if __name__ =='__main__':
#     plog('Enclosure class started locally')
#     enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')
