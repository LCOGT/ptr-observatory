import os, json, time
from warrant import Cognito
from dotenv import load_dotenv
from os.path import join, dirname

import asyncio
import aiohttp
from aiohttp import ClientSession

class API_calls:

    def __init__(self): 

        # AWS cognito account info imported from .env
        dotenv_path = join(dirname(__file__), '.credentials')
        load_dotenv(dotenv_path)
        self.region = os.environ.get('REGION')
        self.userpool_id = os.environ.get('USERPOOL_ID')
        self.app_id_client = os.environ.get('APP_CLIENT_ID')
        self.app_client_secret = os.environ.get('APP_CLIENT_SECRET')
        self.username = os.environ.get('SITE_USERNAME')
        self.password = os.environ.get('SITE_PASS')

        self.user = Cognito(self.userpool_id, 
                       self.app_id_client, 
                       client_secret=self.app_client_secret, 
                       username=self.username,
                       user_pool_region=self.region)
        try:
            self.user.authenticate(password=self.password)
        except Exception as e:
            print(f"Unable to authenticate {self.username}.")
            print(e)

        print('testing aiohttp')
        #asyncio.run(self.test())
        self._session = ClientSession()



    async def test(self):
        header = self.make_authenticated_header()
        async with ClientSession() as session:
            async with session.request(method="GET", url="http://api.photonranch.org/site4/status/", headers=header) as response:
                response = await response.json()
                print(response)

    def base_url(self):
        return "http://api.photonranch.org"

    def make_authenticated_header(self):
        header = {}
        try:
            self.user.check_token()
            header["Authorization"] = f"Bearer {self.user.access_token}"
        except AttributeError as e:
            print("Could not create authorization header.")
            print(e)
        return header

    

    async def api(self, method: str, uri: str, payload: dict = None) -> str:
        header = self.make_authenticated_header()

        #async with ClientSession() as session:

        # Populate the request parameters. Include data only if it was sent.
        request_kwargs = { 
            "method": method,
            "url": f"{self.base_url()}/{uri}",
            "headers": header,
        }
        if payload is not None: 
            request_kwargs["data"] = json.dumps(payload)

        async with self._session.request(**request_kwargs) as response:
            response = await response.json()
            return response


    def get(self, uri: str, payload: dict = None) -> str:
        header = self.make_authenticated_header()
        if payload is None:
            response = requests.get(
                f"{self.base_url()}/{uri}", 
                headers=header
            ) 
        else:
            response = requests.get(
                f"{self.base_url()}/{uri}", 
                data=json.dumps(payload), 
                headers=header
            )
        return response.json()

    def put(self, uri: str, payload: dict) -> str:
        ''' Localhost put request at the specified uri and access token.

        Args: 
            uri (str): the part of the url after the port. Eg: 'site1/status/'.
            payload (dict): body that will be converted to a json string. 
            port (int): optional, specifies localhost port. 

        Return: 
            json response from the request.
        '''
        header = self.make_authenticated_header()
        response = requests.put(
            f"{self.base_url()}/{uri}", 
            data=json.dumps(payload), 
            headers=header
        ) 
        return response.json()

    def post(self, uri: str, payload: dict) -> str:
        ''' Localhost post request at the specified uri and access token.

        Args: 
            uri (str): the part of the url after the port. Eg: 'site1/status/'.
            payload (dict): body that will be converted to a json string. 
            port (int): optional, specifies localhost port. 

        Return: 
            json response from the request.
        '''
        header = self.make_authenticated_header()
        response = requests.post(
            f"{self.base_url()}/{uri}", 
            data=json.dumps(payload), 
            headers=header
        ) 
        return response.json()

if __name__ == "__main__":
    a = API_calls()
        