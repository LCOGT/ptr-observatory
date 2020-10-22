
import win32com.client
import time
from global_yard import g_dev

class Rotator:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev['rot'] = self
        win32com.client.pythoncom.CoInitialize()
        self.rotator = win32com.client.Dispatch(driver)
        self.rotator.Connected = True
        self.rotator_message = '-'
        print(f"rotator connected.")
        print(self.rotator.Description)

    def get_status(self):
        '''
        The position is expressed as an angle from 0 up to but not including
        360 degrees, counter-clockwise against the sky. This is the standard
        definition of Position Angle. However, the rotator does not need to
        (and in general will not) report the true Equatorial Position Angle,
        as the attached imager may not be precisely aligned with the rotator's
        indexing. It is up to the client to determine any offset between
        mechanical rotator position angle and the true Equatorial Position
        Angle of the imager, and compensate for any difference.
        '''
        #NB we had an exception here with Target position.
        status = {
            "position_angle": round(self.rotator.TargetPosition, 4),
            "rotator_moving": self.rotator.IsMoving,
        }
        #print(self.rotator.TargetPosition)
        return status

    def get_quick_status(self, quick):
        quick.append(time.time())
        quick.append(self.rotator.Position)
        quick.append(self.rotator.IsMoving)

        return quick

    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0])/2, 3))
        average.append(round((pre[1] + post[1])/2, 3))
        if pre[2] or post[2]:
            average.append(True)
        else:
            average.append(False)
        return average

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

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
        ''' set the focus position by moving relative to current position '''
        print(f"rotator cmd: move_relative")
        position = float(req['position'])
        self.rotator.Move(position)

    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"rotator cmd: move_absolute")
        position = float(req['position'])
        self.rotator.MoveAbsolute(position)

    def stop_command(self, req: dict, opt: dict):
        ''' stop rotator movement immediately '''
        print(f"rotator cmd: stop")
        self.rotator.Halt()

    def home_command(self, req: dict, opt: dict):
        ''' set the rotator to the home position'''
        print(f"rotator cmd: home")
        pass