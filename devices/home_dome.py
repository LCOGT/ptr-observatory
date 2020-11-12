# -*- coding: utf-8 -*-
"""
Created on Sun Nov  8 14:54:36 2020

@author: WER
"""

import time
import serial
import math


def rectSph(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    print("rSq, pX, pY, pZ:  ", rSq, pX, pY, pZ)
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))

def sphRect(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)

def rotate(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta

def adjust_saf_dome_offset(in_az, in_alt, station):    #degrees
    '''
    CV 19.47E 5.74S, AP 13.49 E, 6.7N, AVG 16.46 E, 0.95N
    
    '''
    if station == 'CV':
        eo = 19.47
        so = 5.74
    elif station == 'AP':
        eo = 13.49
        so = -6.70       
    elif station == 'Both':
        eo = 16.46
        so = -0.95        
    else:
        eo = 0
        so = 0
    #  Surveyor's azimuth used here.
    offset = 0    
    if 0 <= in_az <= 90:    # Tel on West side looking East
        offset += -eo*math.cos(math.degrees(in_alt))
        offset += so*math.sin(math.degrees(in_alt))
    elif 90 < in_az < 180:
        offset += eo*math.cos(math.degrees(in_alt))
        offset += so*math.sin(math.degrees(in_alt))
    elif 180 <= in_az < 270:    # Tel on East side looking West
        offset += -eo*math.cos(math.degrees(in_alt))
        offset += so*math.sin(math.degrees(in_alt))
    elif 270 <= in_az <=360:
        offset += eo*math.cos(math.degrees(in_alt))
        offset += so*math.sin(math.degrees(in_alt))
    else:
        print("Bogus input.")
    
    return round(offset, 1)    
        

        
#    else:               # Tel on West Side looking East
# =============================================================================
#     #Note need to convert Surveyor's az to mathematical angle.
#     tx, ty, tz = sphRect(in_az - 180, in_alt)    #x is South, Y is east
#     print('eo, so:  ', eo, so)
#     print('tx, ty, tz:  ', tx, ty, tz)
#     rx, ry = rotate(tx, ty, math.radians(eo))
#     print('rx, ry, tz:  ', rx, ry, tz)
#     rry, rz = rotate(ry, tz, math.radians(-so))
#     print('rx, rry, rz:  ', rx, rry, rz)
#     m_out_az, out_alt = rectSph(rx, rry, rz)
#     print('m_out_az:  ', m_out_az)
#     out_az = 180 - m_out_az    #Back to Surveyor's azimuth
#     while out_az < 0:
#         out_az += 360
#     while out_az >= 360:
#         out_az -= 360
#     print(round(out_az, 2), round(out_alt,2))
# =============================================================================
    

class HomeDome(object):
    
    def __init__(self):
        self.dome_status = 'unknown'
    
    def home(self):
       self.com = serial.Serial('COM6', timeout=5)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
       self.com.write(b'GHOM')
       time.sleep(3)
       self.com.close()
        
    def goto(self, azimuth):
       self.com = serial.Serial('COM6', timeout=0.2)
       self.com.write(b'G190')
       while True:
           report = self.com.read(5).decode()
           print(report)
           if len(report) > 3 and (report[1] == "V" or 'V' in report):
               break
       tail = self.com.read_all().decode()
       print(report, tail)
       self.com.close()

    
    def test(self):
       self.com = serial.Serial('COM6', timeout=0.2)
       self.com.write(b'GTST')
       time.sleep(1)
       print(self.com.read_all().decode())
       self.com.close()
       return self.dome_status
        
    def open(self):
        self.com = serial.Serial('COM6', timeout=0.1)
        self.com.write(b'GOPN')
        self.dome_status = 'open'
        self.com.close()
        print("HomeDome Opening.")

    def close(self):
       self.com = serial.Serial('COM6', timeout=0.1)
       self.com.write(b'GCLZ')
       self.dome_status = 'closed'
       self.com.close()
       print("HomeDome Closing.")
   
    def status(self):
       self.com = serial.Serial('COM6', timeout=0.1)
       self.com.write(b'GINF')
       time.sleep(2)
       self.dome_status_list = self.com.read_all().decode().split(',')
       print(self.dome_status_list)
       home = False
       if self.dome_status_list[8] == '0':
           home = True
       shutter = "unknown"
       if self.dome_status_list[6] == '1':
           shutter = "closed"
           self.open = False
       elif self.dome_status_list[6] == '2':
           shutter = "open"
           self.open = True
       ring = "unknown"
       if self.dome_status_list[7] == '1':
           ring = "latched"
       elif self.dome_status_list[7] == '2':
           ring = "fault"
       self.com.close()
       self.dome_status = {
               'az':  round(int(self.dome_status_list[4])*359.9/695, 1),
               'roof': shutter,
               'home':  home,
               'ring':  ring}  
       print(self.dome_status)
       
   
if __name__ == '__main__':
    
    hd = HomeDome()
    for az in  [180, 202.5, 225, 247.5, 269.99, 270, 292.5, 315, 337.5, 360]:
        for alt in [0]:  #, 30, 45, 60, 75, 85]:
        
            print(alt, az, adjust_saf_dome_offset(az, alt, "CV"))