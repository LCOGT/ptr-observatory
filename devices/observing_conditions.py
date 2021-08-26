
import win32com.client
import redis
import time
import requests
import json
from global_yard import g_dev

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


def linearize_unihedron(uni_value):
    #  Based on 20080811 data
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
        
    
class ObservingConditions:

    def __init__(self, driver: str, name: str, config: dict, astro_events):

        self.name = name
        self.astro_events = astro_events
        g_dev['ocn'] = self
        self.site = config['site']
        self.config = config
        self.sample_time = 0
        self.ok_to_open = 'No'
        self.observing_condtions_message = '-'
        self.wx_is_ok = None
        self.wx_hold = False
        self.wx_hold_last_updated = time.time()   #This is meant for a stale check on the Wx hold report
        self.wx_hold_tally = 0
        self.wx_clamp = False
        self.clamp_latch = False
        self.wait_time = 0        #A countdown to re-open
        self.wx_close = False     #If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_hold_until_time = None
        self.wx_hold_count = 0     #if >=5 inhibits reopening for Wx
        self.wait_time = 0        #A countdown to re-open
        self.wx_close = False     #If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_system_enable = True   #Purely a debugging aid.
        self.wx_test_cycle = 0
        self.prior_status = None
        self.prior_status_2 = None
        self.wmd_fail_counter = 0
       
        redis_ip = config['redis_ip']
        if redis_ip is not None:           
            self.redis_server = redis.StrictRedis(host=redis_ip, port=6379, db=0,
                                              decode_responses=True)
            self.redis_wx_enabled = True
        else:
            self.redis_wx_enabled = False
        #    self.observing_conditions_connected = True
        #    print("observing_conditions: Redis connected = True")
        #  

        if self.site in ['simulate',  'dht']:  #DEH: added just for testing purposes with ASCOM simulators.
            self.observing_conditions_connected = True
            self.site_is_proxy = False
            print("observing_conditions: Simulator drivers connected True")
        elif not self.config['agent_wms_enc_active']:
            self.site_is_proxy = False
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
                self.unihedron_connected = False
                try:
                    driver = config['observing_conditions']['observing_conditions1']['uni_driver']
                    port = config['observing_conditions']['observing_conditions1']['unihedron_port']
                    self.unihedron = win32com.client.Dispatch(driver)
                    self.unihedron.Connected = True
                    self.unihedron_connected = True
                    print("observing_conditions: Unihedron connected = True, on COM" + str(port))
                except:
                    print("Unihedron on Port 10 is disconnected.  Observing will proceed.")
                    self.unihedron_connected = False
                    # NB NB if no unihedron is installed the status code needs to not report it.
        elif self.config['agent_wms_enc_active']:
            self.site_is_proxy = True

    def get_status(self):
        '''
        Regularly calling this routine returns weather status dict for AWS, evaluates the Wx 
        reporting and manages temporary closes, known as weather-holds.
        
        

        Returns
        -------
        status : TYPE
            DESCRIPTION.

        '''
        if self.site_is_proxy:

            return 

        elif self.site == 'saf':
            illum, mag = self.astro_events.illuminationNow()
            if illum > 100:
                illum = int(illum)
            self.calc_HSI_lux = illum
            # Here we add in-line  a preliminary OpenOK calculation:
            #  NB all parameters should come from config.
            dew_point_gap = not (self.sky_monitor.Temperature  - self.sky_monitor.DewPoint) < 2
            temp_bounds = not (self.sky_monitor.Temperature < -15) or (self.sky_monitor.Temperature > 35)
            wind_limit = self.sky_monitor.WindSpeed < 35/2.235   #sky_monitor reports m/s, Clarity may report in MPH
            sky_amb_limit  = self.sky_monitor.SkyTemperature < -20
            humidity_limit = 1 < self.sky_monitor.Humidity < 80
            rain_limit = self.sky_monitor.RainRate <= 0.001
          
            self.wx_is_ok = dew_point_gap and temp_bounds and wind_limit and sky_amb_limit and \
                            humidity_limit and rain_limit
            #  NB  wx_is_ok does not include ambient light or altitude of the Sun
            if self.wx_is_ok:
                wx_str = "Yes"
            else:
                wx_str = "No"   #Ideally we add the dominant reason in priority order.
            #The following may be more restictive since it includes local measured ambient light.
            #  This signal meant to simulate the sky_monitor relay output.  WE repport it but it is not
            #  actively used.
            if self.sky_monitor_oktoopen.IsSafe and dew_point_gap and temp_bounds:
                self.ok_to_open = 'Yes'
            else:
                self.ok_to_open = "No"
            try:   #sky_monitor cloud cover occasionally faults. 20200805 WER
            # Faults continuing but very rare.  20200909
                status = {}   #This code faults when Rain is reported the Cloudcover does not
                              #return properly
                status2 = {}
                self.temperature = self.sky_monitor.Temperature
                self.pressure = 784*0.750062   #Mbar to mmHg    Please use mbar going forward.
                status = {"temperature_C": round(self.sky_monitor.Temperature, 2),
                          "pressure_mbar": 784.,
                          "humidity_%": self.sky_monitor.Humidity,
                          "dewpoint_C": self.sky_monitor.DewPoint,
                          "sky_temp_C": round(self.sky_monitor.SkyTemperature,2),
                          "last_sky_update_s":  round(self.sky_monitor.TimeSinceLastUpdate('SkyTemperature'), 2),
                          "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                          'rain_rate': self.sky_monitor.RainRate,
                          'solar_flux_w/m^2': None,
                          'cloud_cover_%': str(self.sky_monitor.CloudCover),
                          "calc_HSI_lux": illum,
                          "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                          "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                          "open_ok": self.ok_to_open
                          #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
                          }
                status2 = {}
                status2 = {"temperature_C": round(self.sky_monitor.Temperature, 2),
                          "pressure_mbar": 784.0,
                          "humidity_%": self.sky_monitor.Humidity,
                          "dewpoint_C": self.sky_monitor.DewPoint,
                          "sky_temp_C": round(self.sky_monitor.SkyTemperature,2),
                          "last_sky_update_s":  round(self.sky_monitor.TimeSinceLastUpdate('SkyTemperature'), 2),
                          "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                          'rain_rate': self.sky_monitor.RainRate,
                          'solar_flux_w/m^2': 'NA',
                          #'cloud_cover_%': self.sky_monitor.CloudCover,
                          "calc_HSI_lux": illum,
                          "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                          "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                          "open_ok": self.ok_to_open
                          #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
                          }
                self.prior_status = status
                self.prior_status_2 = status2
                return status
            except:
                #  Note this is trying to deal with a failed sky_monitor report.
                
                try:
                    status = {}
                    status2 = {}
                    status = {"temperature_C": round(self.sky_monitor.Temperature, 2),
                          "pressure_mbar": 784.,
                              "humidity_%": self.sky_monitor.Humidity,
                              "dewpoint_C": self.sky_monitor.DewPoint,
                              "sky_temp_C": round(self.sky_monitor.SkyTemperature,2),
                              "last_sky_update_s":  round(self.sky_monitor.TimeSinceLastUpdate('SkyTemperature'), 2),
                              "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                              'rain_rate': self.sky_monitor.RainRate,
                              'solar_flux_w/m^2': None,
                              'cloud_cover_%': str(self.sky_monitor.CloudCover),
                              "calc_HSI_lux": illum,
                              "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                              "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                              "open_ok": self.ok_to_open
                              #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
                              }
                    status2 = {}
                    status2 = {"temperature_C": round(self.sky_monitor.Temperature, 2),
                              "pressure_mbar": 784.0,
                              "humidity_%": self.sky_monitor.Humidity,
                              "dewpoint_C": self.sky_monitor.DewPoint,
                              "sky_temp_C": round(self.sky_monitor.SkyTemperature,2),
                              "last_sky_update_s":  round(self.sky_monitor.TimeSinceLastUpdate('SkyTemperature'), 2),
                              "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                              'rain_rate': self.sky_monitor.RainRate,
                              'solar_flux_w/m^2': 'NA',
                              #'cloud_cover_%': self.sky_monitor.CloudCover,
                              "calc_HSI_lux": illum,
                              "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                              "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                              "open_ok": self.ok_to_open
                              #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
                              }
                    self.prior_status = status
                    self.prior_status_2 = status2
                    return status
                except:
                    self.prior_status = status
                    self.prior_status_2 = status2
                    return status
                
            #  Note we are still in saf specific site code.
            if self.unihedron_connected:
                uni_measure = self.unihedron.SkyQuality   #  Provenance of 20.01 is dubious 20200504 WER
                if uni_measure == 0:
                    uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
                    status["meas_sky_mpsas"] = uni_measure
                    status2["meas_sky_mpsas"] = uni_measure
                    self.meas_sky_lux = illum
                else:
                    self.meas_sky_lux = linearize_unihedron(uni_measure)
                    status["meas_sky_mpsas"] = uni_measure
                    status2["meas_sky_mpsas"] = uni_measure
            else:
                status["meas_sky_mpsas"] = round((mag - 20.01),2)
                status2["meas_sky_mpsas"] = round((mag - 20.01),2) #  Provenance of 20.01 is dubious 20200504 WER

            # Only write when around dark, put in CSV format.  This is a logfile of the rapid sky brightness transition.
            obs_win_begin, sunset, sunrise, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            quarter_hour = 0.15/24
            if  (obs_win_begin - quarter_hour < ephemNow < sunrise + quarter_hour) \
                 and self.unihedron.Connected and (time.time() >= self.sample_time + 30.):    #  Two samples a minute.
                try:
                    wl = open('C:/000ptr_saf/archive/wx_log.txt', 'a')   #  NB This is currently site specifc but in code w/o config.
                    wl.write('wx, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                             + str(self.unihedron.SkyQuality) + ", \n")
                    wl.close()
                    self.sample_time = time.time()
                except:
                    pass
                    #print("Wx log did not write.")
            self.status = status
            

        #  Note we are now in mrc specific code.

        elif self.site == 'mrc' or self.site == 'mrc2':
            try:
                #breakpoint()
                # pass
                redis_monitor = eval(self.redis_server.get('<ptr-wx-1_state'))
                illum = float(redis_monitor["illum lux"])
                self.last_wx = redis_monitor
            except:
                print('Redis is not returning redis_monitor Data properly.')
                redis_monitor = self.last_wx
                
            try:
                illum, mag = self.astro_events.illuminationNow()
                illum = float(redis_monitor["illum lux"])
                if illum > 500:
                    illum = int(illum)
                else:
                    illum = round(illum, 3)
                #self.wx_is_ok = True
                self.temperature = float(redis_monitor["amb_temp C"])
                self.pressure = 978   #Mbar to mmHg  #THIS IS A KLUDGE
                status = {"temperature_C": float(redis_monitor["amb_temp C"]),
                          "pressure_mbar": 978.0,
                          "humidity_%": float(redis_monitor["humidity %"]),
                          "dewpoint_C": float(redis_monitor["dewpoint C"]),
                          "calc_HSI_lux": illum,
                          "sky_temp_C": float(redis_monitor["sky C"]),
                          "time_to_open_h": float(redis_monitor["time to open"]),
                          "time_to_close_h": float(redis_monitor["time to close"]),
                          "wind_m/s": float(redis_monitor["wind m/s"]),
                          "ambient_light": redis_monitor["light"],
                          "open_ok": redis_monitor["open_possible"],
                          "wx_ok": redis_monitor["open_possible"],
                          "meas_sky_mpsas": float(redis_monitor['meas_sky_mpsas']),
                          "calc_sky_mpsas": round((mag - 20.01), 2)
                          }
                                #Pulled over from saf
                                
                                
                uni_measure = float(redis_monitor['meas_sky_mpsas'])   #  Provenance of 20.01 is dubious 20200504 WER

                if uni_measure == 0:
                    uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
                    status["meas_sky_mpsas"] = uni_measure
                    #status2["meas_sky_mpsas"] = uni_measure
                    self.meas_sky_lux = illum
                else:
                    self.meas_sky_lux = linearize_unihedron(uni_measure)
                    status["meas_sky_mpsas"] = uni_measure
                    #status2["meas_sky_mpsas"] = uni_measure
                    # Only write when around dark, put in CSV format
                    # sunZ88Op, sunZ88Cl, ephemNow = g_dev['obs'].astro_events.getSunEvents()
                    # quarter_hour = 0.75/24    #  Note temp changed to 3/4 of an hour.
                    # if  (sunZ88Op - quarter_hour < ephemNow < sunZ88Cl + quarter_hour) and (time.time() >= \
                    #      self.sample_time + 30.):    #  Two samples a minute.
                    #     try:
                    #         wl = open('Q:/archive/wx_log.txt', 'a')
                    #         wl.write('redis_monitor, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                    #                  + str(self.unihedron.SkyQuality) + ", \n")
                    #         wl.close()
                    #         self.sample_time = time.time()
                    #     except:
                    #         print("redis_monitor log did not write.")

                return status
            except:
                pass
            # Only write when around dark, put in CSV format, used to calibrate Unihedron.
            sunZ88Op, sunZ88Cl, sunrise, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            two_hours = 2/24    #  Note changed to 2 hours.
            if  (sunZ88Op - two_hours < ephemNow < sunZ88Cl + two_hours) and (time.time() >= \
                 self.sample_time + 30.):    #  Two samples a minute.
                try:
                    wl = open('C:/Users/me/Desktop/Work/ptr/wx_log.txt', 'a')
                    # wl.write('redis_monitor, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                    #          + str(self.unihedron.SkyQuality) + ", \n")
                    wl.close()
                    self.sample_time = time.time()
                except:
                    print("redis_monitor log did not write.")
        else:
            #DEH temporary to get past the big fatal error.
            #DEH is this always going to be very site specific or put in a config somewhere?
            pass
            #breakpoint()
            #print("Big fatal error in observing conditons")


        if not self.site_is_proxy:
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
            
            #OLD CODE USED A PROBE. jUST DO THIS EVERY CYCLE
    
                
            #self.wx_is_ok = False 
            breakpoint()
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
             
            #DEH: commented tihs out as not needed and causes errors for testing.    
            #This should be located right after forming the wx status
            #url = "https://api.photonranch.org/api/weather/write"
            #data = json.dumps({
            #    "weatherData": status,
            #    "site": self.site,
            #    "timestamp_s": int(time.time())
            #    })
            #try:
            #    requests.post(url, data)
            #except:
            #    print("Wx post failed, usually not a fatal error, probably site not supported")
            #return status
            
    def get_proxy_temp_press(self):
        if self.site_is_proxy:
            try:
                wx = eval(self.redis_server.get('wx_redis_status'))
                self.temperature = float(wx['temperature_C'])
                self.pressure = float(wx['pressure_mbar'])
            except:
                print('Proxy temp, pressure did not work')
                self.temperature = 20.0
                self.pressure = 875.0    #Half of MRC and SAF

            
    def get_quick_status(self, quick):
        #  This method is used for annotating fits headers.
        # wx = eval(self.redis_server.get('<ptr-wx-1_state'))

        #  NB NB This routine does NOT update self.wx_ok

        if self.site_is_proxy:
            #Need to get data for camera from redis.
            illum, mag = self.astro_events.illuminationNow()
            if illum <= 7500.:
                open_poss = True
                hz = 100000
            else:
                open_poss = False
                hz = 500000
            wx = eval(self.redis_server.get('wx_redis_status'))

            quick.append(time.time())
            quick.append(float(wx['sky_temp_C']))
            quick.append(float(wx['temperature_C']))
            quick.append(float(wx['humidity_%']))
            quick.append(float(wx['dewpoint_C']))
            quick.append(float(abs(wx['wind_m/s'])))
            quick.append(float(wx['pressure_mbar']))   # 20200329 a SWAG!
            quick.append(float(illum))     # Add Solar, Lunar elev and phase
            if True:  #self.unihedron_connected:
                uni_measure = wx['meas_sky_mpsas']
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
        
        elif self.site == 'saf':
            # Should incorporate Davis data into this data set, and Unihedron.
            illum, mag = self.astro_events.illuminationNow()
            if illum <= 7500.:
                open_poss = True
                hz = 100000
            else:
                open_poss = False
                hz = 500000
            quick.append(time.time())
            quick.append(float(self.sky_monitor.SkyTemperature))
            quick.append(float(self.sky_monitor.Temperature))
            quick.append(float(self.sky_monitor.Humidity))
            quick.append(float(self.sky_monitor.DewPoint))
            quick.append(float(abs(self.sky_monitor.WindSpeed)))
            quick.append(float(784.0))   # 20200329 a SWAG!
            quick.append(float(illum))     # Add Solar, Lunar elev and phase
            if self.unihedron_connected:
                uni_measure = self.unihedron.SkyQuality
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
        elif self.site in ['mrc', 'mrc2']:
            wx = eval(self.redis_server.get('<ptr-wx-1_state'))
            quick.append(time.time())
            quick.append(float(wx["sky C"]))
            quick.append(float(wx["amb_temp C"]))
            quick.append(float(wx["humidity %"]))
            quick.append(float(wx["dewpoint C"]))
            quick.append(float(wx["wind m/s"]))
            quick.append(float(973))   # 20200329 a SWAG!
            quick.append(float(wx['illum lux']))     # Add Solar, etc.
            quick.append(float(wx['bright hz']))

        else:
            #print("Big fatal error in ocn quick status, site not supported.")
            quick = {}
            return quick
        
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
