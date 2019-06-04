import win32com.client

class Mount:

    def __init__(self, driver: str):
        self.mount = win32com.client.Dispatch(driver)
        self.mount.Connected = True

        print(f"Mount connected.")
        print(self.mount.Description)

    def get_status(self):
        status = {"type":"mount"}
        return status

    async def parse_command(self, command):
        req = command['required_params']
        opt = command['optional_params']
        action = command['action']
        print(f"Mount command: {command}")