# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

'''
The box with the Wx station needs to be enlarged slightly and painted refelctive
white.  It may need a fan but that is to be avoided. It needs to handle more
sensors.

The weather agent then gets reading from multiple places, with each processed
through an ax+b transformation.  In general  then if there are multiple inputs
we choose a sigma clipped mean as the reported value.

From this data we determine an OK to open condition that can source a signal
permitting the electtronics to open if so requested.  For this to work properly,
the code in this module must pulse a timer whihc will expire and close the
facility.  This is the Weather Heartbeat.  The Ok signal is bracketed by a
band of sun elev < 5 deg  so occasial early opens can happen without much 
difficulty.  Presuably we open only when we can take flats.

The logs will be kept on a groomed disk in the Wx station as well as replicated 
on the QNAP.

Vital for this to be useful is keeping a coordinated IR patch view of the 
Zenith during open conditions.

This subsystem also computes moving averages of various sorts nad publishes
the appropriate graphs in web-ready form.

We can start with a minumum number of sensors and augment as we expand.

Star counts make sense to log from the All sky. But the threshold is going to
vary with the sky and lunar illumination.


'''

import serial
#import codecs
import time
from  datetime import datetime
import json
import redis
from ptr_config import *
from ptr_events import *


core1_redis = redis.StrictRedis(host='10.15.0.109', port=6379, db=0)

#print("Starting Uni routine while loop.", c1r)
#t=datetime.now().isoformat()
#prior_mins = t[12:13]*60 + t[14:15]
#while True:
#    t=datetime.now().isoformat()
#    mins = t[12:13]*60 + t[14:15]
#    if mins == prior_mins:
#        continue
#    else:
#        prior_mins = mins
#            
#        l = []
#        uniFile = open('Q:\\unihedron1\\uniBright.txt', 'w')
#        uniLog = open('Q:\\unihedron1\\uniLog.txt', 'a')
#        uni = serial.Serial('COM13', 115200, timeout=2)
#        uni.reset_input_buffer()
#        uni.write(b'rx')
#        l = str(uni.readline()).split(',')
#        illum, mag =illuminationNow()
#        try:
#            bright = int(float(l[2][:-2]))
#        
#            uniString = (t[:21] + ', ' + str(l[2][:-2]) + ', ' + str(illum) \
#                          + ', ' + str(mag))
#            print(uniString)
#            try:
#                uniFile.write(uniString + '\n')
#            except:
#                pass
#            try:
#                uniLog.write(t[:21] + ', ' + str(l[2][:-2]) + ', ' + str(illum) \
#                             + ', ' + str(mag) + '\n')
#            except:
#                pass
#        except:
#            pass
#        uniFile.close()
#        uniLog.close()
#        uni.close()
#        try:
#            c1r.set('unihedron1', str(bright)+ ', ' + str(illum), ex=600)
#            print('c1r was updated.')
#        except:
#            print('c1r update failed.')
#        
#        if bright <= 500000:
#            time.sleep(30)
#        else:
#            time.sleep(300)
#uniFile.close()
#uniLog.close()
#uni.close() 

