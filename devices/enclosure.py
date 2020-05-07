import win32com.client
from global_yard import g_dev


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
                  'dome_azimuth': str(round(self.enclosure.Azimuth, 1)),                  'dome_slewing': str(self.enclosure.Slewing),
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
        pass

    def close_command(self, req: dict, opt: dict):
        ''' close the enclosure '''
        self.manager(close_cmd=True)
        print(f"enclosure cmd: close")
        pass

    def slew_alt_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: slew_alt")
        pass

    def slew_az_command(self, req: dict, opt: dict):
        print(f"enclosure cmd: slew_az")
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
        pass

    def wx_is_ok(self):   #A placeholder for a proper weather class or ASCOM device.
        return True

    def manager(self, open_cmd=False, close_cmd=False):     #This is the place where the enclosure is autonomus during operating hours. Delicut Code!!!
        '''
        When the code starts up, we wait for the obs_win_begin <= Sun = Z 88 condition and if Wx is OK
        based on analyzing both Redis data and checking on the enable bit in the  Boltwood
        file, we issue ONE open command then set an Open Block so no more commands are
        issued.  At time of normal closing, we issue a series of close signals -- basically
        all day long.

        While it is night, if WxOK goes bad a close is issued every 2 minutes
        and a one-shot timer then refreshes while Wx is bad. If it is NOT BAD for 15 minutes, then a new
        open is issued.

        Now what if code hangs?  To recover from that ideally we need a deadman style timer operating on a
        separate computer.
        '''

        #  NB NB NB Directly calling enclosure methods is to be discouraged, go through commands so logging
        #           and so forth can be done in one place.
        obs_win_begin, sunZ88Op, sunZ88Cl, ephemNow = self.astro_events.getSunEvents()
        if self.site == 'saf':
             shutter_str = "Dome."
        else:
            shutter_str = "Roof."
        if  obs_win_begin <= ephemNow <= sunZ88Cl:
            self.enclosure.Slaved = True
        else:
            self.enclosure.Slaved = False

        wx_is_ok = g_dev['ocn'].wx_is_ok
        if  (obs_win_begin < ephemNow < sunZ88Cl or open_cmd) \
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
                print("Night time Open issued to the "  + shutter_str)
        elif (obs_win_begin >= ephemNow or ephemNow >= sunZ88Cl \
                and self.mode ==
                'Automatic') or close_cmd:
            if close_cmd:
                self.state = 'User Closed the '  + shutter_str
            else:
                self.state = 'Daytime normally Closed the ' + shutter_str
            if self.status_string.lower() in ['open', 'opening']:
                try:
                    self.enclosure.CloseShutter()
                    print("Daytime Close issued to the " + shutter_str)
                except:
                    print("Shutter busy right now!")
        else:
            #Close the puppy.
            pass

if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

