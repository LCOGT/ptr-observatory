wget -c --tries=inf https://s3.amazonaws.com/www.photonranch.org/Kepler.zip
tar -xf .\Kepler.zip
rmdir /s /q "%HOMEPATH%/Documents/Kepler"
move Kepler "%HOMEPATH%/Documents/"
del Kepler.zip