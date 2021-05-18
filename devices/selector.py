import win32com.client
from global_yard import g_dev
import time
import serial


class Selector:

    def __init__(self, driver: str, name: str, config: dict):
        self.name = name
        g_dev['sel']= self
        self.config = config['selector']
        #print("SEL:  ", self.config)
        win32com.client.pythoncom.CoInitialize()
        self.selector = win32com.client.Dispatch(driver)
        self.selector.Connected = True
        default = int(self.config['selector1']['default'] + 1)
        self.selector.SetSwitchValue(0,default)
        #print("Instrument Selector position:  ", int(self.selector.GetSwitchValue(0)))
        
    

    def get_status(self):
        try:
            port = int(self.selector.GetSwitchValue(0))
            desc = self.config['selector1']['instruments'][port - 1]
            camera = self.config['selector1']['cameras'][port - 1]
            guider = self.config['selector1']['guiders'][port - 1]
            status = {
                'port': port,
                'instrument': desc,
                'camera': camera,
                'guider': guider
                }
            return status
        except:
            time.sleep(10)
            port = int(self.selector.GetSwitchValue(0))
            desc = self.config['selector1']['instruments'][port - 1]
            camera = self.config['selector1']['cameras'][port - 1]
            guider = self.config['selector1']['guiders'][port - 1]
            status = {
                'port': port,
                'instrument': desc,
                'camera': camera,
                'guider': guider
                }
            return status
        
    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "new_selection":
            port = req['port']
            if 0 <= port <= 3:
                self.selector.SetSwitchValue(0, port+1)
                print("Port ", port, '; Instrument:  ', port + 1,  'was selected.')
                print("Active camera was changed to: ", self.config['selector1']['cameras'][port - 1] )
                print("Active guider was changed to: ", self.config['selector1']['guiders'][port - 1] )
            else:
                print("Incorrect port specified for instrument selection, at port:  ", int(self.selector.GetSwitchValue(0)) )
            #self.set_position_command(req, opt)
        elif action == "set_name":
            self.set_name_command(req, opt)
        elif action == "home":
            self.home_command(req, opt)
        else:
            print("Command <{action}> not recognized.")




if __name__ == '__main__':
    import config
    pass