import requests, os, json
from warrant import Cognito
from dotenv import load_dotenv
from os.path import join, dirname

class API_calls:

    def __init__(self): 

        self.api = "http://api.photonranch.org"

    def base_url(self):
        return "http://api.photonranch.org/api"

    def make_authenticated_header(self):
        header = {}
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


