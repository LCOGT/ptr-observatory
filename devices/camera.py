import win32com.client
import pythoncom
import time

import os
import math
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.utils.data import get_pkg_data_filename
import sep

from os.path import join, dirname, abspath

from skimage import data, io, filters
from skimage.transform import resize
from skimage import img_as_float
from skimage import exposure
from skimage.io import imsave
import matplotlib.pyplot as plt 

from PIL import Image
from global_yard import g_dev
import ptr_config
import ptr_events
import api_calls
import requests
import config
import ptr_bz2

'''
TO DO
Annotate fits, incl Wx conditions, other devices
Jpeg
Send to S3
Timeout
Power cycle Reset
repeat, then execute blocks     command( [(exposure, bin/area, filter, dither, co-add), ( ...)}, repeat)  co-adds send jpegs
    only for each frame and a DB for the sum.
    
dither
autofocus
bias/dark +screens, skyflats
'''

 

class Camera:

    """ 
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """

    def __init__(self, driver: str, name: str):
        
        self.name = name
        g_dev['cam'] = self
        # Define the camera driver, then connect to it.
        win32com.client.pythoncom.CoInitialize()
        self.camera = win32com.client.Dispatch(driver)
        #Need logic here is camera denies connection.
        print("Connecting to camera.")
        if driver[:5] == 'Maxim':
            print('MaximDL')
            time.sleep(5)
            self.camera.LinkEnabled= True
            self.description = "MaximDL"
            self.maxim = True
        else:

            self.camera.connected = True
            self.description = self.camera.Description
            self.maxim = False
        self.exposure_busy = False
        self.af_mode = False
        self.af_step = -1
        self.f_spot_dia = []
        self.f_positions = []
        self.save_directory = abspath(join(dirname(__file__), '..', 'images'))
        
        print("Connected to camera.", g_dev['mnt'], g_dev['foc'], g_dev['rot'], g_dev['ocn'])
        #print(self.description)
        #NB this should be loaded from the config object      
        self.filters = ['air', 'dif', 'w', 'ContR', 'N2', 'u', 'g', 'r', 'i', 'zs', 'PL', 'PR', 'PG', 'PB', 'O3', 'HA', \
                            'S2', 'dif_u', 'dif_g', 'dif_r', 'dif_i', 'dif_zs', 'dark']
        self.filter_index = [(0, 0), (4, 0), (2, 0), (1, 0), (3, 0), (0, 5), (0, 6), (0, 7), (0, 8), (5, 0), (0, 4), \
                                  (0, 3), (0, 2), (0, 1), (7, 0), (6, 0), (8, 0), (4, 5), (4, 6), (4, 7), (4, 8), (9, 0), \
                                  (10, 9)]
        self.filter_offset = [-1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]        

    @classmethod
    def fit_quadratic(cls, x, y):
        #From Meeus, works fine.
        if len(x) == len(y):
            p = 0
            q = 0
            r = 0
            s = 0
            t = 0
            u = 0
            v = 0
            for i in range(len(x)):
                p += x[i]
                q += x[i]**2
                r += x[i]**3
                s += x[i]**4
                t += y[i]
                u += x[i]*y[i]
                v += x[i]**2*y[i]
            n = len(x)
            d = n*q*s +2*p*q*r - q*q*q - p*p*s - n*r*r
            a = (n*q*v + p*r*t + p*q*u - q*q*t - p*p*v - n*r*u)/d
            b = (n*s*u + p*q*v + q*r*t - q*q*u - p*s*t - n*r*v)/d
            c = (q*s*t + q*r*u + p*r*v - q*q*v - p*s*u - r*r*t)/d
            return a, b, c
        else:
            return None
        
    def get_status(self):
        #status = {"type":"camera"}
        status = {}
        if self.exposure_busy:
            status['busy_lock'] = 'True'
        else:
            status['busy_lock'] = 'False' 
        if self.maxim:
            cam_stat = self.camera.CameraStatus  #Note enumerations are different.
            #Presumably skip if camera would block)
            f1 = self.camera.Filter
            f2 = self.camera.GuiderFilter
            index =(f1, f2)
            filt_pointer = 0#Set up default to be air
            for match in range(len(self.filter_index)):
                if index == self.filter_index[match]:
                    filt_pointer = match
                    break
            self.filter_str = self.filters[filt_pointer]
            #print('Filter_str:  ', self.filter_str)
            self.filter_off = self.filter_offset[filt_pointer]
            status['filter'] = str(self.filter_str)
            status['status'] = str(cam_stat)
        else:
            cam_stat = self.camera.CameraState
        return status

    def parse_command(self, command):
        print("Camera Command incoming:  ", command)
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "expose" and not self.exposure_busy:
            self.expose_command(req, opt)
            self.exposure_busy = False     #Hangup needs to be guarded with a timeout.
            return True    #this resumes Run Thread in Obs.
            
        elif action == "stop":
            self.stop_command(req, opt)
            self.exposure_busy = False
        else:
           
            print(f"Command <{action}> not recognized.")

    ###############################
    #       Camera Commands       #
    ###############################

    def expose_command(self, required_params, optional_params, p_next_filter=None, p_next_focus=None, p_dither=False):
        ''' Apply settings and start an exposure. '''
        c = self.camera
        print('Req:  ', required_params, 'Opt:  ', optional_params)
        bin_x = int(optional_params.get('bin', 1))
        bin_y = 0
        gain = optional_params.get('gain', 1)
        imtype = "Light"
        exposure_time = float(required_params.get('time', 5))
        exposure_time = max(0.2, exposure_time)  #Saves the shutter
        frame = required_params.get('frame', 'Light')
        filter =optional_params.get('filter', 0)
        area = optional_params.get('size', 100)
        if area == None: area = 100
        #breakpoint()
        count = int(optional_params.get('repeat', 1))
        if count < 1:
            count = 1   #Hence repeat does not repeat unless > 1
 
        if type(filter) == int and 0 <= filter < len(self.filters):
            filter = int(filter)
            selection = filter
        elif type(filter) == str:
            #The filter string must match one of the filters, or we pick air.
            selection = 0
            for index in range(len(self.filters)):
                if filter.lower() == self.filters[index].lower():
                    selection = index
                    break
            #use selection later on to set filters.    
        if imtype.lower() == 'light' or imtype.lower() == 'screen' or imtype.lower() == 'skyflat' or imtype.lower() == \
                             'experimental':
            imtypeb = True
        else:
            if imtype.lower() == 'bias':
                exposure_time = 0.0
            imtypeb = False
            
        if required_params['image_type'] == 'auto focus':           
            count = 4
            self.af_mode= True
            self.af_step = -1
            area = "1x-jpg"
            filter = 'w'
            exposure_time = max(exposure_time, 3.0)
            print('AUTOFOCUS CYCLE\n')
        else:
            self.af_mode = False
            self.af_step = -1 
        print(bin_x, count, filter, area, type(area))
        if type(area) == str and area[-1] =='%':
            area = int(area[0:-1])
        
        
        #print('pre area:  ', self.camera, area)
        ##NBNB Need to fold in subtracting overscan for subframes.
        
        #NBNBNB Consider jamming camera X Size in first.
        if bin_y == 0 or self.camera.MaxBinX != self.camera.MaxBinY:
            self.bin_x = min(bin_x, self.camera.MaxBinX)
            self.camera.BinX = self.bin_x 
            self.bin_y = min(bin_x, self.camera.MaxBiny)
            self.camera.BinY = self.bin_y
        else:
            self.bin_x = min(bin_x, self.camera.MaxBinX)
            self.camera.Binx = self.bin_x
            self.bin_y = min(bin_y, self.camera.MaxBinY)
            self.camera.BinY = self.bin_y
        self.len_x = self.camera.CameraXSize//self.bin_x
        self.len_y = self.camera.CameraYSize//self.bin_y    #Unit is binned pixels.
        self.len_xs = self.len_x - 50   #THIS IS A HACK
        #print(self.len_x, self.len_y)
        
        #"area": ['100%', '2X-jpg', '71%', '50%', '1X-jpg', '33%', '25%', '1/2 jpg']
        if type(area) == str and area.lower() == "1x-jpg":
            self.camera.NumX = 768
            self.camera.StartX = 640
            self.camera.NumY = 768
            self.camera.StartY = 640
            self.area = 37.5
        elif type(area) == str and area.lower() == "2x-jpg":
            self.camera.NumX = 1536
            self.camera.StartX = 256
            self.camera.NumY = 1536
            self.camera.StartY = 256
            self.area = 75
        elif type(area) == str and area.lower() == "1/2 jpg":
            self.camera.NumX = 360
            self.camera.StartX = 844
            self.camera.NumY = 360
            self.camera.StartY = 844
            self.area = 18.75
        elif type(area) == str:     #Just defalut to a small area.
            self.camera.NumX = self.len_x//4
            self.camera.StartX = int(self.len_xs/2.667)
            self.camera.NumY = self.len_y//4
            self.camera.StartY = int(self.len_y/2.667)
            self.area = 100
        elif 72 < area <= 100:
            self.camera.NumX = self.len_x
            self.camera.StartX = 0
            self.camera.NumY = self.len_y
            self.camera.StartY = 0
            self.area = 100
        elif 70 <= area <= 72:
            self.camera.NumX = int(self.len_xs/1.4142)
            self.camera.StartX = int(self.len_xs/6.827)
            self.camera.NumY = int(self.len_y/1.4142)
            self.camera.StartY = int(self.len_y/6.827)
            self.area = 71       
        elif area == 50:
            self.camera.NumX = self.len_xs//2
            self.camera.StartX = self.len_xs//4
            self.camera.NumY = self.len_y//2
            self.camera.StartY = self.len_y//4
            self.area = 50
        elif 33 <= area <= 35:
            self.camera.NumX = int(self.len_xs/2.829)
            self.camera.StartX = int(self.len_xs/3.093)
            self.camera.NumY = int(self.len_y/2.829)
            self.camera.StartY = int(self.len_y/3.093)
            self.area = 33
        elif area == 25:
            self.camera.NumX = self.len_xs//4
            self.camera.StartX = int(self.len_xs/2.667)
            self.camera.NumY = self.len_y//4
            self.camera.StartY = int(self.len_y/2.667)
            self.area = 25
        else:
            self.camera.NumX = self.len_x
            self.camera.StartX = 0
            self.camera.NumY = self.len_y
            self.camera.StartY = 0
            self.area = 100
            print("Defult area used. 100%")
        #print(self.camera.NumX, self.camera.StartX, self.camera.NumY, self.camera.StartY)
        
        for seq in range(count):
            try:
                #print("starting exposure, area =  ", self.area)
                #NB NB Ultimately we need to be a thread.
                self.pre_mnt = []
                self.pre_rot = []
                self.pre_foc = []
                self.pre_ocn = []
                if self.maxim:
                    
                    f1,f2 = self.filter_index[selection]
                    if c.Filter != f1: c.filter = f1
                    if c.GuiderFilter != f2: c.GuiderFilter = f2
                    if not self.af_mode:
                        next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name)
                    else:
                        #This is an AF cycle so need to set up.  THIS VERSION PRE_FOCUSES, no overlap
                        if  self.af_step == -1:
                            #breakpoint()
                            self.f_positions = []
                            self.f_spot_dia = []
                            #Take first image with no focus adjustment
                            next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name)
                            self.af_step = 0
                        elif self.af_step == 0:
                            
                            next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name) - 1200
                            self.af_step = 1
                        elif self.af_step == 1:
                            
                            next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name) + 3000
                            if next_focus != g_dev['foc'].focuser.Position:
                                
                                g_dev['foc'].focuser.Move(next_focus)
                                while  g_dev['foc'].focuser.IsMoving:
                                    time.sleep(0.5)
                                    print(';;')
                            next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name) +-600
                            self.af_step = 2                            
                        elif self.af_step == 2:
                            #this should use the self.new_focus solution
                            #breakpoint()
                            next_focus = self.new_focus #self.filter_offset[selection] + ptr_config.get_focal_ref(self.name)
                            next_focus -= self.filter_offset[selection]
                            #ptr_config.set_focal_ref(self.name, next_focus)
                            #Here we would update the shelved reference focus
                            self.af_step = 3
                        elif self.af_step == 3:
                            #breakpoint()
                            #next_focus = self.filter_offset[selection] + ptr_config.get_focal_ref(self.name) 
                            self.f_positions = []
                            self.f_spot_dia = []
                            self.af_mode = False
                            self.af_step = -1
 
                    if next_focus != g_dev['foc'].focuser.Position:
                        
                        g_dev['foc'].focuser.Move(next_focus)
                        while  g_dev['foc'].focuser.IsMoving:     #Check here for filter, guider, still moving
                            time.sleep(0.5)
                            print(';')
                    self.t1 = time.time()
                    g_dev['ocn'].get_quick_status(self.pre_ocn)
                    g_dev['foc'].get_quick_status(self.pre_foc)
                    g_dev['rot'].get_quick_status(self.pre_rot)
                    g_dev['mnt'].get_quick_status(self.pre_mnt)  #stage symmetric around exposure
                    self.exposure_busy = True
                    self.t2 = time.time()
                    c.Expose(exposure_time, imtypeb)     #True indicates Light Frame.
                    self.t3 = time.time()
                else:
                    c.StartExposure(exposure_time, imtypeb)
                    self.t3 = time.time()#True indicates Light Frame.
                self.finish_exposure(exposure_time, imtype, count+1, p_next_filter, p_next_focus, p_dither)
                #self.exposure_busy = False  Need to be able to do repeats
            except Exception as e:
                print("failed exposure")
                print(e)
                return
        return

