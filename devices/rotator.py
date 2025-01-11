'''
rotator.py  rotator.py  rotator.py  rotator.py  rotator.py  rotator.py

'''
import time
import win32com.client
import psutil
from global_yard import g_dev

# We only use Observatory in type hints, so use a forward reference to prevent circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING: 
    from obs import Observatory


def findProcessIdByName(processName):
    '''
    Get a list of all the PIDs of a all the running process whose name contains
    the given string processName
    '''
    listOfProcessObjects = []
    #Iterate over the all the running process
    for proc in psutil.process_iter():
       try:
           pinfo = proc.as_dict(attrs=['pid', 'name', 'create_time'])
           # Check if process name contains the given name string.
           if processName.lower() in pinfo['name'].lower() :
               listOfProcessObjects.append(pinfo)
       except (psutil.NoSuchProcess, psutil.AccessDenied , psutil.ZombieProcess) :
           pass
    return listOfProcessObjects

class Rotator:
    def __init__(self, driver: str, name: str, site_config: dict, observatory: 'Observatory'):
        self.name = name
        self.config = site_config['rotator'][name]
        self.obs = observatory
        g_dev["rot"] = self

        # Configure the role, if it exists
        # Current design allows for only one role per device
        # We can add more roles by changing self.role to a list and adjusting any references
        self.role = None
        for role, device in site_config['device_roles'].items():
            if device == name:
                self.role = role
                break

        win32com.client.pythoncom.CoInitialize()
        self.driver=driver
        self.rotator = win32com.client.Dispatch(driver)
        time.sleep(3)

        self.rotator.Connected = True
        self.rotator_message = "-"
        print("Rotator connected,  at:  ", round(self.rotator.TargetPosition, 4))

        # The telescope driver also needs to be connected
        self.rotator_telescope = win32com.client.Dispatch(driver.replace('Rotator','Telescope'))
        try:
            self.rotator_telescope.Connected = True
        except:
            breakpoint()

        self.TargetPosition=self.rotator.TargetPosition
        self.Position=self.rotator.Position
        self.IsMoving=self.rotator.IsMoving

        self.rotator_meant_to_be_rotating = True

    def get_status(self):
        """
        The position is expressed as an angle from 0 up to but not including
        360 degrees, counter-clockwise against the sky. This is the standard
        definition of Position Angle. However, the rotator does not need to
        (and in general will not) report the true Equatorial Position Angle,
        as the attached imager may not be precisely aligned with the rotator's
        indexing. It is up to the client to determine any offset between
        mechanical rotator position angle and the true Equatorial Position
        Angle of the imager, and compensate for any difference.
        """

        self.TargetPosition=self.rotator.TargetPosition
        self.Position=self.rotator.Position
        self.IsMoving=self.rotator.IsMoving
        # NB we had an exception here with Target position.  mORE THAN ONE OF THESE! 220210709
        try:

            status = {
                "position_angle": round(self.TargetPosition, 4),
                "rotator_moving": self.IsMoving,
            }
        except:
            try:
                status = {
                    "position_angle": round(self.TargetPosition, 4),
                    "rotator_moving": self.IsMoving,
                }
            except:
                status = {
                    "position_angle": round(0.0, 4),
                    "rotator_moving": False,
                }

        return status

    def get_quick_status(self, quick):
        quick.append(time.time())
        try:
            quick.append(self.Position)
            quick.append(self.IsMoving)
        except:
            quick.append(0.0)
            quick.append(False)
        return quick

    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0]) / 2, 3))
        average.append(round((pre[1] + post[1]) / 2, 3))
        if pre[2] or post[2]:
            average.append(True)
        else:
            average.append(False)
        return average

    def parse_command(self, command):
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]

        if action == "move_relative":
            self.move_relative_command(req, opt)
        elif action == "move_absolute":
            self.move_absolute_command(req, opt)
        elif action == "stop":
            self.stop_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print(f"Command <{action}> not recognized.")

    ###############################
    #       Rotator Commands      #
    ###############################

    def move_relative_command(self, req: dict, opt: dict):
        """Sets the rotator position by moving relative to current position."""
        print("rotator cmd: move_relative")
        position = float(req["position"])
        self.rotator.Move(position)

    def move_absolute_command(self, req: dict, opt: dict):
        """Sets the rotator position by moving to an absolute position."""
        print("rotator cmd: move_absolute")
        position = float(req["position"])
        self.rotator.MoveAbsolute(position)

    def stop_command(self, req: dict, opt: dict):
        """Stops rotator movement immediately."""
        print("rotator cmd: stop")
        self.rotator_meant_to_be_rotating = False
        self.rotator.Halt()

    def home_command(self, req: dict, opt: dict):
        """Sets the rotator to the home position."""
        print("rotator cmd: home")
        self.rotator.Action('HomeDevice',1)

