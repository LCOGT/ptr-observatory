
import win32com.client
import redis
import time
# import requests
import json
import socket
from global_yard import g_dev
import config_file
# import ptr_events


'''

This module contains the weather class.  When get_status() is called the weather situation
is evaluated and self.wx_is_ok  and self.open_is_ok is evaluated and published along
with self.status, a dictionary.

This module should be expanded to integrate multiple Wx sources, particularly Davis and
SkyAlert.

Weather holds are counted only when they INITIATE within the Observing window. So if a
hold started just before the window and opening was late that does not count for anti-
flapping purposes.

This is module sends 'signals' through the Events layer then TO the enclosure by checking
as sender that an OPEN for example can get through the Events layer. It is Mandatory
the receiver (the enclosure in this case) also checks the Events layer.  The events layer
is populated once per observing day with default values.  However the dictionary entries
can be modified for debugging or simulation purposes.

'''


def linearize_unihedron(uni_value):  # Need to be coefficients in config.
    #  Based on 20180811 data
    uni_value = float(uni_value)
    if uni_value < -1.9:
        uni_corr = 2.5**(-5.85 - uni_value)
    elif uni_value < -3.8:
        uni_corr = 2.5**(-5.15 - uni_value)
    elif uni_value <= -12:
        uni_corr = 2.5**(-4.88 - uni_value)
    else:
        uni_corr = 6000
    return uni_corr


def f_to_c(f):
    return round(5*(f - 32)/9, 2)


