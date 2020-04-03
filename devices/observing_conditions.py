
import win32com.client
import redis
import time
from global_yard import g_dev
import ptr_events

#  core1_redis.set('<ptr-wx-1_state', json.dumps(wx), ex=120)
#            core1_redis.get('<ptr-wx-1_state')
#            core1_redis = redis.StrictRedis(host='10.15.0.15', port=6379, db=0,\
#                                            decode_responses=True)


class ObservingConditions:

    def __init__(self, driver: str, name: str, config):
        self.name = name
        g_dev['ocn'] = self
        self.site = config['site']
        if self.site == 'wmd':
            self.redis_server = redis.StrictRedis(host='10.15.0.15', port=6379, db=0,
                                                  decode_responses=True)
            self.observing_conditions_connected = True
            print("observing_conditions: Redis connected = True")
        else:
            win32com.client.pythoncom.CoInitialize()
            self.boltwood = win32com.client.Dispatch(driver)
            self.boltwood.connected = True   # This is not an ASCOM device.
            print("observing_conditions: Boltwood connected = True")

    def get_status(self):

        if self.site == 'saf':
            illum, mag = ptr_events.illuminationNow()
            if illum <= 7500.:
                open_poss = 'true'
                hz = 100000
            else:
                open_poss = 'false'
                hz = 500000

            status = {"temperature": str(self.boltwood.Temperature),
                      "pressure": str(784),
                      "humidity": str(self.boltwood.Humidity),
                      "dewpoint": str(self.boltwood.DewPoint),
                      "calc_sky_lux": str(illum),
                      "sky_temp": str(self.boltwood.SkyTemperature),
                      "wind_km/h": str(abs(self.boltwood.WindSpeed)),
                      'rain_rate': str(self.boltwood.RainRate),
                      "ambient_light": str(illum),
                      "sky-mag_asec^2": str(mag),
                      "open_possible": open_poss,
                      "brightness_hz": str(hz)
                      }
            return status
        elif self.site == 'wmd':

            try:
                wx = eval(self.redis_server.get('<ptr-wx-1_state'))
            except:
                print('Redis is not returning Wx Data properly.')
            try:
                status = {"temperature": wx["amb_temp C"],
                          "pressure": ' ---- ',
                          "humidity": wx["humidity %"],
                          "dewpoint": wx["dewpoint C"],
                          "calc_sky_lux": wx["illum lux"],
                          "sky_temp": wx["sky C"],
                          "time_to_open": wx["time to open"],
                          "time_to_close": wx["time to close"],
                          "wind_km/h": wx["wind k/h"],
                          "ambient_light": wx["light"],
                          "open_possible": wx["open_possible"],
                          "brightness_hz": wx['bright hz']
                          }

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
            illum, mag = ptr_events.illuminationNow()
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
            quick.append(float(hz))     # intended for Unihedron
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
