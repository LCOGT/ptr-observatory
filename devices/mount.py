import threading
import win32com.client
import pythoncom
import serial
import time, json
from math import cos, radians
from global_yard import g_dev 
import ptr_events
#from devices.pywinusb_paddle import *

#The mount is not threaded and uses non-blocking seek.
class Mount:

    def __init__(self, driver: str, name: str, settings: dict, tel=False):
        self.name = name
        g_dev['mnt'] = self
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True
#        print('Can Asynch:  ', self.mount.CanSlewAltAzAsync)
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        self.tel = tel
        #print('Can Move Axis is Possible.', self.mount.CanMoveAxis(0), self.mount.CanMoveAxis(1))
        

        if not tel:
            print(f"Mount connected.")
        else:
            print(f"Tel/OTA connected.")
        print(self.mount.Description)
        self._paddle = serial.Serial('COM10', timeout=0.1)
        self._paddle.write(b'ver\n')
        print(self._paddle.read(13).decode()[-8:])
        self._paddle.write(b"gpio iodir 00ff\n")
        self._paddle.write(b"gpio readall\n")
        self.paddleing = False
#        print('a:',self._paddle.read(20).decode())
#        print('b:',self._paddle.read(20).decode())
#        print('c:',self._paddle.read(20).decode())
        print("Paddle connected but not operational??")
#        self.paddle_thread = threading.Thread(target=self.paddle( self._paddle, self.mount), args=())
        #self.paddle_thread.start()
        print("exiting mount _init")


