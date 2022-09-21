# ptr-observatory

When complete, this code will operate observatories in the photon ranch network. 

## Installation and Setup

Boot up your Microsoft Windows machine.

Clone the repository. Install the python dependencies with `$ pip install -r requirements.txt`, preferably in a virtual environment.

Modify `config.py` as appropriate. Make sure to specify the correct ascom drivers for each device. These drivers should already be configured using the ascom device chooser.


## Usage

Run `obs.py`. Credentials will be verified with aws, ascom devices will connect, and finally the infinite loop of checking for commands to run and updating status.

This code is designed to take commands sent through the client web interface (not online yet). You can also send commands directly to api.photonranch.org. See the ptr-api repository readme for details.