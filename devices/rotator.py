
import win32com.client

class Rotator:

    def __init__(self, driver: str, name: str):
        self.name = name
        self.rotator = win32com.client.Dispatch(driver)
        self.rotator.Connected = True

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
        status = {
            "name": self.name, 
            "type": "rotator",
            "position_angle": str(self.rotator.Position),
        }
        return status

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