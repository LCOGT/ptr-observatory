
import win32com.client
import redis
import time
from global_yard import g_dev

#  core1_redis.set('<ptr-wx-1_state', json.dumps(wx), ex=120)
#            core1_redis.get('<ptr-wx-1_state')
#            core1_redis = redis.StrictRedis(host='10.15.0.15', port=6379, db=0,\
#                                            decode_responses=True)


class ObservingConditions:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        g_dev['ocn'] = self
        self.site = config['site']
        self.sample_time = 0
        self.ok_to_open = 'No'
        if self.site == 'wmd':
            self.redis_server = redis.StrictRedis(host='10.15.0.15', port=6379, db=0,
                                                  decode_responses=True)
            self.observing_conditions_connected = True
            print("observing_conditions: Redis connected = True")
        else:
            win32com.client.pythoncom.CoInitialize()
            self.boltwood = win32com.client.Dispatch(driver)
            self.boltwood.connected = True   # This is not an ASCOM device.
            port =config['observing_conditions']['observing_conditions1']['unihedron'].lower()
            driver_2 = config['observing_conditions']['observing_conditions1']['driver_2']
            self.boltwood_oktoopen = win32com.client.Dispatch(driver_2)
            self.boltwood_oktoopen.Connected = True
            driver_3 = config['observing_conditions']['observing_conditions1']['driver_3']
            self.boltwood_oktoimage = win32com.client.Dispatch(driver_3)
            self.boltwood_oktoimage.Connected = True
            print("observing_conditions: Boltwood connected = True")
            if port != 'false':
                driver = config['observing_conditions']['observing_conditions1']['uni_driver']
                self.unihedron = win32com.client.Dispatch(driver)
                self.unihedron.Connected = True
                print("observing_conditions: Unihedron connected = True, on COM" + str(port))


    def get_status(self):
        if self.site == 'saf':
            illum, mag = self.astro_events.illuminationNow()
            if illum > 500:
                illum = int(illum)
            # Here we add in-line (To be changed) a preliminary OpenOK calculation:
            dew_point_gap = not (self.boltwood.Temperature  - self.boltwood.DewPoint) < 2
            temp_bounds = not (self.boltwood.Temperature < 2.0) or (self.boltwood.Temperature > 35)
            # Many other gates can be here.
            if self.boltwood_oktoopen.IsSafe and dew_point_gap and temp_bounds:
                self.ok_to_open = 'Yes'
            else:
                self.ok_to_open = "No"
            status = {"temperature_C": str(round(self.boltwood.Temperature, 2)),
                      "pressure_mbar": str(784.0),
                      "humidity_%": str(self.boltwood.Humidity),
                      "dewpoint_C": str(self.boltwood.DewPoint),
                      "sky_temp_C": str(round(self.boltwood.SkyTemperature,2)),
                      "last_sky_update_s":  str(round(self.boltwood.TimeSinceLastUpdate('SkyTemperature'), 2)),
                      "wind_m/s": str(abs(round(self.boltwood.WindSpeed, 2))),
                      'rain_rate': str(self.boltwood.RainRate),
                      'solar_flux_w/m^2': 'NA',
                      'cloud_cover_%': str(self.boltwood.CloudCover),
                      "calc_sky_lux": str(illum),
                      "calc_HSI_lux": str(illum),
                      "calc_sky_mpsas": str(mag - 20.01),
                      "meas_sky_mpsas":  str(self.unihedron.SkyQuality),
                      "wx_ok": str(self.boltwood_oktoimage.IsSafe),
                      "open_ok": str(self.ok_to_open)
                      #"image_ok": str(self.boltwood_oktoimage.IsSafe)
                      }



            # Only write when around dark, put in CSV format
            sunZ88Op, sunZ88Cl, ephemNow = g_dev['obs'].astro_events.getSunEvents()
            quarter_hour = 0.75/24    #  Note temp changed to 3/4 of an hour.
            if  (sunZ88Op - quarter_hour < ephemNow < sunZ88Cl + quarter_hour) and (time.time() >= \
                 self.sample_time + 30.):    #  Two samples a minute.
                try:
                    wl = open('D:/archive/wx_log.txt', 'a')
                    wl.write('wx, ' + str(time.time()) + ', ' + str(illum) + ', ' + str(mag - 20.01) + ', ' \
                             + str(self.unihedron.SkyQuality) + ", \n")
                    wl.close()
                    self.sample_time = time.time()
                except:
                    print("Wx log did not write.")



            return status
        elif self.site == 'wmd':

            try:
                wx = eval(self.redis_server.get('<ptr-wx-1_state'))
            except:
                print('Redis is not returning Wx Data properly.')
            try:
                status = {"temperature_C": wx["amb_temp C"],
                          "pressur_mbar": '978',
                          "humidity_5": wx["humidity %"],
                          "dewpoint_C": wx["dewpoint C"],
                          "calc_sky_lux": wx["illum lux"],
                          "sky_temp_C": wx["sky C"],
                          "time_to_open": wx["time to open"],
                          "time_to_close": wx["time to close"],
                          "wind_km/h": wx["wind k/h"],
                          "ambient_light": wx["light"],
                          "open_ok": wx["open_possible"],
                          "wx_ok": wx["open_possible"],
                          "meas_sky_mpsas": wx['bright hz']
                          }
                breakpoint()


            except:
                time.sleep(1)
                # This is meant to be a retry
                try:
                    wx = eval(self.redis_server.get('<ptr-wx-1_state'))
                except:
                    print('Redis is not turning Wx Data properly.')
                status = {"temperature": wx["amb_temp C"],
                          "pressure": ' ---- ',
                          "humidity": wx["humidity %"],
                          "dewpoint": wx["dewpoint C"],
                          "calc_sky_lux": wx["illum lux"],
                          "sky_temp": wx["sky C"],
                          "time_to_open": wx["time to open"],
                          "time_to_close": wx["time to close"],
                          "wind_km/h": wx["wind k/h"],
                          "ambient_light":  wx["light"],
                          "open_possible":  wx["open_possible"],
                          "brightness_hz": wx['bright hz']
                          }
            return status
        else:
            print("Big fatal error")

    def get_quick_status(self, quick):
        # wx = eval(self.redis_server.get('<ptr-wx-1_state'))

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
            quick.append(float(self.unihedron.SkyQuality))     # intended for Unihedron
            # print(quick)
            return quick
        elif self.site == 'wmd':
            wx = eval(self.redis_server.get('<ptr-wx-1_state'))
            quick.append(time.time())
            quick.append(float(wx["sky C"]))
            quick.append(float(wx["amb_temp C"]))
            quick.append(float(wx["humidity %"]))
            quick.append(float(wx["dewpoint C"]))
            quick.append(float(wx["wind k/h"]))
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
