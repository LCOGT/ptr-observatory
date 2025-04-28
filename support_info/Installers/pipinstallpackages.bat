conda update -y menuinst
conda install -y git
pip install -U python-dotenv
pip install -U colour-science colour_demosaicing
wget https://aka.ms/vs/17/release/vs_BuildTools.exe -O vsBuildTools.exe
.\vs_BuildTools.exe
del vsBuildTools.exe
pip install -U astropy==5.3.4 numpy scipy matplotlib==3.9.4 pandas fuzzytm
pip install -U streamlit
pip install -U sep
pip install -U Pillow
pip install -U astroalign
pip install -U redis
pip install -U requests
pip install -U ocs_ingester
pip install -U astroquery
pip install -U ephem
pip install -U pyowm
pip install -U pyserial
pip install -U xmltodict
pip install -U image_registration
pip install -U joblib
pip install -U photutils

pip install git+https://github.com/python-zwoasi/python-zwoasi