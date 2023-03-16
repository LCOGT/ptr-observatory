# -*- coding: utf-8 -*-
"""
Created on Sun Mar 12 02:14:36 2023

@author: observatory
"""



import os
import numpy as np
import time
from PIL import Image as PIL_image
from astropy.io import fits
from datetime import datetime

#from qcam.image2ascii import np_array_to_ascii
#from qcam.qCam import *

#from image2ascii.py import np_array_to_ascii
#from qCam.py import *
from ctypes import *

class Qcam:
    LOG_LINE_NUM = 0
    # Python constants
    STR_BUFFER_SIZE = 32

    QHYCCD_SUCCESS = 0
    QHYCCD_ERROR = 0xFFFFFFFF

    stream_single_mode = 0
    stream_live_mode = 1

    bit_depth_8 = 8
    bit_depth_16 = 16

    CONTROL_BRIGHTNESS = c_int(0)
    CONTROL_GAIN = c_int(6)
    CONTROL_OFFSET = c_int(7)
    CONTROL_EXPOSURE = c_int(8)
    CAM_GPS = c_int(36)
    CONTROL_CURTEMP = c_int(14)
    CONTROL_CURPWM = c_int(15)
    CONTROL_MANULPWM = c_int(16)
    CONTROL_CFWPORT = c_int(17)
    CONTROL_CFWSLOTSNUM = c_int(44)
    CONTROL_COOLER = c_int(18)

    camera_params = {}

    so = None

    def __init__(self, dll_path):
        
            # if sys.maxsize > 2147483647:
            #     print(sys.maxsize)
            #     print('64-Bit')
            # else:
            #     print(sys.maxsize)
            #     print('32-Bit')
        self.so = windll.LoadLibrary(dll_path)
        print('Windows')

        self.so.GetQHYCCDParam.restype = c_double
        self.so.GetQHYCCDParam.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDControlAvailable.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDCFWPlugged.argtypes = [c_void_p]

        self.so.GetQHYCCDMemLength.restype = c_ulong
        self.so.OpenQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.argtypes = [c_void_p]
        # self.so.EnableQHYCCDMessage(c_bool(False))
        self.so.EnableQHYCCDMessage(c_bool(True))
        self.so.SetQHYCCDStreamMode.argtypes = [c_void_p, c_uint8]
        self.so.InitQHYCCD.argtypes = [c_void_p]
        self.so.ExpQHYCCDSingleFrame.argtypes = [c_void_p]
        self.so.GetQHYCCDMemLength.argtypes = [c_void_p]
        self.so.BeginQHYCCDLive.argtypes = [c_void_p]
        self.so.SetQHYCCDResolution.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_uint32]
        self.so.GetQHYCCDSingleFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDChipInfo.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDLiveFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.SetQHYCCDParam.argtypes = [c_void_p, c_int, c_double]
        self.so.SetQHYCCDBitsMode.argtypes = [c_void_p, c_uint32]

        # self.so.GetQHYCCDNumberOfReadModes.restype = c_uint32
        # self.so.GetQHYCCDNumberOfReadModes.argtypes = [c_void_p, c_void_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32, c_char_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32]

        self.so.GetReadModesNumber.argtypes = [c_char_p, c_void_p]
        self.so.GetReadModeName.argtypes = [c_char_p, c_uint32, c_char_p]
        self.so.SetQHYCCDReadMode.argtypes = [c_void_p, c_uint32]

    @staticmethod
    def slot_index_to_param(val_slot_index):
        val_slot_index = val_slot_index + 48
        return val_slot_index

    @staticmethod
    def slot_value_to_index(val_slot_value):
        if val_slot_value == 78:
            return -1
        return val_slot_value - 48





cam = Qcam(os.path.join("support_info/qhysdk/x64/qhyccd.dll"))




gscale1 = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
gscale2 = '@%#*+=-:. '


def get_average_l(image):
    im = np.array(image)
    w, h = im.shape
    return np.average(im.reshape(w * h))


