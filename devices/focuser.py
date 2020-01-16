
import win32com.client
import time
import serial
from global_yard import g_dev 
import config_east as config
import ptr_config

#TEMP COEFF ESTIMATED 20190824   fx= round(-164.0673*C_pri +13267.37, 1)  #A very good 1.5C span.  9986@20C. Random Hyst ~ 500 microns! :((( )))
#-104.769 + 12457.5   2019083

'''
class Probe(object):

    def __init__(self, pCom):
        self.probePosition = None
        print('Probe class called with:  ', pCom)
        self.commPort = pCom

    def probeRead(self):
       with serial.Serial(self.commPort, timeout=0.3) as com:
           com.write(b'R1\n')
           self.probePosition = float(com.read(7).decode())  #check # significant digits.
           print(self.probePosition)


def probeRead(com_port):
       with serial.Serial(com_port, timeout=0.3) as com:
           com.write(b'R1\n')
           probePosition = float(com.read(7).decode())  #check # significant digits.
           print(probePosition)
           

probeRead('COM31')
-6.846

'''

def probeRead(com_port):
       with serial.Serial(com_port, timeout=0.3) as com:
           com.write(b'R1\n')
           probePosition = float(com.read(7).decode())*994.96 - 137 #Corrects Probe to Stage. Up and down, lash = 5000 enc.
           print(round(probePosition, 1))

class Focuser:

    def __init__(self, driver: str, name: str, config):
        self.name = name
        g_dev['foc'] = self
        self.config = config['focuser']['focuser1']
        self.focuser = win32com.client.Dispatch(driver)
        self.focuser.Connected = True
        print(f"focuser connected.")
        print(self.focuser.Description)
        time.sleep(0.2)
        try:
            try:
                self.reference = self.calculate_compensation( self.focuser.Temperature)   #need to change to config supplied
                print("Focus reference updated from Compensated value:  ", self.reference)
            except:
                self.reference = float(ptr_config.get_focal_ref('gf01'))   #need to change to config supplied
                print("Focus reference updated from Night Shelf:  ", self.reference)
        except:
            self.reference = int(self.config['reference'])
            print("Focus reference derived from supplied Config dicitionary:  ", self.reference)
        self.focuser.Move(int(self.reference))
    
    def calculate_compensation(self, temp_primary):
        
        if -5 <= temp_primary <= 45:
            trial =round(float(self.config['coef_c'])*temp_primary + float(self.config['coef_0']), 1)
            trial = max(trial,500)  #These values would change for Gemini to more like 11900 max
            trial = min(trial, 14000)
            print('Calculated focus compensated position:  ', trial)
            return int(trial)
        else:
            print('Primary out of range -5 to 45C, using reference focus')
            return self.config['reference']

    def get_status(self):
        status = {
            "focus_position": str(round(self.focuser.Position, 1)),
            "focus_moving": str(self.focuser.IsMoving).lower(),
            "focus_temperature": str(self.focuser.Temperature)
            }
        return status

    def get_quick_status(self, quick):
        quick.append(time.time())
        quick.append(self.focuser.Position)
        quick.append(self.focuser.Temperature)
        quick.append(self.focuser.IsMoving)
        return quick
    
    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0])/2, 3))
        average.append(round((pre[1] + post[1])/2, 3))
        average.append(round((pre[2] + post[2])/2, 3))
        if pre[3] or post[3]:
            average.append('T')
        else:
            average.append('F')            
        return average
    
    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "move_relative":
            self.move_relative_command(req, opt)
        elif action == "move_absolute":
            self.move_absolute_command(req, opt)
        elif action == "go_to_reference":
            reference = ptr_config.get_focal_ref('gf01')
            self.focuser.Move(reference)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')
        elif action == "go_to_compensated":
            reference = self.calculate_compensation( self.focuser.Temperature)
            self.focuser.Move(reference)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')
        elif action == "save_as_reference":
            ptr_config.set_focal_ref('gf01', self.focuser.Position)  #Need to get the alias properly
        else:
            print(f"Command <{action}> not recognized:", command)


    ###############################
    #       Focuser Commands      #
    ###############################

    def move_relative_command(self, req: dict, opt: dict):
        ''' set the focus position by moving relative to current position '''
        #The string must start with a + or a - sign, otherwize treated as zero and no action.
        position_string = req['position']
        position = self.focuser.Position
        if position_string[0] != '-':
            relative = int(position_string)
            position += relative
            self.focuser.Move(position)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')
        elif position_string[0] =='-':
            relative = int(position_string[1:])
            position -= relative
            self.focuser.Move(position)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')            
        else:
            print('Supplied relativemove is lacking a sign; ignoring.')
        #print(f"focuser cmd: move_relative:  ", req, opt)
    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"focuser cmd: move_absolute:  ", req, opt)
        position = int(req['position'])
        self.focuser.Move(position)
        time.sleep(0.1)
        while self.focuser.IsMoving:
            time.sleep(0.5)
            print('>')
        #Here we could spin until the move is completed, simplifying other devices.  Since normally these are short moves,
        #that may make the most sense to keep things seperated.
        '''
        A new seek *may* cause a mount move, a filter,l rotator, and focus change.  How do we launch all of these in parallel, then
        send status until each completes, then move on to exposing?
        
        '''
    def stop_command(self, req: dict, opt: dict):
        ''' stop focuser movement '''
        print(f"focuser cmd: stop")
    def home_command(self, req: dict, opt: dict):
        ''' set the focuser to the home position'''
        print(f"focuser cmd: home")
    def auto_command(self, req: dict, opt: dict):
        ''' autofocus '''
        print(f"focuser cmd: auto")
        
if __name__ == '__main__':
    pass
        
    