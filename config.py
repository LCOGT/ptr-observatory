# -*- coding: utf-8 -*-
'''
Created on Fri Aug  2 11:57:41 2019
Updates 20220107 20:01 WER
l
@author: wrosing
'''
import json
import sys
import time

'''
Ports.txt
Tested 202009
25  
COM8    SkyRoof
COM9    PWI4
COM10   PWI4
COM11   Dew Heater
COM12   EFA
COM13   Alnitak Screen
COM14  	Gemini
COM15   Darkslide
COM16   Camera Peg
        Pwr 1  FLI unPlug
        Pwr 2
        Pwr 3
        Pwr 4   Cam and filters.
Com17   OTA Peg
        Pwr 1  Gemini
        Pwr 2 EFA

Located on CDK 14 OTA:

Pegasus Astro  COM17
PW EFA PWI3    COM12
PW DEW Heat    COM11
GEMINI         COM14

Located on Camera Assembly:

Pegasus Astro   COM16
Vincent Shutt   COM15   Darkslide
FlI FW 1     Closest to tel
FlI FW 2     closest to cam  flifil0
QHY600         AstroImaging Equipment


'''

#NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.

#site_name = 'mrc'    #NB These must be unique across all of PTR. Pre-pend with airport code if needed: 'sba_wmdo'
site_name = input('What site am I running at?\n') 


#print (site_name)

# THIS BIT OF CODE DUMPS AN OLD CONFIG FILE TO A NEW JSON... where    
# with open("sample.json", "w") as outfile:
#     json.dump(sitegoog, outfile)

try:

    with open("configs\\" +str(site_name) + '.json', 'r') as f:
      site_config = json.load(f)
except:
    print (str(site_name) + " isn't a real place or there isn't a config file that I can find!")
    sys.exit()


def linearize_unihedron(uni_value):
    #  Based on 20180811 data   --- Highly suspect.  Need to re-do 20210807
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
last_good_wx_fields = 'n.a'
last_good_daily_lines = 'n.a'