def np_array_to_ascii(pil_image, cols, scale, more_levels):
    global gscale1, gscale2
    W, H = pil_image.size[0], pil_image.size[1]
    print("input image dims: %d x %d" % (W, H))
    w = W / cols
    h = w / scale
    rows = int(H / h)

    print("cols: %d, rows: %d" % (cols, rows))
    print("tile dims: %d x %d" % (w, h))
    if cols > W or rows > H:
        print("Image too small for specified cols!")
        exit(0)

    aimg = []
    for j in range(rows):
        y1 = int(j * h)
        y2 = int((j + 1) * h)

        if j == rows - 1:
            y2 = H

        aimg.append("")

        for i in range(cols):
            x1 = int(i * w)
            x2 = int((i + 1) * w)

            if i == cols - 1:
                x2 = W

            img = pil_image.crop((x1, y1, x2, y2))
            avg = int(get_average_l(img))

            if more_levels:
                gsval = gscale1[int((avg * 69) / 255)]
            else:
                gsval = gscale2[int((avg * 9) / 255)]

            aimg[j] += gsval

    return aimg




@CFUNCTYPE(None, c_char_p)
def pnp_in(cam_id):
    print("cam   + %s" % cam_id.decode('utf-8'))
    init_camera_param(cam_id)
    cam.camera_params[cam_id]['connect_to_pc'] = True
    os.makedirs(cam_id.decode('utf-8'), exist_ok=True)
    # select read mode
    success = cam.so.GetReadModesNumber(cam_id, byref(cam.camera_params[cam_id]['read_mode_number']))
    if success == cam.QHYCCD_SUCCESS:
        print('-  read mode - %s' % cam.camera_params[cam_id]['read_mode_number'].value)
        for read_mode_item_index in range(0, cam.camera_params[cam_id]['read_mode_number'].value):
            read_mode_name = create_string_buffer(cam.STR_BUFFER_SIZE)
            cam.so.GetReadModeName(cam_id, read_mode_item_index, read_mode_name)
            print('%s  %s %s' % (cam_id.decode('utf-8'), read_mode_item_index, read_mode_name.value))
    else:
        print('GetReadModesNumber false')
        cam.camera_params[cam_id]['read_mode_number'] = c_uint32(0)

    read_mode_count = cam.camera_params[cam_id]['read_mode_number'].value
    if read_mode_count == 0:
        read_mode_count = 1
    for read_mode_index in range(0, read_mode_count):
        test_frame(cam_id, cam.stream_single_mode, cam.bit_depth_16, read_mode_index)
        test_frame(cam_id, cam.stream_live_mode, cam.bit_depth_16, read_mode_index)
        test_frame(cam_id, cam.stream_single_mode, cam.bit_depth_8, read_mode_index)
        test_frame(cam_id, cam.stream_live_mode, cam.bit_depth_8, read_mode_index)
        cam.so.CloseQHYCCD(cam.camera_params[cam_id]['handle'])


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id.decode('utf-8'))


def gui_start():
    cam.so.RegisterPnpEventIn(pnp_in)
    cam.so.RegisterPnpEventOut(pnp_out)
    print('scan camera...')
    cam.so.InitQHYCCDResource()


def init_camera_param(cam_id):
    if not cam.camera_params.keys().__contains__(cam_id):
        cam.camera_params[cam_id] = {'connect_to_pc': False,
                                     'connect_to_sdk': False,
                                     'EXPOSURE': c_double(1000.0 * 1000.0),
                                     'GAIN': c_double(54.0),
                                     'CONTROL_BRIGHTNESS': c_int(0),
                                     'CONTROL_GAIN': c_int(6),
                                     'CONTROL_EXPOSURE': c_int(8),
                                     'CONTROL_CURTEMP': c_int(14),
                                     'CONTROL_CURPWM': c_int(15),
                                     'CONTROL_MANULPWM': c_int(16),
                                     'CONTROL_COOLER': c_int(18),
                                     'chip_width': c_double(),
                                     'chip_height': c_double(),
                                     'image_width': c_uint32(),
                                     'image_height': c_uint32(),
                                     'pixel_width': c_double(),
                                     'pixel_height': c_double(),
                                     'bits_per_pixel': c_uint32(),
                                     'mem_len': c_ulong(),
                                     'stream_mode': c_uint8(0),
                                     'channels': c_uint32(),
                                     'read_mode_number': c_uint32(),
                                     'read_mode_index': c_uint32(),
                                     'read_mode_name': c_char('-'.encode('utf-8')),
                                     'prev_img_data': c_void_p(0),
                                     'prev_img': None,
                                     'handle': None,
                                     }


