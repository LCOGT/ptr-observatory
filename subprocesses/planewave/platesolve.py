import os.path
import platform
from subprocess import Popen, PIPE
import tempfile
import glob
from astropy.io import fits
from pathlib import Path
from os import getcwd
import traceback
import time
parentPath = Path(getcwd())

# Point this to the location of the "ps3cli.exe" executable
#PS3CLI_EXE = 'C:/Users/obs/Documents/GitHub/ptr-observatory/planewave/ps3cli/ps3cli.exe'

PS3CLI_EXE = str(parentPath).replace('\subprocesses','') +'/subprocesses/planewave/ps3cli/ps3cli.exe'

print (PS3CLI_EXE)

# For testing purposes...
#PS3CLI_EXE = r"C:\Users\kmi\Desktop\Planewave work\Code\PWGit\PWCode\ps3cli\bin\Debug\ps3cli.exe"


# Set this to the path where the PlateSolve catalogs are located.
# The directory specified here should contain "UC4" and "Orca" subdirectories.
# If this is None, we will try to use the default catalog location
PS3_CATALOG = None

def is_linux():
    return platform.system() == "Linux"

def get_default_catalog_location():
    if is_linux():
        return os.path.expanduser("~/Kepler")
    else:
        return os.path.expanduser("~\\Documents\\Kepler")
    


def platesolve(image_file, arcsec_per_pixel):

    stdout_destination = None  # Replace with PIPE if we want to capture the output rather than displaying on the console

    output_file_path = os.path.join(tempfile.gettempdir(), "ps3cli_results.txt")

    if PS3_CATALOG is None:
        catalog_path = get_default_catalog_location()
    else:
        catalog_path = PS3_CATALOG
    # print(PS3CLI_EXE,
    #       image_file,
    #       str(arcsec_per_pixel),
    #       output_file_path,
    #       catalog_path)
    #print (image_file)
    args = [
        PS3CLI_EXE,
        image_file,
        str(arcsec_per_pixel),
        output_file_path,
        catalog_path
    ]
    print (args)

    if is_linux():
        # Linux systems need to run ps3cli via the mono runtime,
        # so add that to the beginning of the command/argument list
        args.insert(0, "mono")

    process = Popen(
            args,
            #stdout=stdout_destination,
            stdout=None,
            stderr=PIPE
            )

    # Try with initial pixscale
    try:
        process = Popen(
                args,
                #stdout=stdout_destination,
                stdout=None,
                stderr=PIPE
                )
        (stdout, stderr) = process.communicate(timeout=30)  # Obtain stdout and stderr output from the wcs tool
        exit_code = process.wait() # Wait for process to complete and obtain the exit code
        failed = False
        time.sleep(1)
        process.kill()
        
    except:
        print ('failed')
        print (traceback.format_exc())
            
        failed = True
        exit_code = 5
    
    process.kill()
    
    #exit_code = process.wait()
    
    if failed:
        
        # Try again with a lower pixelscale... yes it makes no sense
        # But I didn't write PS3.exe ..... (MTF)        
        args = [
            PS3CLI_EXE,
            image_file,
            str(float(arcsec_per_pixel)/2.0),
            output_file_path,
            catalog_path
        ]
        
        print (args)
        process = Popen(
                args,
                #stdout=stdout_destination,
                stdout=None,
                stderr=PIPE
                )
        (stdout, stderr) = process.communicate(timeout=30)  # Obtain stdout and stderr output from the wcs tool
        exit_code = process.wait() # Wait for process to complete and obtain the exit code
        time.sleep(1)
        process.kill()

    process.kill()
    # print (exit_code)

    #breakpoint()

    if exit_code != 0:
        print ("Exit code: ")
        print (exit_code)
        if int(exit_code) == 2:
            print ("Error code 2 usually means the catalogues are not on the computer.")
            print ("They need to be installed in the users' Documents folder in a ")
            print ("Directory named Kepler")
        if int(exit_code) == 4:
            print ("Error code 4 is an error loading the image. This is usually the coders fault! Please report this!")
        if int(exit_code) == 1:
            print ("Error code 1 is an error with the provided command line options. This is usually the coders fault! Please report this!")
        if int(exit_code) == 3:
            print ("Error code 3 is a standard failure to get a star match. Usually because there aren't enough stars in the image.")
        
        #print ("Error output: ")
        #print (stderr)
        raise Exception("Error finding solution.\n")
                        #"Exit code: " + str(exit_code) + "\n" +
                        #"Error output: " + stderr)

    return parse_platesolve_output(output_file_path)

def parse_platesolve_output(output_file):
    f = open(output_file)

    results = {}

    for line in f.readlines():
        #print (line)
        line = line.strip()
        if line == "":
            continue

        fields = line.split("=")
        if len(fields) != 2:
            continue

        keyword, value = fields

        results[keyword] = float(value)

    return results

#if __name__ == '__main__':

#    file_list = glob.glob('C:/000ptr_saf/archive/sq01/20210502/reduced/*.f*t*')
#    file_list.sort()

#    for item in file_list:
#        try:
#            solve= platesolve(item, 0.5478)
#            img = fits.open(item)
#            hdr = img[0].header
#            breakpoint()
#            print(hdr['MNT-RA  '], hdr['MNT-DEC '], solve['ra_j2000_hours'], solve['dec_j2000_degrees'], hdr['MNT-SIDT'])
#        except:
#           print("Item did not solve:  ", item)


# Traceback (most recent call last):

#   File "<ipython-input-9-8939b03f1935>", line 2, in <module>
#     solve= platesolve(item, 0.5478)

# NameError: name 'platesolve' is not defined


# runfile('C:/Users/obs/Documents/GitHub/ptr-observatory/planewave/platesolve.py', wdir='C:/Users/obs/Documents/GitHub/ptr-observatory/planewave')

# for item in file_list:
#     solve= platesolve(item, 0.5478)
#     print(solve['ra_j2000_hours'], solve['dec_j2000_degrees'])