#    def get_status(self):
#        m = self.mount
#        status = {
#            "name": self.name,
#            "type":"mount",
#            "RightAscension": str(m.RightAscension),
#            "Declination": str(m.Declination),
#            "RightAscensionRate": str(m.RightAscensionRate),
#            "DeclinationRate": str(m.DeclinationRate),
#            "AtHome": str(m.AtHome),
#            "AtPark": str(m.AtPark),
#            "Azimuth": str(m.Azimuth),
#            "GuideRateDeclination":  str(0.0), #str(m.GuideRateDeclination),
#            "GuideRateRightAscension": str(0.0), #(m.GuideRateRightAscension),
#            "IsPulseGuiding": str(m.IsPulseGuiding),
#            "SideOfPier": str(m.SideOfPier),
#            "Slewing": str(m.Slewing),
#            "Tracking": str(m.Tracking),
#            "TrackingRate": str(0.0), #(m.TrackingRate),
#            # Target ra and dec throws error if they have not been set. 
#            # Maybe we don't even need to include them in the status...
#            #"TargetDeclination": str(m.TargetDeclination),
#            #"TargetRightAscension": str(m.TargetRightAscension),
#        }
#        return status

    def check_connect(self):
        
        try:
            if self.mount.Connected:
                return
            else:
                print('Found mount not connected, reconnecting.')
                self.mount.Connected = True
                return
        except:
            print('Found mount not connected via try: block fail, reconnecting.')
            self.mount.Connected = True
            return
        
    def get_status(self):
        self.check_connect()
        self.paddle()
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
        if airmass > 10: airmass = 10.0
        airmass = round(airmass, 4)
        #Be careful to preserve order
        #print(self.device_name, self.name)
        if self.tel == False:
            status = {            
                f'timestamp': str(round(time.time(), 3)),
#                f'right_ascension': str(self.mount.RightAscension),
#                f'declination': str(self.mount.Declination),
#                f'sidereal_time': str(self.mount.SiderealTime),
#                f'tracking_right_ascension_rate': str(self.mount.RightAscensionRate),
#                f'tracking_declination_rate': str(self.mount.DeclinationRate),
#                f'azimuth': str(self.mount.Azimuth),
#                f'altitude': str(alt),
#                f'zenith_distance': str(zen),
#                f'airmass': str(airmass),                
#                f'coordinate_system': str(self.rdsys),
                f'pointing_telescope': str(self.inst),  #needs fixing
                f'is_parked': str(self.mount.AtPark).lower(),
                f'is_tracking': str(self.mount.Tracking).lower(),
                f'is_slewing': str(self.mount.Slewing).lower()
            }
        elif self.tel == True:
            status = {            
                f'timestamp': str(round(time.time(), 3)),
                f'right_ascension': str(round(self.mount.RightAscension, 5)),  #RA reported as decimal hours.  Needs to be
                                                                               #decimal degees or Sexagesimal in FITS header.
                                                                               #HA can be reported as decimal hours in FITS.
                f'declination': str(round(self.mount.Declination,4)),
                f'sidereal_time': str(round(self.mount.SiderealTime, 5)),
                f'tracking_right_ascension_rate': str(self.mount.RightAscensionRate),   #Will use asec/s not s/s as ASCOM does.
                f'tracking_declination_rate': str(self.mount.DeclinationRate),
                f'azimuth': str(round(self.mount.Azimuth, 3)),
                f'altitude': str(round(alt, 3)),
                f'zenith_distance': str(round(zen, 3)),
                f'airmass': str(round(airmass,4)),                
                f'coordinate_system': str(self.rdsys),
                f'pointing_instrument': str(self.inst),  #needs fixing
#                f'is_parked': (self.mount.AtPark),
#                f'is_tracking': str(self.mount.Tracking),
#                f'is_slewing': str(self.mount.Slewing)
            }
        else:
            print('Proper device_name is missing, or tel == None')
            status = {'defective':  'status'}
        return status  #json.dumps(status)
    

        
    
    def get_quick_status(self, pre):
        self.check_connect()
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = abs(round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3))
        if airmass > 10: airmass = 10
        airmass = round(airmass, 4)
        pre.append(time.time())
        pre.append(self.mount.RightAscension)
        pre.append(self.mount.Declination)
        pre.append(self.mount.SiderealTime)
        pre.append(self.mount.RightAscensionRate)
        pre.append(self.mount.DeclinationRate)
        pre.append(self.mount.Azimuth)
        pre.append(alt)
        pre.append(zen)
        pre.append(airmass)
        pre.append(self.mount.AtPark)
        pre.append(self.mount.Tracking)
        pre.append(self.mount.Slewing)
        #print(pre)
        return pre
    
    @classmethod
    def two_pi_avg(cls, pre, post, half):
        if abs(pre - post) > half:
            if pre > half:
                pre = pre - 2*half
            if post > half:
                post = post - 2*half

        avg = (pre + post)/2
        while avg < 0:
            avg = avg + 2*half
        while avg >= 2*half:
            avg = avg - 2*half
        return avg
            
        
        
    def get_average_status(self, pre, post):    #Add HA to this calculation.
        self.check_connect()
        t_avg = round((pre[0] + post[0])/2, 3)
        #print(t_avg)
        ra_avg = round(Mount.two_pi_avg(pre[1],  post[1], 12), 6)
        dec_avg = round((pre[2] + post[2])/2, 4)
        sid_avg = round(Mount.two_pi_avg(pre[3],  post[3], 12), 5)
        rar_avg = round((pre[4] + post[4])/2, 6)
        decr_avg = round((pre[5] + post[5])/2, 6)
        az_avg = round(Mount.two_pi_avg(pre[6],  post[6], 180), 3)
        alt_avg = round((pre[7] + post[7])/2, 3)
        zen_avg = round((pre[8] + post[8])/2, 3)
        air_avg = abs(round((pre[9] + post[9])/2, 4))
        if air_avg > 20.0:
            air_avg = 20.0
        if pre[10] and post[10]:
            park_avg = "T"
        else:
            park_avg = "F"
        if pre[11] or post[11]:
            track_avg = "T"
        else:
            track_avg = "F"
        if pre[12] or post[12]:
            slew_avg = "T"
        else:
            slew_avg = "F"

        status = {
            f'timestamp': t_avg,
            f'right_ascension': ra_avg,
            f'declination': dec_avg,
            f'sidereal_time': sid_avg,
            f'tracking_right_ascension_rate': rar_avg,
            f'tracking_declination_rate': decr_avg,
            f'azimuth':  az_avg,
            f'altitude': alt_avg,
            f'zenith_distance': zen_avg,
            f'airmass': air_avg,            
            f'coordinate_system': str(self.rdsys),
            f'instrument': str(self.inst),
            f'is_parked': park_avg,
            f'is_tracking': track_avg,
            f'is_slewing': slew_avg
            
        }
        return status  #json.dumps(status)
    
    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        self.check_connect()
        if action == "go": 
            self.go_command(req, opt) 
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home": 
            self.home_command(req, opt)
        elif action == "flat_panel":
            self.flat_panel_command(req, opt)
        elif action == "tracking":
            self.tracking_command(req, opt)
        elif action == "park":
            self.park_command(req, opt)
        elif action == 'center_on_pixels':
            print (command)
        elif action == 'sky_flat_position':
            print (command)
            ptr_events.flat_spot_now(go=True)
        else:
            print(f"Command <{action}> not recognized.")

    ###############################
    #        Mount Commands       #
    ###############################

    def go_command(self, req, opt):
        ''' Slew to the given ra/dec coordinates. '''
        print("mount cmd: slewing mount", req, opt)

        ra = req['ra']
        dec = req['dec']

        # Offset from sidereal in arcseconds per SI second, default = 0.0
        tracking_rate_ra = opt.get('tracking_rate_ra', 0)

        # Arcseconds per SI second, default = 0.0
        tracking_rate_dec = opt.get('tracking_rate_dec', 0)

        self.mount.Tracking = True
        self.mount.SlewToCoordinatesAsync(ra, dec)

        self.mount.RightAscensionRate = tracking_rate_ra
        self.mount.DeclinationRate = tracking_rate_dec


    def stop_command(self, req, opt):
        print("mount cmd: stopping mount")
        self.mount.AbortSlew()

    def home_command(self, req, opt):
        ''' slew to the home position '''
        print("mount cmd: homing mount")
        if self.mount.AtHome:
            print(f"Mount is at home.")
        elif False: #self.mount.CanFindHome:
            print(f"can find home: {self.mount.CanFindHome}")
            self.mount.Unpark()
            #home_alt = self.settings["home_altitude"]
            #home_az = self.settings["home_azimuth"]
            #self.mount.SlewToAltAzAsync(home_alt, home_az)
            self.mount.FindHome()
        else:
            print(f"Mount is not capable of finding home. Slewing to zenith.")
            self.mount.SlewToAltAzAsync(88., 0.)

    def flat_panel_command(self, req, opt):
        ''' slew to the flat panel if it exists '''
        print("mount cmd: slewing to flat panel")
        pass

    def tracking_command(self, req, opt):
        ''' set the tracking rates, or turn tracking off '''
        print("mount cmd: tracking changed")
        pass

    def park_command(self, req, opt):
        ''' park the telescope mount '''
        print("mount cmd: parking mount")
        print(self.mount.CanPark)
        self.mount.Park()
        
    def paddle(self):
        '''
        The real way this should work is monitor if a speed button is pushed, then log the time and
        start the thread.  If no button pushed for say 30 seconds, stop thread and re-join.  That way
        image operations are minimally disrupted.
        
        Normally this will never be started, unless we are operating locally in the observatory.
        '''

        self._paddle.write(b"gpio readall\n")
        temp = self._paddle.read(21).decode()
        #print ('|' + temp[16:18] +'|')
        button = temp[17]
        spd= temp[16]
        direc = ''
        speed = 0.0
        #print("Btn:  ", button, "Spd:  ", speed, "Dir:  ", direc)
        if button == 'E': direc = 'N'
        if button == 'B': direc = 'S'
        if button == 'D': direc = 'E'
        if button == '7': direc = 'W'
        if button == 'C': direc = 'NE'
        if button == '9': direc = 'SE'
        if button == '3': direc = 'SW'
        if button == '6': direc = 'NW'
        if spd ==  'C': 
            speed = 0.
            EW = 1
            NS = 1
        if spd == '8': 
            speed = 15.
            EW = 1
            NS = 1
        if spd ==  '4': 
            speed = 45.
            EW = 1
            NS = 1
        if spd ==  '0': 
            speed = 135.
            EW = 1
            NS = 1
        if spd ==  'D': 
            speed = 0.
            EW = -1
            NS = 1
        if spd == '9': 
            speed = 15.
            EW = -1
            NS = 1
        if spd ==  '5': 
            speed = 45.
            EW = -1
            NS = 1
        if spd ==  '1': 
            speed = 135.
            EW = -1
            NS = 1
        if spd ==  'E': 
            speed = 0.
            EW = 1
            NS = -1
        if spd == 'A': 
            speed = 15.
            EW = 1
            NS = -1
        if spd ==  '6': 
            speed = 45.
            EW = 1
            NS = -1
        if spd ==  '2': 
            speed = 135.
            EW = 1
            NS = -1
        if spd ==  'F': 
            speed = 0.
            EW = -1
            NS = -1
        if spd == 'B': 
            speed = 15.
            EW = -1
            NS = -1
        if spd == '7': 
            speed = 45.
            EW = -1
            NS = -1
        if spd == '3': 
            speed = 135.
            EW = -1
            NS = -1

        #print(button, spd, direc, speed)
