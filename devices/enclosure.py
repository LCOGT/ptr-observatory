import win32com.client
from global_yard import g_dev
import ptr_events


class Enclosure:

    def __init__(self, driver: str, name: str):
        self.name = name
        g_dev['enc'] = self
        self.enclosure = win32com.client.Dispatch(driver)
        #breakpoint()
        self.enclosure.Connected = True

        print(f"enclosure connected.")
        print(self.enclosure.Description)
        self.state = 'Closed, normal operation, waiting for observing window.'    #A descriptive string of the state of the enclosure
        self.cycles = 0           #if >=3 inhibits reopening for Wx
        self.wait_time = 0        #A countdown to re-open
        self.wx_close = False     #If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.external_close = False   #If made true by operator system will not reopen for the night

    def get_status(self) -> dict:
        shutter_status = self.enclosure.ShutterStatus
        if shutter_status == 0:
            stat_string = "open"  
        elif shutter_status == 1:
             stat_string = "closed"
        elif shutter_status == 2:
             stat_string = "opening"
        elif shutter_status == 3:
             stat_string = "closing"
        elif shutter_status == 4:
             stat_string = "error"
        status = {'shutter_status': stat_string}
        return status

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "open":
            self.open_command(req, opt)
        elif action == "close":
            self.close_command(req, opt)
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
        print(f"enclosure cmd: open")
        pass

    def close_command(self, req: dict, opt: dict):
        ''' close the enclosure '''
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
    
    def manager(self):     #This is the place where the enclosure is autonomus during operating hours. Delicut Code!!!
        
        #   ptr_events.sunZ88Op <=
        if  ptr_events.sunZ88Op < ptr_events.ephem.now() < ptr_events.sunZ88Cl \
                               and self. wx_is_ok() \
                               and self.wait_time <= 0 \
                               and self.enclosure.ShutterStatus == 1: #Closed
            #print('open')
            #Since this could be a re-open we assume other code opened covers, unparked, seeked, etc.
            #open
            self.state = 'Open, Wx OK, in Observing window.'    #A descriptive string of the state of the enclosure
            self.cycles += 1           #if >=3 inhibits reopening for Wx    #NBNBN THis needs to be persistend across envocatins of the code when testing.
            self.wait_time = 0
            #A countdown to re-open
            self.enclosure.OpenShutter()
            ptr_events.flat_spot_now(go=True)



            
        else:
            #Close the puppy.
            pass
        
if __name__ =='__main__':
    print('Enclosure class started locally')
    enc = Enclosure('ASCOM.SkyRoof.Dome', 'enclosure1')

