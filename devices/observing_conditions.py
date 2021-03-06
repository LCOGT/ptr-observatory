
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

#  core1_redis.set('<ptr-wx-1_state', json.dumps(wx), ex=120)
#            core1_redis.get('<ptr-wx-1_state')
#            core1_redis = redis.StrictRedis(host='10.15.0.109', port=6379, db=0,\
#                                            decode_responses=True)

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
        self.wx_test = False    #Purely a debugging aid.
        self.wx_test_cycle = 0
        self.prior_status = None
        self.prior_status_2 = None
        self.wmd_fail_counter = 0
        if self.site in ['wmd', 'wmd2']:
            self.redis_server = redis.StrictRedis(host='10.15.0.109', port=6379, db=0,
                                                  decode_responses=True)
            self.observing_conditions_connected = True
            print("observing_conditions: Redis connected = True")
        else:
            win32com.client.pythoncom.CoInitialize()
            self.boltwood = win32com.client.Dispatch(driver)
            self.boltwood.connected = True   # This is not an ASCOM device.
            driver_2 = config['observing_conditions']['observing_conditions1']['driver_2']
            self.boltwood_oktoopen = win32com.client.Dispatch(driver_2)
            self.boltwood_oktoopen.Connected = True
            driver_3 = config['observing_conditions']['observing_conditions1']['driver_3']
            self.boltwood_oktoimage = win32com.client.Dispatch(driver_3)
            self.boltwood_oktoimage.Connected = True
            print("observing_conditions: Boltwood connected = True")
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


    def get_status(self):
        '''
        Regularly calling this routine returns weather status dict for AWS, evaluates the Wx 
        reporting and manages temporary closes, known as weather-holds.
        
        

        Returns
        -------
        status : TYPE
            DESCRIPTION.

        '''

        if self.site == 'saf':
            illum, mag = self.astro_events.illuminationNow()
            if illum > 500:
                illum = int(illum)
            # Here we add in-line (To be changed) a preliminary OpenOK calculation:
            #  NB all parameters should come from config.
            dew_point_gap = not (self.boltwood.Temperature  - self.boltwood.DewPoint) < 2
            temp_bounds = not (self.boltwood.Temperature < -15) or (self.boltwood.Temperature > 35)
            wind_limit = self.boltwood.WindSpeed < 35/2.235   #Boltwood reports m/s, Clarity may report in MPH
            sky_amb_limit  = self.boltwood.SkyTemperature < -30
            humidity_limit = 1 < self.boltwood.Humidity < 80
            rain_limit = self.boltwood.RainRate <= 0.001
            self.wx_is_ok = dew_point_gap and temp_bounds and wind_limit and sky_amb_limit and \
                            humidity_limit and rain_limit
            #  NB  wx_is_ok does not include ambient light or altitude of the Sun
            if self.wx_is_ok:
                wx_str = "Yes"
            else:
                wx_str = "No"   #Ideally we add the dominant reason in priority order.
            #The following may be more restictive since it includes local measured ambient light.
            #  This signal meant to simulate the Boltwood relay output.
            if self.boltwood_oktoopen.IsSafe and dew_point_gap and temp_bounds:
                self.ok_to_open = 'Yes'
            else:
                self.ok_to_open = "No"
            try:   #Boltwood cloud cover occasionally faults. 20200805 WER
            # Faults continuing but very rare.  20200909
                status = {}   #This code faults when Rain is reported the Cloudcover does not
                              #return properly
                status2 = {}
                status = {"temperature_C": round(self.boltwood.Temperature, 2),
                          "pressure_mbar": 784.,
                          "humidity_%": self.boltwood.Humidity,
                          "dewpoint_C": self.boltwood.DewPoint,
                          "sky_temp_C": round(self.boltwood.SkyTemperature,2),
                          "last_sky_update_s":  round(self.boltwood.TimeSinceLastUpdate('SkyTemperature'), 2),
                          "wind_m/s": abs(round(self.boltwood.WindSpeed, 2)),
                          'rain_rate': self.boltwood.RainRate,
                          'solar_flux_w/m^2': None,
                          'cloud_cover_%': str(self.boltwood.CloudCover),
                          "calc_HSI_lux": illum,
                          "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                          "wx_ok": wx_str,  #str(self.boltwood_oktoimage.IsSafe),
                          "open_ok": self.ok_to_open
                          #"image_ok": str(self.boltwood_oktoimage.IsSafe)
                          }
                status2 = {}
                status2 = {"temperature_C": round(self.boltwood.Temperature, 2),
                          "pressure_mbar": 784.0,
                          "humidity_%": self.boltwood.Humidity,
                          "dewpoint_C": self.boltwood.DewPoint,
                          "sky_temp_C": round(self.boltwood.SkyTemperature,2),
                          "last_sky_update_s":  round(self.boltwood.TimeSinceLastUpdate('SkyTemperature'), 2),
                          "wind_m/s": abs(round(self.boltwood.WindSpeed, 2)),
                          'rain_rate': self.boltwood.RainRate,
                          'solar_flux_w/m^2': 'NA',
                          #'cloud_cover_%': self.boltwood.CloudCover,
                          "calc_HSI_lux": illum,
                          "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                          "wx_ok": wx_str,  #str(self.boltwood_oktoimage.IsSafe),
                          "open_ok": self.ok_to_open
                          #"image_ok": str(self.boltwood_oktoimage.IsSafe)
                          }
                self.prior_status = status
                self.prior_status_2 = status2
            except:
                #  Note this is trying to deal with a failed Boltwood report.
                
                try:
                    status = {}
                    status2 = {}
                    status = {"temperature_C": round(self.boltwood.Temperature, 2),
                          "pressure_mbar": 784.,
                              "humidity_%": self.boltwood.Humidity,
                              "dewpoint_C": self.boltwood.DewPoint,
                              "sky_temp_C": round(self.boltwood.SkyTemperature,2),
                              "last_sky_update_s":  round(self.boltwood.TimeSinceLastUpdate('SkyTemperature'), 2),
                              "wind_m/s": abs(round(self.boltwood.WindSpeed, 2)),
                              'rain_rate': self.boltwood.RainRate,
                              'solar_flux_w/m^2': None,
                              'cloud_cover_%': str(self.boltwood.CloudCover),
                              "calc_HSI_lux": illum,
                              "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                              "wx_ok": wx_str,  #str(self.boltwood_oktoimage.IsSafe),
                              "open_ok": self.ok_to_open
                              #"image_ok": str(self.boltwood_oktoimage.IsSafe)
                              }
                    status2 = {}
                    status2 = {"temperature_C": round(self.boltwood.Temperature, 2),
                              "pressure_mbar": 784.0,
                              "humidity_%": self.boltwood.Humidity,
                              "dewpoint_C": self.boltwood.DewPoint,
                              "sky_temp_C": round(self.boltwood.SkyTemperature,2),
                              "last_sky_update_s":  round(self.boltwood.TimeSinceLastUpdate('SkyTemperature'), 2),
                              "wind_m/s": abs(round(self.boltwood.WindSpeed, 2)),
                              'rain_rate': self.boltwood.RainRate,
                              'solar_flux_w/m^2': 'NA',
                              #'cloud_cover_%': self.boltwood.CloudCover,
                              "calc_HSI_lux": illum,
                              "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                              "wx_ok": wx_str,  #str(self.boltwood_oktoimage.IsSafe),
                              "open_ok": self.ok_to_open
                              #"image_ok": str(self.boltwood_oktoimage.IsSafe)
                              }
                    self.prior_status = status
                    self.prior_status_2 = status2
                except:
                    self.prior_status = status
                    self.prior_status_2 = status2
                
            #  Note we are still is saf specific site code.
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
            
        #  Note we are now in WMD specific code.
        elif self.site == 'wmd' or self.site == 'wmd2':
            
            try:
                #breakpoint()
                # pass
                wx = eval(self.redis_server.get('<ptr-wx-1_state'))
                illum = float(wx["illum lux"])
                self.last_wx = wx
            except:
                print('Redis is not returning Wx Data properly.')
                wx = self.last_wx
                
            try:
                illum, mag = self.astro_events.illuminationNow()
                illum = float(wx["illum lux"])
                if illum > 500:
                    illum = int(illum)
                else:
                    illum = round(illum, 3)
                self.wx_is_ok = True
                status = {"temperature_C": float(wx["amb_temp C"]),
                          "pressure_mbar": 978.0,
                          "humidity_%": float(wx["humidity %"]),
                          "dewpoint_C": float(wx["dewpoint C"]),
                          "calc_HSI_lux": illum,
                          "sky_temp_C": float(wx["sky C"]),
                          "time_to_open_h": float(wx["time to open"]),
                          "time_to_close_h": float(wx["time to close"]),
                          "wind_m/s": float(wx["wind m/s"]),
                          "ambient_light": wx["light"],
                          "open_ok": wx["open_possible"],
                          "wx_ok": wx["open_possible"],
                          "meas_sky_mpsas": float(wx['meas_sky_mpsas']),
                          "calc_sky_mpsas": round((mag - 20.01), 2)
                          }
                                #Pulled over from saf
                uni_measure = float(wx['meas_sky_mpsas'])   #  Provenance of 20.01 is dubious 20200504 WER

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
                #         wl.write('wx, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                #                  + str(self.unihedron.SkyQuality) + ", \n")
                #         wl.close()
                #         self.sample_time = time.time()
                #     except:
                #         print("Wx log did not write.")

                #return status
            except:
                pass
                # time.sleep(1)
                # self.wmd_fail_counter += 1
                # # This is meant to be a retry
                # try:
                #     #breakpoint()
                #     #pass
                #     wx = eval(self.redis_server.get('<ptr-wx-1_state'))
                #     illum = float(wx["illum lux"])
                #     self.last_wx = wx
                # except:
                #     print('Redis is not turning Wx Data properly.')
                #     wx = self.last_wx
                # status = {"temperature_C": float(wx["amb_temp C"]),
                #           "pressure_mbar": 978.0,
                #           "humidity_%": float(wx["humidity %"]),
                #           "dewpoint_C": float(wx["dewpoint C"]),
                #           "calc_HSI_lux": illum,
                #           "sky_temp_C": float(wx["sky C"]),
                #           "time_to_open_h": float(wx["time to open"]),
                #           "time_to_close_h": float(wx["time to close"]),
                #           "wind_m/s": float(wx["wind m/s"]),
                #           "ambient_light": wx["light"],
                #           "open_ok": wx["open_possible"],
                #           "wx_ok": wx["open_possible"],
                #           "meas_sky_mpsas": float(wx['meas_sky_mpsas']),
                #           "calc_sky_mpsas": round((mag - 20.01), 2)
                #           }
                # #Pulled over from saf
                # breakpoint()
                # uni_measure = float(wx['meas_sky_mpsas']) #  Provenance of 20.01 is dubious 20200504 WER
                # if uni_measure == 0:
                #     uni_measure = round((mag - 20.01),2)   #  Fixes Unihedron when sky is too bright
                #     status["meas_sky_mpsas"] = uni_measure
                #     #status2["meas_sky_mpsas"] = uni_measure
                #     self.meas_sky_lux = illum
                # else:
                #     self.meas_sky_lux = linearize_unihedron(uni_measure)
                #     status["meas_sky_mpsas"] = uni_measure
                #     #status2["meas_sky_mpsas"] = uni_measure

                        # Only write when around dark, put in CSV format
            #ops_win_begin, sunset, sunrise, ephem.now
            sunZ88Op, sunZ88Cl, sunrise, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            two_hours = 2/24    #  Note changed to 2 hours.
            if  (sunZ88Op - two_hours < ephemNow < sunZ88Cl + two_hours) and (time.time() >= \
                 self.sample_time + 30.):    #  Two samples a minute.
                try:
                    wl = open('Q:/archive/wx_log.txt', 'a')
                    # wl.write('wx, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                    #          + str(self.unihedron.SkyQuality) + ", \n")
                    wl.close()
                    self.sample_time = time.time()
                except:
                    print("Wx log did not write.")
        else:
            print("Big fatal error")

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
        self.wx_test_trigger = False
        if self.wx_test:
            self.wx_test_cycle += 1  #This just counts up.
            if self.wx_test_cycle % 10:
                self.wx_test_trigger = True
            
            
        
        if (self.wx_is_ok and not self.wx_test) and not self.wx_hold:     #Normal condition, possibly nothing to do.
            self.wx_hold_last_updated = time.time()

        elif (not self.wx_is_ok or self.wx_test_trigger) and not self.wx_hold:     #Wx bad and no hold yet.
            #Bingo we need to start a cycle
            self.wx_hold = True
            if self.wx_test:
                self.wx_hold_until_time = time.time() + 20    #20 seconds
            else:
                self.wx_hold_until_time = time.time() + 900    #15 minutes  This could be changed if open_ok.
            self.wx_hold_tally += 1     #  This counts all day and night long.
            self.wx_hold_last_updated = time.time()
            if obs_win_begin <= ephemNow <= sunrise:     #Gate the real holds to be in the Observing window.
                self.wx_hold_count += 1
                #We choose to let the enclosure manager handle the close.
                print("Wx hold asserted, flap#:", self.wx_hold_count, self.wx_hold_tally)
            else:
                print("Wx Hold -- out of Observing window.")
                
 

        elif (not self.wx_is_ok or self.wx_test) and self.wx_hold:     #WX is bad and we are on hold.
            self.wx_hold_last_updated = time.time()
            #Stay here as long as we need to. 
            if self.wx_test:
                print("In a wx_test hold.")
        else:
            pass

        if (self.wx_is_ok or self.wx_test) and self.wx_hold:     #Wx now good and still on hold.
            if self.wx_hold_count < 3:
                if time.time() >= self.wx_hold_until_time:
                    #Time to release the hold.
                    self.wx_hold = False
                    self.wx_hold_until_time = time.time()
                    self.wx_hold_last_updated = time.time()
                    print("Wx hold released, flap#, tally#:", self.wx_hold_count, self.wx_hold_tally)
                    #We choose to let the enclosure manager discover it can re-open.
            else:
                #Never release the hold without some special high level intervention.
                if not self.clamp_latch:
                    print('Sorry, Tobor is clamping enclosure shut for the night.')
                self.clamp_latch = True
                self.wx_clamp = True

            self.wx_hold_last_updated = time.time()
            
        #This should be located right after forming the wx status
        url = "https://api.photonranch.org/api/weather/write"
        data = json.dumps({
            "weatherData": status,
            "site": self.site,
            "timestamp_s": int(time.time())
            })
        try:
            requests.post(url, data)
        except:
            print("Wx post failed.")
        return status


    def get_quick_status(self, quick):
        #  This method is used for annotating fits headers.
        # wx = eval(self.redis_server.get('<ptr-wx-1_state'))

        #  NB NB This routine does NOT update self.wx_ok

        if self.site == 'saf':
            # Should incorporate Davis data into this data set, and Unihedron.
            illum, mag = self.astro_events.illuminationNow()
            if illum <= 7500.:
                open_poss = True
                hz = 100000
            else:
                open_poss = False
                hz = 500000
            quick.append(time.time())
            quick.append(float(self.boltwood.SkyTemperature))
            quick.append(float(self.boltwood.Temperature))
            quick.append(float(self.boltwood.Humidity))
            quick.append(float(self.boltwood.DewPoint))
            quick.append(float(abs(self.boltwood.WindSpeed)))
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
        elif self.site == 'wmd':
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
            print("Big fatal error")

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
            self.move_relative_command(req, opt)
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
