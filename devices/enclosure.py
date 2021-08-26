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

NB,  Dome refers to a rotating roof that presumably needs azimuth alignmnet of some form
Shutter, Roof, Slit, etc., are the same things.
'''

# =============================================================================
# This module has been modified into wema only code
# =============================================================================

class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.site = config['site']
        self.config = config
        g_dev['enc'] = self
        redis_ip = config['redis_ip']   #Do we really need to duplicate this config entry?
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
            g_dev['redis_server'] = self.redis_server 
        else:
            self.redis_wx_enabled = False
        if not self.config['agent_wms_enc_active']:
            breakpoint()
            # self.site_is_proxy = False
            # win32com.client.pythoncom.CoInitialize()
            # self.enclosure = win32com.client.Dispatch(driver)
            # print(self.enclosure)
            # if not self.enclosure.Connected:
            #     self.enclosure.Connected = True
            # print("ASCOM enclosure connected.")

            # self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
            # self.state = 'Closed'
            # #self.mode = 'Automatic'   #  Auto|User Control|User Close|Disable
            # self.enclosure_message = '-'
            # #self.shutter_is_closed = False   #NB initializing this is important.
            # self.external_close = False   #If made true by operator,  system will not reopen for the night
            # self.dome_opened = False   #memory of prior issued commands  Restarting code may close dome one time.
            # self.dome_homed = False
            # self.cycles = 0
            # self.prior_status = None
            # self.time_of_next_slew = time.time()
            # if self.config['site_in_automatic_default'] == 'Manual':
            #     self.site_in_automatic = False
            #     self.mode = 'Manual' 
            #     self.automatic_detail = 'Manual'
            # else:
            #     self.site_in_automatic = True
            #     self.mode = 'Automatic'
            #     self.automatic_detail = 'Automatic'
        else:
            self.site_is_proxy = True
            self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
    
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
        if self.site_is_proxy:
            stat_string = self.redis_server.get("shutter_status")
            
            self.status = eval(self.redis_server.get("status"))
            if stat_string is not None:
                if stat_string == 'Closed':
                    self.shutter_is_closed = True
                else:
                    self.shutter_is_closed = False
                #print('Proxy shutter status:  ', status)
                return  stat_string
            else:
                self.shutter_is_closed = True
                return
    #     elif self.site in ['saf', 'mrc', 'mrc2']:
    #         try:
    #             shutter_status = self.enclosure.ShutterStatus
    #         except:
    #             print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
    #             shutter_status = 5
    #         if shutter_status == 0:
    #             stat_string = "Open"
    #             self.shutter_is_closed = False
    #         elif shutter_status == 1:
    #              stat_string = "Closed"
    #              self.shutter_is_closed = True
    #         elif shutter_status == 2:
    #              stat_string = "Opening"
    #              self.shutter_is_closed = False
    #         elif shutter_status == 3:
    #              stat_string = "Closing"
    #              self.shutter_is_closed = False
    #         elif shutter_status == 4:
    #              stat_string = "Error"
    #              self.shutter_is_closed = False
    #         else:
    #              stat_string = "Software Fault"
    #              self.shutter_is_closed = False

    #     if self.site == 'saf':
    #        try:
    #            status = {'shutter_status': stat_string,
    #                   'roof_status': stat_string,
    #                   'enclosure_synch': self.enclosure.Slaved,
    #                   'dome_azimuth': round(self.enclosure.Azimuth, 1),
    #                   'dome_slewing': self.enclosure.Slewing,
    #                   'enclosure_mode': self.mode,
    #                   'enclosure_message': self.state}
    #            self.prior_status = status
    #        except:
    #            status = self.prior_status
    #            print("Prior status used for saf dome azimuth")
    #            # status = {'shutter_status': stat_string,
    #            #        'enclosure_synch': 'unknown',
    #            #        'dome_azimuth': str(round(self.enclosure.Azimuth, 1)),
    #            #        'dome_slewing': str(self.enclosure.Slewing),
    #            #        'enclosure_mode': str(self.mode),
    #            #        'enclosure_message': str(self.state)}

    #     elif self.site in ['mrc', 'mrc2']:
    #         status = {'roof_status': stat_string,
    #                   'shutter_status': stat_string,
    #                   'enclosure_synch': self.enclosure.Slaved,   #  What should  this mean for a roof? T/F = Open/Closed?
    #                   'enclosure_mode': self.mode,
    #                   'enclosure_message': self.state}
    #         self.redis_server.set('roof_status', str(stat_string), ex=600)
    #         self.redis_server.set('shutter_is_closed', self.shutter_is_closed, ex=600)  #Used by autofocus
    #         self.redis_server.set("shutter_status", str(stat_string), ex=600)
    #         self.redis_server.set('enclosure_synch', str(self.enclosure.Slaved), ex=600)
    #         self.redis_server.set('enclosure_mode', str(self.mode), ex=600)
    #         self.redis_server.set('enclosure_message', str(self.state), ex=600)        #print('Enclosure status:  ', status

    #     else:
    #         status = {'roof_status': 'unknown',
    #                   'shutter_status': 'unknown',
    #                   'enclosure_synch': 'unknown',   #  What should  this mean for a roof? T/F = Open/Closed?
    #                   'enclosure_mode': 'unknown',
    #                   'enclosure_message': 'unknown'
    #                   }
    #         stat_string = 'unknown'
    #     #print('Enclosure status:  ', status
    #     self.status_string = stat_string
    #     if self.site_is_proxy:
    #         redis_command = self.redis_server.set('enc_cmd', True, ex=1200)
    #         if redis_command == 'open':
    #             breakpoint()
    #             self.manager(open_cmd=True)
    #             self.redis_server.delete('enc_cmd')
    #             print("enclosure local cmd: open.")
    #             self.dome_open = True
    #             self.dome_home = True
    #         elif redis_command == 'close':
    #             self.manager(close_cmd=True)
    #             self.redis_server.delete('enc_cmd')
    #             print("enclosure local cmd: close.")
    #             self.dome_open = True
    #             self.dome_home = True
    #         else:  
    #             pass
    #     self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    #     return status


    def parse_command(self, command):   #This gets commands from AWS, not normally used.
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "open":
            if self.site_is_proxy:
                self.redis_server.set('enc_cmd', 'open', ex=300)
            else:
                self.open_command(req, opt)
        elif action == "close":
            if self.site_is_proxy:
                self.redis_server.set('enc_cmd', 'close', ex=1200)
            else:
                self.close_command(req, opt)
        elif action == "setAuto":
            if self.site_is_proxy:
                self.redis_server.set('enc_cmd', 'setAuto', ex=300)
            else:
                self.mode = 'Automatic'
                g_dev['enc'].site_in_automatic = True
                g_dev['enc'].automatic_detail =  "Night Automatic"
                print("Site and Enclosure set to Automatic.")
        elif action == "setManual":
            if self.site_is_proxy:
                self.redis_server.set('enc_cmd', 'setManual', ex=300)
            else:
                self.mode = 'Manual'
                g_dev['enc'].site_in_automatic = False
                g_dev['enc'].automatic_detail =  "Manual Only"
        elif action in ["setStayClosed", 'setShutdown', 'shutDown']:
            if self.site_is_proxy:
                self.redis_server.set('enc_cmd', 'setShutdown', ex=300)
                self.mode = 'Shutdown'
                g_dev['enc'].site_in_automatic = False
                g_dev['enc'].automatic_detail =  "Site Shutdown"
                print("Site and Enclosure set to Shutdown.")
        # elif action == "slew_alt":
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
            print("Command <{action}> not recognized.")


    ###############################
    #      Enclosure Commands     #
    ###############################

    def open_command(self, req: dict, opt: dict):
    #     ''' open the enclosure '''
          self.redis_server.set('enc_cmd', 'open', ex=1200)
    #     #self.guarded_open()
    #     self.manager(open_cmd=True)
    #     print("enclosure cmd: open.")
    #     self.dome_open = True
    #     self.dome_home = True
    #     pass

    def close_command(self, req: dict, opt: dict):
    #     ''' close the enclosure '''
          self.redis_server.set('enc_cmd', 'close', ex=1200)
    #     self.manager(close_cmd=True)
    #     print("enclosure cmd: close.")
    #     self.dome_open = False
    #     self.dome_home = True
    #     pass

    # def slew_alt_command(self, req: dict, opt: dict):
    #     print("enclosure cmd: slew_alt")
    #     pass

    # def slew_az_command(self, req: dict, opt: dict):
    #     print("enclosure cmd: slew_az")
    #     self.dome_home = False    #As a general rule
    #     pass

    # def sync_az_command(self, req: dict, opt: dict):
    #     print("enclosure cmd: sync_alt")
    #     pass

    # def sync_mount_command(self, req: dict, opt: dict):
    #     print("enclosure cmd: sync_az")
    #     pass

    # def park_command(self, req: dict, opt: dict):
    #     ''' park the enclosure if it's a dome '''
    #     print("enclosure cmd: park")
    #     self.dome_home = True
    #     pass



if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

