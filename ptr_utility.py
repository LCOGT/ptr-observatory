# -*- coding: utf-8 -*-
"""
ptr_utility  ptr_utility  ptr_utility  ptr_utility  ptr_utility  ptr_utility

Created on Sun Dec 11 23:27:31 2016

@author: obs

This code is confusing because it is mixing degree, hour and radian measure in
a way that is not obvious.  Hungarian might help here or append _d, _r, _h, _am, _as, _m, _s
Conversion constants could be CAP-case as in R2D, R2AS, H2S, etc.

"""


import os
import ephem
from ptr_config import site_config
from global_yard import g_dev

from functools import partial
from datetime import timezone, timedelta, datetime

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

def plog(*args, color=None, process=None, loud=True):
    '''
    Enhanced logging function with color support and module tracking.

    Parameters:
    - *args: Content to log
    - color: Text color (red, green, yellow, blue, magenta, cyan)
    - process: Subprocess name for context
    - loud: Whether to print to console (default True)
    '''
    # Define reset color code - required at the end of colored strings
    r = '\033[0m'

    # Handle None color to avoid "None" being printed
    c = color if color is not None else ''

    try:
        # Special case for progress indicators
        if len(args) == 1 and args[0] in ['.', '>']:
            if loud:
                print(f'{c}{args[0]}{r}')
            return

        # Convert args to a properly formatted string
        args_to_str = ''
        exposure_report = False

        for item in args:
            item_to_string = str(item)
            if item_to_string[-1] == ' ':
                args_to_str += str(item)
            else:
                args_to_str += str(item) + ' '  # Add space between fields

        args_to_str = args_to_str.strip()  # Eliminate trailing space

        # Remove unnecessary line feeds
        args_to_str = args_to_str.replace('\n\n\n', '\n').replace('\n\n', '\n')

        if args_to_str[:4] == '||  ':
            exposure_report = True
            args_to_str = args_to_str[4:]

        if loud:
            if process:
                print(f"{c}[{process}]{r} {args_to_str}")
            else:
                print(f'{args_to_str}')

        if not exposure_report:
            d_t = str(datetime.now(timezone.utc)).split('+')[0][:-3] + ' '
            log_entry = d_t

            # Make CSV-compatible by escaping quotes and enclosing in quotes if needed
            # Default process is "obs", but only for the logs.
            log_category = process or "obs"
            log_entry += f'"{log_category}"'

            # Escape quotes for CSV compatibility
            csv_safe_args = args_to_str.replace('"', '""')
            log_entry += f'"{csv_safe_args}"'

            with open(plog_path + 'nightlog.txt', 'a') as file:
                file.write(log_entry + '\n')
    except Exception as e:
        print(f"plog failed: {str(e)}")
        print("Failed to convert to string: ", args)

    return

def create_color_plog(process_id, rgb256=tuple):
    """
    Creates a module-specific plog function with predefined module name and color.

    Parameters:
    - module_name: Name of the module to be logged
    - default_color: Default color for this module's logs

    Returns:
    - A customized plog function for this module
    """
    rgb = lambda r, g, b: f'\033[38;2;{r};{g};{b}m'
    return partial(plog, process=process_id, color=rgb(*rgb256))
