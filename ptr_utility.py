# -*- coding: utf-8 -*-
"""
Created on Sun Dec 11 23:27:31 2016

@author: obs

This code is confusing because it is mixing degree, hour and radian measure in
a way that is not obvious.  Hungarian might help here or append _d, _r, _h, _am, _as, _m, _s
Conversion constants could be CAP-case as in R2D, R2AS, H2S, etc.

"""


from datetime import datetime
import os
import ephem
from ptr_config import site_config
from obs_config import LOUD, ENG, SERIAL
from global_yard import g_dev

from datetime import timezone, timedelta 

DAY_Directory= g_dev['day']


now_utc = datetime.now(timezone.utc) # timezone aware UTC, shouldn't depend on clock time.

int_sunrise_hour=ephem.Observer().next_rising(ephem.Sun()).datetime().hour + 1
if int(now_utc.hour) < int_sunrise_hour:
    now_utc = now_utc - timedelta(days=1)
DAY_Directory = str(now_utc.year) + str(now_utc.month) + str(now_utc.day)

try:
    if not os.path.exists(site_config['plog_path']  + 'plog/'):
        os.makedirs(site_config['plog_path']  + 'plog/')
    plog_path = site_config['plog_path']  + 'plog/' + DAY_Directory + '/'

except KeyError:
    try:
        #plog_path = site_config['archive_path'] + '/' + site_config['obs_id'] + '/' + DAY_Directory + '/'

        obsid_path = str(site_config["archive_path"] + '/' + site_config['obs_id'] + '/').replace('//','/')
        plog_path= obsid_path + 'plog/'
        if not os.path.exists(obsid_path):
            os.makedirs(obsid_path)
        if not os.path.exists(plog_path):
            os.makedirs(plog_path)
        plog_path = obsid_path + 'plog/' + DAY_Directory + '/'
        if not os.path.exists(plog_path):
            os.makedirs(plog_path)
        #breakpoint()

        # if not g_dev['obs'].obsid_path  + 'plog/':
        #     os.makedirs(g_dev['obs'].obsid_path + 'plog/')

    except:
        if not site_config['archive_path'] + '/' + site_config['obs_id'] + '/'  + 'plog/':
            os.makedirs(site_config['archive_path'] + '/' + site_config['obs_id'] + '/' + 'plog/')
        plog_path = site_config['archive_path'] + '/' + site_config['obs_id'] + '/' + 'plog/' + DAY_Directory + '/'

os.makedirs(plog_path, exist_ok=True)

def plog(*args, loud = True):
    '''
    loud not used, consider adding an optional incoming module
    and error level, also make file format compatible with csv.
    '''

    try:
        if len(args) == 1 and args[0] in ['.', '>']:
            print(args[0])
            return
        args_to_str = ''
        exposure_report = False
        for item in args:
            item_to_string = str(item)
            if item_to_string[-1] == ' ':
                args_to_str += str(item)
            else:
                args_to_str += str(item) + ' '  #  Add space between fields
        args_to_str = args_to_str.strip()   #Eliminate trailing space.
        # ToDo  Need to strip unnecessary line feeds  '\n'
        if args_to_str[:4] == '||  ':
            exposure_report = True
            args_to_str = args_to_str[4:]
        print(args_to_str)
        if not exposure_report:
            d_t = str(datetime.utcnow()) + ' '
            with open(plog_path + 'nightlog.txt', 'a') as file:
                file.write(d_t + " " + args_to_str +'\n')

    except:
        print("plog failed to convert to string:  ", args)

    #Add logging here.

    return
