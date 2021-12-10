import win32com.client
from global_yard import g_dev
#import redis
import time
import json
import math
import os

'''
Curently this module interfaces to a Dome (az control) or a pop-top roof style enclosure.

This module contains a Manager, which is called during a normal status scan which emits
Commands to Open and close based on Events and the weather condition. Call the manager
if you want to do something with the dome since it coordinates with the Events dictionary.

The Events time periods apply a collar, if you will, around when automatic dome opening
is possible.  The event phases are found in g_dev['events'].  The basic window is defined
with respect to Sunset and Sunrise so it varies each day.

NB,  Dome refers to a rotating roof that presumably needs aziumt alignmnet of some form
Shutter, Roof, Slit, etc., are the same things.
'''

#cv 19.5 East, 5.5 South AP 8.5 North, 14.5  redcat 30' e but on axis
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
def dome_adjust (alt, az, ha):

    s = -1
    if az <= 90 or az >=270:
        s = 1
    x = s*(90*math.cos(alt*DTOR) - 5.5*math.sin(alt*DTOR))
    y = -19.5*math.cos(ha*DTOR) + 90*math.sin(ha*DTOR)
    theta = (math.atan2(y,x)*RTOD + 180)

    theta += az
    if theta < 0:
        theta += 360
    if theta >= 360 :
        theta -= 360
    return theta
