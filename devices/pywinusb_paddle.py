# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
"""
Handling raw data inputs example
"""
from time import sleep
from msvcrt import kbhit

import pywinusb.hid as hid
from global_yard import g_dev

_g_prior = None
_NS = 1
_EW = 1
_motion = False
_incr = False

def sample_handler(_paddle):
    '''
    A simple routine that only queues transitions from a paddle device.
    '''

    global _g_prior, _NS, _EW, _motion, _incr
    if _paddle == _g_prior:
        pass
    else:
        #Queue up the new input.
        #print("Raw data: {0}".format(_paddle))

        _g_prior = _paddle
        spd = _paddle[4]
        axis = _paddle[5]
        first = _paddle[2]
        second = _paddle[3]
        steps = _paddle[6]
        if _motion and first == 0 and second == 0 and steps == 0:
            print("STOP")
            _motion = False
        elif _incr and first == 0 and second == 0 and steps == 0:
            _incr = False
        else:
            pass
            #print("Raw data: {0}".format(_paddle))
        direc = None
        speed = 0.0
        step_speed = 0.0
        fast = 1
        incr = 0.0
#        EW = 1
#        NS = 1
        if first ==  2: direc = 'N'
        if first ==  4: direc = 'E'
        if first ==  9: direc = 'S'
        if first ==  6: direc = 'W'
        if first ==  1: direc = 'NE'
        if first ==  8: direc = 'SE'
        if first == 10: direc = 'SW'
        if first ==  3: direc = 'NW'
        if first == 12: fast = 3

        if second ==  2: direc = 'N'
        if second ==  4: direc = 'E'
        if second ==  9: direc = 'S'
        if second ==  6: direc = 'W'
        if second ==  1: direc = 'NE'
        if second ==  8: direc = 'SE'
        if second == 10: direc = 'SW'
        if second ==  3: direc = 'NW'
        if second == 12: fast = 3

        if first ==  7: _EW = 1
        if first == 11: _EW = -1
        if first ==  13: _NS = 1
        if first == 16: _NS = -1

        if spd ==  13:
            speed = 6*fast
            step_speed = 0.25
        if spd == 14:
            speed = 10*fast
            step_speed = 0.5
        if spd ==  15:
            speed = 21*fast
            step_speed = 0.75
        if spd ==  16:
            speed = 52*fast
            step_speed = 1
        if spd ==  26:
            speed = 171*fast
            step_speed = 1.5
        if spd == 27:
            speed = 805*fast
            step_speed = 2.0
        if spd ==  28:
            speed = 3600*fast
            step_speed = 2.5
        if axis > 6:
            if steps != 0:
                if steps < 128:
                    incr = steps*step_speed
                else:
                    incr = (steps - 256)*step_speed
        if axis == 17:
            print("AZ Move:   ", incr)
            _incr = True
        elif axis == 18:
            print("ALT Move:  ", incr)
            _incr = True
        elif axis == 19:
            print("RA Guide:  ", incr)
            _incr = True
        elif axis == 20:
            print("DEC Guide:  ", incr)
            _incr = True





        #print(button, spd, direc, speed)
#            if direc != '':
#                print(direc, speed)
        if direc is None:
            pass
#            _mount.DeclinationRate = 0.0
#            _mount.RightAscensionRate = 0.0
#            self.paddeling = False
        else:
            try:
                _mount = g_dev['mnt']
                breakpoint()
                if direc == 'N':
                    _mount.DeclinationRate = NS*speed
                    self.paddeling = True
                    print(direc,  _NS*speed)
                    motion = True
                if direc == 'NE':
                    _mount.DeclinationRate = NS*speed
                    self.paddeling = True
                    print(direc,  _NS*speed, _EW*speed/15.)
                    motion = True
                if direc == 'NW':
                    _mount.DeclinationRate = NS*speed
                    self.paddeling = True
                    print(direc,  _NS*speed, -_EW*speed/15.)
                    motion = True
                if direc == 'S':
                    _mount.DeclinationRate = -NS*speed
                    self.paddeling = True
                    print(direc,  -_NS*speed)
                    motion = True
                if direc == 'SE':
                    _mount.DeclinationRate = -NS*speed
                    self.paddeling = True
                    print(direc,  -_NS*speed, _EW*speed/15.)
                    motion = True
                if direc == 'SW':
                    _mount.DeclinationRate = -NS*speed
                    self.paddeling = True
                    print(direc,  -_NS*speed, -_EW*speed/15.)
                    motion = True
                if direc == 'E':
                    _mount.RightAscensionRate = EW*speed/15.   #Not quite the correct divisor.
                    self.paddeling = True
                    print(direc, _EW*speed/15.)
                    motion = True
                if direc == 'W':
                    _mount.RightAscensionRate = -EW*speed/15.
                    self.paddeling = True
                    print(direc, -_EW*speed/15.)
                    motion = True
            except:
                print('Paddle command failed.')




def start_paddle(_mount):
    # simple test
    # browse devices...
    import sys
    if sys.version_info >= (3,):
        # as is, don't handle unicodes
        unicode = str
        raw_input = input
    else:
        # allow to show encoded strings
        import codecs
        sys.stdout = codecs.getwriter('mbcs')(sys.stdout)
        
    all_hids = hid.find_all_hid_devices()
    if all_hids:
        while True:
            print("HID paddle is connected.")
#            print("Choose a device to monitor raw input reports:\n")
#            print("0 => Exit")
            for index, device in enumerate(all_hids):
                device_name = unicode("{0.vendor_name} {0.product_name}" \
                        "(vID=0x{1:04x}, pID=0x{2:04x})"\
                        "".format(device, device.vendor_id, device.product_id))
#                print("{0} => {1}".format(index+1, device_name))
#            print("\n\tDevice ('0' to '%d', '0' to exit?) " \
#                    "[press enter after number]:" % len(all_hids))
            index_option = '1'#raw_input()
            if index_option.isdigit() and int(index_option) <= len(all_hids):
                # invalid
                break;
        int_option = int(index_option)
        if int_option:
            device = all_hids[int_option-1]
            try:
                device.open()

                #set custom raw data handler
                device.set_raw_data_handler(sample_handler)

#                print("\nWaiting for data...\nPress any (system keyboard) key to stop...")
                while not kbhit() and device.is_plugged():
                    #just keep the device opened to receive events
                    sleep(0.5)
                return
            finally:
                device.close()
    else:
        print("There's not any non system HID class device available")
#
if __name__ == '__main__':
    # first be kind with local encodings
    import sys
    if sys.version_info >= (3,):
        # as is, don't handle unicodes
        unicode = str
        raw_input = input
    else:
        # allow to show encoded strings
        import codecs
        sys.stdout = codecs.getwriter('mbcs')(sys.stdout)
    start_paddle()


