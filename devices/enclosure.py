import win32com.client
from global_yard import g_dev
import redis
import time
import shelve
import json
import config_file

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
        g_dev['enc'] = self
        if self.config['site_in_automatic_default'] == "Automatic":
            self.site_in_automatic = True
            self.mode = 'Automatic' 
        elif self.config['site_in_automatic_default'] == "Manual":
            self.site_in_automatic = False
            self.mode = 'Manual'
        else:
            self.site_in_automatic = False
            self.mode = 'Shutdown'
        self.is_dome = self.config['enclosure']['enclosure1']['is_dome']
    
        self.time_of_next_slew = time.time()
        if self.site in ['simulate',  'dht']:  #DEH: added just for testing purposes with ASCOM simulators.
            #self.observing_conditions_connected = True
            self.site_is_proxy = False
            print("observing_conditions: Simulator drivers connected True")
        elif self.config['agent_wms_enc_active']:
            self.site_is_proxy = True
        elif self.config['site_is_specific']:
            self.site_is_specific = True
            #  Note OCN has no associated commands.
            #  Here we monkey patch
            self.get_status = config_file.get_enc_status
            # Get current ocn status just as a test.
            self.status = self.get_status(g_dev)
            # All test code
            # quick = []
            # self.get_quick_status(quick)
            # print(quick)
        #self.prior_status = self.status
        self.status = None   #  May need a status seed if site specific.
        #self.state = 'Ok'
        
    def get_status(self) -> dict:
        #<<<<The next attibute reference fails at saf, usually spurious Dome Ring Open report.
        #<<< Have seen other instances of failing.
        #core1_redis.set('unihedron1', str(mpsas) + ', ' + str(bright) + ', ' + str(illum), ex=600)

        if self.config['agent_wms_enc_active'] and self.config['site_IPC_mechanism'] == 'share':
            breakpoint()
            try:
                enclosure = open(self.config['site_share_path'] + 'enclosure.txt', 'r')
                status = json.loads(enclosure.readline())
                enclosure.close()
                self.status = status
                self.prior_status = status
                return status
            except:
                try:
                    time.sleep(3)
                    enclosure = open(self.config['site_share_path'] + 'enclosure.txt', 'r')
                    enclosure.close()
                    status = json.loads(enclosure.readline())
                    self.status = status
                    self.prior_status = status
                    return status
                except:
                    try:
                        time.sleep(3)
                        enclosure = open(self.config['site_share_path'] + 'enclosure.txt', 'r')
                        status = json.loads(enclosure.readline())
                        enclosure.close()
                        self.status = status
                        self.prior_status = status
                        return status
                    except:
                        print("Prior enc status returned fter 3 fails.")
                        return self.prior_status
            
        elif self.site_is_proxy:
            breakpoint()
        else:
            breakpoint()
            #Usually fault here because WEMA is not running.
  
    
          
        #     try:

        #         stat_string = self.redis_server.get("shutter_status")
        #         self.status = eval(self.redis_server.get("enc_status"))
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
        if self.config['enc_is_specific']:
            return  #There is noting to do!
        #This gets commands from AWS, not normally used.
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        cmd_list = []

        if action == "open":
            if self.site_is_proxy:
                #self.redis_server.set('enc_cmd', 'open', ex=300)
                cmd_list.append('open')
            else:
                self.open_command(req, opt)
        elif action == "close":
            if self.site_is_proxy:
                #self.redis_server.set('enc_cmd', 'close', ex=1200)
                cmd_list.append('close')
            else:
                self.close_command(req, opt)
        elif action == "setAuto":
            if self.site_is_proxy:
                #self.redis_server.set('enc_cmd', 'setAuto', ex=300)
                cmd_list.append('setAuto')
            else:
                self.mode = 'Automatic'
                g_dev['enc'].site_in_automatic = True
                g_dev['enc'].automatic_detail =  "Night Automatic"
                print("Site and Enclosure set to Automatic.")
        elif action == "setManual":
            if self.site_is_proxy:
                #self.redis_server.set('enc_cmd', 'setManual', ex=300)
                cmd_list.append('setManual')
            else:
                self.mode = 'Manual'
                g_dev['enc'].site_in_automatic = False
                g_dev['enc'].automatic_detail =  "Manual Only"
        elif action in ["setStayClosed", 'setShutdown', 'shutDown']:
            if self.site_is_proxy:
                #self.redis_server.set('enc_cmd', 'setShutdown', ex=300)
                cmd_list.append('setShutdown')
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

        if len(cmd_list) > 0:
            try:
                enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                enclosure.write(json.dumps(cmd_list))
                enclosure.close()
            except:
                try:
                    time.sleep(3)
                    # enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'r')
                    # enclosure.write(json.loads(status))
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
                        enclosure = open(self.config['wema_path']+'enc_cmd.txt', 'w')
                        enclosure.write(json.dumps(cmd_list))
                        enclosure.close()
                        print("3rd try to append to enc-cmd  list.")


    ###############################
    #      Enclosure Commands     #
    ###############################

    # def open_command(self, req: dict, opt: dict):
    # #     ''' open the enclosure '''
    #       self.redis_server.set('enc_cmd', 'open', ex=1200)
    # #     #self.guarded_open()
    # #     self.manager(open_cmd=True)
    # #     print("enclosure cmd: open.")
    # #     self.dome_open = True
    # #     self.dome_home = True
    # #     pass

    # def close_command(self, req: dict, opt: dict):
    # #     ''' close the enclosure '''
    #       self.redis_server.set('enc_cmd', 'close', ex=1200)
    # #     self.manager(close_cmd=True)
    # #     print("enclosure cmd: close.")
    # #     self.dome_open = False
    # #     self.dome_home = True
    # #     pass

    # # def slew_alt_command(self, req: dict, opt: dict):
    # #     print("enclosure cmd: slew_alt")
    # #     pass

    # # def slew_az_command(self, req: dict, opt: dict):
    # #     print("enclosure cmd: slew_az")
    # #     self.dome_home = False    #As a general rule
    # #     pass

    # # def sync_az_command(self, req: dict, opt: dict):
    # #     print("enclosure cmd: sync_alt")
    # #     pass

    # # def sync_mount_command(self, req: dict, opt: dict):
    # #     print("enclosure cmd: sync_az")
    # #     pass

    # # def park_command(self, req: dict, opt: dict):
    # #     ''' park the enclosure if it's a dome '''
    # #     print("enclosure cmd: park")
    # #     self.dome_home = True
    # #     pass



if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

