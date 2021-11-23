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
        if driver != "Null":
            self.null_selector = False
            win32com.client.pythoncom.CoInitialize()
            self.selector = win32com.client.Dispatch(driver)
            self.selector.Connected = True
            default = int(self.config['selector1']['default'] + 1)
            self.selector.SetSwitchValue(0,default)
            self.port_index = int(self.selector.GetSwitchValue(0))
        else:
            self.null_selector = True
            self.port_index = 0
            
        #print("Instrument Selector position:  ", int(self.selector.GetSwitchValue(0)))
        
    

    def get_status(self):
        if self.null_selector:
            desc = self.config['selector1']['instruments'][0]
            camera = self.config['selector1']['cameras'][0]
            guider = self.config['selector1']['guiders'][0]
            status = {
                'port': self.port_index,
                'instrument': desc,
                'camera': camera,
                'guider': guider
                }
            return status
            
        try:
            port = int(self.selector.GetSwitchValue(0))
            #print("Selector found at position: ", port)
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
            breakpoint()
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
                g_dev['cam'].active_camera =  self.config['selector1']['cameras'][port] 
                g_dev['cam'].active_guider = self.config['selector1']['guiders'][port] 
                print("Port ", port, '; Instrument:  ', port + 1,  'was selected.')
                print("Active camera was changed to: ", self.config['selector1']['cameras'][port] )
                print("Active guider was changed to: ", self.config['selector1']['guiders'][port] )
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