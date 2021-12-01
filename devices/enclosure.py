import win32com.client
from global_yard import g_dev
import redis
import time
import shelve

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
        redis_ip = config['redis_ip']   #Do we really need to duplicate this config entry?
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
            g_dev['redis_server'] = self.redis_server 
        else:
            self.redis_wx_enabled = False
        if self.config['agent_wms_enc_active']:
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
        else:
            self.site_is_proxy = False
        
    def get_status(self) -> dict:
        #<<<<The next attibute reference fails at saf, usually spurious Dome Ring Open report.
        #<<< Have seen other instances of failing.
        #core1_redis.set('unihedron1', str(mpsas) + ', ' + str(bright) + ', ' + str(illum), ex=600)
        if self.site == 'saf':
            try:
                wx = open(self.config['wema_path'] + 'boltwood.txt', 'r')
                wx_line = wx.readline()
                wx.close
                #print(wx_line)
                wx_fields = wx_line.split()
                skyTemperature = float( wx_fields[4])
                temperature = f_to_c(float(wx_fields[5]))
                windspeed = round(float(wx_fields[7])/2.237, 2)
                humidity =  float(wx_fields[8])
                dewpoint = f_to_c(float(wx_fields[9]))
                timeSinceLastUpdate = wx_fields[13]
                open_ok = wx_fields[19]
                #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
                self.focus_temp = temperature
                return
            except:
                time.sleep(5)
                try:
                    wx = open(self.config['wema_path'] + 'boltwood.txt', 'r')
                    wx_line = wx.readline()
                    wx.close
                    #print(wx_line)
                    wx_fields = wx_line.split()
                    skyTemperature = float( wx_fields[4])
                    temperature = f_to_c(float(wx_fields[5]))
                    windspeed = round(float(wx_fields[7])/2.237, 2)
                    humidity =  float(wx_fields[8])
                    dewpoint = f_to_c(float(wx_fields[9]))
                    timeSinceLastUpdate = wx_fields[13]
                    open_ok = wx_fields[19]
                    #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
                    self.focus_temp = temperature
                    return
                except:
                    print('Wema Weather source problem, 2nd try.')
                    self.focus_temp = 10.
                    return
            
            
            
        elif self.site_is_proxy:
            #Usually fault here because WEMA is not running.
  
    
          
            try:

                stat_string = self.redis_server.get("shutter_status")
                self.status = eval(self.redis_server.get("enc_status"))
            except:
                print("\nWxEnc Agent WEMA not running. Please start it up.|n")
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

