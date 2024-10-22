# -*- coding: utf-8 -*-
"""
polar_calculation.py  polar_calculation.py  polar_calculation.py

Created on Sun Dec 10 17:55:12 2023

@author: obs
"""

import math

print('''
From the TPOINT manual:
    (Table referenced below is deleted.  Instead:)

ARO polar axis ME is ideally "-68 asec", so 68 asec ABOVE the true pole.

In the northern hemisphere, the ideal ME(elevation) value for a particular telescope is minus
the figure in the above table. For example, an equatorial telescope mount at 40◦ latitude
and 500 meters above sea level would ideally have ME= −63′′ . If TPOINT estimated
that ME was about +150′′ , the correct action to take would be to raise the polar axis by
150 − (−63) = 213 arcseconds.


The other polar axis misalignment term, MA(azimuth), is more straightforward: the ideal value is
always zero. In either hemisphere, an MA value of (say) +93′′ could be eliminated by
rotating the mount 93′′/ cos ϕ (latitude) anticlockwise (as seen from above), where ϕ is the latitude
of the site. Conversely, a negative MA value would require a clockwise adjustment.
''')
print('\n\n')


#Enter Tpoint MA and ME Then execute this routine
aro_lift = -68            #Negative means 68 asec ABOVE the pole.
aro_latitude = 35.554298
cos_lat = math.cos(math.radians(aro_latitude))

#  Direct quotes from A-P GOTO1600 Manual.
#  "One turn of an altitude knob is approximately 0.41 degrees (24.6 arcminutes)."
#  Counter-clockwise turn of lifting knob RAISES the polar axis.

lift_asec_per_turn = 24.6*60
lift_asec_per_spoke= lift_asec_per_turn/4.

#  "One full turn of the azimuth knob is approximately 0.3733 degrees (22.4 arcminutes)."
#  "Small graduations  are 0.74 arcminutes; long graduations are 3.7 arcminutes."

az_asec_per_full_turn = 22.4*60
az_asec_per_small_grad = 0.74*60
az_asec_per_major_grad = 3.7*60

IH =+2574
ID =  -3767

MA = +598
  #20240524-3   455  Errors doubled and wrong sign.

ME = +4103


  #Both signs verified   620



alt = round(ME -(aro_lift), 1)  #  Per TPOINT Manual. Positive means Raise
alt_turns = round(alt/lift_asec_per_turn, 2)
alt_spokes = round(alt/lift_asec_per_spoke, 2)
az = round(MA/cos_lat, 1) # Per TPOINT manual Positive means  CCW.
small_az = round(az/az_asec_per_small_grad, 2)
major_az = round(az/az_asec_per_major_grad, 2)

print("Polar Axis alignment derived from Tpoint run 20241022-4.DAT.")
print('\n')
print("Elevation Error:  ", ME, "asec.     Azimuth error:  ", MA, "asec.")
print('\n')
print("Note, 4 spokes on the elevation wheel, so 1 spoke = 0.25 turns. \n")

print("Position now West of the mount, so you are looking East at the side of the mount.")

print("Your LEFT hand should be able to reach the 4-spoked knob.\n")
print("You may also stand North of the mount looking South.")

print("Summary of Procedure: \n")
print("Loosen the four button heads on each side so the axis housing can move in the saddle. \n")

if alt > 0:
    print("Elevation Adjustment:  ", alt, 'asec  Raise Tel axis above Pole, lower tail of Tel axis. \n')
    print("Need to raise the polar axis! For the lifting screw, that means tighten. \n")
    print("Pick one of the two following options.\n")
    print("Elevation Adjustment:  ", alt_turns, 'turns COUNTER Clockwise, as seen from above.\n')
    print("Elevation Adjustment:  ", alt_spokes, 'spokes COUNTER Clockwise, as seen from above.')
    print("Note again:  The mount should be lifting. The turns will need some force.\n")
else:
    print("Need to lower the polar axis!  For the lifting screw, that means loosen. \n")
    print("Elevation Adjustment:  ", -alt, 'asec   Lower Tel axis to Pole, raise tail of Tel axis. \n')
    print("Pick one of the two following options.\n")
    print("Elevation Adjustment:  ", -alt_turns, 'turns Clockwise, as you look down above the spoked wheel')
    print("Elevation Adjustment:  ", -alt_spokes, 'spokes Clockwise, as you look down above the spoked wheel\n')
    print('Caution. Note Tightening the screw into the crossbar RAISES the polar axis -- and is a Counter Clockwise move.')
    print('Lowering the screw out of the crossbar Lowers the polar axis -- and is a Clockwise move.')

    print("Last Snug up the four button heads on each side to lock in the elevation. \n\n")

print("Position now South of the mount, so you are looking North.\n")
print("Summary of Procedure:\n")

print("First: Check both az knobs are snug. Second: back off one knob the required amount, then ")
print("turn the other knob to push against the fixed tang the required amount. Then snug other side. \n ")

print("Note this is a bit un-intuitive. The knobs push on a tang coming from the Az pivot.")
print("So tightening the Right-hand knob rotates the axis to the East.  Left-hand knob pushes to the West. \n ")

if az < 0:
   print("Azimuth Adjustment:  ",-az, 'asec CLOCKWISE, as seen from above.\n' )
   print("Pick only one of the following two ways to specify a move:\n")
   print("Azimuth Adjustment:  ", -small_az, "small graduations CLOCKWISE, as seen from above. \n \
          Loosen RIGHT knob to make room for clockwise. \n \
          Tighten LEFT knob to push clockwise. \n" )
   print("Azimuth Adjustment:  ", -major_az, 'major graduations COUNTER-CLOCKWISE, as seen from above. \n \
          Loosen RIGHT knob to make room for clockwise travel \n \
          Tighten LEFT knob to push clockwise. \n \
          Snug up Right knob' )
   print('\n')

else:

    print("Azimuth Adjustment:  ",az, 'asec COUNTER-CLOCKWISE, as seen from above.\n' )
    print("Pick only one of the following two ways to specify a move:\n")
    print("Azimuth Adjustment:  ", small_az, 'small graduations COUNTER-CLOCKWISE, as seen from above. \n \
           Loosen RIGHT knob (a lot, 5 major grads) to make room for counter-clockwise travel. \n \
           Tighten LEFT knob to push counter-clockwise -- front of polar axis moves toward the west. \n' )
    print("Azimuth Adjustment:  ", major_az, 'major graduations COUNTER-CLOCKWISE, as seen from above. \n \
           Loosen RIGHT knob (a lot, 5 major grads)  to make room for counter-clockwise travel. \n \
           Tighten LEFT knob to push counter-clockwise -- front of polar axis moves toward the west. \n')
    print("Snug up the RIGHT knob.")
    print('\n')

print("Last, carefully double check the dec axis and telescope tube are level, clutches are tight, and adjust the black tapes, if necessary, so they line up.")
print('Clear Skies!')