def get_ocn_status(g_dev=None):
    global last_good_wx_fields, last_good_daily_lines   # NB NB NB Perhaps memo-ize these instead?
    if site_config['site'] == 'sro':   #  Belts and suspenders.
        try:
            wx = open('W:/sroweather.txt', 'r')
            wx_line = wx.readline()
            wx.close
            #print(wx_line)
            wx_fields = wx_line.split()
            skyTemperature = f_to_c(float( wx_fields[4]))
            temperature = f_to_c(float(wx_fields[5]))
            windspeed = round(float(wx_fields[7])/2.237, 2)
            humidity =  float(wx_fields[8])
            dewpoint = f_to_c(float(wx_fields[9]))
            #timeSinceLastUpdate = wx_fields[13]
            open_ok = wx_fields[19]
            #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
            #self.focus_temp = temperature
            last_good_wx_fields = wx_fields
        except:
            time.sleep(5)
            try:

                wx = open('W:/sroweather.txt', 'r')
                wx_line = wx.readline()
                wx.close
                #print(wx_line)
                wx_fields = wx_line.split()
                skyTemperature = f_to_c(float( wx_fields[4]))
                temperature = f_to_c(float(wx_fields[5]))
                windspeed = round(float(wx_fields[7])/2.237, 2)
                humidity =  float(wx_fields[8])
                dewpoint = f_to_c(float(wx_fields[9]))
                #timeSinceLastUpdate = wx_fields[13]
                open_ok = wx_fields[19]
                #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
                #self.focus_temp = temperature
                last_good_wx_fields = wx_fields
            except:
                print('SRO Weather source problem, 2nd try.')
                time.sleep(5)
                try:
                    wx = open('W:/sroweather.txt', 'r')
                    wx_line = wx.readline()
                    wx.close
                    #print(wx_line)
                    wx_fields = wx_line.split()
                    skyTemperature = f_to_c(float( wx_fields[4]))
                    temperature = f_to_c(float(wx_fields[5]))
                    windspeed = round(float(wx_fields[7])/2.237, 2)
                    humidity =  float(wx_fields[8])
                    dewpoint = f_to_c(float(wx_fields[9]))
                    #timeSinceLastUpdate = wx_fields[13]
                    open_ok = wx_fields[19]
                    #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
                    #self.focus_temp = temperature
                    last_good_wx_fields = wx_fields
                except:
                    try:

                        wx = open('W:/sroweather.txt', 'r')
                        wx_line = wx.readline()
                        wx.close
                        #print(wx_line)
                        wx_fields = wx_line.split()
                        skyTemperature = f_to_c(float( wx_fields[4]))
                        temperature = f_to_c(float(wx_fields[5]))
                        windspeed = round(float(wx_fields[7])/2.237, 2)
                        humidity =  float(wx_fields[8])
                        dewpoint = f_to_c(float(wx_fields[9]))
                        #timeSinceLastUpdate = wx_fields[13]
                        open_ok = wx_fields[19]
                        #g_dev['o.redis_sever.set("focus_temp", temperature, ex=1200)
                        #self.focus_temp = temperature
                        last_good_wx_fields = wx_fields
                    except:
                        print('SRO Weather source problem, using last known good report.')
                        wx_fields = last_good_wx_fields
                        wx_fields = wx_line.split()
                        skyTemperature = f_to_c(float( wx_fields[4]))
                        temperature = f_to_c(float(wx_fields[5]))
                        windspeed = round(float(wx_fields[7])/2.237, 2)
                        humidity =  float(wx_fields[8])
                        dewpoint = f_to_c(float(wx_fields[9]))
                        #timeSinceLastUpdate = wx_fields[13]
                        open_ok = wx_fields[19]
        #self.last_weather =   NB found this fragment
        try:
            daily= open('W:/daily.txt', 'r')
            daily_lines = daily.readlines()

            daily.close()
            pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
            bright_percent_string = daily_lines[-4].split()[1]  #NB needs to be incorporated
            last_good_daily_lines = daily_lines
        except:
            time.sleep(5)
            try:
                daily= open('W:/daily.txt', 'r')
                daily_lines = daily.readlines()
                daily.close()
                pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
                last_good_daily_lines = daily_lines
            except:
                try:
                    daily= open('W:/daily.txt', 'r')
                    daily_lines = daily.readlines()
                    daily.close()
                    pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
                    last_good_daily_lines = daily_lines
                except:
                    print('SRO Daily source problem, using last known good pressure.')
                    daily_lines = last_good_daily_lines
                    pressure = round(33.846*float(daily_lines[-3].split()[1]), 2)
                   # pressure = round(33.846*float(self.last_good_daily_lines[-3].split()[1]), 2)
        try:   # 20220105 Experienced a glitch, probably the first try faulted in the code above.
            pressure = float(pressure)
        except:
            pressure = site_config['reference_pressure']
        illum, mag = g_dev['evnt'].illuminationNow()

        if illum > 100:
            illum = int(illum)
        calc_HSI_lux = illum
        # NOte criterian below can now vary with the site config file.
        dew_point_gap = not (temperature  - dewpoint) < 2
        temp_bounds = not (temperature < -10) or (temperature > 40)
        # NB NB NB Thiseeds to go into a config entry.
        wind_limit = windspeed < 60/2.235   #sky_monitor reports m/s, Clarity may report in MPH
        sky_amb_limit  = skyTemperature < -20
        humidity_limit =humidity < 85
        rain_limit = True #r ainRate <= 0.001
        wx_is_ok = dew_point_gap and temp_bounds and wind_limit and sky_amb_limit and \
                        humidity_limit and rain_limit
        #  NB  wx_is_ok does not include ambient light or altitude of the Sun
        try:
            enc_stat =g_dev['enc'].stat_string
            if enc_stat in ['Open', 'OPEN', 'Open']:
                wx_str = "Yes"
                wx_is_ok = True
            else:
                wx_str = 'No'
                wx_is_ok = False
        except:
            
            if wx_is_ok:
                wx_str = "Yes"
            else:
                wx_str = "No"   #Ideally we add the dominant reason in priority order.
        # Now assemble the status dictionary.
        status = {"temperature_C": round(temperature, 2),
                      "pressure_mbar": pressure,
                      "humidity_%": humidity,
                      "dewpoint_C": dewpoint,
                      "sky_temp_C": round(skyTemperature,2),
                      "last_sky_update_s":  round(10, 2),
                      "wind_m/s": abs(round(windspeed, 2)),
                      'rain_rate': 0.0, # rainRate,
                      'solar_flux_w/m^2': None,
                      'cloud_cover_%': 0.0, #str(cloudCover),
                      "calc_HSI_lux": illum,
                      "calc_sky_mpsas": round((mag - 20.01),2),    #  Provenance of 20.01 is dubious 20200504 WER
                      "wx_ok": wx_str,  #str(self.sky_monitor_oktoimage.IsSafe),
                      "open_ok": wx_str,  #T his is the special bit in the 
                                           # Boltwood for a roof close relay
                      'wx_hold': 'n.a.',  # THis is usually added by the OCN Manager
                      'hold_duration': 'n.a.',
                      'meas_sky_mpsas': 22   # THis is a plug.  NB NB NB
                      #"image_ok": str(self.sky_monitor_oktoimage.IsSafe)
                      }
        return status
    else:
        return None #breakpoint()       #  Debug bad place.

