
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
        self.redis_server = redis.StrictRedis(host='10.15.0.15', port=6379, db=0, decode_responses=True)
        #self.observing_conditions = win32com.client.Dispatch(driver)
        #self.observing_conditions.Connected = True

        print(f"observing_conditions  connected")
        #print(self.observing_conditions.Description)

    def get_status(self):
        wx = eval(self.redis_server.get('<ptr-wx-1_state'))  #Redis returns a string dict.
        #print(wx)
        #breakpoint()
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
                      "ambient_light":  wx["light"],
                      "open_possible":  wx["open_possible"],
                      "brightness_hz": wx['bright hz']
                      }
        except:
            time.sleep(1)
            wx = eval(self.redis_server.get('<ptr-wx-1_state'))  #Redis returns a string dict.
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
        wx = eval(self.redis_server.get('<ptr-wx-1_state'))
        quick.append(time.time())
        quick.append(float(wx["sky C"]))
        quick.append(float(wx["amb_temp C"]))
        quick.append(float(wx["humidity %"]))
        quick.append(float(wx["dewpoint C"]))
        quick.append(float(wx["wind k/h"]))
        quick.append(float(970.0))
        quick.append(float(wx["illum lux"]))     #Add Solar, Lunar elev and phase
        quick.append(float(wx['bright hz']))
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