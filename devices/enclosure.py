import win32com.client
from global_yard import g_dev
import redis
import time
import shelve
import json
import socket
import os
import config

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
def f_to_c(f):
    return round(5*(f - 32)/9, 2)

class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.site = config['site']
        self.config = config
        self.site_path = self.config['site_path']
        g_dev['enc'] = self
        breakpoint()
        try:
            self.mode, message, timestamp = self.get_site_mode()
        except:
            self.mode, message, timestamp = self.establish_site_mode()
        
        if self.mode == "Automatic":
            self.site_in_automatic = True
        elif self.mode == "Manual":
            self.site_in_automatic = False
        elif self.mode == 'Shutdown':
            self.site_in_automatic = False

        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
    
        self.time_of_next_slew = time.time()
        self.hostname = socket.gethostname()
        if self.hostname in self.config['wema_hostname']:
            self.is_wema = True
        else:
            self.is_wema = False
        if self.config['wema_is_active']:
            self.site_has_proxy = True  #NB Site is proxy needs a new name.
        else:
            self.site_has_proxy = False   
        if self.site in ['simulate',  'dht']:  #DEH: added just for testing purposes with ASCOM simulators.
            self.observing_conditions_connected = True
            self.site_is_proxy = False   
            print("observing_conditions: Simulator drivers connected True")
        elif self.config['site_is_specific']:
            self.site_is_specific = True
            #  Note OCN has no associated commands.
            #  Here we monkey patch
            self.get_status = config.get_enc_status
            # Get current ocn status just as a test.
            self.status = self.get_status(g_dev)

        elif self.is_wema: # or self.site_is_generic:   
            #  This is meant to be a generic Observing_condition code
            #  instance that can be accessed by a simple site or by the WEMA,
            #  assuming the transducers are connected to the WEMA.
            self.site_is_generic = True
            win32com.client.pythoncom.CoInitialize()
            self.enclosure = win32com.client.Dispatch(driver)
            print(self.enclosure)
            try:
                if not self.enclosure.Connected:
                    self.enclosure.Connected = True
                print("ASCOM enclosure connected.")
            except:
                 print("ASCOM enclosure NOT connected, proabably the App is not connected to telescope.")

            # breakpoint()  # All test code
            # quick = []
            # self.get_quick_status(quick)
            # print(quick)
        #self.prior_status = self.status
        #self.status = None   #  May need a status seed if site specific.
        #self.state = 'Ok'
        
    def establish_site_mode(self):
        site_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mode')
        site_shelf['mode'] = self.config['site_in_automatic_default']
        site_shelf['message'] = self.config['automatic_detail_default']
        site_shelf['timestamp']= time.time()
        mode = site_shelf['mode']
        message = site_shelf['message'] 
        timestamp = site_shelf['timestamp']
        site_shelf.close()
        return mode, message, timestamp
    
    def set_site_mode(self,  mode, message, timestamp):
        site_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mode')
        site_shelf['mode'] = mode
        site_shelf['message'] = message
        site_shelf['timestamp']= timestamp
        site_shelf.close()
        return
    
    def get_site_mode(self):
        site_shelf = shelve.open(self.site_path + 'ptr_night_shelf/' + 'mode')
        mode = site_shelf['mode']
        message = site_shelf['message'] 
        timestamp = site_shelf['timestamp']
        site_shelf.close()
        return mode, message, timestamp
        
    def get_status(self) -> dict: 

        if not self.is_wema and self.site_has_proxy:
            if self.config['site_IPC_mechanism'] == 'shares':
                try:
                    enclosure = open(self.config['wema_path'] + 'enclosure.txt', 'r')
                    status = json.loads(enclosure.readline())
                    enclosure.close()
                    self.status = status
                    self.prior_status = status
                    return status
                except:
                    try:
                        time.sleep(3)
                        enclosure = open(self.config['wema_path'] + 'enclosure.txt', 'r')
                        status = json.loads(enclosure.readline())
                        enclosure.close()
                        self.status = status
                        self.prior_status = status
                        return status
                    except:
                        try:
                            time.sleep(3)
                            enclosure = open(self.config['wema_path'] + 'enclosure.txt', 'r')
                            status = json.loads(enclosure.readline())
                            enclosure.close()
                            self.status = status
                            self.prior_status = status
                            return status
                        except:
                            print("Using prior enclosure status after 4 failures.")
                            return self.prior_status()
            elif self.config['site_IPC_mechanism'] == 'redis':
                try:
                    return eval(g_dev['redis'].get('enc_status'))
                except:
                    return g_dev['redis'].get('enc_status')
            else:
                breakpoint()

        if self.site_is_generic or self.is_wema:#  NB Should be AND?
            try:
                shutter_status = self.enclosure.ShutterStatus
            except:
                print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
                shutter_status = 5
            try:
                self.dome_home = self.enclosure.AtHome
            except:
                self.come_home = True
            
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

            status = {'shutter_status': stat_string}
            status['dome_slewing'] = in_motion
            status['enclosure_mode'] = str(self.mode)
            status['dome_azimuth'] = 0.0
            #g_dev['redis'].set('enc_status', status, ex=3600)  #This is occasionally used by mouning.
    
            if self.is_dome:
                try:
                    #Occasionally this property thr0ws an exception:  (W HomeDome)
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
                status = {'shutter_status': stat_string,
                          'enclosure_synchronized': self.following,
                          'dome_azimuth': round(self.enclosure.Azimuth, 1),
                          'dome_slewing': slewing,
                          'enclosure_mode': self.mode,
                          'enclosure_message': self.state}
                # if moving or self.enclosure.Slewing:
                #     in_motion = True
                # else:
                #     in_motion = False
                # status['dome_slewing'] = in_motion
                # # g_dev['redis'].set('dome_slewing', in_motion, ex=3600)
                # # g_dev['redis'].set('enc_status', status, ex=3600)
        if self.config['site_IPC_mechanism'] == 'shares':
            try:
                enclosure = open(self.config['site_share_path']+'enclosure.txt', 'w')
                enclosure.write(json.dumps(status))
                enclosure.close()
            except:
                time.sleep(3)
                try:
                    enclosure = open(self.config['site_share_path']+'enclosure.txt', 'w')
                    enclosure.write(json.dumps(status))
                    enclosure.close()
                except:
                    time.sleep(3)
                    enclosure = open(self.config['site_share_path']+'enclosure.txt', 'w')
                    enclosure.write(json.dumps(status))
                    enclosure.close()
                    print("3rd try to write enclosure status.")
        elif self.config['site_IPC_mechanism'] == 'redis':
            g_dev['redis'].set('<enc_status', status)  #THis needs to become generalized IPC 
            
