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

def adjust_saf_dome(mnt_az, mnt_alt, station='CV', radius=60):
    if station == 'CV':
        eo = 19.47
        so = 5.74
    elif station == 'AP':
        eo = 13.49
        so = -6.70       
    elif station == 'Both':
        eo = 16.685
        so = -0.96        
    else:
        eo = 0
        so = 0
    if mnt_az <= 180:
        flip = 1
    else:
        flip = -1        
    dip = mnt_alt - math.degrees(math.asin(so*flip/radius))
    south_lever = math.cos(math.radians(dip))*radius
    twist = math.degrees(math.atan2(eo*flip, south_lever))
    dome_az = mnt_az - twist
    while dome_az < 0.0:
        dome_az += 360.0
    while dome_az >= 360.:
        dome_az -= 360.0
    return dome_az
    

    

    



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