import win32com.client
import time

class Camera:

    """ 
    http://ascom-standards.org/Help/Developer/html/T_ASCOM_DriverAccess_Camera.htm
    """

    def __init__(self, driver='ASCOM.Simulator.Camera'):

        # Define the camera driver, then connect to it.
        self.camera = win32com.client.Dispatch(driver)
        self.camera.Connected = True

        print("Connected to camera.")
        print(self.camera.Description)
    
    def get_status(self):
        status = {"type":"camera"}
        return status

    def get_ascom_description(self):
        return self.camera.Description

    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "expose":
            self.expose(req, opt)

    def expose(self, required_params, optional_params):
        c = self.camera
        bin = int(optional_params.get('bin', 1))
        gain = optional_params.get('gain', 1)
        count = int(optional_params.get('count', 1))
        exposure_time = required_params.get('time', 5)
        
        # Setting binning requires also setting NumX and NumY: number of pixels per side.
        c.NumX = c.NumX / bin
        c.NumY = c.NumY / bin
        c.BinX = bin
        c.BinY = bin

        try:
            print("starting exposure")
            c.StartExposure(exposure_time, False)
            c.StartExposure(exposure_time, False)
        except Exception as e:
            print("failed exposure")
            print(e)

        for i in range(20):
            pc = c.PercentCompleted
            print(pc)
            if pc == 100: break
            time.sleep(1)

        


        






if __name__ == '__main__':
    c = Camera('ASCOM.Simulator.Camera')
    print(c.get_ascom_description())

        