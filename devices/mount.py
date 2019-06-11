import win32com.client

class Mount:

    def __init__(self, driver: str, name: str, settings: dict):
        self.name = name
        self.settings = settings
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True

        print(f"Mount connected.")
        print(self.mount.Description)

    def get_status(self):
        m = self.mount
        status = {
            "name": self.name,
            "type":"mount",
            "RightAscension": str(m.RightAscension),
            "Declination": str(m.Declination),
            "RightAscensionRate": str(m.RightAscensionRate),
            "DeclinationRate": str(m.DeclinationRate),
            "AtHome": str(m.AtHome),
            "AtPark": str(m.AtPark),
            "Azimuth": str(m.Azimuth),
            "GuideRateDeclination": str(m.GuideRateDeclination),
            "GuideRateRightAscension": str(m.GuideRateRightAscension),
            "IsPulseGuiding": str(m.IsPulseGuiding),
            "SideOfPier": str(m.SideOfPier),
            "Slewing": str(m.Slewing),
            "Tracking": str(m.Tracking),
            "TrackingRate": str(m.TrackingRate),
            # Target ra and dec throws error if they have not been set. 
            # Maybe we don't even need to include them in the status...
            #"TargetDeclination": str(m.TargetDeclination),
            #"TargetRightAscension": str(m.TargetRightAscension),
        }
        return status

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
            home_alt = self.settings["home_altitude"]
            home_az = self.settings["home_azimuth"]
            #self.mount.SlewToAltAzAsync(home_alt, home_az)
            self.mount.FindHome()
        else:
            self.mount.Tracking = False
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