#        for i in range(20):
#            pc = c.PercentCompleted
#            print(f"{pc}%")
#            if pc >= 100: 
#                self.save_image()
#                break
#            time.sleep(1)

    def stop_command(self, required_params, optional_params):
        ''' Stop the current exposure and return the camera to Idle state. '''

        self.camera.AbortExposure()
        self.exposure_busy = False

        # Alternative: self.camera.StopExposure() will stop the exposure and 
        # initiate the readout process. 
        


    ###############################
    #       Helper Methods        #
    ###############################
    
    def finish_exposure(self, exposure_time, frame_type, counter, p_next_filter=None, p_next_focus=None, p_dither=False):
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0
        while True:
            try:
                self.t4 = time.time()
                if self.camera.ImageReady: #and not self.img_available and self.exposing:
                    self.t5 = time.time()
                   
                    g_dev['mnt'].get_quick_status(self.post_mnt)  #stage symmetric around exposure
                    g_dev['rot'].get_quick_status(self.post_rot)
                    g_dev['foc'].get_quick_status(self.post_foc)
                    g_dev['ocn'].get_quick_status(self.post_ocn)
                    ###Here is the place to potentially pipeline dithers, next filter, focus, etc.
                    if p_next_filter is not None:
                        print("Post image filter seek here")
                    if p_next_focus is not None:
                        print("Post Image focus seek here")
                    if p_dither == True:
                        print("Post image dither step here")
                    self.t6 = time.time()
                    self.img = self.camera.ImageArray
                    self.t7 = time.time()
                    #Save image with Maxim Header information, then read back with astropy
                    #This should be a very fast disk.
                    self.camera.SaveImage('Q:\\archive\\ea03\\newest.fits')#, overwrite=True)
       
                    #print('Try#:  ', counter)
                    #print(len(self.img), self.img[0][:5])
                    avg_mnt = g_dev['mnt'].get_average_status(self.pre_mnt, self.post_mnt)
                    avg_foc = g_dev['foc'].get_average_status(self.pre_foc, self.post_foc)
                    avg_rot = g_dev['rot'].get_average_status(self.pre_rot, self.post_rot)
                    avg_ocn = g_dev['ocn'].get_average_status(self.pre_ocn, self.post_ocn)
                    #print(avg_ocn, avg_foc, avg_rot, avg_mnt)

                    counter = 0
                    try:
                        #Save the raw data after adding fits header information.  This means write with MAxim code and then
                        #read the file in and annotate then put in final directory for transfer.  For other camera clients more 
                        #keywords may need to be added.  Writing the temporay file may or may not be required for some camera
                        #drivers
                        
                        #hdu = fits.PrimaryHDU(self.img)
                        #hdu1 =  fits.open('C:\\Users\\obs\\Documents\\PlaneWave Instruments\\Images\\Focus\\2019-07-05\\061138\\FOCUS11357.FIT')
                        hdu1 =  fits.open('Q:\\archive\\ea03\\newest.fits')
                        
                        hdu = hdu1[0]   #get the Primary header and date
                        hdu.data = hdu.data.astype('uint16')    #This is probably redundant but forces unsigned storage
                        self.hdu_data1 = hdu.data.copy()
                        
                        
                        hdu.header['BUNIT'] ='adu'
                        hdu.header['IMGCOUNT'] = int(counter)
                        hdu.header['DITHER'] = 0
                        hdu.header['IMGTYPE'] = frame_type
                        hdu.header['TELESCOP'] = 'PlaneWave CDK 432mm'
                        hdu.header['OBSERVER'] = "WER"
                        hdu.header['ENCLOSE'] = "Clamshell"
                        hdu.header['MNT-SIDT'] = avg_mnt['mnt1_sid']
                        ha = avg_mnt['mnt1_ra'] - avg_mnt['mnt1_sid']
                        hdu.header['MNT-RA'] = avg_mnt['mnt1_ra']
                        while ha >= 12:
                            ha -= 24.
                        while ha < 12:
                            ha += 24.
                        hdu.header['MNT-HA'] = round(ha, 4)
                        hdu.header['MNT-DEC'] = avg_mnt['mnt1_dec']
                        hdu.header['MNRRAVEL'] = avg_mnt['mnt1_tracking_ra_rate']
                        hdu.header['MNTDECVL'] = avg_mnt['mnt1_tracking_dec_rate']
                        hdu.header['AZIMUTH '] = avg_mnt['mnt1_az']
                        hdu.header['ALTITUDE'] = avg_mnt['mnt1_alt']
                        hdu.header['ZENITH  '] = avg_mnt['mnt1_zen']
                        hdu.header['AIRMASS '] = avg_mnt['mnt1_air']
                        hdu.header['MNTRDSYS'] = avg_mnt['mnt1_rdsys']
                        hdu.header['POINTINS'] = avg_mnt['mnt1_inst']
                        hdu.header['MNT-PARK'] = avg_mnt['mnt1_is_parked']
                        hdu.header['MNT-SLEW'] = avg_mnt['mnt1_is_slewing']
                        hdu.header['MNT-TRAK'] = avg_mnt['mnt1_is_tracking']
                        hdu.header['OTA'] = ""
                        hdu.header['ROTATOR'] = "" 
                        hdu.header['ROTANGLE'] = avg_rot[1]
                        hdu.header['ROTMOVNG'] = avg_rot[2]
                        hdu.header['FOCUS'] = ""
                        hdu.header['FOCUSPOS'] = avg_foc[1]
                        hdu.header['FOCUSTEM'] = avg_foc[2]
                        hdu.header['FOCUSMOV'] = avg_foc[3]
                        hdu.header['WX'] = ""
                        hdu.header['SKY-TEMP'] = avg_ocn[1]
                        hdu.header['AIR-TEMP'] = avg_ocn[2]
                        hdu.header['HUMIDITY'] = avg_ocn[3]
                        hdu.header['DEWPOINT'] = avg_ocn[4]
                        hdu.header['WIND'] = avg_ocn[5]
                        hdu.header['PRESSURE'] = avg_ocn[6]
                        hdu.header['CALC-LUX'] = avg_ocn[7]
                        hdu.header['SKY-HZ'] = avg_ocn[8]
        
                        hdu.header['DETECTOR'] = ""
                        hdu.header['CAMNAME'] = 'ea03'
                        hdu.header['GAIN'] = 1.18
                        hdu.header['RDNOISE'] = 5.82
                        hdu.header['PIXSCALE'] = 0.95
                        #Need to assemble a complete header here
                        
                        #hdu1.writeto('Q:\\archive\\ea03\\new2b.fits')#, overwrite=True)
                        alias = config.site_config['camera']['cam1']['alias']
                        im_type = 'E'
                        next_seq = ptr_config.next_seq(alias) 
                        raw_name = config.site_name + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + im_type + '00.fits'
                        db_name = config.site_name + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + im_type + '13.fits'
                        jpeg_name = config.site_name + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + im_type + '13.jpg'
                        text_name = config.site_name + '-' + alias + '-' + g_dev['day'] + '-' + next_seq  + '-' + im_type + '00.txt'
                        im_path = 'Q:\\archive\\ea03\\'
                        hdu.header['FILEPATH'] = str(im_path)
                        hdu.header['FILENAME'] = str(raw_name)
                        #print('Creating:  ', im_path + g_dev['day'] + '\\to_AWS\\  ... subdirectory.')
                        try:
                            
                            os.makedirs(im_path + g_dev['day'] + '\\to_AWS\\', exist_ok=True)
                            #print('Created:  ',im_path + g_dev['day'] + '\\to_AWS\\' )
                            im_path = im_path + g_dev['day'] + '\\to_AWS\\'
                        except:
                            pass
                        
                        hdu1.writeto(im_path + raw_name, overwrite=True)
                        #breakpoint()
                        text = open(im_path + text_name, 'w')
                        text.write(str(hdu.header))
                        text.close()
                        text_data_size = len(str(hdu.header))- 2048
                        raw_data_size = hdu.data.size

                        print("\n\Finish-Exposure is complete:  " + raw_name, raw_data_size, '\n')
                        #Now make the db_image:
                        #THis should be moved into the transfer process and processed in parallel
                        hdu.data.astype('float32')
                        
                        if hdu.data.shape[1] == 2098:
                            overscan = hdu.data[:, 2048:]
                            medover = np.median(overscan)
                            print('Overscan median =  ', medover)
                            hdu.data = hdu.data[:, :2048] - medover
                        else:
                            hdu.data = hdu.data - 1310.0     #This deaals with all subframes
                            
                        img = hdu.data.copy().astype('float')
                        bkg = sep.Background(img)
                        bkg_rms = bkg.rms()
                        img -= bkg
                        sources = sep.extract(img, 2.5, err=bkg_rms, minarea=30)#, filter_kernel=kern)
                        sources.sort(order = 'cflux')
                        print('No. of detections:  ', len(sources))
                        result = []
                        spots = []
                        for source in sources:
                            a0 = source['a']
                            b0 =  source['b']
                            if (a0 - b0)/(a0 + b0)/2 > 0.1:
                                continue
                            r0 = round(math.sqrt(a0**2 + b0**2), 2)
                            result.append((round((source['x']), 1), round((source['y']), 1), round((source['cflux']), 1), \
                                           round(r0), 2))
                            spots.append(round((r0), 2))
                        spot = np.array(spots)
                        spot = np.median(spot)
                        try:
                            print('Spot and flux:  ', spot, source['cflux'], '\n', sources)
                        except:
                            pass
                        if self.af_mode:
                            #THIS NEEDS DEFENSING AGAINST NaN returns from sep
                            if 0 <= self.af_step < 3:
                                #to simulate