def get_enc_status(g_dev=None):
    if site_config['site'] == 'sro':   #  Belts and suspenders.
        try:
            enc = open('R:/Roof_Status.txt')
            enc_text = enc.readline()
            enc.close
            enc_list = enc_text.split()

        except:
            try:
                enc = open('R:/Roof_Status.txt')
                enc_text = enc.readline()
                enc.close
                enc_list = enc_text.split()
            except:
                print("Second read of roof status file failed")
                try:
                    enc = open('R:/Roof_Status.txt')
                    enc_text = enc.readline()
                    enc.close
                    enc_list = enc_text.split()
                except:
                    print("Third read of roof status file failed")
                    enc_list = [1, 2, 3, 4, 'Error']
        if len(enc_list) == 5:
            if enc_list[4] in ['OPEN', 'Open', 'open', 'OPEN\n']:
                shutter_status = 0  #Numbering is correct
                stat_string = "Open"
            elif enc_list[4] in ['OPENING']:  #SRO Does not report this.
                shutter_status = 2
                stat_string = "Open"
            elif enc_list[4] in ['CLOSED', 'Closed', 'closed', "CLOSED\n"]:
                shutter_status = 1
                stat_string = "Closed"
            elif enc_list[4] in ['CLOSING']:  # SRO Does not report this.
                shutter_status = 3
                stat_string = "Closed"
            elif enc_list[4] in ['Error']:  # SRO Does not report this.
                shutter_status = 4
                stat_string = "Fault"  #Do not know if SRO supports this.
        else:
            shutter_status = 4
            stat_string = "Fault"
        #g_dev['enc'].status = shutter_status   # NB NB THIS was a nasty bug
        g_dev['enc'].stat_string = stat_string
        if shutter_status in [2, 3]:
            g_dev['enc'].moving = True
        else:
            g_dev['enc'].moving = False
        if g_dev['enc'].mode == 'Automatic':
            e_mode = "Autonomous!"
        else:
            e_mode = g_dev['enc'].mode
        status = {'shutter_status': stat_string,   # NB NB NB "Roof is open|closed' is more inforative for FAT, but we make boolean decsions on 'Open'
                  'enclosure_synchronized': True,
                  'dome_azimuth': 'n.a',
                  'dome_slewing': 'n.a',
                  'enclosure_mode': e_mode,
                  'enclosure_message':  ''
                 }
        return status
    else:
        return None
    #breakpoint()     #  Debug bad place.


#get_ocn_status = None
#get_enc_status = None
if __name__ == '__main__':
    '''
    This is a simple test to send and receive via json.
    '''

    j_dump = json.dumps(site_config)
    site_unjasoned = json.loads(j_dump)
    if str(site_config)  == str(site_unjasoned):
        print('Strings matched.')
    if site_config == site_unjasoned:
        print('Dictionaries matched.')

