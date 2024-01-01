# -*- coding: utf-8 -*-
"""
Created on Sun Dec 10 17:55:12 2023

@author: obs
"""

from math import *

#Enter Tpoint MA and ME Then execute this routine
aro_lift = -68            #Negative means 68 asec ABOVE the pole.
aro_latitude = 35.554298
cos_lat = cos(radians(aro_latitude))

#  Direct quotes from A-P GOTO1600 Manual.
#  "One turn of the altitude knob is approximately 0.41 degrees (24.6 arcminutes)."
lift_asec_per_turn = 24.6*60
spokes_per_turn = 4

#  "One full turn of the azimuth knob is approximately 0.3733 degrees (22.4 arcminutes)."
#  "Small graduations  are 0.74 arcminutes; long graduations are 3.7 arcminutes."
az_asec_per_small_grad = 0.74*60
az_asec_per_major_grad = 3.7*60

IH = 188

ID =405

MA = 950

ME = -240

#aro_lift = ME + adjust
#aro_lift - ME = adjust
adjust = round(aro_lift - ME, 1)
turns = round(adjust/lift_asec_per_turn, 2)
spokes = round(turns*spokes_per_turn, 1)
az = round(MA/cos_lat, 1)
small_az = round(az/az_asec_per_small_grad, 1)
major_az = round(az/az_asec_per_major_grad, 1)
#print('-- positive means Lower - ClockWise, negative means Raise - counterCW.')
print('\n\n')
print("Polar Axis alignment derived from Tpoint run 20231211.DAT.")
print('\n\n')
if adjust > 0:
    print("Elevation Adjustment:  ", adjust, 'asec Clockwise, as seen from above. Lower Tel, raise tail.')
    print("Elevation Adjustment:  ", turns, 'turns Clockwise, as seen from above.')
    print("Elevation Adjustment:  ", spokes, 'spokes Clockwise, as seen from above.')
else:
    print("Elevation Adjustment:  ", adjust, 'asec COUNTER Clockwise.  Raise Tel, lower tail.')
    print("Elevation Adjustment:  ", turns, 'turns COUNTER Clockwise')
    print("Elevation Adjustment:  ", spokes, 'spokes COUNTER Clockwise')
print('\n\n')
if az > 0:
    print("Azimuth Adjustment:  ", az, 'asec COUNTER-Clockwise, as seen from above.' )
    print("Azimuth Adjustment:  ", small_az, 'small graduations COUNTER-Clockwise, as seen from above.' )
    print("Azimuth Adjustment:  ", major_az, 'major graduations COUNTER-Clockwise, as seen from above.' )
    print("\n")
    print("First: Check both az knobs are snug. Second: back off left az knob the required amount,")
    print("then turn right az knob the suggested amount. Then snug other side.")
else:
    print("Azimuth Adjustment:  ", alt, 'asec CLOCKWISE, as seen from above.' )
    print("Azimuth Adjustment:  ", small_az, 'small graduations COUNTER-Clockwise, as seen from above.' )
    print("AAzimuth Adjustment:  ", major_az, 'major graduations COUNTER-Clockwise, as seen from above.' )
    print('\n')
    print('1: Check right az knob is snug, 2) back off left az knob, then turn right az knob the suggested amount. then snug other side.')
print('\n\n')
print("Last, double check the mount is level and the black tapes line up.")
print('Clear Skies!')