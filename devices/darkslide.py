# -*- coding: utf-8 -*-
"""
Created on Sat Aug 15 19:19:56 2020

@author: wer
"""

import serial
from global_yard import g_dev
import traceback

class Darkslide(object):
    
    def __init__(self, com_port):
        self.slideStatus = 'Unknown'
        self.com_port = com_port
        g_dev['drk'] = self

    def openDarkslide(self):
        try:
            self._com = serial.Serial(self.com_port, timeout=0.3)
            self._com.write(b'@')
            self.slideStatus = 'Open'
            self._com.close()
            print("Darkslide Opened.")
            return True
        except:
            print(traceback.format_exc())
            print ("ALERT: DARKSLIDE EXCEPTION ON OPENING")
            return False
    
    def closeDarkslide(self):
        try:
            self._com = serial.Serial(self.com_port, timeout=0.3)   #Com 12 for saf, needs fixing.
            self._com.write(b'A')
            self.slideStatus = 'Closed'
            self._com.close()
            print("Darkslide Closed.")
            return True
        except:
            print(traceback.format_exc())
            print ("ALERT: DARKSLIDE EXCEPTION ON CLOSING")
            return False
           
    def darkslideStatus(self):
        return self.slideStatus