def main():
    ut = datetime.utcnow()
    jday_index = (ut.hour)*60 + ut.minute
    #getJulianDateTime()
    while True:
        ut = datetime.utcnow()
        jday_index_new = (ut.hour)*60 + ut.minute
        if jday_index_new == jday_index:
            time.sleep(5)
            t=datetime.now().isoformat()
            #print('Spinning')
            l = []
            uniFile = open('Q:\\unihedron1\\uniBright.txt', 'w')
            #uniLog = open('Q:\\unihedron1\\uniLog.txt', 'a')
            uni = serial.Serial('COM15', 115200, timeout=2)
            uni.reset_input_buffer()
            uni.write(b'rx')
            l = str(uni.readline()).split(',')
            print(l)
            uni.close()
            time.sleep(0.1)
            try:
                uni.close()
            except:
                pass
            illum, mag =illuminationNow()
            try:
                mpsas = round(float(l[1][:-2]),2)
                bright = int(float(l[2][:-2]))
            
                uniString = (t[:21] + ', ' + str(mpsas) + ', ' + str(l[2][:-2]) + ', ' + str(illum) \
                              + ', ' + str(mag))
                #print(uniString)
                try:
                    uniFile.write(uniString + '\n')
                except:
                    pass
            except:
                pass
            try:
                core1_redis.set('unihedron1', str(mpsas) + ', ' + str(bright) + ', ' + str(illum), ex=600)
                #print('core1_redis was updated.')

            except:
                pass
            try:
                core1_redis.set('unihedron1', str(mpsas) + ', ' +  str(bright) + ', ' + str(illum), ex=600)
                #print('core1_redis was updated.')
            except:
                print('core1_redis update failed.')
            continue
        else:
            jday_index = jday_index_new
            try:
                uni.close()
            except:
                pass
            try:
                uniFile.close()
            except:
                pass
            try:
                b1 = open('Q:\\boltwood1\\boltwood1.txt', 'r')
                b1l = b1.readline()
                b1.close()
            except:
                time.sleep(0.5)
                try:
                    b1 = open('Q:\\boltwood1\\boltwood1.txt', 'r')
                    b1l = b1.readline()
                    b1.close()
                except:
                    time.sleep(0.5)
                    try:
                        b1 = open('Q:\\boltwood1\\boltwood1.txt', 'r')
                        b1l = b1.readline()
                        b1.close()
                    except:
                        print('Three Boltwood tries failed.')
            try:
                s1 = open('Q:\\skyalert1\\skyalert1.txt', 'r')
                s1l = s1.readline()
                s1.close()
            except:
                time.sleep(0.5)
                try:
                    s1 = open('Q:\\skyalert1\\skyalert1.txt', 'r')
                    s1l = s1.readline()
                    s1.close()
                except:
                    time.sleep(0.5)
                    try:
                        s1 = open('Q:\\skyalert1\\skyalert1.txt', 'r')
                        s1l = s1.readline()
                        s1.close()
                    except:
                        print('Three Skyalert tries faild.')
            #sa = s1l.split(' ')
            #sa2 = sa[4]  + ', ' + sa[9] + sa[11]  + ', ' + sa[17]  + ', '  + sa[23]  + ', ' + sa[25]  + ', ' + sa[28]  + ', ' + sa[31]  
            #print(sa, str(sa2))
            wl = open('Q:\\wxlog\\wxlog.txt','a')
            wl.write(str(jday_index) + ', ' + b1l[0:102] + ', ' +s1l[0:104] + ', ' + str(bright )+ ', ' + str(illum) + ', ' + str(mpsas) +'\n')
            wl.close()
            line = b1l[0:102]
            line = line.split()
            #print(line)
            wx = {}
            if len(line) > 4 and line[2] == 'C' and line[3] == 'm':     #NB NB Danger is you change Boltwood to Faren or MPH, Kph
                sky = float(line[4])
                if sky < -70: sky = 5     #Eliminates -998 error value
                temp = float(line[5])
                wind = float(line[7])
                hum = float(line[8])
                dew = float(line[9])
                vl_l_d = int(line[-2])
                if temp >= 2 and hum <= 85 and sky <-8 and (temp - dew) > 2 and \
                   vl_l_d < 3 and wind < 12 and bright <= 213250 and (sunZ85Op - 5/1440 <= \
                   ephem.now() <= sunZ85Cl + 5/1440): 
                    open_possible = True
                    wx['open_possible'] = "Yes"
                else:
                    open_possible = False
                    wx['open_possible'] = "No"
                wx['timestamp'] = str(round(time.time(), 9))
#                wx['jYear'] = jYear
#                wx['JD'] = str(round(JD, 8))
                wx['sky C'] = str(sky)
                wx['amb_temp C'] = str(temp) 
                wx['humidity %'] = str(hum) 
                wx['dewpoint C'] = str(dew) 
                wx['wind m/s'] = str(wind)
                wx['meas_sky_mpsas'] = str(mpsas)
                wx['pressure mbar'] = str('----')
                wx['solar w/m^2'] = str('----')
                if vl_l_d == 0:
                    light_str = 'Uknown'
                elif vl_l_d == 1:
                    light_str = 'Dark'
                elif vl_l_d == 2:
                    light_str = 'Light'
                elif vl_l_d == 3:
                    light_str = 'Very Light'
                wx['light'] = light_str
                wx['bright hz'] = str(bright)
                wx['illum lux'] = str(illum)
                tt_open = round((sunZ85Op - ephem.now())*24, 2)
                tt_close = round((sunZ85Cl - ephem.now())*24,2)
                if tt_open >= 0:
                    wx['time to open'] = str(tt_open) 
                else:
                    wx['time to open'] = '0.0'
                if tt_close >= 0:
                    wx['time to close'] = str(tt_close)
                else:
                    wx['time to close'] = '0.0'
                print(open_possible, sky, temp, wind, hum, dew, vl_l_d, bright, \
                      sunZ85Op, ephem.now(), sunZ85Cl)
            else:
                open_possible = False
                wx['open_possible'] = "No" 
            core1_redis.set('<ptr-wx-1_state', json.dumps(wx), ex=300)
            
            print('Minute transition at  :', ut, jday_index_new, illum, mag)
            jday_index = jday_index_new
            
    


if __name__ == '__main__':
    print('Welcome to the Wx logger.')
    main()