class ObservingConditions:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        #  We need a way to specify whihc computer in the wema in the
        #  the singular config_file or we have two configurations.
        #  import socket
        #  print(socket.gethostname())

        self.name = name
        self.astro_events = astro_events
        g_dev['ocn'] = self
        self.site = config['site']
        self.config = config
        self.sample_time = 0
        self.ok_to_open = 'No'
        self.observing_condtions_message = '-'
        self.wx_is_ok = False
        self.wx_hold = False
        self.wx_to_go = 0.0
        self.wx_hold_last_updated = time.time()   # This is meant for a stale check on the Wx hold report
        self.wx_hold_tally = 0
        self.wx_clamp = False
        self.clamp_latch = False
        self.wait_time = 0        # A countdown to re-open
        self.wx_close = False     # If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_hold_until_time = None
        self.wx_hold_count = 0     # if >=5 inhibits reopening for Wx
        self.wait_time = 0        # A countdown to re-open
        self.wx_close = False     # If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_system_enable = True   # Purely a debugging aid.
        self.wx_test_cycle = 0
        self.prior_status = None
        self.prior_status_2 = None
        self.wmd_fail_counter = 0
        self.temperature = self.config['reference_ambient']  # Index needs
        self.pressure = self.config['reference_pressure']  # to be months.
        self.unihedron_connected = True  # NB NB NB His needs improving, driving from config
        self.hostname = socket.gethostname()
        self.site_is_specific = False
        if self.hostname in self.config['wema_hostname']:
            self.is_wema = True
        else:
            self.is_wema = False
        if self.config['wema_is_active']:
            self.site_has_proxy = True  # NB Site is proxy needs a new name.
        else:
            self.site_has_proxy = False
        if self.site in ['simulate',  'dht']:  # DEH: added just for testing purposes with ASCOM simulators.
            self.observing_conditions_connected = True
            self.site_is_proxy = False
            print("observing_conditions: Simulator drivers connected True")
        elif self.config['site_is_specific']:
            self.site_is_specific = True
            #  Note OCN has no associated commands.
            #  Here we monkey patch
            self.get_status = config_file.get_ocn_status
            # Get current ocn status just as a test.
            self.status = self.get_status(g_dev)
            # breakpoint()  # All test code
            # quick = []
            # self.get_quick_status(quick)
            # print(quick)
        elif (self.is_wema or self.site_is_specific):
            #  This is meant to be a generic Observing_condition code
            #  instance that can be accessed by a simple site or by the WEMA,
            #  assuming the transducers are connected to the WEMA.
            self.site_is_generic = True
            win32com.client.pythoncom.CoInitialize()
            self.sky_monitor = win32com.client.Dispatch(driver)
            self.sky_monitor.connected = True   # This is not an ASCOM device.
            driver_2 = config['observing_conditions']['observing_conditions1']['driver_2']
            self.sky_monitor_oktoopen = win32com.client.Dispatch(driver_2)
            self.sky_monitor_oktoopen.Connected = True
            driver_3 = config['observing_conditions']['observing_conditions1']['driver_3']
            if driver_3 is not None:
                self.sky_monitor_oktoimage = win32com.client.Dispatch(driver_3)
                self.sky_monitor_oktoimage.Connected = True
            print("observing_conditions: sky_monitors connected = True")
            if config['observing_conditions']['observing_conditions1']['has_unihedron']:
                self.unihedron_connected = True
                try:
                    driver = config['observing_conditions']['observing_conditions1']['uni_driver']
                    port = config['observing_conditions']['observing_conditions1']['unihedron_port']
                    self.unihedron = win32com.client.Dispatch(driver)
                    self.unihedron.Connected = True
                    print("observing_conditions: Unihedron connected = True, on COM" + str(port))
                except:
                    print("Unihedron on Port 10 is disconnected.  Observing will proceed.")
                    self.unihedron_connected = False
                    # NB NB if no unihedron is installed the status code needs to not report it.
        self.status = None   # This **may** need to have a first status if site_specific is True.
        self.last_wx = None

    def get_status(self):   # This is purely generic code for a generic site.
                            # It may be overwritten with a monkey patch found 
                            # in the appropriate config_file.py
        '''
        Regularly calling this routine returns weather status dict for AWS, evaluates the Wx 
        reporting and manages temporary closes, known as weather-holds.
        
        

        Returns
        -------
        status : TYPE
            DESCRIPTION.

        '''

        if not self.is_wema and self.site_has_proxy:
            if self.config['site_IPC_mechanism'] == 'shares':
                try:
                    weather = open(self.config['wema_path'] + 'weather.txt', 'r')
                    status = json.loads(weather.readline())
                    weather.close()
                    self.status = status
                    self.prior_status = status
                    return status
                except:
                    try:
                        time.sleep(3)
                        weather = open(self.config['wema_path'] + 'weather.txt', 'r')
                        status = json.loads(weather.readline())
                        weather.close()
                        self.status = status
                        self.prior_status = status
                        return status
                    except:
                        try:
                            time.sleep(3)
                            weather = open(self.config['wema_path'] + 'weather.txt', 'r')
                            status = json.loads(weather.readline())
                            weather.close()
                            self.status = status
                            self.prior_status = status
                            return status
                        except:
                            print("Using prior OCN status after 4 failures.")
                            return self.prior_status()
            elif self.config['site_IPC_mechanism'] == 'redis':
                 return g_dev['redis'].get('wx_state', status)
            else:
                breakpoint()

        if self.site_is_generic or self.is_wema:  #These operations are common to a generic single computer or wema site.
            status= {}
            illum, mag = self.astro_events.illuminationNow()
            #illum = float(redis_monitor["illum lux"])
            if illum > 500:
                illum = int(illum)
            else:
                illum = round(illum, 3)
            if self.unihedron_connected:
                try:
                    uni_measure = self.unihedron.SkyQuality   #  Provenance of 20.01 is dubious 20200504 WER
                except:
                    print("Unihedron did not read.")
                    uni_measure = 0
            if uni_measure == 0:
                uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
                status["meas_sky_mpsas"] = uni_measure
                self.meas_sky_lux = illum
            else:
                self.meas_sky_lux = linearize_unihedron(uni_measure)
                status["meas_sky_mpsas"] = uni_measure

            self.temperature = round(self.sky_monitor.Temperature, 2)
            try:  #  NB NB Boltwood vs. SkyAlert difference.  What about FAT?
                self.pressure = self.sky_monitor.Pressure,  #978   #Mbar to mmHg  #THIS IS A KLUDGE
            except:
                self.pressure = self.config['reference_pressure']
            status = {"temperature_C": round(self.temperature, 2),
                      "pressure_mbar": self.pressure,
                      "humidity_%": self.sky_monitor.Humidity,
                      "dewpoint_C": self.sky_monitor.DewPoint,
                      "sky_temp_C": round(self.sky_monitor.SkyTemperature,2),
                      "last_sky_update_s":  round(self.sky_monitor.TimeSinceLastUpdate('SkyTemperature'), 2),
                      "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                      'rain_rate': self.sky_monitor.RainRate,
                      'solar_flux_w/m^2': None,
                      'cloud_cover_%': str(self.sky_monitor.CloudCover),
                      "calc_HSI_lux": illum,
                      "calc_sky_mpsas": round(uni_measure,2),    #  Provenance of 20.01 is dubious 20200504 WER
                      #"wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                      "open_ok": self.ok_to_open,
                      'wx_hold': self.wx_hold,
                      'hold_duration': self.wx_to_go
                      }

            dew_point_gap = not (self.sky_monitor.Temperature  - self.sky_monitor.DewPoint) < 2
            temp_bounds = not (self.sky_monitor.Temperature < -15) or (self.sky_monitor.Temperature > 42)
            wind_limit = self.sky_monitor.WindSpeed < 35/2.235   #sky_monitor reports m/s, Clarity may report in MPH
            sky_amb_limit  = (self.sky_monitor.SkyTemperature - self.sky_monitor.Temperature) < -8   #"""NB THIS NEEDS ATTENTION>
            humidity_limit = 1 < self.sky_monitor.Humidity < 85
            rain_limit = self.sky_monitor.RainRate <= 0.001

      
            self.wx_is_ok = dew_point_gap and temp_bounds and wind_limit and sky_amb_limit and \
                            humidity_limit and rain_limit
            #  NB  wx_is_ok does not include ambient light or altitude of the Sun
            if self.wx_is_ok:
                wx_str = "Yes"
                status["wx_ok"] = "Yes"
            else:
                wx_str = "No"   #Ideally we add the dominant reason in priority order.
                status["wx_ok"] = "No"
        
            g_dev['wx_ok']  =  self.wx_is_ok
            if self.config['site_IPC_mechanism'] == 'shares':
                try:
                    weather = open(self.config['site_share_path']+'weather.txt', 'w')
                    weather.write(json.dumps(status))
                    weather.close()
                except:
                    print("1st try to write weather status failed.")
                    time.sleep(3)
                    try:
                        weather = open(self.config['site_share_path']+'weather.txt', 'w')
                        weather.write(json.dumps(status))
                        weather.close()
                    except:
                        print("2nd try to write weather status failed.")
                        time.sleep(3)
                        try:
                            weather = open(self.config['site_share_path']+'weather.txt', 'w')
                            weather.write(json.dumps(status))
                            weather.close()
                        except:
                            print("3rd try to write weather status failed.")
                            time.sleep(3)
                            weather = open(self.config['site_share_path']+'weather.txt', 'w')
                            weather.write(json.dumps(status))
                            weather.close()
                            print("4th try to write weather status.")
            elif self.config['site_IPC_mechanism'] == 'redis':

                g_dev['redis'].set('wx_state', status)  #THis needs to become generalized IP      

            # Only write when around dark, put in CSV format, used to calibrate Unihedron.
            sunZ88Op, sunZ88Cl, sunrise, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            two_hours = 2/24    #  Note changed to 2 hours.   NB NB NB The times need changing to bracket skyflats.
            if  (sunZ88Op - two_hours < ephemNow < sunZ88Cl + two_hours) and (time.time() >= \
                  self.sample_time + 60):    #  Once a minute.
                try:
                    wl = open('C:/ptr/unihedron/wx_log.txt', 'a')
                    wl.write(str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                             + str(uni_measure) + ", \n")
                    wl.close()
                    print('Unihedron log worked.')
                    self.sample_time = time.time()
                except:
                    self.sample_time = time.time() - 61
                    #print("redis_monitor log did not write.")
            '''
            Now lets compute Wx hold condition.  Class is set up to assume Wx has been good.
            The very first time though at Noon, self.open_is_ok will always be False but the
            Weather, which does not include ambient light, can be good.  We will assume that
            changes in ambient light are dealt with more by the Events module.
    
            We want the wx_hold signal to go up and down as a guage on the quality of the
            afternoon.  If there are a lot of cycles, that indicates unsettled conditons even
            if any particular instant is perfect.  So we set self.wx_hold to false during class
            __init__().
    
            When we get to this point of the code first time we expect self.wx_is_ok to be true
            '''
            obs_win_begin, sunset, sunrise, ephemNow = self.astro_events.getSunEvents()
            wx_delay_time = 900
            if (self.wx_is_ok and self.wx_system_enable) and not self.wx_hold:     #Normal condition, possibly nothing to do.
                self.wx_hold_last_updated = time.time()
            elif not self.wx_is_ok and not self.wx_hold:     #Wx bad and no hold yet.
                #Bingo we need to start a cycle
                self.wx_hold = True
                self.wx_hold_until_time = (t := time.time() + wx_delay_time)    #15 minutes   Make configurable
                self.wx_hold_tally += 1     #  This counts all day and night long.
                self.wx_hold_last_updated = t
                if obs_win_begin <= ephemNow <= sunrise:     #Gate the real holds to be in the Observing window.
                    self.wx_hold_count += 1
                    #We choose to let the enclosure manager handle the close.
                    print("Wx hold asserted, flap#:", self.wx_hold_count, self.wx_hold_tally)
                else:
                    print("Wx Hold -- out of Observing window.", self.wx_hold_count, self.wx_hold_tally)
            elif not self.wx_is_ok and self.wx_hold:     #WX is bad and we are on hold.
                self.wx_hold_last_updated = time.time()
                #Stay here as long as we need to.
                self.wx_hold_until_time = (t := time.time() + wx_delay_time)
                if self.wx_system_enable:
                    #print("In a wx_hold.")
                    pass
                    #self.wx_is_ok = True
            elif self.wx_is_ok  and self.wx_hold:     #Wx now good and still on hold.
                if self.wx_hold_count < 3:
                    if time.time() >= self.wx_hold_until_time and not self.wx_clamp:
                        #Time to release the hold.
                        self.wx_hold = False
                        self.wx_hold_until_time = time.time() + wx_delay_time  #Keep pushing the recovery out
                        self.wx_hold_last_updated = time.time()
                        print("Wx hold released, flap#, tally#:", self.wx_hold_count, self.wx_hold_tally)
                        #We choose to let the enclosure manager diecide it needs to re-open.
                else:
                    #Never release the THIRD  hold without some special high level intervention.
                    if not self.clamp_latch:
                        print('Sorry, Tobor is clamping enclosure shut for the night.')
                    self.clamp_latch = True
                    self.wx_clamp = True
    
                self.wx_hold_last_updated = time.time()
            return status
        
  

