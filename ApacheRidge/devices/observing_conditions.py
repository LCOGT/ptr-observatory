
import win32com.client
import redis
import time
from global_yard import g_dev

#core1_redis.set('<ptr-wx-1_state', json.dumps(wx), ex=120)
#            core1_redis.get('<ptr-wx-1_state')
#            core1_redis = redis.StrictRedis(host='10.15.0.15', port=6379, db=0, decode_responses=True)

class ObservingConditions:

    def __init__(self, driver: str, name: str):
        self.name = name
        g_dev['ocn']=  self
        #breakpoint()
        #self.redis_server = redis.StrictRedis(host='10.15.0.15', port=6379, db=0, decode_responses=True)
        #self.observing_conditions = win32com.client.Dispatch(driver)
        self.observing_conditions_connected = True   #This is not an ASCOM device, so this is a bit bogus.
        print("observing_conditions:  Connected == True")

    def get_status(self):
# =============================================================================
#         try:
#             wx = eval(self.redis_server.get('<ptr-wx-1_state'))  #Redis returns a string dict.
#         except:
#             print('Redis is not returning Wx Data properly.')
# =============================================================================
        try:
            status = {"temperature":  '10.0',
                      "pressure": '900',
                      "humidity": '50',
                      "dewpoint": '5',
                      "calc_sky_lux":'0.002',
                      "sky_temp": '-40',
                      "time_to_open":  '2.0',
                      "time_to_close": '10.0',
                      "wind_km/h": '1.234',
                      "ambient_light":  'Dim',
                      "open_possible":  'true',
                      "brightness_hz":'2345'
                      }
# =============================================================================
#             status = {"temperature": wx["amb_temp C"],
#                       "pressure": ' ---- ',
#                       "humidity": wx["humidity %"],
#                       "dewpoint": wx["dewpoint C"],
#                       "calc_sky_lux": wx["illum lux"],
#                       "sky_temp": wx["sky C"],
#                       "time_to_open": wx["time to open"],
#                       "time_to_close": wx["time to close"],
#                       "wind_km/h": wx["wind k/h"],
#                       "ambient_light":  wx["light"],
#                       "open_possible":  wx["open_possible"],
#                       "brightness_hz": wx['bright hz']
#                       }
# =============================================================================
        except:
            time.sleep(1)
            try:
                wx = eval(self.redis_server.get('<ptr-wx-1_state'))  #Redis returns a string dict.
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

    def get_quick_status(self, quick):
        #wx = eval(self.redis_server.get('<ptr-wx-1_state'))
        quick.append(time.time())
        quick.append(float(-40))
        quick.append(float(10))
        quick.append(float(50))
        quick.append(float(6))
        quick.append(float(3.5))
        quick.append(float(970.0))
        quick.append(float(1234))     #Add Solar, Lunar elev and phase
        quick.append(float(4567))
        #print(quick)
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
            self.move_relative_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ####################################
    #   Observing Conditions Commands  #
    ####################################

    def empty_command(self, req: dict, opt: dict):
        ''' does nothing '''
        print(f"obseving conditions cmd: empty command")
        pass

if __name__ == '__main__':
    oc = ObservingConditions('redis', 'wx1')