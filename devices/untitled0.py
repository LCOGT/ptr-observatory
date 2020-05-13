# -*- coding: utf-8 -*-
"""
Created on Tue May 12 22:11:28 2020

@author: obs
"""

def create_simple_sequence(exp_time=0, img_type=0, speed=1, suffix='',repeat=0, \
                    readout_mode="RAW", filter_name='air', enabled=1, \
                    binning=1, binmode=0):

    proto_file = open('D:\\archive\\archive\\kb01\\seq\\ptr_saf_2.pro')
    proto = proto_file.readlines()
    proto_file.close()
    proto[62] = proto[62][:9]  + str(exp_time) + proto[62][10:]
    proto[65] = proto[65][:9]  + str(img_type) + proto[65][10:]
    proto[58] = proto[58][:12] + str(suffix)   + proto[58][12:]
    breakpoint()
    proto[56] = proto[56][:10] + str(speed)    + proto[56][12:]
    proto[37] = proto[37][:11] + str(repeat)   + proto[37][12:]
    proto[33] = proto[33][:17] + readout_mode  + proto[33][17:]
    proto[15] = proto[15][:12] + filter_name   + proto[15][12:]
    proto[11] = proto[11][:12] + str(enabled)  + proto[11][13:]
    proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
    proto_file = open('D:\\archive\\archive\\kb01\\seq\\ptr_saf.seq', 'w')
    breakpoint()
    for item in range(len(proto)):
        proto_file.write(proto[item])
    proto_file.close()
    breakpoint()


create_simple_sequence(exp_time=1.2, img_type=2, speed=0, suffix='ex',repeat=2, \
                    readout_mode="RAW Mono", filter_name='W', enabled=1, \
                    binning=3, binmode=0)