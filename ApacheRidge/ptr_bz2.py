# -*- coding: utf-8 -*-
"""
Created on Tue Jun 25 23:02:14 2019

@author: wrosing
"""

import time
import bz2

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