# =============================================================================
#         # return status
# =============================================================================
        
        #Here we check if the observer has sent the WEMA any commands.
        if self.is_wema and self.site_has_proxy and self.config['site_IPC_mechanism'] == 'shares':
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

        elif self.is_wema and self.site_has_proxy and self.config['site_IPC_mechanism'] == 'redis':
            redis_command = self.redis_server.get('enc_cmd')  #It is presumed there is an expiration date on open command at least.
            #NB NB NB Need to prevent executing stale commands.  Note Redis_command is overloaded.
        if redis_command != ['none']:
            pass
            #print(redis_command)
        try:
            redis_command = redis_command[0]
        except:
            pass
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
        elif self.is_dome and redis_command == 'goHome':
            #breakpoint()
            self.redis_server.delete('goHome')
        elif self.is_dome and redis_command == 'sync_enc':
            self.following = True
            print("Scope Dome following set On")
            self.redis_server.delete('sync_enc')                
        elif self.is_dome and redis_command == 'unsync_enc':
            self.following = False
            print("Scope Dome following turned OFF")
            # NB NB NB no command to dome here
            self.redis_server.delete('unsync_enc')
        else:
            
            pass
            #NB NB NB  Possible race condition here.
          # redis_value = self.redis_server.get('SlewToAzimuth')
