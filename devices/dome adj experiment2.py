# -*- coding: utf-8 -*-
"""
Created on Mon Jun 13 14:47:55 2022

@author: obs
"""
import math
from math import *

DEG_SYM = '°'
PI = math.pi
TWOPI = math.pi*2
PIOVER2 = math.pi/2.
DTOR = math.pi/180.
RTOD = 180/math.pi
STOR = math.pi/180./3600.
RTOS = 3600.*180./math.pi
RTOH = 12./math.pi
HTOR = math.pi/12.
HTOS = 15*3600.
DTOS = 3600.
STOD = 1/3600.
STOH = 1/3600/15.
SecTOH = 1/3600.
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029

def test( p, silent=False):
    if not silent:
        print(p)
    else:
        print("I am silent")
    return silent, p
    

def rect_sph_d(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))

def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)

def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta

def dome_adjust_rah_decd(hah=0.01, dec=90, flip='Looking West', r=60, offe=21, offs=0, silent=False):

    ## NB NB NB offsets can be switched to prefer one OTA for dome positioning

    lat = 36.18*DTOR     #saf
    rd = 60
    xm = 0
    ym = 0
    zm = 0
    p = 0
    q = 19
    r = -6.5

    y = p + r*sin(dec*DTOR) 
    xmo = q*cos(hah*HTOR) + y*sin(hah*HTOR)
    ymo = y*cos(hah*HTOR) - q*sin(hah*HTOR)
    zmo = r*cos(dec*DTOR)
    
    xdo = xm + xmo
    ydo = ym + ymo*sin(lat) + zmo*cos(lat)
    zdo = zm - ymo*cos(lat)  + zmo*sin(lat)
    
    x = -sin(hah*HTOR)*cos(dec*DTOR)
    y = -cos(hah*HTOR)*cos(dec*DTOR)
    z = sin(dec*DTOR)
    
    xs = x
    ys = y*sin(lat) + z*cos(lat)
    zs = -y*cos(lat) + z*sin(lat)
    
    sdt = xs*xdo + ys*ydo + zs*zdo
    t2m = xdo*xdo + ydo*ydo + zdo*zdo
    w = sdt*sdt - t2m + rd*rd
    f = -sdt + sqrt(w)
    
    if w < 0: print("No solution, w is negative.")
    
    x = xdo +f*xs
    y = ydo +f*ys
    z = zdo +f*zs
    
    if x == 0 and y == 0:
        a = 0
        e = pi/2
    else:
        a = atan2(x,y)
        e = atan2(z, sqrt(x*x + y*y))
        if a < 0:
            a += 2*pi
        
    
    print(a*RTOD, e*RTOD)
    print(a*RTOD, e*RTOD)
    
  
#fornpush
if __name__ == '__main__':
    ('Enclosure Test code started locally','\n')
    dome_adjust_rah_decd(silent=False)
    # for ha_test in range(7, -1, -1):
    #     print(dome_adjust_rah_decd(hah=ha_test, dec=90, silent=True))
    #for dec_test in range(90, -55, -10):
    #    print(dome_adjust_rah_decd(hah=0, dec=dec_test, silent=True))
    
    
#Patrick's test code:  Works correctly
    
   # def dome_adjust_rah_decd(hah=0.16653973245135928, dec=37.901158147903956, flip='Looking West', r=60, offe=21, offs=0, silent=False):

   #      ## NB NB NB offsets can be switched to prefer one OTA for dome positioning

   #      lat = 0.6315 #36.18*DTOR     #saf
   #      rd = 1900
   #      xm = -35
   #      ym = +370
   #      zm = 1250
   #      p = 0
   #      q = 505
   #      r = 0

   #      y = p + r*sin(dec*DTOR) 
   #      xmo = q*cos(hah*HTOR) + y*sin(hah*HTOR)
   #      ymo = y*cos(hah*HTOR) - q*sin(hah*HTOR)
   #      zmo = r*cos(dec*DTOR)
        
   #      xdo = xm + xmo
   #      ydo = ym + ymo*sin(lat) + zmo*cos(lat)
   #      zdo = zm - ymo*cos(lat)  + zmo*sin(lat)
        
   #      x = -sin(hah*HTOR)*cos(dec*DTOR)
   #      y = -cos(hah*HTOR)*cos(dec*DTOR)
   #      z = sin(dec*DTOR)
        
   #      xs = x
   #      ys = y*sin(lat) + z*cos(lat)
   #      zs = -y*cos(lat) + z*sin(lat)
        
   #      sdt = xs*xdo + ys*ydo + zs*zdo
   #      t2m = xdo*xdo + ydo*ydo + zdo*zdo
   #      w = sdt*sdt - t2m + rd*rd
   #      f = -sdt + sqrt(w)
        
   #      if w < 0: print("No solution, w is negative.")
        
   #      x = xdo +f*xs
   #      y = ydo +f*ys
   #      z = zdo +f*zs
        
   #      if x == 0 and y == 0:
   #          a = 0
   #          e = pi/2
   #      else:
   #          a = atan2(x,y)
   #          e = atan2(z, sqrt(x*x + y*y))
   #          if a < 0:
   #              a += 2*pi
            
        
   #      print(a*RTOD, e*RTOD)
      
   ## Returns 50.369411 , 72.051742 in computation is correct.