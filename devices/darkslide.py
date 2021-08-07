# -*- coding: utf-8 -*-
"""
Created on Sat Aug 15 19:19:56 2020

@author: wer
"""

import serial

#  NBNB This needs to be integrated with config and camera.
class Darkslide(object):
    
   def __init__(self, com_port):
       self.slideStatus = 'unknown'
       self.com_port = com_port
       self.closeDarkslide()
   
   def openDarkslide(self):
       self._com = serial.Serial(self.com_port, timeout=0.3)
       self._com.write(b'@')
       self.slideStatus = 'open'
       self._com.close()
       print("Darkside Opened.")
    
   def closeDarkslide(self):
       self._com = serial.Serial(self.com_port, timeout=0.3)   #Com 12 for saf, needs fixing.
       self._com.write(b'A')
       self.slideStatus = 'closed'
       self._com.close()
       print("Darkside Closed.")
       
   def darkslideStatus(self):
       return self.slideStatus
   
if __name__ == '__main__':
    
    ds = Darkslide()