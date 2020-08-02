# -*- coding: utf-8 -*-
"""
Created on Fri Jul 24 17:35:59 2020

@author: obs
"""
import pyserial


import serial

(read)

# 0 is minus UV, IR
# 1 is Triad
# 2,3,4 is cover.

# ser = None
# def  home(ser):
#     global ser
#     try:
#         ser.close()
#     except:
#         pass
    
# ser = serial.Serial("COM22')
#   File "<ipython-input-4-cc3daa6ee911>", line 1
#     ser = serial.Serial("COM22')
#                                 ^
# SyntaxError: EOL while scanning string literal

ser = serial.Serial("COM22", timeout=1)
# 

# ser.read()
# Out[6]: b'0'

# ser.send(b'3')
# Traceback (most recent call last):

#   File "<ipython-input-7-6b42865582c8>", line 1, in <module>
#     ser.send(b'3')

# AttributeError: 'Serial' object has no attribute 'send'


# ser.write(b'3')
# Out[8]: 1

# ser.write(b'0')
# Out[9]: 1

# ser.write(b'MXP')
# Out[10]: 3

# ser.write(b'3')
# Traceback (most recent call last):

#   File "<ipython-input-11-28dd1cf2d152>", line 1, in <module>
#     ser.write(b'3')

#   File "C:\ProgramData\Anaconda3\lib\site-packages\serial\serialwin32.py", line 315, in write
#     raise SerialException("WriteFile failed ({!r})".format(ctypes.WinError()))

# SerialException: WriteFile failed (PermissionError(13, 'The device does not recognize the command.', None, 22))


# ser = serial.Serial("COM22")

# ser.write(b'3')
# Out[13]: 1

# ser.read
# Out[14]: <bound method Serial.read of Serial<id=0x21fc9b6fb48, open=True>(port='COM22', baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, xonxoff=False, rtscts=False, dsrdtr=False)>

# ser.read()
# Out[15]: b'0'

# ser.write(b'2')
# Out[16]: 1

# ser.write(b'3')
# Out[17]: 1

# ser.write(b'1')
# Out[18]: 1

# ser.close
# Out[19]: <bound method Serial.close of Serial<id=0x21fc9b6fb48, open=True>(port='COM22', baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, xonxoff=False, rtscts=False, dsrdtr=False)>

# ser.close()

# ser = serial.Serial("COM22")

# ser.write(b'0')
# Out[22]: 1

# ser.read
# Out[23]: <bound method Serial.read of Serial<id=0x21ffadd3188, open=True>(port='COM22', baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, xonxoff=False, rtscts=False, dsrdtr=False)>

# ser.read()
# Out[24]: b'0'

# ser.write(b'1')
# Out[25]: 1

# ser.write(b'1')
# Out[26]: 1

# ser.write(b'2')
# Out[27]: 1

# ser.write(b'3')
# Out[28]: 1

# ser.write(b'4')
# Out[29]: 1

# ser.write(b'1')
# Out[30]: 1

# ser.write(b'0')
# Out[31]: 1

# ser.write(b'0')
# Out[32]: 1

# ser.write(b'3')
# Out[33]: 1

# ser.write(b'0')
# Out[34]: 1

# ser.write(b'1')
# Out[35]: 1

# ser.write(b'2')
# Out[36]: 1

# ser.write(b'3')
# Out[37]: 1

# ser.write(b'0')
# Out[38]: 1

# ser.write(b'2')
# Out[39]: 1

# ser.write(b'3')
# Out[40]: 1

# ser.write(b'3')
# Out[41]: 1