#            if direc != '':
        #print(direc, speed)
        _mount = self.mount
        #Need to add diagonal moves
        if direc == 'N':
            _mount.DeclinationRate = NS*speed
            self.paddleing = True
            print('cmd:  ', direc,  NS*speed)
        if direc == 'S':
            _mount.DeclinationRate = -NS*speed
            self.paddleing = True
            print('cmd:  ',direc,  -NS*speed)
        if direc == 'E':
            _mount.RightAscensionRate = EW*speed/15.   #Not quite the correct divisor.
            self.paddleing = True
            print('cmd:  ',direc, EW*speed/15.)
        if direc == 'W': 
            _mount.RightAscensionRate = -EW*speed/15.
            self.paddleing = True
            print('cmd:  ',direc, -EW*speed/15.)
        if direc == '': 
            _mount.DeclinationRate = 0.0
            _mount.RightAscensionRate = 0.0
            self.paddleing = False
        return

            
            
        
        '''
         class Darkslide(object):
        
           def __init__(self, pCOM):
               self.slideStatus = 'unknown'
        
           def openDarkslide(self):
               self._com = serial.Serial(pCom, timeout=0.1)
               self._com.write(b'@')
               self.slideStatus = 'open'
               self._com.close()
        
           def closeDarkslide(self):
               self._com = serial.Serial(pCom, timeout=0.1)
               self._com.write(b'A')
               self.slideStatus = 'closed'
               self._com.close()
        
           def darkslideStatus(self):
               return self.slideStatus
        
        
        class Probe(object):
        
            def __init__(self, pCom):
                self.probePosition = None
                print('Probe class called with:  ', pCom)
                self.commPort = pCom
        
            def probeRead(self):
               with serial.Serial(self.commPort, timeout=0.3) as com:
                   com.write(b'R1\n')
                   self.probePosition = float(com.read(6).decode())
                   com.close()
                   print(self.probePosition)
        '''

        
if __name__ == '__main__':
    req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
    opt = {'area': 50}
    m = Mount('ASCOM.PWI4.Telescope', "mnt1", {})
    m.paddle()
#    pre=[]
#    post=[]
#    m.get_quick_status(pre)
#    time.sleep(2)
#    m.get_quick_status(post)
#    print(m.get_average_status(pre, post))
    #print(c.get_ascom_description())