#                                if self.af_step == 0: spot = 5
#                                if self.af_step == 1: spot = 8
#                                if self.af_step == 2: spot = 7.9
                                
                                self.f_positions.append(g_dev['foc'].focuser.Position)
                                self.f_spot_dia.append(spot)
                                print(self.f_spot_dia, self.f_positions)
                            if self.af_step == 2:
                                
                                a,b,c = Camera.fit_quadratic(self.f_positions, self.f_spot_dia)
                                print ('a, b, c:  ', a ,b, c, self.f_positions, self.f_spot_dia)
                                #find the minimum
                                try:
                                    x = -b/(2*a)
                                except:
                                    x = 11186
                                print('a, b, c, x, spot:  ', a ,b, c, x, a*x**2 + b*x + c)
                                self.new_focus = x
                            if self.af_step == 3:
                                print("Check before seeking to final.")
                                #breakpoint()
                                print('AF result:  ', spot, g_dev['foc'].focuser.Position)
                                self.f_spot_dia = []
                                self.f_positions = []
                            
                            
                                
                        #return  focus, temp, float(spot)
                            
                        resized_a = resize(hdu.data, (768, 768), preserve_range=True)
                        #print(resized_a.shape, resized_a.astype('uint16'))
                        hdu.data = resized_a.astype('uint16')
                        db_data_size = hdu.data.size
                        hdu1.writeto(im_path + db_name, overwrite=True)
                        hdu.data = resized_a.astype('float')
                        istd = np.std(hdu.data)
                        imean = np.mean(hdu.data)                                             
                        img3 = hdu.data/(imean + 3*istd)
                        fix = np.where(img3 >= 0.999)
                        fiz = np.where(img3 <= -0.1)
                        img3[fix] = .999
                        img3[fiz] = -0.1
                        img3[:, 384] = 0.995
                        img3[384, :] = 0.995
                        print(istd, img3.max(), img3.mean(), img3.min())
                        imsave(im_path + jpeg_name, img3)
                        jpeg_data_size = img3.size  -  1024

                        
                        self.enqueue_image(jpeg_data_size, im_path, jpeg_name)
                        self.enqueue_image(text_data_size, im_path, text_name)
                        self.enqueue_image(db_data_size, im_path, db_name)
                        self.enqueue_image(raw_data_size, im_path, raw_name)
                        
                        self.img = None
                        hdu = None
                    except:
                        pass
                        print('Header assembly block failed.')
                    return
                else:               #here we are in waiting for imageReady loop and could send status and check Queue
                    counter += 1
                    g_dev['obs'].update()    #This keeps status alive while camera is looping
                    continue
            except:
                counter += 1
                time.sleep(1)
                continue
            