class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.site = config['site']
        self.config = config
        self.site_is_proxy = self.config['agent_wms_enc_active'] 
        g_dev['enc'] = self
        if driver is not None:
            win32com.client.pythoncom.CoInitialize()
            self.enclosure = win32com.client.Dispatch(driver)
            print(self.enclosure)
            try:
                if not self.enclosure.Connected:
                    self.enclosure.Connected = True
                print("ASCOM enclosure connected.")
            except:
                 print("ASCOM enclosure NOT connected, proabably the App is not connected to telescope.")
        redis_ip = config['redis_ip']   #Do we really need to dulicate this config entry?
        if redis_ip is not None:           
            #self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
            #                                   decode_responses=True)
            self.redis_server = g_dev['redis_server']   #ensure we only have one working.
            self.redis_wx_enabled = True
            #g_dev['redis_server'] = self.redis_server 
        else:
            self.redis_wx_enabled = False
        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
        self.status = None
        self.state = 'Closed'
        self.last_az = 316   #Set to normal home for the respective dome.
        self.last_slewing = False
        self.slew_latch = False
        self.enclosure_message = '-'
        self.external_close = False   #  Not used If made true by operator,  system will not reopen for the night
        self.dome_opened = False   #memory of prior issued commands  Restarting code may close dome one time.
        self.dome_homed = False
        self.cycles = 0
        self.last_current_az = 0
        self.prior_status = None
        self.time_of_next_slew = time.time()
        self.following = False


        if self.config['site_in_automatic_default'] == "Automatic":
            self.site_in_automatic = True
            self.mode = 'Automatic' 
        elif self.config['site_in_automatic_default'] == "Manual":
            self.site_in_automatic = False
            self.mode = 'Manual'
        else:
            self.site_in_automatic = False
            self.mode = 'Shutdown'
        
    def get_status(self) -> dict:
        #<<<<The next attibute reference fails at saf, usually spurious Dome Ring Open report.
        #<<< Have seen other instances of failing.
        
        if self.site == 'fat':
            try:
                enc = open('R:/Roof_Status.txt')
                enc_text = enc.readline()
                enc.close
                enc_list = enc_text.split()
            except:
                try:
                    enc = open('R:/Roof_Status.txt')
                    enc_text = enc.readline()
                    enc.close
                    enc_list = enc_text.split()
                except:
                    print("Two reads of roof status file failed")
                    enc_list = [1, 2, 3, 4, 'Error']
            if len(enc_list) == 5:
                if enc_list[4] in ['OPEN', 'Open', 'open', 'OPEN\n']:
                    shutter_status = 0
                elif enc_list[4] in ['OPENING']:
                    shutter_status = 2
                elif enc_list[4] in ['CLOSED', 'Closed', 'closed', "CLOSED\n"]:
                    shutter_status = 1
                elif enc_list[4] in ['CLOSING']:
                    shutter_status = 3
                elif enc_list[4] in ['Error']:
                    shutter_status = 4
                else:
                    shutter_status = 5
            else:
                shutter_status = 4
        else: 
            try:
                shutter_status = self.enclosure.ShutterStatus
            except:
                print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
                shutter_status = 5
            try:
                self.dome_home = self.enclosure.AtHome
            except:
                pass
        
        if shutter_status == 0:
            stat_string = "Open"
            self.shutter_is_closed = False
            self.redis_server.set('Shutter_is_open', True)
        elif shutter_status == 1:
             stat_string = "Closed"
             self.shutter_is_closed = True
             self.redis_server.set('Shutter_is_open', False)
        elif shutter_status == 2:
             stat_string = "Opening"
             self.shutter_is_closed = False
             self.redis_server.set('Shutter_is_open', False)
        elif shutter_status == 3:
             stat_string = "Closing"
             self.shutter_is_closed = False
             self.redis_server.set('Shutter_is_open', False)
        elif shutter_status == 4:
             stat_string = "Error"
             self.shutter_is_closed = False
             self.redis_server.set('Shutter_is_open', False)
        else:
             stat_string = "Software Fault"
             self.shutter_is_closed = False
             self.redis_server.set('Shutter_is_open', False)
        self.status_string = stat_string
        if shutter_status in [2, 3]:
            moving = True
        else:
            moving = False
        

        if self.is_dome:

            try:
                #Occasionally this property thrws an exception:
                current_az = self.enclosure.Azimuth
                slewing = self.enclosure.Slewing
                self.last_current_az = current_az
                self.last_slewing = slewing
            except:
                current_az = self.last_current_az
                slewing = self.last_slewing
                
            gap = current_az - self.last_az
            while gap >= 360:
                gap -= 360
            while gap <= -360:
                gap += 360
            if abs(gap) > 1.5:
                print("Azimuth change detected,  Slew:  ", self.enclosure.Slewing)
                slewing = True
            else:
                slewing = False
            self.last_az = current_az
            try:
                status = {'shutter_status': stat_string,
                          'enclosure_synchronized': self.following,
                          'dome_azimuth': round(self.enclosure.Azimuth, 1),
                          'dome_slewing': slewing,
                          'enclosure_mode': self.mode,
                          'enclosure_message': self.state}
                # self.redis_server.set('roof_status', str(stat_string), ex=3600)
                # self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=3600)  #Used by autofocus
                # self.redis_server.set("shutter_status", str(stat_string), ex=3600)
                # self.redis_server.set('enclosure_synchronized', str(self.following), ex=3600)
                # self.redis_server.set('enclosure_mode', str(self.mode), ex=3600)
                # self.redis_server.set('enclosure_message', str(self.state), ex=3600)
                # self.redis_server.set('dome_azimuth', str(round(self.enclosure.Azimuth, 1)))
                if moving or self.enclosure.Slewing:
                    in_motion = True
                else:
                    in_motion = False
                status['dome_slewing'] = in_motion
                # self.redis_server.set('dome_slewing', in_motion, ex=3600)
                # self.redis_server.set('enc_status', status, ex=3600)
                self.status = status
                try:
                    enclosure = open(self.config['wema_path']+'enclosure.txt', 'w')
                    enclosure.write(json.dumps(status))
                    enclosure.close()
                except:
                    time.sleep(3)
                    try:
                        enclosure = open(self.config['wema_path']+'enclosure.txt', 'w')
                        enclosure.write(json.dumps(status))
                        enclosure.close()
                    except:
                        time.sleep(3)
                        enclosure = open(self.config['wema_path']+'enclosure.txt', 'w')
                        enclosure.write(json.dumps(status))
                        enclosure.close()
                        print("3rd try to write enclosure status.")
            except:  #Not a dome, presumably a roll top roof or clamshell
 #Should not get here at SAF
                status = {'shutter_status': stat_string,
                          'enclosure_synchronized': False,
                          'dome_azimuth': 0.0, #round(self.enclosure.Azimuth, 1),
                          'dome_slewing': False,
                          'enclosure_mode': self.mode,
                          'enclosure_message': self.state}
                self.redis_server.set('roof_status', str(stat_string), ex=3600)
                self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=3600)  #Used by autofocus
                self.redis_server.set("shutter_status", str(stat_string), ex=3600)
                self.redis_server.set('enclosure_synchronized', False, ex=3600)
                self.redis_server.set('enclosure_mode', str(self.mode), ex=3600)
                self.redis_server.set('enclosure_message', str(self.state), ex=3600)
                self.redis_server.set('dome_azimuth', 0.0) #str(round(self.enclosure.Azimuth, 1)))
                if moving or slewing:   #  elf.enclosure.Slewing:
                    in_motion = True
                else:
                    in_motion = False
                status['dome_slewing'] = in_motion
                self.redis_server.set('dome_slewing', in_motion, ex=3600)
                self.redis_server.set('enc_status', status, ex=3600)

                
                
        else:
            status = {'shutter_status': stat_string,
                      'enclosure_synchronized': True,
                      'dome_azimuth': 180.0,
                      'dome_slewing': False,
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
            self.redis_server.set('roof_status', str(stat_string), ex=3600)
            self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=3600)  #Used by autofocus
            self.redis_server.set("shutter_status", str(stat_string), ex=3600)
            self.redis_server.set('enclosure_synchronized', True, ex=3600)
            self.redis_server.set('enclosure_mode', str(self.mode), ex=3600)
            self.redis_server.set('enclosure_message', str(self.state), ex=3600)        #print('Enclosure status:  ', status
            self.redis_server.set('dome_azimuth', str(180.0))  
            self.redis_server.set('dome_slewing', False, ex=3600)
            self.redis_server.set('enc_status', status, ex=3600)
        # This code picks up commands forwarded by the observer Enclosure 
        if self.site_is_proxy and self.site != 'fat':
            if self.site == 'saf':
                try:
                    enc_cmd = open(self.config['wema_path'] + 'enc_cmd.txt', 'r')
                    status = json.loads(enc_cmd.readline())
                    enc_cmd.close()
                    os.remove(self.config['wema_path'] + 'enc_cmd.txt')
                    redis_command = status
                except:
                    try:
                        time.sleep(1)
                        enc_cmd = open(self.config['wema_path'] + 'enc_cmd.txt', 'r')
                        status = json.loads(enc_cmd.readline())
                        enc_cmd.close()
                        os.remove(self.config['wema_path'] + 'enc_cmd.txt')
                        redis_command = status
                    except:
                        try:
                            time.sleep(1)
                            enc_cmd = open(self.config['wema_path'] + 'enc_cmd.txt', 'r')
                            status = json.loads(enc_cmd.readline())
                            enc_cmd.close()
                            os.remove(self.config['wema_path'] + 'enc_cmd.txt')
                            redis_command = status
                        except:
                            #print("Finding enc_cmd failed after 3 tries, no harm done.")
                            redis_command = ['none']         
                try:
                    mnt_cmd = open(self.config['wema_path'] + 'mnt_cmd.txt', 'r')
                    mount_command  = json.loads(mnt_cmd.readline())

                    mnt_cmd.close()
                    os.remove(self.config['wema_path'] + 'mnt_cmd.txt')

                except:
                    try:
                        time.sleep(1)
                        mnt_cmd = open(self.config['wema_path'] + 'mnt_cmd.txt', 'r')
                        mount_command  = json.loads(mnt_cmd.readline())

                        mnt_cmd.close()
                        os.remove(self.config['wema_path'] + 'mnt_cmd.txt')

                    except:
                        try:
                            time.sleep(1)
                            mnt_cmd = open(self.config['wema_path'] + 'mnt_cmd.txt', 'r')
                            mount_command  = json.loads(mnt_cmd.readline())

                            mnt_cmd.close()
                            os.remove(self.config['wema_path'] + 'mnt_cmd.txt')

                        except:
                            #print("Finding mnt_cmd failed after 3 tries, no harm done.")
                            mount_command = ['none']
                            
                    
            #redis_command = self.redis_server.get('enc_cmd')  #It is presumed there is an expiration date on open command at least.
            #NB NB NB Need to prevent executing stale commands.
            if redis_command != ['none']:
                print(redis_command)
            redis_command = redis_command[0]
            if redis_command == 'open':
                self.redis_server.delete('enc_cmd')
                print("enclosure remote cmd: open.")
                self.manager(open_cmd=True, close_cmd=False)
                try:
                    self.following = True
                except:
                    pass
                self.dome_open = True
                self.dome_home = True
            elif redis_command == 'close':

                self.redis_server.delete('enc_cmd')
                print("enclosure remote cmd: close.")
                self.manager(close_cmd=True, open_cmd=False)

                try:
                    self.following = False
                except:
                    pass
                self.dome_open = False
                self.dome_home = True
            elif redis_command == 'setAuto':
                self.redis_server.delete('enc_cmd')
                print("Change to Automatic.")
                self.site_in_automatic = True
                self.mode = 'Automatic'
            elif redis_command == 'setManual':
                self.redis_server.delete('enc_cmd')
                print("Change to Manual.")
                self.site_in_automatic = False
                self.mode = 'Manual'
            elif redis_command == 'setShutdown':
                self.redis_server.delete('enc_cmd')
                print("Change to Shutdown & Close")
                self.manager(close_cmd=True, open_cmd=False)
                self.site_in_automatic = False
                self.mode = 'Shutdown'
            elif redis_command == 'goHome':
                #breakpoint()
                self.redis_server.delete('goHome')
            elif redis_command == 'sync_enc':
               if self.is_dome:
                   try:
                       self.following = True
                       print("Scope Dome following set On")
                   except:
                       pass
               self.redis_server.delete('sync_enc')                
            elif redis_command == 'unsync_enc':
                if self.is_dome:
                    try:
                        self.following = False
                        print("Scope Dome following turned OFF")
                    except:
                        pass
                self.redis_server.delete('unsync_enc')
            else:
                
                pass
            #NB NB NB  Possible race condition here.
            # redis_value = self.redis_server.get('SlewToAzimuth')
        if self.config['site'] in ['saf'] and mount_command is not None and mount_command != '' and mount_command != ['none']:
            try:
                print(self.status,'\n\n', mount_command)

                adj1 = dome_adjust(mount_command['altitude'], mount_command['azimuth'], \
                                  mount_command['hour_angle'])
                adjt = dome_adjust(mount_command['altitude'], mount_command['target_az'], \
                                  mount_command['hour_angle'])
               
                    
                    
            except:
                adj = 0
                pass
            if self.is_dome and self.status is not None:   #First time around, stauts is None.
                if mount_command['is_slewing'] and not self.slew_latch:   # NB NB NB THIS should have a timeout
                    self.enclosure.SlewToAzimuth(float(adjt))
                    self.slew_latch = True   #Isuing multiple Slews causes jerky Dome motion.
                elif self.slew_latch and not mount_command['is_slewing']:
                    self.slew_latch = False   #  Return to Dpme following.
                    self.enclosure.SlewToAzimuth(float(adj1))
                elif (not self.slew_latch) and (self.status['enclosure_synchronized'] or \
                                                self.mode == "Automatic"):
                    #This is normal dome following.
                    try:
                        if shutter_status not in [2,3]:    #THis should end annoying report.
                            self.enclosure.SlewToAzimuth(float(adj1))
                    except:
                        print("Dome refused slew, probably closing or opening, usually a harmless situation.")
                    
                    
                
                 
            
            
        #self.status = status
        
        if self.site != 'fat':   #There is noting for the local code to manage @ FAT , but Dome at SAF.
            self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status


    def parse_command(self, command):   #There should not be commands from AWS
        return
    
    # from math import *
    # def position_dome(self, dec, hour_angle, elev, az ):
    #     lat = radians(35)
    #     h = radians(hour_angle*15)
    #     d = radians(dec)
    #     x = 20   #CV EAST,   14.5 AP East 
    #     y = -5   #CV South    8.5 AP North.
    #     r = 60
    #     vert = pi/2 - lat + d
    #     zp = r*cos(vert)
    #     xp = x - r*sin(h)
    #     yp = y + r*sin(vert)
    #     print (xp, yp, zp, degrees(atan2(yp, xp)))
        
        
        
   

    ###############################
    #      Enclosure Commands     #
    ###############################

    def open_command(self, req: dict, opt: dict):
        ''' open the enclosure '''
        #self.guarded_open()
        self.manager(open_cmd=True)
        print("enclosure cmd: open.")
        self.dome_open = True
        self.dome_home = True
        pass

    def close_command(self, req: dict, opt: dict):
        ''' close the enclosure '''
        self.manager(close_cmd=True)
        print("enclosure cmd: close.")
        self.dome_open = False
        self.dome_home = True
        pass

    def slew_alt_command(self, req: dict, opt: dict):
        print("enclosure cmd: slew_alt")
        pass

    def slew_az_command(self, req: dict, opt: dict):
        print("enclosure cmd: slew_az")
        self.dome_home = False    #As a general rule
        pass

    def sync_az_command(self, req: dict, opt: dict):
        print("enclosure cmd: sync_alt")
        pass

    def sync_mount_command(self, req: dict, opt: dict):
        print("enclosure cmd: sync_az")
        pass

    def park_command(self, req: dict, opt: dict):
        ''' park the enclosure if it's a dome '''
        print("enclosure cmd: park")
        self.dome_home = True
        pass

    def guarded_open(self):
        #The guard is obsessively redundant!
        if g_dev['ocn'].wx_is_ok and not (g_dev['ocn'].wx_hold \
                                          or g_dev['ocn'].clamp_latch):     # NB Is Wx ok really the right criterion???
            try:
                self.enclosure.OpenShutter()
                print("An actual shutter open command has been issued.")
                self.redis_server.set('Shutter_is_open', True)
                return True
            except:
                print("Attempt to open shutter failed at quarded_open command")
                self.redis_server.set('Shutter_is_open', False)
                return False
        return False


    def manager(self, open_cmd=False, close_cmd=False):     #This is the place where the enclosure is autonomus during operating hours. Delicut Code!!!
        '''
        Now what if code hangs?  To recover from that ideally we need a deadman style timer operating on a
        separate computer.
        First check out code restarts and roof is NOT CLOSED, what happens
        during day, etc.
        '''

        #  NB NB NB Gather some facts:

        ops_window_start, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()

        az_opposite_sun = g_dev['evnt'].sun_az_now()
        #print('Sun Az: ', az_opposite_sun)
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
       

       #The following Redis hold makes little sense

        try:
            redis_hold = eval(self.redis_server.get('wx_hold'))
        except:
            redis_hold =False
        wx_hold = g_dev['ocn'].wx_hold or redis_hold  #TWO PATHS to pick up wx-hold.
        if self.mode == 'Shutdown':
            #  NB in this situation we should always Park telescope, rotators, etc.
            #  NB This code is weak
            if self.is_dome and self.enclosure.CanSlave :
                try:
                    self.following = False
                    self.enclosure_synchronized = False
                except:
                    print('Could not decouple dome following.')
            if self.status_string in ['Open']:
                try:
                    self.enclosure.CloseShutter()
                except:
                    print('Dome refused close command.')
            self.dome_opened = False
            self.dome_homed = True
            self.enclosure_synchronized = False
            self.redis_server.set('park_the_mount', True, ex=3600)
        elif wx_hold:   #There is no reason to deny a wx_hold!
            # We leave telescope to track with dome closed.
            if self.is_dome and self.enclosure.CanSlave :
                try:
                    self.following = False
                    self.enclosure_synchronized = False
                except:
                    self.following = False
                    self.enclosure_synchronized = False
                    print('Could not decouple dome following.')
            if self.status_string in ['Open']:
                try:
                    self.enclosure.CloseShutter()
                except:
                    print('Dome refused close command.')
            self.dome_opened = False
            self.dome_homed = True

            #Note we left the telescope alone

        elif open_cmd and self.mode == 'Manual':   #  NB NB NB Ideally Telescope parked away from Sun.
            self.guarded_open()
            self.dome_opened = True
            self.dome_homed = True

        elif close_cmd and self.mode == 'Manual':
            try:
                self.enclosure.CloseShutter()
            except:
                print('Dome refused close command. Try again in 120 sec')
                time.sleep(120)
                try:
                    self.enclosure.CloseShutter()
                except:
                    print('Dome refused close command second time.')
            self.dome_opened = False
            self.dome_homed = True    #g_dev['events']['Cool Down, Open']  <=
        elif ((g_dev['events']['Cool Down, Open']  <= ephem_now < g_dev['events']['Observing Ends']) and \
               g_dev['enc'].mode == 'Automatic') and not (g_dev['ocn'].wx_hold or g_dev['ocn'].clamp_latch):
            if self.status_string in ['Closed']:
                self.guarded_open()
            self.dome_opened = True
            self.dome_homed = True
            self.redis_server.set('Enc Auto Opened', True, ex= 600)
            if self.status_string in ['Open'] and ephem_now < g_dev['events']['End Eve Sky Flats']:
                self.enclosure.SlewToAzimuth(az_opposite_sun)
                time.sleep(15)
        #THIS should be the ultimate backup to force a close
        elif ephem_now >=  g_dev['events']['Civil Dawn']:  #sunrise + 45/1440:
            #WE are now outside the observing window, so Sun is up!!!
            if self.site_in_automatic or (close_cmd and self.mode in ['Manual', 'Shutdown']):  #If Automatic just close straight away.
                if self.is_dome and self.enclosure.CanSlave:
                    #enc_at_home = self.enclosure.AtHome
                    self.following = False
                else:
                    self.following = False
                    #enc_at_home = True
                    pass
                if close_cmd:
                    self.state = 'User Closed the '  + shutter_str
                else:
                    self.state = 'Automatic Daytime normally Closed the ' + shutter_str
                try:
                    if self.status_string in ['Open']:
                        self.enclosure.CloseShutter()
                    self.dome_opened = False
                    self.dome_homed = True
                   # print("Daytime Close issued to the " + shutter_str  + "   No longer following Mount.")
                except:
                    print("Shutter Failed to close at Civil Dawn.")
                self.mode = 'Manual'




if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

