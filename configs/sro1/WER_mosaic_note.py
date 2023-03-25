# -*- coding: utf-8 -*-
"""
Created on Thu Nov 24 21:46:18 2022

@author: wer
"""

#                'x_field_deg': 1.3333,   #   round(4784*1.0481/3600, 4),
#                'y_field_deg': 1.0665,   #  round(3194*1.0481/3600, 4),

'''

SQUARE is just a vertical shift of 0.2668 and a vert shift of Y center by 0.1334

1deg x 1deg is satisifed by the chip.
1.414 x 1.414  Step X over 0.0809  X center over 0.0406
step Y up 0.3477 AND Raise center 0.1739
So this mosaic has lots of overlap

2.0 x 2.0 deg:
    Step X 0.6667 and X center 0.3334
    Step Y 0.9335 and Y center 0.4668   So we have about a 7% overlap.
    Add  a fifth image dead center?  That should permit a good stich-together