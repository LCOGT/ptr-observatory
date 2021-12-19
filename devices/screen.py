
import win32com.client
import time
import os
import subprocess
from global_yard import g_dev

class Screen(object):
    def __init__(self, driver: str, name: str, config):
        g_dev['scr'] = self
        self.config = config['screen']['screen1']
        self.device_name = name 
        win32com.client.pythoncom.CoInitialize()
        self.screen = win32com.client.Dispatch(driver)
        self.description = self.config['desc']
        self.screen.Connected=True
        #self.pC =  ' ' +self.driver.split('COM')[1]  #just last 0ne or two digits.
        #print('COM port used for Screen:  ' + self.driver)
        print("Screens may take a few seconds to process commands.")
        self.scrn = str ('Alnitak')
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        #C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller
        
        #subprocess.call('C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller/AACmd.exe' + self.pC + ' D s')
        #subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe' + self.pC + ' C')
        self.screen.CalibratorOff()
        self.status = 'Off'
        #self.screen.Calibrator)n(123))
        self.screen_message = '-'
        self.dark_setting = 'Screen is Off'
        self.bright_setting = 0.0
        self.minimum = 5
        self.saturate = 255    # NB should pick up from config
        self.screen_dark()
        #os.chdir(self.priorWd)

    def set_screen_bright(self, pBright, is_percent=False):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        if pBright <= 0:
            self.screen_dark()
        if is_percent:
            pBright = min(abs(pBright), 100)
            scrn_setting = int(pBright*self.saturate/100.)
        else:
            pBright = min(abs(pBright), self.saturate)
            scrn_setting = int(pBright)
        # subprocess.call('C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller/AACmd.exe'  + self.pC + \
        #                 ' b'+ str(scrn_setting) +'s' )        
        self.bright_setting = pBright
        #os.chdir(self.priorWd)
        print("Brightness set to:  ", scrn_setting)

    def screen_light_on(self):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        #subprocess.call('C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller/AACmd.exe'  + self.pC + ' L s')
        self.screen.CalibratorOn(self.bright_setting)
        self.dark_setting = 'Screen is On'
        #os.chdir(self.priorWd)

    def screen_dark(self):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        #subprocess.call('C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller/AACmd.exe'  + self.pC + ' D s')
        self.screen.CalibratorOff()
        self.dark_setting = 'Screen is Off'
        self.bright_setting = 0
        
    def screen_light_off(self):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        #subprocess.call('C:/Program Files (x86)/Optec/Alnitak Astrosystems Controller/AACmd.exe'  + self.pC + ' D s')
        self.screen.CalibratorOff()
        self.dark_setting = 'Screen is Off'
        self.bright_setting = 0
        #os.chdir(self.priorWd)

#   def openCover(self):
#       self.priorWd = os.getcwd()
#       os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
#       if self.scrn == 'WestAlnitak':
#           subprocess.call('aacmd.exe  ' + self.pC + ' O')
#       elif self.scrn == 'EastAlnitak':
#           subprocess.call('aacmd.exe  ' +self.pC + ' O')
#       elif self.scrn == 'EastFlipFlat':
#           subprocess.call('AACmd.exe  ' +self.pC + ' O')
#       self.status = 'open'
#       os.chdir(self.priorWd)
#
#   def closeCover(self):
#      self.priorWd = os.getcwd()
#      os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
#      if self.scrn == 'WestAlnitak':
#           subprocess.call('aacmd.exe  ' + self.pC + ' C')
#      elif self.scrn == 'EastAlnitak':
#           subprocess.call('aacmd.exe  ' + self.pC + ' C')
#      elif self.scrn == 'WestFlipFlat':
#          subprocess.call('AACmd.exe  ' + self.pC + ' C')
#      self.status = 'closed'
#      os.chdir(self.priorWd)




    def get_status(self):

        status = {
            "bright_setting": round(self.bright_setting, 1),
            "dark_setting": self.dark_setting
        }
        return status

    def parse_command(self, command):
        req = command['required_params']
        #opt = command['optional_params']
        action = command['action']
        if action == "turn_off":
            self.screen_dark()
        elif action == 'turn_on':
             bright = int(req['brightness'])
             self.set_screen_bright(bright)
             self. screen_light_on()
        else:
            print("Defective Screen Command", command)

if __name__== "__main__":

    sc = Screen('COM22', 'screen1')

