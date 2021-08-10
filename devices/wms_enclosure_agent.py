import win32com.client
from global_yard import g_dev
import redis
import time

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


class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.site = config['site']
        self.config = config
        self.site_is_proxy = self.config['has_wx_enc_agent'] 
        g_dev['enc'] = self
        #if self.site != 'mrc2':
        win32com.client.pythoncom.CoInitialize()
        self.enclosure = win32com.client.Dispatch(driver)
        print(self.enclosure)
        if not self.enclosure.Connected:
            self.enclosure.Connected = True
        print("ASCOM enclosure connected.")
        redis_ip = config['redis_ip']   #Do we really need to dulicate this config entry?
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
            g_dev['redis_server'] = self.redis_server 
        else:
            self.redis_wx_enabled = False
        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
        self.state = 'Closed'
        self.enclosure_message = '-'
        self.external_close = False   #If made true by operator,  system will not reopen for the night
        self.dome_opened = False   #memory of prior issued commands  Restarting code may close dome one time.
        self.dome_homed = False
        self.cycles = 0
        self.prior_status = None
        self.time_of_next_slew = time.time()
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
        #core1_redis.set('unihedron1', str(mpsas) + ', ' + str(bright) + ', ' + str(illum), ex=600)
        
        try:
            shutter_status = self.enclosure.ShutterStatus
        except:
            print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
            shutter_status = 5
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
        
        if self.is_dome:
            status = {'shutter_status': stat_string,
                      'enclosure_synch': self.enclosure.Slaved,
                      'dome_azimuth': round(self.enclosure.Azimuth, 1),
                      'dome_slewing': self.enclosure.Slewing,
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
            self.redis_server.set('roof_status', str(stat_string), ex=600)
            self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=600)  #Used by autofocus
            self.redis_server.set("shutter_status", str(stat_string), ex=600)
            self.redis_server.set('enclosure_synch', str(self.enclosure.Slaved), ex=600)
            self.redis_server.set('enclosure_mode', str(self.mode), ex=600)
            self.redis_server.set('enclosure_message', str(self.state), ex=600)
            self.prior_status = status
        else:
            status = {'shutter_status': stat_string,
                      'enclosure_synch': True,
                      'dome_azimuth': 180.0,
                      'dome_slewing': False,
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
            self.redis_server.set('roof_status', str(stat_string), ex=600)
            self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=600)  #Used by autofocus
            self.redis_server.set("shutter_status", str(stat_string), ex=600)
            self.redis_server.set('enclosure_synch', True, ex=600)
            self.redis_server.set('enclosure_mode', str(self.mode), ex=600)
            self.redis_server.set('enclosure_message', str(self.state), ex=600)        #print('Enclosure status:  ', status


        
        if self.site_is_proxy:
            redis_command = self.redis_server.get('enc_cmd')  #It is presumed there is an expiration date on open command at least.
            if redis_command == 'open':
                self.redis_server.delete('enc_cmd')
                print("enclosure remote cmd: open.")
                self.manager(open_cmd=True, close_cmd=False)
                self.dome_open = True
                self.dome_home = True
            elif redis_command == 'close':               
                self.redis_server.delete('enc_cmd')
                print("enclosure remote cmd: close.")
                self.manager(close_cmd=True, open_cmd=False)
                self.dome_open = False
                self.dome_home = True
            elif redis_command == 'automatic':
                self.redis_server.delete('enc_cmd')
                print("Change to Automatic.")
                self.site_in_automatic = True
                self.mode = 'Automatic'
            elif redis_command == 'manual':
                self.redis_server.delete('enc_cmd')
                print("Change to Manual.")
                self.site_in_automatic = False
                self.mode = 'Manual'
            elif redis_command == 'shutdown':
                self.redis_server.delete('enc_cmd')
                print("Change to Shutdow & Close")
                self.manager(close_cmd=True, open_cmd=False)
                self.site_in_automatic = False
                self.mode = 'Shutdown'
            else:  
                pass
        self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status


    def parse_command(self, command):   #There should not be commands from AWS
        return
   

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
        obs_win_begin, sunset, sunrise, ephemNow = self.astro_events.getSunEvents()
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
        wx_hold = g_dev['ocn'].wx_hold
        #wx_is_ok = g_dev['ocn'].wx_is_ok

        #  NB NB First deal with the possible observing window being available or not.
        #  THis routine basically opens and keeps dome opposite the sun. Whether system
        #  takes sky flats or not is determined by the scheduler or calendar.  Mounting
        #  could be parked.
       

        debugOffset = 0/24 #hours.
        try:
            obs_time = self.redis_server.get('obs_heart_time')
            
        except:
            pass
            #print("Obs process not producing time heartbeat.")
        
        #Thisis meant to be quite sweeping
        if (wx_hold or self.mode == 'Shutdown'):
            if self.is_dome:
                self.enclosure.Slaved = False
            if self.status_string.lower() in ['open']:
                self.enclosure.CloseShutter()
            self.dome_opened = False
            self.dome_homed = True
        elif obs_time is None or (time.time() - float(obs_time)) > 120.:  #This might want to have a delay to aid debugging
            if self.is_dome:
                self.enclosure.Slaved = False
            if self.status_string.lower() in ['open']:
                self.enclosure.CloseShutter()
            self.dome_opened = False
            self.dome_homed = True
            
            
        #  We are now in the full operational window.   ###Ops Window Start
        elif (g_dev['events']['Ops Window Start'] - debugOffset <= ephemNow <= g_dev['events']['Ops Window Closes'] + debugOffset) \
                and not (wx_hold or self.mode == 'Shutdown') \
                and (self.site_in_automatic or open_cmd and not self.site_in_automatic):   #Note Manual Open works in the window.
            #  Basically if in above window and Automatic and Not Wx_hold: if closed, open up.
            #  print('\nSlew to opposite the azimuth of the Sun, open and cool-down. Az =  ', az_opposite_sun)
            #  NB There is no corresponding warm up phase in the Morning.
            #  Wx hold will delay the open until it expires.

            if self.status_string.lower() in ['closed']:  #, 'closing']:
                self.guarded_open()
                self.dome_opened = True
                self.dome_homed = True
                self.time_of_next_slew = time.time()
                if open_cmd:
                    self.state = 'User Opened the ' + shutter_str
                else:
                    self.state = 'Automatic nightime Open ' + shutter_str + '   Wx is OK; in Observing window.'
            #During skyflat time, slew dome opposite sun's azimuth'
            if self.status_string.lower() in ['open'] and \
                (g_dev['events']['Eve Sky Flats'] - debugOffset <= ephemNow <= g_dev['events']['End Eve Sky Flats'] + debugOffset) or \
                (g_dev['events']['End Astro Dark'] - debugOffset <= ephemNow <= g_dev['events']['Ops Window Closes'] + debugOffset):    #WE found it open.
                #  NB NB The aperture spec is wrong, there are two; one for eve, one for morning.
                if self.is_dome and time.time() >= self.time_of_next_slew:
                    try:
                        self.enclosure.SlewToAzimuth(az_opposite_sun)
                        print("Now slewing Dome to an azimuth opposite the Sun:  ", round(az_opposite_sun, 3))

                        self.dome_homed = False
                        self.time_of_next_slew = time.time() + 30  # seconds between slews.
                    except:
                        pass#
                    
            
            
             

            #  This routine basically opens the dome only.  Whether the system
            #  takes images or not is determined by the scheduler or calendar.  Azimuth meant
            #  to be determined by that of the telescope.

            # if (obs_win_begin - debugOffset < ephemNow < sunrise + debugOffset or open_cmd) \
            #         and g_dev['enc'].site_in_automatic \
            #         and g_dev['ocn'].wx_is_ok \
            #         and self.enclosure.ShutterStatus == 1: #  Closed
            #     if open_cmd:
            #         self.state = 'User Opened the ' + shutter_str
            #     else:
            #         self.state = 'Automatic nightime Open ' + shutter_str + '   Wx is OK; in Observing window.'
            #     self.cycles += 1           #if >=3 inhibits reopening for Wx  -- may need shelving so this persists.
            #     #  A countdown to re-open
            #     if self.status_string.lower() in ['closed', 'closing']:
            #         self.guarded_open()   #<<<<NB NB NB Only enable when code is fully proven to work.
            #         if self.is_dome:
            #             self.enclosure.Slaved = True
            #         else:
            #             pass
                    
            #         print("Night time Open issued to the "  + shutter_str, +   ' and is now following Mounting.')
        elif (obs_win_begin - debugOffset >= ephemNow or ephemNow >= sunrise + debugOffset):
            #WE are now outside the observing window, so Sun is up!!!
            if self.site_in_automatic or (close_cmd and not self.site_in_automatic):  #If Automatic just close straight away.
                if close_cmd:
                    self.state = 'User Closed the '  + shutter_str
                else:
                    self.state = 'Automatic Daytime normally Closed the ' + shutter_str
                if self.is_dome:
                    enc_at_home = self.enclosure.AtHome
                else:
                    enc_at_home = True
                if self.status_string.lower() in ['open', 'opening'] \
                    or not enc_at_home:
                    try:
                        if self.is_dome:
                            self.enclosure.Slaved = False
                        self.enclosure.CloseShutter()
                        self.dome_opened = False
                        self.dome_homed = True
                       # print("Daytime Close issued to the " + shutter_str  + "   No longer following Mount.")
                    except:
                        print("Shutter busy right now!")
            elif (open_cmd and not self.site_in_automatic):  #This is a manual Open

                #first verify scope is parked, otherwise command park and 
                #report failing.
                if True:  #g_dev['mnt'].mount.AtPark:                
                    if self.status_string.lower() in ['closed', 'closing']:
                        self.guarded_open()
                        self.dome_opened = True
                        self.dome_homed = True
                else:
                    #g_dev['mnt'].park_command()
                    #??Add darkslide close here or een tothe park command itself??
                    #print("Telescope commanded to park, try again in a minute.")
                    pass
                    
                
            
            
            else:
                #  We are outside of the observing window so close the dome, with a one time command to
                #  deal with the case of software restarts. Do not pound on the dome because it makes
                #  off-hours entry difficult.
                #  NB this happens regardless of automatic mode.
                #  The dome may come up reporting closed when it is open, but it does report unhomed as
                #  the condition not AtHome.
    
        
                if not self.dome_homed:
                    # breakpoint()
                    # self.dome_homed = True
                    # return
                    if self.is_dome:
                        self.enclosure.Slaved = False
                        try:
                            
                            if self.status_string.lower() in ['open'] \
                                or not self.enclosure.AtHome:
                                pass
                                #self.enclosure.CloseShutter()   #ASCOM DOME will fault if it is Opening or closing
                        except:
                            pass
                            #print('Dome close cmd appeared to fault.')
                    self.dome_opened = False
                    self.dome_homed = True
                    #print("One time close of enclosure issued, normally done during Python code restart.")


if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

