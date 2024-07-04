# -*- coding: utf-8 -*-
"""
Created on Tue Jun 25 18:49:23 2024

@author: observatory
"""
import requests
# Incorporate better request retry strategy
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))
from dotenv import load_dotenv
# The ingester should only be imported after environment variables are loaded in.
load_dotenv(".env")
import json
import shelve
import time
import shutil
from astropy.wcs import WCS
from PIL import Image
import matplotlib.pyplot as plt
from astropy import units as u
from astropy.visualization.wcsaxes import Quadrangle
import random
import numpy as np

def add_margin(pil_img, top, right, bottom, left, color):
    width, height = pil_img.size
    new_width = width + right + left
    new_height = height + top + bottom
    result = Image.new(pil_img.mode, (new_width, new_height), color)
    result.paste(pil_img, (left, top))
    return result

def authenticated_request(method: str, uri: str, payload: dict = None) -> str:

    # Populate the request parameters. Include data only if it was sent.
    base_url="https://api.photonranch.org/api"
    request_kwargs = {
        "method": method,
        "timeout" : 10,
        "url": f"{base_url}/{uri}",
    }
    if payload is not None:
        request_kwargs["data"] = json.dumps(payload)

    response = requests.request(**request_kwargs)
    return response.json()

timeperiod=60

# def next_sequence(pCamera):
#     global SEQ_Counter
#     camShelf = shelve.open("C:\ptr\eco2\ptr_night_shelf/" + pCamera + str('eco2'))
#     sKey = "Sequence"
#     try:
#         seq = camShelf[sKey]  # get an 8 character string
#     except:
#         print ("Failed to get seq key, starting from zero again")
#         seq=1
#     seqInt = int(seq)
#     seqInt += 1
#     seq = ("0000000000" + str(seqInt))[-8:]
#     camShelf["Sequence"] = seq
#     camShelf.close()
#     SEQ_Counter = seq
#     return seq

def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open("F:\ptr/aro1/ptr_night_shelf/" + pCamera + str('aro1'))
    sKey = "Sequence"
    try:
        seq = camShelf[sKey]  # get an 8 character string
    except:
        print ("Failed to get seq key, starting from zero again")
        seq=1
    seqInt = int(seq)
    seqInt += 1
    seq = ("0000000000" + str(seqInt))[-8:]
    camShelf["Sequence"] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

