import win32com.client
import pythoncom
import time, json
from math import cos, radians
from global_yard import g_dev 

#The mount is not threaded and uses non-blocking seek.
class Mount:

    def __init__(self, driver: str, name: str, settings: dict):
        self.name = name
        g_dev['mnt'] = self
        self.device_name = name
        self.settings = settings
        win32com.client.pythoncom.CoInitialize()
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True
        self.rdsys = 'J.now'
        self.inst = 'tel1'
        

        print(f"Mount connected.")
        print(self.mount.Description)

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
        
        
    def get_status(self):
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3)
        if airmass > 10: airmass = 10.0
        airmass = round(airmass, 4)
        #Be careful to preserve order
        status = {            
                f'{self.device_name}_timestamp': str(round(time.time(), 3)),
                f'{self.device_name}_ra': str(self.mount.RightAscension),
                f'{self.device_name}_dec': str(self.mount.Declination),
                f'{self.device_name}_sid': str(self.mount.SiderealTime),
                f'{self.device_name}_tracking_ra_rate': str(self.mount.RightAscensionRate),
                f'{self.device_name}_tracking_dec_rate': str(self.mount.DeclinationRate),
                f'{self.device_name}_az': str(self.mount.Azimuth),
                f'{self.device_name}_alt': str(alt),
                f'{self.device_name}_zen': str(zen),
                f'{self.device_name}_air': str(airmass),                
                f'{self.device_name}_rdsys': str(self.rdsys),
                f'{self.device_name}_inst': str(self.inst),
                f'{self.device_name}_is_parked': (self.mount.AtPark),
                f'{self.device_name}_is_tracking': str(self.mount.Tracking),
                f'{self.device_name}_is_slewing': str(self.mount.Slewing)

            
        }
        return status  #json.dumps(status)
    
    def get_quick_status(self, pre):
        alt = self.mount.Altitude
        zen = round((90 - alt), 3)
        if zen > 90:
            zen = 90.0
        if zen < 0.1:    #This can blow up when zen <=0!
            new_z = 0.1
        else:
            new_z = zen
        sec_z = 1/cos(radians(new_z))
        airmass = round(sec_z - 0.0018167*(sec_z - 1) - 0.002875*((sec_z - 1)**2) - 0.0008083*((sec_z - 1)**3),3)
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
        print(pre)
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
            
        
        
    def get_average_status(self, pre, post):
        t_avg = round((pre[0] + post[0])/2, 3)
        print(t_avg)
        ra_avg = round(Mount.two_pi_avg(pre[1],  post[1], 12), 6)
        dec_avg = round((pre[2] + post[2])/2, 4)
        sid_avg = round(Mount.two_pi_avg(pre[3],  post[3], 12), 5)
        rar_avg = round((pre[4] + post[4])/2, 6)
        decr_avg = round((pre[5] + post[5])/2, 6)
        az_avg = round(Mount.two_pi_avg(pre[6],  post[6], 180), 3)
        alt_avg = round((pre[7] + post[7])/2, 3)
        zen_avg = round((pre[8] + post[8])/2, 3)
        air_avg = round((pre[9] + post[9])/2, 4)
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
            f'{self.device_name}_timestamp': t_avg,
            f'{self.device_name}_ra': ra_avg,
            f'{self.device_name}_dec': dec_avg,
            f'{self.device_name}_sid': sid_avg,
            f'{self.device_name}_tracking_ra_rate': rar_avg,
            f'{self.device_name}_tracking_dec_rate': decr_avg,
            f'{self.device_name}_az':  az_avg,
            f'{self.device_name}_alt': alt_avg,
            f'{self.device_name}_zen': zen_avg,
            f'{self.device_name}_air': air_avg,            
            f'{self.device_name}_rdsys': str(self.rdsys),
            f'{self.device_name}_inst': str(self.inst),
            f'{self.device_name}_is_parked': park_avg,
            f'{self.device_name}_is_tracking': track_avg,
            f'{self.device_name}_is_slewing': slew_avg
            
        }
        return status  #json.dumps(status)
    
    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

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
        else:
            print(f"Command <{action}> not recognized.")

    ###############################
    #        Mount Commands       #
    ###############################

    def go_command(self, req, opt):
        ''' Slew to the given ra/dec coordinates. '''
        print("mount cmd: slewing mount")

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
        
if __name__ == '__main__':
    req = {'time': 1,  'alias': 'ea03', 'frame': 'Light', 'filter': 2}
    opt = {'area': 50}
    m = Mount('ASCOM.PWI4.Telescope', "mnt1", {})
    pre=[]
    post=[]
    m.get_quick_status(pre)
    time.sleep(2)
    m.get_quick_status(post)
    print(m.get_average_status(pre, post))
    #print(c.get_ascom_description())