#
#            #                        self.last_image_name = f'{int(time.time())}_{site}_testimage_{duration}s_no{self.image_number}.jpg'
#            #                        print(f"image file: {self.last_image_name}")
#            #                        self.images.append(self.last_image_name)
#            #                        #self.save_image(self.last_image_name)
#            #                        self.image_number += 1


    def enqueue_image(self, priority, im_path, name):
        image = (im_path, name)
        print("stuffing Queue:  ", priority, im_path, name)
        g_dev['obs'].aws_queue.put((priority, image), block=False)
        
#        aws_req = {"object_name": "raw_data/2019/" + name}
#        aws_resp = g_dev['obs'].api.authenticated_request('GET', 'WMD/upload/', aws_req)
#
#        with open(im_path + name , 'rb') as f:
#            files = {'file': (im_path + name, f)}
#            http_response = requests.post(aws_resp['url'], data=aws_resp['fields'], files=files)
#            print("\n\nhttp_response:  ", http_response, '\n')
        

if __name__ == '__main__':
    req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
    opt = {'size': 50}
    cam = Camera('Maxim.CCDCamera', "cam1")
    cam.expose_command(req, opt)
    #print(c.get_ascom_description())


'''

0 CameraIdle At idle state, available to start exposure
csIdle (2) : Camera is connected but inactive

1 CameraWaiting Exposure started but waiting (for shutter, trigger, filter wheel, etc.)
csFlushing (6) : Camera is flushing the sensor array
csWaitTrigger (7) : Camera is waiting for a trigger signal
csDelay (9) : Camera Control is waiting for it to be time to acquire next image
csFilterWheelMoving (15) : Camera Control window is waiting for filter wheel or focuser
csGuidingSuspended (28) : Autoguiding is suspended while main camera is downloading
csWaitingForDownload (29) : Guide camera is waiting for main camera to finish downloading


5 CameraError Camera error condition serious enough to prevent further operations (connection fail, etc.).
csError (1) : Camera is reporting an error

0 CameraIdle At idle state, available to start exposure
csIdle (2) : Camera is connected but inactive

2 CameraExposing Exposure currently in progress
csExposing (3) : Camera is exposing a light image
csExposingAutoDark (10) : Camera is exposing a dark needed by Simple Auto Dark
csExposingBias (11) : Camera is exposing a Bias frame
csExposingDark (12) : Camera is exposing a Dark frame
csExposingFlat (13) : Camera is exposing a Flat frame
csExposingRed (24) : Camera is exposing a red image (MaxIm+ only)
csExposingGreen (25) : Camera is exposing a green image (MaxIm+ only)
csExposingBlue (26) : Camera is exposing a blue image (MaxIm+ only)


3 CameraReading CCD array is being read out (digitized)
csReading (4) : Camera is reading an image from the sensor array

4 CameraDownload Downloading data to PC
csDownloading (5) : Camera is downloading an image to the computer
csWaiting (8) : Camera Control Window is waiting for MaxIm DL to be ready to accept an image

5 CameraError Camera error condition serious enough to prevent further operations (connection fail, etc.).
csError (1) : Camera is reporting an error
csNoCamera (0) : Camera is not connected

'''    