while True:

    #filename='eco2-ec002cs-20240625-00000004-EX10.jpg'
    filename='aro1-sq003ms-20240625-00000004-EX10.jpg'
    next_seq = next_sequence('sq003ms')
    newfilename=filename.split('-')
    newfilename[3]=str(next_seq)
    newfilename= newfilename[0] + '-' + newfilename[1] + '-' + newfilename[2] + '-' + newfilename[3] + '-' +newfilename[4]
    print (newfilename)
    # shutil.copy(filename, newfilename)
    filepath=newfilename






    target_ra=random.randint(0,3600) / 10 / 15

    RA_where_it_actually_is = target_ra + random.randint(0,100) / 100

    target_dec=random.randint(0,900) / 10

    DEC_where_it_actually_is =  target_dec + random.randint(0,100) / 100

    pointing_ra=target_ra+0.1

    pointing_dec=target_dec+0.1


    wcs_input_dict = {
    'CTYPE1': 'RA---TAN',
    'CUNIT1': 'deg',
    'CDELT1': -0.002777777778,
    'CRPIX1': 512,
    'CRVAL1': target_ra/15,
    'NAXIS1': 1024,
    'CTYPE2': 'DEC--TAN',
    'CUNIT2': 'deg',
    'CDELT2': 0.002777777778,
    'CRPIX2': 512,
    'CRVAL2': -target_dec,
    'NAXIS2': 1024
    }

    xfig=9
    yfig=7
    aspect=1/(9/7)
    #print (pointing_image.shape[0]/pointing_image.shape[1])
    plt.rcParams['figure.figsize'] = [xfig, yfig]
    wcs=WCS(wcs_input_dict)



    plt.rcParams["figure.facecolor"] = 'black'
    plt.rcParams["text.color"] = 'yellow'
    plt.rcParams["xtick.color"] = 'yellow'
    plt.rcParams["ytick.color"] = 'yellow'
    plt.rcParams["axes.labelcolor"] = 'yellow'
    plt.rcParams["axes.titlecolor"] = 'yellow'

    ax = plt.subplot(projection=wcs, facecolor='black')

    #fig.set_facecolor('black')
    ax.set_facecolor('black')
    pointing_image=np.random.rand(1024,1024)
    ax.imshow(pointing_image, origin='lower', cmap='gray')
    ax.grid(color='yellow', ls='solid')
    ax.set_xlabel('Right Ascension')
    ax.set_ylabel('Declination')

    print ([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is])

    ax.plot([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is],  linestyle='dashed',color='green',
          linewidth=2, markersize=12,transform=ax.get_transform('fk5'))
    # #ax.set_autoscale_on(False)

    # ax.plot([target_ra * 15,RA_where_it_actually_is * 15],[ target_dec, DEC_where_it_actually_is],  linestyle='dashed',color='white',
    #       linewidth=2, markersize=12,transform=ax.get_transform('fk5'))





    # This should point to the center of the box.
    ax.scatter(target_ra * 15, target_dec, transform=ax.get_transform('icrs'), s=300,
                edgecolor='red', facecolor='none')

    # ax.scatter(target_ra * 15, target_dec, transform=ax.get_transform('icrs'), s=300,
    #             edgecolor='white', facecolor='none')


    # This should point to the center of the current image
    ax.scatter(RA_where_it_actually_is * 15, DEC_where_it_actually_is, transform=ax.get_transform('icrs'), s=300,
                edgecolor='white', facecolor='none')

    # This should point to the where the telescope is reporting it is positioned.
    ax.scatter(pointing_ra * 15, pointing_dec, transform=ax.get_transform('icrs'), s=300,
                edgecolor='lime', facecolor='none')

    # r = Quadrangle((target_ra * 15 - 0.5 * y_deg_field_size, target_dec - 0.5 * x_deg_field_size)*u.deg, y_deg_field_size*u.deg, x_deg_field_size*u.deg,
    #                 edgecolor='red', facecolor='none',
    #                 transform=ax.get_transform('icrs'))

    y_deg_field_size=0.5
    x_deg_field_size=0.5

    r = Quadrangle((target_ra * 15 - 0.5 * y_deg_field_size, target_dec - 0.5 * x_deg_field_size)*u.deg, y_deg_field_size*u.deg, x_deg_field_size*u.deg,
                    edgecolor='red', facecolor='none',
                    transform=ax.get_transform('icrs'))


    # ax.add_patch(r)
    # ax.axes.set_aspect(aspect)
    # plt.axis('scaled')
    # plt.gca().set_aspect(aspect)

    # breakpoint()
    # plt.canvas.draw()
    # temp_canvas = plt.canvas
    # plt.close()
    # pil_image=Image.frombytes('RGB', temp_canvas.get_width_height(),  temp_canvas.tostring_rgb())

    # pil_image.save(jpeg_filename.replace('.jpg','temp.jpg'), keep_rgb=True)#, quality=95)
    # os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)

    plt.savefig(newfilename.replace('.jpg','matplotlib.png'), dpi=100, bbox_inches='tight', pad_inches=0)


    im = Image.open(newfilename.replace('.jpg','matplotlib.png'))

    # Get amount of padding to add
    fraction_of_padding=(im.size[0]/im.size[1])/aspect
    padding_added_pixels=int(((fraction_of_padding * im.size[1])- im.size[1])/2)
    if padding_added_pixels > 0:
        im=add_margin(im,padding_added_pixels,0,padding_added_pixels,0,(0,0,0))

    #im=ImageOps.grayscale(im)
    #breakpoint()
    im=im.convert('RGB')

    im.save(newfilename, keep_rgb=True)#, quality=95)
    #os.rename(jpeg_filename.replace('.jpg','temp.jpg'),jpeg_filename)




    #breakpoint()
    aws_resp = authenticated_request("POST", "/upload/", {"object_name": newfilename})
    with open(filepath, "rb") as fileobj:
        files = {"file": (filepath, fileobj)}
        #while True:
        try:
            reqs.post(aws_resp["url"], data=aws_resp["fields"], files=files, timeout=10)
        except Exception as e:
            if 'timeout' in str(e).lower() or 'SSLWantWriteError' or 'RemoteDisconnected' in str(e):
                print("Seems to have been a timeout on the file posted: " + str(e) + "Putting it back in the queue.")
                print(filename)
                #self.fast_queue.put(pri_image, block=False)
            else:
                print("Fatal connection glitch for a file posted: " + str(e))
                print(files)
                #print((traceback.format_exc()))
    time.sleep(timeperiod)