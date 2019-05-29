import requests, os
from warrant import Cognito
from dotenv import load_dotenv
from os.path import join, dirname

class API_calls:

    def __init__(self): 

        # AWS cognito account info imported from .env
        dotenv_path = join(dirname(__file__), '.credentials')
        load_dotenv(dotenv_path)
        self.region = os.environ.get('REGION')
        self.userpool_id = os.environ.get('USERPOOL_ID')
        self.app_id_client = os.environ.get('APP_CLIENT_ID')
        self.app_client_secret = os.environ.get('APP_CLIENT_SECRET')
        self.username = os.environ.get('USERNAME')
        self.password = os.environ.get('PASS')

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

        self.api = "http://api.photonranch.org"

    def base_url(self, port):
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


    def get(self, uri, payload=None, port=5000):
        header = self.make_authenticated_header()
        if payload is None:
            response = requests.get(f"{self.base_url(port)}/{uri}", headers=header) 
        else:
            response = requests.get(f"{self.base_url(port)}/{uri}", data=json.dumps(payload), headers=header)
        return response.json()

    def put(self, uri, payload, port=5000):
        ''' Localhost put request at the specified uri and access token.

        Args: 
            uri (str): the part of the url after the port. Eg: 'site1/status/'.
            payload (dict): body that will be converted to a json string. 
            port (int): optional, specifies localhost port. 

        Return: 
            json response from the request.
        '''
        header = self.make_authenticated_header()
        response = requests.put(f"{self.base_url(port)}/{uri}", data=json.dumps(payload), headers=header) 
        return response.json()

    def post(self, uri, payload, port=5000):
        ''' Localhost post request at the specified uri and access token.

        Args: 
            uri (str): the part of the url after the port. Eg: 'site1/status/'.
            payload (dict): body that will be converted to a json string. 
            port (int): optional, specifies localhost port. 

        Return: 
            json response from the request.
        '''
        header = self.make_authenticated_header()
        response = requests.post(f"{self.base_url(port)}/{uri}", data=json.dumps(payload), headers=header) 
        return response.json()

        