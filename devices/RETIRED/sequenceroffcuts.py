# -*- coding: utf-8 -*-
"""
Created on Mon Nov 25 19:43:29 2024

@author: psyfi
"""

# COLLECTING A TWO SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 2s exposure dark frames.")
req = {'time': 2,  'script': 'True', 'image_type': 'twosec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}

# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)

if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A THREEPOINTFIVE SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 3.5s exposure dark frames.")
req = {'time': 3.5,  'script': 'True', 'image_type': 'threepointfivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}

# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})

g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A FIVE SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 5s exposure dark frames.")
req = {'time': 5,  'script': 'True', 'image_type': 'fivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}

# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()


# COLLECTING A SEVENPOINTFIVE SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 7.5s exposure dark frames.")
req = {'time': 7.5,  'script': 'True', 'image_type': 'sevenpointfivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A TEN SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 ten second exposure dark frames.")
req = {'time': 10,  'script': 'True', 'image_type': 'tensec_exposure_dark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A FIFTEEN SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 15 second exposure dark frames.")
req = {'time': 15,  'script': 'True', 'image_type': 'fifteensec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A TWENTY SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 20 second exposure dark frames.")
req = {'time': 20,  'script': 'True', 'image_type': 'twentysec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A THIRTY SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 30 second exposure dark frames.")
req = {'time': 30,  'script': 'True', 'image_type': 'thirtysec_exposure_dark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A BROADBAND SMARTSTACK BIASDARK FRAME
plog("Expose " + str(stride) +" 1x1 broadband smstack biasdark frames.")
req = {'time': broadband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'broadband_ss_biasdark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A NARROWBAND SMARTSTACK BIASDARK FRAME
# But only if there is a filterwheel, otherwise no point.
if not g_dev["fil"].null_filterwheel:
    plog("Expose " + str(stride) +" 1x1 narrowband smstack biasdark frames.")
    req = {'time': narrowband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'narrowband_ss_biasdark'}
    opt = {'count': 2*min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()


# If we've been collecting bias darks for TWO HOURS, bail out... someone has asked for too many!
if time.time() - bias_darks_started > 7200:
    self.bias_dark_latch = False
    break

# COLLECTING A 0.0045 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.0045:
    plog("Expose " + str(5*stride) +" 1x1 0.0045 second exposure dark frames.")
    req = {'time': 0.0045,  'script': 'True', 'image_type': 'pointzerozerofourfive_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()


# COLLECTING A 0.0004 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.0004:
    plog("Expose " + str(5*stride) +" 1x1 0.0004 second exposure dark frames.")
    req = {'time': 0.0004,  'script': 'True', 'image_type': 'fortymicrosecond_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A 0.00004 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.00004:
    plog("Expose " + str(5*stride) +" 1x1 0.00004 second exposure dark frames.")
    req = {'time': 0.00004,  'script': 'True', 'image_type': 'fourhundredmicrosecond_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()


# COLLECTING A 0.015 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.015:
    plog("Expose " + str(5*stride) +" 1x1 0.015 second exposure dark frames.")
    req = {'time': 0.015,  'script': 'True', 'image_type': 'onepointfivepercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A 0.05 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.05:
    plog("Expose " + str(5*stride) +" 1x1 0.05 second exposure dark frames.")
    req = {'time': 0.05,  'script': 'True', 'image_type': 'fivepercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A 0.1 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.1:
    plog("Expose " + str(5*stride) +" 1x1 0.1 second exposure dark frames.")
    req = {'time': 0.1,  'script': 'True', 'image_type': 'tenpercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A 0.25 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.25:
    plog("Expose " + str(5*stride) +" 1x1 0.25 second exposure dark frames.")
    req = {'time': 0.25,  'script': 'True', 'image_type': 'quartersec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A Half Second EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 half-second exposure dark frames.")
req = {'time': 0.5,  'script': 'True', 'image_type': 'halfsec_exposure_dark'}
opt = {'count':  min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A 0.75 Second EXPOSURE DARK FRAME
if min_flat_exposure <= 0.75:
    plog("Expose " + str(5*stride) +" 1x1 0.75 second exposure dark frames.")
    req = {'time': 0.75,  'script': 'True', 'image_type': 'threequartersec_exposure_dark'}
    opt = {'count': min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

# COLLECTING A one Second EXPOSURE DARK FRAME
if min_flat_exposure <= 1.0:
    plog("Expose " + str(5*stride) +" 1x1  1 second exposure dark frames.")
    req = {'time': 1,  'script': 'True', 'image_type': 'onesec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()

# COLLECTING A one and a half Second EXPOSURE DARK FRAME
if min_flat_exposure <= 1.5:
    plog("Expose " + str(5*stride) +" 1x1  1.5 second exposure dark frames.")
    req = {'time': 1.5,  'script': 'True', 'image_type': 'oneandahalfsec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    # Check it is in the park position and not pointing at the sky.
    # It can be pointing at the sky if cool down open is triggered during the biasdark process
    if not g_dev['obs'].mountless_operation:
        g_dev['mnt'].park_command({}, {})
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    if self.stop_script_called:
        g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
        self.bias_dark_latch = False
        return
    if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
        self.bias_dark_latch = False
        break
    g_dev['obs'].request_scan_requests()


# COLLECTING A BIAS FRAME
# COLLECT BIAS FRAMES LATER as there is no way to know whether bias frames are affected
# by slowly-closing shutters... whereas darks can be rejected.
plog("Expose " + str(stride) +" 1x1 bias frames.")
req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
# Check it is in the park position and not pointing at the sky.
# It can be pointing at the sky if cool down open is triggered during the biasdark process
if not g_dev['obs'].mountless_operation:
    g_dev['mnt'].park_command({}, {})
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break
g_dev['obs'].request_scan_requests()

plog("Expose 1x1 dark of " \
     + str(dark_count) + " using exposure:  " + str(dark_exp_time) )
req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
opt = {'count': 1, 'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                   do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
if self.stop_script_called:
    g_dev["obs"].send_to_user("Cancelling out of calibration script as stop script has been called.")
    self.bias_dark_latch = False
    return
if ephem.now() + (dark_exp_time + cycle_time + 30)/86400 > ending:
    self.bias_dark_latch = False
    break


****************** MIDNIGHT DARK ROUTINE

# COLLECTING A TWO SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 2s exposure dark frames.")
req = {'time': 2,  'script': 'True', 'image_type': 'twosec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    plog (self.stop_script_called)
    plog (g_dev['obs'].open_and_enabled_to_observe)
    plog ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark']))
    return

# COLLECTING A Three point five sec SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 3.5s exposure dark frames.")
req = {'time': 3.5,  'script': 'True', 'image_type': 'threepointfivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}

g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    plog (self.stop_script_called)
    plog (g_dev['obs'].open_and_enabled_to_observe)
    plog ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark']))
    return


# COLLECTING A FIVE SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 5s exposure dark frames.")
req = {'time': 5,  'script': 'True', 'image_type': 'fivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A SEVENPOINTFIVE SECOND EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 7.5s exposure dark frames.")
req = {'time': 7.5,  'script': 'True', 'image_type': 'sevenpointfivesec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A TEN SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 ten second exposure dark frames.")
req = {'time': 10,  'script': 'True', 'image_type': 'tensec_exposure_dark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A FIFTEEN SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 15 second exposure dark frames.")
req = {'time': 15,  'script': 'True', 'image_type': 'fifteensec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A TWENTY SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 20 second exposure dark frames.")
req = {'time': 20,  'script': 'True', 'image_type': 'twentysec_exposure_dark'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A THIRTY SECOND EXPOSURE DARK FRAME
plog("Expose " + str(2*stride) +" 1x1 30 second exposure dark frames.")
req = {'time': 30,  'script': 'True', 'image_type': 'thirtysec_exposure_dark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A BROADBAND SMARTSTACK BIASDARK FRAME
plog("Expose " + str(stride) +" 1x1 broadband smstack biasdark frames.")
req = {'time': broadband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'broadband_ss_biasdark'}
opt = {'count': 2*min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A NARROWBAND SMARTSTACK BIASDARK FRAME
if not g_dev["fil"].null_filterwheel:
    plog("Expose " + str(stride) +" 1x1 narrowband smstack biasdark frames.")
    req = {'time': narrowband_ss_biasdark_exp_time,  'script': 'True', 'image_type': 'narrowband_ss_biasdark'}
    opt = {'count': 2*min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.0045 Second EXPOSURE DARK FRAME
if min_exposure <= 0.0045:
    plog("Expose " + str(5*stride) +" 1x1 0.0045 second exposure dark frames.")
    req = {'time': 0.0045,  'script': 'True', 'image_type': 'pointzerozerofourfive_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.0004 Second EXPOSURE DARK FRAME
if min_exposure <= 0.0004:
    plog("Expose " + str(5*stride) +" 1x1 0.0004 second exposure dark frames.")
    req = {'time': 0.0004,  'script': 'True', 'image_type': 'fortymicrosecond_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.00004 Second EXPOSURE DARK FRAME
if min_exposure <= 0.00004:
    plog("Expose " + str(5*stride) +" 1x1 0.00004 second exposure dark frames.")
    req = {'time': 0.00004,  'script': 'True', 'image_type': 'fourhundredmicrosecond_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.015 Second EXPOSURE DARK FRAME
if min_exposure <= 0.015:
    plog("Expose " + str(5*stride) +" 1x1 0.015 second exposure dark frames.")
    req = {'time': 0.015,  'script': 'True', 'image_type': 'onepointfivepercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.05 Second EXPOSURE DARK FRAME
if min_exposure <= 0.05:
    plog("Expose " + str(5*stride) +" 1x1 0.05 second exposure dark frames.")
    req = {'time': 0.05,  'script': 'True', 'image_type': 'fivepercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.1 Second EXPOSURE DARK FRAME
if min_exposure <= 0.1:
    plog("Expose " + str(5*stride) +" 1x1 0.1 second exposure dark frames.")
    req = {'time': 0.1,  'script': 'True', 'image_type': 'tenpercent_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A 0.25 Second EXPOSURE DARK FRAME
if min_exposure <= 0.25:
    plog("Expose " + str(5*stride) +" 1x1 0.25 second exposure dark frames.")
    req = {'time': 0.25,  'script': 'True', 'image_type': 'quartersec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A Half Second EXPOSURE DARK FRAME
plog("Expose " + str(5*stride) +" 1x1 half-second exposure dark frames.")
req = {'time': 0.5,  'script': 'True', 'image_type': 'halfsec_exposure_dark'}
opt = {'count':  min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

# COLLECTING A 0.75 Second EXPOSURE DARK FRAME
if min_exposure <= 0.75:
    plog("Expose " + str(5*stride) +" 1x1 0.75 second exposure dark frames.")
    req = {'time': 0.75,  'script': 'True', 'image_type': 'threequartersec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A one Second EXPOSURE DARK FRAME
if min_exposure <= 1.0:
    plog("Expose " + str(5*stride) +" 1x1  1 second exposure dark frames.")
    req = {'time': 1,  'script': 'True', 'image_type': 'onesec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A one and a half Second EXPOSURE DARK FRAME
if min_exposure <= 1.5:
    plog("Expose " + str(5*stride) +" 1x1  1.5 second exposure dark frames.")
    req = {'time': 1.5,  'script': 'True', 'image_type': 'oneandahalfsec_exposure_dark'}
    opt = {'count':  min_to_do,  \
           'filter': 'dk'}
    g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                    do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
    g_dev['obs'].request_scan_requests()
    if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
        return

# COLLECTING A BIAS FRAME
# COLLECT BIAS FRAMES LATER as there is no way to know whether bias frames are affected
# by slowly-closing shutters... whereas darks can be rejected.
plog("Expose " + str(stride) +" 1x1 bias frames.")
req = {'time': 0.0,  'script': 'True', 'image_type': 'bias'}
opt = {'count': min_to_do,  \
       'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)
g_dev['obs'].request_scan_requests()
if self.stop_script_called or g_dev['obs'].open_and_enabled_to_observe or ( not (events['Astro Dark'] <=  ephem.now() < events['End Astro Dark'])): # Essentially if stop script of the roof opens or it is out of astrodark, bail out of calibrations
    return

plog("Expose 1x1 dark of " \
     + str(1) + " using exposure:  " + str(dark_exp_time) )
req = {'time': dark_exp_time ,  'script': 'True', 'image_type': 'dark'}
opt = {'count': 1, 'filter': 'dk'}
g_dev['cam'].expose_command(req, opt, user_id='Tobor', user_name='Tobor', user_roles='system', no_AWS=False, \
                   do_sep=False, quick=False, skip_open_check=True,skip_daytime_check=True)