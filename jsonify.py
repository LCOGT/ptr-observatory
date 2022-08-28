# -*- coding: utf-8 -*-
"""
Created on Tue Aug 23 15:35:19 2022

@author: wrosingoutline of fixes:

    use the original wer config ormat named <obsy>.py

    When startng up a fresh instance ask the user for a parameter supplied
    in a console comand line.  for example 'obsy' in the above sentence.

    That file gets JSONIFIED into essentially config.json.  it is sent to AWS
    and used at the observatory to guarantee both sides are using the same
    configuration.

    chagne filter specification to be based on strings only and try to regularize
    filter names,

    deal with exposing certain classes of imagee with boht RGB and Mono camerase and
    multiple R G B exxposures.  Add CWL and BW spec to filters and a det QE curve as
    well.

    Do a much better job of mapping Unihedron to Luminance, prsumably V
"""

import json
import config as site_config
breakpoint()
with open("sample.json", "w") as outfile:
     json.dump(site_config.site_config, outfile)