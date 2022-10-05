# -*- coding: utf-8 -*-
"""
Created on Thu Aug 5 21:19:46 2021

@author: obs
"""
import serial


thorium_mirror = bytes([0x0D, 0x01, 0x42, 0xA0, 0x10])
tungsten_mirror = bytes([0x0D, 0x01, 0x42, 0x90, 0x20])
blue_mirror = bytes([0x0D, 0x01, 0x42, 0xC0, 0xF0])
white_mirror = bytes(
    [0x0D, 0x01, 0x42, 0xD0, 0xE0]
)  # Combining Blue and Tungsten_halogen
solar_mirror = bytes([0x0D, 0x01, 0x42, 0x90, 0x20])  # Wrong spec, just a placeholder.
dark_mirror = bytes(
    [0x0D, 0x01, 0x42, 0x80, 0x30]
)  # Mirror in AGU is deployed, No Light
no_light_no_mirror = bytes(
    [0x0D, 0x01, 0x42, 0x00, 0xB0]
)  # Mirror in AGU out of the way
arc_status = "unknown"


def set_arc_box(com_port, cmd):
    """Sets calibration lamps to a specified configuration."""

    _com = serial.Serial(
        com_port, baudrate=2400, bytesize=8, parity="N", stopbits=1, timeout=0.1
    )
    if cmd == "Thorium":
        cmd_arc = thorium_mirror
    elif cmd == "Tungsten":
        cmd_arc = tungsten_mirror
    elif cmd == "Blue":
        cmd_arc = blue_mirror
    elif cmd == "White":
        cmd_arc = white_mirror
    elif cmd == "Solar":
        cmd_arc = solar_mirror
    elif cmd == "Dark_mirror":
        cmd_arc = dark_mirror
    elif cmd == "Object" or cmd == "Reset":
        cmd_arc = no_light_no_mirror
    else:
        print("Arc box command not recognized.")

    _com.write(cmd_arc * 2)
    arc_status = cmd
    _com.close()
    print("Arc_box:  ", cmd)


def arc_lamp_status():
    # This part needs a redo. Placeholder
    if arc_status is not None:
        return arc_status
