import win32com.client
from global_yard import g_dev

import time

class Enclosure:

    def __init__(self, driver: str, name: str, config: dict, astro_events):
        self.name = name
        self.astro_events = astro_events
        self.site = config['site']
        g_dev['enc'] = self
        win32com.client.pythoncom.CoInitialize()
        self.enclosure = win32com.client.Dispatch(driver)
        print(self.enclosure)
        self.enclosure.Connected = True
        print(f"enclosure connected.")
        print(self.enclosure.Description)
        self.state = 'Closed.  Initialized class property value.'
        self.mode = 'Manual'   #  Auto|User Control|User Close|Disable
        self.enclosure_message = '-'
        self.cycles = 0           #if >=3 inhibits reopening for Wx
        self.wait_time = 0        #A countdown to re-open
        self.wx_close = False     #If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.external_close = False   #If made true by operator system will not reopen for the night
        self.dome_opened = False   #memory of prior issued commands  Restarting code may close dome one time.
        self.dome_homed = False
        self.wx_test = False
        self.wx_hold_time = None


    def get_status(self) -> dict:
        #<<<<The next attibute reference fails at SAF, usually spurious Dome Ring Open report.
        #<<< Have seen other instances of failing.
        try:
            shutter_status = self.enclosure.ShutterStatus
        except:
            print("self.enclosure.Roof.ShutterStatus -- Faulted. ")
            shutter_status = 5
        if shutter_status == 0:
            stat_string = "Open"
        elif shutter_status == 1:
             stat_string = "Closed"
        elif shutter_status == 2:
             stat_string = "Opening"
        elif shutter_status == 3:
             stat_string = "Closing"
        elif shutter_status == 4:
             stat_string = "Error"
        else:
             stat_string = "Fault"

        if self.site == 'saf':
            status = {'shutter_status': stat_string,
                  'enclosure_slaving': str(self.enclosure.Slaved),
                  'dome_azimuth': str(round(self.enclosure.Azimuth, 1)),
                  'dome_slewing': str(self.enclosure.Slewing),
                  'enclosure_mode': str(self.mode),
                  'enclosure_message': str(self.state)}
        else:
            status = {'roof_status': stat_string,
                  'enclosure_slaving': str(self.enclosure.Slaved),
                  'enclosure_mode': str(self.mode),
                  'enclosure_message': str(self.state)}
        #print('Enclosure status:  ', status
        self.status_string = stat_string
        self.manager()   #There be monsters here. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        if action == "open":
            self.open_command(req, opt)
        elif action == "close":
            self.close_command(req, opt)
        elif action == "setAuto":
            self.mode = 'Automatic'
            print("Enclosure set to Automatic.")
        elif action == "setManual":
            self.mode = 'Manual'
            print("Enclosure set to Manual.")
        elif action == "slew_alt":
            self.slew_alt_command(req, opt)
        elif action == "slew_az":
            self.slew_az_command(req, opt)
        elif action == "sync_az":
            self.sync_az_command(req, opt)
        elif action == "sync_mount":
            self.sync_mount_command(req, opt)
        elif action == "park":
            self.park_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")


    ###############################
    #      Enclosure Commands     #
    ###############################

    def open_command(self, req: dict, opt: dict):
        ''' open the enclosure '''
        self.manager(open_cmd=True)
        print(f"enclosure cmd: open")
        self.dome_open = True
        self.dome_home = True
        pass

    def close_command(self, req: dict, opt: dict):
        ''' close the enclosure '''
        self.manager(close_cmd=True)
        print(f"enclosure cmd: close")
        self.dome_open = False
        self.dome_home = True
        pass

    def slew_alt_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: slew_alt")
        pass

    def slew_az_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: slew_az")
        self.dome_home = False    #As a general rule
        pass

    def sync_az_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: sync_alt")
        pass

    def sync_mount_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: sync_az")
        pass

    def park_command(self, req: dict, opt: dict):
        ''' park the enclosure if it's a dome '''
        print(f"enclosure cmd: park")
        self.dome_home = True
        pass

    def wx_is_ok(self):   #A placeholder for a proper weather class or ASCOM device.
        return True

    def manager(self, open_cmd=False, close_cmd=False):     #This is the place where the enclosure is autonomus during operating hours. Delicut Code!!!
        '''
        Now what if code hangs?  To recover from that ideally we need a deadman style timer operating on a
        separate computer.
        '''

        #  NB NB NB Gather some facts:
        obs_win_begin, sunset, sunrise, ephemNow = self.astro_events.getSunEvents()
        az = g_dev['evnt'].sun_az_now()
        az = az - 180.
        if az < 0:
            az += 360.
        if self.site == 'saf':
            shutter_str = "Dome."
        else:
            shutter_str = "Roof."

        if  obs_win_begin <= ephemNow <= sunrise:
            self.enclosure.Slaved = True
            # nb tHIS SHOULD WORK DIFFERENT. Open then slew to Opposite az to Sun set.  Stay
            # there until telescope is unparked, then  slave the dome.  Or maybe leave it at
            # park, where Neyle can see it from house and always ready to respong to a Wx close.
        else:
            try:
                breakpoint()
                self.enclosure.Slaved = False
            except:
                pass    #Megawan (roofs) do not slave

        wx_is_ok = g_dev['ocn'].wx_is_ok

        #  Check the Wx and go into the Wx hold sequence.   The third hold Closes and
        #  turns off Autmatic for owner re-enable.

        #  NB NB what do we want to do if Wx goes bad outside of the window?
        if (not wx_is_ok or self.wx_test) and self.status_string.lower() in ['open', 'opening']:
            self.enclosure.Slaved = False
            self.enclosure.CloseShutter()
            self.dome_opened = False
            self.dome_homed = True
            if self.wx_test:
                self.wx_hold_time = time.time() + 120    #2 minutes
            else:
                self.wx_hold_time = time.time() + 900    #15 minutes
            self.cycles += 1
            print("Weather close issued, cycle:  ", self.cycles)

        #NB NB First deal with the possible observing window being available or not.

        if  obs_win_begin <= ephemNow <= sunrise:
            #  We are now in the full operational window.
            if  obs_win_begin <= ephemNow <= sunset and self.mode == 'Automatic':
                print('\nSlew to opposite the azimuth of the Sun, open and cool-down. Az =  ', az)
                #NB There is no corresponding warm up phase in the Morning.
                if self.status_string.lower() in ['closed', 'closing']:
                    self.enclosure.OpenShutter()
                    self.dome_opened = True
                    self.dome_homed = True
                if self.status_string.lower() in ['open']:
                    try:
                        self.enclosure.SlewToAzimuth(az)
                    except:
                        pass
                    self.dome_homed = False
                    #self.enclosure.Slaved = False


            if  (obs_win_begin < ephemNow < sunrise or open_cmd) \
                    and self.mode == 'Automatic' \
                    and wx_is_ok \
                    and self.wait_time <= 0 \
                    and self.enclosure.ShutterStatus == 1: #Closed
                if open_cmd:
                    self.state = 'User Opened the ' + shutter_str
                else:
                    self.state = 'Automatic nightime Open ' + shutter_str + '   Wx is OK; in Observing window.'
                self.cycles += 1           #if >=3 inhibits reopening for Wx  -- may need shelving so this persists.
                #A countdown to re-open
                if self.status_string.lower() in ['closed', 'closing']:
                    self.enclosure.OpenShutter()   #<<<<NB NB NB Only enable when code is fully proven to work.
                    self.enclosure.Slaved = True
                    print("Night time Open issued to the "  + shutter_str, +   '   Following Mounting.')
            elif (obs_win_begin >= ephemNow or ephemNow >= sunrise \
                    and self.mode ==
                    'Automatic') or close_cmd:
                if close_cmd:
                    self.state = 'User Closed the '  + shutter_str
                else:
                    self.state = 'Daytime normally Closed the ' + shutter_str
                if self.status_string.lower() in ['open', 'opening']:
                    try:
                        self.enclosure.Slaved = False
                        self.enclosure.CloseShutter()
                        print("Daytime Close issued to the " + shutter_str  + "   No longer follwing Mount.")
                    except:
                        print("Shutter busy right now!")
        else:
            #  We are outside of the observing window so close the dome, with a one time command to
            #  deal with the case of software restarts. Do not pound on the dome because it makes
            #  off-hours entry difficult.
            #  NB this happens regardless of automatic mode.

            if not self.dome_homed:
                self.enclosure.Slaved = False
                self.enclosure.CloseShutter()
                self.dome_opened = False
                self.dome_homed = True
                print("One time close of enclosure issued, normally after a code restart.")


if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