def test_frame(cam_id, stream_mode, bit_depth, read_mode):
    print('open camera %s' % cam_id.decode('utf-8'))
    cam.camera_params[cam_id]['handle'] = cam.so.OpenQHYCCD(cam_id)
    if cam.camera_params[cam_id]['handle'] is None:
        print('open camera error %s' % cam_id)

    success = cam.so.SetQHYCCDReadMode(cam.camera_params[cam_id]['handle'], read_mode)
    cam.camera_params[cam_id]['stream_mode'] = c_uint8(stream_mode)
    success = cam.so.SetQHYCCDStreamMode(cam.camera_params[cam_id]['handle'], cam.camera_params[cam_id]['stream_mode'])
    print('set StreamMode   =' + str(success))
    success = cam.so.InitQHYCCD(cam.camera_params[cam_id]['handle'])
    print('init Camera   =' + str(success))

    mode_name = create_string_buffer(cam.STR_BUFFER_SIZE)
    cam.so.GetReadModeName(cam_id, read_mode, mode_name)

    success = cam.so.SetQHYCCDBitsMode(cam.camera_params[cam_id]['handle'], c_uint32(bit_depth))

    success = cam.so.GetQHYCCDChipInfo(cam.camera_params[cam_id]['handle'],
                                       byref(cam.camera_params[cam_id]['chip_width']),
                                       byref(cam.camera_params[cam_id]['chip_height']),
                                       byref(cam.camera_params[cam_id]['image_width']),
                                       byref(cam.camera_params[cam_id]['image_height']),
                                       byref(cam.camera_params[cam_id]['pixel_width']),
                                       byref(cam.camera_params[cam_id]['pixel_height']),
                                       byref(cam.camera_params[cam_id]['bits_per_pixel']))

    print('info.   =' + str(success))
    cam.camera_params[cam_id]['mem_len'] = cam.so.GetQHYCCDMemLength(cam.camera_params[cam_id]['handle'])
    i_w = cam.camera_params[cam_id]['image_width'].value
    i_h = cam.camera_params[cam_id]['image_height'].value
    print('c-w:     ' + str(cam.camera_params[cam_id]['chip_width'].value), end='')
    print('    c-h: ' + str(cam.camera_params[cam_id]['chip_height'].value))
    print('p-w:     ' + str(cam.camera_params[cam_id]['pixel_width'].value), end='')
    print('    p-h: ' + str(cam.camera_params[cam_id]['pixel_height'].value))
    print('i-w:     ' + str(i_w), end='')
    print('    i-h: ' + str(i_h))
    print('bit: ' + str(cam.camera_params[cam_id]['bits_per_pixel'].value))
    print('mem len: ' + str(cam.camera_params[cam_id]['mem_len']))

    val_temp = cam.so.GetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_CURTEMP)
    val_pwm = cam.so.GetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_CURPWM)

    # todo  c_uint8 c_uint16??
    if bit_depth == cam.bit_depth_16:
        print('using c_uint16()')
        cam.camera_params[cam_id]['prev_img_data'] = (c_uint16 * int(cam.camera_params[cam_id]['mem_len'] / 2))()
    else:
        print('using c_uint8()')
        cam.camera_params[cam_id]['prev_img_data'] = (c_uint8 * cam.camera_params[cam_id]['mem_len'])()

    success = cam.QHYCCD_ERROR

    image_width_byref = c_uint32()
    image_height_byref = c_uint32()
    bits_per_pixel_byref = c_uint32()
    # TODO resolution
    cam.so.SetQHYCCDResolution(cam.camera_params[cam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                   c_uint32(i_h))

    if stream_mode == cam.stream_live_mode:
        success = cam.so.BeginQHYCCDLive(cam.camera_params[cam_id]['handle'])
        print('exp  Live = ' + str(success))

    frame_counter = 0
    time_string = '---'
    retry_counter = 0  # todo error control
    live_mode_skip_frame = 0

    while frame_counter < 2:
        time_string = datetime.now().strftime("%Y%m%d%H%M%S")
        if stream_mode == cam.stream_single_mode:
            success = cam.so.ExpQHYCCDSingleFrame(cam.camera_params[cam_id]['handle'])
            print('exp  single = ' + str(success))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_EXPOSURE, c_double(20000))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_GAIN, c_double(30))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_OFFSET, c_double(40))
        # success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], CONTROL_EXPOSURE, EXPOSURE)
        if stream_mode == cam.stream_live_mode:
            success = cam.so.GetQHYCCDLiveFrame(cam.camera_params[cam_id]['handle'],
                                                byref(image_width_byref),
                                                byref(image_height_byref),
                                                byref(bits_per_pixel_byref),
                                                byref(cam.camera_params[cam_id]['channels']),
                                                byref(cam.camera_params[cam_id]['prev_img_data']))
            print('read  single = ' + str(success))
        if stream_mode == cam.stream_single_mode:
            success = cam.so.GetQHYCCDSingleFrame(cam.camera_params[cam_id]['handle'],
                                                  byref(image_width_byref),
                                                  byref(image_height_byref),
                                                  byref(bits_per_pixel_byref),
                                                  byref(cam.camera_params[cam_id]['channels']),
                                                  byref(cam.camera_params[cam_id]['prev_img_data']))
            print('read  single = ' + str(success))
        time.sleep(2)
        try_counter = 0
        while try_counter < 5 and success != cam.QHYCCD_SUCCESS:
            try_counter += 1
            print("success != 0  = " + str(success))
            time.sleep(1)

        if stream_mode == cam.stream_live_mode:
            live_mode_skip_frame += 1
            if live_mode_skip_frame < 3:
                print('skip frame in live mode  [%s]' % live_mode_skip_frame)
                continue
        frame_counter += 1

        cam.camera_params[cam_id]['prev_img'] = np.ctypeslib.as_array(cam.camera_params[cam_id]['prev_img_data'])
        print("---------------->" + str(len(cam.camera_params[cam_id]['prev_img'])))
        image_size = i_h * i_w
        print("image size =     " + str(image_size))
        print("prev_img_list sub length-->" + str(len(cam.camera_params[cam_id]['prev_img'])))
        print("Image W=" + str(i_w) + "        H=" + str(i_h))
        cam.camera_params[cam_id]['prev_img'] = cam.camera_params[cam_id]['prev_img'][0:image_size]
        image = np.reshape(cam.camera_params[cam_id]['prev_img'], (i_h, i_w))

        stream_mode_str = 'stream_mode'
        read_mode_name_str = mode_name.value.decode('utf-8').replace(' ', '_')
        bit_depth_str = 'bit_dep'
        if stream_mode == cam.stream_live_mode:
            stream_mode_str = 'live'
        else:
            stream_mode_str = 'single'
        if bit_depth == cam.bit_depth_16:
            bit_depth_str = '16bit'
        else:
            bit_depth_str = '8bit'

        if bit_depth == cam.bit_depth_8:
            pil_image = PIL_image.fromarray(image)
            # pil_image_save = PIL_image.fromarray(image).convert('L')
            pil_image.save('%s/%s_%s.bmp' % (cam_id.decode('utf-8'), time_string, frame_counter))
            pil_image = pil_image.resize((400, 400))
            # pil_image.show()
            ascii_img = np_array_to_ascii(pil_image, 50, 0.5, False)
            for row in ascii_img:
                print(row)

        hdu = fits.PrimaryHDU(image)
        hdul = fits.HDUList([hdu])
        hdul.writeto('%s/%s_%s_str_%s_mode_%s_%s.fits' % (cam_id.decode('utf-8'), time_string, frame_counter,
                                                          stream_mode_str, read_mode_name_str, bit_depth_str))

        print("----   readMode %s / stream %s / bit %s / frame %s --------->" %
              (read_mode, stream_mode, bit_depth, frame_counter), end='')
        time.sleep(1)


