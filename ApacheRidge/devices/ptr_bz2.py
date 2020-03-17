# -*- coding: utf-8 -*-
"""
Created on Tue Jun 25 23:02:14 2019

@author: wrosing
"""

import time

import os
import threading



import bz2


#from skimage import data, io, filters

from astropy.modeling import models
from astropy import units as u
from astropy import nddata
from astropy.io import fits
from astropy.io.fits import getheader



import ccdproc
from ccdproc import ImageFileCollection
from astropy.io.fits import getheader

from ccdproc import CCDData, Combiner
import sep




#raw = ccdproc.CCDData.read("C:\\Users\\wrosing\\Desktop\\all\\FOCUS10062.FIT", unit='adu')

#uc = open('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000059-E13.FITS', 'rb')
#uo = open('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000059-E13.FITS.bzip', 'wb')
#ucr = uc.read()
#ucc = bz2.compress(ucr)
#print(len(ucr), len(ucc))
#uo.write(ucc)
#uc.close()
#uo.close()
#
#ua = open('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000059-E13.FITS.bzip', 'rb')
#ub = open('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000059-E14.FITS', 'wb')
#uau = bz2.decompress(ua.read())
#ub.write(uau)
#ua.close()
#ub.close()

def to_bz2(filename, delete=False):
    try:
        uncomp = open(filename, 'rb')
        comp = bz2.compress(uncomp.read())
        uncomp.close()
        if delete:
            os.remove(filename)
        target = open(filename +'.bz2', 'wb')
        target.write(comp)
        target.close()
        return True
    except:
        print('to_bz2 failed.')
        return False
    
def from_bz2(filename, delete=False):
    try:
        comp = open(filename, 'rb')
        uncomp = bz2.decompress(comp.read())
        comp.close()
        if delete:
            os.remove(filename)
        target=open(filename[0:-4], 'wb')
        target.write(uncomp)
        target.close()
        return True
    except:
        print('from_bz2 failed.')
        return False    
    
if __name__ == '__main__':
    #to_bz2('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000064-E00.FITS')
    from_bz2('Q:\\archive\\ea03\\20190625\\to_AWS\\WMD-ea03-20190625-00000064-E00.FITS.bz2')
