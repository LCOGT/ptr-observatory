# -*- coding: utf-8 -*-
"""
Created on Tue May 12 22:11:28 2020

@author: obs
"""
# Default filter needs to be pulled from site camera or filter config
def create_simple_sequence(exp_time=0, img_type=0, speed=0, suffix='', repeat=1, \
                    readout_mode="RAW", filter_name='W', enabled=1, \
                    binning=1, binmode=0, column=1):
    exp_time = round(abs(float(exp_time)), 3)
    if img_type > 3:
        img_type = 0
    repeat = abs(int(repeat))
    if repeat < 1:
        repeat = 1
    binning = abs(int(binning))
    if binning > 4:
        binning = 4
    if filter_name == "":
        filter_name = 'W'
    proto_file = open('D:\\archive\\archive\\kb01\\seq\\ptr_saf.pro')
    proto = proto_file.readlines()
    proto_file.close()
    print(proto, '\n\n')
    if column == 1:
        proto[62] = proto[62][:9]  + str(exp_time) + proto[62][12:]
        proto[65] = proto[65][:9]  + str(img_type) + proto[65][10:]
        proto[58] = proto[58][:12] + str(suffix)   + proto[58][12:]
        proto[56] = proto[56][:10] + str(speed)    + proto[56][11:]
        proto[37] = proto[37][:11] + str(repeat)   + proto[37][12:]
        proto[33] = proto[33][:17] + readout_mode  + proto[33][20:]
        proto[15] = proto[15][:12] + filter_name   + proto[15][13:]
        proto[11] = proto[11][:12] + str(enabled)  + proto[11][13:]
        proto[1]  = proto[1][:12]  + str(binning)  + proto[1][13:]
    seq_file = open('D:\\archive\\archive\\kb01\\seq\\ptr_saf.seq', 'w')
    for item in range(len(proto)):
        seq_file.write(proto[item])
    seq_file.close()
    print(proto)


#  TEST  create_simple_sequence(exp_time=0, img_type=0, suffix='', repeat=1, \
#                       binning=3, filter_name='air')