print("path: %s" % os.path.dirname(__file__))

gui_start()
print("=    type q to quit        =")
command = ""
while command != "q":
    #command = input()
    breakpoint()













































sys.exit()
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

def init_camera_param(cam_id):
    if not cam.camera_params.keys().__contains__(cam_id):
        cam.camera_params[cam_id] = {'connect_to_pc': False,
                                     'connect_to_sdk': False,
                                     'EXPOSURE': c_double(1000.0 * 1000.0),
                                     'GAIN': c_double(54.0),
                                     'CONTROL_BRIGHTNESS': c_int(0),
                                     'CONTROL_GAIN': c_int(6),
                                     'CONTROL_EXPOSURE': c_int(8),
                                     'CONTROL_CURTEMP': c_int(14),
                                     'CONTROL_CURPWM': c_int(15),
                                     'CONTROL_MANULPWM': c_int(16),
                                     'CONTROL_COOLER': c_int(18),
                                     'chip_width': c_double(),
                                     'chip_height': c_double(),
                                     'image_width': c_uint32(),
                                     'image_height': c_uint32(),
                                     'pixel_width': c_double(),
                                     'pixel_height': c_double(),
                                     'bits_per_pixel': c_uint32(),
                                     'mem_len': c_ulong(),
                                     'stream_mode': c_uint8(0),
                                     'channels': c_uint32(),
                                     'read_mode_number': c_uint32(),
                                     'read_mode_index': c_uint32(),
                                     'read_mode_name': c_char('-'.encode('utf-8')),
                                     'prev_img_data': c_void_p(0),
                                     'prev_img': None,
                                     'handle': None,
                                     }


