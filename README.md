# ptr-observatory

When complete, this code will operate observatories in the Photon Ranch network. 

## Installation and Setup

This code requires Python 3.8 or above. Clone the repository to your local Windows machine:

```
git clone https://github.com/LCOGT/ptr-observatory.git
cd ptr-observatory
```

Install the Python dependencies with `$ pip install -r requirements.txt`, preferably in a virtual environment.

Currently, this project does not run on Mac or Linux systems.

### Config Files

Modify `config.py` as appropriate. Make sure to specify the correct ASCOM drivers for each device. These drivers should already be configured using the ASCOM device chooser.



### ASCOM Drivers



## Usage

Run `obs.py`. Credentials will be verified with aws, ASCOM devices will connect, and finally the infinite loop of checking for commands to run and updating status.

This code is designed to take commands sent through the client web interface at [www.photonranch.org](www.photonranch.org). Alternatively, you can send commands directly to api.photonranch.org. See the [photonranch-api](https://github.com/LCOGT/photonranch-api) repository README for details.

