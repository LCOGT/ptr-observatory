# -*- coding: utf-8 -*-
"""
Created on Sun Dec 10 17:55:12 2023

@author: obs
"""

from math import *

print('''
In the northern hemisphere, the ideal ME value for a particular telescope is minus
the figure in the above table. For example, an equatorial telescope mount at 40◦ latitude
and 500 meters above sea level would ideally have ME= −63′′ . If TPOINT estimated
that ME was about +150′′ , the correct action to take would be to raise the polar axis by
150 − (−63) = 213 arcseconds.  ARO polar axis is ideally -68 asec above the true pole.

The other polar axis misalignment term, MA, is more straightforward: the ideal value is
always zero. In either hemisphere, an MA value of (say) +93′′ could be eliminated by
rotating the mount 93′′/ cos ϕ (latitude) anticlockwise (as seen from above), where ϕ is the latitude
of the site. Conversely, a negative MA value would require a clockwise adjustment.
''')
print('\n\n')


#Enter Tpoint MA and ME Then execute this routine
aro_lift = -68            #Negative means 68 asec ABOVE the pole.
aro_latitude = 35.554298
cos_lat = cos(radians(aro_latitude))

#  Direct quotes from A-P GOTO1600 Manual.
#  "One turn of an altitude knob is approximately 0.41 degrees (24.6 arcminutes)."

lift_asec_per_turn = 24.6*60
lift_asec_per_spoke= lift_asec_per_turn/4.

#  "One full turn of the azimuth knob is approximately 0.3733 degrees (22.4 arcminutes)."
#  "Small graduations  are 0.74 arcminutes; long graduations are 3.7 arcminutes."
#  Counter-clockwise turn of lifting knob RAISES the polar axis.

az_asec_per_small_grad = 0.74*60
az_asec_per_major_grad = 3.7*60

IH = 188

ID =405

MA = -128 #-250

ME = -1373 #-342


#breakpoint()
alt = round(aro_lift - ME, 1)
alt_turns = round(alt/lift_asec_per_turn, 2)
alt_spokes = round(alt/lift_asec_per_spoke, 2)
az = round(MA/cos_lat, 1)
small_az = round(az/az_asec_per_small_grad, 2)
major_az = round(az/az_asec_per_major_grad, 2)

print("Polar Axis alignment derived from Tpoint run 20231211.DAT.")
print('\n')
print("Elevation Error:  ", ME, "    Azimuth error:  ", MA)
print('\n')
print("Note, 4 spokes on the elevation wheel, so 1 spoke = 0.25 turns. \n")
if alt < 0:
    print("Elevation Adjustment:  ", -alt, 'asec COUNTER Clockwise, as seen from above. Raise Tel above Pole, lower tail of Tel.')
    print("Need to raise the polar axis!\n")
    print("Elevation Adjustment:  ", -alt_turns, 'turns COUNTER Clockwise, as seen from above.')
    print("Elevation Adjustment:  ", -alt_spokes, 'spokes COUNTER Clockwise, as seen from above.')
    print("\n")
else:
    print("Need to lower the polar axis!")
    print("Elevation Adjustment:  ", alt, 'asec  Clockwise. Lower Tel to Pole, raise tail of Tel. \n')
    print("Elevation Adjustment:  ", alt_turns, 'turns Clockwise')
    print("Elevation Adjustment:  ", alt_spokes, 'spokes Clockwise')
    print("\n")

if az > 0:
   print("Azimuth Adjustment:  ", az, 'asec COUNTER-CLOCKWISE, as seen from above.\n' )
   print("First: Check both az knobs are snug. Second: back off left az knob the required amount,")
   print("then turn right az knob the required amount. Then snug other side. \n ")
   print("Azimuth Adjustment:  ", small_az, 'small graduations COUNTER-CLOCKWISE, as seen from above. \n \
          Loosen LEFT knob to make room for counter-clockwise travel \n \
          Tighten RIGHT knob to push counter-clockwise.' )
   print("Azimuth Adjustment:  ", major_az, 'major graduations COUNTER-CLOCKWISE, as seen from above. \n \
          Loosen LEFT knob to make room for counter-clockwise travel \n \
          Tighten RIGHT knob to push counter-clockwise.' )
   print('\n')

else:
    print("First: Check both az knobs are snug. Second: back off left az knob the required amount,")
    print("then turn right az knob the required amount. Then snug other side. \n ")
    print("Azimuth Adjustment:  ", az, 'asec CLOCKWISE, as seen from above.\n' )
    print("Azimuth Adjustment:  ", -small_az, 'small graduations CLOCKWISE, as seen from above. \n \
           Loosen RIGHT knob to make room for clockwise travel \n \
           Tighten LEFT knob to push clockwise.' )
    print("Azimuth Adjustment:  ", -major_az, 'major graduations CLOCKWISE, as seen from above. \n \
           Loosen RIGHT knob to make room for clockwise travel \n \
           Tighten LEFT knob to push clockwise.' )
    print('\n')

print("Last, double check the dec axis and telescope tube are level, cluches are tight, and the black tapes line up.")
print('Clear Skies!')