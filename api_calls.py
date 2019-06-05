import requests, os, json
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
        self.username = os.environ.get('SITE_USERNAME')
        self.password = os.environ.get('SITE_PASS')

        self.user = Cognito(self.userpool_id, 
                       self.app_id_client, 
                       client_secret=self.app_client_secret, 
                       username=self.username,
                       user_pool_region=self.region)
        try:
            print("Authenticating...")
            self.user.authenticate(password=self.password)
        except Exception as e:
            print(f"Unable to authenticate {self.username}.")
            print(e)

        self.api = "http://api.photonranch.org"

    def base_url(self):
        return "http://api.photonranch.org"
        #return "http://localhost:5000"

    def make_authenticated_header(self):
        header = {}
        try:
            self.user.check_token()
            header["Authorization"] = f"Bearer {self.user.access_token}"
        except AttributeError as e:
            print("Could not create authorization header.")
            print(e)
        return header


    def authenticated_request(self, method: str, uri: str, payload: dict = None) -> str:
        header = self.make_authenticated_header()

        # Populate the request parameters. Include data only if it was sent.
        request_kwargs = { 
            "method": method,
            "url": f"{self.base_url()}/{uri}",
            "headers": header,
        }
        if payload is not None: 
            request_kwargs["data"] = json.dumps(payload)

        #print(request_kwargs)
        response = requests.request(**request_kwargs)
        return response.json()


