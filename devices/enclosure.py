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
        g_dev['enc'] = self
        if self.site != 'mrc2':
            win32com.client.pythoncom.CoInitialize()
            self.enclosure = win32com.client.Dispatch(driver)
            print(self.enclosure)
            self.enclosure.Connected = True
            print("ASCOM enclosure connected.")
            print(self.enclosure.Description)
        else:
            print("'MRC2' enclosure linked to 'mrc'. ")
        if self.site in ['mrc', 'mrc2']:
            self.redis_server = redis.StrictRedis(host='10.15.0.109', port=6379, db=0, decode_responses=True)
        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
        self.state = 'Closed. (Initially on code startup.)'
        self.mode = 'Automatic'   #  Auto|User Control|User Close|Disable
        self.enclosure_message = '-'
        self.external_close = False   #If made true by operator,  system will not reopen for the night
        self.dome_opened = False   #memory of prior issued commands  Restarting code may close dome one time.
        self.dome_homed = False
        self.cycles = 0
        self.prior_status = None
        self.time_of_next_slew = time.time()
        self.site_in_automatic = True
        

    def get_status(self) -> dict:
        #<<<<The next attibute reference fails at saf, usually spurious Dome Ring Open report.
        #<<< Have seen other instances of failing.
        #core1_redis.set('unihedron1', str(mpsas) + ', ' + str(bright) + ', ' + str(illum), ex=600)
        if self.site in ['saf', 'mrc']:
            try:
                shutter_status = self.enclosure.ShutterStatus
            except:
                print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
                shutter_status = 5
            if shutter_status == 0:
                stat_string = "Open"
                self.shutter_is_closed = False
            elif shutter_status == 1:
                 stat_string = "Closed"
                 self.shutter_is_closed = True
            elif shutter_status == 2:
                 stat_string = "Opening"
                 self.shutter_is_closed = False
            elif shutter_status == 3:
                 stat_string = "Closing"
                 self.shutter_is_closed = False
            elif shutter_status == 4:
                 stat_string = "Error"
                 self.shutter_is_closed = False
            else:
                 stat_string = "Fault"
                 self.shutter_is_closed = False

        if self.site == 'saf':
           try:
               status = {'shutter_status': stat_string,
                      'enclosure_synch': self.enclosure.Slaved,
                      'dome_azimuth': round(self.enclosure.Azimuth, 1),
                      'dome_slewing': self.enclosure.Slewing,
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
               self.prior_status = status
           except:
               status = self.prior_status
               print("Prior status used for saf dome azimuth")
               # status = {'shutter_status': stat_string,
               #        'enclosure_synch': 'unknown',
               #        'dome_azimuth': str(round(self.enclosure.Azimuth, 1)),
               #        'dome_slewing': str(self.enclosure.Slewing),
               #        'enclosure_mode': str(self.mode),
               #        'enclosure_message': str(self.state)}
        elif self.site == 'mrc':
            status = {'roof_status': stat_string,
                      'shutter_status': stat_string,
                      'enclosure_synch': self.enclosure.Slaved,   #  What should  this mean for a roof? T/F = Open/Closed?
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
            self.redis_server.set('roof_status', str(stat_string), ex=600)
            self.redis_server.set("shutter_status", str(stat_string), ex=600)
            self.redis_server.set('enclosure_synch', str(self.enclosure.Slaved), ex=600)
            self.redis_server.set('enclosure_mode', str(self.mode), ex=600)
            self.redis_server.set('enclosure_message', str(self.state), ex=600)        #print('Enclosure status:  ', status
        elif self.site == 'mrc2':
            # status = {'roof_status': stat_string,
            #           'shutter_status': stat_string,
            #           'enclosure_synch': self.enclosure.Slaved,   #  What should  this mean for a roof? T/F = Open/Closed?
            #           'enclosure_mode': self.mode,
            #           'enclosure_message': self.state}
            stat_string = self.redis_server.get('roof_status')#, str(stat_string), ex=600)
            stat_string = self.redis_server.get("shutter_status")#, str(stat_string), ex=600)
            encl_synched = self.redis_server.get('enclosure_synch')#, str(self.enclosure.Slaved), ex=600)
            self.mode = self.redis_server.get('enclosure_mode')#, str(self.mode), ex=600)
            self.state = self.redis_server.get('enclosure_message')#, str(self.state), ex=600)
            status = {'roof_status': stat_string,
                      'shutter_status': stat_string,
                      'enclosure_synch': encl_synched,  #self.enclosure.Slaved,   #  What should  this mean for a roof? T/F = Open/Closed?
                      'enclosure_mode': self.mode,
                      'enclosure_message': self.state}
        else:
            status = {'roof_status': 'unknown',
                      'shutter_status': 'unknown',
                      'enclosure_synch': 'unknown',   #  What should  this mean for a roof? T/F = Open/Closed?
                      'enclosure_mode': 'unknown',
                      'enclosure_message': 'unknown'
                      }
            stat_string = 'unknown'
        #print('Enclosure status:  ', status
        self.status_string = stat_string
        self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status


    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        if action == "open":
            self.open_command(req, opt)
        elif action == "close":
            self.close_command(req, opt)
        elif action == "setAuto":
            self.mode = 'Automatic'
            g_dev['mnt'].site_in_automatic = True
            g_dev['mnt'].automatic_detail =  "Night Automatic"
            print("Site and Enclosure set to Automatic.")
        elif action == "setManual":
            self.mode = 'Manual'
            g_dev['mnt'].site_in_automatic = False
            g_dev['mnt'].automatic_detail =  "Manual Only"
            print("Site and Enclosure set to Manual.")
        elif action == "slew_alt":
            self.slew_alt_command(req, opt)
        elif action == "slew_az":
            self.slew_az_command(req, opt)
        elif action == "sync_az":
            self.sync_az_command(req, opt)
        elif action == "sync_mount":
            self.sync_mount_command(req, opt)
        elif action == "park":
            self.park_command(req, opt)
        else:
            print("Command <{action}> not recognized.")


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
                return True
            except:
                print("Attempt to open shutter failed at quarded_open command")
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





        #  NB NB First deal with the possible observing window being available or not.
        #  THis routine basically opens and keeps dome opposite the sun. Whether system
        #  takes sky flats or not is determined by the scheduler or calendar.  Mounting
        #  could be parked.
        
        #  At opposite end of night we will only open for morning skyflats if system
        #  bserverved for some specified time??
        if close_cmd or open_cmd:
            pass   #breakpoint()

        # if (ephemNow < g_dev['events']['Ops Window Start'] or ephemNow > g_dev['events']['Ops Window Closes']) \
        #     and g_dev['mnt'].site_in_automatic and False:
        #     #We want to force  closure but not bang on the dome agent too hard since the owner may want to
        #     #Get in the dome.  For now we pass.

        #     pass
                        
        debugOffset = 0.0 #days
        if g_dev['events']['Eve Sky Flats'] - debugOffset <= ephemNow <= g_dev['events']['Sun Rise'] + debugOffset:
            #  We are now in the full operational window.   ###Ops Window Start
            if g_dev['events']['Ops Window Start'] - debugOffset <= ephemNow <= g_dev['events']['Sun Set'] + debugOffset \
                and g_dev['mnt'].site_in_automatic and not wx_hold and True:
                #  Basically if in above window and Automatic and Not Wx_hold: if closed, open up.
                #  print('\nSlew to opposite the azimuth of the Sun, open and cool-down. Az =  ', az_opposite_sun)
                #  NB There is no corresponding warm up phase in the Morning.
                if self.status_string.lower() in ['closed']:  #, 'closing']:
                    self.guarded_open()
                    self.dome_opened = True
                    self.dome_homed = True
                if self.status_string.lower() in ['open']:    #WE found it open.
                    if self.is_dome and time.time() >= self.time_of_next_slew:
                        try:
                            #breakpoint()
                            self.enclosure.SlewToAzimuth(az_opposite_sun)
                            print("Now slewing to an azimuth opposite the Sun.")
                            self.dome_homed = False
                            self.time_of_next_slew = time.time() + 15
                        except:
                            pass#breakpoint()
                        
                    else:
                        self.dome_homed = False
            
             

        #  This routine basically opens the dome only.  Whether system
        #  takes images or not is determined by the scheduler or calendar.  Azimuth meant
        #  to be determined by that of the telescope.

            if (obs_win_begin < ephemNow < sunrise or open_cmd) \
                    and g_dev['mnt'].site_in_automatic \
                    and g_dev['ocn'].wx_is_ok \
                    and self.enclosure.ShutterStatus == 1: #  Closed
                if open_cmd:
                    self.state = 'User Opened the ' + shutter_str
                else:
                    self.state = 'Automatic nightime Open ' + shutter_str + '   Wx is OK; in Observing window.'
                self.cycles += 1           #if >=3 inhibits reopening for Wx  -- may need shelving so this persists.
                #  A countdown to re-open
                if self.status_string.lower() in ['closed', 'closing']:
                    self.guarded_open()   #<<<<NB NB NB Only enable when code is fully proven to work.
                    if self.is_dome:
                        self.enclosure.Slaved = True
                    else:
                        pass
                    
                    print("Night time Open issued to the "  + shutter_str, +   ' and is now following Mounting.')
        elif (obs_win_begin >= ephemNow or ephemNow >= sunrise):
            #WE are now outside the observing window, so Sun is up!!!
            if g_dev['enc'].site_in_automatic or close_cmd:
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
                       # self.enclosure.CloseShutter()
                        self.dome_opened = False
                        self.dome_homed = True
                       # print("Daytime Close issued to the " + shutter_str  + "   No longer following Mount.")
                    except:
                        print("Shutter busy right now!")
            elif not g_dev['enc'].site_in_automatic and open_cmd:

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
                    print("Telescope commanded to park, try again in a minute.")
                    
                
            
            
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