# =============================================================================
#         if self.config['site'] in ['saf'] and mount_command is not None and mount_command != '' and mount_command != ['none']:
#             try:
#                 print(self.status,'\n\n', mount_command)
# 
#                 adj1 = dome_adjust(mount_command['altitude'], mount_command['azimuth'], \
#                                   mount_command['hour_angle'])
#                 adjt = dome_adjust(mount_command['altitude'], mount_command['target_az'], \
#                                   mount_command['hour_angle'])
#                
#                     
#                     
#             except:
#                 adj = 0
#                 pass
#             if self.is_dome and self.status is not None:   #First time around, stauts is None.
#                 if mount_command['is_slewing'] and not self.slew_latch:   # NB NB NB THIS should have a timeout
#                     self.enclosure.SlewToAzimuth(float(adjt))
#                     self.slew_latch = True   #Isuing multiple Slews causes jerky Dome motion.
#                 elif self.slew_latch and not mount_command['is_slewing']:
#                     self.slew_latch = False   #  Return to Dpme following.
#                     self.enclosure.SlewToAzimuth(float(adj1))
#                 elif (not self.slew_latch) and (self.status['enclosure_synchronized'] or \
#                                                 self.mode == "Automatic"):
#                     #This is normal dome following.
#                     try:
#                         if shutter_status not in [2,3]:    #THis should end annoying report.
#                             self.enclosure.SlewToAzimuth(float(adj1))
#                     except:
#                         print("Dome refused slew, probably closing or opening, usually a harmless situation.")
#                     
# =============================================================================
                    
                
                 
            
            
        #self.status = status
        
        breakpoint()
        #self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status
    
          
        #     try:

        #         stat_string = g_dev['redis'].get("shutter_status")
        #         self.status = eval(g_dev['redis'].get("enc_status"))
        #     except:
        #         print("\nWxEnc Agent WEMA not running. Please start it up.|n")
        #     if stat_string is not None:
        #         if stat_string == 'Closed':
        #             self.shutter_is_closed = True
        #         else:
        #             self.shutter_is_closed = False
        #         #print('Proxy shutter status:  ', status)
        #         return  stat_string
        #     else:
        #         self.shutter_is_closed = True
        #         return

    def parse_command(self, command):
        "Note:  This code is typically received by the observer's enclosure module but commands execute at the WEMA's\
                host computer.  The command is killed upon execution."

        if self.config['enclosure']['enclosure1']['enc_is_specific']:
            return  #There is noting to do!
        #This gets commands from AWS, not normally used.
        req = command['required_params']
        opt = command['optional_params']

        action = command['action']
        cmd_list = []
        generic = True
        _redis = False
        shares = False
        if self.config['wema_is_active'] and self.config['site_IPC_mechanism']  == 'redis':
             _redis = True
             shares = False
             generic = False
        if self.config['wema_is_active'] and self.config['site_IPC_mechanism']  == 'shares':
             _redis = False
             shares = True
             generic = False
        if action == "open":
            if _redis:  g_dev['redis'].set('enc_cmd', 'open', ex=300)
            if shares:  cmd_list.append('open')
            if generic:  self.open_command(req, opt)
        elif action == "close":
            if _redis:  g_dev['redis'].set('enc_cmd', 'close', ex=300)
            if shares:  cmd_list.append('close')
            if generic:  self.close_command(req, opt)
        elif action == "setAuto":
            if _redis:  g_dev['redis'].set('enc_cmd', 'setAuto', ex=300)
            if shares:  cmd_list.append('set_auto')
            if generic:
                self.mode = 'Automatic'
            g_dev['enc'].site_in_automatic = True
            g_dev['enc'].automatic_detail =  "Night Automatic"
            print("Site and Enclosure set to Automatic.")
        elif action == "setManual":
            if _redis:  g_dev['redis'].set('enc_cmd', 'setManual', ex=300)
            if shares:  cmd_list.append('setManual')
            if generic:
                self.mode = 'Manual'
            g_dev['enc'].site_in_automatic = False
            g_dev['enc'].automatic_detail =  "Manual Only"
        elif action in ["setStayClosed", 'setShutdown', 'shutDown']:
            if _redis:  g_dev['redis'].set('enc_cmd', 'setShutdown', ex=300)
            if shares:  cmd_list.append('setShutdown')
            if generic:
                self.mode = 'Shutdown'
            g_dev['enc'].site_in_automatic = False
            g_dev['enc'].automatic_detail =  "Site Shutdown"
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

        if len(cmd_list) > 0:
            try:
                enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                enclosure.write(json.dumps(cmd_list))
                enclosure.close()
            except:
                try:
                    time.sleep(3)
                    enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                    enclosure.write(json.dumps(cmd_list))
                    enclosure.close()
                except:
                    try:
                        time.sleep(3)
                        enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                        enclosure.write(json.dumps(cmd_list))
                        enclosure.close()
                    except:
                        time.sleep(3)
                        enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                        enclosure.write(json.dumps(cmd_list))
                        enclosure.close()
                        print("4th try to append to enc-cmd  list.")
        return


    ##############################
    #     Enclosure Commands     #
    ##############################

    def open_command(self, req: dict, opt: dict):
    #     ''' open the enclosure '''
          g_dev['redis'].set('enc_cmd', 'open', ex=1200)
    #     #self.guarded_open()
    #     self.manager(open_cmd=True)
    #     print("enclosure cmd: open.")
    #     self.dome_open = True
    #     self.dome_home = True
    #     pass

    def close_command(self, req: dict, opt: dict):
    #     ''' close the enclosure '''
          g_dev['redis'].set('enc_cmd', 'close', ex=1200)
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



# if __name__ =='__main__':
#     print('Enclosure class started locally')
#     enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

