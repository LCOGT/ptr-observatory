
# -*- coding: utf-8 -*-
'''
Created on Fri Feb 07,  11:57:41 2020
20220902  Update for status corruption incident.  This worked today.

@author: wrosing
'''

obs_id = 'eco2' # THIS IS THE NAME OF THIS OBSERVATORY if it is an obs
                    #\\192.168.1.57\SRO10-Roof  r:
                    #SRO-Weather (\\192.168.1.57) w:
                    #Username: wayne_rosingPW: 29yzpe
                    


site_config = {
    # Instance type specifies whether this is an obs or a wema
    'instance_type' : 'obs',
    # If this is not a wema, this specifies the wema that this obs is connected to
    'wema_name' : 'eco',
    # The unique identifier for this obs
    'obs_id': 'eco2',
    
    
    
    
    # Name, local and owner stuff
    'name': 'Eltham College Observatory, 0m28',
    'airport_code':  'MEL: Melbourne Airport',
    'location': 'Eltham, Victoria, Australia',
    'telescope_description': 'n.a.',
    'observatory_url': 'https://elthamcollege.vic.edu.au/',   #  This is meant to be optional
    'observatory_logo': None,   # I expect these will ususally end up as .png format icons
    'mpc_code':  'ZZ23',    #This is made up for now.
    'description':  '''Eltham College is an independent, non-denominational, co-educational day school situated in Research, an outer suburb north east of Melbourne.
                    ''',    #  i.e, a multi-line text block supplied and eventually mark-up formatted by the owner.
    'owner':  ['google-oauth2|112401903840371673242'],  # WER,  Or this can be
                                                        # some aws handle.
    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "KVH", "TELOPS", "TB", "DH", 'KC'],
    
    
   
    
    
    # Default safety settings
    'safety_check_period': 45,  # MF's original setting.
    'closest_distance_to_the_sun': 45,  # Degrees. For normal pointing requests don't go this close to the sun.
    'closest_distance_to_the_moon': 3,  # Degrees. For normal pointing requests don't go this close to the moon.
    'minimum_distance_from_the_moon_when_taking_flats': 45,
    'lowest_requestable_altitude': -10,  # Degrees. For normal pointing requests don't allow requests to go this low.
    'degrees_to_avoid_zenith_area_for_calibrations': 0, 
    'temperature_at_which_obs_too_hot_for_camera_cooling' : 23, 
    
    # These are the default values that will be set for the obs
    # on a reboot of obs.py. They are safety checks that 
    # can be toggled by an admin in the Observe tab.
    'scope_in_manual_mode': False,
    'mount_reference_model_off': True,
    'sun_checks_on': True,
    'moon_checks_on': True,
    'altitude_checks_on': True,    
    'daytime_exposure_time_safety_on': True,
    
    
    
    # Setup of folders on local and network drives.
    'client_hostname':  'ECO-0m28-OSC',
    'archive_path':  'C:/ptr/',  
    'alt_path':  'C:/ptr/',  # Generic place for this host to stash misc stuff
    'save_to_alt_path' : 'no',
    'local_calibration_path': 'C:/ptr/', # THIS FOLDER HAS TO BE ON A LOCAL DRIVE, not a network drive due to the necessity of huge memmap files    
    'archive_age' : 2.0, # Number of days to keep files in the local archive before deletion. Negative means never delete
    
    
    
    # For low bandwidth sites, do not send up large files until the end of the night. set to 'no' to disable
    'send_files_at_end_of_night': 'no',
    # For low diskspace sites (or just because they aren't needed), don't save a separate raw file to disk after conversion to fz.
    'save_raw_to_disk': False,
    # PTR uses the reduced file for some calculations (focus, SEP, etc.). To save space, this file can be removed after usage or not saved.
    'keep_reduced_on_disk': True,
    'keep_focus_images_on_disk': False,  # To save space, the focus file can not be saved.   
    # A certain type of naming that sorts filenames by numberid first
    'save_reduced_file_numberid_first' : False,
    
    
    
   
    
    
    # Minimum realistic seeing at the site.
    # This allows culling of unphysical results in photometry and other things
    # Particularly useful for focus
    'minimum_realistic_seeing' : 1.2,
    
    
    # TIMING FOR CALENDAR EVENTS
    # How many minutes with respect to eve sunset start flats
    'eve_sky_flat_sunset_offset': +5,  # 40 before Minutes  neg means before, + after.
    # How many minutes after civilDusk to do....
    'end_eve_sky_flats_offset': 5 , 
    'clock_and_auto_focus_offset': 8,
    'observing_begins_offset': 18,    
    # How many minutes before civilDawn to do ....
    'observing_ends_offset': 18,   
    
    
    # Exposure times for standard system exposures
    'focus_exposure_time': 15,  # Exposure time in seconds for exposure image
    'pointing_exposure_time': 20,  # Exposure time in seconds for exposure image

    # How often to do various checks and such
    'observing_check_period': 1,    # How many minutes between weather checks
    'enclosure_check_period': 1,    # How many minutes between enclosure checks

    # Turn on and off various automated calibrations at different times.
    'auto_eve_bias_dark': False,
    'auto_eve_sky_flat': True,
    'auto_midnight_moonless_bias_dark': False,
    'auto_morn_sky_flat': True,
    'auto_morn_bias_dark': False,
    
    # FOCUS OPTIONS
    'periodic_focus_time': 12.0, # This is a time, in hours, over which to bypass automated focussing (e.g. at the start of a project it will not refocus if a new project starts X hours after the last focus)
    'stdev_fwhm': 0.5,  # This is the expected variation in FWHM at a given telescope/camera/site combination. This is used to check if a fwhm is within normal range or the focus has shifted
    'focus_trigger': 0.75,  # What FWHM increase is needed to trigger an autofocus
    
    # PLATESOLVE options
    'solve_nth_image': 1,  # Only solve every nth image
    'solve_timer': 0.05,  # Only solve every X minutes
    'threshold_mount_update': 45,  # only update mount when X arcseconds away        



    'defaults': {
        'screen': 'screen1',
        'mount': 'mount1',
        'telescope': 'telescope1',     #How do we handle selector here, if at all?
        'focuser': 'focuser1',
        'rotator': 'rotator1',
        'selector': None,
        'filter_wheel': 'filter_wheel1',
        'camera': 'camera_1_1',
        'sequencer': 'sequencer1'
        },
    'device_types': [
            'mount',
            'telescope',
            #'screen',
            #'rotator',
            'focuser',
            'selector',
            'filter_wheel',
            'camera',
            'sequencer'
            ],
    
    'short_status_devices': [
            'mount',
            'telescope',
            'screen',
            'rotator',
            'focuser',
            'selector',
            'filter_wheel',
            'camera',
            'sequencer'
            ],
    

    'mount': {
        'mount1': {
            'parent': 'enclosure1',
            'tel_id': '0m40',
            'name': 'ecocdkpier',
            'hostIP':  '10.0.0.140',     #Can be a name if local DNS recognizes it.
            'hostname':  'ecocdkpier',
            'desc':  'Paramount MX+',
            'driver': 'ASCOM.SoftwareBisque.Telescope',
            'alignment': 'Equatorial',
            'default_zenith_avoid': 0.0,   #degrees floating, 0.0 means do not apply this constraint.
            'has_paddle': False,      #paddle refers to something supported by the Python code, not the AP paddle.
            'has_ascom_altaz': False,
            'pointing_tel': 'tel1',     #This can be changed to 'tel2'... by user.  This establishes a default.
            'west_clutch_ra_correction':  0.0, #
            'west_clutch_dec_correction': 0.0, #
            'east_flip_ra_correction':  0.0, #
            'east_flip_dec_correction': 0.0,  #  #
            'home_after_unpark' : True,
            
            'home_before_park' : True,
            
            
            'settle_time_after_unpark' : 0,
            'settle_time_after_park' : 0,
            'permissive_mount_reset' : 'yes', # if this is set to yes, it will reset the mount at startup and when coordinates are out significantly
            'time_inactive_until_park' : 3600.0, # How many seconds of inactivity until it will park the telescope
            'settings': {
			    'latitude_offset': 0.0,     #Decimal degrees, North is Positive   These *could* be slightly different than site.
			    'longitude_offset': 0.0,   #Decimal degrees, West is negative  #NB This could be an eval( <<site config data>>))
			    'elevation_offset': 0.0,    # meters above sea level
                'home_park_altitude': 0.0,
                'home_park_azimuth': 270.,

                'home_altitude' : 70,
                'home_azimuth' : 160,

                'horizon':  15.,    #  Meant to be a circular horizon. Or set to None if below is filled in.
                'horizon_detail': {  #  Meant to be something to draw on the Skymap with a spline fit.
                     '0.1': 10,
                     ' 90': 10,
                     '180': 10,
                     '270': 10,
                     '360': 10
                     },  #  We use a dict because of fragmented azimuth mesurements.
                'refraction_on': True,
                'model_on': True,
                'rates_on': True,
                'model': {
                    'IH': 0.0,
                    'ID': 0.0,
                    'WIH': 0.0,
                    'WID': 0.0,
                    'CH': 0.0,
                    'NP': 0.0,
                    'MA': 0.0,
                    'ME': 0.0,
                    'TF': 0.0,
                    'TX': 0.0,
                    'HCES': 0.0,
                    'HCEC': 0.0,
                    'DCES': 0.0,
                    'DCEC': 0.0,
                    }
            },
        },

    },

    'telescope': {                            #Note telescope == OTA  Optical Tube Assembly.
        'telescope1': {
            'parent': 'mount1',
            'name': 'Main OTA',
            'telescop': 'eco2',
            'ptrtel': 'RASA11',
            'desc':  'RASA11',
            'driver': None,                     #  Essentially this device is informational.  It is mostly about the optics.
            'collecting_area': 55381,
            'obscuration':  23.7,   #  %
            'aperture': 432,
            'focal_length': 2939,
            'has_dew_heater':  True,
            'screen_name': 'screen1',
            'focuser_name':  'focuser1',
            'rotator_name':  'rotator1',
            'has_instrument_selector': False,   #This is a default for a single instrument system
            'selector_positions': 1,            #Note starts with 1
            'instrument names':  ['camera1'],
            'instrument aliases':  ['ASI071MCPro'],
            'configuration': {
                 "position1": ["darkslide1", "filter_wheel1", "camera1"]
                 },
            'camera_name':  'camera1',
            #'filter_wheel_name':  'filter_wheel1',
            'filter_wheel_name':  None,
            'has_fans':  False,
            'has_cover':  False,
            'settings': {
                'fans': ['Auto','High', 'Low', 'Off'],
                'offset_collimation': 0.0,    #  If the mount model is current, these numbers are usually near 0.0
                                              #  for tel1.  Units are arcseconds.
                'offset_declination': 0.0,
                'offset_flexure': 0.0,
                'west_flip_ha_offset': 0.0,  #  new terms.
                'west_flip_ca_offset': 0.0,
                'west_flip_dec_offset': 0.0
            },



        },
    },



    'rotator': {
        'rotator1': {
            'parent': 'telescope1',
            'name': 'rotator',
            'desc':  False,
            'driver': None,
			'com_port':  False,
            'minimum': -180.,
            'maximum': 360.0,
            'step_size':  0.0001,     #Is this correct?
            'backlash':  0.0,
            'unit':  'degree'    #  'steps'
        },
    },

    'screen': {
        'screen1': {
            'parent': 'telescope1',
            'name': 'screen',
            'desc':  'No Screen',
            'driver': None,
            'com_port': 'COM10',  #  This needs to be a 4 or 5 character string as in 'COM8' or 'COM22'
            'minimum': 5,   #  This is the % of light emitted when Screen is on and nominally at 0% bright.
            'saturate': 255,  #  Out of 0 - 255, this is the last value where the screen is linear with output.
                              #  These values have a minor temperature sensitivity yet to quantify.


        },
    },

    'focuser': {
        'focuser1': {
            'parent': 'telescope1',
            'name': 'focuser',
            'desc':  'Planewave Focuser',
            #'driver': 'ASCOM.SeletekFocuser.Focuser',
            'driver': 'SeletekFocuser.Focuser',
			'com_port':  'COM9',
            'start_at_config_reference': False,
            'correct_focus_for_temperature' : True,
            'maximum_good_focus_in_arcsecond': 2.5, # highest value to consider as being in "good focus". Used to select last good focus value
            'reference':24900,    #  20210313  Nominal at 10C Primary temperature            
            'minimum': 0,     #  NB this area is confusing steps and microns, and need fixing.
            'maximum': 30000,   #12672 actually
            'step_size': 1,
            'backlash': 0,
            'throw' : 200,
            'unit': 'counts',
            'unit_conversion': 1.0,
            'has_dial_indicator': False
        },

    },

    'selector': {
        'selector1': {
            'parent': 'telescope1',
            'name': 'None',
            'desc':  'Null Changer',
            'driver': None,
            'com_port': None,
            'startup_script':  None,
            'recover_script':  None,
            'shutdown_script':  None,
            'ports': 1,
            'instruments':  ['Main_camera'], #, 'eShel_spect', 'planet_camera', 'UVEX_spect'],
            'cameras':  ['camera_1_1'], # , 'camera_1_2', None, 'camera_1_4'],
            'guiders':  [None], # , 'guider_1_2', None, 'guide_1_4'],
            'default': 0
            },

    },

   
    'filter_wheel': {        
        "filter_wheel1": {
            "parent": "telescope1",
            "name": "RGGB" ,  # When there is no filter wheel, the filter will be named this.
            'service_date': '20180101',
            
            "filter_settle_time": 0, #how long to wait for the filter to settle after a filter change(seconds)
            'override_automatic_filter_throughputs': False, # This ignores the automatically estimated filter gains and starts with the values from the config file
            
            'flat_sky_gain' : 650,

            "driver":   None,   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
            #"driver":   "Maxim.Image",   #"LCO.dual",  #  'ASCOM.FLI.FilterWheel',
            'settings': {'auto_color_options' : ['none']}, # OPtions include 'OSC', 'manual','RGB','NB','RGBHA','RGBNB'
            'ip_string': None,
            "dual_wheel": False,
        },
    },

    'lamp_box': {
        'lamp_box1': {
            'parent': 'camera_1',  # Parent is camera for the spectrograph
            'name': 'None',  # "UVEX Calibration Unit", 'None'
            'desc': 'None', #'eshel',  # "uvex", 'None'
            'spectrograph': 'None', #'echelle', 'uvex'; 'None'
            'driver': 'None', # ASCOM.Spox.Switch; 'None'; Note change to correct COM port used for the eShel calibration unit at mrc2
            'switches': "None"  # A string of switches/lamps the box has for the FITS header. # 'None'; "Off,Mirr,Tung,NeAr" for UVEX
        },
    },


    'camera': {
        'camera_1_1': {
            'parent': 'telescope1',
            'name': 'ec002cs',      #Important because this points to a server file structure by that name.
            'desc':  'QHY 600C Pro',
            #'driver':  "ASCOM.QHYCCD_CAM2.Camera", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            'driver':  "QHYCCD_Direct_Control", # NB Be careful this is not QHY Camera2 or Guider  "Maxim.CCDCamera",   #'ASCOM.FLI.Kepler.Camera', "ASCOM.QHYCCD.Camera",   #
            
            
            
            
            
            'detector':  'Sony IMX455 Color',  #  It would be good to build out a table of chip characteristics
            'use_file_mode':  False,   # NB we should clean out all file mode stuff.
            'file_mode_path':  'Q:/archive/sq01/maxim/',   #NB NB all file_mode Maxim stuff should go!
            'manufacturer':  "QHY",
            'settings': {
                
                'hold_flats_in_memory': True, # If there is sufficient memory ... OR .... not many flats, it is faster to keep the flats in memory.

                
                
                # For direct QHY usage we need to set the appropriate gain.
                # This changes from site to site. "Fast" scopes like the RASA need lower gain then "slow".
                # Sky quality is also important, the worse the sky quality, the higher tha gain needs to be
                # Default for QHY600 is GAIN: 26, OFFSET: 60, readout mode 3. 
                # Random tips from the internet:
                # After the exposure, the background in the image should not be above 10% saturation of 16Bit while the brightest bits of the image should not be overexposed
                # The offset should be set so that there is at least 300ADU for the background
                # I guess try this out on the standard smartstack exposure time.        
                # https://www.baader-planetarium.com/en/blog/gain-and-offset-darks-flats-and-bias-at-cooled-cmos-cameras/
                #
                # Also the "Readout Mode" is really important also
                # Readout Mode #0 (Photographic DSO Mode)
                # Readout Mode #1 (High Gain Mode)
                # Readout Mode #2 (Extended Fullwell Mode)
                # Readout Mode #3 (Extended Fullwell Mode-2CMS)
                #
                # With the powers invested in me, I have decided that readout mode 3 is the best. We can only pick one standard one
                # and 0 is also debatably better for colour images, but 3 is way better for dynamic range....
                # We can't swip and swap because the biases and darks and flats will change, so we are sticking with 3 until
                # something bad happens with 3 for some reason
                #
                # In that sense, QHY600 NEEDS to be set at GAIN 26 and the only thing to adjust is the offset.....
                # USB Speed is a tradeoff between speed and banding, min 0, max 60. 60 is least banding. Most of the 
                # readout seems to be dominated by the slow driver (difference is a small fraction of a second), so I've left it at 60 - least banding.
                'direct_qhy_readout_mode' : 3,        
                'direct_qhy_gain' : 26,
                'direct_qhy_offset' : 60,  
                'direct_qhy_usb_speed' : 60,
                
                
                
                
                
                'is_osc' : True,
                
                'squash_on_x_axis' : True,
                'osc_brightness_enhance' : 1.0,
                'osc_contrast_enhance' : 1.5,
                'osc_saturation_enhance' : 2.5,
                'osc_colour_enhance' : 1.7,
                'osc_sharpness_enhance' : 1.5,                
                'osc_background_cut' : 25.0,
                
                # These options set whether an OSC gets binned or interpolated for different functions
                # If the pixel scale is well-sampled (e.g. 0.6 arcsec per RGGB pixel or 0.3 arcsec per individual debayer pixel)
                # Then binning is probably fine for all three. For understampled pixel scales - which are likely with OSCs
                # then binning for focus is recommended. SEP and Platesolve can generally always be binned.                
                'interpolate_for_focus': True,
                'bin_for_focus' : False, # This setting will bin the image for focussing rather than interpolating. Good for 1x1 pixel sizes < 0.6.
                'focus_bin_value' : 1,
                'interpolate_for_sep' : False,
                'bin_for_sep' : True, # This setting will bin the image for SEP photometry.
                'sep_bin_value' : 1,
                'bin_for_platesolve' : True, # This setting will bin the image for platesolving.
                'platesolve_bin_value' : 2,
                
                # ONLY TRANSFORM THE FITS IF YOU HAVE
                # A DATA-BASED REASON TO DO SO.....
                # USUALLY TO GET A BAYER GRID ORIENTATED CORRECTLY
                # ***** ONLY ONE OF THESE SHOULD BE ON! *********
                'transpose_fits' : False,
                'flipx_fits' : False,
                'flipy_fits' : False,
                'rotate180_fits' : False, # This also should be flipxy!
                'rotate90_fits' : False,
                'rotate270_fits' : False,
                # What number of pixels to crop around the edges of a REDUCED image
                # This is primarily to get rid of overscan areas and also all images
                # Do tend to be a bit dodgy around the edges, so perhaps a standard
                # value of 30 is good. Increase this if your camera has particularly bad
                # edges.
                'reduced_image_edge_crop': 30,
                
                # HERE YOU CAN FLIP THE IMAGE TO YOUR HEARTS DESIRE
                # HOPEFULLY YOUR HEARTS DESIRE IS SIMILAR TO THE
                # RECOMMENDED DEFAULT DESIRE OF PTR
                'transpose_jpeg' : False,
                'flipx_jpeg' : False,
                'flipy_jpeg' : False,
                'rotate180_jpeg' : False,
                'rotate90_jpeg' : False,
                'rotate270_jpeg' : False,
                
                # For large fields of view, crop the images down to solve faster.                 
                # Realistically the "focus fields" have a size of 0.2 degrees, so anything larger than 0.5 degrees is unnecesary
                # Probably also similar for platesolving.
                # for either pointing or platesolving even on more modest size fields of view. 
                # These were originally inspired by the RASA+QHY which is 3.3 degrees on a side and regularly detects
                # tens of thousands of sources, but any crop will speed things up. Don't use SEP crop unless 
                # you clearly need to. 
                'focus_image_crop_width': 0.5, # For excessive fields of view, to speed things up crop the image to a fraction of the full width    
                'focus_image_crop_height': 0.5, # For excessive fields of view, to speed things up crop the image to a fraction of the full height
                                
               'focus_jpeg_size': 500, # How many pixels square to crop the focus image for the UI Jpeg
                # PLATESOLVE CROPS HAVE TO BE EQUAL! OTHERWISE THE PLATE CENTRE IS NOT THE POINTING CENTRE                
                'platesolve_image_crop': 0.75, # Platesolve crops have to be symmetrical 
                # Really, the SEP image should not be cropped unless your field of view and number of sources
                # Are taking chunks out of the processing time. 
                'sep_image_crop_width': 0.1, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
                'sep_image_crop_height': 0.1, # For excessive fields of view, to speed things up crop the processed image area to a fraction of the full width    
                
                'osc_bayer' : 'RGGB',
                'crop_preview': False,
                'crop_preview_ybottom': 2,  #  2 needed if Bayer array
                'crop_preview_ytop': 2,
                'crop_preview_xleft': 2,
                'crop_preview_xright': 2,
                'temp_setpoint': -4,    #Verify we can go colder, this system has a chiller
                'has_chiller': True,
                
                'day_warm': True,
                'day_warm_degrees' : 6, # Number of degrees to warm during the daytime.
                'protect_camera_from_overheating' : True,
                'cooler_on': True,
                "cam_needs_NumXY_init": True,
                
                'x_pixel':  3.76, # microns
                'y_pixel':  3.76, # microns
                
                '1x1_pix_scale': 1.25,    #  This is the 1x1 binning pixelscale
                'native_bin': 1, # Needs to be simple, it will recalculate things on the 1x1 binning pixscale above.
                
                
                # The drizzle_value is by the new pixelscale
                # for the new resolution when stacking in the EVA pipeline
                # Realistically you want a resolution of about 0.5 arcseconds per pixel
                # Unless you are at a very poor quality site.
                # If you have a higher resolution pixelscale it will use that instead.
                # Generally leave this at 0.5 - the optimal value for ground based
                # observatories.... unless you have a large field of view.                
                'drizzle_value_for_later_stacking': 0.5,
                
                'north_offset': 0.0,    #  These three are normally 0.0 for the primary telescope
                'east_offset': 0.0,
                'rotation': 0.0,
                'min_exposure': 0.0001,
                'min_flat_exposure' : 1.0, # For certain shutters, short exposures aren't good for flats. Some CMOS have banding in too short an exposure. Largely applies to ccds though.

                'max_flat_exposure' : 20.0, # Realistically there should be a maximum flat_exposure that makes sure flats are efficient and aren't collecting actual stars.
                'reject_new_flat_by_known_gain' : True,
                

                'max_exposure': 180.,
                'max_daytime_exposure': 0.0001,
                'can_subframe':  True,
                'min_subframe': [128,128],
                'camera_gain':   2.417, #[10., 10., 10., 10.],     #  One val for each binning.
                'camera_gain_stdev':   0.11, #[10., 10., 10., 10.],     #  One val for each binning.
                'read_noise':  10.224, #[9, 9, 9, 9],    #  All SWAGs right now
                'read_noise_stdev':   0.003, #[10., 10., 10., 10.],     #  One val for each binning.
                'reference_dark': 0.2,  #  NB  Guess
                'reference_offset': 611, #  NB Guess  ADU vaules not times in sec.
                'fullwell_capacity': 80000,   #  NB Guess
                'bin-desc':              ['1x1', '2x2', '3x3', '4x4' ],
                'chan_color':            ['col', 'gry', 'gry', 'gry' ],
                
                'cycle_time':            0.5,   # Meas 20230219  for a bias


                'number_of_bias_to_collect' : 128,
                'number_of_dark_to_collect' : 128,
                'number_of_flat_to_collect' : 128,
                'number_of_bias_to_store' : 128,
                'number_of_dark_to_store' : 128,
                'number_of_flat_to_store' : 128,

 
                'dark_exposure': 20,
                
                'do_cosmics' : False,
                
                'rbi_delay':  0,      #  This being zero says RBI is not available, eg. for SBIG.
                'is_cmos':  True,
                'is_color': True,   #NB we also have a is_osc key.
                'can_set_gain':  True,
                'max_linearity':  80000,   # Guess

                'saturate':   65535 ,    #[[1, 65000], [2,262000], [3,589815], [4, 1048560]] ,   # e-.  This is a close guess, not measured, but taken from data sheet.



                'read_mode':  'Normal',
                'readout_mode': 'Normal',
                'readout_speed':  0.4,
                'readout_seconds': 2.4,
                'smart_stack_exposure_time': 20,
                'square_detector': False,
                'square_pixels': True,
                'areas_implemented': ['Full', 'SQR', '0.5*0.5°',  '0.7x0.7°', '1x1°', '1.4x1.4°', '2x2°', '2.8x2.8°', '4x4sq°', '5.6x5.6°'],
                'default_area':  "Full",
                'default_rotation': 0.0000,

                'has_darkslide':  False,
                'darkslide_com':  'COM15',
                'shutter_type': "Electronic",
                'has_screen': True,
                'screen_settings':  {
                    'screen_saturation':  157.0,
                    'screen_x4':  -4E-12,  #  'y = -4E-12x4 + 3E-08x3 - 9E-05x2 + 0.1285x + 8.683     20190731'
                    'screen_x3':  3E-08,
                    'screen_x2':  -9E-05,
                    'screen_x1':  .1258,
                    'screen_x0':  8.683
                },
            },

        },


    },

    'sequencer': {
        'sequencer1': {
            'parent': 'site',
            'name': 'Sequencer',
            'desc':  'Automation Control',
            'driver': None,


        },
    },

    #  I am not sure AWS needs this, but my configuration code might make use of it.
    'server': {
        'server1': {
            'name': None,
            'win_url': None,
            'redis':  '(host=none, port=6379, db=0, decode_responses=True)'
        },
    },
}

