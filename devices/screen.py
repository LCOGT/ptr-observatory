
import win32com.client
import time
import os
import subprocess
from global_yard import g_dev

class Screen(object):
    def __init__(self, driver: str, name: str):
        self.name = name
        g_dev['scr'] = self
        self.driver = driver
        self.description = 'Optec Alnitak 24" screen'
        #self.priorWd = os.getcwd()
        self.pC =  ' ' +self.driver.split('COM')[1]  #just last 0ne or two digits.
        print('COM port used for Screen:  ' + self.driver)
        print("Screen takes a few seconds to process commands.")
        self.scrn = str ('EastAlnitak')
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe' + self.pC + ' D s')
        #subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe' + self.pC + ' C')
        self.status = 'Off'
        self.screen_message = '-'
        self.dark_setting = 'Screen is Off'
        self.bright_setting = 0.0
        self.minimum = 5
        self.saturate = 170    # NB should pick up from config
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
        subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe ' + self.pC + ' B s' + \
                        str(scrn_setting))
        self.bright_setting = pBright
        #os.chdir(self.priorWd)
        print("Brightness set to:  ", scrn_setting)

    def screen_light_on(self):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe ' + self.pC + ' L s')
        self.dark_setting = 'Screen is On'
        #os.chdir(self.priorWd)

    def screen_dark(self):
        #self.priorWd = os.getcwd()
        #os.chdir('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller')
        subprocess.call('C:\\Program Files (x86)\\Optec\\Alnitak Astrosystems Controller\\AACmd.exe ' + self.pC + ' D s')
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
            "bright_setting": str(round(self.bright_setting, 1)),
            "dark_setting": str(self.dark_setting).lower()
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

