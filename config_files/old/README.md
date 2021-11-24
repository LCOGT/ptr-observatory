# Config files

Some config files are stored here for development convenience. Eventually, we should remove them from the master repository and include a template for users to fill out instead. 

For now, specify which config file to run with the `--config=<site>` argument. This will select the config file named `config_<site>.py`, where <site> is whatever the user submitted.

Currently, the default config option (running `python obs.py`) will load `config_wmd_eastpier`. 

To run the simulator config (called `config_simulator.py`), just run `python obs.py --config=simulator`.