def test_frame(cam_id, stream_mode, bit_depth, read_mode):
    print('open camera %s' % cam_id.decode('utf-8'))
    cam.camera_params[cam_id]['handle'] = cam.so.OpenQHYCCD(cam_id)
    if cam.camera_params[cam_id]['handle'] is None:
        print('open camera error %s' % cam_id)

    success = cam.so.SetQHYCCDReadMode(cam.camera_params[cam_id]['handle'], read_mode)
    cam.camera_params[cam_id]['stream_mode'] = c_uint8(stream_mode)
    success = cam.so.SetQHYCCDStreamMode(cam.camera_params[cam_id]['handle'], cam.camera_params[cam_id]['stream_mode'])
    print('set StreamMode   =' + str(success))
    success = cam.so.InitQHYCCD(cam.camera_params[cam_id]['handle'])
    print('init Camera   =' + str(success))

    mode_name = create_string_buffer(cam.STR_BUFFER_SIZE)
    cam.so.GetReadModeName(cam_id, read_mode, mode_name)

    success = cam.so.SetQHYCCDBitsMode(cam.camera_params[cam_id]['handle'], c_uint32(bit_depth))

    success = cam.so.GetQHYCCDChipInfo(cam.camera_params[cam_id]['handle'],
                                       byref(cam.camera_params[cam_id]['chip_width']),
                                       byref(cam.camera_params[cam_id]['chip_height']),
                                       byref(cam.camera_params[cam_id]['image_width']),
                                       byref(cam.camera_params[cam_id]['image_height']),
                                       byref(cam.camera_params[cam_id]['pixel_width']),
                                       byref(cam.camera_params[cam_id]['pixel_height']),
                                       byref(cam.camera_params[cam_id]['bits_per_pixel']))

    print('info.   =' + str(success))
    cam.camera_params[cam_id]['mem_len'] = cam.so.GetQHYCCDMemLength(cam.camera_params[cam_id]['handle'])
    i_w = cam.camera_params[cam_id]['image_width'].value
    i_h = cam.camera_params[cam_id]['image_height'].value
    print('c-w:     ' + str(cam.camera_params[cam_id]['chip_width'].value), end='')
    print('    c-h: ' + str(cam.camera_params[cam_id]['chip_height'].value))
    print('p-w:     ' + str(cam.camera_params[cam_id]['pixel_width'].value), end='')
    print('    p-h: ' + str(cam.camera_params[cam_id]['pixel_height'].value))
    print('i-w:     ' + str(i_w), end='')
    print('    i-h: ' + str(i_h))
    print('bit: ' + str(cam.camera_params[cam_id]['bits_per_pixel'].value))
    print('mem len: ' + str(cam.camera_params[cam_id]['mem_len']))

    val_temp = cam.so.GetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_CURTEMP)
    val_pwm = cam.so.GetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_CURPWM)

    # todo  c_uint8 c_uint16??
    if bit_depth == cam.bit_depth_16:
        print('using c_uint16()')
        cam.camera_params[cam_id]['prev_img_data'] = (c_uint16 * int(cam.camera_params[cam_id]['mem_len'] / 2))()
    else:
        print('using c_uint8()')
        cam.camera_params[cam_id]['prev_img_data'] = (c_uint8 * cam.camera_params[cam_id]['mem_len'])()

    success = cam.QHYCCD_ERROR

    image_width_byref = c_uint32()
    image_height_byref = c_uint32()
    bits_per_pixel_byref = c_uint32()
    # TODO resolution
    cam.so.SetQHYCCDResolution(cam.camera_params[cam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                   c_uint32(i_h))

    if stream_mode == cam.stream_live_mode:
        success = cam.so.BeginQHYCCDLive(cam.camera_params[cam_id]['handle'])
        print('exp  Live = ' + str(success))

    frame_counter = 0
    time_string = '---'
    retry_counter = 0  # todo error control
    live_mode_skip_frame = 0

    while frame_counter < 2:
        time_string = datetime.now().strftime("%Y%m%d%H%M%S")
        if stream_mode == cam.stream_single_mode:
            success = cam.so.ExpQHYCCDSingleFrame(cam.camera_params[cam_id]['handle'])
            print('exp  single = ' + str(success))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_EXPOSURE, c_double(20000))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_GAIN, c_double(30))
        success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], cam.CONTROL_OFFSET, c_double(40))
        # success = cam.so.SetQHYCCDParam(cam.camera_params[cam_id]['handle'], CONTROL_EXPOSURE, EXPOSURE)
        if stream_mode == cam.stream_live_mode:
            success = cam.so.GetQHYCCDLiveFrame(cam.camera_params[cam_id]['handle'],
                                                byref(image_width_byref),
                                                byref(image_height_byref),
                                                byref(bits_per_pixel_byref),
                                                byref(cam.camera_params[cam_id]['channels']),
                                                byref(cam.camera_params[cam_id]['prev_img_data']))
            print('read  single = ' + str(success))
        if stream_mode == cam.stream_single_mode:
            success = cam.so.GetQHYCCDSingleFrame(cam.camera_params[cam_id]['handle'],
                                                  byref(image_width_byref),
                                                  byref(image_height_byref),
                                                  byref(bits_per_pixel_byref),
                                                  byref(cam.camera_params[cam_id]['channels']),
                                                  byref(cam.camera_params[cam_id]['prev_img_data']))
            print('read  single = ' + str(success))
        time.sleep(2)
        try_counter = 0
        while try_counter < 5 and success != cam.QHYCCD_SUCCESS:
            try_counter += 1
            print("success != 0  = " + str(success))
            time.sleep(1)

        if stream_mode == cam.stream_live_mode:
            live_mode_skip_frame += 1
            if live_mode_skip_frame < 3:
                print('skip frame in live mode  [%s]' % live_mode_skip_frame)
                continue
        frame_counter += 1

        cam.camera_params[cam_id]['prev_img'] = np.ctypeslib.as_array(cam.camera_params[cam_id]['prev_img_data'])
        print("---------------->" + str(len(cam.camera_params[cam_id]['prev_img'])))
        image_size = i_h * i_w
        print("image size =     " + str(image_size))
        print("prev_img_list sub length-->" + str(len(cam.camera_params[cam_id]['prev_img'])))
        print("Image W=" + str(i_w) + "        H=" + str(i_h))
        cam.camera_params[cam_id]['prev_img'] = cam.camera_params[cam_id]['prev_img'][0:image_size]
        image = np.reshape(cam.camera_params[cam_id]['prev_img'], (i_h, i_w))

        stream_mode_str = 'stream_mode'
        read_mode_name_str = mode_name.value.decode('utf-8').replace(' ', '_')
        bit_depth_str = 'bit_dep'
        if stream_mode == cam.stream_live_mode:
            stream_mode_str = 'live'
        else:
            stream_mode_str = 'single'
        if bit_depth == cam.bit_depth_16:
            bit_depth_str = '16bit'
        else:
            bit_depth_str = '8bit'

        if bit_depth == cam.bit_depth_8:
            pil_image = PIL_image.fromarray(image)
            # pil_image_save = PIL_image.fromarray(image).convert('L')
            pil_image.save('%s/%s_%s.bmp' % (cam_id.decode('utf-8'), time_string, frame_counter))
            pil_image = pil_image.resize((400, 400))
            # pil_image.show()
            ascii_img = np_array_to_ascii(pil_image, 50, 0.5, False)
            for row in ascii_img:
                print(row)

        hdu = fits.PrimaryHDU(image)
        hdul = fits.HDUList([hdu])
        hdul.writeto('%s/%s_%s_str_%s_mode_%s_%s.fits' % (cam_id.decode('utf-8'), time_string, frame_counter,
                                                          stream_mode_str, read_mode_name_str, bit_depth_str))

        print("----   readMode %s / stream %s / bit %s / frame %s --------->" %
              (read_mode, stream_mode, bit_depth, frame_counter), end='')
        time.sleep(1)


print("path: %s" % os.path.dirname(__file__))

gui_start()
print("=    type q to quit        =")
command = ""
while command != "q":
    command = input()