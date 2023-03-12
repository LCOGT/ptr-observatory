# -*- coding: utf-8 -*-
"""
Created on Sun Mar 12 02:14:36 2023

@author: observatory
"""

#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
from ctypes import *
import os

LOG_LINE_NUM = 0

# Python constants
STR_BUFFER_SIZE = 32
# STREAM_MODE = c_uint8(0)
EXPOSURE = c_double(1000.0 * 1000.0)  # us
BRIGHTNESS = c_double(1.0)
GAIN = c_double(54.0)

# Constants from the SDK, found in "qhyccdstruct.h
# Add more, if more are necessary
QHY183_MAX_WIDTH = c_uint32(5544)
QHY183_MAX_HEIGHT = c_uint32(3684)
CONTROL_BRIGHTNESS = c_int(0)
CONTROL_GAIN = c_int(6)
CONTROL_EXPOSURE = c_int(8)
CONTROL_CURTEMP = c_int(14)
CONTROL_CURPWM = c_int(15)
CONTROL_MANULPWM = c_int(16)
CONTROL_COOLER = c_int(18)

chip_width_index = c_double()
chip_height_index = c_double()
image_width_index = c_uint32()
image_height_index = c_uint32()
pixel_width_index = c_double()
pixel_height_index = c_double()
bits_per_pixel_index = c_uint32()

chip_width_c1 = c_double()
chip_height_c1 = c_double()
image_width_c1 = c_uint32()
image_height_c1 = c_uint32()
pixel_width_c1 = c_double()
pixel_height_c1 = c_double()
bits_per_pixel_c1 = c_uint32()
# todo
chip_width_c2 = c_double()
chip_height_c2 = c_double()
image_width_c2 = c_uint32()
image_height_c2 = c_uint32()
pixel_width_c2 = c_double()
pixel_height_c2 = c_double()
bits_per_pixel_c2 = c_uint32()


QHYCCD_SUCCESS = 0
QHYCCD_ERROR = 0xFFFFFFFF
from sys import platform

# so = None
# if platform == "linux" or platform == "linux2":
#     so = CDLL("/usr/local/lib/libqhyccd.so")
#     print('Linux')
# elif platform == "darwin":
#     so = CDLL("/usr/local/lib/libqhyccd.dylib")
#     print('Mac')
# elif platform == "win32":
#     if sys.maxsize > 2147483647:
#         print(sys.maxsize)
#         print('64-Bit')
#         os.chdir("C:\Program Files\QHYCCD\AllInOne\sdk\x64")
#     else:
#         print(sys.maxsize)
#         print('32-Bit')
#         os.chdir("C:/SoftwareSVN/sdk_publish/QHYCCD_SDK_CrossPlatform/build32/src/Release")
#     # so = CDLL("qhyccd.dll")
so = windll.LoadLibrary("support_info/qhysdk/x64/qhyccd.dll")
# so = CDLL("C:/SoftwareSVN/sdk_publish/QHYCCD_SDK_CrossPlatform/build64/src/Release/qhyccd.dll")
print('Windows')

so.GetQHYCCDParam.restype = c_double
so.GetQHYCCDMemLength.restype = c_ulong
so.OpenQHYCCD.restype = c_void_p
# so.EnableQHYCCDMessage(c_bool(False))
so.EnableQHYCCDMessage(c_bool(True))
so.SetQHYCCDStreamMode.argtypes = [c_void_p, c_uint8]
so.InitQHYCCD.argtypes = [c_void_p]
so.ExpQHYCCDSingleFrame.argtypes = [c_void_p]
so.GetQHYCCDMemLength.argtypes = [c_void_p]
so.BeginQHYCCDLive.argtypes = [c_void_p]
so.SetQHYCCDResolution.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_uint32]
so.GetQHYCCDSingleFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
so.GetQHYCCDChipInfo.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
so.GetQHYCCDLiveFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]


@CFUNCTYPE(None, c_char_p)
def pnp_in(cam_id):
    print("cam   + %s" % cam_id)


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id)


def gui_start():
    so.RegisterPnpEventIn(pnp_in)
    so.RegisterPnpEventOut(pnp_out)
    so.InitQHYCCDResource()


gui_start()
command = ""
while command != "q":
    command = input()
    if command == "info":
        goog=so.GetQHYCCDChipInfo
        print (goog.camhandle)