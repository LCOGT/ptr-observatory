
# obs.py

import time, json
from random import randint
import threading
from api_calls import API_calls


class Observatory:

    update_status_period = 5 #seconds
    scan_for_tasks_period = 2

    def __init__(self, name): 
        self.api = API_calls()
        self.name = name

        self.run()

    def run(self):
        """
        Run two loops in separate threads:
        - Update status regularly to dynamodb.
        - Get commands from sqs and execute them.
        """
        threading.Thread(target=self.update_status).start()
        threading.Thread(target=self.scan_requests).start()


    def scan_requests(self):
        while True:
            uri = f"{self.name}/mount1/command/"
            cmd = json.loads(self.api.get(uri))

            if cmd == {'Body': 'empty'}:
                continue

            print(cmd)


    def update_status(self):
        pass
        #while True:
        #    m_status = json.loads(self.m.get_mount_status())
        #    c_status = json.loads(self.c.get_camera_status())

        #    status ={**m_status, **c_status}

        #    # Include index key/val: key 'State' with value 'State'.
        #    status['State'] = 'State'
        #    status['site'] = self.name
        #    status['timestamp'] = str(int(time.time()))
        #    try:
        #        self.d.insert_item(status)
        #    except:
        #        print("Error sending to dynamodb.")
        #        print("If this is a new site, dynamodb might still be initializing.") 
        #        print("Code will automatically retry until successful.")

        #    time.sleep(self.update_status_period)



if __name__=="__main__":
    Observatory("site4")
