# -*- coding: utf-8 -*-
"""
Created in May 2021

@author: wer
"""

import serial


class ArcLampBox(object):

    '''
    COM Port must be set to 2400N1  Sequence copied with
    ELTIMA Serial Port Monitor.  Presumably supplied from the
    instrument config file.
   
    Call an instance of this object with the various source
    strings to set the lamp on and switch the beam into the
    spectrograph.
   
    Choices are: 'Object'' or 'Reset', "Thorium", "Tungsten", "Blue",
    "White"  (both Blue and Tungsten), "Solar", and Dark (the star
     beam is still blocked but no light from the calibration box.)
    '''


    def __init__(self, com_port):
        self.thorium_mirror = bytes([0x0d, 0x01, 0x42, 0xa0, 0x10])
        self.tungsten_mirror = bytes([0x0d, 0x01, 0x42, 0x90, 0x20])
        self.blue_mirror = bytes([0x0d, 0x01, 0x42, 0xc0, 0xf0])
        self.white_mirror = bytes([0x0d, 0x01, 0x42, 0xd0, 0xe0]) #Combining Blue and Tungsten_halogen
        self.solar_mirror = bytes([0x0d, 0x01, 0x42, 0x90, 0x20])  #Wrong spec, just a placeholder.
        self.dark_mirror = bytes([0x0d, 0x01, 0x42, 0x80, 0x30])   #Mirror in AGU is deployed, No Light
        self.no_light_no_mirror = bytes([0x0d, 0x01, 0x42, 0x00, 0xb0])    #Mirror in AGU out of the way
        self.arc_status = 'unknown'
        self.com_port = com_port
        if com_port is not None: 
            self.set_arc_box('Reset')
        else:
            print ("No calibration unit detected.")
            #pass

    def set_arc_box(self, cmd):
        self._com = serial.Serial(self.com_port, baudrate=2400, bytesize=8, \
                                  parity='N', stopbits=1, timeout=0.1)
        if cmd == "Thorium":
            cmd_arc = self.thorium_mirror
        elif cmd == "Tungsten":
            cmd_arc = self.tungsten_mirror
        elif cmd == "Blue":
            cmd_arc = self.blue_mirror
        elif cmd == "White":
            cmd_arc = self.white_mirror
        elif cmd == "Solar":
            cmd_arc = self.solar_mirror
        elif cmd == 'Dark_mirror':
            cmd_arc = self.dark_mirror
        elif cmd == 'Object' or cmd == 'Reset':
            cmd_arc = self.no_light_no_mirror
        self._com.write(cmd_arc*2)
        self.arc_status = cmd
        self._com.close()
        print('Arc_box:  ', cmd)


    def get_arc_status(self):
        return self.arc_status



#if __name__ == '__main__':

    #arc_lamp = ArcLampBox('COM11')
    #arc_lamp.set_arc_box("White")   #This shoulld turn on White light and Blue LED