# Older MRC code


        # if not self.is_wema and self.site in ['mrc', 'mrc2']:   #THis code relates to MRC old weather 
        #     breakpoint()
        #     try:
        #         #breakpoint()
        #         # pass
        #         redis_monitor = eval(self.redis_server.get('<ptr-wx-1_state'))
        #         illum = float(redis_monitor["illum lux"])
        #         self.last_wx = redis_monitor
        #     except:
        #         print('Redis is not returning redis_monitor Data properly.')
        #         redis_monitor = self.last_wx
                
        #     try:
        #         illum, mag = self.astro_events.illuminationNow()
        #         illum = float(redis_monitor["illum lux"])
        #         if illum > 500:
        #             illum = int(illum)
        #         else:
        #             illum = round(illum, 3)
        #         #self.wx_is_ok = True
        #         self.temperature = float(redis_monitor["amb_temp C"])
        #         self.pressure = 978   #Mbar to mmHg  #THIS IS A KLUDGE
        #         status = {"temperature_C": float(redis_monitor["amb_temp C"]),
        #                   "pressure_mbar": 978.0,
        #                   "humidity_%": float(redis_monitor["humidity %"]),
        #                   "dewpoint_C": float(redis_monitor["dewpoint C"]),
        #                   "calc_HSI_lux": illum,
        #                   "sky_temp_C": float(redis_monitor["sky C"]),
        #                   "time_to_open_h": float(redis_monitor["time to open"]),
        #                   "time_to_close_h": float(redis_monitor["time to close"]),
        #                   "wind_m/s": float(redis_monitor["wind m/s"]),
        #                   "ambient_light": redis_monitor["light"],
        #                   "open_ok": redis_monitor["open_possible"],
        #                   "wx_ok": redis_monitor["open_possible"],
        #                   "meas_sky_mpsas": float(redis_monitor['meas_sky_mpsas']),
        #                   "calc_sky_mpsas": round((mag - 20.01), 2)
        #                   }
        #                         #Pulled over from saf
                                
                                
        #         uni_measure = float(redis_monitor['meas_sky_mpsas'])   #  Provenance of 20.01 is dubious 20200504 WER

        #         if uni_measure == 0:
        #             uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
        #             status["meas_sky_mpsas"] = uni_measure
        #             #status2["meas_sky_mpsas"] = uni_measure
        #             self.meas_sky_lux = illum
        #         else:
        #             self.meas_sky_lux = linearize_unihedron(uni_measure)
        #             status["meas_sky_mpsas"] = uni_measure
        #             #status2["meas_sky_mpsas"] = uni_measure
        #             # Only write when around dark, put in CSV format
        #             # sunZ88Op, sunZ88Cl, ephemNow = g_dev['obs'].astro_events.getSunEvents()
        #             # quarter_hour = 0.75/24    #  Note temp changed to 3/4 of an hour.
        #             # if  (sunZ88Op - quarter_hour < ephemNow < sunZ88Cl + quarter_hour) and (time.time() >= \
        #             #      self.sample_time + 30.):    #  Two samples a minute.
        #             #     try:
        #             #         wl = open('Q:/archive/wx_log.txt', 'a')
        #             #         wl.write('redis_monitor, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
        #             #                  + str(self.unihedron.SkyQuality) + ", \n")
        #             #         wl.close()
        #             #         self.sample_time = time.time()
        #             #     except:
        #             #         print("redis_monitor log did not write.")

        #         return status
        #     except:
        #         pass

                  # try:
            #     wx = open(self.config['wema_path'] + 'boltwood.txt', 'r')
            #     wx_line = wx.readline()
            #     wx.close
            #     #print(wx_line)
            #     wx_fields = wx_line.split()
            #     skyTemperature = float( wx_fields[4])
            #     temperature = f_to_c(float(wx_fields[5]))
            #     windspeed = round(float(wx_fields[7])/2.237, 2)
            #     humidity =  float(wx_fields[8])
            #     dewpoint = f_to_c(float(wx_fields[9]))
            #     timeSinceLastUpdate = wx_fields[13]
            #     open_ok = wx_fields[19]
            #     #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
            #     self.focus_temp = temperature
            #     self.temperature = temperature
            #     return
            # except:
            #     time.sleep(5)
            #     try:
            #         wx = open(self.config['wema_path'] + 'boltwood.txt', 'r')
            #         wx_line = wx.readline()
            #         wx.close
            #         #print(wx_line)
            #         wx_fields = wx_line.split()
            #         skyTemperature = float( wx_fields[4])
            #         temperature = f_to_c(float(wx_fields[5]))
            #         windspeed = round(float(wx_fields[7])/2.237, 2)
            #         humidity =  float(wx_fields[8])
            #         dewpoint = f_to_c(float(wx_fields[9]))
            #         timeSinceLastUpdate = wx_fields[13]
            #         open_ok = wx_fields[19]
            #         #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
            #         self.focus_temp = temperature
            #         self.temperature = temperature
            #         return
            #     except:
            #         print('Wema Weather source problem, 2nd try.')
            #         self.focus_temp = 10.
            #         self.temperature = 10.
            # illum, mag = self.astro_events.illuminationNow()
            # status = {"temperature_C": temperature,
            #         "pressure_mbar": 748,
            #         "humidity_%": humidity,
            #         "dewpoint_C": dewpoint,
            #         "calc_HSI_lux": illum,
            #         "sky_temp_C": skyTemperature,
            #         "time_to_open_h": 1.,
            #         "time_to_close_h": 8.,
            #         "wind_m/s": float(windspeed),
            #         "ambient_light": 77777,
            #         "open_ok": True,
            #         "wx_ok": True,
            #         "meas_sky_mpsas": 12.345,
            #         "calc_sky_mpsas": round((mag - 20.01), 2)
            #         }
            
            # #  Note we are still in saf specific site code.
            # if self.unihedron_connected:
            #     uni_measure = self.unihedron.SkyQuality   #  Provenance of 20.01 is dubious 20200504 WER
            #     if uni_measure == 0:
            #         uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
            #         status["meas_sky_mpsas"] = uni_measure
            #         #status2["meas_sky_mpsas"] = uni_measure
            #         self.meas_sky_lux = illum
            #     else:
            #         self.meas_sky_lux = linearize_unihedron(uni_measure)
            #         status["meas_sky_mpsas"] = uni_measure
            #         #status2["meas_sky_mpsas"] = uni_measure
            # else:
            #     status["meas_sky_mpsas"] = round((mag - 20.01),2)
            #     #status2["meas_sky_mpsas"] = round((mag - 20.01),2) #  Provenance of 20.01 is dubious 20200504 WER

            # # Only write when around dark, put in CSV format.  This is a logfile of the rapid sky brightness transition.
            # obs_win_begin, sunset, sunrise, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            # quarter_hour = 0.15/24
            # if  (obs_win_begin - quarter_hour < ephemNow < sunrise + quarter_hour) \
            #      and self.unihedron.Connected and (time.time() >= self.sample_time + 30.):    #  Two samples a minute.
            #     try:
            #         wl = open('C:/000ptr_saf/archive/wx_log.txt', 'a')   #  NB This is currently site specifc but in code w/o config.
            #         wl.write('wx, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
            #                  + str(self.unihedron.SkyQuality) + ", \n")
            #         wl.close()
            #         self.sample_time = time.time()
            #     except:
            #         pass
            #         #print("Wx log did not write.")
            # self.status = status
            



            
    def get_quick_status(self, quick):
        #  This method is used for annotating fits headers.
        # wx = eval(self.redis_server.get('<ptr-wx-1_state'))
        #  NB NB This routine does NOT update self.wx_ok
        #Above is cruft
        self.status = self.get_status(g_dev)  # Get current stat.
        #if self.site_is_proxy:
            #Need to get data for camera from redis.
        illum, mag = g_dev['evnt'].illuminationNow()
        # if self.config['site'] in ['fat']:
        #     wx = eval(self.redis_server.get('ocn_status')) 
        # else:
        #     try:
        #         wx = g_dev['ocn'].status
        #     except:
        #         wx = eval(self.redis_server.get('ocn_status'))   #NB NB NB This needs cleaning up.

        quick.append(time.time())
        quick.append(float(self.status['sky_temp_C']))
        quick.append(float(self.status['temperature_C']))
        quick.append(float(self.status['humidity_%']))
        quick.append(float(self.status['dewpoint_C']))
        quick.append(float(abs(self.status['wind_m/s'])))
        quick.append(float(self.status['pressure_mbar']))   # 20200329 a SWAG!
        quick.append(float(illum))     # Add Solar, Lunar elev and phase
        if self.unihedron_connected:
            uni_measure = 0#wx['meas_sky_mpsas']   #NB NB note we are about to average logarithums.
        else:
            uni_measure  = 0
        if uni_measure == 0:
            uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
            quick.append(float(uni_measure))
            self.meas_sky_lux = illum
        else:
            self.meas_sky_lux = linearize_unihedron(uni_measure)
            quick.append(float(self.meas_sky_lux))     # intended for Unihedron
        return quick
        
        # elif self.site == 'saf':  # This is the generic implementation of ocn-stat.
        #     # Should incorporate Davis data into this data set, and Unihedron.
        #     illum, mag = self.astro_events.illuminationNow()

        #     quick.append(time.time())
        #     quick.append(float(self.sky_monitor.SkyTemperature))
        #     quick.append(float(self.sky_monitor.Temperature))
        #     quick.append(float(self.sky_monitor.Humidity))
        #     quick.append(float(self.sky_monitor.DewPoint))
        #     quick.append(float(abs(self.sky_monitor.WindSpeed)))
        #     quick.append(float(784.0))   # 20200329 a SWAG!
        #     quick.append(float(illum))     # Add Solar, Lunar elev and phase
        #     if self.unihedron_connected:
        #         uni_measure = self.unihedron.SkyQuality
        #     else:
        #         uni_measure  = 0
        #     if uni_measure == 0:
        #         uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
        #         quick.append(float(uni_measure))
        #         self.meas_sky_lux = illum
        #     else:
        #         self.meas_sky_lux = linearize_unihedron(uni_measure)
        #         quick.append(float(self.meas_sky_lux))     # intended for Unihedron
        #     return quick
        # elif self.site in ['mrc', 'mrc2']:
        #     wx = eval(self.redis_server.get('<ptr-wx-1_state'))
        #     quick.append(time.time())
        #     quick.append(float(wx["sky C"]))
        #     quick.append(float(wx["amb_temp C"]))
        #     quick.append(float(wx["humidity %"]))
        #     quick.append(float(wx["dewpoint C"]))
        #     quick.append(float(wx["wind m/s"]))
        #     quick.append(float(973))   # 20200329 a SWAG!
        #     quick.append(float(wx['illum lux']))     # Add Solar, etc.
        #     quick.append(float(wx['bright hz']))

        # else:
        #     #print("Big fatal error in ocn quick status, site not supported.")
        #     quick = {}
        #     return quick
        
    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0])/2, 3))
        average.append(round((pre[1] + post[1])/2, 1))
        average.append(round((pre[2] + post[2])/2, 1))
        average.append(round((pre[3] + post[3])/2, 1))
        average.append(round((pre[4] + post[4])/2, 1))
        average.append(round((pre[5] + post[5])/2, 1))
        average.append(round((pre[6] + post[6])/2, 2))
        average.append(round((pre[7] + post[7])/2, 3))
        average.append(round((pre[8] + post[8])/2, 1))
        return average

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        if action is not None:
            pass
            #self.move_relative_command(req, opt)   ???
        else:
            print(f"Command <{action}> not recognized.")

    # ###################################
    #   Observing Conditions Commands  #
    # ###################################

    def empty_command(self, req: dict, opt: dict):
        ''' does nothing '''
        print(f"obseving conditions cmd: empty command")
        pass


if __name__ == '__main__':
    pass
