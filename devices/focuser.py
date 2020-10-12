
import win32com.client
import time
import serial
from global_yard import g_dev
#import config_east as config
import shelve

import requests
import json



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


#  Unused except for WMD
def probeRead(com_port):
       with serial.Serial(com_port, timeout=0.3) as com:
           com.write(b'R1\n')
           probePosition = float(com.read(7).decode())*994.96 - 137 #Corrects Probe to Stage. Up and down, lash = 5000 enc.
           print(round(probePosition, 1))

class Focuser:

    def __init__(self, driver: str, name: str, config: dict):
        self.site = config['site']
        self.name = name
        self.site_path = config['site_path']
        self.camera_name = config['camera']['camera1']['name']
        g_dev['foc'] = self
        self.config = config['focuser']['focuser1']
        win32com.client.pythoncom.CoInitialize()
        self.focuser = win32com.client.Dispatch(driver)
        self.focuser.Connected = True
        self.focuser.TempComp = False
        self.micron_to_steps= float(config['focuser']['focuser1']['unit_conversion'])   #  Note tis can be a bogus value
        self.steps_to_micron = 1/self.micron_to_steps
        self.focuser_message = '-'
        print("focuser connected.")
        print(self.focuser.Description, "At:  ", round(self.focuser.Position*self.steps_to_micron, 1))
        try:   #  NB NB NB This mess neads cleaning up.
            try:

                self.reference = self.calculate_compensation( self.focuser.Temperature)   #need to change to config supplied
                print("Focus reference updated from Compensated value:  ", self.reference)
            except:
                self.reference = float(self.get_focal_ref())   #need to change to config supplied
                print("Focus reference updated from Night Shelf:  ", self.reference)
        except:
            self.reference = int(self.config['reference'])
            print("Focus reference derived from supplied Config dicitionary:  ", self.reference)
        self.focuser.Move(int(float(self.reference)*self.micron_to_steps))

    def calculate_compensation(self, temp_primary):

        if -5 <= temp_primary <= 45:
            # NB this math is awkward, should use delta_temp

            trial =round(-float(self.config['coef_c'])*temp_primary + float(self.config['coef_0']), 1)
            trial = max(trial,500)  #These values would change for Gemini to more like 11900 max
            trial = min(trial, 12150)
            print('Calculated focus compensated position:  ', trial)
            return int(trial)
        else:
            print('Primary out of range -5 to 45C, using reference focus')
            return float(self.config['reference'])

    def get_status(self):
        status = {
            "focus_position": round(self.focuser.Position*self.steps_to_micron, 1),
            "focus_moving": self.focuser.IsMoving
            #"focus_temperature": self.focuser.Temperature
            }
        try:
            status["focus_temperature"] = self.focuser.Temperature
        except:
            status['focus_temperature'] = self.reference
        return status

    def get_quick_status(self, quick):
        quick.append(time.time())
        quick.append(self.focuser.Position*self.steps_to_micron)
        quick.append(self.focuser.Temperature)
        quick.append(self.focuser.IsMoving)
        return quick

    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0])/2, 3))
        average.append(round((pre[1] + post[1])/2, 3))
        average.append(round((pre[2] + post[2])/2, 3))
        if pre[3] or post[3]:
            average.append(True)
        else:
            average.append(False)
        return average

    def update_job_status(self, cmd_id, status, seconds_remaining=-1):
        """
        Update the status of a job.
        Args:
            cmd_id (string): the ulid that identifies the job to update
            status (string): the new status (eg. "STARTED")
            seconds_remaining (int): time estimate until job is updated as "COMPLETE".
                Note: value of -1 used when no estimate is provided.
        """
        url = "https://jobs.photonranch.org/jobs/updatejobstatus"
        body = {
            "site": self.site,
            "ulid": cmd_id,
            "secondsUntilComplete": seconds_remaining,
            "newStatus": status,
        }
        response = requests.request('POST', url, data=json.dumps(body))
        print(response)
        return response


    def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']

        if action == "move_relative":
            # Mark a job as "STARTED" just before starting it.
            # Include a time estmiate if possible. This is sent to the UI.
            self.update_job_status(command['ulid'], 'STARTED', 5)

            # Do the command. Additional job updates can be sent in this function too.
            self.move_relative_command(req, opt)

            # Mark the job "COMPLETE" when finished.
            self.update_job_status(command['ulid'], 'COMPLETE')

        elif action == "move_absolute":
            self.update_job_status(command['ulid'], 'STARTED', 5)
            self.move_absolute_command(req, opt)
            self.update_job_status(command['ulid'], 'COMPLETE')
        elif action == "go_to_reference":
            self.update_job_status(command['ulid'], 'STARTED', 5)
            reference = self.get_focal_ref()
            self.focuser.Move(reference*self.micron_to_steps)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')
            self.update_job_status(command['ulid'], 'COMPLETE')
        elif action == "go_to_compensated":
            reference = self.calculate_compensation(self.focuser.Temperature)
            self.focuser.Move(reference*self.micron_to_steps)
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>')
        elif action == "save_as_reference":
            self.set_focal_ref(self.focuser.Position*self.steps_to_micron)  #Need to get the alias properly
        else:
            print(f"Command <{action}> not recognized:", command)


    ###############################
    #       Focuser Commands      #
    ###############################

    def get_position(self, counts=False):
        if not counts:
            return int(self.focuser.Position*self.steps_to_micron)

    def move_relative_command(self, req: dict, opt: dict):
        ''' set the focus position by moving relative to current position '''
        #The string must start with a + or a - sign, otherwize treated as zero and no action.

        position_string = req['position']
        position = int(self.focuser.Position*self.steps_to_micron)
        if position_string[0] != '-':
            relative = int(position_string)
            position += relative
            self.focuser.Move(int(position*self.micron_to_steps))
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>f++')
        elif position_string[0] =='-':
            relative = int(position_string[1:])
            position -= relative
            self.focuser.Move(int(position*self.micron_to_steps))
            time.sleep(0.1)
            while self.focuser.IsMoving:
                time.sleep(0.5)
                print('>f--')
        else:
            print('Supplied relativemove is lacking a sign; ignoring.')
        #print(f"focuser cmd: move_relative:  ", req, opt)
    def move_absolute_command(self, req: dict, opt: dict):
        ''' set the focus position by moving to an absolute position '''
        print(f"focuser cmd: move_absolute:  ", req, opt)
        position = int(req['position'])
        self.focuser.Move(int(position*self.micron_to_steps))
        time.sleep(0.1)
        while self.focuser.IsMoving:
            time.sleep(0.5)
            print('>f abs')
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

    def set_focal_ref(self, ref):
        camShelf = shelve.open(self.site_path + 'ptr_night_shelf/' + self.camera_name)
        camShelf['Focus Ref'] = ref
        camShelf['af_log'] = []
        camShelf.close()
        return
    
    def af_log(self, ref, fwhm, solved):
        camShelf = shelve.open(self.site_path + 'ptr_night_shelf/' + self.camera_name, writeback=True)
        camShelf['af_log'].append((ref, fwhm, solved, self.focuser.Temperature, time.time()))
        camShelf.close()
        return


    def get_focal_ref(self):
        camShelf = shelve.open(self.site_path + 'ptr_night_shelf/' + self.camera_name)
        focus_ref = camShelf['Focus Ref']
        camShelf.close()
        return focus_ref

if __name__ == '__main__':
    pass

